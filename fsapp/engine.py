"""Builds the financial statements and ratios from classified accounts.

Sign convention: net = debit - credit. Assets are shown as +net, liabilities,
equity and income as -net. The income statement uses the period movement; the
balance sheet uses closing balances (current) and opening balances (comparative).
"""
from dataclasses import dataclass, field

from .categories import (BY_KEY, CA, NCA, CL, NCL, EQ, REV, EXP, EXCL, CATEGORIES,
                         CF_CASH, CF_OP_WC, CF_OP_NONCASH, CF_INV, CF_FIN, keys_in)


@dataclass
class Line:
    key: str            # category key or a computed-line key
    amount: float
    prior: float | None = None
    kind: str = "item"  # item | subtotal | total | header
    accounts: list = field(default_factory=list)


@dataclass
class Statements:
    bs: dict
    is_: dict
    cf: dict
    equity: dict
    ratios: list
    checks: dict
    accounts: list


def _sum(accounts, keys, attr):
    keys = set(keys)
    return sum(getattr(a, attr) for a in accounts if a.category in keys)


def build(accounts, months=12):
    acc = [a for a in accounts if a.category and BY_KEY[a.category].group != EXCL]

    def bal(key, attr, sign):
        return sign * _sum(acc, [key], attr)

    def members(key):
        return [a for a in acc if a.category == key]

    # ---------- Income statement (period movement) ----------
    def isv(key):  # positive for income, positive for expense (shown as deductions)
        g = BY_KEY[key].group
        return -_sum(acc, [key], "mov_net") if g == REV else _sum(acc, [key], "mov_net")

    rev = isv("revenue")
    cogs = isv("cogs")
    gross = rev - cogs
    selling, admin, dep_exp = isv("selling_exp"), isv("admin_exp"), isv("depreciation_exp")
    op_profit = gross - selling - admin - dep_exp
    other_inc, other_exp, fin_cost = isv("other_income"), isv("other_exp"), isv("finance_cost")
    pbt = op_profit + other_inc - other_exp - fin_cost
    tax = isv("tax_exp")
    net_income = pbt - tax
    # Equivalent check: net income must equal minus the net movement of all P&L accounts
    ni_check = -_sum(acc, keys_in(REV, EXP), "mov_net")

    is_lines = [
        Line("revenue", rev, accounts=members("revenue")),
        Line("cogs", -cogs, accounts=members("cogs")),
        Line("gross_profit", gross, kind="subtotal"),
        Line("selling_exp", -selling, accounts=members("selling_exp")),
        Line("admin_exp", -admin, accounts=members("admin_exp")),
        Line("depreciation_exp", -dep_exp, accounts=members("depreciation_exp")),
        Line("operating_profit", op_profit, kind="subtotal"),
        Line("other_income", other_inc, accounts=members("other_income")),
        Line("other_exp", -other_exp, accounts=members("other_exp")),
        Line("finance_cost", -fin_cost, accounts=members("finance_cost")),
        Line("profit_before_tax", pbt, kind="subtotal"),
        Line("tax_exp", -tax, accounts=members("tax_exp")),
        Line("net_income", net_income, kind="total"),
    ]

    # ---------- Balance sheet ----------
    # P&L balances carried in the opening column (not closed yet) belong to retained earnings.
    pl_open = -_sum(acc, keys_in(REV, EXP), "open_net")

    def group_lines(group, sign):
        lines = []
        for c in CATEGORIES:
            if c.group != group:
                continue
            cur, pri = bal(c.key, "close_net", sign), bal(c.key, "open_net", sign)
            if c.key == "retained_earnings":
                cur += pl_open
                pri += pl_open
            if members(c.key) or abs(cur) > 1e-9 or abs(pri) > 1e-9:
                lines.append(Line(c.key, cur, pri, accounts=members(c.key)))
        return lines

    def tot(lines):
        return sum(l.amount for l in lines), sum(l.prior or 0 for l in lines)

    ca_l, nca_l = group_lines(CA, 1), group_lines(NCA, 1)
    cl_l, ncl_l, eq_l = group_lines(CL, -1), group_lines(NCL, -1), group_lines(EQ, -1)
    if not any(l.key == "retained_earnings" for l in eq_l) and abs(pl_open) > 1e-9:
        eq_l.append(Line("retained_earnings", pl_open, pl_open))
    eq_l.append(Line("net_income_period", net_income, 0.0))

    ca_t, nca_t = tot(ca_l), tot(nca_l)
    cl_t, ncl_t, eq_t = tot(cl_l), tot(ncl_l), tot(eq_l)
    assets = (ca_t[0] + nca_t[0], ca_t[1] + nca_t[1])
    liabs = (cl_t[0] + ncl_t[0], cl_t[1] + ncl_t[1])
    le = (liabs[0] + eq_t[0], liabs[1] + eq_t[1])

    bs = {
        "CA": ca_l, "CA_total": ca_t, "NCA": nca_l, "NCA_total": nca_t, "assets": assets,
        "CL": cl_l, "CL_total": cl_t, "NCL": ncl_l, "NCL_total": ncl_t, "liabilities": liabs,
        "EQ": eq_l, "EQ_total": eq_t, "liabilities_equity": le,
    }

    # ---------- Cash flow statement (indirect method) ----------
    def delta(key):  # change in net balance (debit positive)
        return _sum(acc, [key], "close_net") - _sum(acc, [key], "open_net")

    def cf_lines(treatment):
        out = []
        for c in CATEGORIES:
            if c.cf != treatment or c.key == "reserves":
                continue
            d = delta(c.key)
            mem = members(c.key)
            if c.key == "retained_earnings":
                # Transfers between reserves and retained earnings are not cash movements.
                d += delta("reserves")
                mem = mem + members("reserves")
            if mem and abs(d) > 1e-9:
                out.append(Line("cf_" + c.key, -d, accounts=mem))
        return out

    op_adj = cf_lines(CF_OP_NONCASH)
    op_wc = cf_lines(CF_OP_WC)
    cfo = net_income + sum(l.amount for l in op_adj + op_wc)
    inv = cf_lines(CF_INV)
    cfi = sum(l.amount for l in inv)
    fin = cf_lines(CF_FIN)
    cff = sum(l.amount for l in fin)
    net_change = cfo + cfi + cff
    cash_open = _sum(acc, ["cash"], "open_net")
    cash_close = _sum(acc, ["cash"], "close_net")
    capex = sum(-l.amount for l in inv if l.key in ("cf_ppe", "cf_cwip", "cf_intangibles"))
    cf = {
        "net_income": net_income, "op_adj": op_adj, "op_wc": op_wc, "cfo": cfo,
        "inv": inv, "cfi": cfi, "fin": fin, "cff": cff, "net_change": net_change,
        "cash_open": cash_open, "cash_close": cash_close,
        "cash_close_calc": cash_open + net_change, "capex": capex,
    }

    # ---------- Statement of changes in equity ----------
    comps = ["capital", "reserves", "retained_earnings", "drawings"]
    eq_rows = {}
    for k in comps:
        o, c = -_sum(acc, [k], "open_net"), -_sum(acc, [k], "close_net")
        if k == "retained_earnings":
            o += pl_open
            c += pl_open
        eq_rows[k] = {"open": o, "ni": 0.0, "other": c - o, "close": c}
    eq_rows["retained_earnings"]["ni"] = net_income
    eq_rows["retained_earnings"]["close"] += net_income
    equity = {"cols": comps, "rows": eq_rows}

    # ---------- Ratios ----------
    ratios = compute_ratios(locals_for_ratios(
        acc, bs, rev, cogs, gross, op_profit, net_income, fin_cost, dep_exp, pbt, cfo, capex, months))

    checks = {
        "bs_diff": assets[0] - le[0],
        "bs_diff_prior": assets[1] - le[1],
        "ni_diff": net_income - ni_check,
        "cash_diff": cash_open + net_change - cash_close,
    }
    is_ = {"lines": is_lines, "revenue": rev, "net_income": net_income}
    return Statements(bs, is_, cf, equity, ratios, checks, acc)


