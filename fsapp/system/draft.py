"""Draft financial statements in the company's own format (financial position, comprehensive income, cash flows)
with notes showing the accounts behind every line, from the trial balances in the program.

The program's FS items are more detailed than the published lines, so each FS item is mapped to a draft line
(sensible defaults, editable and saved in the company file). Current period = start of the fiscal year → selected
month; comparative = end of the previous fiscal year.
"""
import json
from dataclasses import dataclass, field

from .calc import month_add
from .defaults import ASSET_SECTIONS, BS_SECTIONS, IS_SECTIONS

# (key, label, section, activity) — activity drives the cash flow statement:
# CASH, OP (working capital), OP2 (provisions paid, after "cash from operations"), PPE, INV, FIN, RET (retained)
BS_LINES = [
    ("cash", "نقد لدى البنوك", "CA", "CASH"),
    ("trade_rec", "ذمم مدينة تجارية", "CA", "OP"),
    ("other_rec", "ذمم مدينة وموجودات متداولة أخرى", "CA", "OP"),
    ("rp_from", "مستحق على أطراف ذات علاقة", "CA", "OP"),
    ("inventory", "مخزون", "CA", "OP"),
    ("ppe", "ممتلكات وآلات ومعدات", "NCA", "PPE"),
    ("rou", "موجودات حق الاستخدام", "NCA", "INV"),
    ("investments", "استثمارات", "NCA", "INV"),
    ("other_nca", "موجودات غير متداولة أخرى", "NCA", "INV"),
    ("st_fin", "تسهيلات ومرابحات بنكية قصيرة الأجل", "CL", "FIN"),
    ("cur_loans", "أقساط متداولة من القروض طويلة الأجل", "CL", "FIN"),
    ("trade_pay", "ذمم دائنة تجارية", "CL", "OP"),
    ("other_pay", "ذمم دائنة ومستحقات أخرى", "CL", "OP"),
    ("rp_to", "مستحق لأطراف ذات علاقة", "CL", "OP"),
    ("lease_cur", "التزامات عقود إيجار — الجزء المتداول", "CL", "FIN"),
    ("zakat_prov", "مخصص الزكاة", "CL", "OP2"),
    ("lt_fin", "تسهيلات ومرابحات بنكية طويلة الأجل", "NCL", "FIN"),
    ("eosb", "التزامات المنافع المحددة للموظفين", "NCL", "OP2"),
    ("lease_nc", "التزامات عقود إيجار — الجزء غير المتداول", "NCL", "FIN"),
    ("other_ncl", "مطلوبات غير متداولة أخرى", "NCL", "FIN"),
    ("capital", "رأس المال", "EQ", "FIN"),
    ("reserve", "احتياطي نظامي", "EQ", "FIN"),
    ("owners", "جاري الشركاء", "EQ", "FIN"),
    ("retained", "أرباح مبقاة", "EQ", "RET"),
    ("reval", "ناتج إعادة تقييم أصول", "EQ", "PPE"),
]
# (key, label, nature) nature: rev = income shown positive, exp = expense shown positive
IS_LINES = [
    ("sales", "صافي المبيعات", "rev"),
    ("cogs", "تكلفة المبيعات", "exp"),
    ("selling", "مصروفات بيعية وتسويقية", "exp"),
    ("admin", "مصروفات عمومية وإدارية", "exp"),
    ("finance", "مصاريف تمويلية", "exp"),
    ("invest", "إيراد استثمار عقاري", "rev"),
    ("other", "إيرادات ومصاريف أخرى", "rev"),
    ("zakat", "الزكاة", "exp"),
]
BS_LABEL = {k: lbl for k, lbl, *_ in BS_LINES}
IS_LABEL = {k: lbl for k, lbl, _ in IS_LINES}
BS_SECTION = {k: s for k, _, s, _ in BS_LINES}
BS_ACTIVITY = {k: a for k, _, _, a in BS_LINES}
IS_NATURE = {k: n for k, _, n in IS_LINES}
LIABILITY_SECTIONS = ("CL", "NCL", "EQ")


def _has(name, *words):
    return any(w in name for w in words)


