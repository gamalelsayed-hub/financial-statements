"""Sales reps: reading the system reports the rep evaluation is built from.

- Sales by rep (items or customers): rep column like "4002-سلطان العمودي", the item or customer, net and cost.
- Invoices: number, type (نقد / آجل / من حساب), date, account, customer name, net, cost.
- Receipt vouchers: number, date, type, box / bank, account, account name, analytic account (customer number), amount.
- Rep settings (salary, target ...) and monthly commissions from Excel.
"""
import datetime
import re

from ..importer import to_number

REP_RE = re.compile(r"^\s*(\d+)\s*-\s*(.*)$")
MONTH_RE = re.compile(r"^\s*(\d{4})\s*[-/]\s*(\d{1,2})\s*$")


def norm_name(s):
    """Name for matching: no extra spaces, one form of alef / yaa / taa marbuta."""
    s = str(s or "").strip()
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه"), ("ـ", "")):
        s = s.replace(a, b)
    return " ".join(s.split())


def split_rep(v):
    """'4002-سلطان العمودي' → ('4002', 'سلطان العمودي'); a plain name → ('', name)."""
    s = str(v or "").strip()
    m = REP_RE.match(s)
    if m:
        return m.group(1), m.group(2).strip()
    return "", s


def text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def find_header(rows, must, limit=30):
    """Index of the first row whose cells contain every word in must."""
    for i, r in enumerate(rows[:limit]):
        cells = " | ".join(text(c) for c in r)
        if all(w in cells for w in must):
            return i
    return None


def col_of(header, *words, exclude=()):
    for w in words:
        for i, c in enumerate(header):
            t = text(c)
            if w in t and not any(x in t for x in exclude):
                return i
    return None


# ------------------------------------------------------------------ sales by rep
def parse_rep_sales(rows):
    """Items-by-rep or customers-by-rep report → (kind, rows). kind: items | customers."""
    h = find_header(rows, ["صافي", "التكلفة"])
    if h is None:
        raise ValueError("ما لقيت صف العناوين (صافي … التكلفة).")
    header = rows[h]
    net_c = col_of(header, "صافي")
    cost_c = col_of(header, "التكلفة")
    body = [r for r in rows[h + 1:] if any(c not in (None, "") for c in r)]
    # the rep column is the one whose values look like "4002-name"
    best, rep_c = 0, None
    for c in range(len(header)):
        n = sum(1 for r in body[:300] if REP_RE.match(text(r[c])))
        if n > best:
            best, rep_c = n, c
    if rep_c is None:
        raise ValueError("ما لقيت عمود المندوب (قيم مثل 4002-اسم المندوب).")
    others = [c for c in range(len(header)) if c not in (rep_c, net_c, cost_c)]
    key_c, name_c = others[0], others[1] if len(others) > 1 else others[0]
    kind = "items" if "الصنف" in " ".join(text(c) for c in header) else "customers"
    out = {}
    for r in body:
        code, rname = split_rep(r[rep_c])
        key = text(r[key_c])
        if not code or not key:
            continue
        k = (code, key)
        rec = out.setdefault(k, {"rep": code, "rep_name": rname, "key": key, "name": text(r[name_c]),
                                 "net": 0.0, "cost": 0.0})
        rec["net"] += to_number(r[net_c]) or 0.0
        rec["cost"] += to_number(r[cost_c]) or 0.0
    return kind, list(out.values())


