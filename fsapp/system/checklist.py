"""Inputs checklist: which files were uploaded for each month of the year and which are missing.

One row per kind of input (trial balance, branches, agings, items, reps ...), one column per month. A kind of input
the company never uploaded is shown as «not used» instead of missing, so the list stays about what matters.
"""
from .blocks import Para, Report, Row, Table
from .calc import month_add, month_label, range_label

OK, MISSING, PARTIAL, UNUSED = "✓", "✗", "◐", "—"


def months_between(a, b):
    """Every month from a to b."""
    out, m = [], a
    while m <= b:
        out.append(m)
        m = month_add(m, 1)
    return out


def _cell(status, note=""):
    return (status + (f" {note}" if note else "")).strip(), status


def monthly_status(ctx, months):
    """[(input name, used?, {month: (text, status)}, what to do when missing)]."""
    db = ctx.db
    rows = []

    # trial balance: missing, or uploaded before entries that were posted later (the next month's opening differs)
    tb = {}
    for m in months:
        if m not in ctx.tbs:
            tb[m] = _cell(MISSING)
        elif ctx.continuity_breaks(month_add(m, 1)):
            tb[m] = _cell(PARTIAL, "أعد رفعه")
        else:
            tb[m] = _cell(OK)
    rows.append(("ميزان المراجعة", True, tb, "«البيانات الشهرية» ← رفع ميزان الشهر. «أعد رفعه» = قيود اتسجلت على الشهر "
                                             "بعد رفعه (رصيد أول الشهر اللي بعده مختلف)."))

    # branch movements: every branch of the list
    branches = list(ctx.branches)
    used = bool(ctx.bmov)
    br = {}
    for m in months:
        have = [b for b in branches if ctx.bmov.get(m, {}).get(b)]
        if not ctx.bmov.get(m):
            br[m] = _cell(MISSING)
        elif branches and len(have) < len(branches):
            br[m] = _cell(PARTIAL, f"{len(have)}/{len(branches)}")
        else:
            br[m] = _cell(OK)
    rows.append(("حركة الفروع", used, br, "«البيانات الشهرية» ← رفع حركة الفروع. الرقم = عدد الفروع المرفوعة من القائمة."))

    for table, name in (("customers", "أعمار العملاء"), ("suppliers", "أعمار الموردين")):
        ps = set(db.aging_periods(table))
        rows.append((name, bool(ps), {m: _cell(OK if m in ps else MISSING) for m in months},
                     "«البيانات الشهرية» ← رفع الأعمار لآخر الشهر."))

    items = db.item_periods()
    sales = {p for p, v in items.items() if v[0]}
    purch = {p for p, v in items.items() if v[2]}
    no_cost = {p for p, v in items.items() if v[0] and not v[1]}
    rows.append(("مبيعات الأصناف", bool(sales),
                 {m: _cell(MISSING) if m not in sales else _cell(PARTIAL, "بدون تكلفة") if m in no_cost else _cell(OK)
                  for m in months}, "«الأصناف والعملاء» ← رفع مبيعات الشهر (PDF أو Excel)."))
    rows.append(("مشتريات الأصناف", bool(purch), {m: _cell(OK if m in purch else MISSING) for m in months},
                 "«الأصناف والعملاء» ← رفع مشتريات الشهر."))

    # sales reps
    files = db.rep_sales_files()
    monthly = {a for _, a, b, _, _ in files if a == b}
    ranged = {m for _, a, b, _, _ in files if a != b for m in months_between(a, b)}
    rows.append(("مبيعات المناديب (الأصناف أو العملاء بالمندوب)", bool(files),
                 {m: _cell(OK) if m in monthly else _cell(PARTIAL, "ضمن ملف فترة") if m in ranged else _cell(MISSING)
                  for m in months},
                 "«تقييم المناديب» ← البيانات. «ضمن ملف فترة» = الشهر داخل ملف مجمّع، فما يظهر لوحده."))
    for table, name in (("invoices", "فواتير المناديب"), ("receipts", "سندات القبض")):
        ps = set(db.monthly_counts(table))
        rows.append((name, bool(ps), {m: _cell(OK if m in ps else MISSING) for m in months},
                     "«تقييم المناديب» ← البيانات."))
    com = set(db.commissions())
    rows.append(("عمولات المناديب", bool(com), {m: _cell(OK if m in com else MISSING) for m in months},
                 "«تقييم المناديب» ← البيانات ← العمولات الشهرية."))
    return rows


