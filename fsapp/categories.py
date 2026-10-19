"""Account categories and how each one maps into the financial statements.

Every category belongs to a main group (current assets, non-current assets, ...)
and carries its cash-flow treatment, so the cash flow statement is built
automatically from the classification without any extra input from the user.
"""
from dataclasses import dataclass

# Main groups
CA, NCA, CL, NCL, EQ, REV, EXP, EXCL = "CA", "NCA", "CL", "NCL", "EQ", "REV", "EXP", "EXCL"

BS_GROUPS = (CA, NCA, CL, NCL, EQ)
IS_GROUPS = (REV, EXP)
ASSET_GROUPS = (CA, NCA)

# Cash-flow treatment
CF_CASH = "CASH"          # cash and cash equivalents (the result of the statement)
CF_OP_WC = "OP_WC"        # operating - working capital change
CF_OP_NONCASH = "OP_NC"   # operating - non-cash adjustment (depreciation, provisions)
CF_INV = "INV"            # investing
CF_FIN = "FIN"            # financing
CF_NONE = "NONE"          # income statement accounts (already inside net profit) / excluded

GROUP_NAMES = {
    CA: ("أصول متداولة", "Current assets"),
    NCA: ("أصول غير متداولة (ثابتة)", "Non-current assets"),
    CL: ("التزامات متداولة", "Current liabilities"),
    NCL: ("التزامات غير متداولة (طويلة الأجل)", "Non-current liabilities"),
    EQ: ("حقوق الملكية", "Equity"),
    REV: ("إيرادات", "Revenue & income"),
    EXP: ("مصروفات وتكاليف", "Expenses & costs"),
    EXCL: ("مستبعد", "Excluded"),
}


@dataclass(frozen=True)
class Category:
    key: str
    group: str
    ar: str
    en: str
    cf: str


CATEGORIES = [
    # Current assets
    Category("cash", CA, "النقدية وما في حكمها (خزينة وبنوك)", "Cash and cash equivalents", CF_CASH),
    Category("st_investments", CA, "استثمارات قصيرة الأجل", "Short-term investments", CF_INV),
    Category("receivables", CA, "العملاء وأوراق القبض", "Trade receivables", CF_OP_WC),
    Category("inventory", CA, "المخزون", "Inventory", CF_OP_WC),
    Category("prepaid", CA, "مصروفات مقدمة وأرصدة مدينة أخرى", "Prepayments and other receivables", CF_OP_WC),
    # Non-current assets
    Category("ppe", NCA, "الأصول الثابتة (بالتكلفة)", "Property, plant and equipment (cost)", CF_INV),
    Category("accum_dep", NCA, "مجمع الإهلاك", "Accumulated depreciation", CF_OP_NONCASH),
    Category("cwip", NCA, "مشروعات تحت التنفيذ", "Capital work in progress", CF_INV),
    Category("intangibles", NCA, "أصول غير ملموسة", "Intangible assets", CF_INV),
    Category("lt_investments", NCA, "استثمارات طويلة الأجل", "Long-term investments", CF_INV),
    Category("other_nca", NCA, "أصول غير متداولة أخرى", "Other non-current assets", CF_INV),
    # Current liabilities
    Category("payables", CL, "الموردين وأوراق الدفع", "Trade payables", CF_OP_WC),
    Category("accrued", CL, "مصروفات مستحقة وأرصدة دائنة أخرى", "Accruals and other payables", CF_OP_WC),
    Category("tax_payable", CL, "ضرائب مستحقة", "Taxes payable", CF_OP_WC),
    Category("st_loans", CL, "بنوك دائنة وقروض قصيرة الأجل", "Bank overdrafts and short-term loans", CF_FIN),
    Category("current_ltd", CL, "أقساط قروض طويلة الأجل تستحق خلال عام", "Current portion of long-term loans", CF_FIN),
    # Non-current liabilities
    Category("lt_loans", NCL, "قروض طويلة الأجل", "Long-term loans", CF_FIN),
    Category("provisions", NCL, "مخصصات والتزامات طويلة الأجل أخرى", "Provisions and other long-term liabilities", CF_OP_NONCASH),
    # Equity
    Category("capital", EQ, "رأس المال", "Share capital", CF_FIN),
    Category("reserves", EQ, "الاحتياطيات", "Reserves", CF_FIN),
    Category("retained_earnings", EQ, "أرباح (خسائر) مرحلة", "Retained earnings", CF_FIN),
    Category("drawings", EQ, "توزيعات / جاري الشركاء والمسحوبات", "Dividends / partners' drawings", CF_FIN),
    # Revenue
    Category("revenue", REV, "المبيعات / إيرادات النشاط", "Sales / operating revenue", CF_NONE),
    Category("other_income", REV, "إيرادات أخرى", "Other income", CF_NONE),
    # Expenses
    Category("cogs", EXP, "تكلفة المبيعات / المشتريات", "Cost of sales", CF_NONE),
    Category("selling_exp", EXP, "مصروفات بيعية وتسويقية", "Selling and distribution expenses", CF_NONE),
    Category("admin_exp", EXP, "مصروفات إدارية وعمومية", "General and administrative expenses", CF_NONE),
    Category("depreciation_exp", EXP, "مصروف الإهلاك والاستهلاك", "Depreciation and amortization expense", CF_NONE),
    Category("other_exp", EXP, "مصروفات أخرى", "Other expenses", CF_NONE),
    Category("finance_cost", EXP, "مصروفات تمويلية (فوائد)", "Finance costs (interest)", CF_NONE),
    Category("tax_exp", EXP, "ضريبة الدخل", "Income tax expense", CF_NONE),
    # Excluded
    Category("exclude", EXCL, "حساب رئيسي / إجمالي (يُستبعد)", "Parent / total account (excluded)", CF_NONE),
]

BY_KEY = {c.key: c for c in CATEGORIES}


def cat_name(key, lang):
    c = BY_KEY[key]
    return c.ar if lang == "ar" else c.en


def full_label(key, lang):
    c = BY_KEY[key]
    g = GROUP_NAMES[c.group][0 if lang == "ar" else 1]
    return f"{g} ← {c.ar}" if lang == "ar" else f"{g} → {c.en}"


def keys_in(*groups):
    return [c.key for c in CATEGORIES if c.group in groups]
