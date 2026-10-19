"""Report builders. Every report is a list of tables, rendered to HTML (screen/PDF) and Excel."""
from dataclasses import dataclass, field

from .calc import (Ctx, MONTHS_AR, month_add, month_label, months_range, range_label, safe_div)
from .defaults import BUCKET_NAMES, BS_SECTIONS, IS_SECTIONS
from . import aging as AG
from . import diagnose as D


@dataclass
class Row:
    label: str
    values: list = field(default_factory=list)
    kind: str = "item"   # item | sub | tot | hdr | note
    fmt: str = "n"       # n | % | x | d | t
    styles: list = None  # optional css class per value (good / warn / bad)


@dataclass
class Table:
    columns: list
    rows: list
    col_fmts: list = None   # per value column, overrides the row format
    title: str = None


@dataclass
class Para:
    text: str
    cls: str = "sub"


@dataclass
class Report:
    key: str
    title: str
    subtitle: str
    blocks: list


@dataclass
class Params:
    end: str
    n: int = 1
    comp: str = "prev"      # prev | ly | none | YYYY-MM
    branch: str = ""
    view: str = "period"    # period | ytd

    def months(self):
        return months_range(self.end, self.n)

    def comp_months(self):
        if self.comp == "none":
            return None
        if self.comp == "prev":
            end = month_add(self.end, -self.n)
        elif self.comp == "ly":
            end = month_add(self.end, -12)
        else:
            end = self.comp
        return months_range(end, self.n)


def pct_change(a, b):
    if a is None or b is None or abs(b) < 1e-9:
        return None
    return (a - b) / abs(b)


def alert(diff, base, ctx):
    if diff is None:
        return ""
    big_pct = base is not None and abs(base) > 1e-9 and abs(diff) / abs(base) > ctx.alert_pct
    if abs(diff) > ctx.alert_amount and (big_pct or base in (None, 0)):
        return "▲ ارتفاع" if diff > 0 else "▼ انخفاض"
    return ""


# ================================================================== period reports
def rpt_bs(ctx: Ctx, p: Params):
    m = p.months()
    close, open_ = ctx.bs_figures(m, 2), ctx.bs_figures(m, 0)
    cm = p.comp_months()
    comp = ctx.bs_figures(cm, 2) if cm and ctx.has(cm[-1]) else None
    rows = []
    for key, label, kind in ctx.bs_rows():
        if key is None:
            rows.append(Row(label, kind="hdr"))
            continue
        c, o = ctx.bs_value(close, key), ctx.bs_value(open_, key)
        cp = ctx.bs_value(comp, key) if comp else None
        rows.append(Row(label, [c, o, c - o, cp, None if cp is None else c - cp, pct_change(c, cp),
                                safe_div(c, close["assets"])], kind))
    cols = ["البند", "ختامي الفترة", "بداية الفترة", "التغير خلال الفترة",
            "ختامي المقارنة" + (f" ({month_label(cm[-1])})" if cm else ""), "الفرق عن المقارنة", "الفرق %",
            "% من إجمالي الأصول"]
    blocks = [Table(cols, rows, ["n", "n", "n", "n", "n", "%", "%"]),
              Para("مصدر أي بند: شاشة ربط الحسابات (فلتر بند القائمة). «فرق ميزان المراجعة» يجب أن يكون صفرًا؛ "
                   "إن لم يكن فالميزان المدخل غير متوازن.")]
    return Report("bs", "المركز المالي", f"في نهاية {month_label(m[-1])}", blocks)


def rpt_is(ctx: Ctx, p: Params):
    m = p.months()
    cur = ctx.is_figures(m)
    cm = p.comp_months()
    comp = ctx.is_figures(cm) if cm and all(ctx.has(x) for x in cm) else None
    ytd_m = ctx.ytd_months(m[-1])
    ytd = ctx.is_figures([m[-1]], ytd=True)
    nmonths = len(ytd_m)
    rows = []
    for key, label, kind in ctx.is_rows():
        if key is None:
            rows.append(Row(label, kind="hdr"))
            continue
        v = ctx.is_value(cur, key)
        c = ctx.is_value(comp, key) if comp else None
        y = ctx.is_value(ytd, key)
        rows.append(Row(label, [v, safe_div(v, cur["net_sales"]), c, None if c is None else v - c,
                                pct_change(v, c), y, safe_div(y, ytd["net_sales"]), y / nmonths], kind))
    rows.append(Row("مطابقة: صافي الربح من كل حسابات الدخل",
                    [-sum(v[1] for code, v in ctx.bal(m).items() if ctx.is_pl(code))], "note"))
    cols = ["البند", f"الفترة الحالية ({range_label(m)})", "% من المبيعات",
            "فترة المقارنة" + (f" ({range_label(cm)})" if cm else ""), "الفرق", "الفرق %",
            f"من بداية السنة ({nmonths} شهر)", "% من المبيعات", "متوسط شهري"]
    blocks = [Table(cols, rows, ["n", "%", "n", "n", "%", "n", "%", "n"]),
              Para("الإيرادات بالموجب والمصروفات بالسالب. الفترة الحالية = حركة الفترة، "
                   "ومن بداية السنة = الرصيد الختامي لحسابات الدخل.")]
    return Report("is", "قائمة الدخل", f"عن {range_label(m)}", blocks)


def _cf_table(ctx, columns_data, headers, col_fmts=None):
    """columns_data: list of cash_flow() dicts → one table with the union of rows."""
    rows = []
    titles = {"OP": "الأنشطة التشغيلية", "INV": "الأنشطة الاستثمارية", "FIN": "الأنشطة التمويلية"}
    totals = {"OP": ("cfo", "صافي التدفقات من الأنشطة التشغيلية"),
              "INV": ("cfi", "صافي التدفقات من الأنشطة الاستثمارية"),
              "FIN": ("cff", "صافي التدفقات من الأنشطة التمويلية")}
    for act in ("OP", "INV", "FIN"):
        rows.append(Row(titles[act], kind="hdr"))
        if act == "OP":
            rows.append(Row("صافي ربح الفترة", [d["ni"] if d else None for d in columns_data]))
        keys, labels = [], {}
        for d in columns_data:
            if not d:
                continue
            for k, label, v in d["sections"][act]:
                if k not in labels:
                    keys.append(k)
                    labels[k] = label
        for k in keys:
            vals = []
            for d in columns_data:
                if not d:
                    vals.append(None)
                    continue
                vals.append(next((v for kk, _, v in d["sections"][act] if kk == k), 0.0))
            rows.append(Row(labels[k], vals))
        key, label = totals[act]
        rows.append(Row(label, [d[key] if d else None for d in columns_data], "sub"))
    for key, label, kind in (("net_change", "صافي التغير في النقد", "sub"),
                             ("cash_open", "النقد في بداية الفترة", "item"),
                             ("cash_close_calc", "النقد في نهاية الفترة (محسوب)", "tot"),
                             ("cash_close", "النقد في نهاية الفترة (من الميزان)", "item"),
                             ("cash_diff", "الفرق (يجب أن يكون صفرًا)", "note")):
        rows.append(Row(label, [d[key] if d else None for d in columns_data], kind))
    return Table(headers, rows, col_fmts)


