"""Customer and supplier aging: overdue rules and summaries (same rules as the Excel model).

Customers: overdue = over 30 days for custody ("عهدة") customers, over 60 days for any other type.
Suppliers: overdue = the buckets beyond the supplier's credit period, converted with the currency rate.
"""

BUCKETS = ["b0", "b1", "b2", "b3", "b4"]
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
