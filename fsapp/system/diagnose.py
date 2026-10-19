"""Finds where a problem is when the statements do not balance or an account looks misclassified.

Uses the account-code convention of most charts of accounts (editable in the settings):
1 assets, 2 liabilities, 3 equity, 4 revenue, 5 expenses.
Each difference is split into the accounts that cause it, so the listed amounts add up to the difference.
"""
import json
import re
from dataclasses import dataclass

from .defaults import ASSET_SECTIONS, BS_SECTIONS, IS_SECTIONS

TYPE_NAMES = {"A": "أصول", "L": "التزامات", "E": "حقوق ملكية", "R": "إيرادات", "X": "مصروفات", "": "—"}
TYPE_SECTIONS = {
    "A": set(ASSET_SECTIONS),
    "L": {"CL", "NCL"},
    "E": {"EQ"},
    "R": set(IS_SECTIONS),
    "X": set(IS_SECTIONS),
}
DEFAULT_PREFIX = {"1": "A", "2": "L", "3": "E", "4": "R", "5": "X", "6": "", "7": "", "8": "", "9": ""}
CONTRA_WORDS = ("مجمع", "مخصص", "مردود", "خصم", "جاري", "محتجزة", "مرحلة", "خسائر", "مؤجلة", "تسويات", "فروقات")


@dataclass
class Finding:
    severity: str   # error | warn | info
    area: str
    code: str
    name: str
    amount: float
    issue: str
    fix: str


def prefix_map(db):
    try:
        m = json.loads(db.setting("prefix_map", "") or "{}")
    except ValueError:
        m = {}
    out = dict(DEFAULT_PREFIX)
    out.update({k: v for k, v in m.items() if k in out and v in TYPE_NAMES})
    return out


def expected_type(code, pmap):
    c = (code or "").strip()
    return pmap.get(c[:1], "") if c[:1].isdigit() else ""


def actual_type(section):
    if section in ASSET_SECTIONS:
        return "A"
    if section in ("CL", "NCL"):
        return "L"
    if section == "EQ":
        return "E"
    if section in IS_SECTIONS:
        return "IS"
    return ""


def type_matches(exp, section):
    if not exp or not section:
        return True
    return section in TYPE_SECTIONS[exp]


# ---------------------------------------------------------------- suggestions for unmapped accounts
def _norm(s):
    s = re.sub("[إأآا]", "ا", (s or "").lower()).replace("ة", "ه").replace("ى", "ي")
    return set(w for w in re.split(r"[\s\-_/().،,]+", s) if len(w) > 1)


def suggest(accounts, sections, pmap, code, name):
    """Return (Account-like dict of mapping fields, reason) from the closest mapped account."""
    exp = expected_type(code, pmap)
    mapped = [a for c, a in accounts.items() if c != code and sections.get(a.fs_item)]
    best, best_len = None, 0
    for a in mapped:
        n = 0
        for x, y in zip(a.code, code):
            if x != y:
                break
            n += 1
        if n > best_len and type_matches(exp, sections.get(a.fs_item)):
            best, best_len = a, n
    if best and best_len >= max(3, len(code) - 3):
        kw, why = _keyword_suggestion(sections, exp, code, name, strong_only=True)
        if kw and kw.fs_item != best.fs_item:
            return kw, why
        return best, f"نفس ربط الحساب الأقرب في الرقم {best.code} ({best.name})"
    words = _norm(name)
    scored = []
    for a in mapped:
        if not type_matches(exp, sections.get(a.fs_item)):
            continue
        common = len(words & _norm(a.name))
        if common:
            scored.append((common, len(a.code), a))
    if scored:
        scored.sort(key=lambda x: (-x[0], x[1]))
        a = scored[0][2]
        return a, f"تشابه الاسم مع الحساب {a.code} ({a.name})"
    return _keyword_suggestion(sections, exp, code, name)