def rpt_cf(ctx: Ctx, p: Params):
    m = p.months()
    cur = ctx.cash_flow(m)
    cm = p.comp_months()
    comp = ctx.cash_flow(cm) if cm and all(ctx.has(x) for x in cm) else None
    headers = ["البند", f"الفترة الحالية ({range_label(m)})", "فترة المقارنة" + (f" ({range_label(cm)})" if cm else "")]
    blocks = [_cf_table(ctx, [cur, comp], headers)]
    if cur["no_item"]:
        blocks.append(Para(f"⚠ حسابات ميزانية لها حركة وليس لها بند تدفق: {len(cur['no_item'])} — "
                           "اربطها من شاشة ربط الحسابات.", "bad"))
    return Report("cf", "التدفقات النقدية (الطريقة غير المباشرة)", f"عن {range_label(m)}", blocks)


def _cf_flat(cf):
    acts = {"OP": "التشغيلية", "INV": "الاستثمارية", "FIN": "التمويلية"}
    out = [("صافي ربح الفترة", "التشغيلية", cf["ni"])]
    for act in ("OP", "INV", "FIN"):
        out += [(label, acts[act], v) for _, label, v in cf["sections"][act]]
    return out


def rpt_su(ctx: Ctx, p: Params):
    m = p.months()
    flat = [x for x in _cf_flat(ctx.cash_flow(m)) if abs(x[2]) > 0.005]
    src = sum(v for *_, v in flat if v > 0)
    use = -sum(v for *_, v in flat if v < 0)
    rows = [Row(label, [act, v, max(v, 0), max(-v, 0), safe_div(max(v, 0), src), safe_div(max(-v, 0), use)])
            for label, act, v in flat]
    rows.append(Row("الإجمالي", ["", src - use, src, use, 1 if src else None, 1 if use else None], "tot"))
    t1 = Table(["البند", "النشاط", "المبلغ", "مصدر", "استخدام", "% من المصادر", "% من الاستخدامات"], rows,
               ["t", "n", "n", "n", "%", "%"])
    top_s = sorted([x for x in flat if x[2] > 0], key=lambda x: -x[2])[:5]
    top_u = sorted([x for x in flat if x[2] < 0], key=lambda x: x[2])[:5]
    rows2 = []
    for i in range(max(len(top_s), len(top_u))):
        s = top_s[i] if i < len(top_s) else ("", "", None)
        u = top_u[i] if i < len(top_u) else ("", "", None)
        rows2.append(Row(str(i + 1), [s[0], s[2], u[0], None if u[2] is None else -u[2]]))
    t2 = Table(["#", "أكبر 5 مصادر", "المبلغ", "أكبر 5 استخدامات", "المبلغ"], rows2, ["t", "n", "t", "n"],
               title="أكبر المصادر والاستخدامات")
    return Report("su", "مصادر النقد واستخداماته", f"عن {range_label(m)}", [t1, t2])


def _branch_rows(ctx, figs, labels_extra=True):
    """figs: list of branch_figures dicts (with allocation keys) → rows."""
    rows = []

    def add(label, getter, kind="item", fmt="n"):
        rows.append(Row(label, [getter(f) for f in figs], kind, fmt))

    for c in ctx.cat_order:
        if ctx.cat_kind.get(c) == "sales":
            add(c, lambda f, c=c: f["cats"][c])
    add("صافي المبيعات", lambda f: f["net_sales"], "sub")
    for c in ctx.cat_order:
        if ctx.cat_kind.get(c) == "cogs":
            add(c, lambda f, c=c: f["cats"][c])
    add("مجمل الربح", lambda f: f["gross"], "sub")
    add("نسبة مجمل الربح", lambda f: safe_div(f["gross"], f["net_sales"]), fmt="%")
    rows.append(Row("المصروفات المباشرة", kind="hdr"))
    for g in ctx.exp_groups:
        if any(abs(f["groups"][g]) > 0.005 for f in figs):
            add(g, lambda f, g=g: f["groups"][g])
    add("مصروفات تشغيلية بلا مجموعة (راجع الربط)", lambda f: f["no_group"])
    add("إجمالي المصروفات المباشرة", lambda f: f["direct"], "sub")
    add("ربح الفرع قبل التوزيع (المساهمة)", lambda f: f["contribution"], "sub")
    add("نسبة التوزيع", lambda f: f.get("ratio"), fmt="%")
    add(f"نصيب الفرع من مصروفات {ctx.admin_label}", lambda f: f.get("share"))
    add("صافي الربح التشغيلي بعد التوزيع", lambda f: f.get("after"), "tot")
    add("هامش صافي الربح التشغيلي", lambda f: safe_div(f.get("after"), f["net_sales"]), fmt="%")
    rows.append(Row("بنود على مستوى الشركة (لا توزع)", kind="hdr"))
    for c in ctx.cat_order:
        if ctx.cat_kind.get(c) == "below":
            add(c, lambda f, c=c: f["cats"][c])
    add("صافي الربح", lambda f: f.get("net"), "tot")
    return rows


def rpt_branches(ctx: Ctx, p: Params):
    m = ctx.ytd_months(p.end) if p.view == "ytd" else p.months()
    cols, admin, company = ctx.branches_report_data(m, ytd_view=(p.view == "ytd"))
    figs = list(cols.values()) + [admin, company]
    rows = _branch_rows(ctx, figs)
    total_sales = company["net_sales"]
    rows.append(Row("حصة الفرع من صافي المبيعات", [safe_div(f["net_sales"], total_sales) for f in figs], fmt="%"))
    rows.append(Row("المصروفات المباشرة إلى المبيعات", [safe_div(-f["direct"], f["net_sales"]) for f in figs], fmt="%"))
    rows.append(Row("مطابقة مع قائمة الدخل (يجب صفر)",
                    [None] * (len(figs) - 1) + [company["net"] - ctx.is_figures(m if p.view != "ytd" else [p.end],
                                                                                   ytd=p.view == "ytd")["ni"]], "note"))
    headers = ["البند"] + list(cols) + [f"{ctx.admin_label} (غير موزع)", "الإجمالي (الشركة)"]
    view = "من بداية السنة" if p.view == "ytd" else "الفترة"
    blocks = [Table(headers, rows),
              Para(f"عمود «{ctx.admin_label}» = الشركة ناقص مجموع الفروع، وتوزع مصروفاته المباشرة على الفروع "
                   "بنسبة المصروفات المباشرة لكل فرع.")]
    return Report("branches", f"دخل الفروع وتوزيع مصروفات {ctx.admin_label}", f"{view}: {range_label(m)}", blocks)


def _avg_prior(ctx, months, getter):
    prior = ctx.prior_months_in_year(months)
    if not prior:
        return None
    return sum(getter([x]) for x in prior) / len(prior) * len(months)


