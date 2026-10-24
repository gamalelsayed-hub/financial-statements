"""Item data: the items list with its classification, the customer master, monthly item sales (quantities file and
sales-with-cost file) and item purchases by supplier (system PDF or Excel)."""
import datetime
import math
import re
import unicodedata
from collections import Counter, defaultdict

from . import aging as AG

UNCLASSIFIED = "غير مصنف"
LEVELS = ["grp_main", "grp_sub1", "grp_sub2", "main_item"]
LEVEL_NAMES = {"grp_main": "المجموعة الرئيسية", "grp_sub1": "المجموعة الفرعية 1", "grp_sub2": "المجموعة الفرعية 2",
               "main_item": "الصنف الرئيسي"}

ARABIC = re.compile("[؀-ۿﭐ-﷿ﹰ-﻿]")
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
CODE_RE = re.compile(r"\d{2}-\d{4,6}")


# ------------------------------------------------------------------ text helpers
def norm(s):
    s = unicodedata.normalize("NFKC", str(s or "")).strip().lower().translate(AR_DIGITS)
    s = re.sub("[إأآا]", "ا", s).replace("ة", "ه").replace("ى", "ي").replace("ـ", "")
    s = re.sub("[ً-ْ]", "", s)
    return re.sub(r"\s+", " ", s)