def locals_for_ratios(acc, bs, rev, cogs, gross, op_profit, net_income, fin_cost, dep_exp, pbt, cfo, capex, months):
    def cur_pri(key, sign=1):
        return sign * _sum(acc, [key], "close_net"), sign * _sum(acc, [key], "open_net")

    def avg(pair):
        c, p = pair
        return (c + p) / 2 if p else c

    debt_keys = ["st_loans", "current_ltd", "lt_loans"]
    debt = (-_sum(acc, debt_keys, "close_net"), -_sum(acc, debt_keys, "open_net"))
    if dep_exp == 0:
        dep_exp = max(0.0, -(_sum(acc, ["accum_dep"], "close_net") - _sum(acc, ["accum_dep"], "open_net")))
    return dict(
        months=months, rev=rev, cogs=cogs, gross=gross, op=op_profit, ni=net_income, fin=fin_cost,
        dep=dep_exp, pbt=pbt, cfo=cfo, capex=capex,
        ca=bs["CA_total"], cl=bs["CL_total"], assets=bs["assets"], liabs=bs["liabilities"],
        eq=bs["EQ_total"], cash=cur_pri("cash"), inv=cur_pri("inventory"),
        rec=cur_pri("receivables"), pay=cur_pri("payables", -1), sti=cur_pri("st_investments"),
        debt=debt, avg=avg,
    )


def _div(a, b):
    if b is None or abs(b) < 1e-9 or a is None:
        return None
    return a / b


