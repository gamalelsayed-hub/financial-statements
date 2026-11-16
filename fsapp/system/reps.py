"""Sales reps evaluation: sales, margin, items, customers, invoices, cost, commission, collection and a score out of
100 for each rep, for one month or several months (from the start of the year to the chosen month).

Score = five criteria, each measured on the rep himself (his target, or the company average) by its real value:
  sales target achievement, profit target achievement (profit target = sales target × company margin),
  collection rate (collected ÷ (collected + customers' balance at period end)) against the company rate,
  return on each riyal of cost (gross profit ÷ rep cost) against the company, margin against the company.
Each criterion gives its full weight at the cap (100% of target / of the average; return: 1.5 × the average).
Rep cost = salary + iqama (non-Saudi) + medical insurance + other costs. The commission is shown, not counted.
"""
from collections import defaultdict

from . import aging as AG
from . import rep_data as D
from .blocks import Para, Report, Row, Table
from .calc import month_add, range_label, safe_div

GRADES = [(85, "ممتاز"), (70, "جيد جداً"), (55, "جيد"), (40, "مقبول"), (0, "ضعيف")]
CRITERIA = [("sales", "تارجت المبيعات", "rep_w_sales"), ("profit", "تارجت الربح", "rep_w_profit"),
            ("coll", "التحصيل", "rep_w_coll"), ("roi", "العائد لكل ريال تكلفة", "rep_w_roi"),
            ("margin", "الهامش", "rep_w_margin")]
NOT_RATED = "غير مقيّم"
UNLINKED = "غير مربوط"


def grade(score):
    if score is None:
        return NOT_RATED
    return next(g for lim, g in GRADES if score >= lim)


def months_between(a, b):
    out, m = [], a
    while m <= b:
        out.append(m)
        m = month_add(m, 1)
    return out


# ------------------------------------------------------------------ which uploaded files cover the months
def pick_blocks(rows, months):
    """Sales-by-rep rows of the files that fall inside the months, without counting a month twice.

    Longer files first (the most months covered), then the monthly files for the months still missing.
    Returns (rows, covered months, files left out because they cross the period edge)."""
    want = set(months)
    files = sorted({(r["p_from"], r["p_to"]) for r in rows}, key=lambda f: (-len(months_between(*f)), f))
    chosen, covered, outside = [], set(), []
    for f in files:
        span = set(months_between(*f))
        if not span <= want:
            if span & want:
                outside.append(f)
            continue
        if span & covered:
            continue
        chosen.append(f)
        covered |= span
    keep = set(chosen)
    return [r for r in rows if (r["p_from"], r["p_to"]) in keep], sorted(covered), outside


class RepRow:
    """Everything about one rep for the period."""

    def __init__(self, code, name):
        self.code, self.name = code, name
        self.nationality, self.active = "مقيم", 1
        self.salary_m = self.target_m = self.other_m = 0.0
        self.net = self.cost_goods = 0.0
        self.items, self.customers = {}, {}          # key → [name, net, cost]
        self.inv = defaultdict(lambda: [0, 0.0])      # type → [count, value]
        self.inv_customers = set()
        self.commission = 0.0
        self.collected = 0.0
        self.closing = self.overdue = self.opening = None
        self.salaries = self.iqama = self.insurance = self.other = 0.0
        self.parts, self.score, self.rank = {}, None, None

    # ---- figures
    @property
    def gp(self):
        return self.net - self.cost_goods

    @property
    def margin(self):
        return safe_div(self.gp, self.net)

    @property
    def rep_cost(self):
        return self.salaries + self.iqama + self.insurance + self.other

    @property
    def contribution(self):
        return self.gp - self.rep_cost

    @property
    def roi(self):
        return safe_div(self.gp, self.rep_cost)

    @property
    def customer_count(self):
        """Customers who bought in the period: from the customers-by-rep file, else the invoices' customers."""
        n = sum(1 for v in self.customers.values() if v[1] > 0.5)
        return n or len(self.inv_customers)

    @property
    def inv_count(self):
        return sum(v[0] for v in self.inv.values())

    @property
    def inv_value(self):
        return sum(v[1] for v in self.inv.values())

    @property
    def avg_invoice(self):
        return safe_div(self.inv_value, self.inv_count)

    @property
    def coll_rate(self):
        if self.closing is None:
            return None
        return safe_div(self.collected, self.collected + self.closing)

    @property
    def overdue_share(self):
        return safe_div(self.overdue, self.closing) if self.closing else None

    @property
    def grade(self):
        return grade(self.score)