def default_line(name, section, role):
    """Best draft line for an FS item, from its name, section and role."""
    if section == "CA":
        if role == "cash":
            return "cash"
        if _has(name, "أطراف ذات علاقة", "اطراف ذات علاقة", "شركات شقيقة"):
            return "rp_from"
        if role == "receivables":
            return "trade_rec"
        if role in ("inventory", "transit") or _has(name, "مخزون"):
            return "inventory"
        return "other_rec"
    if section == "NCA":
        if _has(name, "حق الانتفاع", "حق الاستخدام"):
            return "rou"
        if _has(name, "استثمار"):
            return "investments"
        if _has(name, "أصول ثابتة", "الأصول الثابتة", "إهلاك", "اهلاك", "ممتلكات", "مشروعات تحت التنفيذ", "معدات"):
            return "ppe"
        return "other_nca"
    if section == "CL":
        if _has(name, "أقساط متداولة", "الجزء المتداول من القروض"):
            return "cur_loans"
        if _has(name, "أطراف ذات علاقة", "اطراف ذات علاقة"):
            return "rp_to"
        if _has(name, "إيجار", "ايجار", "تأجير"):
            return "lease_cur"
        if _has(name, "زكاة", "الزكاة"):
            return "zakat_prov"
        if role == "debt" or _has(name, "قروض", "تسهيلات", "مرابحات", "اعتمادات", "أوراق الدفع"):
            return "st_fin"
        if role == "payables":
            return "trade_pay"
        return "other_pay"
    if section == "NCL":
        if _has(name, "نهاية الخدمة", "المنافع"):
            return "eosb"
        if _has(name, "إيجار", "ايجار", "تأجير"):
            return "lease_nc"
        if role == "debt" or _has(name, "قروض", "تسهيلات", "مرابحات"):
            return "lt_fin"
        return "other_ncl"
    if section == "EQ":
        if _has(name, "رأس المال", "راس المال"):
            return "capital"
        if _has(name, "احتياطي", "الاحتياطيات"):
            return "reserve"
        if _has(name, "إعادة تقييم", "اعادة تقييم"):
            return "reval"
        if _has(name, "جاري"):
            return "owners"
        return "retained"
    if section == "SALES":
        return "sales"
    if section == "COGS":
        return "cogs"
    if section == "SELLING":
        return "selling"
    if section == "ADMIN":
        return "admin"
    if section == "ZAKAT":
        return "zakat"
    if role == "finance_cost" or _has(name, "تمويلية", "تمويل"):
        return "finance"
    if section == "NONOP" and _has(name, "استثمار"):
        return "invest"
    return "other"


def load_map(ctx):
    """{fs_item: line} — saved choices over the defaults; every FS item gets a line."""
    try:
        saved = json.loads(ctx.db.setting("draft_map", "{}") or "{}")
    except ValueError:
        saved = {}
    out = {}
    for item in ctx.fs_order:
        s = ctx.fs_section.get(item)
        valid = BS_LABEL if s in BS_SECTIONS else IS_LABEL if s in IS_SECTIONS else None
        if valid is None:
            continue
        line = saved.get(item)
        out[item] = line if line in valid else default_line(item, s, ctx.fs_role.get(item, ""))
    return out


def save_map(db, mapping):
    db.set_setting("draft_map", json.dumps(mapping, ensure_ascii=False))


# ------------------------------------------------------------------ figures
@dataclass
class Column:
    """One column of the statements (current period or comparative)."""
    label: str
    end: str                      # month of the closing balance, or "open:YYYY-MM" for an opening balance
    bs: dict = None               # line → value (assets positive, liabilities/equity positive)
    is_: dict = None              # line → value (presentation sign) or None when not available
    ni: float = None
    profit: float = 0.0
    plug: float = 0.0
    dep: float = 0.0
    accounts_bs: dict = field(default_factory=dict)   # line → {code: value}
    accounts_is: dict = field(default_factory=dict)
    acc_dep: float = 0.0          # accumulated depreciation (negative)
    dep_exp: float = None         # depreciation expense of the period (income statement), for the cash flow add-back


