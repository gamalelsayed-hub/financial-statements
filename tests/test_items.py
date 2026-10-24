"""Items, customer master, item sales / purchases and annual comparisons on synthetic data (no real data)."""
from fsapp.system import annual as AN
from fsapp.system import draft as DR
from fsapp.system import item_reports as IR
from fsapp.system import items as I
from fsapp.system import render
from fsapp.system import reports as R
from fsapp.system.calc import Ctx
from tests.test_system import company  # noqa: F401  (fixture)

CLASS_A = ("مواد بناء", "مواد انشائية", "مسامير ومثبتات", "مسمار")
CLASS_B = ("أدوات", "أدوات وعدد", "لواصق", "شريط لاصق")


def items_rows():
    return [
        ["ملف الأصناف"], [], [],
        ["رقم الصنف", "اسم الصنف", "الوحدة", "المجموعة الرئيسية", "المجموعة الفرعية 1", "المجموعة الفرعية 2",
         "الصنف الرئيسي", "نوع الصنف", "نشاط الصنف"],
        ["01-00001", "مسمار صلب 3 سم شد 10", "علبه", *CLASS_A, "محلي", "يعمل"],
        ["01-00002", "شريط لاصق ازرق عريض", "حبه", *CLASS_B, "خارجي", "يعمل"],
        ["01-00003", "مسمار حديد 5 سم", "علبه", "غير مصنف", "غير مصنف", "غير مصنف", "غير مصنف", "محلي", "يعمل"],
        ["01-00004", "لاصق شريط ازرق رفيع", "حبه", None, None, None, None, "خارجي", "يعمل"],
        ["01-00005", "قطعة غريبة جدا", "حبه", "", "", "", "", "", ""],
    ]


def qty_rows():
    head = [None, None, None, None, None, None, "المبيعات", "", "", "مردود المبيعات", "", "", "صافي المبيعات", "",
            "", None]
    cols = ["رقم العميل", " ", "العملة", "رقم الصنف", "اسم الصنف", "الوحدة", "الكمية", "ك.المجانيه", "المبلغ",
            "الكمية", "ك.المجانيه", "المبلغ", "الكمية", "ك.المجانيه", "المبلغ", "مبلغ الصافي بالمحلي"]

    def r(cust, name, item, iname, q, free, amt, rq, ramt):
        return [cust, name, "SAR", item, iname, "حبه", q, free, amt, rq, 0, ramt, q - rq, free, amt - ramt, amt - ramt]

    return [head, cols,
            r("1001", "عميل أول", "01-00001", "مسمار", 10, 1, 1000, 0, 0),
            r("1001", "عميل أول", "01-00002", "شريط", 5, 0, 500, 1, 100),
            r("1002", "عميل ثاني", "01-00003", "مسمار حديد", 20, 0, 2000, 0, 0),
            r("1003", "عميل ثالث", "01-00005", "غريبة", 1, 0, 50, 0, 0)]


def cost_rows():
    # the net amount sits under an empty title, its own title column is empty (like the system export)
    return [["رقم الصنف", "اسم الصنف", None, "صافي الفاتورة بالمحلي ", "التكلفة", "هامش الربح - مبلغ",
             "نسبة الربح - نسبة(%)", "اسم العميل :"],
            ["01-00001", "مسمار", 1000, None, 700, 300, 42.8, "1001-عميل أول"],
            ["01-00002", "شريط", 400, None, 300, 100, 33.3, "1001-عميل أول"],
            ["01-00003", "مسمار حديد", 2000, None, 2100, -100, -4.7, "1002-عميل ثاني"]]


def test_items_classification_guess():
    its = I.read_items_sheets([("الأصناف", items_rows())])
    assert len(its) == 5 and sum(I.is_classified(r) for r in its) == 2
    n = I.guess_classes(its)
    by = {r["code"]: r for r in its}
    assert tuple(by["01-00003"][lv] for lv in I.LEVELS) == CLASS_A and by["01-00003"]["guessed"] == 1
    assert "مسمار" in by["01-00003"]["guess_from"]
    assert tuple(by["01-00004"][lv] for lv in I.LEVELS) == CLASS_B
    assert not I.is_classified(by["01-00005"])
    assert n == 2
    assert I.item_class(by, "01-00005") == (I.UNCLASSIFIED,) * 4


def test_sales_formats_and_merge():
    assert I.sales_format(qty_rows()) == "qty" and I.sales_format(cost_rows()) == "cost"
    q = I.parse_sales_qty(qty_rows())
    assert len(q) == 4
    r = q[1]
    assert (r["sales"], r["returns"], r["net"], r["ret_qty"], r["net_qty"]) == (500, 100, 400, 1, 4)
    assert q[0]["free_qty"] == 1
    c = I.parse_sales_cost(cost_rows())
    assert [x["cnet"] for x in c] == [1000, 400, 2000] and c[0]["cust_code"] == "1001"
    m = I.merge_sales(I.merge_sales([], q, "qty"), c, "cost")
    assert len(m) == 4
    one = next(x for x in m if x["item_code"] == "01-00001")
    assert one["net"] == 1000 and one["cost"] == 700
    # uploading the quantities again keeps the cost
    again = I.merge_sales(m, q, "qty")
    one = next(x for x in again if x["item_code"] == "01-00001")
    assert one["net"] == 1000 and one["cost"] == 700


