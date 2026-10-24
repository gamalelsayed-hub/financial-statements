"""Annual comparisons: every fiscal year with full-year data (12 months entered, or an uploaded full-year trial
balance), side by side with growth, compound annual growth (CAGR) and trend tables."""
from .blocks import Para, Report, Row, Table
from .calc import MONTHS_AR, month_add, safe_div

MAX_YEARS = 6
SRC = {"monthly": "من الشهور المدخلة", "annual": "من ميزان السنة المرفوع", "year_end": "من ميزان نهاية السنة"}


class Year:
    def __init__(self, ctx, key, label, c, months, source, prev=None):
        self.key, self.label, self.source = key, label, source
        self.is_ = c.is_figures(months)
        self.bs = c.bs_figures([months[-1]], 2)
        self.open_bs = prev.bs if prev else None
        self.cf = c.cash_flow(months)
        self.branches = c.branches_report_data(months) if c.bmov.get(months[-1]) or any(c.bmov.get(m) for m in months) \
            else None
        self.months = len(months) if source == "monthly" else 12


def years(ctx, p):
    """Full years up to the report end (newest MAX_YEARS) + the current year to date when it isn't complete."""
    end_key = ctx.year_months(p.end)[-1]
    keys = [k for k in ctx.full_years() if k <= end_key][-MAX_YEARS:]
    out, prev = [], None
    for k in keys:
        c, months, src = ctx.year_source(k)
        y = Year(ctx, k, ctx.year_label(k), c, months, src, prev if prev and _consecutive(ctx, prev.key, k) else None)
        out.append(y)
        prev = y
    partial = None
    if end_key not in keys:
        ytd = [m for m in ctx.ytd_months(p.end) if ctx.has(m)]
        if ytd:
            label = f"{ctx.year_label(end_key)} حتى {MONTHS_AR[int(p.end[5:7]) - 1]}"
            partial = Year(ctx, end_key, label, ctx, ytd, "monthly", prev if prev and _consecutive(ctx, prev.key, end_key)
                           else None)
            partial.months = len(ytd)
    return out, partial


def _consecutive(ctx, a, b):
    return ctx.year_months(b)[0] == month_add(a, 1)


def growth(a, b):
    """Change of a over b. Two negative values (expenses shown as negatives) compare their sizes: −120 → −150 = +25%."""
    if a is None or b is None or abs(b) < 1e-9:
        return None
    if a < 0 and b < 0:
        return (abs(a) - abs(b)) / abs(b)
    return (a - b) / abs(b)


def cagr(first, last, n):
    if n < 1 or first is None or last is None:
        return None
    if first < 0 and last < 0:
        first, last = -first, -last
    if first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / n) - 1


def _columns(ys, partial):
    cols = ["البند"] + [y.label for y in ys]
    fmts = ["n"] * len(ys)
    if len(ys) >= 2:
        cols += [f"النمو {ys[-1].label} / {ys[-2].label}"]
        fmts += ["%"]
    if len(ys) >= 3:
        cols += [f"النمو السنوي المركب {ys[0].label}–{ys[-1].label}"]
        fmts += ["%"]
    if partial:
        cols += [partial.label]
        fmts += ["n"]
    return cols, fmts


def _row(label, vals, ys, partial, pval=None, kind="item", fmt="n", grow=True):
    """vals: one value per full year. Adds growth of the last year (points difference for % rows) and CAGR."""
    out = list(vals)
    if len(ys) >= 2:
        if fmt == "%":
            out.append(None if None in (vals[-1], vals[-2]) else vals[-1] - vals[-2])
        else:
            out.append(growth(vals[-1], vals[-2]) if grow else None)
    if len(ys) >= 3:
        out.append(cagr(vals[0], vals[-1], len(vals) - 1) if fmt == "n" and grow else None)
    if partial:
        out.append(pval)
    return Row(label, out, kind, fmt)


def _empty(key, title):
    return Report(key, title, "", [Para(
        "لا توجد سنوات كاملة بعد. ارفع ميزان نهاية السنة للسنوات السابقة من «البيانات الشهرية» ← «📥 ميزان سنة كاملة»، "
        "والسنة التي لها 12 شهرًا في البرنامج تُحسب تلقائيًا.", "warn")])