def _bs_column(ctx, mapping, months, idx, label, end_key):
    f = ctx.bs_figures(months, idx)
    col = Column(label, end_key, bs={k: 0.0 for k, *_ in BS_LINES}, profit=f["profit"], plug=f["plug"])
    for item, v in f["items"].items():
        line = mapping.get(item)
        if line in col.bs:
            col.bs[line] += v
    col.bs["retained"] += f["profit"] + f["plug"]
    for code, vals in ctx.bal(months).items():
        a = ctx.accounts.get(code)
        if not a or a.fs_item not in mapping or ctx.fs_section.get(a.fs_item) not in BS_SECTIONS:
            continue
        sign = 1 if ctx.fs_section[a.fs_item] in ASSET_SECTIONS else -1
        col.accounts_bs.setdefault(mapping[a.fs_item], {})[code] = vals[idx] * sign
    # accumulated depreciation (credit balance) for the cash flow add-back
    col.acc_dep = sum(v for item, v in f["items"].items()
                      if mapping.get(item) == "ppe" and _has(item, "مجمع") and _has(item, "إهلاك", "اهلاك", "استهلاك"))
    return col


def _is_values(ctx, mapping, end):
    f = ctx.is_figures([end], ytd=True)
    vals = {k: 0.0 for k, *_ in IS_LINES}
    dep = sum(-v for item, v in f["items"].items()
              if _has(item, "إهلاك", "اهلاك", "استهلاك") and not _has(item, "مجمع"))
    for item, v in f["items"].items():      # v: income positive, expense negative
        line = mapping.get(item)
        if line in vals:
            vals[line] += v if IS_NATURE[line] == "rev" else -v
    accts = {}
    for code, (o, m, c) in ctx.bal([end]).items():
        a = ctx.accounts.get(code)
        if not a or a.fs_item not in mapping or ctx.fs_section.get(a.fs_item) not in IS_SECTIONS:
            continue
        line = mapping[a.fs_item]
        accts.setdefault(line, {})[code] = -c if IS_NATURE[line] == "rev" else c
    return vals, f["ni"], accts, dep


def is_totals(v):
    t = {"gross": v["sales"] - v["cogs"]}
    t["expenses"] = v["selling"] + v["admin"]
    t["op"] = t["gross"] - t["expenses"]
    t["after_fin"] = t["op"] - v["finance"]
    t["pbt"] = t["after_fin"] + v["invest"] + v["other"]
    t["ni"] = t["pbt"] - v["zakat"]
    return t


def bs_totals(v):
    t = {s: sum(v[k] for k, *_ in BS_LINES if BS_SECTION[k] == s) for s in BS_SECTIONS}
    t["assets"] = t["CA"] + t["NCA"]
    t["liabilities"] = t["CL"] + t["NCL"]
    t["le"] = t["liabilities"] + t["EQ"]
    t["diff"] = t["assets"] - t["le"]
    return t


def cash_flow(open_col, close_col, ni):
    """Indirect method from the change of every draft line; ties to the cash line by construction."""
    o, c = open_col.bs, close_col.bs
    d = {k: c[k] - o[k] for k in c}
    # depreciation expense of the period; without one, the increase of accumulated depreciation
    dep = close_col.dep_exp if close_col.dep_exp else -(close_col.acc_dep - open_col.acc_dep)
    op, op2, inv, fin = [], [], [], []
    for k, label, s, act in BS_LINES:
        sign = -1 if s in ASSET_SECTIONS else 1
        if act == "OP":
            op.append((label, sign * d[k]))
        elif act == "OP2":
            op2.append((label, sign * d[k]))
        elif act == "INV":
            inv.append((label, sign * d[k]))
        elif act == "FIN":
            fin.append((label, sign * d[k]))
    inv.insert(0, ("إضافات ممتلكات وآلات ومعدات (بالصافي)", -(d["ppe"] + dep - d["reval"])))
    fin.append(("توزيعات وتسويات الأرباح المبقاة", d["retained"] - ni))
    r = {"ni": ni, "dep": dep, "op": op, "op2": op2, "inv": inv, "fin": fin}
    r["adjusted"] = ni + dep
    r["cash_ops"] = r["adjusted"] + sum(v for _, v in op)
    r["cfo"] = r["cash_ops"] + sum(v for _, v in op2)
    r["cfi"] = sum(v for _, v in inv)
    r["cff"] = sum(v for _, v in fin)
    r["net"] = r["cfo"] + r["cfi"] + r["cff"]
    r["open"], r["close"] = o["cash"], c["cash"]
    r["diff"] = o["cash"] + r["net"] - c["cash"]
    return r