# Name keywords (shared with the quick tool) → default items of a new company.
# old category: (fs item, cash-flow item, branch income category, expense group)
KEYWORD_TARGETS = {
    "cash": ("النقد وما في حكمه", "النقد", "", ""),
    "st_investments": ("استثمارات قصيرة الأجل", "الاستثمارات", "", ""),
    "receivables": ("العملاء وعهد المبيعات", "العملاء وعهد المبيعات", "", ""),
    "inventory": ("المخزون", "المخزون", "", ""),
    "prepaid": ("أرصدة مدينة أخرى ومصروفات مقدمة", "أرصدة مدينة أخرى", "", ""),
    "ppe": ("الأصول الثابتة (التكلفة)", "شراء واستبعاد أصول ثابتة", "", ""),
    "intangibles": ("الأصول الثابتة (التكلفة)", "شراء واستبعاد أصول ثابتة", "", ""),
    "accum_dep": ("مجمع إهلاك الأصول الثابتة", "الإهلاك", "", ""),
    "cwip": ("مشروعات تحت التنفيذ", "مشروعات تحت التنفيذ", "", ""),
    "lt_investments": ("استثمارات طويلة الأجل", "الاستثمارات", "", ""),
    "other_nca": ("استثمارات طويلة الأجل", "الاستثمارات", "", ""),
    "payables": ("الموردون والدائنون التجاريون", "الموردون والدائنون التجاريون", "", ""),
    "accrued": ("مصاريف مستحقة", "المصاريف المستحقة", "", ""),
    "tax_payable": ("ضريبة القيمة المضافة المستحقة", "ضريبة القيمة المضافة", "", ""),
    "st_loans": ("قروض بنكية قصيرة الأجل", "القروض قصيرة الأجل والاعتمادات", "", ""),
    "current_ltd": ("أقساط متداولة من القروض طويلة الأجل", "القروض طويلة الأجل", "", ""),
    "lt_loans": ("قروض طويلة الأجل", "القروض طويلة الأجل", "", ""),
    "provisions": ("مخصص نهاية الخدمة", "المخصصات", "", ""),
    "capital": ("رأس المال", "رأس المال والاحتياطيات", "", ""),
    "reserves": ("الاحتياطيات", "رأس المال والاحتياطيات", "", ""),
    "retained_earnings": ("الأرباح المحتجزة", "تسويات حقوق الملكية", "", ""),
    "drawings": ("جاري الملاك", "جاري الملاك", "", ""),
    "revenue": ("إجمالي المبيعات", "", "المبيعات", ""),
    "other_income": ("إيرادات أخرى متعلقة بالنشاط", "", "إيرادات أخرى", ""),
    "cogs": ("تكلفة المبيعات", "", "تكلفة المبيعات", ""),
    "selling_exp": ("مصروفات بيعية وتسويقية", "", "مصروفات تشغيلية", "مصروفات تسويقية ومستلزمات"),
    "admin_exp": ("مصروفات عمومية وإدارية", "", "مصروفات تشغيلية", "مصروفات عمومية أخرى"),
    "depreciation_exp": ("الإهلاك", "", "مصروفات تشغيلية", "الإهلاك"),
    "other_exp": ("مصروفات وخسائر غير عادية", "", "إيرادات ومصروفات غير تشغيلية", ""),
    "finance_cost": ("مصروفات تمويلية", "", "مصروفات تمويلية", ""),
    "tax_exp": ("الزكاة", "", "الزكاة", ""),
}
# refinements by words in the account name: (words, fs item, branch category, expense group)
NAME_REFINE = [
    (("مردود",), "مردودات المبيعات", "مردودات المبيعات", None),
    (("خصم مسموح",), "الخصم المسموح به", "الخصم المسموح به", None),
    (("رواتب", "اجور", "أجور", "مرتبات"), "رواتب وأجور - إدارية", None, "الرواتب والأجور وما في حكمها"),
    (("ايجار", "إيجار"), None, None, "الإيجارات"),
    (("كهرباء", "مياه"), None, None, "الكهرباء والمياه"),
    (("هاتف", "تليفون", "اتصالات", "انترنت", "إنترنت"), None, None, "الاتصالات والتقنية"),
    (("سيارات", "وقود", "محروقات"), None, None, "السيارات والرافعات"),
    (("رسوم حكومية", "اقامات", "إقامات"), None, None, "الرسوم الحكومية والإقامات"),
    (("نقل", "شحن"), None, None, "نقل البضائع"),
    (("عمولات بنكية", "رسوم بنكية", "مصروفات بنكية"), None, None, "رسوم بنكية وتمويلية وشبكات"),
]


