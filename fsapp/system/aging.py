"""Customer and supplier aging: overdue rules and summaries (same rules as the Excel model).

Customers: overdue = over 30 days for custody ("عهدة") customers, over 60 days for any other type.
Suppliers: overdue = the buckets beyond the supplier's credit period, converted with the currency rate.
"""

import datetime
import re

BUCKETS = ["b0", "b1", "b2", "b3", "b4"]
MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر",
             "ديسمبر"]
BUCKET_NAMES = ["0 - 30", "31 - 60", "61 - 90", "91 - 120", "أكثر من 120"]


def n(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def is_custody(ctype):
    return "عهد" in (ctype or "")


def is_credit(ctype):
    t = (ctype or "").replace("آ", "ا")
    return "اجل" in t


def customer_total(r):
    return sum(n(r[b]) for b in BUCKETS)


def customer_overdue(r):
    first = 1 if is_custody(r.get("ctype")) else 2
    return sum(n(r[b]) for b in BUCKETS[first:])


def supplier_total(r):
    return sum(n(r[b]) for b in BUCKETS)


def supplier_overdue(r):
    credit = n(r.get("credit"))
    if credit <= 30:
        first = 1
    elif credit <= 60:
        first = 2
    elif credit <= 90:
        first = 3
    elif credit <= 120:
        first = 4
    else:
        return 0.0
    return sum(n(r[b]) for b in BUCKETS[first:])


def rates(db):
    out = {}
    for code, rate in db.currencies():
        if rate not in (None, ""):
            out[code.upper()] = float(rate)
    return out


SUPPLIER_TYPES = ["محلي", "خارجي", "خدمات وأخرى"]
TYPE_TITLES = {"محلي": "الموردون المحليون", "خارجي": "الموردون الخارجيون", "خدمات وأخرى": "موردو الخدمات وأخرى"}


def supplier_type(no):
    """By the first digit of the supplier number: 1 local, 2 foreign, anything else services and other."""
    s = str(no or "").strip()
    return "محلي" if s.startswith("1") else "خارجي" if s.startswith("2") else "خدمات وأخرى"


def suppliers_by_type(rows, rate_map, base):
    """[(type, summary)] for the three supplier types (empty types included)."""
    return [(t, suppliers_summary([r for r in rows if supplier_type(r.get("no")) == t], rate_map, base))
            for t in SUPPLIER_TYPES]


def supplier_rate(r, rate_map, base):
    cur = (r.get("currency") or "").strip().upper() or base
    return rate_map.get(cur)


def customers_summary(rows):
    tot = sum(customer_total(r) for r in rows)
    od = sum(customer_overdue(r) for r in rows)
    need = [r for r in rows if customer_overdue(r) > 0.005]
    return {"count": len(rows), "total": tot, "overdue": od, "need_count": len(need),
            "need_amount": sum(customer_overdue(r) for r in need)}


def suppliers_summary(rows, rate_map, base):
    tot = od = 0.0
    no_rate = []
    over = []
    for r in rows:
        rate = supplier_rate(r, rate_map, base)
        if rate is None:
            no_rate.append(r)
            continue
        tot += supplier_total(r) * rate
        o = supplier_overdue(r) * rate
        od += o
        if o > 0.005:
            over.append(r)
    return {"count": len(rows), "total": tot, "overdue": od, "no_rate": len(no_rate), "over_count": len(over)}


# ---------------------------------------------------------------- one file for several months / several types
def parse_month(v):
    """A month cell → 'YYYY-MM': 2026-03, 2026/3, 03/2026, a real date, or «مارس 2026». None if not a month."""
    if isinstance(v, (datetime.date, datetime.datetime)):
        return f"{v.year:04d}-{v.month:02d}"
    t = str(v or "").strip().replace("إ", "ا").replace("أ", "ا")
    m = re.match(r"^(\d{4})\s*[-/.]\s*(\d{1,2})(?:\s*[-/.]\s*\d{1,2})?$", t)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.match(r"^(?:\d{1,2}\s*[-/.]\s*)?(\d{1,2})\s*[-/.]\s*(\d{4})$", t)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}"
    y = re.search(r"(\d{4})", t)
    if y:
        for i, name in enumerate(MONTHS_AR, 1):
            if name.replace("أ", "ا") in t:
                return f"{int(y.group(1)):04d}-{i:02d}"
    return None


def split_by_month(rows):
    """Rows that carry a «month» field → ({month: rows}, rows whose month could not be read)."""
    out, bad = {}, 0
    for r in rows:
        p = parse_month(r.get("month"))
        if p:
            out.setdefault(p, []).append(r)
        else:
            bad += 1
    return out, bad


def merge_aging(existing, new):
    """Add a file of one type (e.g. «عهدة») to a month that already has another (e.g. «آجل»): a customer of the
    same number and type is replaced by the new row, everything else is kept."""
    key = lambda r: (str(r.get("no") or r.get("name") or "").strip(), (r.get("ctype") or "").strip())  # noqa: E731
    new_keys = {key(r) for r in new}
    return [r for r in existing if key(r) not in new_keys] + list(new)
