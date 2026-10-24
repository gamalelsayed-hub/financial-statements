"""Item reports: sales by item classification, top items and ABC, profitability, customers, reps / branches /
regions, returns and free quantities, customers who stopped buying, purchases by supplier type and purchases
against sales. Built from the monthly item sales / purchases uploads of the report period."""
from collections import defaultdict

from . import aging as AG
from . import items as I
from .blocks import Para, Report, Row, Table
from .calc import MONTHS_AR, month_add, range_label, safe_div

NO_DATA = ("لا توجد مبيعات أصناف للفترة — ارفع ملف مبيعات الأصناف بالعميل للشهر من «البيانات الشهرية» "
           "← «📥 مبيعات الأصناف».")


# ------------------------------------------------------------------ data
class Data:
    """Sales rows of the months, each with its classification and customer info."""

    def __init__(self, ctx, months):
        self.months = [m for m in months]
        self.items = _cached(ctx, "items", lambda: ctx.db.items())
        self.cust = _cached(ctx, "cust_info", lambda: I.customer_info(ctx.db))
        self.rows = ctx.db.item_sales(self.months) if self.months else []
        for r in self.rows:
            r["val"] = r["net"] if r["net"] is not None else (r["cnet"] or 0.0)
            r["cls"] = I.item_class(self.items, r["item_code"])
            c = self.cust.get(r["cust_code"], {})
            r["rep"] = c.get("rep") or "بدون مندوب"
            r["branch"] = c.get("branch") or "غير محدد"
            r["region"] = c.get("region") or "غير محدد"
            r["ctype"] = c.get("ctype") or "غير محدد"
            if not r.get("cust_name"):
                r["cust_name"] = c.get("name", "")
            it = self.items.get(r["item_code"])
            if it and it.get("name"):
                r["item_name"] = it["name"]
        self.total = sum(r["val"] for r in self.rows)
        self.has_cost = any(r["cost"] is not None for r in self.rows)


def _cached(ctx, key, fn):
    cache = ctx.__dict__.setdefault("_item_cache", {})
    if key not in cache:
        cache[key] = fn()
    return cache[key]


def data(ctx, months):
    cache = ctx.__dict__.setdefault("_item_cache", {})
    key = ("data", tuple(months or ()))
    if key not in cache:
        cache[key] = Data(ctx, months or [])
    return cache[key]


class Agg:
    __slots__ = ("val", "qty", "sales", "returns", "ret_qty", "free", "cnet", "cost", "custs", "items", "months",
                 "name", "extra")

    def __init__(self):
        self.val = self.qty = self.sales = self.returns = self.ret_qty = self.free = self.cnet = self.cost = 0.0
        self.custs, self.items, self.months = set(), set(), set()
        self.name, self.extra = "", {}

    def add(self, r):
        self.val += r["val"]
        self.qty += r["net_qty"] or 0.0
        self.sales += r["sales"] or 0.0
        self.returns += r["returns"] or 0.0
        self.ret_qty += r["ret_qty"] or 0.0
        self.free += r["free_qty"] or 0.0
        if r["cost"] is not None:
            self.cost += r["cost"]
            self.cnet += r["cnet"] if r["cnet"] is not None else (r["net"] or 0.0)
        self.custs.add(r["cust_code"])
        self.items.add(r["item_code"])
        self.months.add(r["period"])

    @property
    def profit(self):
        return self.cnet - self.cost if self.cnet or self.cost else None

    @property
    def margin(self):
        return safe_div(self.profit, self.cnet) if self.cnet else None


def group(rows, key):
    out = defaultdict(Agg)
    for r in rows:
        k = key(r)
        out[k].add(r)
    return out


def _subtitle(p, cmp_months):
    s = range_label(p.months())
    if cmp_months:
        s += f" — المقارنة: {range_label(cmp_months)}"
    return s


def _cmp(ctx, p):
    m = p.comp_months()
    return data(ctx, m) if m else None


def _missing_note(d, p):
    have = {r["period"] for r in d.rows}
    miss = [m for m in p.months() if m not in have]
    if miss and have:
        return Para("⚠ شهور بدون مبيعات أصناف في الفترة: " + "، ".join(range_label([m]) for m in miss), "warn")
    return None


def _no_data(key, title, p):
    return Report(key, title, range_label(p.months()), [Para(NO_DATA, "warn")])


def _chg(a, b):
    if b is None or abs(b) < 1e-9:
        return None
    return (a - b) / abs(b)