def _notes(ys, partial):
    parts = [f"{y.label}: {SRC[y.source]}" for y in ys]
    blocks = [Para("مصدر كل سنة — " + " | ".join(parts))]
    if partial:
        blocks.append(Para(f"عمود «{partial.label}» للسنة الحالية حتى آخر شهر ({partial.months} شهر) — "
                           "غير داخل في النمو والنمو المركب."))
    return blocks


def rpt_an_is(ctx, p):
    ys, partial = years(ctx, p)
    if not ys:
        return _empty("an_is", "قائمة الدخل — مقارنة سنوية")
    cols, fmts = _columns(ys, partial)
    rows = []
    for key, label, kind in ctx.is_rows():
        if key is None:
            rows.append(Row(label, kind="hdr"))
            continue
        rows.append(_row(label, [ctx.is_value(y.is_, key) for y in ys], ys, partial,
                         ctx.is_value(partial.is_, key) if partial else None, kind))
    for k, label in (("gross", "هامش مجمل الربح"), ("op", "هامش الربح التشغيلي"), ("ni", "هامش صافي الربح")):
        rows.append(_row(label, [safe_div(y.is_[k], y.is_["net_sales"]) for y in ys], ys, partial,
                         safe_div(partial.is_[k], partial.is_["net_sales"]) if partial else None, fmt="%"))
    blocks = [Table(cols, rows, fmts)] + _notes(ys, partial)
    blocks.append(Para("النمو المركب = (السنة الأخيرة ÷ السنة الأولى)^(1 ÷ عدد السنوات) − 1. "
                       "في سطور النِسَب عمود النمو = الفرق بالنقاط."))
    return Report("an_is", "قائمة الدخل — مقارنة سنوية", f"{ys[0].label} إلى {ys[-1].label}", blocks)


def rpt_an_bs(ctx, p):
    ys, partial = years(ctx, p)
    if not ys:
        return _empty("an_bs", "المركز المالي — مقارنة سنوية")
    cols, fmts = _columns(ys, partial)
    rows = []
    for key, label, kind in ctx.bs_rows():
        if key is None:
            rows.append(Row(label, kind="hdr"))
            continue
        rows.append(_row(label, [_bs_value(ctx, y.bs, key) for y in ys], ys, partial,
                         _bs_value(ctx, partial.bs, key) if partial else None, kind))
    return Report("an_bs", "المركز المالي — مقارنة سنوية", f"في نهاية كل سنة: {ys[0].label} إلى {ys[-1].label}",
                  [Table(cols, rows, fmts)] + _notes(ys, partial))


def _bs_value(ctx, f, key):
    if key.startswith("sec:"):
        return f["sec"][key[4:]]
    if key in f["items"]:
        return f["items"][key]
    return f.get(key)


def _kpis(y):
    f, b, o = y.is_, y.bs, y.open_bs
    ann = 12 / y.months

    def avg(k):
        return (b[k] + o[k]) / 2 if o else b[k]

    ns = f["net_sales"]
    dso = safe_div(avg("receivables") * 365, ns * ann)
    dio = safe_div(avg("inventory") * 365, f["cogs"] * ann)
    dpo = safe_div(avg("payables") * 365, f["cogs"] * ann)
    ca, cl = b["sec"]["CA"], b["sec"]["CL"]
    return {
        "ns": ns, "gm": safe_div(f["gross"], ns), "om": safe_div(f["op"], ns), "nm": safe_div(f["ni"], ns),
        "admin": safe_div(f["admin"], ns), "selling": safe_div(f["selling"], ns),
        "opex": safe_div(f["admin"] + f["selling"], ns), "fin": safe_div(f["finance_cost"], ns),
        "cr": safe_div(ca, cl), "qr": safe_div(ca - b["inventory"] - b["transit"], cl), "wc": ca - cl,
        "dso": dso, "dio": dio, "dpo": dpo,
        "ccc": None if None in (dso, dio, dpo) else dso + dio - dpo,
        "roa": safe_div(f["ni"] * ann, avg("assets")), "roe": safe_div(f["ni"] * ann, avg("equity")),
        "at": safe_div(ns * ann, avg("assets")), "de": safe_div(b["debt"], b["equity"]),
        "la": safe_div(b["liabilities"], b["assets"]), "nd": b["debt"] - b["cash"],
        "cfo": y.cf["cfo"], "fcf": y.cf["cfo"] - y.cf["capex"], "cash": b["cash"],
    }


