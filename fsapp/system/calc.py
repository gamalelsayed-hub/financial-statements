"""Financial computations on the company database.

Conventions (same as the Excel model):
  net = debit - credit for every balance.
  Balance sheet: assets shown as +net, liabilities and equity as -net.
  Income statement: every line shown as -net (income positive, expenses negative).
  Period income statement = movement of the months in the period; year-to-date = closing balance
  of P&L accounts at the end month.
  Cash-flow line of an item = -(movement of the balance-sheet accounts mapped to it). P&L accounts
  mapped to a cash-flow item (e.g. gain on sale of assets) are taken out of operating activities and
  moved to the item's activity (investing for an operating item).
"""
from collections import OrderedDict

from .defaults import ASSET_SECTIONS, BS_SECTIONS, IS_SECTIONS, SECTION_NAMES

MONTHS_AR = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر",
             "نوفمبر", "ديسمبر"]


# ---------------------------------------------------------------- periods
def month_add(p, k):
    y, m = int(p[:4]), int(p[5:7])
    i = y * 12 + (m - 1) + k
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def months_range(end, n):
    return [month_add(end, -i) for i in range(n - 1, -1, -1)]


def month_label(p):
    return f"{MONTHS_AR[int(p[5:7]) - 1]} {p[:4]}"


def range_label(months):
    if len(months) == 1:
        return month_label(months[0])
    return f"{month_label(months[0])} — {month_label(months[-1])}"


def safe_div(a, b):
    if a is None or b is None or abs(b) < 1e-9:
        return None
    return a / b