# ------------------------------------------------------------------ 1. by classification
def rpt_it_groups(ctx, p):
    d = data(ctx, p.months())
    if not d.rows:
        return _no_data("it_groups", "المبيعات حسب مجموعات الأصناف", p)
    c = _cmp(ctx, p)
    cmp_total = c.total if c and c.rows else None
    cols = ["البند", "صافي المبيعات", "% من الإجمالي", "عدد الأصناف", "عدد العملاء", "مجمل الربح", "هامش الربح"]
    fmts = ["n", "%", "d", "d", "n", "%"]
    if cmp_total is not None:
        cols += ["المقارنة", "التغير %"]
        fmts += ["n", "%"]

    def vals(a, b=None):
        v = [a.val, safe_div(a.val, d.total), len(a.items), len(a.custs), a.profit, a.margin]
        if cmp_total is not None:
            v += [b.val if b else 0.0, _chg(a.val, b.val if b else None)]
        return v

    # summary by main group
    main = group(d.rows, lambda r: r["cls"][0])
    main_c = group(c.rows, lambda r: r["cls"][0]) if cmp_total is not None else {}
    rows = [Row(k, vals(a, main_c.get(k))) for k, a in sorted(main.items(), key=lambda x: -x[1].val)]
    tot = Agg()
    for r in d.rows:
        tot.add(r)
    ctot = Agg()
    for r in (c.rows if cmp_total is not None else []):
        ctot.add(r)
    rows.append(Row("الإجمالي", vals(tot, ctot), "tot"))
    blocks = [Table(cols, rows, fmts, title="حسب المجموعة الرئيسية")]

    # the full tree: main group → sub group 1 → sub group 2 → main item
    tree = []
    level_kind = ["sub", "item", "item", "item"]
    indent = ["", "   ", "      ", "         • "]

    def walk(rows_, depth, prefix_c):
        g = group(rows_, lambda r: r["cls"][depth])
        gc = group(prefix_c, lambda r: r["cls"][depth]) if cmp_total is not None else {}
        for k, a in sorted(g.items(), key=lambda x: -x[1].val):
            sub_rows = [r for r in rows_ if r["cls"][depth] == k]
            sub_c = [r for r in prefix_c if r["cls"][depth] == k]
            tree.append(Row(indent[depth] + k, vals(a, gc.get(k)), level_kind[depth]))
            if depth < 3 and not (k == I.UNCLASSIFIED):
                walk(sub_rows, depth + 1, sub_c)

    walk(d.rows, 0, c.rows if cmp_total is not None else [])
    tree.append(Row("الإجمالي", vals(tot, ctot), "tot"))
    blocks.append(Table(cols, tree, fmts, title="التصنيف بالتفصيل: المجموعة الرئيسية ← الفرعية 1 ← الفرعية 2 ← الصنف الرئيسي"))
    unc = main.get(I.UNCLASSIFIED)
    if unc:
        blocks.append(Para(f"«غير مصنف»: {len(unc.items)} صنف بمبيعات {unc.val:,.0f} ({safe_div(unc.val, d.total):.1%}) — "
                           "صنّفها من «الأصناف والعملاء» ← قائمة الأصناف.", "warn"))
    if not d.has_cost:
        blocks.append(Para("مجمل الربح يظهر بعد رفع ملف «مبيعات الأصناف بالتكلفة» لنفس الشهر."))
    note = _missing_note(d, p)
    if note:
        blocks.append(note)
    return Report("it_groups", "المبيعات حسب مجموعات الأصناف", _subtitle(p, p.comp_months() if cmp_total else None),
                  blocks)


# ------------------------------------------------------------------ 2. top items and ABC
def abc(items_aggs, total):
    """{item: 'A'|'B'|'C'} — A up to 80% of sales, B up to 95%, C the rest."""
    out, cum = {}, 0.0
    for k, a in sorted(items_aggs.items(), key=lambda x: -x[1].val):
        share = safe_div(cum, total) or 0.0
        out[k] = "A" if share < 0.80 else "B" if share < 0.95 else "C"
        cum += a.val
    return out


def rpt_it_top(ctx, p):
    d = data(ctx, p.months())
    if not d.rows:
        return _no_data("it_top", "أعلى الأصناف وتحليل ABC", p)
    its = group(d.rows, lambda r: r["item_code"])
    names = {r["item_code"]: (r["item_name"], r["unit"], r["cls"]) for r in d.rows}
    cls = abc(its, d.total)
    summ = []
    for k, label in (("A", "A — تمثل 80% من المبيعات"), ("B", "B — الـ 15% التالية"), ("C", "C — آخر 5%")):
        keys = [i for i, c in cls.items() if c == k]
        v = sum(its[i].val for i in keys)
        summ.append(Row(label, [len(keys), safe_div(len(keys), len(its)), v, safe_div(v, d.total)]))
    summ.append(Row("الإجمالي", [len(its), 1.0, d.total, 1.0], "tot"))
    rows, cum = [], 0.0
    for code, a in sorted(its.items(), key=lambda x: -x[1].val)[:50]:
        cum += a.val
        n, unit, c = names[code]
        rows.append(Row(code, [n, c[0], c[3], unit, a.qty, a.val, safe_div(a.val, d.total), safe_div(cum, d.total),
                               cls[code], len(a.custs), a.margin]))
    blocks = [Table(["الفئة", "عدد الأصناف", "% من الأصناف", "صافي المبيعات", "% من المبيعات"], summ,
                    ["d", "%", "n", "%"], title="تحليل ABC"),
              Table(["رقم الصنف", "اسم الصنف", "المجموعة الرئيسية", "الصنف الرئيسي", "الوحدة", "صافي الكمية",
                     "صافي المبيعات", "% من الإجمالي", "التراكمي", "الفئة", "عدد العملاء", "هامش الربح"], rows,
                    ["t", "t", "t", "t", "n", "n", "%", "%", "t", "d", "%"], title="أعلى 50 صنفًا")]
    # main items (the level above the item) by sales
    mi = group(d.rows, lambda r: r["cls"][3])
    mrows = [Row(k, [a.val, safe_div(a.val, d.total), len(a.items), a.margin])
             for k, a in sorted(mi.items(), key=lambda x: -x[1].val)[:30]]
    blocks.append(Table(["الصنف الرئيسي", "صافي المبيعات", "% من الإجمالي", "عدد الأصناف", "هامش الربح"], mrows,
                        ["n", "%", "d", "%"], title="أعلى 30 صنفًا رئيسيًا"))
    note = _missing_note(d, p)
    if note:
        blocks.append(note)
    return Report("it_top", "أعلى الأصناف وتحليل ABC", range_label(p.months()), blocks)