KPI_ROWS = [
    (None, "الربحية", None), ("ns", "صافي المبيعات", "n"), ("gm", "هامش مجمل الربح", "%"),
    ("om", "هامش الربح التشغيلي", "%"), ("nm", "هامش صافي الربح", "%"), ("roa", "العائد على الأصول", "%"),
    ("roe", "العائد على حقوق الملكية", "%"),
    (None, "المصروفات إلى المبيعات", None), ("admin", "المصروفات الإدارية", "%"), ("selling", "المصروفات البيعية", "%"),
    ("opex", "إجمالي المصروفات التشغيلية", "%"), ("fin", "المصروفات التمويلية", "%"),
    (None, "السيولة ورأس المال العامل", None), ("cr", "نسبة التداول", "x"), ("qr", "النسبة السريعة", "x"),
    ("wc", "رأس المال العامل", "n"), ("cash", "النقد في نهاية السنة", "n"),
    ("dso", "أيام التحصيل", "d"), ("dio", "أيام المخزون", "d"), ("dpo", "أيام السداد", "d"),
    ("ccc", "دورة التحويل النقدي (يوم)", "d"), ("at", "دوران الأصول", "x"),
    (None, "المديونية والتدفقات", None), ("de", "القروض إلى حقوق الملكية", "x"), ("la", "الخصوم إلى الأصول", "%"),
    ("nd", "صافي الدين", "n"), ("cfo", "التدفق النقدي التشغيلي", "n"), ("fcf", "التدفق الحر (بعد شراء الأصول)", "n"),
]


def rpt_an_kpi(ctx, p):
    ys, partial = years(ctx, p)
    if not ys:
        return _empty("an_kpi", "المؤشرات والنسب — مقارنة سنوية")
    cols, fmts = _columns(ys, partial)
    data = [_kpis(y) for y in ys]
    pdata = _kpis(partial) if partial else None
    rows = []
    for k, label, fmt in KPI_ROWS:
        if k is None:
            rows.append(Row(label, kind="hdr"))
            continue
        vals = [d[k] for d in data]
        grow = k not in ("wc", "nd", "cfo", "fcf")     # may change sign: growth % means nothing
        rows.append(_row(label, vals, ys, partial, pdata[k] if pdata else None, fmt=fmt, grow=grow))
    blocks = [Table(cols, rows, fmts)] + _notes(ys, partial)
    blocks.append(Para("الأيام على أساس 365 يوم ومتوسط رصيد بداية ونهاية السنة (عند توفر السنة السابقة). "
                       "أعمدة السنة الحالية حتى الشهر محولة لسنوية في العوائد والأيام."))
    return Report("an_kpi", "المؤشرات والنسب — مقارنة سنوية", f"{ys[0].label} إلى {ys[-1].label}", blocks)