@dataclass
class Draft:
    company: str
    end: str
    cur: Column
    comp: Column
    cf_cur: dict
    cf_comp: dict
    mapping: dict
    checks: list


def build(ctx, end):
    mapping = load_map(ctx)
    ytd = ctx.ytd_months(end)
    first, prev_end = ytd[0], month_add(ytd[0], -1)
    cur = _bs_column(ctx, mapping, [end], 2, end, end)
    cur.is_, cur.ni, cur.accounts_is, cur.dep_exp = _is_values(ctx, mapping, end)
    year_open = _bs_column(ctx, mapping, [first], 0, first, "open:" + first) if ctx.has(first) else None
    if ctx.has(prev_end):
        comp = _bs_column(ctx, mapping, [prev_end], 2, prev_end, prev_end)
        comp.is_, comp.ni, comp.accounts_is, comp.dep_exp = _is_values(ctx, mapping, prev_end)
    elif year_open:
        comp = year_open            # opening balances of the year = closing of the previous year
    else:
        comp = None
    open_for_cf = year_open or comp
    cf_cur = cash_flow(open_for_cf, cur, cur.ni) if open_for_cf else None
    cf_comp = None
    if comp is not None and comp.is_ is not None:
        pfirst = ctx.ytd_months(prev_end)[0]
        if ctx.has(pfirst):
            cf_comp = cash_flow(_bs_column(ctx, mapping, [pfirst], 0, pfirst, "open:" + pfirst), comp, comp.ni)

    checks = []
    for col, name in ((cur, "الفترة الحالية"), (comp, "المقارنة")):
        if col is None:
            continue
        t = bs_totals(col.bs)
        if abs(t["diff"]) > 1:
            checks.append(f"⚠ المركز المالي غير متوازن في {name}: الفرق {t['diff']:,.2f}")
        if abs(col.plug) > 1:
            checks.append(f"⚠ ميزان {name} غير متوازن بمقدار {col.plug:,.2f} — أضيف للأرباح المبقاة، راجع الميزان")
        if col.is_ is not None and abs(is_totals(col.is_)["ni"] - col.ni) > 1:
            checks.append(f"⚠ صافي الدخل في {name} لا يطابق حسابات الدخل")
    for cf, name in ((cf_cur, "الفترة الحالية"), (cf_comp, "المقارنة")):
        if cf and abs(cf["diff"]) > 1:
            checks.append(f"⚠ التدفقات النقدية في {name} لا تطابق رصيد النقد: الفرق {cf['diff']:,.2f}")
    unmapped = [code for code, v in ctx.bal([end]).items()
                if abs(v[2]) > 0.005 and (not ctx.accounts.get(code) or ctx.accounts[code].fs_item not in mapping)]
    if unmapped:
        checks.append(f"⚠ {len(unmapped)} حساب له رصيد وغير مربوط ببند (يظهر ضمن الأرباح المبقاة): "
                      + "، ".join(unmapped[:8]) + (" ..." if len(unmapped) > 8 else ""))
    if comp is None:
        checks.append("ℹ لا يوجد ميزان للسنة السابقة ولا أرصدة افتتاحية — عمود المقارنة فارغ")
    elif comp.is_ is None:
        checks.append("ℹ ميزان نهاية السنة السابقة غير مرفوع — المقارنة للمركز المالي من الأرصدة الافتتاحية، "
                      "وقائمة الدخل والتدفقات بدون مقارنة")
    return Draft(ctx.company, end, cur, comp, cf_cur, cf_comp, mapping, checks)