# ------------------------------------------------------------------ 3. profitability
def rpt_it_margin(ctx, p):
    d = data(ctx, p.months())
    rows_c = [r for r in d.rows if r["cost"] is not None]
    if not rows_c:
        return Report("it_margin", "ربحية الأصناف", range_label(p.months()), [Para(
            "لا توجد تكلفة للفترة — ارفع ملف «مبيعات الأصناف بالعميل (المبيعات والتكلفة)» من «📥 مبيعات الأصناف».",
            "warn")])
    tot = Agg()
    for r in rows_c:
        tot.add(r)
    blocks = [Table(["البيان", "القيمة"], [
        Row("صافي المبيعات (في ملف التكلفة)", [tot.cnet]), Row("التكلفة", [tot.cost]),
        Row("مجمل الربح", [tot.profit], "sub"), Row("هامش الربح", [tot.margin], fmt="%"),
        Row("عدد الأصناف", [len(tot.items)], fmt="d"), Row("عدد العملاء", [len(tot.custs)], fmt="d")], ["n"],
        title="الإجمالي")]
    cols = ["البند", "صافي المبيعات", "التكلفة", "مجمل الربح", "هامش الربح", "% من مجمل الربح"]
    fm = ["n", "n", "n", "%", "%"]
    for lv, title in ((0, "حسب المجموعة الرئيسية"), (1, "حسب المجموعة الفرعية 1"), (3, "حسب الصنف الرئيسي (أعلى 25)")):
        g = group(rows_c, lambda r, lv=lv: r["cls"][lv])
        items_ = sorted(g.items(), key=lambda x: -(x[1].profit or 0))
        if lv == 3:
            items_ = items_[:25]
        rows = [Row(k, [a.cnet, a.cost, a.profit, a.margin, safe_div(a.profit, tot.profit)], styles=[
            "", "", "", "bad" if (a.margin or 0) < 0 else "", ""]) for k, a in items_]
        blocks.append(Table(cols, rows, fm, title=title))
    its = group(rows_c, lambda r: r["item_code"])
    names = {r["item_code"]: r["item_name"] for r in rows_c}
    icols = ["رقم الصنف", "اسم الصنف", "صافي المبيعات", "التكلفة", "مجمل الربح", "هامش الربح"]
    ifm = ["t", "n", "n", "n", "%"]
    best = sorted(its.items(), key=lambda x: -(x[1].profit or 0))[:20]
    blocks.append(Table(icols, [Row(k, [names[k], a.cnet, a.cost, a.profit, a.margin]) for k, a in best], ifm,
                        title="أعلى 20 صنفًا في مجمل الربح"))
    floor = tot.cnet * 0.002
    low = sorted([x for x in its.items() if x[1].cnet >= floor and x[1].margin is not None],
                 key=lambda x: x[1].margin)[:20]
    blocks.append(Table(icols, [Row(k, [names[k], a.cnet, a.cost, a.profit, a.margin],
                                    styles=["", "", "", "", "bad" if a.margin < 0 else "warn"]) for k, a in low], ifm,
                        title="أقل 20 صنفًا في هامش الربح (من الأصناف المؤثرة: 0.2% من المبيعات فأكثر)"))
    loss = [x for x in its.items() if (x[1].profit or 0) < -0.5]
    if loss:
        blocks.append(Para(f"⚠ {len(loss)} صنف يُباع بأقل من التكلفة — خسارة {-sum(a.profit for _, a in loss):,.0f}.",
                           "warn"))
    cu = group(rows_c, lambda r: r["cust_code"])
    cnames = {r["cust_code"]: (r["cust_name"], r["rep"]) for r in rows_c}
    crow = [Row(k, [cnames[k][0], cnames[k][1], a.cnet, a.profit, a.margin])
            for k, a in sorted(cu.items(), key=lambda x: -(x[1].profit or 0))[:20]]
    blocks.append(Table(["رقم العميل", "اسم العميل", "المندوب", "صافي المبيعات", "مجمل الربح", "هامش الربح"], crow,
                        ["t", "t", "n", "n", "%"], title="أعلى 20 عميلًا في مجمل الربح"))
    return Report("it_margin", "ربحية الأصناف", range_label(p.months()), blocks)