class Evaluation:
    """The evaluation of every rep for the months (consecutive, oldest first)."""

    def __init__(self, db, months):
        self.db, self.months = db, list(months)
        self.n = len(self.months)
        self.first, self.last = self.months[0], self.months[-1]
        self.notes = []
        s = db.setting_float
        self.w = {k: s(key) for k, _, key in CRITERIA}
        self.cap, self.roi_cap = s("rep_cap") or 1.0, s("rep_roi_cap") or 1.5
        self.iqama_y, self.ins_y = s("rep_iqama"), s("rep_insurance")
        self.prefix = str(db.setting("rep_cust_prefix") or "114").strip()
        self.reps = {}
        self._load_master()
        self._load_sales()
        self._load_invoices()
        self._load_commissions()
        self._load_collections()
        self._costs()
        self._score()

    # ---------------- helpers
    def rep(self, code, name=""):
        if code not in self.reps:
            self.reps[code] = RepRow(code, name or code)
        r = self.reps[code]
        if name and r.name == code:
            r.name = name
        return r

    def rep_key(self, value):
        """A rep written as '4002-name', a code or a name → the rep code ('' if unknown)."""
        code, name = D.split_rep(value)
        if code:
            return code
        s = str(value or "").strip()
        if s.isdigit() and s in self.reps:
            return s
        n = D.norm_name(name)
        if not n:
            return ""
        exact = [c for c, r in self.reps.items() if D.norm_name(r.name) == n]
        if exact:
            return exact[0]
        part = [c for c, r in self.reps.items() if n in D.norm_name(r.name) or D.norm_name(r.name) in n]
        return part[0] if len(part) == 1 else ""

    # ---------------- data
    def _load_master(self):
        for code, m in self.db.reps().items():
            r = self.rep(code, m["name"])
            r.nationality = m["nationality"] or "مقيم"
            r.salary_m, r.target_m, r.other_m = m["salary"] or 0.0, m["target"] or 0.0, m["other"] or 0.0
            r.active = 1 if m["active"] in (None, "", 1, "1") else 0

    def _load_sales(self):
        self.has_sales = False
        self.sales_kind = None
        self.cust_owner = {}                      # customer number → rep code (biggest sales in all uploads)
        self.name_reps = defaultdict(set)        # customer name → rep codes (for invoices)
        all_c = self.db.rep_sales("customers")
        best = {}
        for r in all_c:
            self.rep(r["rep"], r["rep_name"])
            self.name_reps[D.norm_name(r["name"])].add(r["rep"])
            k = r["key"]
            if r["net"] > best.get(k, (None, -1e18))[1]:
                best[k] = (r["rep"], r["net"])
        self.cust_owner = {k: v[0] for k, v in best.items()}
        for kind in ("items", "customers"):
            rows, covered, outside = pick_blocks(self.db.rep_sales(kind), self.months)
            label = "الأصناف بالمندوب" if kind == "items" else "العملاء بالمندوب"
            for f in outside:
                self.notes.append(f"⚠ ملف {label} ({range_label(months_between(*f))}) يتعدى حدود الفترة فلم يدخل.")
            if rows and len(covered) < self.n:
                miss = [m for m in self.months if m not in covered]
                self.notes.append(f"⚠ ملف {label} لا يغطي: {'، '.join(range_label([m]) for m in miss)}.")
            for x in rows:
                r = self.rep(x["rep"], x["rep_name"])
                target = r.items if kind == "items" else r.customers
                t = target.setdefault(x["key"], [x["name"], 0.0, 0.0])
                t[1] += x["net"] or 0.0
                t[2] += x["cost"] or 0.0
            if rows and not self.has_sales:
                self.has_sales, self.sales_kind = True, kind
        src = "items" if any(r.items for r in self.reps.values()) else "customers"
        for r in self.reps.values():
            data = r.items if src == "items" else r.customers
            r.net = sum(v[1] for v in data.values())
            r.cost_goods = sum(v[2] for v in data.values())
        if not self.has_sales:
            self.notes.append("⚠ لا يوجد ملف مبيعات بالمندوب (الأصناف أو العملاء) للفترة.")

    def _load_invoices(self):
        inv = self.db.invoices(self.months)
        self.inv_total = len(inv)
        self.inv_unlinked = [0, 0.0]
        if not inv:
            return
        # branch (first 7 digits of the invoice number) → reps seen with it, from invoices linked by name alone
        by_prefix = defaultdict(lambda: defaultdict(int))
        cands = []
        for x in inv:
            c = self.name_reps.get(D.norm_name(x["cust_name"]), set())
            cands.append(c)
            if len(c) == 1:
                by_prefix[(x["inv_no"] or "")[:7]][next(iter(c))] += 1
        for x, c in zip(inv, cands):
            pre = by_prefix.get((x["inv_no"] or "")[:7], {})
            code = ""
            if len(c) == 1:
                code = next(iter(c))
            elif len(c) > 1:
                code = max(c, key=lambda k: pre.get(k, 0))
            elif pre:
                top, n = max(pre.items(), key=lambda kv: kv[1])
                if n >= 0.9 * sum(pre.values()):
                    code = top
            if not code:
                self.inv_unlinked[0] += 1
                self.inv_unlinked[1] += x["net"] or 0.0
                continue
            r = self.rep(code)
            t = r.inv[x["itype"] or "غير محدد"]
            t[0] += 1
            t[1] += x["net"] or 0.0
            r.inv_customers.add(D.norm_name(x["cust_name"]))
        if self.inv_unlinked[0]:
            self.notes.append(f"فواتير لم تُربط بمندوب: {self.inv_unlinked[0]} فاتورة بقيمة {self.inv_unlinked[1]:,.0f} "
                              "(اسم العميل غير موجود في ملف العملاء بالمندوب).")

    def _load_commissions(self):
        com = self.db.commissions()
        for m in self.months:
            for code, a in com.get(m, {}).items():
                self.rep(code).commission += a or 0.0

    def _owner(self, cust_no, aging_owner):
        return aging_owner.get(cust_no) or self.master_owner.get(cust_no) or self.cust_owner.get(cust_no) or ""

    def _aging_map(self, period):
        rows = self.db.aging("customers", period) if period in self.aging_periods else []
        return {str(r.get("no") or "").strip(): r for r in rows if r.get("no")}

    def _load_collections(self):
        self.aging_periods = set(self.db.aging_periods("customers"))
        self.has_closing = self.last in self.aging_periods
        self.has_opening = month_add(self.first, -1) in self.aging_periods
        end = self._aging_map(self.last)
        opening = self._aging_map(month_add(self.first, -1))
        aging_owner = {no: self.rep_key(r.get("rep")) for no, r in end.items()}
        aging_owner.update({no: self.rep_key(r.get("rep")) for no, r in opening.items() if no not in aging_owner})
        self.master_owner = {k: self.rep_key(v.get("rep")) for k, v in self.db.customer_master().items() if v.get("rep")}
        rec = self.db.receipts(self.months)
        self.has_receipts = bool(rec)
        self.excluded = defaultdict(lambda: [0, 0.0])     # account → [count, amount] (not customer collections)
        self.unlinked = []                                # customer receipts whose customer has no rep
        self.cust_paid = defaultdict(float)
        for x in rec:
            acct, cust = x["acct"] or "", (x["analytic"] or "").strip()
            if not acct.startswith(self.prefix) or not cust:
                e = self.excluded[f"{acct} {x['acct_name']}".strip()]
                e[0] += 1
                e[1] += x["amount"] or 0.0
                continue
            self.cust_paid[cust] += x["amount"] or 0.0
            code = self._owner(cust, aging_owner)
            if code:
                self.rep(code).collected += x["amount"] or 0.0
            else:
                self.unlinked.append(x)
        self.collected_total = sum(self.cust_paid.values())
        if self.has_closing:
            for no, a in end.items():
                code = aging_owner.get(no) or self._owner(no, {})
                if not code:
                    continue
                r = self.rep(code)
                r.closing = (r.closing or 0.0) + AG.customer_total(a)
                r.overdue = (r.overdue or 0.0) + AG.customer_overdue(a)
            for r in self.reps.values():
                if r.closing is None and r.collected:
                    r.closing, r.overdue = 0.0, 0.0
        if self.has_opening:
            for no, a in opening.items():
                code = aging_owner.get(no) or self._owner(no, {})
                if code:
                    r = self.rep(code)
                    r.opening = (r.opening or 0.0) + AG.customer_total(a)
        self.end_aging, self.open_aging = end, opening
        if self.has_receipts and not self.has_closing:
            self.notes.append(f"⚠ معيار التحصيل لم يُحسب: ارفع أعمار العملاء لشهر {range_label([self.last])} "
                              "من «البيانات الشهرية» (رصيد العملاء آخر الفترة).")
        elif not self.has_receipts:
            self.notes.append("⚠ معيار التحصيل لم يُحسب: لا توجد سندات قبض للفترة.")

    def _costs(self):
        n = self.n
        for r in self.reps.values():
            r.salaries = r.salary_m * n
            r.iqama = 0.0 if "سعود" in (r.nationality or "") else self.iqama_y / 12 * n
            r.insurance = self.ins_y / 12 * n
            r.other = r.other_m * n

    # ---------------- score
    def evaluated(self):
        return [r for r in self.reps.values() if r.active and (r.net or r.target_m)]

    def _score(self):
        ev = self.evaluated()
        net = sum(r.net for r in ev)
        gp = sum(r.gp for r in ev)
        cost = sum(r.rep_cost for r in ev)
        self.company_margin = safe_div(gp, net)
        self.company_roi = safe_div(gp, cost)
        with_bal = [r for r in ev if r.coll_rate is not None]
        coll = sum(r.collected for r in with_bal)
        self.company_coll = safe_div(coll, coll + sum(r.closing for r in with_bal)) if with_bal else None
        use_coll = self.has_closing and self.has_receipts and self.company_coll
        cap, rc = self.cap, self.roi_cap
        for r in ev:
            if not r.target_m:
                continue
            target = r.target_m * self.n
            vals = {"sales": safe_div(r.net, target),
                    "profit": safe_div(r.gp, target * (self.company_margin or 0)),
                    "coll": safe_div(r.coll_rate, self.company_coll) if use_coll and r.coll_rate is not None else None,
                    "roi": safe_div(r.roi, self.company_roi),
                    "margin": safe_div(r.margin, self.company_margin)}
            got = wsum = 0.0
            for k, _, _ in CRITERIA:
                if k == "coll" and not use_coll:
                    continue
                lim = rc if k == "roi" else cap
                v = max(0.0, min(vals[k] or 0.0, lim)) / lim
                r.parts[k] = 100 * self.w[k] * v
                got += r.parts[k]
                wsum += self.w[k]
            if wsum:
                r.parts = {k: v / wsum for k, v in r.parts.items()}
            r.score = round(got / wsum, 1) if wsum else None
        self.use_coll = bool(use_coll)
        rated = sorted([r for r in ev if r.score is not None], key=lambda r: (-r.score, -r.contribution))
        for i, r in enumerate(rated, 1):
            r.rank = i

    def ordered(self):
        """Evaluated reps: ranked first, then the ones without a target."""
        ev = self.evaluated()
        return sorted(ev, key=lambda r: (r.rank is None, r.rank or 0, -r.net))

    def totals(self):
        ev = self.evaluated()
        t = {"net": sum(r.net for r in ev), "gp": sum(r.gp for r in ev), "cost": sum(r.rep_cost for r in ev),
             "commission": sum(r.commission for r in ev), "collected": sum(r.collected for r in ev),
             "closing": sum(r.closing or 0 for r in ev), "overdue": sum(r.overdue or 0 for r in ev),
             "target": sum(r.target_m * self.n for r in ev)}
        t["margin"] = safe_div(t["gp"], t["net"])
        t["contribution"] = t["gp"] - t["cost"]
        t["ach"] = safe_div(sum(r.net for r in ev if r.target_m), t["target"])
        t["coll_rate"] = self.company_coll
        return t

    def weights_used(self):
        """(criterion, label, weight) of the criteria used, weights scaled to sum 1 (collection may be missing)."""
        used = [(k, label, self.w[k]) for k, label, _ in CRITERIA if k != "coll" or self.use_coll]
        total = sum(w for _, _, w in used) or 1
        return [(k, label, w / total) for k, label, w in used]

    # ---------------- customers' balance check
    def reconciliation(self):
        """Per customer: opening + credit invoices − receipts against the closing balance (needs both agings).

        Invoices carry the customer name only, so they are matched to the aging by name."""
        if not (self.has_opening and self.has_closing):
            return None
        inv = self.db.invoices(self.months)
        credit = defaultdict(float)
        for x in inv:
            if "نقد" not in (x["itype"] or ""):
                credit[D.norm_name(x["cust_name"])] += x["net"] or 0.0
        out = []
        for no in set(self.end_aging) | set(self.open_aging):
            a, o = self.end_aging.get(no), self.open_aging.get(no)
            name = (a or o).get("name") or ""
            op = AG.customer_total(o) if o else 0.0
            cl = AG.customer_total(a) if a else 0.0
            sales = credit.get(D.norm_name(name), 0.0)
            paid = self.cust_paid.get(no, 0.0)
            diff = cl - (op + sales - paid)
            code = self.rep_key((a or o).get("rep")) or self._owner(no, {})
            out.append({"no": no, "name": name, "rep": code, "opening": op, "sales": sales, "paid": paid,
                        "closing": cl, "diff": diff})
        return out