def rpt_an_trend(ctx, p):
    """Year-on-year growth of the main lines, with the compound growth and a direction reading."""
    ys, partial = years(ctx, p)
    if len(ys) < 2:
        return Report("an_trend", "اتجاهات النمو السنوية", "", [Para(
            "يلزم سنتان كاملتان على الأقل لتحليل الاتجاه — ارفع موازين نهاية السنوات السابقة.", "warn")])
    lines = [("صافي المبيعات", lambda y: y.is_["net_sales"]), ("تكلفة المبيعات", lambda y: y.is_["cogs"]),
             ("مجمل الربح", lambda y: y.is_["gross"]), ("المصروفات الإدارية", lambda y: y.is_["admin"]),
             ("المصروفات البيعية", lambda y: y.is_["selling"]), ("الربح التشغيلي", lambda y: y.is_["op"]),
             ("صافي الربح", lambda y: y.is_["ni"]), ("إجمالي الأصول", lambda y: y.bs["assets"]),
             ("العملاء", lambda y: y.bs["receivables"]), ("المخزون", lambda y: y.bs["inventory"]),
             ("الموردون", lambda y: y.bs["payables"]), ("حقوق الملكية", lambda y: y.bs["equity"]),
             ("القروض والتسهيلات", lambda y: y.bs["debt"])]
    cols = ["البند"] + [f"{b.label} / {a.label}" for a, b in zip(ys, ys[1:])] + ["النمو السنوي المركب", "الاتجاه"]
    rows = []
    for label, fn in lines:
        vals = [fn(y) for y in ys]
        g = [growth(b, a) for a, b in zip(vals, vals[1:])]
        c = cagr(vals[0], vals[-1], len(vals) - 1)
        rows.append(Row(label, g + [c, _direction(g)], fmt="%",
                        styles=[_style(label, x) for x in g] + [_style(label, c), ""]))
    sales = [y.is_["net_sales"] for y in ys]
    pairs = [("التكلفة مقابل المبيعات", [y.is_["cogs"] for y in ys]),
             ("المصروفات التشغيلية مقابل المبيعات", [y.is_["admin"] + y.is_["selling"] for y in ys]),
             ("العملاء مقابل المبيعات", [y.bs["receivables"] for y in ys]),
             ("المخزون مقابل المبيعات", [y.bs["inventory"] for y in ys])]
    prow = []
    for label, vals in pairs:
        diff = []
        for i in range(1, len(ys)):
            a, b = growth(vals[i], vals[i - 1]), growth(sales[i], sales[i - 1])
            diff.append(None if None in (a, b) else a - b)
        prow.append(Row(label, diff + [None, "أسرع من المبيعات" if diff and (diff[-1] or 0) > 0.02 else
                                       "أبطأ من المبيعات" if diff and (diff[-1] or 0) < -0.02 else "بنفس الوتيرة"],
                        fmt="%", styles=[("bad" if (x or 0) > 0.02 else "good" if (x or 0) < -0.02 else "")
                                         for x in diff] + ["", ""]))
    blocks = [Table(cols, rows, ["%"] * (len(cols) - 2) + ["t"], title="نسبة النمو سنة بسنة"),
              Table(["البند"] + cols[1:], prow, ["%"] * (len(cols) - 2) + ["t"],
                    title="نمو البند ناقص نمو المبيعات (موجب = البند ينمو أسرع من المبيعات)")]
    blocks += _notes(ys, None)
    return Report("an_trend", "اتجاهات النمو السنوية", f"{ys[0].label} إلى {ys[-1].label}", blocks)


def _direction(g):
    vals = [x for x in g if x is not None]
    if not vals:
        return ""
    if all(x > 0 for x in vals):
        return "نمو مستمر"
    if all(x < 0 for x in vals):
        return "تراجع مستمر"
    return "متذبذب — " + ("آخر سنة نمو" if vals[-1] > 0 else "آخر سنة تراجع")


COST_LINES = {"تكلفة المبيعات", "المصروفات الإدارية", "المصروفات البيعية", "القروض والتسهيلات", "العملاء",
              "المخزون", "الموردون"}


def _style(label, v):
    if v is None:
        return ""
    good = v > 0 if label not in COST_LINES else v < 0
    return "good" if good else "bad"