# ------------------------------------------------------------------ 4. customers
def rpt_it_customers(ctx, p):
    d = data(ctx, p.months())
    if not d.rows:
        return _no_data("it_customers", "مبيعات الأصناف حسب العملاء", p)
    c = _cmp(ctx, p)
    cg = group(c.rows, lambda r: r["cust_code"]) if c and c.rows else None
    g = group(d.rows, lambda r: r["cust_code"])
    info = {r["cust_code"]: r for r in d.rows}
    cols = ["رقم العميل", "اسم العميل", "النوع", "المندوب", "الفرع", "صافي المبيعات", "% من الإجمالي", "التراكمي",
            "عدد الأصناف", "هامش الربح"]
    fm = ["t", "t", "t", "t", "n", "%", "%", "d", "%"]
    if cg is not None:
        cols += ["المقارنة", "التغير %"]
        fm += ["n", "%"]
    rows, cum = [], 0.0
    for k, a in sorted(g.items(), key=lambda x: -x[1].val)[:40]:
        cum += a.val
        r = info[k]
        v = [r["cust_name"], r["ctype"], r["rep"], r["branch"], a.val, safe_div(a.val, d.total), safe_div(cum, d.total),
             len(a.items), a.margin]
        if cg is not None:
            b = cg.get(k)
            v += [b.val if b else 0.0, _chg(a.val, b.val if b else None)]
        rows.append(Row(k, v))
    n = len(g)
    top10 = sum(a.val for _, a in sorted(g.items(), key=lambda x: -x[1].val)[:10])
    blocks = [Table(cols, rows, fm, title="أعلى 40 عميلًا"),
              Para(f"عدد العملاء المشترين: {n} — أعلى 10 عملاء = {safe_div(top10, d.total) or 0:.1%} من المبيعات "
                   f"(تركّز {'مرتفع' if (safe_div(top10, d.total) or 0) > 0.5 else 'مقبول'}).")]
    t = group(d.rows, lambda r: r["ctype"])
    blocks.append(Table(["نوع العميل", "عدد العملاء", "صافي المبيعات", "% من الإجمالي", "هامش الربح"],
                        [Row(k, [len(a.custs), a.val, safe_div(a.val, d.total), a.margin])
                         for k, a in sorted(t.items(), key=lambda x: -x[1].val)], ["d", "n", "%", "%"],
                        title="حسب نوع العميل"))
    unknown = [k for k in g if k not in d.cust]
    if unknown:
        blocks.append(Para(f"ℹ {len(unknown)} عميل غير موجود في «بيانات العملاء» ولا في أعمار العملاء — "
                           "مندوبه وفرعه غير محدد. أضفهم من «الأصناف والعملاء» ← بيانات العملاء.", "warn"))
    return Report("it_customers", "مبيعات الأصناف حسب العملاء", _subtitle(p, p.comp_months() if cg else None), blocks)