def setup_status(ctx, end):
    """Inputs that are not monthly: account mapping, branches, reps, customers, last year's trial balance."""
    db = ctx.db
    out = []
    unmapped = [c for p in ctx.tbs for c in ctx.tbs[p] if not ctx.section(c)]
    n = len(set(unmapped))
    out.append(("ربط الحسابات بالقوائم", OK if not n else MISSING, f"{n} حساب غير مربوط" if n else "كل الحسابات مربوطة",
                "«ربط الحسابات» ← فلتر الحسابات الناقصة."))
    if ctx.bmov:
        no_cat = {c for p in ctx.bmov for b in ctx.bmov[p] for c in ctx.bmov[p][b]
                  if not ctx.is_bs(c) and not (ctx.accounts.get(c) and ctx.accounts[c].branch_cat)}
        out.append(("فئات دخل الفروع", OK if not no_cat else MISSING,
                    f"{len(no_cat)} حساب في حركة الفروع بدون فئة" if no_cat else "كل حسابات الفروع لها فئة",
                    "«ربط الحسابات» ← عمود فئة دخل الفروع."))
    reps = db.reps()
    if reps:
        active = [r for r in reps.values() if r["active"] not in (0, "0")]
        no_sal = [r["name"] for r in active if not r["salary"]]
        no_tgt = [r["name"] for r in active if not r["target"]]
        bad = no_sal or no_tgt
        note = "، ".join(x for x in (f"بدون راتب: {'، '.join(no_sal[:4])}" if no_sal else "",
                                     f"بدون تارجت: {'، '.join(no_tgt[:4])}" if no_tgt else "") if x)
        out.append(("بيانات المناديب (الراتب والتارجت)", PARTIAL if bad else OK, note or f"{len(active)} مندوب مكتمل",
                    "«تقييم المناديب» ← البيانات ← جدول المناديب."))
    cm = db.customer_master()
    out.append(("بيانات العملاء (الفرع والمندوب)", OK if cm else UNUSED, f"{len(cm):,} عميل" if cm else "غير مرفوعة",
                "«الأصناف والعملاء» ← بيانات العملاء."))
    y, m = int(end[:4]), int(end[5:7])
    ends_in = y if (ctx.fiscal_start == 1 or m < ctx.fiscal_start) else y + 1
    prev_year = ctx.year_key(ends_in - 1)
    annual = db.annual_periods()
    has = prev_year in annual or prev_year in ctx.tbs
    out.append(("ميزان السنة السابقة (للمقارنات وأول المدة)", OK if has else MISSING,
                f"{month_label(prev_year)}: " + ("مرفوع" if has else "غير مرفوع"),
                "«البيانات الشهرية» ← ميزان آخر شهر في السنة السابقة، أو الموازين السنوية."))
    return out


def summary(ctx, months):
    """(missing cells, months with something missing) for the dashboard / data page."""
    miss = set()
    count = 0
    for name, used, cells, _ in monthly_status(ctx, months):
        if not used:
            continue
        for m, (_, st) in cells.items():
            if st in (MISSING, PARTIAL):
                count += 1
                miss.add(m)
    return count, sorted(miss)


def rpt_inputs(ctx, p):
    months = ctx.ytd_months(p.end)
    rows_m = monthly_status(ctx, months)
    styles = {OK: "good", MISSING: "bad", PARTIAL: "warn", UNUSED: None}
    rows = []
    for name, used, cells, fix in rows_m:
        if not used:
            rows.append(Row(name, ["غير مستخدم"] + [UNUSED] * len(months) + [""], "note"))
            continue
        vals = [cells[m][0] for m in months]
        st = [styles[cells[m][1]] for m in months]
        ok = sum(1 for m in months if cells[m][1] == OK)
        rows.append(Row(name, [f"{ok}/{len(months)}"] + vals + [fix], styles=[None] + st + [None]))
    cols = ["المدخل", "المكتمل"] + [month_label(m) for m in months] + ["المكان / الحل"]
    count, miss = summary(ctx, months)
    head = Para("✓ كل المدخلات المستخدمة مرفوعة لكل شهور السنة." if not count else
                f"⚠ ناقص أو يحتاج مراجعة: {count} خانة في {len(miss)} شهر — "
                + "، ".join(month_label(m) for m in miss), "good" if not count else "bad")
    blocks = [head, Table(cols, rows, ["t"] + ["t"] * len(months) + ["t"], title="المدخلات الشهرية"),
              Para("✓ مرفوع   ✗ ناقص   ◐ ناقص جزئيًا أو يحتاج إعادة رفع   — مدخل لم يُستخدم في هذه الشركة")]
    srows = [Row(name, [st, note, fix], styles=[styles.get(st), None, None]) for name, st, note, fix in setup_status(ctx, p.end)]
    blocks.append(Table(["الإعداد", "الحالة", "التفاصيل", "المكان / الحل"], srows, ["t", "t", "t"],
                        title="البيانات الثابتة والربط"))
    return Report("inputs", "قائمة تحقق المدخلات", range_label(months), blocks)