def rpt_branch_exp(ctx: Ctx, p: Params):
    branch = p.branch or (ctx.branches[0] if ctx.branches else "")
    m = p.months()
    ytd = ctx.ytd_months(p.end)

    def fig(months):
        return ctx.branch_figures(ctx.branch_values(months, branch))

    cur, y = fig(m), fig(ytd)
    prior = ctx.prior_months_in_year(m)
    prior_figs = [fig([x]) for x in prior]

    def avg(get):
        return sum(get(f) for f in prior_figs) / len(prior_figs) * len(m) if prior_figs else None

    rows = []
    ns, ns_avg = cur["net_sales"], avg(lambda f: f["net_sales"])
    rows.append(Row("صافي مبيعات الفرع", [ns, ns_avg, None if ns_avg is None else ns - ns_avg,
                                          pct_change(ns, ns_avg), y["net_sales"], None, ""], "sub"))
    for g in ctx.exp_groups:
        v, a_ = -cur["groups"][g], avg(lambda f, g=g: -f["groups"][g])
        yv = -y["groups"][g]
        if abs(v) < 0.005 and abs(yv) < 0.005:
            continue
        d = None if a_ is None else v - a_
        rows.append(Row(g, [v, a_, d, pct_change(v, a_), yv, safe_div(v, ns), alert(d, a_, ctx)]))
    tv, ta = -cur["direct"], avg(lambda f: -f["direct"])
    td = None if ta is None else tv - ta
    rows.append(Row("الإجمالي", [tv, ta, td, pct_change(tv, ta), -y["direct"], safe_div(tv, ns), alert(td, ta, ctx)], "tot"))
    headers = ["مجموعة المصروف", f"الفترة الحالية ({range_label(m)})",
               f"متوسط الفترات السابقة ({len(prior)} شهر)", "الفرق", "الفرق %", "من بداية السنة",
               "% من مبيعات الفرع", "تنبيه"]
    return Report("branch_exp", f"تحليل مصروفات فرع: {branch}", range_label(m),
                  [Table(headers, rows, ["n", "n", "n", "%", "n", "%", "t"]),
                   Para(f"التنبيه: التغير عن المتوسط أكبر من {ctx.alert_pct:.0%} وأكبر من {ctx.alert_amount:,.0f} معًا.")])


def rpt_exp(ctx: Ctx, p: Params):
    m = p.months()
    cm = p.comp_months()
    cur = ctx.opex_by_account(m)
    comp = ctx.opex_by_account(cm) if cm else {}
    ytd = ctx.opex_by_account(ctx.ytd_months(p.end))
    prior = ctx.prior_months_in_year(m)
    prior_vals = [ctx.opex_by_account([x]) for x in prior]
    ns = ctx.is_figures(m)["net_sales"]

    def avg(code):
        return sum(v.get(code, 0.0) for v in prior_vals) / len(prior_vals) * len(m) if prior_vals else None

    codes = sorted(set(cur) | set(comp) | set(ytd), key=lambda c: (ctx.accounts[c].exp_group, c))

    def line(label, code_label, group, v, c, a_, y, kind="item"):
        d = v - c
        da = None if a_ is None else v - a_
        return Row(label, [code_label, group, v, c, d, pct_change(v, c), a_, da, safe_div(v, ns), y,
                           alert(da if da is not None else d, a_ if a_ is not None else c, ctx)], kind)

    rows = [Row("ملخص حسب المجموعة", kind="hdr")]
    groups = ctx.exp_groups + [""]
    for g in groups:
        cs = [c for c in codes if (ctx.accounts[c].exp_group or "") == g]
        if not cs:
            continue
        v = sum(cur.get(c, 0.0) for c in cs)
        cv = sum(comp.get(c, 0.0) for c in cs)
        a_ = None if not prior_vals else sum(avg(c) for c in cs)
        y = sum(ytd.get(c, 0.0) for c in cs)
        rows.append(line(g or "بلا مجموعة", "", "", v, cv, a_, y))
    tv = sum(cur.values())
    tc = sum(comp.values())
    ta = None if not prior_vals else sum(avg(c) for c in codes)
    rows.append(line("الإجمالي", "", "", tv, tc, ta, sum(ytd.values()), "tot"))
    rows.append(Row("التفصيل حسب الحساب", kind="hdr"))
    for c in codes:
        a = ctx.accounts[c]
        rows.append(line(a.name, c, a.exp_group, cur.get(c, 0.0), comp.get(c, 0.0), avg(c), ytd.get(c, 0.0)))
    headers = ["البيان", "رقم الحساب", "المجموعة", f"الفترة الحالية ({range_label(m)})",
               "فترة المقارنة" + (f" ({range_label(cm)})" if cm else ""), "الفرق", "الفرق %",
               f"متوسط الفترات السابقة ({len(prior)} شهر)", "الفرق عن المتوسط", "% من المبيعات", "من بداية السنة", "تنبيه"]
    return Report("exp", "تحليل المصروفات بين فترتين", range_label(m),
                  [Table(headers, rows, ["t", "t", "n", "n", "n", "%", "n", "n", "%", "n", "t"]),
                   Para("المصروفات التشغيلية = حسابات الدخل التي فئتها «مصروف تشغيلي». تظهر بالموجب.")])


def rpt_ratios(ctx: Ctx, p: Params):
    rs, note = ctx.ratios(p.months())
    rows = [Row(name, [val, grp, formula, reading], fmt=fmt) for name, val, fmt, grp, formula, reading in rs]
    blocks = [Table(["النسبة", "القيمة", "المجموعة", "طريقة الحساب", "القراءة"], rows, [None, "t", "t", "t"])]
    blocks.append(Para("النسب من بداية السنة ومحولة لسنوية؛ المتوسطات = (رصيد بداية الفترة + ختامي الفترة) ÷ 2."))
    if note:
        blocks.append(Para(note, "warn"))
    return Report("ratios", "النسب المالية", f"حتى {month_label(p.end)}", blocks)