def _load(db):
    its = I.read_items_sheets([("الأصناف", items_rows())])
    I.guess_classes(its)
    db.save_items(its)
    db.save_customer_master([
        {"code": "1001", "name": "عميل أول", "ctype": "اجل", "rep": "مندوب أ", "branch": "الفرع أ", "region": ""},
        {"code": "1002", "name": "عميل ثاني", "ctype": "نقدي", "rep": "مندوب ب", "branch": "الفرع ب", "region": "الوسطى"},
    ])
    m = I.merge_sales(I.merge_sales([], I.parse_sales_qty(qty_rows()), "qty"), I.parse_sales_cost(cost_rows()), "cost")
    db.save_item_sales("2026-03", m)
    # February: customer 1004 bought, nothing in March → stopped
    feb = [dict(x, cust_code="1004", cust_name="عميل متوقف") for x in I.parse_sales_qty(qty_rows())[:1]]
    db.save_item_sales("2026-02", I.merge_sales([], feb, "qty"))
    db.save_currencies([("SAR", 1), ("USD", 3.75)])
    db.save_item_purchases("2026-03", [
        {"supp_no": "10001", "supp_name": "مورد محلي", "currency": "SAR", "item_code": "01-00001", "item_name": "",
         "unit": "علبه", "qty": 10, "net": 600},
        {"supp_no": "20001", "supp_name": "مورد خارجي", "currency": "USD", "item_code": "01-00002", "item_name": "",
         "unit": "حبه", "qty": 100, "net": 100},
        {"supp_no": "40001", "supp_name": "مورد خدمات", "currency": "SAR", "item_code": "01-00009", "item_name": "خدمة",
         "unit": "", "qty": 1, "net": 50},
    ])


def test_item_reports(company, tmp_path):  # noqa: F811
    db = company
    _load(db)
    ctx = Ctx(db)
    p = R.Params(end="2026-03", n=1, comp="prev")
    d = IR.data(ctx, ["2026-03"])
    assert abs(d.total - (1000 + 400 + 2000 + 50)) < 0.01
    info = {r["cust_code"]: r for r in d.rows}
    assert info["1001"]["rep"] == "مندوب أ" and info["1001"]["region"] == "المنطقة"   # region from the branch list
    assert info["1002"]["region"] == "الوسطى" and info["1003"]["rep"] == "بدون مندوب"
    g = R.build("it_groups", ctx, p)
    main = {r.label: r.values for r in g.blocks[0].rows}
    assert abs(main["مواد بناء"][0] - 3000) < 0.01                         # guessed «مسمار حديد» joins its group
    assert abs(main["الإجمالي"][4] - 300) < 0.01                           # profit (3400 − 3100)
    m = R.build("it_margin", ctx, p)
    tot = {r.label: r.values[0] for r in m.blocks[0].rows}
    assert tot["التكلفة"] == 3100 and abs(tot["مجمل الربح"] - 300) < 0.01
    lost = R.build("it_lost", ctx, p)
    assert lost.blocks[0].rows[0].label == "1004"
    pu = R.build("it_purch", ctx, p)
    types = {r.label: r.values for r in pu.blocks[0].rows}
    assert types["الموردون الخارجيون"][2] == 375                           # 100 USD × 3.75
    assert types["موردو الخدمات وأخرى"][2] == 50 and types["الإجمالي"][2] == 1025
    p2 = R.Params(end="2026-03", n=1, comp="prev", supp_view="total")
    assert len(R.build("it_purch", ctx, p2).blocks) < len(pu.blocks)
    reps = [R.build(k, ctx, p) for k, _, _ in IR.ITEM_REPORTS]
    render.reports_html(reps, ctx.company)
    render.write_excel(reps, ctx.company, str(tmp_path / "items.xlsx"))
    # a month without item data
    empty = R.build("it_groups", ctx, R.Params(end="2026-01"))
    assert "لا توجد" in empty.blocks[0].text


def _annual_2025(db):
    """A full-year 2025 trial balance that closes into the synthetic company's January 2026 opening."""
    jan = db.tb("2026-01")
    pl = {c for c in jan if c[0] in "45"}
    pl_val = {c: ((jan[c][3] or 0) - (jan[c][4] or 0)) * 12 * 0.9 for c in pl}
    s = sum(pl_val.values())
    close = {c: (r[1] or 0) - (r[2] or 0) for c, r in jan.items() if c not in pl}
    close["3201"] -= s
    open_ = {c: v * 0.9 for c, v in close.items()}
    open_["3201"] = 0
    open_["3201"] = -sum(open_.values())
    rows = []
    for c in jan:
        o = open_.get(c, 0.0)
        cl = close[c] if c not in pl else pl_val[c]
        mv = cl - o
        rows.append((c, jan[c][0], max(o, 0), max(-o, 0), max(mv, 0), max(-mv, 0), max(cl, 0), max(-cl, 0)))
    return rows, pl_val


