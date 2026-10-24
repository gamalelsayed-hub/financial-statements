"""One SQLite file per company: settings, lists, account mapping, monthly trial balances, branch movements."""
import sqlite3
from dataclasses import dataclass

from . import defaults

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS branches(name TEXT PRIMARY KEY, region TEXT DEFAULT '', sort INTEGER);
CREATE TABLE IF NOT EXISTS currencies(code TEXT PRIMARY KEY, rate REAL);
CREATE TABLE IF NOT EXISTS fs_items(name TEXT PRIMARY KEY, section TEXT, role TEXT DEFAULT '', sort INTEGER);
CREATE TABLE IF NOT EXISTS cf_items(name TEXT PRIMARY KEY, activity TEXT, bucket TEXT DEFAULT '', sort INTEGER);
CREATE TABLE IF NOT EXISTS branch_cats(name TEXT PRIMARY KEY, kind TEXT, sort INTEGER);
CREATE TABLE IF NOT EXISTS exp_groups(name TEXT PRIMARY KEY, sort INTEGER);
CREATE TABLE IF NOT EXISTS accounts(
    code TEXT PRIMARY KEY, name TEXT, grp TEXT DEFAULT '', fs_item TEXT DEFAULT '', cf_item TEXT DEFAULT '',
    branch_cat TEXT DEFAULT '', exp_group TEXT DEFAULT '', behavior TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS tb(
    period TEXT, code TEXT, name TEXT, od REAL, oc REAL, md REAL, mc REAL, cd REAL, cc REAL,
    PRIMARY KEY(period, code));
CREATE TABLE IF NOT EXISTS branch_mov(
    period TEXT, branch TEXT, code TEXT, name TEXT, amount REAL, PRIMARY KEY(period, branch, code));
CREATE TABLE IF NOT EXISTS customers(
    id INTEGER PRIMARY KEY, period TEXT, no TEXT, name TEXT, region TEXT, branch TEXT, rep TEXT, cls TEXT,
    ctype TEXT, b0 REAL, b1 REAL, b2 REAL, b3 REAL, b4 REAL, guarantee REAL);
CREATE INDEX IF NOT EXISTS customers_period ON customers(period);
CREATE TABLE IF NOT EXISTS suppliers(
    id INTEGER PRIMARY KEY, period TEXT, no TEXT, name TEXT, account TEXT, credit REAL, currency TEXT,
    b0 REAL, b1 REAL, b2 REAL, b3 REAL, b4 REAL);
CREATE INDEX IF NOT EXISTS suppliers_period ON suppliers(period);
CREATE TABLE IF NOT EXISTS customer_master(
    code TEXT PRIMARY KEY, name TEXT, ctype TEXT DEFAULT '', rep TEXT DEFAULT '', branch TEXT DEFAULT '',
    region TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS items(
    code TEXT PRIMARY KEY, name TEXT, unit TEXT DEFAULT '', grp_main TEXT DEFAULT '', grp_sub1 TEXT DEFAULT '',
    grp_sub2 TEXT DEFAULT '', main_item TEXT DEFAULT '', itype TEXT DEFAULT '', active TEXT DEFAULT '',
    guessed INTEGER DEFAULT 0, guess_from TEXT DEFAULT '', guess_score REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS item_sales(
    period TEXT, cust_code TEXT, cust_name TEXT, item_code TEXT, item_name TEXT, unit TEXT,
    qty REAL, free_qty REAL, sales REAL, ret_qty REAL, returns REAL, net_qty REAL, net REAL,
    cnet REAL, cost REAL, PRIMARY KEY(period, cust_code, item_code));
CREATE TABLE IF NOT EXISTS item_purchases(
    id INTEGER PRIMARY KEY, period TEXT, supp_no TEXT, supp_name TEXT, currency TEXT, item_code TEXT,
    item_name TEXT, unit TEXT, qty REAL, net REAL);
CREATE INDEX IF NOT EXISTS item_purchases_period ON item_purchases(period);
CREATE TABLE IF NOT EXISTS annual_tb(
    period TEXT, code TEXT, name TEXT, od REAL, oc REAL, md REAL, mc REAL, cd REAL, cc REAL,
    PRIMARY KEY(period, code));
CREATE TABLE IF NOT EXISTS annual_branch(
    period TEXT, branch TEXT, code TEXT, name TEXT, amount REAL, PRIMARY KEY(period, branch, code));
"""

CUSTOMER_FIELDS = ["no", "name", "region", "branch", "rep", "cls", "ctype", "b0", "b1", "b2", "b3", "b4", "guarantee"]
SUPPLIER_FIELDS = ["no", "name", "account", "credit", "currency", "b0", "b1", "b2", "b3", "b4"]
MASTER_FIELDS = ["code", "name", "ctype", "rep", "branch", "region"]
ITEM_FIELDS = ["code", "name", "unit", "grp_main", "grp_sub1", "grp_sub2", "main_item", "itype", "active",
               "guessed", "guess_from", "guess_score"]
SALES_FIELDS = ["cust_code", "cust_name", "item_code", "item_name", "unit", "qty", "free_qty", "sales", "ret_qty",
                "returns", "net_qty", "net", "cnet", "cost"]
PURCHASE_FIELDS = ["supp_no", "supp_name", "currency", "item_code", "item_name", "unit", "qty", "net"]

LISTS = {
    # table: (columns after name, account column that references it)
    "fs_items": (("section", "role"), "fs_item"),
    "cf_items": (("activity", "bucket"), "cf_item"),
    "branch_cats": (("kind",), "branch_cat"),
    "exp_groups": ((), "exp_group"),
}


@dataclass
class Account:
    code: str
    name: str
    grp: str = ""
    fs_item: str = ""
    cf_item: str = ""
    branch_cat: str = ""
    exp_group: str = ""
    behavior: str = ""


ACCOUNT_FIELDS = ["code", "name", "grp", "fs_item", "cf_item", "branch_cat", "exp_group", "behavior"]


class CompanyDB:
    def __init__(self, path):
        self.path = path
        self.con = sqlite3.connect(path)
        self.con.executescript(SCHEMA)
        if not self.con.execute("SELECT 1 FROM settings LIMIT 1").fetchone():
            self._seed()
        self.con.commit()

    def close(self):
        self.con.close()

    def _seed(self):
        c = self.con
        c.executemany("INSERT INTO settings VALUES(?,?)", defaults.SETTINGS.items())
        c.executemany("INSERT INTO fs_items VALUES(?,?,?,?)", [(n, s, r, i) for i, (n, s, r) in enumerate(defaults.FS_ITEMS)])
        c.executemany("INSERT INTO cf_items VALUES(?,?,?,?)", [(n, a, b, i) for i, (n, a, b) in enumerate(defaults.CF_ITEMS)])
        c.executemany("INSERT INTO branch_cats VALUES(?,?,?)", [(n, k, i) for i, (n, k) in enumerate(defaults.BRANCH_CATS)])
        c.executemany("INSERT INTO exp_groups VALUES(?,?)", [(n, i) for i, n in enumerate(defaults.EXP_GROUPS)])
        c.execute("INSERT INTO currencies VALUES('SAR', 1)")

    # ---------------- settings
    def setting(self, key, default=None):
        r = self.con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r[0] if r else (defaults.SETTINGS.get(key) if default is None else default)

    def setting_float(self, key):
        try:
            return float(self.setting(key))
        except (TypeError, ValueError):
            return float(defaults.SETTINGS[key])

    def set_setting(self, key, value):
        self.con.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))
        self.con.commit()

    # ---------------- branches / currencies
    def branches(self):
        return [r[0] for r in self.con.execute("SELECT name FROM branches ORDER BY sort, rowid")]

    def branch_rows(self):
        return self.con.execute("SELECT name, region FROM branches ORDER BY sort, rowid").fetchall()

    def save_branches(self, rows):
        """rows: [(name, region)] — renames are not tracked; data keeps the old name."""
        self.con.execute("DELETE FROM branches")
        self.con.executemany("INSERT OR IGNORE INTO branches VALUES(?,?,?)",
                             [(n.strip(), r.strip(), i) for i, (n, r) in enumerate(rows) if n.strip()])
        self.con.commit()

    def currencies(self):
        return self.con.execute("SELECT code, rate FROM currencies ORDER BY rowid").fetchall()

    def save_currencies(self, rows):
        self.con.execute("DELETE FROM currencies")
        self.con.executemany("INSERT OR IGNORE INTO currencies VALUES(?,?)", [(c.strip().upper(), r) for c, r in rows if c.strip()])
        self.con.commit()

    # ---------------- lists
    def list_rows(self, table):
        cols = LISTS[table][0]
        sel = ", ".join(("name",) + cols)
        return self.con.execute(f"SELECT {sel} FROM {table} ORDER BY sort, rowid").fetchall()

    def list_names(self, table):
        return [r[0] for r in self.list_rows(table)]

    def list_attr(self, table, attr):
        cols = LISTS[table][0]
        i = cols.index(attr) + 1
        return {r[0]: r[i] for r in self.list_rows(table)}

    def save_list(self, table, rows, renames=None):
        """rows: tuples (name, *attrs). renames: {old: new} applied to accounts too."""
        cols, acc_col = LISTS[table]
        c = self.con
        for old, new in (renames or {}).items():
            if old != new:
                c.execute(f"UPDATE accounts SET {acc_col}=? WHERE {acc_col}=?", (new, old))
        c.execute(f"DELETE FROM {table}")
        ph = ",".join("?" * (len(cols) + 2))
        c.executemany(f"INSERT OR IGNORE INTO {table} VALUES({ph})",
                      [tuple(r[:len(cols) + 1]) + (i,) for i, r in enumerate(rows) if r[0].strip()])
        c.commit()

    # ---------------- accounts
    def accounts(self):
        rows = self.con.execute(f"SELECT {', '.join(ACCOUNT_FIELDS)} FROM accounts").fetchall()
        return {r[0]: Account(*r) for r in rows}

    def save_accounts(self, accounts):
        self.con.executemany(
            f"INSERT OR REPLACE INTO accounts VALUES({','.join('?' * len(ACCOUNT_FIELDS))})",
            [tuple(getattr(a, f) or "" for f in ACCOUNT_FIELDS) for a in accounts])
        self.con.commit()

    def delete_accounts(self, codes):
        self.con.executemany("DELETE FROM accounts WHERE code=?", [(c,) for c in codes])
        self.con.commit()

    def ensure_accounts(self, pairs):
        """Add any (code, name) not yet in the chart (unmapped). Returns the new codes."""
        existing = set(r[0] for r in self.con.execute("SELECT code FROM accounts"))
        new = [(c, n) for c, n in pairs if c not in existing]
        self.con.executemany("INSERT OR IGNORE INTO accounts(code, name) VALUES(?,?)", new)
        self.con.commit()
        return [c for c, _ in new]

    # ---------------- trial balances
    def periods(self):
        return [r[0] for r in self.con.execute("SELECT DISTINCT period FROM tb ORDER BY period")]

    def tb(self, period):
        rows = self.con.execute("SELECT code, name, od, oc, md, mc, cd, cc FROM tb WHERE period=?", (period,))
        return {r[0]: r[1:] for r in rows}

    def all_tb(self):
        out = {}
        for r in self.con.execute("SELECT period, code, name, od, oc, md, mc, cd, cc FROM tb"):
            out.setdefault(r[0], {})[r[1]] = r[2:]
        return out

    def save_tb(self, period, rows):
        """rows: (code, name, od, oc, md, mc, cd, cc). Replaces the period."""
        c = self.con
        c.execute("DELETE FROM tb WHERE period=?", (period,))
        c.executemany("INSERT OR REPLACE INTO tb VALUES(?,?,?,?,?,?,?,?,?)", [(period,) + tuple(r) for r in rows])
        c.commit()
        return self.ensure_accounts([(r[0], r[1]) for r in rows])

    def delete_period(self, period):
        for table in ("tb", "branch_mov", "customers", "suppliers", "item_sales", "item_purchases"):
            self.con.execute(f"DELETE FROM {table} WHERE period=?", (period,))
        self.con.commit()

    # ---------------- customer / supplier aging
    def save_aging(self, table, period, rows):
        """table: customers | suppliers. rows: dicts with the table fields. Replaces the period."""
        fields = CUSTOMER_FIELDS if table == "customers" else SUPPLIER_FIELDS
        self.con.execute(f"DELETE FROM {table} WHERE period=?", (period,))
        self.con.executemany(
            f"INSERT INTO {table}(period, {', '.join(fields)}) VALUES({','.join('?' * (len(fields) + 1))})",
            [(period,) + tuple(r.get(f) for f in fields) for r in rows])
        self.con.commit()

    def aging(self, table, period):
        fields = CUSTOMER_FIELDS if table == "customers" else SUPPLIER_FIELDS
        cur = self.con.execute(f"SELECT {', '.join(fields)} FROM {table} WHERE period=? ORDER BY id", (period,))
        return [dict(zip(fields, r)) for r in cur]

    def aging_periods(self, table):
        return [r[0] for r in self.con.execute(f"SELECT DISTINCT period FROM {table} ORDER BY period")]

    # ---------------- branch movements
    def branch_periods(self):
        return self.con.execute(
            "SELECT period, branch, COUNT(*) FROM branch_mov GROUP BY period, branch ORDER BY period, branch").fetchall()

    def all_branch_mov(self):
        out = {}
        for p, b, code, amt in self.con.execute("SELECT period, branch, code, amount FROM branch_mov"):
            out.setdefault(p, {}).setdefault(b, {})[code] = amt
        return out

    def save_branch_mov(self, period, branch, rows):
        """rows: (code, name, amount net = debit - credit). Replaces that branch/period."""
        c = self.con
        c.execute("DELETE FROM branch_mov WHERE period=? AND branch=?", (period, branch))
        c.executemany("INSERT OR REPLACE INTO branch_mov VALUES(?,?,?,?,?)",
                      [(period, branch, code, name, amt) for code, name, amt in rows])
        c.commit()
        if branch not in self.branches():
            c.execute("INSERT OR IGNORE INTO branches VALUES(?,?,?)", (branch, "", 999))
            c.commit()
        return self.ensure_accounts([(r[0], r[1]) for r in rows])

    def delete_branch_mov(self, period, branch):
        self.con.execute("DELETE FROM branch_mov WHERE period=? AND branch=?", (period, branch))
        self.con.commit()

    # ---------------- customer master (code → type, rep, branch, region)
    def customer_master(self):
        cur = self.con.execute(f"SELECT {', '.join(MASTER_FIELDS)} FROM customer_master ORDER BY code")
        return {r[0]: dict(zip(MASTER_FIELDS, r)) for r in cur}

    def save_customer_master(self, rows, replace=True):
        """rows: dicts. replace=False updates/adds without deleting customers missing from the file."""
        if replace:
            self.con.execute("DELETE FROM customer_master")
        self.con.executemany(
            f"INSERT OR REPLACE INTO customer_master VALUES({','.join('?' * len(MASTER_FIELDS))})",
            [tuple(r.get(f, "") or "" for f in MASTER_FIELDS) for r in rows])
        self.con.commit()

    # ---------------- items and their classification
    def items(self):
        cur = self.con.execute(f"SELECT {', '.join(ITEM_FIELDS)} FROM items ORDER BY code")
        return {r[0]: dict(zip(ITEM_FIELDS, r)) for r in cur}

    def save_items(self, rows):
        self.con.execute("DELETE FROM items")
        self.con.executemany(f"INSERT OR REPLACE INTO items VALUES({','.join('?' * len(ITEM_FIELDS))})",
                             [tuple(r.get(f, "") for f in ITEM_FIELDS) for r in rows])
        self.con.commit()

    def update_item(self, code, **fields):
        sets = ", ".join(f"{k}=?" for k in fields)
        self.con.execute(f"UPDATE items SET {sets} WHERE code=?", (*fields.values(), code))
        self.con.commit()

    # ---------------- item sales / purchases (monthly)
    def item_sales(self, periods):
        q = ",".join("?" * len(periods))
        cur = self.con.execute(f"SELECT period, {', '.join(SALES_FIELDS)} FROM item_sales WHERE period IN ({q})",
                               tuple(periods))
        return [dict(zip(["period"] + SALES_FIELDS, r)) for r in cur]

    def save_item_sales(self, period, rows):
        self.con.execute("DELETE FROM item_sales WHERE period=?", (period,))
        self.con.executemany(
            f"INSERT OR REPLACE INTO item_sales(period, {', '.join(SALES_FIELDS)}) "
            f"VALUES({','.join('?' * (len(SALES_FIELDS) + 1))})",
            [(period,) + tuple(r.get(f) for f in SALES_FIELDS) for r in rows])
        self.con.commit()

    def item_purchases(self, periods):
        q = ",".join("?" * len(periods))
        cur = self.con.execute(
            f"SELECT period, {', '.join(PURCHASE_FIELDS)} FROM item_purchases WHERE period IN ({q}) ORDER BY id",
            tuple(periods))
        return [dict(zip(["period"] + PURCHASE_FIELDS, r)) for r in cur]

    def save_item_purchases(self, period, rows):
        self.con.execute("DELETE FROM item_purchases WHERE period=?", (period,))
        self.con.executemany(
            f"INSERT INTO item_purchases(period, {', '.join(PURCHASE_FIELDS)}) "
            f"VALUES({','.join('?' * (len(PURCHASE_FIELDS) + 1))})",
            [(period,) + tuple(r.get(f) for f in PURCHASE_FIELDS) for r in rows])
        self.con.commit()

    def item_periods(self):
        """{period: (sales rows, has cost, purchase rows)}"""
        out = {}
        for p, n, c in self.con.execute(
                "SELECT period, COUNT(*), SUM(CASE WHEN cost IS NOT NULL THEN 1 ELSE 0 END) FROM item_sales GROUP BY period"):
            out[p] = [n, bool(c), 0]
        for p, n in self.con.execute("SELECT period, COUNT(*) FROM item_purchases GROUP BY period"):
            out.setdefault(p, [0, False, 0])[2] = n
        return out

    # ---------------- full-year trial balances and branch movements (key = last month of the fiscal year)
    def annual_tb(self):
        out = {}
        for r in self.con.execute("SELECT period, code, name, od, oc, md, mc, cd, cc FROM annual_tb"):
            out.setdefault(r[0], {})[r[1]] = r[2:]
        return out

    def save_annual_tb(self, period, rows):
        c = self.con
        c.execute("DELETE FROM annual_tb WHERE period=?", (period,))
        c.executemany("INSERT OR REPLACE INTO annual_tb VALUES(?,?,?,?,?,?,?,?,?)", [(period,) + tuple(r) for r in rows])
        c.commit()
        return self.ensure_accounts([(r[0], r[1]) for r in rows])

    def annual_branch(self):
        out = {}
        for p, b, code, amt in self.con.execute("SELECT period, branch, code, amount FROM annual_branch"):
            out.setdefault(p, {}).setdefault(b, {})[code] = amt
        return out

    def save_annual_branch(self, period, branch, rows):
        c = self.con
        c.execute("DELETE FROM annual_branch WHERE period=? AND branch=?", (period, branch))
        c.executemany("INSERT OR REPLACE INTO annual_branch VALUES(?,?,?,?,?)",
                      [(period, branch, code, name, amt) for code, name, amt in rows])
        c.commit()
        if branch not in self.branches():
            c.execute("INSERT OR IGNORE INTO branches VALUES(?,?,?)", (branch, "", 999))
            c.commit()
        return self.ensure_accounts([(r[0], r[1]) for r in rows])

    def annual_periods(self):
        """{period: (accounts in the company TB, [branches])}"""
        out = {}
        for p, n in self.con.execute("SELECT period, COUNT(*) FROM annual_tb GROUP BY period"):
            out[p] = [n, []]
        for p, b in self.con.execute("SELECT DISTINCT period, branch FROM annual_branch ORDER BY branch"):
            out.setdefault(p, [0, []])[1].append(b)
        return out

    def delete_annual(self, period):
        for table in ("annual_tb", "annual_branch"):
            self.con.execute(f"DELETE FROM {table} WHERE period=?", (period,))
        self.con.commit()