# ------------------------------------------------------------------ checks & summary
def run_checks(ctx: Ctx, p: Params):
    m = p.months()
    end = m[-1]
    out = []

    def add(name, value, tol, action, is_count=False):
        ok = value is not None and abs(value) <= tol
        out.append((name, value, tol, ok, action, is_count))

    tb = ctx.tbs.get(end, {})
    sums = [sum((r[i] or 0) for r in tb.values()) for i in range(1, 7)]
    add("توازن الميزان — الأرصدة الافتتاحية", sums[0] - sums[1], 1, "سنة سابقة غير مقفلة في الأرباح المحتجزة، أو حساب ناقص")
    add("توازن الميزان — الحركة", sums[2] - sums[3], 1, "أكمل أسطر الميزان")
    add("توازن الميزان — الأرصدة الختامية", sums[4] - sums[5], 1, "نفس سبب الأرصدة الافتتاحية")
    unmapped = [c for c in tb if not (ctx.accounts.get(c) and ctx.accounts[c].fs_item in ctx.fs_section)]
    add("حسابات في الميزان غير مربوطة ببند قائمة", len(unmapped), 0, "شاشة ربط الحسابات: فلتر «غير مربوط»", True)
    bs = ctx.bs_figures(m, 2)
    add("المركز المالي متوازن", bs["diff"], 1, "راجع الربط")
    bad_row = [c for c, r in tb.items() if abs((r[1] or 0) - (r[2] or 0) + (r[3] or 0) - (r[4] or 0) - (r[5] or 0) + (r[6] or 0)) > 1]
    add("حسابات رصيدها الختامي ≠ الافتتاحي + الحركة", len(bad_row), 0, "راجع تصدير الميزان من النظام", True)
    cf = ctx.cash_flow(m)
    add("التدفقات تنتهي برصيد النقد الفعلي", cf["cash_diff"], 1, "حساب ميزانية بلا «بند تدفق» أو بند نقد غير صحيح")
    add("حسابات ميزانية لها حركة بلا بند تدفق", len(cf["no_item"]), 0, "في الربط أعطِ الحساب بند تدفق", True)
    comp_pl = ctx.branch_figures(ctx.company_pl_values(m))
    add("حسابات دخل بلا «فئة دخل الفروع»", comp_pl["unmapped"], 1, "في الربط أعطِ الحساب فئة دخل الفروع")
    add("مصروفات تشغيلية بلا مجموعة", comp_pl["no_group"], 1, "في الربط أعطِ الحساب مجموعة مصروف")
    # continuity: opening of each month = closing of the previous month
    breaks = 0
    for i, per in enumerate(ctx.periods):
        prev = month_add(per, -1)
        if prev in ctx.tbs:
            a, b = ctx.tbs[prev], ctx.tbs[per]
            for code in set(a) | set(b):
                ca = (a[code][5] - a[code][6]) if code in a else 0.0
                ob = (b[code][1] - b[code][2]) if code in b else 0.0
                if abs(ca - ob) > 1:
                    breaks += 1
    add("أرصدة أول الشهر = آخر الشهر السابق (كل الأشهر)", breaks, 0, "ميزان شهر ناقص أو قيود بعد إقفال الشهر السابق", True)
    ytd = ctx.ytd_months(end)
    miss = ctx.missing(ytd)
    add("أشهر غير مدخلة من بداية السنة", len(miss), 0, "أدخل ميزان الأشهر: " + "، ".join(month_label(x) for x in miss), True)
    worst = 0.0
    for x in ytd:
        if ctx.has(x):
            worst = max(worst, abs(ctx.bs_figures([x], 2)["diff"]))
    add("المركز المالي متوازن في نهاية كل شهر", worst, 1, "راجع ربط الحسابات الظاهرة في الأشهر السابقة")
    bunm = set()
    for x in m:
        for b, vals in ctx.bmov.get(x, {}).items():
            for code in vals:
                a = ctx.accounts.get(code)
                if not a or a.branch_cat not in ctx.cat_kind:
                    bunm.add(code)
    add("حسابات في حركة الفروع بلا فئة", len(bunm), 0, "في الربط أعطِ الحساب فئة دخل الفروع", True)
    cust = ctx.aging("customers", end)
    if cust:
        add("تقرير أعمار العملاء = الميزان", bs["receivables"] - AG.customers_summary(cust)["total"], 1,
            "فرق توقيت أو عملاء خارج التقرير — يُشرح")
    supp = ctx.aging("suppliers", end)
    if supp:
        ss = AG.suppliers_summary(supp, AG.rates(ctx.db), ctx.base_currency)
        add("تقرير أعمار الموردين = الميزان", bs["payables"] - ss["total"], 1, "عملات أجنبية أو موردون خارج التقرير")
        add("موردون بعملة بدون سعر صرف", ss["no_rate"], 0, "أضف سعر العملة في الإعدادات", True)
    return out


def rpt_checks(ctx: Ctx, p: Params):
    checks = run_checks(ctx, p)
    rows = []
    for name, value, tol, ok, action, is_count in checks:
        rows.append(Row(name, [value, tol, "سليم" if ok else "يحتاج مراجعة", "" if ok else action],
                        fmt="d" if is_count else "n",
                        styles=[None, None, "good" if ok else "bad", None]))
    fails = sum(1 for c in checks if not c[3])
    head = Para("✓ كل الفحوصات سليمة" if not fails else
                f"⚠ فحوصات تحتاج مراجعة: {fails} — افتح «تشخيص الخلل» لمعرفة الحسابات المسببة بالضبط والحل.",
                "good" if not fails else "bad")
    return Report("checks", "المطابقات والفحوصات", range_label(p.months()),
                  [head, Table(["الفحص", "القيمة", "السماحية", "النتيجة", "ماذا أفعل لو فشل؟"], rows,
                               [None, None, "t", "t"])])


SEVERITY = {"error": ("⛔ خطأ", "bad"), "warn": ("⚠ تنبيه", "warn"), "info": ("ℹ معلومة", None)}


def rpt_diag(ctx: Ctx, p: Params):
    summary, findings = D.diagnose(ctx, p.months())
    blocks = [Para(s, "good" if s.startswith("لا توجد أخطاء") else "bad") for s in summary]
    n_err = sum(1 for f in findings if f.severity == "error")
    n_warn = sum(1 for f in findings if f.severity == "warn")
    blocks.append(Para(f"الأخطاء: {n_err}   |   التنبيهات: {n_warn}. المبالغ: مدين بالموجب ودائن بالسالب، "
                       "ومجموع مبالغ كل مجال يساوي الفرق الذي يشرحه."))
    rows = []
    for f in findings:
        label, cls = SEVERITY[f.severity]
        rows.append(Row(label, [f.area, f.code, f.name, f.amount, f.issue, f.fix], styles=[None] * 6))
    t = Table(["الخطورة", "المجال", "رقم الحساب", "اسم الحساب", "المبلغ", "المشكلة", "الحل المقترح"], rows,
              ["t", "t", "t", "n", "t", "t"])
    blocks.append(t)
    pm = D.prefix_map(ctx.db)
    blocks.append(Para("قاعدة أرقام الحسابات المستخدمة: " + "، ".join(
        f"{k} = {D.TYPE_NAMES[v]}" for k, v in pm.items() if v) + " (تُعدّل من الإعدادات)."))
    return Report("diag", "تشخيص الخلل", range_label(p.months()), blocks)