def test_annual_comparisons(company, tmp_path):  # noqa: F811
    db = company
    rows, pl_val = _annual_2025(db)
    db.save_annual_tb("2025-12", rows)
    db.save_annual_branch("2025-12", "الفرع أ", [("4101", "مبيعات", pl_val["4101"] * 0.6)])
    ctx = Ctx(db)
    assert ctx.periods == ["2026-01", "2026-02", "2026-03"]           # annual data never shows up as a month
    assert ctx.full_years() == ["2025-12"]
    c, months, src = ctx.year_source("2025-12")
    assert src == "annual" and months == ["2025-12"]
    f = c.is_figures(months)
    assert abs(f["net_sales"] - (-(pl_val["4101"] + pl_val["4102"]))) < 0.01
    assert abs(c.bs_figures(months, 2)["diff"]) < 0.01
    p = R.Params(end="2026-03")
    ys, partial = AN.years(ctx, p)
    assert [y.key for y in ys] == ["2025-12"] and partial is not None and partial.months == 3
    rep = R.build("an_is", ctx, p)
    sales_row = next(r for r in rep.blocks[0].rows if r.label == "صافي المبيعات")
    assert abs(sales_row.values[0] - f["net_sales"]) < 0.01
    assert abs(sales_row.values[-1] - ctx.is_figures(["2026-01", "2026-02", "2026-03"])["net_sales"]) < 0.01
    # the draft comparative uses the full-year trial balance of 2025
    dr = DR.build(ctx, "2026-03")
    assert dr.comp.end == "2025-12" and dr.comp.is_ is not None
    assert abs(DR.bs_totals(dr.comp.bs)["diff"]) < 0.01
    assert dr.cf_comp is not None and abs(dr.cf_comp["diff"]) < 0.01
    # a second year → growth and CAGR
    rows24 = [(c, n, od * 0.8, oc * 0.8, md * 0.8, mc * 0.8, cd * 0.8, cc * 0.8) for c, n, od, oc, md, mc, cd, cc in rows]
    db.save_annual_tb("2024-12", rows24)
    db.save_annual_tb("2023-12", [(c, n, od * 0.5, oc * 0.5, md * 0.5, mc * 0.5, cd * 0.5, cc * 0.5)
                                  for c, n, od, oc, md, mc, cd, cc in rows])
    ctx = Ctx(db)
    rep = R.build("an_is", ctx, p)
    sales_row = next(r for r in rep.blocks[0].rows if r.label == "صافي المبيعات")
    assert abs(sales_row.values[3] - 0.25) < 1e-9                      # 2025 / 2024 = 1 / 0.8
    assert abs(sales_row.values[4] - ((1 / 0.5) ** 0.5 - 1)) < 1e-9     # CAGR 2023 → 2025
    assert AN.growth(-150, -120) == 0.25 and abs(AN.cagr(-50, -200, 2) - 1) < 1e-9
    reps = [R.build(k, ctx, p) for k, _, _ in AN.ANNUAL_REPORTS]
    trend = reps[3]
    assert trend.blocks[0].rows[0].values[-1] == "نمو مستمر"
    render.reports_html(reps, ctx.company)
    render.write_excel(reps, ctx.company, str(tmp_path / "annual.xlsx"))


def test_year_end_tb_entered_as_month_counts_as_a_year(company):  # noqa: F811
    db = company
    rows, _ = _annual_2025(db)
    db.save_tb("2025-12", rows)
    ctx = Ctx(db)
    assert ctx.year_source("2025-12")[2] == "year_end"
    assert "2025-12" in ctx.full_years()


def test_purchases_pdf_words():
    assert I.fix_word("مقر") == "رقم"
    assert I.fix_word("١٠٠٦٥") == "10065"
    assert I.fix_word("(١٢٠)ساقم") == "مقاس(120)"
    assert I.supplier_type("20166") == "خارجي"
    rows = [["رقم المورد", "اسم المورد", "العملة", "رقم الصنف", "اسم الصنف", "الوحدة", "الكمية", "صافي المبلغ"],
            ["20001", "مورد", "USD", "01-00002", "شريط", "حبه", "100", "1,000.50"]]
    first, m = I.guess_purchase_cols(rows)
    out = I.read_purchases(rows, first, m)
    assert out[0]["net"] == 1000.5 and out[0]["qty"] == 100 and out[0]["currency"] == "USD"
    assert I.purchase_base(out[0], {"USD": 3.75}, "SAR") == 1000.5 * 3.75