def text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def num(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().translate(AR_DIGITS).replace(",", "").replace(" ", "")
    if not s or s in ("-", "—"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    if s.endswith("-"):
        neg, s = True, s[:-1]
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if neg else n


def find_header(rows, *needles, limit=40):
    """Index of the first row whose cells contain every needle (normalized)."""
    for i, r in enumerate(rows[:limit]):
        cells = [norm(c) for c in r]
        if all(any(norm(n) in c for c in cells if c) for n in needles):
            return i
    return None


def col(cells, *words, exclude=()):
    for w in words:
        w = norm(w)
        for k, c in enumerate(cells):
            if c and w in c and k not in exclude:
                return k
    return None


def blank(v):
    return not text(v) or norm(v) == norm(UNCLASSIFIED)


# ------------------------------------------------------------------ customer master
MASTER_WORDS = {
    "code": ("رقم العميل", "كود العميل", "رقم"), "name": ("اسم العميل", "الاسم"),
    "ctype": ("نوع العميل", "النوع"), "rep": ("المندوب", "البائع"), "branch": ("الفرع",), "region": ("المنطقة",),
}


def guess_master(rows):
    """(first data row, {field: column})"""
    for i, r in enumerate(rows[:30]):
        cells = [norm(c) for c in r]
        found = {}
        for f, words in MASTER_WORDS.items():
            c = col(cells, *words, exclude=set(found.values()))
            if c is not None:
                found[f] = c
        if "code" in found and len(found) >= 3:
            return i + 1, found
    return 0, {}


def read_master(rows, first, mapping):
    out = {}
    for r in rows[first:]:
        rec = {f: text(r[c]) if c < len(r) else "" for f, c in mapping.items()}
        if not rec.get("code"):
            continue
        out[rec["code"]] = rec
    return list(out.values())


def customer_info(db):
    """{customer code: {name, ctype, rep, branch, region}} from the master, completed from the latest customer aging
    and the branch → region list in the settings."""
    info = {}
    periods = db.aging_periods("customers")
    for p in periods[-3:]:
        for r in db.aging("customers", p):
            if r.get("no"):
                info[text(r["no"])] = {"name": r.get("name") or "", "ctype": r.get("ctype") or "",
                                       "rep": r.get("rep") or "", "branch": r.get("branch") or "",
                                       "region": r.get("region") or ""}
    for code, m in db.customer_master().items():
        cur = info.setdefault(code, {})
        for k in ("name", "ctype", "rep", "branch", "region"):
            if m.get(k):
                cur[k] = m[k]
    regions = dict(db.branch_rows())
    for v in info.values():
        if not v.get("region") and v.get("branch"):
            v["region"] = regions.get(v["branch"], "")
    return info


# ------------------------------------------------------------------ items list and classification
def read_items_sheets(sheets):
    """sheets: [(title, rows)]. Takes the sheet titled «الأصناف» or the first one with item code + main group."""
    order = sorted(sheets, key=lambda s: norm(s[0]) != norm("الأصناف"))
    for _, rows in order:
        h = find_header(rows, "رقم الصنف", "اسم الصنف")
        if h is None:
            continue
        cells = [norm(c) for c in rows[h]]
        if col(cells, "المجموعة الرئيسية", "المجموعه الرئيسيه") is None and norm(_) != norm("الأصناف"):
            continue
        return parse_items(rows, h)
    raise ValueError("لم أجد ورقة الأصناف (رقم الصنف، اسم الصنف، المجموعة الرئيسية ...)")


def parse_items(rows, h):
    cells = [norm(c) for c in rows[h]]
    c = {"code": col(cells, "رقم الصنف"), "name": col(cells, "اسم الصنف"), "unit": col(cells, "الوحدة"),
         "grp_main": col(cells, "المجموعة الرئيسية"), "grp_sub1": col(cells, "الفرعية 1", "الفرعيه 1"),
         "grp_sub2": col(cells, "الفرعية 2", "الفرعيه 2"), "main_item": col(cells, "الصنف الرئيسي"),
         "itype": col(cells, "نوع الصنف"), "active": col(cells, "نشاط الصنف", "حالة الصنف")}
    out = {}
    for r in rows[h + 1:]:
        rec = {f: text(r[k]) if k is not None and k < len(r) else "" for f, k in c.items()}
        if not rec["code"] or not CODE_RE.search(rec["code"]) and not rec["name"]:
            continue
        for lv in LEVELS:
            if norm(rec[lv]) == norm(UNCLASSIFIED):
                rec[lv] = ""
        rec.update(guessed=0, guess_from="", guess_score=0.0)
        out[rec["code"]] = rec
    return list(out.values())


def is_classified(rec):
    return bool(rec.get("grp_main"))


STOP = {norm(w) for w in ("شد", "ح", "حبه", "حبة", "كرتون", "مقاس", "سم", "مم", "متر", "م", "كيلو", "كجم", "جرام",
                          "غرام", "لتر", "مل", "بوصه", "انش", "x", "*", "-", "/", "و", "من", "مع", "على", "في",
                          "لون", "علبه", "باله", "لفه", "طقم", "درزن")}


def tokens(name):
    s = norm(name)
    s = re.sub(r"[()\[\]{}.,:;+*/\\_\-\"'×]", " ", s)
    out = []
    for t in s.split():
        if t in STOP or any(ch.isdigit() for ch in t) or len(t) < 2:
            continue
        out.append(t)
    return out


def guess_classes(items, min_score=0.34):
    """Fill the classification of unclassified items from the most similar classified item.
    1) the name starts with a known «main item» name (longest match) → that main item's usual classification;
    2) otherwise weighted token similarity (rarer words count more, the first word counts double).
    Items with no good match stay «غير مصنف». Returns the number guessed."""
    known = [r for r in items if is_classified(r) and not r.get("guessed")]
    if not known:
        return 0
    # main item name → most common full classification
    by_main = defaultdict(Counter)
    for r in known:
        if r.get("main_item"):
            by_main[norm(r["main_item"])][tuple(r.get(lv, "") for lv in LEVELS)] += 1
    mains = sorted(by_main, key=len, reverse=True)
    df = Counter()
    toks = {}
    for r in known:
        t = tokens(r["name"])
        toks[r["code"]] = t
        df.update(set(t))
    n = len(known)
    idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
    index = defaultdict(list)
    for r in known:
        for t in set(toks[r["code"]]):
            index[t].append(r)

    def weights(t):
        w = {}
        for i, x in enumerate(t):
            w[x] = max(w.get(x, 0), idf.get(x, math.log(n + 1)) * (2.0 if i == 0 else 1.0))
        return w

    count = 0
    for r in items:
        if is_classified(r) and not r.get("guessed"):
            continue
        name = norm(r["name"])
        best = None
        for m in mains:
            if m and (name == m or name.startswith(m + " ")):
                cls = by_main[m].most_common(1)[0][0]
                best = (0.95, cls, f"الصنف الرئيسي «{cls[3]}»")
                break
        if best is None:
            t = tokens(r["name"])
            if t:
                wa = weights(t)
                cands = {c["code"]: c for x in set(t) for c in index.get(x, [])[:400]}
                for c in cands.values():
                    wb = weights(toks[c["code"]])
                    inter = sum(min(wa[k], wb[k]) for k in wa.keys() & wb.keys())
                    union = sum(max(wa.get(k, 0), wb.get(k, 0)) for k in wa.keys() | wb.keys())
                    s = inter / union if union else 0
                    if best is None or s > best[0]:
                        best = (s, tuple(c.get(lv, "") for lv in LEVELS), f"{c['code']} {c['name']}")
        if best and best[0] >= min_score:
            for lv, v in zip(LEVELS, best[1]):
                r[lv] = v
            r.update(guessed=1, guess_from=best[2], guess_score=round(best[0], 2))
            count += 1
        else:
            for lv in LEVELS:
                r[lv] = ""
            r.update(guessed=0, guess_from="", guess_score=0.0)
    return count


def item_class(items, code, name=""):
    """Classification tuple (main, sub1, sub2, main item), «غير مصنف» where missing."""
    r = items.get(code)
    if not r or not is_classified(r):
        return (UNCLASSIFIED,) * 4
    return tuple(r.get(lv) or UNCLASSIFIED for lv in LEVELS)


# ------------------------------------------------------------------ item sales
def sales_format(rows):
    """'qty' (sales / returns / net with quantities), 'cost' (net with cost and margin) or None."""
    if find_header(rows, "رقم العميل", "رقم الصنف") is not None:
        return "qty"
    if find_header(rows, "رقم الصنف", "التكلفة") is not None:
        return "cost"
    return None


def parse_sales_qty(rows):
    """Item sales by customer: customer, currency, item, unit, then sales / returns / net groups of
    (quantity, free quantity, amount) and optionally the net amount in local currency."""
    h = find_header(rows, "رقم العميل", "رقم الصنف")
    cells = [norm(c) for c in rows[h]]
    above = [norm(c) for c in rows[h - 1]] if h > 0 else [""] * len(cells)
    # spread the group titles (merged cells) over their columns
    group, groups = "", []
    for c in above:
        if c:
            group = c
        groups.append(group)
    c_cust = col(cells, "رقم العميل")
    c_item = col(cells, "رقم الصنف")
    c_iname = col(cells, "اسم الصنف")
    c_unit = col(cells, "الوحدة")
    c_cname = col(cells, "اسم العميل")
    if c_cname is None and c_cust is not None and c_cust + 1 < len(cells) and c_cust + 1 not in (c_item, c_iname):
        c_cname = c_cust + 1
    c_local = col(cells, "بالمحلي", "المحلي")

    def block(word):
        ks = [k for k, g in enumerate(groups) if word in g]
        qty = next((k for k in ks if "كميه" in cells[k] and "مجان" not in cells[k]), None)
        free = next((k for k in ks if "مجان" in cells[k]), None)
        amt = next((k for k in ks if "مبلغ" in cells[k] and k != c_local), None)
        return qty, free, amt

    s_q, s_f, s_a = block(norm("المبيعات"))
    r_q, r_f, r_a = block(norm("مردود"))
    n_q, n_f, n_a = block(norm("صافي"))
    if s_a is None:      # no group titles: take the amount columns in order
        amts = [k for k, c in enumerate(cells) if "مبلغ" in c and k != c_local]
        qtys = [k for k, c in enumerate(cells) if "كميه" in c and "مجان" not in c]
        frees = [k for k, c in enumerate(cells) if "مجان" in c]
        pad = lambda lst: (lst + [None, None, None])[:3]  # noqa: E731
        s_a, r_a, n_a = pad(amts)
        s_q, r_q, n_q = pad(qtys)
        s_f, r_f, n_f = pad(frees)

    def v(r, k):
        return (num(r[k]) or 0.0) if k is not None and k < len(r) else 0.0

    out = []
    for r in rows[h + 1:]:
        cust, item = text(r[c_cust]), text(r[c_item])
        if not cust or not item or not re.search(r"\d", cust):
            continue
        sales, ret = v(r, s_a), v(r, r_a)
        net = v(r, c_local) if c_local is not None else (v(r, n_a) if n_a is not None else sales - ret)
        out.append({
            "cust_code": cust, "cust_name": text(r[c_cname]) if c_cname is not None else "",
            "item_code": item, "item_name": text(r[c_iname]) if c_iname is not None else "",
            "unit": text(r[c_unit]) if c_unit is not None else "",
            "qty": v(r, s_q), "free_qty": v(r, n_f) if n_f is not None else v(r, s_f), "sales": sales, "ret_qty": v(r, r_q),
            "returns": ret, "net_qty": v(r, n_q) if n_q is not None else v(r, s_q) - v(r, r_q), "net": net,
        })
    return out


def parse_sales_cost(rows):
    """Item sales by customer with cost: item code / name, net, cost, margin, «code-name» of the customer.
    The net amount sometimes sits in the column before its title, so the numeric column is taken."""
    h = find_header(rows, "رقم الصنف", "التكلفة")
    cells = [norm(c) for c in rows[h]]
    data = rows[h + 1:]
    c_item, c_iname = col(cells, "رقم الصنف"), col(cells, "اسم الصنف")
    c_cost = col(cells, "التكلفه")
    c_cust = col(cells, "العميل")
    c_ccode = col(cells, "رقم العميل")

    def numeric(k):
        return sum(1 for r in data[:200] if k is not None and k < len(r) and isinstance(num(r[k]), float))

    c_net = col(cells, "صافي")
    cands = [k for k in (c_net, (c_net - 1) if c_net else None, (c_net + 1) if c_net is not None else None)
             if k is not None and 0 <= k < len(cells) and k not in (c_item, c_iname, c_cost, c_cust) and
             (not cells[k] or "صافي" in cells[k])]
    if not cands:
        cands = [k for k, c in enumerate(cells) if not c and k not in (c_item, c_iname)]
    c_net = max(cands, key=numeric) if cands else None
    out = []
    for r in data:
        item = text(r[c_item]) if c_item is not None else ""
        if not item or not CODE_RE.search(item) and not re.search(r"\d", item):
            continue
        cust_raw = text(r[c_cust]) if c_cust is not None else ""
        code, name = "", cust_raw
        m = re.match(r"\s*(\d+)\s*[-–—:]\s*(.*)", cust_raw)
        if m:
            code, name = m.group(1), m.group(2).strip()
        if c_ccode is not None and c_ccode != c_cust:
            code = text(r[c_ccode]) or code
        out.append({"cust_code": code or name, "cust_name": name, "item_code": item,
                    "item_name": text(r[c_iname]) if c_iname is not None else "",
                    "cnet": num(r[c_net]) or 0.0 if c_net is not None else 0.0,
                    "cost": num(r[c_cost]) or 0.0 if c_cost is not None else 0.0})
    return out


QTY_KEYS = ("qty", "free_qty", "sales", "ret_qty", "returns", "net_qty", "net")
COST_KEYS = ("cnet", "cost")


def merge_sales(existing, new, fmt):
    """Combine a month's saved rows with a newly read file of format fmt (the file replaces its own fields;
    the other format's fields are kept). Rows are summed by (customer, item)."""
    keys = QTY_KEYS if fmt == "qty" else COST_KEYS
    other = COST_KEYS if fmt == "qty" else QTY_KEYS
    out = {}
    for r in existing:
        k = (r["cust_code"], r["item_code"])
        rec = dict(r)
        for f in keys:
            rec[f] = None
        if any(rec.get(f) for f in other):
            out[k] = rec
    for r in new:
        k = (r["cust_code"], r["item_code"])
        rec = out.get(k)
        if rec is None:
            rec = {"cust_code": r["cust_code"], "cust_name": r.get("cust_name", ""), "item_code": r["item_code"],
                   "item_name": r.get("item_name", ""), "unit": r.get("unit", "")}
            for f in QTY_KEYS + COST_KEYS:
                rec[f] = None
            out[k] = rec
        for f in ("cust_name", "item_name", "unit"):
            if r.get(f) and not rec.get(f):
                rec[f] = r[f]
        for f in keys:
            if f in r:
                rec[f] = (rec.get(f) or 0.0) + (r[f] or 0.0)
    return list(out.values())


# ------------------------------------------------------------------ item purchases (system PDF)
def fix_word(token):
    """The system's PDFs store Arabic in visual order with presentation forms: reverse the Arabic runs (and their
    order inside a mixed token), keep numbers and Latin text as they are."""
    token = token.translate(AR_DIGITS)
    if not ARABIC.search(token):
        return token
    runs = re.findall(f"{ARABIC.pattern}+|[^؀-ۿﭐ-﷿ﹰ-﻿]+", token)
    runs = [unicodedata.normalize("NFKC", r[::-1]) if ARABIC.search(r) else r for r in runs]
    return "".join(reversed(runs))


def _line_text(words):
    """Words of one line → logical text (Arabic lines run right to left; pure Latin lines left to right)."""
    if all(not ARABIC.search(w["text"]) for w in words) and any(re.search("[A-Za-z]", w["text"]) for w in words):
        return " ".join(w["text"] for w in sorted(words, key=lambda w: w["x0"]))
    s = " ".join(fix_word(w["text"]) for w in sorted(words, key=lambda w: -w["x0"]))
    return re.sub(r"\)\s*([^()]*?)\s*\(", r"(\1)", s)     # brackets come mirrored in visual order


def parse_purchases_pdf(path):
    """Purchases by supplier and item (system report). Returns (last date in the report or None, rows)."""
    import pdfplumber
    rows, last_date = [], None
    supp = {"supp_no": "", "supp_name": "", "currency": ""}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue
            lines = defaultdict(list)
            for w in words:
                lines[round(w["top"] / 4)].append(w)
            keys = sorted(lines)
            # column positions from the header line (item no / item name / unit / quantity / net amount)
            cols = None
            for k in keys:
                fixed = {fix_word(w["text"]): w for w in lines[k]}
                if "الكمية" in fixed and "الوحدة" in fixed:
                    cols = {"unit": fixed["الوحدة"]["x0"], "qty": fixed["الكمية"]["x0"]}
                    break
            qty_words = []
            items = []
            for k in keys:
                ws = sorted(lines[k], key=lambda w: -w["x0"])
                fixed = [fix_word(w["text"]) for w in ws]
                joined = " ".join(fixed)
                for d in re.findall(r"\d{1,2}/\d{1,2}/\d{4}", joined):
                    try:
                        dt = datetime.datetime.strptime(d, "%d/%m/%Y").date()
                        if "تاريخ التقرير" not in joined and (last_date is None or dt > last_date):
                            last_date = dt
                    except ValueError:
                        pass
                if "المورد" in joined and "رقم" in joined:
                    supp = _supplier_line(ws)
                    continue
                code_w = next((w for w in ws if CODE_RE.search(w["text"].translate(AR_DIGITS))), None)
                if code_w is not None:
                    items.append((k, ws, code_w))
                    continue
                if len(ws) == 1 and re.fullmatch(r"[\d,.]+", ws[0]["text"].translate(AR_DIGITS)):
                    qty_words.append(ws[0])
            for k, ws, code_w in items:
                raw = code_w["text"].translate(AR_DIGITS)
                code = CODE_RE.search(raw).group(0)
                amounts = [w for w in ws if w["x0"] < (cols["qty"] - 20 if cols else 130)
                           and re.fullmatch(r"-?[\d,]+\.\d+|-?[\d,]+", w["text"].translate(AR_DIGITS))]
                qtys = [w for w in ws if cols and cols["qty"] - 20 <= w["x0"] < cols["unit"] - 15
                        and num(w["text"]) is not None]
                if not qtys:   # the quantity is printed a little above or below its line
                    top = code_w["top"]
                    near = [w for w in qty_words if abs(w["top"] - top) < 9]
                    qtys = sorted(near, key=lambda w: abs(w["top"] - top))[:1]
                    for w in qtys:
                        qty_words.remove(w)
                unit_w = [w for w in ws if cols and cols["unit"] - 25 <= w["x0"] < cols["unit"] + 40
                          and w not in qtys and w not in amounts]
                name_ws = [w for w in ws if w is not code_w and w not in amounts and w not in qtys and w not in unit_w]
                rest = raw.replace(code, "").strip()
                name = _line_text(name_ws)
                if rest:
                    name = (fix_word(rest) + " " + name).strip()
                rows.append({**supp, "item_code": code, "item_name": name,
                             "unit": " ".join(fix_word(w["text"]) for w in unit_w),
                             "qty": sum(num(w["text"]) or 0 for w in qtys),
                             "net": sum(num(w["text"]) or 0 for w in amounts)})
    return last_date, rows


def _supplier_line(ws):
    """«رقم المورد : 10065   اسم المورد : ...   العملة : SAR» (words right to left)."""
    fixed = [fix_word(w["text"]) for w in ws]
    no = next((t for t in fixed if re.fullmatch(r"\d{3,}", t)), "")
    cur = next((t for t in reversed(fixed) if re.fullmatch(r"[A-Z]{3}", t)), "")   # leftmost: after «العملة :»
    start = next((i + 1 for i in range(1, len(fixed)) if fixed[i] == "المورد" and fixed[i - 1] == "اسم"), None)
    name_ws = []
    if start is not None:
        if start < len(fixed) and fixed[start] == ":":
            start += 1
        for t, w in zip(fixed[start:], ws[start:]):
            if "العملة" in t:
                rest = w["text"].translate(AR_DIGITS)
                rest = re.sub(f"{ARABIC.pattern}+", "", rest).strip()
                if rest:
                    name_ws.append({"text": rest, "x0": w["x0"]})
                break
            name_ws.append(w)
    return {"supp_no": no, "supp_name": _line_text(name_ws) if name_ws else "", "currency": cur}


PURCHASE_WORDS = {
    "supp_no": ("رقم المورد", "كود المورد"), "supp_name": ("اسم المورد", "المورد"), "currency": ("العملة",),
    "item_code": ("رقم الصنف", "كود الصنف"), "item_name": ("اسم الصنف",), "unit": ("الوحدة",),
    "qty": ("الكمية",), "net": ("صافي المبلغ", "الصافي", "المبلغ", "القيمة"),
}


def guess_purchase_cols(rows):
    h = find_header(rows, "الصنف", "المورد")
    if h is None:
        return 0, {}
    cells = [norm(c) for c in rows[h]]
    found = {}
    for f, words in PURCHASE_WORDS.items():
        c = col(cells, *words, exclude=set(found.values()))
        if c is not None:
            found[f] = c
    return h + 1, found


def read_purchases(rows, first, mapping):
    out = []
    for r in rows[first:]:
        rec = {f: (num(r[c]) or 0.0) if f in ("qty", "net") else text(r[c]) for f, c in mapping.items()}
        if not rec.get("item_code"):
            continue
        for f in ("supp_no", "supp_name", "currency", "item_name", "unit"):
            rec.setdefault(f, "")
        rec.setdefault("qty", 0.0)
        rec.setdefault("net", 0.0)
        out.append(rec)
    return out


def purchase_base(row, rates, base):
    """Net purchase in the base currency (foreign suppliers are in their currency, e.g. USD)."""
    cur = (row.get("currency") or base).upper()
    if cur == base:
        return row.get("net") or 0.0
    rate = rates.get(cur)
    return (row.get("net") or 0.0) * rate if rate else (row.get("net") or 0.0)


def supplier_type(no):
    return AG.supplier_type(no)