def rpt_summary(ctx: Ctx, p: Params):
    m = p.months()
    cm = p.comp_months()
    cur = ctx.is_figures(m)
    comp = ctx.is_figures(cm) if cm and all(ctx.has(x) for x in cm) else None
    fails = sum(1 for c in run_checks(ctx, p) if not c[3])
    blocks = [Para("✓ كل الفحوصات سليمة" if not fails else f"⚠ فحوصات تحتاج مراجعة: {fails} (راجع «تشخيص الخلل»)",
                   "good" if not fails else "bad")]
    rows = []
    for key, label in (("net_sales", "صافي المبيعات"), ("gross", "مجمل الربح"), ("op", "الربح التشغيلي"), ("ni", "صافي الربح")):
        c = comp[key] if comp else None
        rows.append(Row(label, [cur[key], c, pct_change(cur[key], c)]))
    for num, label in (("gross", "هامش مجمل الربح"), ("op", "هامش الربح التشغيلي"), ("ni", "هامش صافي الربح")):
        rows.append(Row(label, [safe_div(cur[num], cur["net_sales"]), safe_div(comp[num], comp["net_sales"]) if comp else None,
                                None], fmt="%"))
    blocks.append(Table(["المؤشر", f"الفترة الحالية ({range_label(m)})", "فترة المقارنة", "التغير %"], rows,
                        [None, None, "%"], title="الربحية"))
    close, open_ = ctx.bs_figures(m, 2), ctx.bs_figures(m, 0)
    cf = ctx.cash_flow(m)
    rows = []
    for role, label in (("cash", "النقد"), ("receivables", "العملاء"), ("inventory", "المخزون"),
                        ("payables", "الموردون"), ("debt", "القروض والتسهيلات")):
        rows.append(Row(label, [close[role], open_[role], pct_change(close[role], open_[role])]))
    rows.append(Row("صافي التدفق النقدي التشغيلي", [cf["cfo"], None, None]))
    rows.append(Row("صافي التغير في النقد", [cf["net_change"], None, None]))
    blocks.append(Table(["البند", "الرصيد", "بداية الفترة", "التغير %"], rows, [None, None, "%"], title="المركز المالي والنقد"))
    rs, _ = ctx.ratios(m)
    pick = ["نسبة التداول", "النسبة السريعة", "أيام المخزون", "فترة التحصيل (يوم)", "فترة السداد (يوم)",
            "دورة التحويل النقدي (يوم)", "هامش صافي الربح", "القروض إلى حقوق الملكية", "تغطية الفوائد (مرة)"]
    rows = [Row(name, [val], fmt=fmt) for name, val, fmt, *_ in rs if name in pick]
    blocks.append(Table(["النسبة (من بداية السنة)", "القيمة"], rows, title="أهم النسب"))
    if ctx.branches:
        cols, admin, company = ctx.branches_report_data(ctx.ytd_months(p.end), ytd_view=True)
        rows = [Row(b, [f["net_sales"], f["after"], safe_div(f["after"], f["net_sales"])]) for b, f in cols.items()]
        blocks.append(Table(["الفرع", "صافي المبيعات", "صافي الربح التشغيلي بعد التوزيع", "الهامش"], rows,
                            [None, None, "%"], title="الفروع — من بداية السنة"))
    return Report("summary", "الملخص التنفيذي", range_label(m), blocks)


# ================================================================== monthly reports
def _year(ctx, p):
    months = ctx.year_months(p.end)
    entered = [x for x in months if ctx.has(x) and x <= p.end]
    return months, entered


def _monthly_headers(months, extra=True):
    h = ["البند"] + [MONTHS_AR[int(x[5:7]) - 1] for x in months]
    if extra:
        h += ["الربع 1", "الربع 2", "الربع 3", "الربع 4", "إجمالي السنة", "المتوسط الشهري"]
    return h


def _agg(vals, months, entered, mode="sum"):
    """vals: {month: value}. Adds quarters, total, average (sum mode) or only months (point mode)."""
    row = [vals.get(x) if x in entered else None for x in months]
    if mode != "sum":
        return row
    q = []
    for i in range(4):
        part = [vals.get(x, 0.0) for x in months[i * 3:i * 3 + 3] if x in entered]
        q.append(sum(part) if part else None)
    tot = sum(vals.get(x, 0.0) for x in entered) if entered else None
    avg = tot / len(entered) if entered else None
    return row + q + [tot, avg]


def rpt_m_is(ctx, p):
    months, entered = _year(ctx, p)
    figs = {x: ctx.is_figures([x]) for x in entered}
    rows = []
    for key, label, kind in ctx.is_rows():
        if key is None:
            rows.append(Row(label, kind="hdr"))
            continue
        rows.append(Row(label, _agg({x: ctx.is_value(f, key) for x, f in figs.items()}, months, entered), kind))
    rows.append(Row("هامش مجمل الربح", _ratio_row(figs, months, entered, "gross", "net_sales"), fmt="%"))
    rows.append(Row("هامش صافي الربح", _ratio_row(figs, months, entered, "ni", "net_sales"), fmt="%"))
    return Report("m_is", "قائمة الدخل الشهرية", f"السنة المنتهية {month_label(months[-1])}",
                  [Table(_monthly_headers(months), rows)])


def _ratio_row(figs, months, entered, num, den):
    out = [safe_div(figs[x][num], figs[x][den]) if x in entered else None for x in months]
    qs = []
    for i in range(4):
        part = [x for x in months[i * 3:i * 3 + 3] if x in entered]
        qs.append(safe_div(sum(figs[x][num] for x in part), sum(figs[x][den] for x in part)) if part else None)
    tot = safe_div(sum(figs[x][num] for x in entered), sum(figs[x][den] for x in entered)) if entered else None
    return out + qs + [tot, tot]


def rpt_m_exp(ctx, p):
    months, entered = _year(ctx, p)
    data = {x: ctx.opex_by_account([x]) for x in entered}
    rows = []
    for g in ctx.exp_groups + [""]:
        vals = {x: sum(v for c, v in d.items() if (ctx.accounts[c].exp_group or "") == g) for x, d in data.items()}
        if any(abs(v) > 0.005 for v in vals.values()):
            rows.append(Row(g or "بلا مجموعة", _agg(vals, months, entered)))
    rows.append(Row("الإجمالي", _agg({x: sum(d.values()) for x, d in data.items()}, months, entered), "tot"))
    sales = {x: ctx.is_figures([x])["net_sales"] for x in entered}
    tot = {x: sum(d.values()) for x, d in data.items()}
    rows.append(Row("المصروفات إلى المبيعات", [safe_div(tot.get(x), sales.get(x)) if x in entered else None for x in months]
                    + [None] * 4 + [safe_div(sum(tot.values()), sum(sales.values())) if entered else None] * 2, fmt="%"))
    alerts = []
    if len(entered) >= 2:
        last = entered[-1]
        prior = entered[:-1]
        for g in ctx.exp_groups:
            cur = sum(v for c, v in data[last].items() if ctx.accounts[c].exp_group == g)
            avg = sum(sum(v for c, v in data[x].items() if ctx.accounts[c].exp_group == g) for x in prior) / len(prior)
            a = alert(cur - avg, avg, ctx)
            if a:
                alerts.append(f"{g}: {cur:,.0f} مقابل متوسط {avg:,.0f} ({a})")
    blocks = [Table(_monthly_headers(months), rows)]
    if alerts:
        blocks.append(Para(f"مجموعات تجاوزت متوسطها في {month_label(entered[-1])}: " + " | ".join(alerts), "warn"))
    return Report("m_exp", "المصروفات الشهرية حسب المجموعة", f"السنة المنتهية {month_label(months[-1])}", blocks)