# ------------------------------------------------------------------ dates
def _parse_text_date(s):
    s = s.strip().split(" ")[0]
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def read_dates(values):
    """Dates of a column as written by the system (day/month/year).

    Excel turns a text date whose day is 12 or less into a real date with day and month swapped (10/02/2026
    becomes 2 October → 10 February). When the column also has text dates, the real dates are swapped back if
    that puts them in the same months as the text dates. Returns (dates, number swapped back)."""
    parsed, kinds = [], []
    for v in values:
        if isinstance(v, datetime.datetime):
            parsed.append(v.date())
            kinds.append("dt")
        elif isinstance(v, datetime.date):
            parsed.append(v)
            kinds.append("dt")
        elif v not in (None, ""):
            parsed.append(_parse_text_date(str(v)))
            kinds.append("txt")
        else:
            parsed.append(None)
            kinds.append("")
    text_months = {(d.year, d.month) for d, k in zip(parsed, kinds) if k == "txt" and d}

    def swapped(d):
        return datetime.date(d.year, d.day, d.month) if d.day <= 12 else d

    dts = [d for d, k in zip(parsed, kinds) if k == "dt" and d]
    if not text_months or not dts:
        return parsed, 0
    as_is = sum(1 for d in dts if (d.year, d.month) in text_months)
    sw = sum(1 for d in dts if (swapped(d).year, swapped(d).month) in text_months)
    if sw <= as_is:
        return parsed, 0
    out, n = [], 0
    for d, k in zip(parsed, kinds):
        if k == "dt" and d and d.day <= 12 and d.day != d.month:
            out.append(swapped(d))
            n += 1
        else:
            out.append(d)
    return out, n


def _by_month(recs, dates, fallback):
    out, no_date = {}, 0
    for rec, d in zip(recs, dates):
        if d:
            p = f"{d.year:04d}-{d.month:02d}"
            rec["date"] = d.isoformat()
        else:
            p = fallback
            no_date += 1
        if p:
            out.setdefault(p, []).append(rec)
    return out, no_date


def dominant(by):
    """(month with most rows, its share of all rows)."""
    total = sum(len(v) for v in by.values())
    if not total:
        return None, 0.0
    p = max(by, key=lambda k: len(by[k]))
    return p, len(by[p]) / total


def merge_into(by, period):
    """Every row in one month (a monthly report whose returns carry the dates of older invoices)."""
    return {period: [r for v in by.values() for r in v]}


# ------------------------------------------------------------------ invoices
def parse_invoices(rows, fallback=None):
    """Invoices report → ({month: [invoice]}, info)."""
    h = find_header(rows, ["رقم الفاتورة", "صافي"])
    if h is None:
        raise ValueError("ما لقيت صف العناوين (رقم الفاتورة … صافي الفاتورة).")
    hd = rows[h]
    c = {"inv_no": col_of(hd, "رقم الفاتورة"), "itype": col_of(hd, "نوع الفاتورة", "النوع"),
         "date": col_of(hd, "تاريخ"), "acct": col_of(hd, "رقم الحساب"), "cust_name": col_of(hd, "اسم الحساب", "اسم العميل"),
         "net": col_of(hd, "صافي"), "cost": col_of(hd, "التكلفة", exclude=("نسبة",))}
    body = [r for r in rows[h + 1:] if r[c["inv_no"]] not in (None, "") or (c["cust_name"] is not None and r[c["cust_name"]])]
    recs = []
    for r in body:
        g = lambda k: r[c[k]] if c[k] is not None else None  # noqa: E731
        no = g("inv_no")
        if isinstance(no, float):
            no = f"{no:.0f}"
        recs.append({"inv_no": text(no), "itype": text(g("itype")), "acct": text(g("acct")),
                     "cust_name": text(g("cust_name")), "net": to_number(g("net")) or 0.0,
                     "cost": to_number(g("cost"))})
    dates, fixed = read_dates([r[c["date"]] if c["date"] is not None else None for r in body])
    by, no_date = _by_month(recs, dates, fallback)
    return by, {"rows": len(recs), "fixed_dates": fixed, "no_date": no_date}