def evaluate(db, months):
    return Evaluation(db, months)


def available_months(db):
    """Months with any rep data (sales files, invoices, receipts, commissions)."""
    ms = set(db.monthly_counts("invoices")) | set(db.monthly_counts("receipts")) | set(db.commissions())
    for _, a, b, _, _ in db.rep_sales_files():
        ms |= set(months_between(a, b))
    return sorted(ms)


# ================================================================== reports
def _sub(ev):
    return f"{range_label(ev.months)} — {ev.n} شهر"


def _notes(ev):
    return [Para(t, "warn" if t.startswith("⚠") else "sub") for t in ev.notes]


def rpt_summary(ev):
    t = ev.totals()
    blocks = [Table(["المؤشر", "القيمة"], [
        Row("صافي المبيعات", [t["net"]]), Row("مجمل الربح", [t["gp"]]), Row("هامش الشركة", [t["margin"]], fmt="%"),
        Row("تحقيق التارجت", [t["ach"]], fmt="%"), Row("تكلفة المناديب (بدون العمولة)", [t["cost"]]),
        Row("العمولات", [t["commission"]]), Row("صافي المساهمة", [t["contribution"]]),
        Row("التحصيل", [t["collected"]]), Row("نسبة التحصيل", [t["coll_rate"]], fmt="%"),
        Row("رصيد العملاء آخر الفترة", [t["closing"] if ev.has_closing else None]),
        Row("المتأخر", [t["overdue"] if ev.has_closing else None])], title="الإجمالي")]
    cols = ["المندوب", "الترتيب", "الدرجة", "التقدير", "صافي المبيعات", "تحقيق التارجت", "مجمل الربح", "الهامش",
            "تكلفة المندوب", "العمولة", "صافي المساهمة", "العائد لكل ريال", "نسبة التحصيل", "المتأخر %",
            "عدد العملاء", "عدد الفواتير", "متوسط الفاتورة"]
    fm = ["d", "x", "t", "n", "%", "n", "%", "n", "n", "n", "x", "%", "%", "d", "d", "n"]
    rows = []
    for r in ev.ordered():
        st = [None] * len(fm)
        st[2] = {"ممتاز": "good", "جيد جداً": "good", "ضعيف": "bad", "مقبول": "warn"}.get(r.grade)
        if r.contribution < 0:
            st[9] = "bad"
        rows.append(Row(f"{r.code} {r.name}", [
            r.rank, r.score, r.grade, r.net, safe_div(r.net, r.target_m * ev.n) if r.target_m else None, r.gp, r.margin,
            r.rep_cost, r.commission, r.contribution, r.roi, r.coll_rate, r.overdue_share, r.customer_count or None,
            r.inv_count or None, r.avg_invoice], styles=st))
    rows.append(Row("الإجمالي", [None, None, "", t["net"], t["ach"], t["gp"], t["margin"], t["cost"], t["commission"],
                                t["contribution"], safe_div(t["gp"], t["cost"]), t["coll_rate"],
                                safe_div(t["overdue"], t["closing"]) if ev.has_closing else None,
                                sum(r.customer_count for r in ev.evaluated()) or None,
                                sum(r.inv_count for r in ev.evaluated()) or None,
                                safe_div(sum(r.inv_value for r in ev.evaluated()),
                                         sum(r.inv_count for r in ev.evaluated()))], "tot"))
    blocks.append(Table(cols, rows, fm, title="ترتيب المناديب"))
    w = "، ".join(f"{label} {wt * 100:.0f}%" for _, label, wt in ev.weights_used())
    blocks.append(Para(f"الأوزان: {w}. كل معيار يُقاس على تارجت المندوب أو متوسط الشركة بقيمته الفعلية، والدرجة كاملة "
                       f"عند {ev.cap * 100:.0f}% (العائد عند {ev.roi_cap:.1f} ضعف المتوسط). تكلفة المندوب = الراتب + الإقامة "
                       "+ التأمين + تكاليف أخرى، والعمولة تظهر ولا تدخل في التكلفة."))
    blocks += _notes(ev)
    return Report("rep_summary", "تقييم أداء المناديب", _sub(ev), blocks)