def rpt_m_bs(ctx, p):
    months, entered = _year(ctx, p)
    figs = {x: ctx.bs_figures([x], 2) for x in entered}
    rows = []
    for key, label, kind in ctx.bs_rows():
        if key is None:
            rows.append(Row(label, kind="hdr"))
            continue
        rows.append(Row(label, _agg({x: ctx.bs_value(f, key) for x, f in figs.items()}, months, entered, "point"), kind))
    return Report("m_bs", "المركز المالي في نهاية كل شهر", f"السنة المنتهية {month_label(months[-1])}",
                  [Table(_monthly_headers(months, extra=False), rows)])


def rpt_m_kpi(ctx, p):
    months, entered = _year(ctx, p)
    rows_def = []
    data = {}
    for x in entered:
        f = ctx.is_figures([x])
        b = ctx.bs_figures([x], 2)
        cf = ctx.cash_flow([x])
        cogs = f["cogs"]
        dso = safe_div(b["receivables"], f["net_sales"] * ctx.credit_ratio)
        dio = safe_div(b["inventory"], cogs)
        dpo = safe_div(b["payables"], cogs)
        data[x] = {
            "ns": f["net_sales"], "gm": safe_div(f["gross"], f["net_sales"]), "om": safe_div(f["op"], f["net_sales"]),
            "nm": safe_div(f["ni"], f["net_sales"]), "opex": safe_div(f["admin"] + f["selling"], f["net_sales"]),
            "cash": b["cash"], "rec": b["receivables"], "inv": b["inventory"], "pay": b["payables"],
            "dso": None if dso is None else dso * 30, "dio": None if dio is None else dio * 30,
            "dpo": None if dpo is None else dpo * 30,
            "cr": safe_div(b["sec"]["CA"], b["sec"]["CL"]), "de": safe_div(b["debt"], b["equity"]),
            "nd": b["debt"] - b["cash"], "cfo": cf["cfo"], "fcf": cf["cfo"] - cf["capex"],
        }
        d = data[x]
        d["ccc"] = None if None in (d["dso"], d["dio"], d["dpo"]) else d["dso"] + d["dio"] - d["dpo"]
    rows_def = [("ns", "صافي المبيعات", "n"), ("gm", "هامش مجمل الربح", "%"), ("om", "هامش الربح التشغيلي", "%"),
                ("nm", "هامش صافي الربح", "%"), ("opex", "المصروفات التشغيلية إلى المبيعات", "%"),
                ("cash", "النقد آخر الشهر", "n"), ("rec", "العملاء", "n"), ("inv", "المخزون", "n"), ("pay", "الموردون", "n"),
                ("dso", "أيام التحصيل (على المبيعات الآجلة)", "d"), ("dio", "أيام المخزون", "d"),
                ("dpo", "أيام السداد (تقريبي)", "d"), ("ccc", "دورة التحويل النقدي", "d"),
                ("cr", "نسبة التداول", "x"), ("de", "القروض إلى حقوق الملكية", "x"), ("nd", "صافي الدين", "n"),
                ("cfo", "التدفق التشغيلي", "n"), ("fcf", "التدفق الحر (بعد شراء الأصول)", "n")]
    rows = [Row(label, [data[x][k] if x in entered else None for x in months], fmt=fmt) for k, label, fmt in rows_def]
    return Report("m_kpi", "المؤشرات الشهرية", "الأيام على أساس 30 يوم للشهر",
                  [Table(_monthly_headers(months, extra=False), rows)])


def _cf_months(ctx, months, entered):
    return {x: ctx.cash_flow([x]) for x in entered}


def rpt_m_cf(ctx, p):
    months, entered = _year(ctx, p)
    cfs = _cf_months(ctx, months, entered)
    cols = [cfs.get(x) for x in months]
    t = _cf_table(ctx, cols, _monthly_headers(months, extra=False))
    return Report("m_cf", "التدفقات النقدية الشهرية (الطريقة غير المباشرة)", f"السنة المنتهية {month_label(months[-1])}", [t])


def rpt_m_cash(ctx, p):
    months, entered = _year(ctx, p)
    cfs = _cf_months(ctx, months, entered)
    rows = []
    for b, label in BUCKET_NAMES.items():
        rows.append(Row(label, _agg({x: cfs[x]["buckets"][b] for x in entered}, months, entered)))
    rows.append(Row("= التغير في النقد", _agg({x: cfs[x]["net_change"] for x in entered}, months, entered), "tot"))
    rows.append(Row("النقد آخر الشهر", _agg({x: cfs[x]["cash_close"] for x in entered}, months, entered, "point")
                    + [None] * 6, "note"))
    neg = sum(1 for x in entered if cfs[x]["cfo"] < 0)
    ni = sum(cfs[x]["ni"] for x in entered)
    cfo = sum(cfs[x]["cfo"] for x in entered)
    notes = [Para(f"أشهر التدفق التشغيلي فيها سالب: {neg} من {len(entered)} أشهر."),
             Para(f"تحول الربح إلى كاش من بداية السنة: {safe_div(cfo, ni) or 0:.1%} (التدفق التشغيلي ÷ صافي الربح).")]
    return Report("m_cash", "الكاش راح فين؟ — ملخص شهري", "الموجب = مصدر للنقد، السالب = استخدام",
                  [Table(_monthly_headers(months), rows)] + notes)


def rpt_m_su(ctx, p):
    months, entered = _year(ctx, p)
    cfs = _cf_months(ctx, months, entered)
    rows = [Row("المصادر — من أين جاء الكاش؟", kind="hdr")]
    for b, label in BUCKET_NAMES.items():
        vals = {x: max(cfs[x]["buckets"][b], 0.0) for x in entered}
        if any(v > 0.005 for v in vals.values()):
            rows.append(Row(label, _agg(vals, months, entered)))
    rows.append(Row("إجمالي المصادر", _agg({x: sum(max(v, 0) for v in cfs[x]["buckets"].values()) for x in entered},
                                           months, entered), "sub"))
    rows.append(Row("الاستخدامات — أين صُرف الكاش؟", kind="hdr"))
    for b, label in BUCKET_NAMES.items():
        vals = {x: max(-cfs[x]["buckets"][b], 0.0) for x in entered}
        if any(v > 0.005 for v in vals.values()):
            rows.append(Row(label, _agg(vals, months, entered)))
    rows.append(Row("إجمالي الاستخدامات", _agg({x: sum(max(-v, 0) for v in cfs[x]["buckets"].values()) for x in entered},
                                              months, entered), "sub"))
    rows.append(Row("صافي التغير في النقد", _agg({x: cfs[x]["net_change"] for x in entered}, months, entered), "tot"))
    return Report("m_su", "مصادر النقد واستخداماته شهريًا", f"السنة المنتهية {month_label(months[-1])}",
                  [Table(_monthly_headers(months), rows)])


def _branch_month_data(ctx, months, entered):
    return {x: ctx.branches_report_data([x]) for x in entered}


