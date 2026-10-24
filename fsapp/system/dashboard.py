"""Dashboard figures: cards for the shown month, alerts, monthly chart series and the working-capital analysis.

Days are on a 30-day month: collection days use credit sales (net sales × credit ratio), inventory and
payment days use the cost of sales.
"""
from . import aging as AG
from .calc import MONTHS_AR, month_add, month_label, safe_div
from .defaults import BUCKET_NAMES


def iso(text):
    """Keep numbers like +10.8% or -1,272 in left-to-right order inside Arabic text."""
    return "\u2066" + text + "\u2069"


def _pct(a, b):
    if a is None or b is None or abs(b) < 1e-9:
        return None
    return (a - b) / abs(b)


def _days(balance, flow):
    d = safe_div(balance, flow)
    return None if d is None else d * 30


def month_figures(ctx, m):
    f = ctx.is_figures([m])
    b = ctx.bs_figures([m], 2)
    cf = ctx.cash_flow([m])
    sales_credit = f["net_sales"] * ctx.credit_ratio
    out = {
        "net_sales": f["net_sales"], "gross": f["gross"], "ni": f["ni"], "opex": f["admin"] + f["selling"],
        "cash": b["cash"], "rec": b["receivables"], "inv": b["inventory"], "pay": b["payables"],
        "st": b["debt_st"], "lt": b["debt_lt"], "cfo": cf["cfo"], "capex": cf["capex"],
        "fcf": cf["cfo"] - cf["capex"], "net_change": cf["net_change"], "buckets": cf["buckets"],
        "dso": _days(b["receivables"], sales_credit), "dio": _days(b["inventory"], f["cost_of_sales"]),
        "dpo": _days(b["payables"], f["cost_of_sales"]), "cost_of_sales": f["cost_of_sales"],
    }
    d = out
    out["ccc"] = None if None in (d["dso"], d["dio"], d["dpo"]) else d["dso"] + d["dio"] - d["dpo"]
    return out


def financing_story(fcf, st_change, cash_change):
    if fcf >= 0 and st_change < -0.5:
        return "فائض سدّد تسهيلات قصيرة"
    if fcf >= 0 and st_change > 0.5:
        return "فائض + سحب تسهيلات (زاد النقد)"
    if fcf >= 0:
        return "فائض زاد النقد"
    if st_change > 0.5:
        return "عجز مُوّل بالتسهيلات القصيرة"
    if cash_change < -0.5:
        return "عجز مُوّل من رصيد النقد"
    return "عجز مُوّل من مصادر أخرى (قروض/ملاك)"