# ------------------------------------------------------------------ 5. rep / branch / region
def rpt_it_reps(ctx, p):
    d = data(ctx, p.months())
    if not d.rows:
        return _no_data("it_reps", "المبيعات حسب المندوب والفرع والمنطقة", p)
    c = _cmp(ctx, p)
    has_c = bool(c and c.rows)
    blocks = []
    for key, title in (("region", "المنطقة"), ("branch", "الفرع"), ("rep", "المندوب")):
        g = group(d.rows, lambda r, k=key: r[k])
        gc = group(c.rows, lambda r, k=key: r[k]) if has_c else {}
        cols = [title, "عدد العملاء", "عدد الأصناف", "صافي المبيعات", "% من الإجمالي", "متوسط العميل", "مجمل الربح",
                "هامش الربح", "المردودات", "نسبة المردودات"]
        fm = ["d", "d", "n", "%", "n", "n", "%", "n", "%"]
        if has_c:
            cols += ["المقارنة", "التغير %"]
            fm += ["n", "%"]
        rows = []
        for k, a in sorted(g.items(), key=lambda x: -x[1].val):
            v = [len(a.custs), len(a.items), a.val, safe_div(a.val, d.total), safe_div(a.val, len(a.custs)), a.profit,
                 a.margin, a.returns, safe_div(a.returns, a.sales)]
            if has_c:
                b = gc.get(k)
                v += [b.val if b else 0.0, _chg(a.val, b.val if b else None)]
            rows.append(Row(k, v))
        tot = Agg()
        for r in d.rows:
            tot.add(r)
        v = [len(tot.custs), len(tot.items), tot.val, 1.0, safe_div(tot.val, len(tot.custs)), tot.profit, tot.margin,
             tot.returns, safe_div(tot.returns, tot.sales)]
        if has_c:
            v += [c.total, _chg(tot.val, c.total)]
        rows.append(Row("الإجمالي", v, "tot"))
        blocks.append(Table(cols, rows, fm, title=f"حسب {title}"))
    # rep × main group
    reps = group(d.rows, lambda r: r["rep"])
    mains = [k for k, _ in sorted(group(d.rows, lambda r: r["cls"][0]).items(), key=lambda x: -x[1].val)][:8]
    rows = []
    for rep, a in sorted(reps.items(), key=lambda x: -x[1].val):
        by = group([r for r in d.rows if r["rep"] == rep], lambda r: r["cls"][0])
        rows.append(Row(rep, [by[m].val if m in by else 0.0 for m in mains] + [a.val]))
    blocks.append(Table(["المندوب"] + mains + ["الإجمالي"], rows, title="المندوب × المجموعة الرئيسية"))
    blocks.append(Para("المندوب والفرع والمنطقة من «بيانات العملاء» برقم العميل (وإن لم يوجد فمن آخر أعمار عملاء "
                       "مرفوعة، والمنطقة من الفرع في الإعدادات)."))
    return Report("it_reps", "المبيعات حسب المندوب والفرع والمنطقة", _subtitle(p, p.comp_months() if has_c else None),
                  blocks)


# ------------------------------------------------------------------ 6. returns and free quantities
def rpt_it_returns(ctx, p):
    d = data(ctx, p.months())
    if not d.rows:
        return _no_data("it_returns", "المردودات والكميات المجانية", p)
    tot = Agg()
    for r in d.rows:
        tot.add(r)
    blocks = [Table(["البيان", "القيمة"], [
        Row("إجمالي المبيعات", [tot.sales]), Row("المردودات", [tot.returns]),
        Row("صافي المبيعات", [tot.sales - tot.returns], "sub"),
        Row("نسبة المردودات", [safe_div(tot.returns, tot.sales)], fmt="%"),
        Row("الكميات المجانية (كل الوحدات)", [tot.free]),
        Row("أصناف لها كمية مجانية", [len({r['item_code'] for r in d.rows if (r['free_qty'] or 0) > 0})], fmt="d")],
        ["n"], title="الإجمالي")]
    its = group(d.rows, lambda r: r["item_code"])
    names = {r["item_code"]: (r["item_name"], r["unit"]) for r in d.rows}
    ret = sorted([x for x in its.items() if x[1].returns > 0], key=lambda x: -x[1].returns)[:20]
    blocks.append(Table(["رقم الصنف", "اسم الصنف", "الوحدة", "كمية المردود", "المردودات", "المبيعات", "نسبة المردود"],
                        [Row(k, [names[k][0], names[k][1], a.ret_qty, a.returns, a.sales, safe_div(a.returns, a.sales)])
                         for k, a in ret], ["t", "t", "n", "n", "n", "%"], title="أعلى 20 صنفًا في المردودات"))
    cu = group(d.rows, lambda r: r["cust_code"])
    cn = {r["cust_code"]: (r["cust_name"], r["rep"]) for r in d.rows}
    cret = sorted([x for x in cu.items() if x[1].returns > 0], key=lambda x: -x[1].returns)[:20]
    blocks.append(Table(["رقم العميل", "اسم العميل", "المندوب", "المردودات", "المبيعات", "نسبة المردود"],
                        [Row(k, [cn[k][0], cn[k][1], a.returns, a.sales, safe_div(a.returns, a.sales)])
                         for k, a in cret], ["t", "t", "n", "n", "%"], title="أعلى 20 عميلًا في المردودات"))
    free = sorted([x for x in its.items() if x[1].free > 0], key=lambda x: -x[1].free)[:20]
    if free:
        blocks.append(Table(["رقم الصنف", "اسم الصنف", "الوحدة", "الكمية المجانية", "صافي الكمية المباعة",
                             "المجاني ÷ المباع"],
                            [Row(k, [names[k][0], names[k][1], a.free, a.qty, safe_div(a.free, a.qty)]) for k, a in free],
                            ["t", "t", "n", "n", "%"], title="الكميات المجانية"))
    return Report("it_returns", "المردودات والكميات المجانية", range_label(p.months()), blocks)