def _top(d, n, key=lambda v: v[1] - v[2], reverse=True):
    return sorted(d.items(), key=lambda kv: key(kv[1]), reverse=reverse)[:n]


def rpt_rep(ev, code):
    r = ev.reps[code]
    blocks = []
    rank = f"#{r.rank} من {sum(1 for x in ev.evaluated() if x.rank)}" if r.rank else "—"
    head = [Row("الدرجة", [r.score if r.score is not None else NOT_RATED], fmt="x"), Row("التقدير", [r.grade]),
            Row("الترتيب", [rank]), Row("الجنسية", [r.nationality]),
            Row("عدد العملاء", [f"{r.customer_count:,}" if r.customer_count else "—"]),
            Row("عدد الفواتير", [f"{r.inv_count:,}" if r.inv_count else "—"]),
            Row("متوسط الفاتورة", [f"{r.avg_invoice:,.0f}" if r.avg_invoice else "—"])]
    blocks.append(Table(["التقييم", ""], head, ["t"], title=f"{r.code} — {r.name}"))
    if r.parts:
        rows = []
        for k, label, wt in ev.weights_used():
            rows.append(Row(label, [r.parts.get(k, 0.0), wt * 100, safe_div(r.parts.get(k, 0.0), wt * 100)]))
        rows.append(Row("الدرجة", [r.score, 100, safe_div(r.score, 100)], "tot"))
        blocks.append(Table(["المعيار", "الدرجة", "من", "النسبة"], rows, ["x", "d", "%"], title="تفصيل الدرجة"))
    target = r.target_m * ev.n
    perf = [Row("صافي المبيعات", [r.net, target or None, safe_div(r.net, target) if target else None]),
            Row("مجمل الربح", [r.gp, target * (ev.company_margin or 0) or None,
                               safe_div(r.gp, target * (ev.company_margin or 0)) if target else None]),
            Row("هامش الربح", [r.margin, ev.company_margin, safe_div(r.margin, ev.company_margin)], fmt="%"),
            Row("العائد لكل ريال تكلفة", [r.roi, ev.company_roi, safe_div(r.roi, ev.company_roi)], fmt="x"),
            Row("نسبة التحصيل", [r.coll_rate, ev.company_coll, safe_div(r.coll_rate, ev.company_coll)], fmt="%")]
    blocks.append(Table(["المؤشر", "الفعلي", "المطلوب / متوسط الشركة", "التحقيق"], perf, ["n", "n", "%"],
                        title="الأداء مقابل المطلوب"))
    cost = [Row("الرواتب", [r.salaries]), Row("الإقامة", [r.iqama]), Row("التأمين الصحي", [r.insurance]),
            Row("تكاليف أخرى", [r.other]), Row("إجمالي تكلفة المندوب", [r.rep_cost], "tot"),
            Row("العمولة (لا تدخل في التكلفة)", [r.commission], "note"),
            Row("صافي المساهمة = مجمل الربح − التكلفة", [r.contribution], "tot")]
    blocks.append(Table(["التكلفة", "المبلغ"], cost, title="التكلفة والمساهمة"))
    if ev.has_receipts or r.closing is not None:
        c = [Row("رصيد العملاء أول الفترة", [r.opening]), Row("التحصيل في الفترة", [r.collected]),
             Row("رصيد العملاء آخر الفترة", [r.closing]), Row("منه متأخر", [r.overdue]),
             Row("نسبة المتأخر", [r.overdue_share], fmt="%"),
             Row("نسبة التحصيل = التحصيل ÷ (التحصيل + الرصيد)", [r.coll_rate], fmt="%")]
        blocks.append(Table(["التحصيل", "المبلغ"], c, title="التحصيل وأرصدة العملاء"))
    if r.inv:
        rows = [Row(t, [v[0], v[1], safe_div(v[1], v[0]), safe_div(v[1], r.inv_value)])
                for t, v in sorted(r.inv.items(), key=lambda kv: -kv[1][1])]
        rows.append(Row("الإجمالي", [r.inv_count, r.inv_value, r.avg_invoice, 1.0], "tot"))
        blocks.append(Table(["نوع الفاتورة", "العدد", "القيمة", "متوسط الفاتورة", "% من القيمة"], rows,
                            ["d", "n", "n", "%"], title=f"الفواتير — {len(r.inv_customers)} عميل"))
    for data, title, label in ((r.items, "الأصناف", "الصنف"), (r.customers, "العملاء", "العميل")):
        if not data:
            continue
        tot_gp = sum(v[1] - v[2] for v in data.values())
        tot_net = sum(v[1] for v in data.values())
        rows = [Row(f"{k} {v[0]}", [v[1], v[1] - v[2], safe_div(v[1] - v[2], v[1]), safe_div(v[1] - v[2], tot_gp)])
                for k, v in _top(data, 10)]
        top10 = sum(v[1] - v[2] for _, v in _top(data, 10))
        rows.append(Row(f"عدد {title}: {len(data)} — حصة أعلى 10 من الربح", [None, top10, None,
                                                                          safe_div(top10, tot_gp)], "tot"))
        blocks.append(Table([label, "صافي المبيعات", "مجمل الربح", "الهامش", "% من ربحه"], rows, ["n", "n", "%", "%"],
                            title=f"أعلى 10 {title} ربحاً"))
        loss = [(k, v) for k, v in data.items() if v[1] - v[2] < -0.5]
        if loss:
            rows = [Row(f"{k} {v[0]}", [v[1], v[2], v[1] - v[2]]) for k, v in sorted(loss, key=lambda kv: kv[1][1] - kv[1][2])[:10]]
            blocks.append(Table([label, "المبيعات", "التكلفة", "الخسارة"], rows,
                                title=f"{title} بيعت بأقل من تكلفتها ({len(loss)})"))
        if tot_net and label == "العميل":
            blocks.append(Para(f"متوسط المبيعات للعميل: {tot_net / len(data):,.0f}"))
    return Report(f"rep_{code}", f"تقرير أداء المندوب: {r.name}", _sub(ev), blocks + _notes(ev))