# ------------------------------------------------------------------ layout shared by Excel and PDF
def date_label(key):
    """'2026-06' → '30/6/2026'; 'open:2026-01' → '31/12/2025'."""
    import calendar
    if key.startswith("open:"):
        y, m = map(int, month_add(key[5:], -1).split("-"))
    else:
        y, m = map(int, key.split("-"))
    return f"{calendar.monthrange(y, m)[1]}/{m}/{y}"


def statements(dr, ctx):
    """[(title, [rows])], rows: (label, note, cur, comp, kind) — kind: item, sub, tot, hdr, blank.
    Notes are numbered: income statement lines first, then financial position lines."""
    cur, comp = dr.cur, dr.comp
    notes = []

    def note_no(kind, key, has_value):
        if not has_value:
            return ""
        notes.append((kind, key))
        return len(notes)

    def visible(d1, d2, key):
        return abs(d1.get(key, 0) or 0) > 0.5 or abs((d2 or {}).get(key, 0) or 0) > 0.5

    # income statement (numbered first)
    is_c, is_p = cur.is_, comp.is_ if comp else None
    tc, tp = is_totals(is_c), is_totals(is_p) if is_p else None

    def line(key):
        return (IS_LABEL[key], note_no("is", key, bool(cur.accounts_is.get(key)) or bool(comp and comp.accounts_is.get(key))),
                is_c[key], is_p[key] if is_p else None, "item")

    def tot(key, label, kind="sub"):
        return (label, "", tc[key], tp[key] if tp else None, kind)
    inc = [line("sales"), line("cogs"), tot("gross", "مجمل الربح"), ("", "", None, None, "blank"),
           line("selling"), line("admin"), tot("expenses", "إجمالي المصروفات"),
           tot("op", "صافي الدخل من العمليات الرئيسية"), ("", "", None, None, "blank"), line("finance"),
           tot("after_fin", "صافي الدخل بعد المصاريف التمويلية")]
    for k in ("invest", "other"):
        if visible(is_c, is_p, k):
            inc.append(line(k))
    inc += [tot("pbt", "صافي الربح قبل الزكاة")]
    if visible(is_c, is_p, "zakat"):
        inc.append(line("zakat"))
    inc.append(tot("ni", "صافي الدخل", "tot"))

    # financial position
    bc, bp = cur.bs, comp.bs if comp else None
    btc, btp = bs_totals(bc), bs_totals(bp) if bp else None

    def bline(key):
        has = bool(cur.accounts_bs.get(key)) or bool(comp and comp.accounts_bs.get(key)) or key == "retained"
        return (BS_LABEL[key], note_no("bs", key, has), bc[key], bp[key] if bp else None, "item")

    def btot(key, label, kind="sub"):
        return (label, "", btc[key], btp[key] if btp else None, kind)

    def section(s):
        return [bline(k) for k, _, sec, _ in BS_LINES if sec == s and (visible(bc, bp, k) or k in ("cash", "capital"))]
    fp = [("الموجودات", "", None, None, "hdr"), ("الموجودات المتداولة", "", None, None, "hdr")] + section("CA") + [
        btot("CA", "إجمالي الموجودات المتداولة"), ("الموجودات غير المتداولة", "", None, None, "hdr")] + section("NCA") + [
        btot("NCA", "إجمالي الموجودات غير المتداولة"), btot("assets", "إجمالي الموجودات", "tot"),
        ("المطلوبات وحقوق الشركاء", "", None, None, "hdr"), ("المطلوبات المتداولة", "", None, None, "hdr")] + section(
        "CL") + [btot("CL", "إجمالي المطلوبات المتداولة"), ("المطلوبات غير المتداولة", "", None, None, "hdr")] + section(
        "NCL") + [btot("NCL", "إجمالي المطلوبات غير المتداولة"), btot("liabilities", "إجمالي المطلوبات"),
                  ("حقوق الشركاء", "", None, None, "hdr")] + section("EQ") + [
        btot("EQ", "إجمالي حقوق الشركاء"), btot("le", "إجمالي المطلوبات وحقوق الشركاء", "tot")]

    # cash flows
    cc, cp = dr.cf_cur, dr.cf_comp
    cfr = []

    def cfrow(label, a, b, kind="item"):
        cfr.append((label, "", a, b, kind))

    def pair(key):
        return (cc[key] if cc else None), (cp[key] if cp else None)

    if cc:
        cfr.append(("الأنشطة التشغيلية", "", None, None, "hdr"))
        cfrow("صافي الدخل", *pair("ni"))
        if abs(cc["dep"]) > 0.5 or (cp and abs(cp["dep"]) > 0.5):
            cfrow("تعديلات غير نقدية: استهلاك ممتلكات وآلات ومعدات", *pair("dep"))
        cfrow("صافي الدخل بعد التعديلات غير النقدية", *pair("adjusted"), "sub")
        cfr.append(("التغير في الموجودات والمطلوبات التشغيلية", "", None, None, "hdr"))
        for i, (label, v) in enumerate(cc["op"]):
            w = cp["op"][i][1] if cp else None
            if abs(v) > 0.5 or (w and abs(w) > 0.5):
                cfrow(label, v, w)
        cfrow("النقد الناتج من (المستخدم في) العمليات", *pair("cash_ops"), "sub")
        for i, (label, v) in enumerate(cc["op2"]):
            w = cp["op2"][i][1] if cp else None
            if abs(v) > 0.5 or (w and abs(w) > 0.5):
                cfrow(label, v, w)
        cfrow("صافي النقد الناتج من (المستخدم في) الأنشطة التشغيلية", *pair("cfo"), "tot")
        for title, key, total in (("الأنشطة الاستثمارية", "inv", "cfi"), ("الأنشطة التمويلية", "fin", "cff")):
            cfr.append((title, "", None, None, "hdr"))
            for i, (label, v) in enumerate(cc[key]):
                w = cp[key][i][1] if cp else None
                if abs(v) > 0.5 or (w and abs(w) > 0.5):
                    cfrow(label, v, w)
            cfrow(f"صافي النقد الناتج من (المستخدم في) {title}", *pair(total), "tot")
        cfrow("صافي التغير في النقد", *pair("net"), "sub")
        cfrow("رصيد النقد أول المدة", *pair("open"))
        cfrow("رصيد النقد آخر المدة", *pair("close"), "tot")
    return [("fp", fp), ("is", inc), ("cf", cfr)], notes