class _Suggestion:
    def __init__(self, fs_item, cf_item, branch_cat, exp_group):
        self.code, self.name, self.grp, self.behavior = "", "", "", ""
        self.fs_item, self.cf_item, self.branch_cat, self.exp_group = fs_item, cf_item, branch_cat, exp_group


# Name keywords specific enough to win over the mapping of the neighbouring account number.
STRONG_KEYWORDS = {"accum_dep"}


def _keyword_suggestion(sections, exp, code, name, strong_only=False):
    from ..classifier import suggest as keyword_category
    cat = keyword_category(name)
    if cat not in KEYWORD_TARGETS or (strong_only and cat not in STRONG_KEYWORDS):
        return None, ""
    fs, cf, bc, grp = KEYWORD_TARGETS[cat]
    if sections.get(fs) in IS_SECTIONS:
        for words, r_fs, r_bc, r_grp in NAME_REFINE:
            if any(w in name for w in words):
                fs = r_fs if r_fs and r_fs in sections else fs
                bc = r_bc or bc
                grp = r_grp or grp
                break
    if fs not in sections or not type_matches(exp, sections[fs]):
        return None, ""
    return _Suggestion(fs, cf, bc, grp), "من اسم الحساب" + (f" ورقمه يبدأ بـ {code[:1]}" if exp else "")


# ---------------------------------------------------------------- trial balance imbalance hints
def tb_imbalance_hints(rows, tol=0.5):
    """rows: {code: (name, od, oc, md, mc, cd, cc)}. Returns findings explaining unbalanced columns."""
    out = []
    cols = (("الافتتاحي", 1, 2), ("الحركة", 3, 4), ("الختامي", 5, 6))
    codes = sorted(rows)
    parents = {c for i, c in enumerate(codes) if i + 1 < len(codes) and codes[i + 1].startswith(c) and codes[i + 1] != c}
    for label, d, c in cols:
        diff = sum((r[d] or 0) for r in rows.values()) - sum((r[c] or 0) for r in rows.values())
        if abs(diff) <= tol:
            continue
        side = "المدين أكبر" if diff > 0 else "الدائن أكبر"
        out.append(Finding("error", f"توازن الميزان ({label})", "", "", diff,
                           f"عمود {label} غير متوازن ({side} بـ {abs(diff):,.2f}).",
                           "راجع الأسباب المحتملة التالية، أو أعد تصدير الميزان من النظام."))
        for code, r in rows.items():
            for amt, side_name in ((r[d] or 0, "مدين"), (r[c] or 0, "دائن")):
                if amt <= tol:
                    continue
                if abs(amt - abs(diff)) <= tol:
                    out.append(Finding("warn", f"توازن الميزان ({label})", code, r[0], amt,
                                       f"رصيده {side_name} يساوي الفرق بالضبط.",
                                       "ربما الحساب مكرر أو ناقص له حساب مقابل — تأكد من وجوده مرة واحدة."))
                elif abs(amt - abs(diff) / 2) <= tol:
                    out.append(Finding("warn", f"توازن الميزان ({label})", code, r[0], amt,
                                       f"رصيده {side_name} يساوي نصف الفرق.",
                                       f"غالبًا مسجل في الجانب الخطأ (مدين بدل دائن أو العكس)."))
        if abs(diff) >= 9 and abs(round(diff) - diff) < 0.01 and round(abs(diff)) % 9 == 0:
            out.append(Finding("info", f"توازن الميزان ({label})", "", "", diff,
                               "الفرق يقبل القسمة على 9.",
                               "احتمال خطأ تبديل أرقام عند الإدخال (مثلًا 5,400 بدل 4,500)."))
        if parents:
            pdiff = sum((rows[p][d] or 0) - (rows[p][c] or 0) for p in parents)
            if abs(abs(pdiff) - abs(diff)) <= tol:
                out.append(Finding("error", f"توازن الميزان ({label})", "", "", pdiff,
                                   f"مجموع الحسابات الرئيسية ({len(parents)}) يساوي الفرق.",
                                   "الميزان يحتوي حسابات رئيسية مع فرعياتها — احذف الرئيسية عند الرفع."))
    for code, r in rows.items():
        gap = (r[1] or 0) - (r[2] or 0) + (r[3] or 0) - (r[4] or 0) - ((r[5] or 0) - (r[6] or 0))
        if abs(gap) > tol:
            out.append(Finding("warn", "سطر الميزان", code, r[0], gap,
                               "الرصيد الختامي لا يساوي الافتتاحي + الحركة.",
                               "راجع الحساب في تصدير النظام (قيد بعد الإقفال أو عمود منقول خطأ)."))
    return out