def rpt_m_br_sales(ctx, p):
    months, entered = _year(ctx, p)
    data = _branch_month_data(ctx, months, entered)
    rows = []
    for b in ctx.branches:
        rows.append(Row(b, _agg({x: data[x][0][b]["net_sales"] for x in entered if b in data[x][0]}, months, entered)))
    rows.append(Row(ctx.admin_label, _agg({x: data[x][1]["net_sales"] for x in entered}, months, entered)))
    rows.append(Row("الإجمالي (الشركة)", _agg({x: data[x][2]["net_sales"] for x in entered}, months, entered), "tot"))
    return Report("m_br_sales", "الفروع شهريًا — صافي المبيعات", f"السنة المنتهية {month_label(months[-1])}",
                  [Table(_monthly_headers(months), rows)])


def rpt_m_br_profit(ctx, p):
    months, entered = _year(ctx, p)
    data = _branch_month_data(ctx, months, entered)
    rows = [
        Row("مصروفات الشركة التشغيلية", _agg({x: data[x][2]["direct"] for x in entered}, months, entered)),
        Row("المصروفات المباشرة لكل الفروع", _agg({x: sum(f["direct"] for f in data[x][0].values()) for x in entered},
                                                  months, entered)),
        Row(f"مصروفات {ctx.admin_label} (للتوزيع)", _agg({x: data[x][1]["direct"] for x in entered}, months, entered), "sub"),
        Row("صافي الربح التشغيلي بعد التوزيع", kind="hdr"),
    ]
    for b in ctx.branches:
        rows.append(Row(b, _agg({x: data[x][0][b]["after"] for x in entered if b in data[x][0]}, months, entered)))
    rows.append(Row(f"{ctx.admin_label} (بعد التوزيع)", _agg({x: data[x][1]["after"] for x in entered}, months, entered)))
    rows.append(Row("الإجمالي (الشركة)", _agg({x: data[x][2]["after"] for x in entered}, months, entered), "tot"))
    return Report("m_br_profit", "الفروع شهريًا — صافي الربح التشغيلي بعد توزيع مصروفات الإدارة",
                  f"السنة المنتهية {month_label(months[-1])}", [Table(_monthly_headers(months), rows)])


def rpt_m_branch(ctx, p):
    branch = p.branch or (ctx.branches[0] if ctx.branches else "")
    months, entered = _year(ctx, p)
    data = {x: ctx.branches_report_data([x])[0].get(branch) for x in entered}
    data = {x: f for x, f in data.items() if f}
    rows = []

    def add(label, get, kind="item", fmt="n"):
        rows.append(Row(label, _agg({x: get(f) for x, f in data.items()}, months, list(data)) if fmt == "n" else
                        [get(data[x]) if x in data else None for x in months] + [None] * 6, kind, fmt))

    add("صافي المبيعات", lambda f: f["net_sales"], "sub")
    add("تكلفة المبيعات والتسويات", lambda f: f["gross"] - f["net_sales"])
    add("مجمل الربح", lambda f: f["gross"], "sub")
    add("نسبة مجمل الربح", lambda f: safe_div(f["gross"], f["net_sales"]), fmt="%")
    rows.append(Row("المصروفات المباشرة", kind="hdr"))
    for g in ctx.exp_groups:
        if any(abs(f["groups"][g]) > 0.005 for f in data.values()):
            add(g, lambda f, g=g: f["groups"][g])
    add("إجمالي المصروفات المباشرة", lambda f: f["direct"], "sub")
    add("المساهمة قبل التوزيع", lambda f: f["contribution"], "sub")
    add(f"نصيب الفرع من مصروفات {ctx.admin_label}", lambda f: f["share"])
    add("صافي الربح التشغيلي بعد التوزيع", lambda f: f["after"], "tot")
    add("هامش صافي الربح التشغيلي", lambda f: safe_div(f["after"], f["net_sales"]), fmt="%")
    return Report("m_branch", f"تحليل فرع شهريًا: {branch}", f"السنة المنتهية {month_label(months[-1])}",
                  [Table(_monthly_headers(months), rows)])



# ================================================================== customers & suppliers
def _cust_group_rows(rows, key, total_all):
    groups = {}
    for r in rows:
        groups.setdefault((r.get(key) or "—").strip() or "—", []).append(r)
    out = []
    for g, rs in sorted(groups.items(), key=lambda kv: -sum(AG.customer_total(r) for r in kv[1])):
        tot = sum(AG.customer_total(r) for r in rs)
        od = sum(AG.customer_overdue(r) for r in rs)
        out.append(Row(g, [len(rs), tot, tot - od, od, safe_div(od, tot),
                           sum(AG.customer_total(r) for r in rs if AG.is_credit(r.get("ctype"))),
                           sum(AG.customer_total(r) for r in rs if AG.is_custody(r.get("ctype"))),
                           sum(AG.n(r.get("guarantee")) for r in rs), safe_div(tot, total_all)]))
    return out


CUST_COLS = ["عدد العملاء", "الرصيد", "ضمن المدة (غير متأخر)", "المتأخر", "نسبة المتأخر", "آجل", "عهدة",
             "ضمانات بنكية", "% من الإجمالي"]
CUST_FMTS = ["d", "n", "n", "n", "%", "n", "n", "n", "%"]


def rpt_customers(ctx: Ctx, p: Params):
    rows = ctx.aging("customers", p.end)
    if not rows:
        return Report("customers", "تحليل أرصدة العملاء", month_label(p.end),
                      [Para("لا توجد بيانات أعمار عملاء لهذا الشهر — ارفعها من شاشة «البيانات الشهرية».", "warn")])
    s = AG.customers_summary(rows)
    tb_rec = ctx.bs_figures([p.end], 2)["receivables"] if ctx.has(p.end) else None
    by_branch = _cust_group_rows(rows, "branch", s["total"])
    by_branch.append(Row("الإجمالي", [s["count"], s["total"], s["total"] - s["overdue"], s["overdue"],
                                      safe_div(s["overdue"], s["total"]),
                                      sum(AG.customer_total(r) for r in rows if AG.is_credit(r.get("ctype"))),
                                      sum(AG.customer_total(r) for r in rows if AG.is_custody(r.get("ctype"))),
                                      sum(AG.n(r.get("guarantee")) for r in rows), 1.0], "tot"))
    if tb_rec is not None:
        by_branch.append(Row("رصيد العملاء في الميزان", [None, tb_rec], "note"))
        by_branch.append(Row("الفرق بين الميزان وتقرير الأعمار", [None, tb_rec - s["total"]], "note"))
    buckets = [sum(AG.n(r[b]) for r in rows) for b in AG.BUCKETS]
    dist = Table(["الفترة"] + AG.BUCKET_NAMES + ["الإجمالي"],
                 [Row("المبلغ", buckets + [sum(buckets)]),
                  Row("النسبة", [safe_div(b, sum(buckets)) for b in buckets] + [1.0], fmt="%")],
                 title="توزيع الأعمار")
    top = sorted(rows, key=lambda r: -AG.customer_overdue(r))[:20]
    top_rows = [Row(r["name"] or "", [r["no"], r.get("branch") or "", r.get("rep") or "", r.get("ctype") or "",
                                      AG.customer_total(r), AG.customer_overdue(r), AG.n(r["b4"])])
                for r in top if AG.customer_overdue(r) > 0.005]
    blocks = [
        Para(f"عملاء مطلوب منهم مطابقة شهرية: {s['need_count']} عميل بمتأخر {s['need_amount']:,.0f}. "
             "المتأخر: العهدة أكثر من 30 يوم، وغيرها أكثر من 60 يوم.", "warn" if s["need_count"] else "good"),
        dist,
        Table(["الفرع"] + CUST_COLS, by_branch, CUST_FMTS, title="حسب الفرع"),
        Table(["المندوب"] + CUST_COLS, _cust_group_rows(rows, "rep", s["total"]), CUST_FMTS, title="حسب المندوب"),
        Table(["اسم العميل", "رقم العميل", "الفرع", "المندوب", "النوع", "الرصيد", "المتأخر", "أكثر من 120"], top_rows,
              ["t", "t", "t", "t", "n", "n", "n"], title="أعلى 20 عميلًا في الرصيد المتأخر"),
    ]
    return Report("customers", "تحليل أرصدة العملاء", f"في نهاية {month_label(p.end)}", blocks)


