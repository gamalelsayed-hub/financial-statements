"""Reading a trial balance from Excel / CSV and turning it into accounts."""
import csv
import re
from dataclasses import dataclass, field

ROLES = ["code", "name", "od", "oc", "md", "mc", "cd", "cc"]
AMOUNT_ROLES = ["od", "oc", "md", "mc", "cd", "cc"]

TOTAL_WORDS = ("الاجمالي", "الإجمالي", "اجمالي", "إجمالي", "المجموع", "مجموع", "total", "grand total")


@dataclass
class Account:
    code: str
    name: str
    od: float = 0.0
    oc: float = 0.0
    md: float = 0.0
    mc: float = 0.0
    cd: float = 0.0
    cc: float = 0.0
    category: str | None = None
    warnings: list = field(default_factory=list)

    @property
    def open_net(self):
        return self.od - self.oc

    @property
    def mov_net(self):
        return self.md - self.mc

    @property
    def close_net(self):
        return self.cd - self.cc


def read_table(path):
    """Return the sheet as a list of rows (lists of raw cell values)."""
    p = path.lower()
    if p.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        ws = wb.worksheets[0]
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    elif p.endswith((".csv", ".txt")):
        rows = None
        for enc in ("utf-8-sig", "cp1256", "latin-1"):
            try:
                with open(path, newline="", encoding=enc) as f:
                    sample = f.read(4096)
                    f.seek(0)
                    try:
                        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
                    except csv.Error:
                        dialect = csv.excel
                    rows = [list(r) for r in csv.reader(f, dialect)]
                break
            except UnicodeDecodeError:
                continue
    else:
        raise ValueError("unsupported")
    width = max((len(r) for r in rows), default=0)
    return [r + [None] * (width - len(r)) for r in rows]


def to_number(v):
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s or s in ("-", "—"):
        return None
    # Arabic-Indic digits and separators
    s = s.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,"))
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace(" ", "")
    if s.endswith("-"):
        neg, s = True, s[:-1]
    try:
        n = float(s)
    except ValueError:
        return None
    return -n if neg else n


def is_text(v):
    return v is not None and str(v).strip() != "" and to_number(v) is None


def guess_mapping(rows):
    """Guess the first data row and the column of each role.

    The usual layout is: code, name, then six amount columns
    (opening Dr/Cr, movement Dr/Cr, closing Dr/Cr).
    """
    first = None
    for i, r in enumerate(rows[:60]):
        nums = sum(1 for v in r if to_number(v) is not None)
        texts = sum(1 for v in r if is_text(v))
        if nums >= 4 and texts >= 1:
            first = i
            break
    if first is None:
        return 0, {}
    sample = rows[first:first + 40]
    width = len(rows[0]) if rows else 0
    num_cols, text_cols = [], []
    for c in range(width):
        vals = [r[c] for r in sample if r[c] is not None and str(r[c]).strip() != ""]
        if not vals:
            continue
        n = sum(1 for v in vals if to_number(v) is not None)
        if n >= len(vals) * 0.6:
            num_cols.append(c)
        else:
            text_cols.append(c)
    mapping = {}
    # The account code is usually a numeric-looking column that comes before the name.
    if text_cols:
        name_col = max(text_cols, key=lambda c: sum(len(str(r[c] or "")) for r in sample))
        mapping["name"] = name_col
        before = [c for c in num_cols if c < name_col] + [c for c in text_cols if c < name_col]
        if before:
            mapping["code"] = max(before)
    amount_cols = [c for c in num_cols if c != mapping.get("code")]
    if "name" in mapping:
        amount_cols = [c for c in amount_cols if c > mapping["name"]] or amount_cols
    if len(amount_cols) >= 6:
        for role, c in zip(AMOUNT_ROLES, amount_cols[:6]):
            mapping[role] = c
    elif len(amount_cols) >= 4:
        for role, c in zip(["od", "oc", "cd", "cc"], amount_cols[:4]):
            mapping[role] = c
    elif len(amount_cols) >= 2:
        mapping["cd"], mapping["cc"] = amount_cols[0], amount_cols[1]
    return first, mapping


def build_accounts(rows, first_row, mapping):
    """Create accounts from the mapped columns. Missing amount pairs are derived
    (movement = closing - opening, closing = opening + movement)."""
    accounts = []
    have = {r: r in mapping and mapping[r] is not None for r in ROLES}
    for idx, r in enumerate(rows[first_row:], start=first_row + 1):
        name = str(r[mapping["name"]]).strip() if have["name"] and r[mapping["name"]] is not None else ""
        code_raw = r[mapping["code"]] if have["code"] else None
        if isinstance(code_raw, float) and code_raw.is_integer():
            code_raw = int(code_raw)
        code = str(code_raw).strip() if code_raw is not None else ""
        vals = {}
        for role in AMOUNT_ROLES:
            vals[role] = (to_number(r[mapping[role]]) or 0.0) if have[role] else 0.0
        if not name and not code:
            continue
        low = name.lower().replace("أ", "ا").replace("إ", "ا")
        if not code and any(w.replace("أ", "ا").replace("إ", "ا") in low for w in TOTAL_WORDS):
            continue
        if all(abs(v) < 1e-9 for v in vals.values()):
            continue
        a = Account(code=code or f"#{idx}", name=name, **vals)
        # Negative numbers in a debit column mean credit (and vice versa).
        for d, c in (("od", "oc"), ("md", "mc"), ("cd", "cc")):
            dv, cv = getattr(a, d), getattr(a, c)
            if dv < 0:
                cv, dv = cv - dv, 0.0
            if cv < 0:
                dv, cv = dv - cv, 0.0
            setattr(a, d, dv)
            setattr(a, c, cv)
        if not have["md"] and not have["mc"]:
            net = a.close_net - a.open_net
            a.md, a.mc = (net, 0.0) if net >= 0 else (0.0, -net)
        if not have["cd"] and not have["cc"]:
            net = a.open_net + a.mov_net
            a.cd, a.cc = (net, 0.0) if net >= 0 else (0.0, -net)
        accounts.append(a)
    return accounts


def mark_parent_accounts(accounts):
    """In hierarchical charts (1, 11, 1101 ...) parent rows repeat their children's
    totals. Return codes of accounts that are a prefix of another account code."""
    codes = [a.code for a in accounts if not a.code.startswith("#")]
    parents = set()
    srt = sorted(codes)
    for i, c in enumerate(srt):
        if i + 1 < len(srt) and srt[i + 1].startswith(c) and srt[i + 1] != c:
            parents.add(c)
    return parents


def validate(accounts, tol=0.5):
    """Return a dict of totals and a list of problems found in the trial balance."""
    t = {k: sum(getattr(a, k) for a in accounts) for k in AMOUNT_ROLES}
    problems = []
    for d, c, label in (("od", "oc", "opening"), ("md", "mc", "movement"), ("cd", "cc", "closing")):
        if abs(t[d] - t[c]) > tol:
            problems.append(("unbalanced", label, t[d] - t[c]))
    bad = [a for a in accounts if abs(a.open_net + a.mov_net - a.close_net) > tol]
    for a in bad:
        problems.append(("row", a.code, a.name, a.open_net + a.mov_net - a.close_net))
    return t, problems


def natural_key(code):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", code)]