# ------------------------------------------------------------------ 7. stopped / new / declining customers
def rpt_it_lost(ctx, p):
    months = p.months()
    d = data(ctx, months)
    if not d.rows:
        return _no_data("it_lost", "العملاء المتوقفون عن الشراء والجدد", p)
    prior = [month_add(months[0], -i) for i in range(6, 0, -1)]
    pd = data(ctx, prior)
    have_prior = sorted({r["period"] for r in pd.rows})
    if not have_prior:
        return Report("it_lost", "العملاء المتوقفون عن الشراء والجدد", range_label(months), [Para(
            "يلزم مبيعات أصناف لشهور قبل الفترة (حتى 6 أشهر) للمقارنة.", "warn")])
    cur = group(d.rows, lambda r: r["cust_code"])
    old = group(pd.rows, lambda r: r["cust_code"])
    info = {**{r["cust_code"]: r for r in pd.rows}, **{r["cust_code"]: r for r in d.rows}}
    n_prior = len(have_prior)
    stopped = sorted([(k, a) for k, a in old.items() if k not in cur], key=lambda x: -x[1].val)
    srows = [Row(k, [info[k]["cust_name"], info[k]["rep"], info[k]["branch"], range_label([max(a.months)]),
                     len(a.months), a.val / n_prior]) for k, a in stopped[:60]]
    blocks = [Table(["رقم العميل", "اسم العميل", "المندوب", "الفرع", "آخر شهر شراء", "شهور الشراء",
                     "متوسط الشراء الشهري"], srows, ["t", "t", "t", "t", "d", "n"],
                    title=f"اشتروا في {range_label(have_prior)} ولم يشتروا في الفترة ({len(stopped)} عميل)")]
    lost_val = sum(a.val / n_prior for _, a in stopped) * len(months)
    blocks.append(Para(f"المبيعات المفقودة التقديرية للفترة: {lost_val:,.0f} (متوسطهم الشهري × عدد شهور الفترة)."))
    decl = []
    for k, a in cur.items():
        if k in old:
            expected = old[k].val / n_prior * len(months)
            if expected > 0 and a.val < expected * 0.5:
                decl.append((k, a, expected))
    decl.sort(key=lambda x: -(x[2] - x[1].val))
    blocks.append(Table(["رقم العميل", "اسم العميل", "المندوب", "المتوقع (حسب المتوسط)", "الفعلي", "نسبة الفعلي"],
                        [Row(k, [info[k]["cust_name"], info[k]["rep"], e, a.val, safe_div(a.val, e)])
                         for k, a, e in decl[:40]], ["t", "t", "n", "n", "%"],
                        title=f"تراجع أكثر من 50% عن متوسطهم ({len(decl)} عميل)"))
    new = sorted([(k, a) for k, a in cur.items() if k not in old], key=lambda x: -x[1].val)
    blocks.append(Table(["رقم العميل", "اسم العميل", "المندوب", "الفرع", "صافي المبيعات", "عدد الأصناف"],
                        [Row(k, [info[k]["cust_name"], info[k]["rep"], info[k]["branch"], a.val, len(a.items)])
                         for k, a in new[:40]], ["t", "t", "t", "n", "d"],
                        title=f"عملاء جدد أو عائدون (لم يشتروا في الشهور السابقة) — {len(new)} عميل"))
    by_rep = defaultdict(lambda: [0, 0.0, 0])
    for k, a in stopped:
        by_rep[info[k]["rep"]][0] += 1
        by_rep[info[k]["rep"]][1] += a.val / n_prior
    for k, _ in new:
        by_rep[info[k]["rep"]][2] += 1
    blocks.append(Table(["المندوب", "المتوقفون", "متوسط شرائهم الشهري", "الجدد"],
                        [Row(k, v) for k, v in sorted(by_rep.items(), key=lambda x: -x[1][1])], ["d", "n", "d"],
                        title="حسب المندوب"))
    return Report("it_lost", "العملاء المتوقفون عن الشراء والجدد", range_label(months), blocks)


# ------------------------------------------------------------------ 8. purchases by supplier type
def _purchases(ctx, months):
    rows = ctx.db.item_purchases(months) if months else []
    rates, base = AG.rates(ctx.db), ctx.base_currency
    items = _cached(ctx, "items", lambda: ctx.db.items())
    for r in rows:
        r["base"] = I.purchase_base(r, rates, base)
        r["type"] = AG.supplier_type(r["supp_no"])
        r["cls"] = I.item_class(items, r["item_code"])
        r["no_rate"] = (r.get("currency") or base).upper() not in (base, *rates)
    return rows