def rpt_suppliers(ctx: Ctx, p: Params):
    rows = ctx.aging("suppliers", p.end)
    if not rows:
        return Report("suppliers", "تحليل أرصدة الموردين", month_label(p.end),
                      [Para("لا توجد بيانات أعمار موردين لهذا الشهر — ارفعها من شاشة «البيانات الشهرية».", "warn")])
    rate_map = AG.rates(ctx.db)
    base = ctx.base_currency
    s = AG.suppliers_summary(rows, rate_map, base)
    by_cur = {}
    for r in rows:
        by_cur.setdefault((r.get("currency") or base).strip().upper() or base, []).append(r)
    trows = []
    tot_b = [0.0] * 5
    for cur, rs in by_cur.items():
        rate = rate_map.get(cur)
        b = [sum(AG.n(r[x]) for r in rs) for x in AG.BUCKETS]
        tot = sum(b)
        od = sum(AG.supplier_overdue(r) for r in rs)
        if rate is not None:
            tot_b = [t + v * rate for t, v in zip(tot_b, b)]
        trows.append(Row(cur, b + [tot, od, safe_div(od, tot), rate,
                                   None if rate is None else tot * rate, None if rate is None else od * rate]))
    trows.append(Row(f"الإجمالي ({base})", tot_b + [s["total"], s["overdue"], safe_div(s["overdue"], s["total"]),
                                                   None, s["total"], s["overdue"]], "tot"))
    tb_pay = ctx.bs_figures([p.end], 2)["payables"] if ctx.has(p.end) else None
    if tb_pay is not None:
        trows.append(Row("رصيد الموردين في الميزان", [None] * 9 + [tb_pay], "note"))
        trows.append(Row("الفرق بين الميزان وتقرير الأعمار", [None] * 9 + [tb_pay - s["total"]], "note"))
    over = []
    for r in rows:
        rate = AG.supplier_rate(r, rate_map, base)
        if rate is None:
            continue
        o = AG.supplier_overdue(r) * rate
        if o > 0.005:
            over.append((o, r, rate))
    over.sort(key=lambda x: -x[0])
    top_rows = [Row(r["name"] or "", [r["no"], r.get("currency") or base, AG.n(r.get("credit")),
                                      AG.supplier_total(r) * rate, o, AG.n(r["b4"]) * rate])
                for o, r, rate in over[:15]]
    blocks = [
        Para(f"المتجاوز لفترة الائتمان: {s['overdue']:,.0f} {base} لدى {s['over_count']} مورد."
             + (f" ⚠ {s['no_rate']} مورد بعملة بدون سعر صرف — أضف السعر في الإعدادات." if s["no_rate"] else ""),
             "warn" if s["overdue"] > 0.5 or s["no_rate"] else "good"),
        Table(["العملة"] + AG.BUCKET_NAMES + ["الإجمالي", "المتجاوز لفترة الائتمان", "نسبة المتجاوز", "سعر الصرف",
                                              f"الإجمالي ({base})", f"المتجاوز ({base})"], trows,
              ["n", "n", "n", "n", "n", "n", "n", "%", "x", "n", "n"], title="حسب العملة"),
        Table(["اسم المورد", "رقم المورد", "العملة", "فترة الائتمان (يوم)", f"الإجمالي ({base})",
               f"المتجاوز ({base})", f"أكثر من 120 ({base})"], top_rows, ["t", "t", "d", "n", "n", "n"],
              title="أعلى 15 موردًا في المتجاوز لفترة الائتمان"),
    ]
    return Report("suppliers", "تحليل أرصدة الموردين", f"في نهاية {month_label(p.end)}", blocks)

# ================================================================== registry
PERIOD_REPORTS = [
    ("summary", "الملخص التنفيذي", rpt_summary),
    ("checks", "المطابقات والفحوصات", rpt_checks),
    ("diag", "تشخيص الخلل", rpt_diag),
    ("bs", "المركز المالي", rpt_bs),
    ("is", "قائمة الدخل", rpt_is),
    ("cf", "التدفقات النقدية", rpt_cf),
    ("su", "مصادر النقد واستخداماته", rpt_su),
    ("branches", "دخل الفروع وتوزيع مصروفات الإدارة", rpt_branches),
    ("branch_exp", "تحليل مصروفات فرع", rpt_branch_exp),
    ("exp", "تحليل المصروفات بين فترتين", rpt_exp),
    ("ratios", "النسب المالية", rpt_ratios),
    ("customers", "تحليل أرصدة العملاء", rpt_customers),
    ("suppliers", "تحليل أرصدة الموردين", rpt_suppliers),
]
MONTHLY_REPORTS = [
    ("m_is", "قائمة الدخل الشهرية", rpt_m_is),
    ("m_exp", "المصروفات الشهرية حسب المجموعة", rpt_m_exp),
    ("m_bs", "المركز المالي في نهاية كل شهر", rpt_m_bs),
    ("m_kpi", "المؤشرات الشهرية", rpt_m_kpi),
    ("m_cf", "التدفقات النقدية الشهرية", rpt_m_cf),
    ("m_cash", "الكاش راح فين؟", rpt_m_cash),
    ("m_su", "مصادر النقد واستخداماته شهريًا", rpt_m_su),
    ("m_br_sales", "الفروع شهريًا — صافي المبيعات", rpt_m_br_sales),
    ("m_br_profit", "الفروع شهريًا — صافي الربح بعد التوزيع", rpt_m_br_profit),
    ("m_branch", "تحليل فرع شهريًا", rpt_m_branch),
]
ALL_REPORTS = PERIOD_REPORTS + MONTHLY_REPORTS
NEEDS_BRANCH = {"branch_exp", "m_branch"}
NEEDS_VIEW = {"branches"}


def build(key, ctx, params):
    for k, _, fn in ALL_REPORTS:
        if k == key:
            return fn(ctx, params)
    raise KeyError(key)