# ---------------------------------------------------------------- full diagnosis
def diagnose(ctx, months):
    end = months[-1]
    pmap = prefix_map(ctx.db)
    tb = ctx.tbs.get(end, {})
    bal = ctx.bal(months)
    findings = []
    summary = []

    def acc_name(code):
        a = ctx.accounts.get(code)
        if a and a.name:
            return a.name
        r = tb.get(code)
        return r[0] if r else ""

    def sug_text(code):
        a, why = suggest(ctx.accounts, ctx.fs_section, pmap, code, acc_name(code))
        if not a:
            exp = expected_type(code, pmap)
            return f"اربطه ببند {TYPE_NAMES[exp]}." if exp else "اربطه ببند قائمة في شاشة الربط."
        return f"اقتراح: بند «{a.fs_item}»" + (f" / تدفق «{a.cf_item}»" if a.cf_item else "") + f" — {why}."

    # 1) trial balance itself
    tb_findings = tb_imbalance_hints(tb) if tb else []
    tb_bad = any(f.severity == "error" and f.area.startswith("توازن") for f in tb_findings)
    findings += tb_findings
    if tb_bad:
        summary.append("الميزان المدخل نفسه غير متوازن — هذا يظهر في «فرق ميزان المراجعة» داخل حقوق الملكية. ابدأ بإصلاحه.")

    # 2) balance sheet difference = unmapped accounts
    bs = ctx.bs_figures([end], 2)
    if abs(bs["diff"]) > 0.5:
        parts = []
        for code, (o, m, c) in bal.items():
            a = ctx.accounts.get(code)
            if not (a and a.fs_item in ctx.fs_section) and abs(c) > 0.005:
                parts.append((code, -c))
        parts.sort(key=lambda x: -abs(x[1]))
        summary.append(f"المركز المالي غير متوازن بفرق {bs['diff']:,.2f}. السبب: {len(parts)} حساب غير مربوط ببند قائمة "
                       f"مجموع أثرها {sum(p[1] for p in parts):,.2f}.")
        for code, amt in parts:
            exp = expected_type(code, pmap)
            findings.append(Finding("error", "توازن المركز المالي", code, acc_name(code), amt,
                                    "غير مربوط ببند قائمة" + (f" (رقمه يبدأ بـ {code[:1]} ← غالبًا {TYPE_NAMES[exp]})" if exp else ""),
                                    sug_text(code)))

    # 3) cash-flow difference split by cause
    cf = ctx.cash_flow(months)
    if abs(cf["cash_diff"]) > 0.5:
        parts = []
        for code, (o, m, c) in bal.items():
            a = ctx.accounts.get(code)
            sec = ctx.section(code)
            item = a.cf_item if a and a.cf_item in ctx.cf_activity else ""
            if not sec:
                if abs(m) > 0.005:
                    parts.append(Finding("error", "التدفقات النقدية", code, acc_name(code), m,
                                         "حساب غير مربوط ببند قائمة وله حركة.", sug_text(code)))
            elif sec in BS_SECTIONS and not item and abs(m) > 0.005:
                exp_cf = "النقد" if ctx.fs_role.get(a.fs_item) == "cash" else "بند التدفق المناسب"
                parts.append(Finding("error", "التدفقات النقدية", code, acc_name(code), m,
                                     "حساب ميزانية له حركة وليس له بند تدفق.",
                                     f"في الربط أعطه «{exp_cf}»." if exp_cf == "النقد" else sug_text(code)))
            elif sec in BS_SECTIONS and item and ctx.cf_activity[item] == "CASH" and abs(m - (c - o)) > 0.005:
                parts.append(Finding("error", "التدفقات النقدية", code, acc_name(code), m - (c - o),
                                     "حساب نقدية: الحركة ≠ الختامي − الافتتاحي.", "راجع سطر الحساب في الميزان."))
        sums = [sum((r[i] or 0) for r in ctx.tbs.get(x, {}).values()) for x in months for i in (3, 4)]
        t = sum(sums[0::2]) - sum(sums[1::2])
        if abs(t) > 0.005:
            parts.append(Finding("error", "التدفقات النقدية", "", "", -t, "عمود الحركة في الميزان غير متوازن.",
                                 "أصلح توازن الميزان أولًا."))
        explained = sum(p.amount for p in parts)
        summary.append(f"التدفقات لا تنتهي برصيد النقد الفعلي (فرق {cf['cash_diff']:,.2f}). الأسباب المكتشفة مجموعها "
                       f"{explained:,.2f}.")
        findings += parts
    # cash accounts consistency (even if it balances)
    for code, a in ctx.accounts.items():
        if code not in bal:
            continue
        is_cash_item = a.cf_item in ctx.cf_activity and ctx.cf_activity[a.cf_item] == "CASH"
        is_cash_role = ctx.fs_role.get(a.fs_item) == "cash"
        if is_cash_item != is_cash_role and ctx.section(code) in BS_SECTIONS:
            findings.append(Finding("warn", "التدفقات النقدية", code, a.name, bal[code][2],
                                    "بند القائمة نقدية وبند التدفق ليس «النقد»" if is_cash_role else
                                    "بند التدفق «النقد» لكن بند القائمة ليس نقدية",
                                    "وحّد ربط الحساب: حسابات الخزينة والبنوك = بند النقد في القائمة والتدفق."))

    # 4) code prefix vs mapping (misclassification that does not unbalance anything)
    wrong = []
    for code, (o, m, c) in bal.items():
        a = ctx.accounts.get(code)
        if not a or a.fs_item not in ctx.fs_section:
            continue
        exp = expected_type(code, pmap)
        sec = ctx.fs_section[a.fs_item]
        if exp and not type_matches(exp, sec):
            big = (exp in ("A", "L", "E")) != (sec in BS_SECTIONS)
            amount = c if sec in BS_SECTIONS else m
            wrong.append(Finding("error" if big else "warn", "تصنيف حسب رقم الحساب", code, a.name, amount,
                                 f"رقمه يبدأ بـ {code[:1]} ({TYPE_NAMES[exp]}) لكنه مربوط بـ «{a.fs_item}»"
                                 + (" في " + ("الميزانية" if sec in BS_SECTIONS else "قائمة الدخل")),
                                 ("يغيّر صافي الربح وحقوق الملكية حتى لو القوائم متوازنة — راجع الربط."
                                  if big else "تأكد أن هذا مقصود (مثل حساب مقابل أو حساب جاري).")))
    if wrong:
        summary.append(f"{len(wrong)} حساب ربطه لا يتفق مع رقمه "
                       f"({sum(1 for w in wrong if w.severity == 'error')} منها بين الميزانية وقائمة الدخل).")
    findings += wrong

    # 5) balances on the unusual side
    for code, (o, m, c) in bal.items():
        a = ctx.accounts.get(code)
        if not a or a.fs_item not in ctx.fs_section or abs(c) < 1:
            continue
        sec = ctx.fs_section[a.fs_item]
        text = a.fs_item + " " + a.name
        if any(w in text for w in CONTRA_WORDS):
            continue
        if sec in ASSET_SECTIONS and c < -1:
            findings.append(Finding("warn", "طبيعة الرصيد", code, a.name, c, "أصل برصيده دائن.",
                                    "راجع القيود (سداد أكثر من الرصيد؟) أو الربط (ربما التزام)."))
        elif sec in ("CL", "NCL") and c > 1:
            findings.append(Finding("warn", "طبيعة الرصيد", code, a.name, c, "التزام برصيده مدين.",
                                    "راجع القيود (دفعة مقدمة؟) أو الربط (ربما أصل)."))

    # 6) parent accounts inside the trial balance (double counting)
    codes = sorted(tb)
    for i, cde in enumerate(codes):
        if i + 1 < len(codes) and codes[i + 1].startswith(cde) and codes[i + 1] != cde:
            r = tb[cde]
            findings.append(Finding("error", "حسابات رئيسية", cde, r[0], (r[5] or 0) - (r[6] or 0),
                                    "حساب رئيسي موجود مع حساباته الفرعية (رصيده يتكرر).",
                                    "احذف الحسابات الرئيسية من الميزان وأعد رفعه."))

    # 7) branch income vs income statement
    comp = ctx.branch_figures(ctx.company_pl_values(months))
    if abs(comp["unmapped"]) > 0.5:
        for code, v in ctx.company_pl_values(months).items():
            a = ctx.accounts.get(code)
            if not a or a.branch_cat not in ctx.cat_kind:
                if abs(v) > 0.005:
                    s, why = suggest(ctx.accounts, ctx.fs_section, pmap, code, acc_name(code))
                    fix = f"اقتراح: فئة «{s.branch_cat}» — {why}." if s and s.branch_cat else "أعطه فئة دخل الفروع."
                    findings.append(Finding("error", "دخل الفروع", code, acc_name(code), v,
                                            "حساب دخل بلا فئة دخل الفروع (دخل الفروع لن يطابق قائمة الدخل).", fix))
    if abs(comp["no_group"]) > 0.5:
        for code, v in ctx.company_pl_values(months).items():
            a = ctx.accounts.get(code)
            if a and ctx.cat_kind.get(a.branch_cat) == "opex" and a.exp_group not in ctx.exp_groups and abs(v) > 0.005:
                findings.append(Finding("warn", "مجموعات المصروفات", code, a.name, v,
                                        "مصروف تشغيلي بلا مجموعة مصروف.", "أعطه مجموعة مصروف في الربط."))

    # 8) month-to-month continuity
    from .calc import month_add, month_label
    for per in months:
        prev = month_add(per, -1)
        if prev not in ctx.tbs or per not in ctx.tbs:
            continue
        a_, b_ = ctx.tbs[prev], ctx.tbs[per]
        for code in set(a_) | set(b_):
            ca = (a_[code][5] - a_[code][6]) if code in a_ else 0.0
            ob = (b_[code][1] - b_[code][2]) if code in b_ else 0.0
            if abs(ca - ob) > 1:
                findings.append(Finding("warn", "استمرارية الأرصدة", code, acc_name(code), ob - ca,
                                        f"رصيد أول {month_label(per)} ≠ رصيد آخر {month_label(prev)}.",
                                        f"قيد سُجل على {month_label(prev)} بعد رفع ميزانه — أعد رفع ميزان {month_label(prev)}."))

    order = {"error": 0, "warn": 1, "info": 2}
    areas = ["توازن الميزان", "سطر الميزان", "حسابات رئيسية", "توازن المركز المالي", "التدفقات النقدية",
             "تصنيف حسب رقم الحساب", "دخل الفروع", "مجموعات المصروفات", "استمرارية الأرصدة", "طبيعة الرصيد"]

    def area_rank(a):
        return next((i for i, x in enumerate(areas) if a.startswith(x)), len(areas))

    findings.sort(key=lambda f: (order[f.severity], area_rank(f.area), -abs(f.amount or 0)))
    if not summary and not any(f.severity == "error" for f in findings):
        summary.append("لا توجد أخطاء: الميزان والقوائم متوازنة والربط متسق مع أرقام الحسابات.")
    return summary, findings