def rpt_it_purch(ctx, p):
    rows = _purchases(ctx, p.months())
    if not rows:
        return Report("it_purch", "مشتريات الأصناف حسب المورد", range_label(p.months()), [Para(
            "لا توجد مشتريات أصناف للفترة — ارفع تقرير «إجمالي المشتريات حسب الموردين والأصناف» (PDF أو Excel) من "
            "«📥 مشتريات الأصناف».", "warn")])
    base = ctx.base_currency
    total = sum(r["base"] for r in rows)
    trows = []
    for t in AG.SUPPLIER_TYPES:
        rs = [r for r in rows if r["type"] == t]
        v = sum(r["base"] for r in rs)
        trows.append(Row(AG.TYPE_TITLES[t], [len({r["supp_no"] for r in rs}), len({r["item_code"] for r in rs}), v,
                                             safe_div(v, total)]))
    trows.append(Row("الإجمالي", [len({r["supp_no"] for r in rows}), len({r["item_code"] for r in rows}), total, 1.0],
                     "tot"))
    blocks = [Table(["نوع المورد", "عدد الموردين", "عدد الأصناف", f"صافي المشتريات ({base})", "% من الإجمالي"], trows,
                    ["d", "d", "n", "%"], title="حسب نوع المورد — رقم المورد: 1 محلي، 2 خارجي، غيره خدمات وأخرى")]
    detailed = (p.supp_view or "type") == "type"
    sup = defaultdict(lambda: {"name": "", "cur": "", "net": 0.0, "base": 0.0, "items": set(), "type": ""})
    for r in rows:
        s = sup[r["supp_no"]]
        s["name"], s["cur"], s["type"] = r["supp_name"], r["currency"], r["type"]
        s["net"] += r["net"] or 0.0
        s["base"] += r["base"]
        s["items"].add(r["item_code"])
    cols = ["رقم المورد", "اسم المورد", "العملة", "المبلغ بالعملة", f"المبلغ ({base})", "% من الإجمالي", "عدد الأصناف"]
    fm = ["t", "t", "n", "n", "%", "d"]
    if detailed:
        for t in AG.SUPPLIER_TYPES:
            ss = sorted([(k, s) for k, s in sup.items() if s["type"] == t], key=lambda x: -x[1]["base"])
            if ss:
                blocks.append(Table(cols, [Row(k, [s["name"], s["cur"], s["net"], s["base"], safe_div(s["base"], total),
                                                   len(s["items"])]) for k, s in ss], fm, title=AG.TYPE_TITLES[t]))
    else:
        ss = sorted(sup.items(), key=lambda x: -x[1]["base"])
        blocks.append(Table(cols[:2] + ["النوع"] + cols[2:],
                            [Row(k, [s["name"], s["type"], s["cur"], s["net"], s["base"], safe_div(s["base"], total),
                                     len(s["items"])]) for k, s in ss], ["t", "t"] + fm[1:], title="كل الموردين"))
    g = defaultdict(lambda: {t: 0.0 for t in AG.SUPPLIER_TYPES})
    for r in rows:
        g[r["cls"][0]][r["type"]] += r["base"]
    blocks.append(Table(["المجموعة الرئيسية"] + AG.SUPPLIER_TYPES + ["الإجمالي", "% من الإجمالي"],
                        [Row(k, [v[t] for t in AG.SUPPLIER_TYPES] + [sum(v.values()), safe_div(sum(v.values()), total)])
                         for k, v in sorted(g.items(), key=lambda x: -sum(x[1].values()))],
                        ["n", "n", "n", "n", "%"], title="حسب المجموعة الرئيسية ونوع المورد"))
    if any(r["no_rate"] for r in rows):
        blocks.append(Para("⚠ عملات بدون سعر صرف في الإعدادات — احتُسبت بدون تحويل.", "warn"))
    blocks.append(Para(f"المبالغ بالعملة الأجنبية (مثل الدولار للموردين الخارجيين) محولة إلى {base} بسعر الصرف في الإعدادات."))
    return Report("it_purch", "مشتريات الأصناف حسب المورد", range_label(p.months()), blocks)