def note_tables(dr, ctx, notes):
    """[(no, title, [(code, name, cur, comp)], total_cur, total_comp)] in the order of the numbering."""
    out = []
    for no, (kind, key) in enumerate(notes, start=1):
        if kind == "is":
            a1, a2 = dr.cur.accounts_is.get(key, {}), (dr.comp.accounts_is.get(key, {}) if dr.comp and dr.comp.is_ else {})
            title = IS_LABEL[key]
            t1, t2 = dr.cur.is_[key], (dr.comp.is_[key] if dr.comp and dr.comp.is_ else None)
        else:
            a1, a2 = dr.cur.accounts_bs.get(key, {}), (dr.comp.accounts_bs.get(key, {}) if dr.comp else {})
            title = BS_LABEL[key]
            t1, t2 = dr.cur.bs[key], (dr.comp.bs[key] if dr.comp else None)
        has_comp = t2 is not None
        rows = []
        for code in sorted(set(a1) | set(a2)):
            v1, v2 = a1.get(code, 0.0), a2.get(code, 0.0)
            if abs(v1) > 0.005 or abs(v2) > 0.005:
                acc = ctx.accounts.get(code)
                rows.append((code, acc.name if acc else "", v1, v2 if has_comp else None))
        if kind == "bs" and key == "retained":
            rows.append(("", "صافي ربح الفترة (من بداية السنة)", dr.cur.profit, dr.comp.profit if dr.comp else None))
            if abs(dr.cur.plug) > 0.5 or (dr.comp and abs(dr.comp.plug) > 0.5):
                rows.append(("", "فرق ميزان المراجعة (أرصدة غير مقفلة)", dr.cur.plug, dr.comp.plug if dr.comp else None))
        out.append((no, title, kind, rows, t1, t2))
    return out