def compute(ctx, end):
    year = ctx.year_months(end)
    entered = [m for m in year if m in ctx.tbs and m <= end]
    if end not in ctx.tbs:
        return None
    figs = {m: month_figures(ctx, m) for m in entered}
    cur = figs[end]
    prev_m = month_add(end, -1)
    prev = figs.get(prev_m) or (month_figures(ctx, prev_m) if prev_m in ctx.tbs else None)
    ytd = ctx.is_figures([end], ytd=True)
    first = entered[0]
    start_cash = ctx.bs_figures([first], 0)["cash"]
    ytd_cfo = sum(figs[m]["cfo"] for m in entered)
    ytd_fcf = sum(figs[m]["fcf"] for m in entered)
    ytd_ni = sum(figs[m]["ni"] for m in entered)
    st_change = cur["st"] - (ctx.bs_figures([end], 0)["debt_st"])
    lt_change = cur["lt"] - (ctx.bs_figures([end], 0)["debt_lt"])
    open_bs = ctx.bs_figures([end], 0)
    cash_conv = safe_div(ytd_cfo, ytd_ni) if ytd_ni > 0 else None

    def money(v):
        return "—" if v is None else iso(f"{v:,.0f}")

    def signed(v):
        return "—" if v is None else iso(f"{v:+,.0f}")

    def pct(v):
        return "—" if v is None else iso(f"{v:+.1%}")

    def p1(v):
        return iso(f"{v or 0:.1%}")

    cards = {
        "profit": [
            ("صافي المبيعات", cur["net_sales"], f"من بداية السنة: {money(ytd['net_sales'])}",
             f"مقابل الشهر السابق: {pct(_pct(cur['net_sales'], prev['net_sales'] if prev else None))}"),
            ("مجمل الربح", cur["gross"], f"الهامش: {p1(safe_div(cur['gross'], cur['net_sales']))}",
             f"من بداية السنة: {money(ytd['gross'])}  ({p1(safe_div(ytd['gross'], ytd['net_sales']))})"),
            ("صافي الربح", cur["ni"], f"الهامش: {p1(safe_div(cur['ni'], cur['net_sales']))}",
             f"من بداية السنة: {money(ytd['ni'])}  ({p1(safe_div(ytd['ni'], ytd['net_sales']))})"),
            ("المصروفات التشغيلية", cur["opex"], f"إلى المبيعات: {p1(safe_div(cur['opex'], cur['net_sales']))}",
             f"مقابل الشهر السابق: {pct(_pct(cur['opex'], prev['opex'] if prev else None))}"),
        ],
        "cash": [
            ("النقد آخر الشهر", cur["cash"], f"التغير خلال الشهر: {signed(cur['net_change'])}",
             f"أول السنة: {money(start_cash)}"),
            ("التدفق التشغيلي", cur["cfo"], f"من بداية السنة: {money(ytd_cfo)}",
             "الربح→كاش (من بداية السنة): " + ("—" if cash_conv is None else p1(cash_conv))),
            ("التدفق الحر (بعد شراء الأصول)", cur["fcf"], f"من بداية السنة: {money(ytd_fcf)}",
             financing_story(cur["fcf"], st_change, cur["net_change"])),
            ("التسهيلات القصيرة والاعتمادات", cur["st"], f"صافي سحب/سداد الشهر: {signed(st_change)}",
             f"القروض الطويلة: {money(cur['lt'])}  |  حركة الشهر: {signed(lt_change)}"),
        ],
        "wc": [
            ("العملاء وعهد المبيعات", cur["rec"], "أيام التحصيل: " + ("—" if cur["dso"] is None else f"{cur['dso']:.0f} يوم"),
             f"التغير خلال الشهر: {signed(cur['rec'] - open_bs['receivables'])}"),
            ("المخزون", cur["inv"], "أيام المخزون: " + ("—" if cur["dio"] is None else f"{cur['dio']:.0f} يوم"),
             f"التغير خلال الشهر: {signed(cur['inv'] - open_bs['inventory'])}"),
            ("الموردون", cur["pay"], "أيام السداد (تقريبي): " + ("—" if cur["dpo"] is None else f"{cur['dpo']:.0f} يوم"),
             f"التغير خلال الشهر: {signed(cur['pay'] - open_bs['payables'])}"),
            ("دورة التحويل النقدي", None if cur["ccc"] is None else round(cur["ccc"]), "تحصيل + مخزون − سداد",
             "كلما قلّت قلّ التمويل المطلوب"),
        ],
    }

    # ---------------- alerts
    alerts = []
    wc_names = {"receivables": "العملاء", "inventory": "المخزون والبضاعة بالطريق", "other_wc": "رأس المال العامل الآخر"}
    trap = min(wc_names, key=lambda k: cur["buckets"][k])
    trap_txt = wc_names[trap] if cur["buckets"][trap] < -0.5 else "لا يوجد (رأس المال العامل حرّر نقدًا)"
    alerts.append(("info", f"من موّل مَن هذا الشهر: {financing_story(cur['fcf'], st_change, cur['net_change'])}   |   "
                           f"أكبر بند حبس الكاش في رأس المال العامل: {trap_txt}"))
    if cash_conv is not None:
        level = "good" if cash_conv >= 0.8 else "warn" if cash_conv >= 0.5 else "bad"
        word = {"good": "جيد", "warn": "مقبول", "bad": "ضعيف: الأرباح محبوسة في العملاء والمخزون"}[level]
        alerts.append((level, f"تحول الربح إلى كاش من بداية السنة: {p1(cash_conv)}  ← {word}"))
    neg = [m for m in entered if figs[m]["cfo"] < 0]
    alerts.append(("warn" if neg else "good", f"أشهر التدفق التشغيلي فيها سالب: {len(neg)} من {len(entered)} أشهر"
                   + (f" ({'، '.join(MONTHS_AR[int(m[5:7]) - 1] for m in neg)})" if neg else "")))
    prior = [m for m in entered if m < end]
    over = []
    if prior:
        data = {m: ctx.opex_by_account([m]) for m in prior + [end]}
        for g in ctx.exp_groups:
            def gsum(m):
                return sum(v for c, v in data[m].items() if ctx.accounts[c].exp_group == g)
            c, avg = gsum(end), sum(gsum(m) for m in prior) / len(prior)
            if c - avg > ctx.alert_amount and (avg <= 0 or (c - avg) / avg > ctx.alert_pct):
                over.append(f"{g} ({iso(format(c - avg, '+,.0f'))})")
    alerts.append(("warn" if over else "good", f"بنود مصروفات تجاوزت متوسطها الشهري هذا الشهر: {len(over)}"
                   + (f" — {'، '.join(over)}" if over else "")))
    cust = ctx.aging("customers", end)
    if cust:
        s = AG.customers_summary(cust)
        alerts.append(("warn" if s["need_count"] else "good",
                       f"العملاء: مطلوب مطابقة شهرية لـ {s['need_count']} عميل، متأخر {s['need_amount']:,.0f} "
                       f"({iso(format(safe_div(s['overdue'], s['total']) or 0, '.0%'))} من رصيد الأعمار)"))
    supp = ctx.aging("suppliers", end)
    if supp:
        s = AG.suppliers_summary(supp, AG.rates(ctx.db), ctx.base_currency)
        if (ctx.db.setting("supp_view", "type") or "type") == "type":
            parts = [f"{t} {ts['overdue']:,.0f} ({ts['over_count']})"
                     for t, ts in AG.suppliers_by_type(supp, AG.rates(ctx.db), ctx.base_currency) if ts["count"]]
            alerts.append(("warn" if s["overdue"] > 0.5 else "good",
                           f"الموردون — المتجاوز لفترة الائتمان ({ctx.base_currency}): " + "، ".join(parts)
                           + (f" — {s['no_rate']} مورد بعملة بلا سعر صرف" if s["no_rate"] else "")))
        else:
            alerts.append(("warn" if s["overdue"] > 0.5 else "good",
                           f"الموردون: المتجاوز لفترة الائتمان {s['overdue']:,.0f} {ctx.base_currency} لدى "
                           f"{s['over_count']} مورد" + (f" — {s['no_rate']} مورد بعملة بلا سعر صرف" if s["no_rate"] else "")))

    # ---------------- chart series (12 months of the year; None when not entered)
    def series(key):
        return [figs[m][key] if m in figs else None for m in year]

    months = [MONTHS_AR[int(m[5:7]) - 1] for m in year]
    ytd_buckets = {k: sum(figs[m]["buckets"][k] for m in entered) for k in BUCKET_NAMES}
    branches = []
    if ctx.branches:
        cols, admin, company = ctx.branches_report_data(ctx.ytd_months(end))
        branches = [(b, f["net_sales"]) for b, f in cols.items()]
    charts = {
        "months": months,
        "profit": [("صافي المبيعات", series("net_sales")), ("مجمل الربح", series("gross")), ("صافي الربح", series("ni"))],
        "cash_vs_profit": [("صافي الربح", series("ni")), ("التدفق التشغيلي", series("cfo"))],
        "funding": [("النقد آخر الشهر", series("cash")), ("التسهيلات القصيرة والاعتمادات", series("st")),
                    ("القروض الطويلة", series("lt"))],
        "wc": [("العملاء", series("rec")), ("المخزون", series("inv")), ("الموردون", series("pay"))],
        "cash_moves": [(BUCKET_NAMES[k], v) for k, v in ytd_buckets.items()],
        "branches": sorted(branches, key=lambda x: -x[1]),
    }

    # ---------------- working-capital analysis: end of first entered month vs shown month
    a, z = figs[first], cur

    def trapped(f):
        return f["rec"] + f["inv"] - f["pay"]

    wc_rows = [
        ("العملاء وعهد المبيعات", a["rec"], z["rec"], "n"),
        ("المخزون", a["inv"], z["inv"], "n"),
        ("الموردون", a["pay"], z["pay"], "n"),
        ("الصافي المحبوس (عملاء + مخزون − موردين)", trapped(a), trapped(z), "n"),
        ("صافي المبيعات للشهر (للمقارنة)", a["net_sales"], z["net_sales"], "n"),
        ("أيام التحصيل", a["dso"], z["dso"], "d"),
        ("أيام المخزون", a["dio"], z["dio"], "d"),
        ("أيام السداد (تقريبي)", a["dpo"], z["dpo"], "d"),
        ("دورة التحويل النقدي", a["ccc"], z["ccc"], "d"),
    ]
    reading = []
    d_rec = z["rec"] - a["rec"]
    rec_pct = iso(format(_pct(z["rec"], a["rec"]) or 0, "+.0%"))
    sales_pct = iso(format(_pct(z["net_sales"], a["net_sales"]) or 0, "+.0%"))
    reading.append(f"العملاء: {'زادوا' if d_rec >= 0 else 'نقصوا'} {abs(d_rec):,.0f} ({rec_pct})، "
                   f"والمبيعات الشهرية تغيرت {sales_pct} — "
                   + ("العملاء يكبرون أسرع من المبيعات." if (_pct(z['rec'], a['rec']) or 0) > (_pct(z['net_sales'], a['net_sales']) or 0) else
                      "نمو العملاء متناسب مع المبيعات."))
    if z["dio"] is not None:
        reading.append(f"المخزون: {z['inv']:,.0f} = {z['dio']:.0f} يوم من التكلفة الشهرية.")
    d_pay = z["pay"] - a["pay"]
    reading.append(f"الموردون: {'زادوا' if d_pay >= 0 else 'نقصوا'} {abs(d_pay):,.0f}.")
    reading.append(f"المخزون الذي لا يموله الموردون: {z['inv'] - z['pay']:,.0f}.")
    d_tr = trapped(z) - trapped(a)
    reading.append(f"الصافي المحبوس في رأس المال العامل {'زاد' if d_tr >= 0 else 'نقص'} {abs(d_tr):,.0f} منذ نهاية {month_label(first)}.")
    day_value = z["net_sales"] * ctx.credit_ratio / 30
    if day_value > 0:
        reading.append(f"قيمة اليوم الواحد: كل يوم تحصيل أقل يحرر ≈ {day_value:,.0f} نقدًا.")
    pri = []
    if a["dso"] is not None and z["dso"] is not None and z["dso"] - a["dso"] > 3:
        pri.append(f"تسريع التحصيل (أيام التحصيل زادت {z['dso'] - a['dso']:.0f} يوم)")
    if a["dio"] is not None and z["dio"] is not None and z["dio"] - a["dio"] > 3:
        pri.append(f"تخفيض المخزون (أيامه زادت {z['dio'] - a['dio']:.0f} يوم)")
    if z["dpo"] is not None and z["dso"] is not None and z["dio"] is not None:
        pri.append(f"تمديد فترات الموردين (السداد {z['dpo']:.0f} يوم مقابل {z['dso'] + z['dio']:.0f} يوم تحصيل + مخزون)")
    if pri:
        reading.append("الأولوية: " + " | ".join(pri))

    fails = None
    try:
        from .reports import Params, run_checks
        fails = sum(1 for c in run_checks(ctx, Params(end=end)) if not c[3])
    except Exception:  # noqa: BLE001
        pass
    return {
        "end": end, "label": month_label(end), "last": month_label(ctx.periods[-1]), "fails": fails,
        "cards": cards, "alerts": alerts, "charts": charts, "wc_rows": wc_rows, "wc_first": month_label(first),
        "reading": reading,
    }
