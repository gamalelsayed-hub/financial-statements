"""Suggest a category for an account from its name (Arabic or English).

This is only a starting point: the user reviews and confirms every account.
"""
import json
import os
import re

from .categories import BY_KEY


def normalize(s):
    s = (s or "").lower()
    s = re.sub("[إأآا]", "ا", s)
    s = s.replace("ة", "ه").replace("ى", "ي").replace("ـ", "")
    s = re.sub("[ً-ْ]", "", s)  # tashkeel
    return f" {s} "


# Ordered: the first rule that matches wins, so specific rules come first.
RULES = [
    ("exclude", ["اجمالي", "الاجمالي", "مجموع", "total"]),
    ("accum_dep", ["مجمع اهلاك", "مجمع الاهلاك", "مخصص الاهلاك", "مخصص اهلاك", "مجمع استهلاك",
                   "accumulated depreciation", "accumulated amortization", "acc. dep", "acc dep"]),
    ("depreciation_exp", ["مصروف الاهلاك", "مصروف اهلاك", "مصروفات الاهلاك", "اهلاك", "استهلاك",
                          "depreciation", "amortization"]),
    ("tax_exp", ["ضريبه الدخل", "ضرائب الدخل", "income tax expense", "income tax"]),
    ("tax_payable", ["ضرائب مستحقه", "ضريبه مستحقه", "مصلحه الضرائب", "ضريبه القيمه المضافه",
                     "ضرائب", "ضريبه", "tax payable", "vat", "taxes"]),
    ("finance_cost", ["فوائد مدينه", "فوائد بنكيه", "مصروفات بنكيه", "مصاريف بنكيه", "مصروفات تمويليه",
                      "عمولات بنكيه", "interest expense", "finance cost", "bank charges"]),
    ("current_ltd", ["اقساط قروض", "الجزء المتداول", "current portion"]),
    ("lt_loans", ["قروض طويله", "قرض طويل", "long term loan", "long-term loan"]),
    ("st_loans", ["بنوك دائنه", "بنك دائن", "سحب علي المكشوف", "قروض قصيره", "تسهيلات", "قرض",
                  "قروض", "overdraft", "short term loan", "loan"]),
    ("cogs", ["تكلفه المبيعات", "تكلفه البضاعه", "تكلفه الايراد", "تكلفه النشاط", "مشتريات",
              "cost of sales", "cost of goods", "cogs", "purchases"]),
    ("revenue", ["مبيعات", "المبيعات", "ايرادات النشاط", "ايراد النشاط", "ايرادات المبيعات",
                 "مردودات المبيعات", "خصم مسموح", "sales", "revenue"]),
    ("other_income", ["ايرادات اخري", "ايراد اخر", "فوائد دائنه", "ارباح بيع", "ايرادات متنوعه",
                      "other income", "interest income", "gain"]),
    ("selling_exp", ["بيعيه", "تسويق", "دعايه", "اعلان", "عمولات بيع", "نقل للخارج", "selling",
                     "marketing", "advertising", "distribution"]),
    ("cash", ["الصندوق", "صندوق", "خزينه", "الخزينه", "نقديه", "النقديه", "بنك", "البنك", "بنوك",
              "عهد نقديه", "شيكات تحت التحصيل", "cash", "bank", "petty"]),
    ("receivables", ["ديون مشكوك", "مشكوك في تحصيلها", "عملاء", "العملاء", "مدينون", "اوراق قبض", "اوراق القبض", "receivable",
                     "debtors", "customers"]),
    ("inventory", ["مخزون", "المخزون", "بضاعه", "خامات", "مخازن", "inventory", "stock"]),
    ("prepaid", ["مصروفات مقدمه", "مصروف مقدم", "مقدما", "دفعات مقدمه للموردين", "تامينات لدي الغير",
                 "سلف", "ارصده مدينه", "عهد", "prepaid", "prepayment", "advances to"]),
    ("payables", ["موردين", "الموردين", "موردون", "دائنون", "اوراق دفع", "اوراق الدفع", "payable",
                  "creditors", "suppliers"]),
    ("accrued", ["مستحقه", "مستحق", "دائنه اخري", "ارصده دائنه", "دفعات مقدمه من العملاء",
                 "تامينات للغير", "accrued", "accrual", "unearned"]),
    ("cwip", ["تحت التنفيذ", "تحت الانشاء", "work in progress", "cwip"]),
    ("intangibles", ["شهره", "برامج", "علامه تجاريه", "غير ملموسه", "intangible", "goodwill", "software"]),
    ("lt_investments", ["استثمارات طويله", "استثمارات في شركات", "استثمارات عقاريه", "long term invest"]),
    ("st_investments", ["استثمارات", "اوراق ماليه", "ودائع", "investment", "deposits"]),
    ("ppe", ["اصول ثابته", "الاصول الثابته", "مباني", "اراضي", "سيارات", "اثاث", "الات", "معدات",
             "اجهزه", "اجهزه كمبيوتر", "عدد وادوات", "property", "equipment", "vehicles", "furniture",
             "building", "land", "machinery"]),
    ("provisions", ["مخصص", "مخصصات", "مكافاه نهايه الخدمه", "provision", "end of service"]),
    ("capital", ["راس المال", "راس مال", "capital"]),
    ("reserves", ["احتياطي", "الاحتياطي", "reserve"]),
    ("retained_earnings", ["ارباح مرحله", "خسائر مرحله", "ارباح وخسائر مرحله", "الارباح المحتجزه",
                           "retained earnings", "accumulated losses"]),
    ("drawings", ["جاري الشركاء", "جاري الشريك", "مسحوبات", "توزيعات", "drawings", "dividend"]),
    ("admin_exp", ["مصروفات", "مصروف", "مصاريف", "رواتب", "اجور", "مرتبات", "ايجار", "كهرباء",
                   "مياه", "تليفون", "صيانه", "ادوات كتابيه", "اتعاب", "تامينات اجتماعيه",
                   "expense", "salaries", "wages", "rent", "utilities", "admin"]),
]

_RULES_NORM = [(k, [normalize(w).strip() for w in words]) for k, words in RULES]


def suggest(name):
    n = normalize(name)
    for key, words in _RULES_NORM:
        for w in words:
            if w and w in n:
                return key
    return None


# ---- Remembering the user's choices between sessions ----

def _store_path():
    base = os.path.join(os.path.expanduser("~"), ".fsapp")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "classification_memory.json")


def load_memory():
    try:
        with open(_store_path(), encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if v in BY_KEY}
    except (OSError, ValueError):
        return {}


def save_memory(accounts):
    mem = load_memory()
    for a in accounts:
        if a.category:
            mem[memory_key(a)] = a.category
    try:
        with open(_store_path(), "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def memory_key(a):
    return f"{a.code}|{normalize(a.name).strip()}"


def export_mapping(accounts, path):
    data = {memory_key(a): a.category for a in accounts if a.category}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def import_mapping(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return {k: v for k, v in data.items() if v in BY_KEY}


def apply_mapping(accounts, mapping, only_empty=False):
    """Apply a saved mapping, matching on code+name first and then on code alone."""
    by_code = {}
    for k, v in mapping.items():
        by_code.setdefault(k.split("|", 1)[0], v)
    n = 0
    for a in accounts:
        if only_empty and a.category:
            continue
        v = mapping.get(memory_key(a)) or (by_code.get(a.code) if not a.code.startswith("#") else None)
        if v:
            a.category = v
            n += 1
    return n