# ------------------------------------------------------------------ receipts
def parse_receipts(rows, fallback=None):
    """Receipt vouchers → ({month: [receipt]}, info)."""
    h = find_header(rows, ["رقم السند", "المبلغ"])
    if h is None:
        raise ValueError("ما لقيت صف العناوين (رقم السند … المبلغ).")
    hd = rows[h]
    c = {"vno": col_of(hd, "رقم السند"), "date": col_of(hd, "تاريخ السند", "تاريخ"), "vtype": col_of(hd, "نوع السند"),
         "box": col_of(hd, "الصندوق", "البنك"), "acct": col_of(hd, "رقم الحساب"), "acct_name": col_of(hd, "اسم الحساب"),
         "analytic": col_of(hd, "التحليلي"), "amount": col_of(hd, "المبلغ")}
    body = [r for r in rows[h + 1:] if to_number(r[c["amount"]])]
    recs = []
    for r in body:
        g = lambda k: r[c[k]] if c[k] is not None else None  # noqa: E731
        recs.append({"vno": text(g("vno")), "vtype": text(g("vtype")), "box": text(g("box")), "acct": text(g("acct")),
                     "acct_name": text(g("acct_name")), "analytic": text(g("analytic")),
                     "amount": to_number(g("amount")) or 0.0})
    dates, fixed = read_dates([r[c["date"]] if c["date"] is not None else None for r in body])
    by, no_date = _by_month(recs, dates, fallback)
    return by, {"rows": len(recs), "fixed_dates": fixed, "no_date": no_date}


# ------------------------------------------------------------------ rep settings and commissions
REP_COLS = {"code": ("كود", "رقم المندوب", "الرقم"), "name": ("المندوب", "الاسم"), "nationality": ("الجنسية",),
            "salary": ("الراتب",), "target": ("التارجت", "الهدف"), "other": ("تكاليف أخرى", "أخرى"),
            "active": ("يدخل التقييم", "نشط"), "note": ("ملاحظات",)}


def parse_reps(rows):
    h = find_header(rows, ["الراتب"])
    if h is None:
        raise ValueError("ما لقيت صف العناوين (كود، المندوب، الجنسية، الراتب، التارجت …).")
    hd = rows[h]
    c = {k: col_of(hd, *w) for k, w in REP_COLS.items()}
    if c["code"] is None:
        raise ValueError("ما لقيت عمود كود المندوب.")
    out = []
    for r in rows[h + 1:]:
        code = text(r[c["code"]])
        if not code or not code[0].isdigit():
            continue
        g = lambda k: r[c[k]] if c[k] is not None else None  # noqa: E731
        act = text(g("active"))
        out.append({"code": code, "name": text(g("name")), "nationality": text(g("nationality")) or "مقيم",
                    "salary": to_number(g("salary")) or 0.0, "target": to_number(g("target")) or 0.0,
                    "other": to_number(g("other")) or 0.0,
                    "active": 0 if act in ("لا", "0", "no", "No") else 1, "note": text(g("note"))})
    return out


def month_of(v):
    """A month column header → 'YYYY-MM' (2026-01, 2026/1, or a real date)."""
    if isinstance(v, (datetime.date, datetime.datetime)):
        return f"{v.year:04d}-{v.month:02d}"
    m = MONTH_RE.match(text(v))
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    return None


def parse_commissions(rows):
    """Wide sheet: rep code column, then one column per month (header 2026-01 ...) → {month: {code: amount}}."""
    for i, r in enumerate(rows[:30]):
        months = {c: month_of(v) for c, v in enumerate(r) if month_of(v)}
        if months:
            code_c = col_of(r, "كود", "رقم المندوب") if col_of(r, "كود", "رقم المندوب") is not None else 0
            out = {p: {} for p in months.values()}
            for row in rows[i + 1:]:
                code = text(row[code_c])
                if not code or not code[0].isdigit():
                    continue
                for c, p in months.items():
                    a = to_number(row[c])
                    if a:
                        out[p][code] = out[p].get(code, 0.0) + a
            return out
    raise ValueError("ما لقيت أعمدة الشهور (عناوين مثل 2026-01).")