# (key, group, format, higher_is_better, good_threshold, warn_threshold)
RATIO_DEFS = [
    ("current_ratio", "liquidity", "x", True, 1.5, 1.0),
    ("quick_ratio", "liquidity", "x", True, 1.0, 0.7),
    ("cash_ratio", "liquidity", "x", True, 0.5, 0.2),
    ("working_capital", "liquidity", "amount", True, 0.0, 0.0),
    ("gross_margin", "profitability", "%", True, 0.30, 0.15),
    ("operating_margin", "profitability", "%", True, 0.10, 0.03),
    ("ebitda_margin", "profitability", "%", True, 0.15, 0.05),
    ("net_margin", "profitability", "%", True, 0.08, 0.02),
    ("roa", "profitability", "%", True, 0.08, 0.03),
    ("roe", "profitability", "%", True, 0.15, 0.05),
    ("asset_turnover", "activity", "x", True, 1.0, 0.5),
    ("receivables_turnover", "activity", "x", True, 8.0, 4.0),
    ("dso", "activity", "days", False, 45, 90),
    ("inventory_turnover", "activity", "x", True, 6.0, 3.0),
    ("dio", "activity", "days", False, 60, 120),
    ("payables_turnover", "activity", "x", None, None, None),
    ("dpo", "activity", "days", None, None, None),
    ("ccc", "activity", "days", False, 60, 120),
    ("debt_to_equity", "leverage", "x", False, 1.0, 2.0),
    ("debt_ratio", "leverage", "%", False, 0.5, 0.7),
    ("equity_ratio", "leverage", "%", True, 0.5, 0.3),
    ("financial_debt_to_equity", "leverage", "x", False, 0.5, 1.5),
    ("interest_coverage", "leverage", "x", True, 3.0, 1.5),
    ("ocf_ratio", "cashflow", "x", True, 1.0, 0.5),
    ("cash_quality", "cashflow", "x", True, 1.0, 0.7),
    ("free_cash_flow", "cashflow", "amount", True, 0.0, 0.0),
    ("cash_debt_coverage", "cashflow", "x", True, 0.3, 0.1),
]


def compute_ratios(v):
    days = 365 * v["months"] / 12
    avg = v["avg"]
    ca, cl = v["ca"][0], v["cl"][0]
    quick_assets = v["cash"][0] + v["sti"][0] + v["rec"][0]
    total_debt = v["liabs"][0]
    eq = v["eq"][0]
    rec_t = _div(v["rev"], avg(v["rec"]))
    inv_t = _div(v["cogs"], avg(v["inv"]))
    pay_t = _div(v["cogs"], avg(v["pay"]))
    dso = _div(days, rec_t)
    dio = _div(days, inv_t)
    dpo = _div(days, pay_t)
    ccc = None
    if dso is not None or dio is not None:
        ccc = (dso or 0) + (dio or 0) - (dpo or 0)
    values = {
        "current_ratio": _div(ca, cl),
        "quick_ratio": _div(quick_assets, cl),
        "cash_ratio": _div(v["cash"][0] + v["sti"][0], cl),
        "working_capital": ca - cl,
        "gross_margin": _div(v["gross"], v["rev"]),
        "operating_margin": _div(v["op"], v["rev"]),
        "ebitda_margin": _div(v["op"] + v["dep"], v["rev"]),
        "net_margin": _div(v["ni"], v["rev"]),
        "roa": _div(v["ni"], avg(v["assets"])),
        "roe": _div(v["ni"], avg(v["eq"])) if avg(v["eq"]) > 0 else None,
        "asset_turnover": _div(v["rev"], avg(v["assets"])),
        "receivables_turnover": rec_t,
        "dso": dso,
        "inventory_turnover": inv_t,
        "dio": dio,
        "payables_turnover": pay_t,
        "dpo": dpo,
        "ccc": ccc,
        "debt_to_equity": _div(total_debt, eq) if eq > 0 else None,
        "debt_ratio": _div(total_debt, v["assets"][0]),
        "equity_ratio": _div(eq, v["assets"][0]),
        "financial_debt_to_equity": _div(v["debt"][0], eq) if eq > 0 else None,
        "interest_coverage": _div(v["op"], v["fin"]),
        "ocf_ratio": _div(v["cfo"], cl),
        "cash_quality": _div(v["cfo"], v["ni"]) if v["ni"] > 0 else None,
        "free_cash_flow": v["cfo"] - v["capex"],
        "cash_debt_coverage": _div(v["cfo"], total_debt),
    }
    out = []
    for key, group, fmt, hib, good, warn in RATIO_DEFS:
        val = values[key]
        out.append({"key": key, "group": group, "fmt": fmt, "value": val,
                    "status": _status(val, hib, good, warn)})
    return out


def _status(val, hib, good, warn):
    if val is None or hib is None:
        return "na" if val is None else "info"
    if hib:
        return "good" if val >= good else ("warn" if val >= warn else "bad")
    return "good" if val <= good else ("warn" if val <= warn else "bad")