# ------------------------------------------------------------------ 9. purchases against sales
def rpt_it_pvs(ctx, p):
    d = data(ctx, p.months())
    pur = _purchases(ctx, p.months())
    if not d.rows and not pur:
        return _no_data("it_pvs", "المشتريات مقابل المبيعات", p)
    s_it = group(d.rows, lambda r: r["item_code"])
    p_it = defaultdict(lambda: {"qty": 0.0, "base": 0.0, "unit": "", "name": "", "cls": None})
    for r in pur:
        x = p_it[r["item_code"]]
        x["qty"] += r["qty"] or 0.0
        x["base"] += r["base"]
        x["unit"], x["name"], x["cls"] = r["unit"], r["item_name"], r["cls"]
    names = {r["item_code"]: (r["item_name"], r["unit"], r["cls"]) for r in d.rows}
    g = defaultdict(lambda: [0.0, 0.0, 0.0])
    for k, a in s_it.items():
        g[names[k][2][0]][0] += a.val
        g[names[k][2][0]][2] += a.cost if a.cost else 0.0
    for k, x in p_it.items():
        g[x["cls"][0]][1] += x["base"]
    grows = [Row(k, [v[0], v[1], v[1] - v[0], safe_div(v[1], v[0])]) for k, v in
             sorted(g.items(), key=lambda x: -max(x[1][0], x[1][1]))]
    grows.append(Row("الإجمالي", [sum(v[0] for v in g.values()), sum(v[1] for v in g.values()),
                                  sum(v[1] - v[0] for v in g.values()),
                                  safe_div(sum(v[1] for v in g.values()), sum(v[0] for v in g.values()))], "tot"))
    blocks = [Table(["المجموعة الرئيسية", "صافي المبيعات", "المشتريات", "الفرق", "المشتريات ÷ المبيعات"], grows,
                    ["n", "n", "n", "%"], title="حسب المجموعة الرئيسية (القيمة)")]
    codes = sorted(set(s_it) | set(p_it), key=lambda k: -max(s_it[k].val if k in s_it else 0, p_it[k]["base"]
                                                               if k in p_it else 0))[:50]
    rows = []
    for k in codes:
        s = s_it.get(k)
        pp = p_it.get(k)
        name = names[k][0] if k in names else pp["name"]
        su = names[k][1] if k in names else ""
        pu = pp["unit"] if pp else ""
        rows.append(Row(k, [name, su, s.qty if s else 0.0, s.val if s else 0.0, pu, pp["qty"] if pp else 0.0,
                            pp["base"] if pp else 0.0,
                            "✓" if not su or not pu or I.norm(su) == I.norm(pu) else "⚠ وحدة مختلفة"]))
    blocks.append(Table(["رقم الصنف", "اسم الصنف", "وحدة البيع", "الكمية المباعة", "صافي المبيعات", "وحدة الشراء",
                         "الكمية المشتراة", "المشتريات", "الوحدة"], rows, ["t", "t", "n", "n", "t", "n", "n", "t"],
                        title="أعلى 50 صنفًا"))
    only_p = [k for k in p_it if k not in s_it]
    if only_p:
        blocks.append(Para(f"ℹ {len(only_p)} صنف اشتُري في الفترة ولم يُبع منه شيء."))
    blocks.append(Para("قارن الكميات فقط عندما تكون وحدة البيع والشراء واحدة (مثلًا الشراء بالكرتون والبيع بالحبة)."))
    return Report("it_pvs", "المشتريات مقابل المبيعات", range_label(p.months()), blocks)


# ------------------------------------------------------------------ 10. monthly by main group
def rpt_it_monthly(ctx, p):
    months = ctx.year_months(p.end)
    d = data(ctx, [m for m in months if m <= p.end])
    if not d.rows:
        return _no_data("it_monthly", "مبيعات المجموعات شهريًا", p)
    have = sorted({r["period"] for r in d.rows})
    by = defaultdict(lambda: defaultdict(float))
    for r in d.rows:
        by[r["cls"][0]][r["period"]] += r["val"]
    cols = ["المجموعة الرئيسية"] + [MONTHS_AR[int(m[5:7]) - 1] for m in months] + ["الإجمالي", "المتوسط الشهري",
                                                                                    "% من الإجمالي"]
    rows = []
    for k, v in sorted(by.items(), key=lambda x: -sum(x[1].values())):
        t = sum(v.values())
        rows.append(Row(k, [v.get(m) if m in have else None for m in months] + [t, t / len(have), safe_div(t, d.total)]))
    totm = defaultdict(float)
    for r in d.rows:
        totm[r["period"]] += r["val"]
    rows.append(Row("الإجمالي", [totm.get(m) if m in have else None for m in months] +
                    [d.total, d.total / len(have), 1.0], "tot"))
    fm = ["n"] * (len(months) + 2) + ["%"]
    reps = defaultdict(lambda: defaultdict(float))
    for r in d.rows:
        reps[r["rep"]][r["period"]] += r["val"]
    rrows = [Row(k, [v.get(m) if m in have else None for m in months] + [sum(v.values()), sum(v.values()) / len(have),
                                                                          safe_div(sum(v.values()), d.total)])
             for k, v in sorted(reps.items(), key=lambda x: -sum(x[1].values()))]
    return Report("it_monthly", "مبيعات الأصناف شهريًا", f"السنة المنتهية {range_label([months[-1]])}",
                  [Table(cols, rows, fm, title="حسب المجموعة الرئيسية"),
                   Table(["المندوب"] + cols[1:], rrows, fm, title="حسب المندوب")])


ITEM_REPORTS = [
    ("it_groups", "المبيعات حسب مجموعات الأصناف", rpt_it_groups),
    ("it_top", "أعلى الأصناف وتحليل ABC", rpt_it_top),
    ("it_margin", "ربحية الأصناف", rpt_it_margin),
    ("it_customers", "مبيعات الأصناف حسب العملاء", rpt_it_customers),
    ("it_reps", "المبيعات حسب المندوب والفرع والمنطقة", rpt_it_reps),
    ("it_returns", "المردودات والكميات المجانية", rpt_it_returns),
    ("it_lost", "العملاء المتوقفون عن الشراء والجدد", rpt_it_lost),
    ("it_monthly", "مبيعات الأصناف شهريًا", rpt_it_monthly),
    ("it_purch", "مشتريات الأصناف حسب المورد", rpt_it_purch),
    ("it_pvs", "المشتريات مقابل المبيعات", rpt_it_pvs),
]
