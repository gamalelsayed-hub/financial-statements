"""Import a company from the Excel model (sheets: الإعدادات، البنود، الربط، المدخلات).

Values are read from the cached results of the workbook formulas, so the workbook should have been
saved by Excel after its last recalculation.
"""
import datetime

from . import defaults
from .calc import month_add
from .db import Account

INPUT_TABLES = {
    "tb": "1) ميزان مراجعة الشركة",
    "comp": "2) ميزان مراجعة الشركة",
    "monthly": "3) حركة الحسابات الشهرية",
    "branches": "4) حركة الفروع الشهرية",
}


def _num(v):
    if v is None or v == "":
        return 0.0
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return 0.0


def _code(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _split(net):
    return (net, 0.0) if net >= 0 else (0.0, -net)


def _find_table(ws, title_prefix):
    """Row of the header line of an input table (the row after its title and description)."""
    for r in range(1, ws.max_row + 1):
        v = ws.cell(r, 1).value
        if isinstance(v, str) and v.strip().startswith(title_prefix):
            for rr in range(r + 1, r + 5):
                h = ws.cell(rr, 1).value
                if isinstance(h, str) and ("رقم" in h or "الفرع" in h):
                    return rr
    return None


def _rows_until_blank(ws, start, key_col, max_blank=30):
    r, blanks = start, 0
    while blanks < max_blank and r <= ws.max_row:
        if ws.cell(r, key_col).value in (None, ""):
            blanks += 1
        else:
            blanks = 0
            yield r
        r += 1


class _Cell:
    __slots__ = ("value",)

    def __init__(self, value):
        self.value = value


class _Sheet:
    """Rows of a sheet held in memory, with the small part of the openpyxl API used here."""

    def __init__(self, ws):
        self.rows = [list(r) for r in ws.iter_rows(values_only=True)]
        self.max_row = len(self.rows)

    def cell(self, r, c):
        row = self.rows[r - 1] if 0 < r <= self.max_row else ()
        return _Cell(row[c - 1] if c - 1 < len(row) else None)

    def __getitem__(self, ref):
        col = ord(ref[0]) - 64
        return self.cell(int(ref[1:]), col)


class _Book:
    def __init__(self, path):
        import openpyxl
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
        self.sheetnames = wb.sheetnames
        self._wb = wb
        self._cache = {}

    def __getitem__(self, name):
        if name not in self._cache:
            self._cache[name] = _Sheet(self._wb[name])
        return self._cache[name]

    def close(self):
        self._wb.close()


def read_workbook(path):
    return _Book(path)


def inspect(path):
    """Quick look used by the import dialog: company name, year, months found, TB periods guess."""
    wb = read_workbook(path)
    info = {"company": "", "year": None}
    if "الإعدادات" in wb.sheetnames:
        s = wb["الإعدادات"]
        info["company"] = s["C4"].value or ""
        d = s["C5"].value
        if isinstance(d, (datetime.date, datetime.datetime)):
            info["year"] = d.year
    wb.close()
    return info


def migrate(path, db, year=None, comp_period=None, log=print):
    wb = read_workbook(path)
    missing = [s for s in ("الربط", "البنود", "المدخلات") if s not in wb.sheetnames]
    if missing:
        raise ValueError("الملف لا يحتوي على الأوراق: " + "، ".join(missing))

    # ---------------- settings
    if "الإعدادات" in wb.sheetnames:
        s = wb["الإعدادات"]
        if s["C4"].value:
            db.set_setting("company", s["C4"].value)
        for key, cell in (("alert_pct", "C10"), ("alert_amount", "C11"), ("credit_ratio", "C13")):
            if isinstance(s[cell].value, (int, float)):
                db.set_setting(key, s[cell].value)
        d = s["C5"].value
        if year is None and isinstance(d, (datetime.date, datetime.datetime)):
            year = d.year
        branches, currencies = [], []
        for r in range(15, 40):
            name = s.cell(r, 2).value
            if isinstance(s.cell(r, 1).value, (int, float)) and isinstance(name, str) and name.strip():
                branches.append((name.strip(), str(s.cell(r, 3).value or "").strip()))
            cur, rate = s.cell(r, 5).value, s.cell(r, 6).value
            if isinstance(cur, str) and 2 <= len(cur.strip()) <= 4 and cur.strip().isalpha():
                currencies.append((cur.strip(), _num(rate) if rate not in (None, "") else None))
        if branches:
            db.save_branches(branches)
        if currencies:
            db.save_currencies(currencies)
        log(f"الإعدادات: {len(branches)} فرع، {len(currencies)} عملة")
    year = year or datetime.date.today().year

    # ---------------- lists
    s = wb["البنود"]

    def col_values(col):
        out = []
        for r in range(5, s.max_row + 1):
            v = s.cell(r, col).value
            if isinstance(v, str) and v.strip():
                out.append(v.strip())
        return out

    known_fs = {n: (sec, role) for n, sec, role in defaults.FS_ITEMS}
    fs_rows, last_sec = [], "CA"
    for n in col_values(1):
        sec, role = known_fs.get(n, (last_sec, ""))
        fs_rows.append((n, sec, role))
        last_sec = sec
    known_cf = {n: (a, b) for n, a, b in defaults.CF_ITEMS}
    cf_rows, last_act = [], "OP"
    for n in col_values(3):
        act, bucket = known_cf.get(n, (last_act, ""))
        cf_rows.append((n, act, bucket))
        last_act = act
    known_cat = dict(defaults.BRANCH_CATS)
    cat_rows = [(n, known_cat.get(n, "below")) for n in col_values(5)]
    grp_rows = [(n,) for n in col_values(7)]
    if fs_rows:
        db.save_list("fs_items", fs_rows)
    if cf_rows:
        db.save_list("cf_items", cf_rows)
    if cat_rows:
        db.save_list("branch_cats", cat_rows)
    if grp_rows:
        db.save_list("exp_groups", grp_rows)
    log(f"البنود: {len(fs_rows)} بند قوائم، {len(cf_rows)} بند تدفق، {len(cat_rows)} فئة فروع، {len(grp_rows)} مجموعة مصروف")

    # ---------------- account mapping
    s = wb["الربط"]
    accounts = []
    for r in _rows_until_blank(s, 5, 1):
        code = _code(s.cell(r, 1).value)
        if not code:
            continue
        accounts.append(Account(
            code=code, name=str(s.cell(r, 2).value or "").strip(), grp=str(s.cell(r, 3).value or "").strip(),
            fs_item=str(s.cell(r, 5).value or "").strip(), cf_item=str(s.cell(r, 6).value or "").strip(),
            branch_cat=str(s.cell(r, 7).value or "").strip(), exp_group=str(s.cell(r, 8).value or "").strip(),
            behavior=str(s.cell(r, 15).value or "").strip()))
    db.save_accounts(accounts)
    log(f"الربط: {len(accounts)} حساب")

    ws = wb["المدخلات"]

    # ---------------- monthly company movements -> one trial balance per month
    h = _find_table(ws, INPUT_TABLES["monthly"])
    monthly = {}
    names = {}
    if h:
        for r in _rows_until_blank(ws, h + 1, 1):
            code = _code(ws.cell(r, 1).value)
            names[code] = str(ws.cell(r, 2).value or "").strip()
            monthly[code] = (_num(ws.cell(r, 3).value), [_num(ws.cell(r, 4 + i).value) for i in range(12)])
    entered = [i for i in range(12) if any(abs(v[1][i]) > 0.004 for v in monthly.values())]
    if entered:
        last = max(entered)
        for i in range(last + 1):
            period = f"{year:04d}-{i + 1:02d}"
            rows = []
            for code, (year_open, movs) in monthly.items():
                op = year_open + sum(movs[:i])
                mv = movs[i]
                cl = op + mv
                if abs(op) < 0.004 and abs(mv) < 0.004 and abs(cl) < 0.004:
                    continue
                rows.append((code, names[code]) + _split(op) + _split(mv) + _split(cl))
            db.save_tb(period, rows)
        log(f"الحركة الشهرية: {last + 1} شهر ({len(monthly)} حساب)")

    # ---------------- current trial balance (detailed debit/credit) replaces its month
    def read_tb(title):
        hh = _find_table(ws, title)
        if not hh:
            return []
        out = []
        for r in _rows_until_blank(ws, hh + 1, 1, max_blank=5):
            code = _code(ws.cell(r, 1).value)
            vals = [_num(ws.cell(r, c).value) for c in range(3, 9)]
            if code and any(abs(v) > 0.004 for v in vals):
                out.append((code, str(ws.cell(r, 2).value or "").strip(), *vals))
        return out

    def match_month(rows):
        if not rows or not entered:
            return None, None
        best, best_err = None, None
        mov = {r[0]: r[4] - r[5] for r in rows}
        for i in entered:
            err = sum(abs(mov.get(c, 0.0) - monthly.get(c, (0, [0] * 12))[1][i]) for c in set(mov) | set(monthly))
            if best_err is None or err < best_err:
                best, best_err = i, err
        return best, best_err

    tb_rows = read_tb(INPUT_TABLES["tb"])
    i, err = match_month(tb_rows)
    current_period = None
    if i is not None and err < 1.0:
        current_period = f"{year:04d}-{i + 1:02d}"
        db.save_tb(current_period, tb_rows)
        log(f"ميزان الفترة الحالية ({len(tb_rows)} حساب) = شهر {current_period}")
    elif tb_rows:
        log(f"تنبيه: ميزان الفترة الحالية لا يطابق أي شهر في الحركة الشهرية (فرق {err:,.0f}) — لم يُستورد.")

    comp_rows = read_tb(INPUT_TABLES["comp"])
    if comp_rows:
        i, err = match_month(comp_rows)
        if i is not None and err < 1.0:
            log(f"ميزان المقارنة يطابق شهر {year:04d}-{i + 1:02d} الموجود بالفعل.")
        else:
            period = comp_period or (month_add(current_period, -12) if current_period else None)
            if period:
                db.save_tb(period, comp_rows)
                log(f"ميزان المقارنة ({len(comp_rows)} حساب) حُفظ كشهر {period}")

    # ---------------- branch monthly movements
    h = _find_table(ws, INPUT_TABLES["branches"])
    n = 0
    if h:
        data = {}
        for r in _rows_until_blank(ws, h + 1, 2):
            branch = str(ws.cell(r, 1).value or "").strip()
            code = _code(ws.cell(r, 2).value)
            if not branch or not code:
                continue
            name = str(ws.cell(r, 3).value or "").strip()
            for m in range(12):
                v = _num(ws.cell(r, 4 + m).value)
                if abs(v) > 0.004:
                    data.setdefault((m, branch), []).append((code, name, v))
        for (m, branch), rows in data.items():
            db.save_branch_mov(f"{year:04d}-{m + 1:02d}", branch, rows)
            n += 1
        log(f"حركة الفروع: {n} (فرع × شهر)")
    wb.close()
    return current_period