def rpt_collections(ev):
    blocks = []
    rows = []
    for r in ev.ordered():
        rows.append(Row(f"{r.code} {r.name}", [r.opening, r.collected, r.closing, r.overdue, r.overdue_share, r.coll_rate]))
    t = ev.totals()
    rows.append(Row("الإجمالي", [None, t["collected"], t["closing"] if ev.has_closing else None,
                                t["overdue"] if ev.has_closing else None,
                                safe_div(t["overdue"], t["closing"]) if ev.has_closing else None, t["coll_rate"]], "tot"))
    blocks.append(Table(["المندوب", "رصيد أول الفترة", "التحصيل", "رصيد آخر الفترة", "المتأخر", "المتأخر %",
                         "نسبة التحصيل"], rows, ["n", "n", "n", "n", "%", "%"], title="التحصيل لكل مندوب"))
    blocks.append(Para(f"تحصيل العملاء = سندات القبض على حسابات تبدأ بـ {ev.prefix} ولها رقم عميل (الحساب التحليلي): "
                       f"{ev.collected_total:,.0f}. العميل يتبع المندوب المسجّل عليه في أعمار العملاء، ثم «بيانات العملاء»، "
                       "ثم المندوب الأكبر مبيعات له."))
    if ev.excluded:
        rows = [Row(k, [v[0], v[1]]) for k, v in sorted(ev.excluded.items(), key=lambda kv: -kv[1][1])]
        blocks.append(Table(["الحساب", "عدد السندات", "المبلغ"], rows, ["d", "n"],
                            title="سندات ليست تحصيل عملاء (توريد صناديق المناديب، تحويلات بين البنوك ...)"))
    if ev.unlinked:
        g = defaultdict(lambda: ["", 0, 0.0])
        for x in ev.unlinked:
            e = g[x["analytic"]]
            e[0], e[1], e[2] = x["acct_name"], e[1] + 1, e[2] + (x["amount"] or 0)
        rows = [Row(f"{k} {v[0]}", [v[1], v[2]]) for k, v in sorted(g.items(), key=lambda kv: -kv[1][2])]
        blocks.append(Table(["العميل", "عدد السندات", "المبلغ"], rows, ["d", "n"],
                            title="تحصيل لعملاء بدون مندوب (أضفهم في «بيانات العملاء» أو أعمار العملاء)"))
    rec = ev.reconciliation()
    if rec is None:
        blocks.append(Para("مطابقة أرصدة العملاء تحتاج أعمار العملاء لآخر الشهر السابق للفترة ولآخر شهر فيها.", "warn"))
    else:
        bad = [x for x in rec if abs(x["diff"]) >= 1]
        blocks.append(Para(f"مطابقة أرصدة العملاء: {len(rec) - len(bad)} عميل مطابق من {len(rec)}. "
                           "الرصيد المتوقع = أول الفترة + الفواتير الآجلة (بالاسم) − سندات القبض (برقم العميل). "
                           "الفرق غالبًا مرتجعات أو خصومات أو قيود يدوية أو اسم مختلف في الفواتير.",
                           "good" if not bad else "warn"))
        if bad:
            rows = [Row(f"{x['no']} {x['name']}", [ev.reps[x["rep"]].name if x["rep"] in ev.reps else UNLINKED,
                                                    x["opening"], x["sales"], x["paid"], x["closing"], x["diff"]])
                    for x in sorted(bad, key=lambda x: -abs(x["diff"]))[:60]]
            blocks.append(Table(["العميل", "المندوب", "أول الفترة", "فواتير آجلة", "سندات", "آخر الفترة", "الفرق"], rows,
                                ["t", "n", "n", "n", "n", "n"], title="أكبر الفروق (أول 60)"))
    return Report("rep_collections", "التحصيل ومطابقة أرصدة العملاء", _sub(ev), blocks + _notes(ev))