class Ctx:
    """Everything loaded once from the database for building reports."""

    def __init__(self, db):
        self.db = db
        self.accounts = db.accounts()
        self.tbs = db.all_tb()
        self.bmov = db.all_branch_mov()
        self.periods = sorted(self.tbs)
        self.fs_section = db.list_attr("fs_items", "section")
        self.fs_role = db.list_attr("fs_items", "role")
        self.fs_order = db.list_names("fs_items")
        self.cf_activity = db.list_attr("cf_items", "activity")
        self.cf_bucket = db.list_attr("cf_items", "bucket")
        self.cf_order = db.list_names("cf_items")
        self.cat_kind = db.list_attr("branch_cats", "kind")
        self.cat_order = db.list_names("branch_cats")
        self.exp_groups = db.list_names("exp_groups")
        self.branches = db.branches()
        for p in self.bmov:
            for b in self.bmov[p]:
                if b not in self.branches:
                    self.branches.append(b)
        self.company = db.setting("company") or "—"
        self.currency = db.setting("currency") or ""
        self.fiscal_start = int(db.setting_float("fiscal_start") or 1)
        self.credit_ratio = db.setting_float("credit_ratio")
        self.alert_pct = db.setting_float("alert_pct")
        self.alert_amount = db.setting_float("alert_amount")
        self.admin_label = db.setting("admin_label") or "الإدارة والمستودع المركزي"
        self.base_currency = (db.currencies()[0][0] if db.currencies() else "SAR").upper()
        self._bal_cache = {}
        self._aging = {}

    def aging(self, table, period):
        key = (table, period)
        if key not in self._aging:
            self._aging[key] = self.db.aging(table, period)
        return self._aging[key]

    # -------- account helpers
    def section(self, code):
        a = self.accounts.get(code)
        return self.fs_section.get(a.fs_item, "") if a else ""

    def is_bs(self, code):
        return self.section(code) in BS_SECTIONS

    def is_pl(self, code):
        return self.section(code) in IS_SECTIONS

    # -------- periods
    def ytd_months(self, end):
        y, m = int(end[:4]), int(end[5:7])
        start_y = y if m >= self.fiscal_start else y - 1
        start = f"{start_y:04d}-{self.fiscal_start:02d}"
        n = (y * 12 + m) - (start_y * 12 + self.fiscal_start) + 1
        return months_range(end, n)

    def year_months(self, end):
        """The 12 months of the fiscal year containing end."""
        first = self.ytd_months(end)[0]
        return [month_add(first, i) for i in range(12)]

    def has(self, p):
        return p in self.tbs

    # -------- balances
    def bal(self, months):
        """{code: [open, mov, close]} for a list of consecutive months."""
        key = tuple(months)
        if key in self._bal_cache:
            return self._bal_cache[key]
        out = {}
        first, last = self.tbs.get(months[0], {}), self.tbs.get(months[-1], {})
        for code, r in first.items():
            out.setdefault(code, [0.0, 0.0, 0.0])[0] = (r[1] or 0) - (r[2] or 0)
        for code, r in last.items():
            out.setdefault(code, [0.0, 0.0, 0.0])[2] = (r[5] or 0) - (r[6] or 0)
        for m in months:
            for code, r in self.tbs.get(m, {}).items():
                out.setdefault(code, [0.0, 0.0, 0.0])[1] += (r[3] or 0) - (r[4] or 0)
        self._bal_cache[key] = out
        return out

    def missing(self, months):
        return [m for m in months if m not in self.tbs]

    def fs_net(self, months, idx):
        """{fs_item: net} for idx 0=open, 1=movement, 2=close. Unmapped accounts under ''."""
        out = {}
        for code, v in self.bal(months).items():
            a = self.accounts.get(code)
            item = a.fs_item if a and a.fs_item in self.fs_section else ""
            out[item] = out.get(item, 0.0) + v[idx]
        return out

    # ---------------------------------------------------------------- income statement
    def is_figures(self, months, ytd=False):
        """Income statement values per item and subtotals (shown as -net)."""
        if ytd:
            net = self.fs_net(months, 2)
        else:
            net = self.fs_net(months, 1)
        val = {i: -net.get(i, 0.0) for i in self.fs_order if self.fs_section.get(i) in IS_SECTIONS}
        sec = {s: sum(v for i, v in val.items() if self.fs_section[i] == s) for s in IS_SECTIONS}
        f = {"items": val, "sec": sec}
        f["net_sales"] = sec["SALES"]
        f["cogs"] = -sec["COGS"]
        f["gross"] = sec["SALES"] + sec["COGS"]
        f["admin"] = -sec["ADMIN"]
        f["selling"] = -sec["SELLING"]
        f["op"] = f["gross"] + sec["OTHER_OP"] + sec["ADMIN"] + sec["SELLING"]
        f["pbt"] = f["op"] + sec["NONOP"]
        f["ni"] = f["pbt"] + sec["ZAKAT"]
        f["finance_cost"] = -sum(v for i, v in val.items() if self.fs_role.get(i) == "finance_cost")
        cos = [v for i, v in val.items() if self.fs_role.get(i) == "cost_of_sales"]
        f["cost_of_sales"] = -sum(cos) if cos else f["cogs"]
        return f

    def is_rows(self):
        """Row layout of the income statement: (key, label, kind). key = item name or subtotal key."""
        rows = []

        def items(s):
            for i in self.fs_order:
                if self.fs_section.get(i) == s:
                    rows.append((i, i, "item"))

        items("SALES")
        rows.append(("net_sales", "صافي المبيعات", "sub"))
        items("COGS")
        rows.append(("gross", "مجمل الربح", "sub"))
        items("OTHER_OP")
        rows.append((None, SECTION_NAMES["ADMIN"], "hdr"))
        items("ADMIN")
        rows.append(("sec:ADMIN", "إجمالي " + SECTION_NAMES["ADMIN"], "sub"))
        rows.append((None, SECTION_NAMES["SELLING"], "hdr"))
        items("SELLING")
        rows.append(("sec:SELLING", "إجمالي " + SECTION_NAMES["SELLING"], "sub"))
        rows.append(("op", "الربح التشغيلي", "sub"))
        items("NONOP")
        rows.append(("pbt", "الربح قبل الزكاة", "sub"))
        items("ZAKAT")
        rows.append(("ni", "صافي الربح", "tot"))
        return rows

    @staticmethod
    def is_value(f, key):
        if key is None:
            return None
        if key.startswith("sec:"):
            return f["sec"][key[4:]]
        if key in f["items"]:
            return f["items"][key]
        return f[key]

    # ---------------------------------------------------------------- balance sheet
    def bs_figures(self, months, idx):
        """idx 2 = closing of the range, 0 = opening of the range."""
        net = self.fs_net(months, idx)
        val = {}
        for i in self.fs_order:
            s = self.fs_section.get(i)
            if s in BS_SECTIONS:
                val[i] = net.get(i, 0.0) * (1 if s in ASSET_SECTIONS else -1)
        sec = {s: sum(v for i, v in val.items() if self.fs_section[i] == s) for s in BS_SECTIONS}
        pl = -sum(net.get(i, 0.0) for i in self.fs_order if self.fs_section.get(i) in IS_SECTIONS)
        plug = sum(net.values())
        f = {"items": val, "sec": sec, "profit": pl, "plug": plug}
        f["sec"]["EQ"] = sec["EQ"] + pl + plug
        f["assets"] = sec["CA"] + sec["NCA"]
        f["liabilities"] = sec["CL"] + sec["NCL"]
        f["le"] = f["liabilities"] + f["sec"]["EQ"]
        f["diff"] = f["assets"] - f["le"]
        f["equity"] = f["sec"]["EQ"]
        for role in ("cash", "receivables", "inventory", "transit", "payables", "debt"):
            f[role] = sum(v for i, v in val.items() if self.fs_role.get(i) == role)
        # short facilities / long loans follow the cash-flow grouping of the accounts (like the Excel dashboard)
        st = lt = 0.0
        for code, v in self.bal(months).items():
            a = self.accounts.get(code)
            if not a or self.fs_role.get(a.fs_item) != "debt":
                continue
            if self.cf_bucket.get(a.cf_item) == "st_fin":
                st -= v[idx]
            else:
                lt -= v[idx]
        f["debt_st"], f["debt_lt"] = st, lt
        return f

    def bs_rows(self):
        rows = []
        for s, total in (("CA", "إجمالي الأصول المتداولة"), ("NCA", "إجمالي الأصول غير المتداولة")):
            rows.append((None, SECTION_NAMES[s], "hdr"))
            rows += [(i, i, "item") for i in self.fs_order if self.fs_section.get(i) == s]
            rows.append(("sec:" + s, total, "sub"))
        rows.append(("assets", "إجمالي الأصول", "tot"))
        for s, total in (("CL", "إجمالي الخصوم المتداولة"), ("NCL", "إجمالي الخصوم غير المتداولة")):
            rows.append((None, SECTION_NAMES[s], "hdr"))
            rows += [(i, i, "item") for i in self.fs_order if self.fs_section.get(i) == s]
            rows.append(("sec:" + s, total, "sub"))
        rows.append(("liabilities", "إجمالي الخصوم", "sub"))
        rows.append((None, SECTION_NAMES["EQ"], "hdr"))
        rows += [(i, i, "item") for i in self.fs_order if self.fs_section.get(i) == "EQ"]
        rows.append(("profit", "صافي ربح الفترة (من بداية السنة)", "item"))
        rows.append(("plug", "فرق ميزان المراجعة (أرصدة غير مقفلة)", "item"))
        rows.append(("sec:EQ", "إجمالي حقوق الملكية", "sub"))
        rows.append(("le", "إجمالي الخصوم وحقوق الملكية", "tot"))
        rows.append(("diff", "الفرق (يجب أن يكون صفرًا)", "note"))
        return rows

    @staticmethod
    def bs_value(f, key):
        if key is None:
            return None
        if key.startswith("sec:"):
            return f["sec"][key[4:]]
        if key in f["items"]:
            return f["items"][key]
        return f[key]

    # ---------------------------------------------------------------- cash flow
    def cash_flow(self, months):
        b = self.bal(months)
        lines = {i: 0.0 for i in self.cf_order}
        reclass_op = {}   # P&L accounts taken out of operating activities
        reclass_to = {}   # ... and added to their activity
        cash_open = cash_close = 0.0
        no_item = []
        ni = 0.0
        for code, (o, m, c) in b.items():
            a = self.accounts.get(code)
            sec = self.section(code)
            item = a.cf_item if a and a.cf_item in self.cf_activity else ""
            if sec in IS_SECTIONS:
                ni -= m
                if item:
                    reclass_op[item] = reclass_op.get(item, 0.0) + m
                    reclass_to[item] = reclass_to.get(item, 0.0) - m
                continue
            if sec not in BS_SECTIONS:
                continue
            if not item:
                if abs(m) > 0.005:
                    no_item.append((code, m))
                continue
            if self.cf_activity[item] == "CASH":
                cash_open += o
                cash_close += c
            else:
                lines[item] -= m
        out = {"ni": ni, "cash_open": cash_open, "cash_close": cash_close, "no_item": no_item}
        sections = {}
        for act in ("OP", "INV", "FIN"):
            rows = []
            for i in self.cf_order:
                if self.cf_activity.get(i) != act:
                    continue
                label = i
                if act == "OP" and self.cf_bucket.get(i) != "profit":
                    label = "التغير في " + i
                rows.append(("cf:" + i, label, lines[i]))
                if act == "OP" and i in reclass_op:
                    rows.append(("rc:" + i, f"ناقص: {i} (تُنقل للاستثمارية)", reclass_op[i]))
            if act == "INV":
                for i, v in reclass_to.items():
                    if self.cf_activity.get(i) in ("OP", "INV"):
                        rows.append(("rt:" + i, f"{i} (جزء من المتحصلات)", v))
            if act == "FIN":
                for i, v in reclass_to.items():
                    if self.cf_activity.get(i) == "FIN":
                        rows.append(("rt:" + i, f"{i} (تسوية)", v))
            sections[act] = rows
        # P&L reclasses into operating items that are not listed before (activity INV/FIN items)
        for i, v in reclass_op.items():
            if self.cf_activity.get(i) in ("INV", "FIN"):
                sections["OP"].append(("rc:" + i, f"ناقص: {i}", v))
        out["sections"] = sections
        out["cfo"] = ni + sum(r[2] for r in sections["OP"])
        out["cfi"] = sum(r[2] for r in sections["INV"])
        out["cff"] = sum(r[2] for r in sections["FIN"])
        out["net_change"] = out["cfo"] + out["cfi"] + out["cff"]
        out["cash_close_calc"] = cash_open + out["net_change"]
        out["cash_diff"] = out["cash_close_calc"] - cash_close
        capex = 0.0
        for key, label, v in sections["INV"]:
            capex -= v
        out["capex"] = capex
        out["buckets"] = self._buckets(lines, reclass_op, reclass_to, ni)
        return out

    def _buckets(self, lines, reclass_op, reclass_to, ni):
        bk = OrderedDict((k, 0.0) for k in ("profit", "receivables", "inventory", "payables", "other_wc",
                                            "assets", "st_fin", "owners", "lt_fin"))
        bk["profit"] += ni
        for i, v in lines.items():
            b = self.cf_bucket.get(i) or ("assets" if self.cf_activity.get(i) == "INV" else
                                          "lt_fin" if self.cf_activity.get(i) == "FIN" else "other_wc")
            if self.cf_activity.get(i) == "CASH":
                continue
            bk[b] += v
        for i, v in reclass_op.items():
            bk["profit"] += v
        for i, v in reclass_to.items():
            bk["assets"] += v
        return bk

    # ---------------------------------------------------------------- branches
    def branch_values(self, months, branch):
        """{code: -net summed over months} for a branch."""
        out = {}
        for m in months:
            for code, amt in self.bmov.get(m, {}).get(branch, {}).items():
                out[code] = out.get(code, 0.0) - (amt or 0.0)
        return out

    def company_pl_values(self, months, ytd=False):
        out = {}
        for code, (o, mv, c) in self.bal(months).items():
            if self.is_pl(code):
                out[code] = -(c if ytd else mv)
        return out

    def branch_figures(self, values):
        """Group code values into branch-income categories and expense groups."""
        cats = {c: 0.0 for c in self.cat_order}
        groups = {g: 0.0 for g in self.exp_groups}
        no_group = 0.0
        unmapped = 0.0
        for code, v in values.items():
            a = self.accounts.get(code)
            cat = a.branch_cat if a else ""
            if cat not in cats:
                unmapped += v
                continue
            cats[cat] += v
            if self.cat_kind.get(cat) == "opex":
                if a.exp_group in groups:
                    groups[a.exp_group] += v
                else:
                    no_group += v
        kind_sum = {k: sum(v for c, v in cats.items() if self.cat_kind.get(c) == k)
                    for k in ("sales", "cogs", "opex", "below")}
        f = {"cats": cats, "groups": groups, "no_group": no_group, "unmapped": unmapped}
        f["net_sales"] = kind_sum["sales"]
        f["gross"] = kind_sum["sales"] + kind_sum["cogs"]
        f["direct"] = kind_sum["opex"]
        f["contribution"] = f["gross"] + f["direct"]
        f["below"] = kind_sum["below"]
        return f

    def branches_report_data(self, months, ytd_view=False):
        """Per-branch income with the admin/central column and allocation of its expenses."""
        cols = OrderedDict()
        for b in self.branches:
            cols[b] = self.branch_figures(self.branch_values(months, b))
        company_months = months
        company = self.branch_figures(self.company_pl_values(company_months, ytd=ytd_view))
        # admin column = company minus all branches
        admin = {"cats": {}, "groups": {}}
        for k in ("cats", "groups"):
            for key in company[k]:
                admin[k][key] = company[k][key] - sum(c[k][key] for c in cols.values())
        for k in ("no_group", "unmapped", "net_sales", "gross", "direct", "contribution", "below"):
            admin[k] = company[k] - sum(c[k] for c in cols.values())
        total_direct = sum(c["direct"] for c in cols.values())
        for b, c in cols.items():
            c["ratio"] = safe_div(c["direct"], total_direct) or 0.0
            c["share"] = c["ratio"] * admin["direct"]
            c["after"] = c["contribution"] + c["share"]
            c["net"] = c["after"] + c["below"]
        admin["ratio"] = None
        admin["share"] = -sum(c["share"] for c in cols.values())
        admin["after"] = admin["contribution"] + admin["share"]
        admin["net"] = admin["after"] + admin["below"]
        company["ratio"] = 1.0 if cols else None
        company["share"] = 0.0
        company["after"] = company["contribution"]
        company["net"] = company["contribution"] + company["below"]
        return cols, admin, company

    # ---------------------------------------------------------------- expenses
    def opex_by_account(self, months, source=None):
        """Operating expenses (positive) per account. source: None = company, else branch name."""
        vals = self.branch_values(months, source) if source else self.company_pl_values(months)
        out = {}
        for code, v in vals.items():
            a = self.accounts.get(code)
            if a and self.cat_kind.get(a.branch_cat) == "opex":
                out[code] = -v
        return out

    def prior_months_in_year(self, months):
        ytd = self.ytd_months(months[-1])
        return [m for m in ytd if m < months[0] and m in self.tbs]

    # ---------------------------------------------------------------- ratios
    def ratios(self, months):
        """Year-to-date ratios, annualized; averages use the opening and closing of the report period."""
        end = months[-1]
        ytd = self.ytd_months(end)
        avail = [m for m in ytd if m in self.tbs]
        n = len(ytd)
        ann = 12 / n
        f = self.is_figures([end], ytd=True)
        close = self.bs_figures([end], 2)
        start = self.bs_figures(months, 0) if months[0] in self.tbs else close

        def avg(k):
            return (close[k] + start[k]) / 2

        ca, cl = close["sec"]["CA"], close["sec"]["CL"]
        days = 365
        inv_t = safe_div(f["cogs"] * ann, avg("inventory"))
        rec_t = safe_div(f["net_sales"] * ann * self.credit_ratio, avg("receivables"))
        pay_t = safe_div(f["cogs"] * ann, avg("payables"))
        dio, dso, dpo = safe_div(days, inv_t), safe_div(days, rec_t), safe_div(days, pay_t)
        ccc = None if None in (dio, dso, dpo) else dio + dso - dpo
        r = [
            ("نسبة التداول", safe_div(ca, cl), "x", "السيولة", "الأصول المتداولة ÷ الخصوم المتداولة",
             "أعلى من 1 = الأصول القصيرة تغطي الالتزامات القصيرة"),
            ("النسبة السريعة", safe_div(ca - close["inventory"] - close["transit"], cl), "x", "السيولة",
             "(المتداولة − المخزون − الاعتمادات) ÷ الخصوم المتداولة", ""),
            ("نسبة النقدية", safe_div(close["cash"], cl), "x", "السيولة", "النقد ÷ الخصوم المتداولة", ""),
            ("رأس المال العامل", ca - cl, "n", "السيولة", "الأصول المتداولة − الخصوم المتداولة", ""),
            ("دوران المخزون (مرة/سنة)", inv_t, "x", "النشاط", "تكلفة المبيعات السنوية ÷ متوسط المخزون", ""),
            ("أيام المخزون", dio, "d", "النشاط", "365 ÷ دوران المخزون", ""),
            ("دوران العملاء (مرة/سنة)", rec_t, "x", "النشاط", "صافي المبيعات الآجلة السنوية ÷ متوسط العملاء",
             f"نسبة الآجل المستخدمة {self.credit_ratio:.0%}"),
            ("فترة التحصيل (يوم)", dso, "d", "النشاط", "365 ÷ دوران العملاء", ""),
            ("دوران الموردين (مرة/سنة)", pay_t, "x", "النشاط", "تكلفة المبيعات السنوية ÷ متوسط الموردين", ""),
            ("فترة السداد (يوم)", dpo, "d", "النشاط", "365 ÷ دوران الموردين", ""),
            ("دورة التحويل النقدي (يوم)", ccc, "d", "النشاط", "أيام المخزون + التحصيل − السداد",
             "مدة بقاء النقد محبوسًا في التشغيل"),
            ("دوران الأصول", safe_div(f["net_sales"] * ann, avg("assets")), "x", "النشاط",
             "صافي المبيعات السنوية ÷ متوسط الأصول", ""),
            ("هامش مجمل الربح", safe_div(f["gross"], f["net_sales"]), "%", "الربحية", "مجمل الربح ÷ صافي المبيعات", ""),
            ("هامش الربح التشغيلي", safe_div(f["op"], f["net_sales"]), "%", "الربحية", "الربح التشغيلي ÷ صافي المبيعات", ""),
            ("هامش صافي الربح", safe_div(f["ni"], f["net_sales"]), "%", "الربحية", "صافي الربح ÷ صافي المبيعات", ""),
            ("المصروفات التشغيلية إلى المبيعات", safe_div(f["admin"] + f["selling"], f["net_sales"]), "%", "الربحية",
             "(الإدارية + البيعية) ÷ المبيعات", ""),
            ("العائد على الأصول (سنوي)", safe_div(f["ni"] * ann, avg("assets")), "%", "الربحية",
             "صافي الربح السنوي ÷ متوسط الأصول", ""),
            ("العائد على حقوق الملكية (سنوي)", safe_div(f["ni"] * ann, avg("equity")), "%", "الربحية",
             "صافي الربح السنوي ÷ متوسط حقوق الملكية", ""),
            ("القروض إلى حقوق الملكية", safe_div(close["debt"], close["equity"]), "x", "المديونية",
             "القروض والتسهيلات ÷ حقوق الملكية", ""),
            ("الخصوم إلى الأصول", safe_div(close["liabilities"], close["assets"]), "%", "المديونية",
             "إجمالي الخصوم ÷ إجمالي الأصول", ""),
            ("تغطية الفوائد (مرة)", safe_div(f["op"], f["finance_cost"]), "x", "المديونية",
             "الربح التشغيلي ÷ المصروفات التمويلية", "أقل من 1.5 ضغط تمويلي"),
            ("صافي الدين", close["debt"] - close["cash"], "n", "المديونية", "القروض − النقد", ""),
            ("دورة التشغيل (يوم)", None if None in (dio, dso) else dio + dso, "d", "السيولة",
             "أيام المخزون + فترة التحصيل", "المدة من شراء البضاعة حتى تحصيل ثمنها"),
        ]
        note = None if len(avail) == n else f"بعض أشهر السنة غير مدخلة ({n - len(avail)} شهر)."
        return r, note