def rpt_an_branch(ctx, p):
    ys, partial = years(ctx, p)
    ys = [y for y in ys if y.branches]
    if not ys:
        return Report("an_branch", "الفروع — مقارنة سنوية", "", [Para(
            "لا توجد حركة فروع لسنوات كاملة — ارفع حركة الفروع للسنة من «📥 ميزان سنة كاملة».", "warn")])
    if partial and not partial.branches:
        partial = None
    cols, fmts = _columns(ys, partial)
    blocks = []
    for key, title in (("net_sales", "صافي المبيعات"), ("after", "صافي الربح التشغيلي بعد توزيع مصروفات الإدارة")):
        rows = []
        names = [b for b in ctx.branches if any(b in y.branches[0] for y in ys)]
        for b in names:
            rows.append(_row(b, [y.branches[0][b][key] if b in y.branches[0] else None for y in ys], ys, partial,
                             partial.branches[0][b][key] if partial and b in partial.branches[0] else None))
        rows.append(_row(ctx.admin_label, [y.branches[1][key] for y in ys], ys, partial,
                         partial.branches[1][key] if partial else None))
        rows.append(_row("الإجمالي (الشركة)", [y.branches[2][key] for y in ys], ys, partial,
                         partial.branches[2][key] if partial else None, kind="tot"))
        blocks.append(Table(cols, rows, fmts, title=title))
    # ranking and share in the last full year
    last = ys[-1]
    tot = last.branches[2]["net_sales"]
    ranked = sorted(((b, f) for b, f in last.branches[0].items()), key=lambda x: -x[1]["net_sales"])
    rrows = []
    for i, (b, f) in enumerate(ranked, 1):
        prev = ys[-2].branches[0].get(b) if len(ys) >= 2 else None
        rrows.append(Row(b, [i, f["net_sales"], safe_div(f["net_sales"], tot), growth(f["net_sales"], prev["net_sales"])
                             if prev else None, safe_div(f["gross"], f["net_sales"]), safe_div(f["after"], f["net_sales"])]))
    blocks.append(Table(["الفرع", "الترتيب", "صافي المبيعات", "الحصة من المبيعات", "النمو عن السنة السابقة",
                         "هامش مجمل الربح", "هامش الربح بعد التوزيع"], rrows, ["d", "n", "%", "%", "%", "%"],
                        title=f"ترتيب الفروع — {last.label}"))
    blocks += _notes(ys, partial)
    return Report("an_branch", "الفروع — مقارنة سنوية", f"{ys[0].label} إلى {ys[-1].label}", blocks)


def rpt_an_exp(ctx, p):
    ys, partial = years(ctx, p)
    if not ys:
        return _empty("an_exp", "المصروفات حسب المجموعة — مقارنة سنوية")
    cols, fmts = _columns(ys, partial)

    def groups(y):
        c, months, _ = ctx.year_source(y.key) if y is not partial else (ctx, [m for m in ctx.ytd_months(p.end)
                                                                              if ctx.has(m)], "")
        return c.branch_figures(c.company_pl_values(months))["groups"]

    data = [groups(y) for y in ys]
    pdata = groups(partial) if partial else None
    rows, ratio_rows = [], []
    for g in ctx.exp_groups:
        vals = [-d.get(g, 0.0) for d in data]
        if not any(abs(v) > 0.5 for v in vals):
            continue
        rows.append(_row(g, vals, ys, partial, -pdata.get(g, 0.0) if pdata else None))
        ratio_rows.append(_row(g, [safe_div(v, y.is_["net_sales"]) for v, y in zip(vals, ys)], ys, partial,
                               safe_div(-pdata.get(g, 0.0), partial.is_["net_sales"]) if pdata else None, fmt="%"))
    tot = [sum(r.values[i] or 0 for r in rows) for i in range(len(ys))]
    rows.append(_row("الإجمالي", tot, ys, partial, sum(-v for v in pdata.values()) if pdata else None, kind="tot"))
    return Report("an_exp", "المصروفات حسب المجموعة — مقارنة سنوية", f"{ys[0].label} إلى {ys[-1].label}",
                  [Table(cols, rows, fmts, title="المبالغ"),
                   Table(cols, ratio_rows, fmts, title="النسبة إلى صافي المبيعات (عمود النمو = الفرق بالنقاط)")]
                  + _notes(ys, partial))


ANNUAL_REPORTS = [
    ("an_is", "قائمة الدخل — مقارنة سنوية", rpt_an_is),
    ("an_bs", "المركز المالي — مقارنة سنوية", rpt_an_bs),
    ("an_kpi", "المؤشرات والنسب — مقارنة سنوية", rpt_an_kpi),
    ("an_trend", "اتجاهات النمو السنوية", rpt_an_trend),
    ("an_exp", "المصروفات حسب المجموعة — مقارنة سنوية", rpt_an_exp),
    ("an_branch", "الفروع — مقارنة سنوية", rpt_an_branch),
]