def rpt_invoices(ev):
    types = sorted({t for r in ev.reps.values() for t in r.inv})
    if not types:
        return Report("rep_invoices", "فواتير المناديب", _sub(ev),
                      [Para("لا توجد فواتير للفترة — ارفع تقرير الفواتير من صفحة «تقييم المناديب» ← «البيانات».", "warn")])
    cols = ["المندوب"] + [f"{t} (عدد)" for t in types] + ["عدد الفواتير", "القيمة", "متوسط الفاتورة", "عدد العملاء"]
    fm = ["d"] * len(types) + ["d", "n", "n", "d"]
    rows = []
    for r in sorted(ev.reps.values(), key=lambda r: -r.inv_value):
        if not r.inv:
            continue
        rows.append(Row(f"{r.code} {r.name}", [r.inv[t][0] if t in r.inv else 0 for t in types] +
                        [r.inv_count, r.inv_value, r.avg_invoice, len(r.inv_customers)]))
    blocks = [Table(cols, rows, fm, title="عدد الفواتير ونوعها ومتوسط الفاتورة")]
    if ev.inv_unlinked[0]:
        blocks.append(Para(f"فواتير بدون مندوب: {ev.inv_unlinked[0]} بقيمة {ev.inv_unlinked[1]:,.0f}.", "warn"))
    blocks.append(Para("الفاتورة تُربط بالمندوب باسم العميل من ملف العملاء بالمندوب؛ لو العميل عند أكثر من مندوب يُختار "
                       "المندوب الأكثر فواتير في نفس الفرع (أول 7 أرقام من رقم الفاتورة)."))
    return Report("rep_invoices", "فواتير المناديب", _sub(ev), blocks)
