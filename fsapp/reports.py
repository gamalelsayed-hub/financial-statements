"""HTML rendering of the statements (used for the screen and for PDF export)."""
import html

from .i18n import t, lang, ratio_text
from .categories import GROUP_NAMES

NUM_COLOR_NEG = "#b42318"


def fmt(v, decimals=0):
    if v is None:
        return "—"
    if abs(v) < 0.5 * 10 ** -decimals:
        return "-"
    s = f"{abs(v):,.{decimals}f}"
    return f"({s})" if v < 0 else s


def fmt_ratio(r):
    v = r["value"]
    if v is None:
        return t("st_na")
    if r["fmt"] == "%":
        return f"{v * 100:,.1f}%"
    if r["fmt"] == "x":
        return f"{v:,.2f} {t('times')}"
    if r["fmt"] == "days":
        return f"{v:,.0f} {t('days_unit')}"
    return fmt(v)


def esc(s):
    return html.escape(str(s))


CSS = """
body { font-family: 'Segoe UI', 'Tahoma', 'Arial'; font-size: 10.5pt; color: #1d2433; }
h1 { font-size: 15pt; margin: 0; color: #12355b; }
h2 { font-size: 12.5pt; margin: 2px 0; color: #12355b; }
.sub { color: #5b6475; font-size: 9.5pt; }
table.st { border-collapse: collapse; width: 100%; margin-top: 8px; }
table.st td, table.st th { padding: 4px 8px; }
table.st th { background: #12355b; color: white; font-weight: 600; }
td.num { text-align: right; white-space: nowrap; }
tr.hdr td { font-weight: 700; color: #12355b; padding-top: 10px; border-bottom: 1px solid #c9d3e0; }
tr.sub td { font-weight: 700; border-top: 1px solid #8a96a8; background: #f2f5f9; }
tr.tot td { font-weight: 800; border-top: 2px solid #12355b; border-bottom: 3px double #12355b; background: #e6edf6; }
tr.item td.lbl { padding-left: 18px; padding-right: 18px; }
td.note { color: #5b6475; text-align: center; font-size: 9pt; }
.good { color: #067647; font-weight: 700; }
.warn { color: #b54708; font-weight: 700; }
.bad { color: #b42318; font-weight: 700; }
.info, .na { color: #5b6475; }
.ok { color: #067647; font-weight: 700; }
.fail { color: #b42318; font-weight: 700; }
"""


class Notes:
    """Assigns note numbers to lines that have account details."""

    def __init__(self):
        self.items = []

    def ref(self, line):
        if not line.accounts:
            return ""
        for i, (k, _) in enumerate(self.items):
            if k == line.key:
                return str(i + 1)
        self.items.append((line.key, line.accounts))
        return str(len(self.items))


def _dir():
    return "rtl" if lang() == "ar" else "ltr"


def _align():
    return "right" if lang() == "ar" else "left"


def header(title, company, sub):
    return (f'<p align="center"><b style="font-size:15pt;color:#12355b">{esc(company)}</b><br>'
            f'<b style="font-size:12.5pt;color:#12355b">{esc(title)}</b><br>'
            f'<span class="sub">{esc(sub)}</span></p>')


def wrap(body):
    return (f'<html dir="{_dir()}"><head><meta charset="utf-8"><style>{CSS}</style></head>'
            f'<body dir="{_dir()}">{body}</body></html>')


def _row(label, values, kind="item", note=""):
    a = _align()
    cells = "".join(f'<td class="num">{fmt(v)}</td>' for v in values)
    return (f'<tr class="{kind}"><td class="lbl" align="{a}">{esc(label)}</td>'
            f'<td class="note">{note}</td>{cells}</tr>')


def _table(head_cols, rows_html):
    a = _align()
    heads = "".join(f"<th>{esc(h)}</th>" for h in head_cols)
    return (f'<table class="st" dir="{_dir()}" width="100%" cellspacing="0">'
            f'<tr><th align="{a}"></th><th>{t("note")}</th>{heads}</tr>{rows_html}</table>')


def balance_sheet(st, meta, notes):
    bs = st.bs
    rows = []
    cols = [t("current"), t("prior")]
    rows.append(f'<tr class="hdr"><td colspan="4">{t("assets")}</td></tr>')
    for grp, tot_key in (("CA", "total_CA"), ("NCA", "total_NCA")):
        rows.append(f'<tr class="hdr"><td colspan="4">{GROUP_NAMES[grp][0 if lang() == "ar" else 1]}</td></tr>')
        for l in bs[grp]:
            rows.append(_row(t(l.key), [l.amount, l.prior], note=notes.ref(l)))
        rows.append(_row(t(tot_key), bs[grp + "_total"], "sub"))
    rows.append(_row(t("total_assets"), bs["assets"], "tot"))
    rows.append(f'<tr class="hdr"><td colspan="4">{t("liab_equity")}</td></tr>')
    for grp, tot_key in (("CL", "total_CL"), ("NCL", "total_NCL")):
        if not bs[grp]:
            continue
        rows.append(f'<tr class="hdr"><td colspan="4">{GROUP_NAMES[grp][0 if lang() == "ar" else 1]}</td></tr>')
        for l in bs[grp]:
            rows.append(_row(t(l.key), [l.amount, l.prior], note=notes.ref(l)))
        rows.append(_row(t(tot_key), bs[grp + "_total"], "sub"))
    rows.append(_row(t("total_liabilities"), bs["liabilities"], "sub"))
    rows.append(f'<tr class="hdr"><td colspan="4">{GROUP_NAMES["EQ"][0 if lang() == "ar" else 1]}</td></tr>')
    for l in bs["EQ"]:
        rows.append(_row(t(l.key), [l.amount, l.prior], note=notes.ref(l)))
    rows.append(_row(t("total_EQ"), bs["EQ_total"], "sub"))
    rows.append(_row(t("total_le"), bs["liabilities_equity"], "tot"))
    return header(t("statement_of_fp"), meta["company"], t("as_at", d=meta["period"])) + _table(cols, "".join(rows))


def income_statement(st, meta, notes):
    rows = []
    kinds = {"item": "item", "subtotal": "sub", "total": "tot"}
    for l in st.is_["lines"]:
        if l.kind == "item" and not l.accounts and abs(l.amount) < 1e-9:
            continue
        rows.append(_row(t(l.key), [l.amount], kinds[l.kind], notes.ref(l)))
    return header(t("statement_of_pl"), meta["company"], t("for_period", d=meta["period"])) + _table([t("amount")], "".join(rows))


def cash_flow(st, meta, notes):
    cf = st.cf
    rows = [f'<tr class="hdr"><td colspan="3">{t("cfo_title")}</td></tr>',
            _row(t("net_income"), [cf["net_income"]])]
    if cf["op_adj"]:
        rows.append(f'<tr class="item"><td colspan="3"><i>{t("adjustments")}</i></td></tr>')
        rows += [_row(t(l.key), [l.amount]) for l in cf["op_adj"]]
    if cf["op_wc"]:
        rows.append(f'<tr class="item"><td colspan="3"><i>{t("wc_changes")}</i></td></tr>')
        rows += [_row(t(l.key), [l.amount]) for l in cf["op_wc"]]
    rows.append(_row(t("cfo"), [cf["cfo"]], "sub"))
    rows.append(f'<tr class="hdr"><td colspan="3">{t("cfi_title")}</td></tr>')
    rows += [_row(t(l.key), [l.amount]) for l in cf["inv"]]
    rows.append(_row(t("cfi"), [cf["cfi"]], "sub"))
    rows.append(f'<tr class="hdr"><td colspan="3">{t("cff_title")}</td></tr>')
    rows += [_row(t(l.key), [l.amount]) for l in cf["fin"]]
    rows.append(_row(t("cff"), [cf["cff"]], "sub"))
    rows.append(_row(t("net_change"), [cf["net_change"]], "sub"))
    rows.append(_row(t("cash_open"), [cf["cash_open"]]))
    rows.append(_row(t("cash_close"), [cf["cash_close_calc"]], "tot"))
    return header(t("statement_of_cf"), meta["company"], t("for_period", d=meta["period"])) + _table([t("amount")], "".join(rows))


def equity_statement(st, meta, notes):
    eq = st.equity
    cols = [k for k in eq["cols"] if any(abs(v) > 1e-9 for v in eq["rows"][k].values())] or eq["cols"][:3]
    a = _align()
    heads = "".join(f"<th>{esc(t(k))}</th>" for k in cols) + f"<th>{t('total')}</th>"
    body = ""
    for part, label, kind in (("open", "eq_open", "sub"), ("ni", "eq_ni", "item"),
                              ("other", "eq_other", "item"), ("close", "eq_close", "tot")):
        vals = [eq["rows"][k][part] for k in cols]
        cells = "".join(f'<td class="num">{fmt(v)}</td>' for v in vals + [sum(vals)])
        body += f'<tr class="{kind}"><td align="{a}" width="28%">{t(label)}</td>{cells}</tr>'
    table = (f'<table class="st" dir="{_dir()}" width="100%" cellspacing="0">'
             f'<tr><th width="30%"></th>{heads}</tr>{body}</table>')
    return header(t("statement_of_eq"), meta["company"], t("for_period", d=meta["period"])) + table


def notes_page(notes, meta):
    a = _align()
    out = header(t("notes_title"), meta["company"], t("as_at", d=meta["period"]))
    for i, (key, accounts) in enumerate(notes.items, start=1):
        rows = ""
        tc = tp = tm = 0
        for ac in accounts:
            rows += (f'<tr class="item"><td>{esc(ac.code)}</td><td align="{a}">{esc(ac.name)}</td>'
                     f'<td class="num">{fmt(ac.open_net)}</td><td class="num">{fmt(ac.mov_net)}</td>'
                     f'<td class="num">{fmt(ac.close_net)}</td></tr>')
            tp += ac.open_net
            tm += ac.mov_net
            tc += ac.close_net
        rows += (f'<tr class="sub"><td></td><td align="{a}">{t("total")}</td><td class="num">{fmt(tp)}</td>'
                 f'<td class="num">{fmt(tm)}</td><td class="num">{fmt(tc)}</td></tr>')
        out += (f'<h2>({i}) {esc(t(key))}</h2>'
                f'<table class="st" dir="{_dir()}" width="100%" cellspacing="0"><tr><th>{t("col_code")}</th>'
                f'<th align="{a}">{t("col_name")}</th><th>{t("opening")}</th><th>{t("movement")}</th>'
                f'<th>{t("closing")}</th></tr>{rows}</table>')
    out += f'<p class="sub">{"الأرصدة موجبة = مدين، وبين أقواس = دائن." if lang() == "ar" else "Positive = debit, in brackets = credit."}</p>'
    return out


def checks_page(st, meta):
    a = _align()
    rows = ""
    for key, val in (("check_bs", st.checks["bs_diff"]), ("check_bs_prior", st.checks["bs_diff_prior"]),
                     ("check_ni", st.checks["ni_diff"]), ("check_cash", st.checks["cash_diff"])):
        ok = abs(val) < 1
        res = f'<span class="ok">{t("check_ok")}</span>' if ok else f'<span class="fail">{t("check_fail", d=fmt(val, 2))}</span>'
        rows += f'<tr class="item"><td align="{a}">{t(key)}</td><td>{res}</td></tr>'
    return (header(t("tab_checks"), meta["company"], meta["period"]) +
            f'<table class="st" dir="{_dir()}" width="100%">{rows}</table><p class="sub">{t("checks_hint")}</p>')


def ratios_page(st, meta):
    a = _align()
    out = header(t("ratios_title"), meta["company"], t("for_period", d=meta["period"]))
    out += f"<h2>{t('summary')}</h2><ul>" + "".join(f"<li>{esc(s)}</li>" for s in summary(st)) + "</ul>"
    kf = [(t("revenue"), st.is_["revenue"]), (t("net_income"), st.is_["net_income"]),
          (t("total_assets"), st.bs["assets"][0]), (t("total_EQ"), st.bs["EQ_total"][0]),
          (t("cfo"), st.cf["cfo"])]
    out += f"<h2>{t('key_figures')}</h2><table class='st' dir='{_dir()}' width='100%'>"
    out += "".join(f"<tr class='item'><td align='{a}'>{esc(k)}</td><td class='num'>{fmt(v)}</td></tr>" for k, v in kf)
    out += "</table>"
    groups = []
    for r in st.ratios:
        if r["group"] not in groups:
            groups.append(r["group"])
    for g in groups:
        rows = ""
        for r in [x for x in st.ratios if x["group"] == g]:
            stt = r["status"]
            rows += (f'<tr class="item"><td align="{a}"><b>{esc(ratio_text(r["key"], 0))}</b><br>'
                     f'<span class="sub">{esc(ratio_text(r["key"], 2))}</span></td>'
                     f'<td class="num"><b>{fmt_ratio(r)}</b></td>'
                     f'<td align="{a}" class="sub">{esc(ratio_text(r["key"], 1))}</td>'
                     f'<td align="center" class="{stt}">{t("st_" + stt)}</td></tr>')
        out += (f"<h2>{t('grp_' + g)}</h2><table class='st' dir='{_dir()}' width='100%' cellspacing='0'>"
                f"<tr><th align='{a}'>{t('ratio')}</th><th>{t('value')}</th><th align='{a}'>{t('formula')}</th>"
                f"<th>{t('assessment')}</th></tr>{rows}</table>")
    out += f"<p class='sub'>{t('ratios_note')}</p>"
    return out


def summary(st):
    r = {x["key"]: x for x in st.ratios}
    ar = lang() == "ar"
    out = []

    def v(k):
        return r[k]["value"]

    cr = v("current_ratio")
    if cr is not None:
        if cr >= 1.5:
            out.append(f"السيولة جيدة: نسبة التداول {cr:.2f} مرة." if ar else f"Liquidity is healthy: current ratio {cr:.2f}x.")
        elif cr >= 1:
            out.append(f"السيولة مقبولة لكنها تحتاج متابعة: نسبة التداول {cr:.2f} مرة." if ar else f"Liquidity is acceptable but needs monitoring: current ratio {cr:.2f}x.")
        else:
            out.append(f"تحذير سيولة: الالتزامات المتداولة أكبر من الأصول المتداولة (نسبة التداول {cr:.2f})." if ar else f"Liquidity warning: current liabilities exceed current assets (current ratio {cr:.2f}).")
    nm = v("net_margin")
    if nm is not None:
        if nm < 0:
            out.append(f"الشركة حققت خسارة صافية بهامش {nm * 100:.1f}% من المبيعات." if ar else f"The company made a net loss of {nm * 100:.1f}% of revenue.")
        else:
            out.append(f"هامش صافي الربح {nm * 100:.1f}% وهامش مجمل الربح {(v('gross_margin') or 0) * 100:.1f}%." if ar else f"Net margin is {nm * 100:.1f}% and gross margin {(v('gross_margin') or 0) * 100:.1f}%.")
    de = v("debt_to_equity")
    if de is not None:
        if de > 2:
            out.append(f"الاعتماد على التمويل الخارجي مرتفع (الالتزامات = {de:.2f} ضعف حقوق الملكية)." if ar else f"High reliance on external financing (liabilities = {de:.2f}x equity).")
        else:
            out.append(f"هيكل التمويل متوازن نسبيًا (الالتزامات = {de:.2f} ضعف حقوق الملكية)." if ar else f"Financing structure is reasonably balanced (liabilities = {de:.2f}x equity).")
    elif st.bs["EQ_total"][0] <= 0:
        out.append("حقوق الملكية سالبة — الخسائر المتراكمة تجاوزت رأس المال." if ar else "Equity is negative — accumulated losses exceed capital.")
    cfo, ni = st.cf["cfo"], st.is_["net_income"]
    if cfo < 0:
        out.append("التدفق النقدي من التشغيل سالب: النشاط يستهلك نقدية — راجع التحصيل والمخزون." if ar else "Operating cash flow is negative: operations consume cash — review collections and inventory.")
    elif ni > 0 and cfo < ni * 0.7:
        out.append("جزء كبير من الأرباح لم يتحول إلى نقدية بعد (غالبًا بسبب زيادة العملاء أو المخزون)." if ar else "A large part of profit has not turned into cash (often due to higher receivables or inventory).")
    elif cfo > 0:
        out.append("النشاط التشغيلي يولد نقدية موجبة." if ar else "Operations generate positive cash.")
    ccc = v("ccc")
    if ccc is not None:
        out.append(f"دورة التحويل النقدي حوالي {ccc:.0f} يوم." if ar else f"Cash conversion cycle is about {ccc:.0f} days.")
    return out


def full_report(st, meta):
    """All statements in one HTML document (with page breaks) for PDF export."""
    notes = Notes()
    parts = [balance_sheet(st, meta, notes), income_statement(st, meta, notes), cash_flow(st, meta, notes),
             equity_statement(st, meta, notes), notes_page(notes, meta), ratios_page(st, meta)]
    br = '<div style="page-break-before: always;"></div>'
    return wrap(br.join(parts))


def screen_pages(st, meta):
    notes = Notes()
    pages = {
        "bs": balance_sheet(st, meta, notes),
        "is": income_statement(st, meta, notes),
        "cf": cash_flow(st, meta, notes),
        "eq": equity_statement(st, meta, notes),
    }
    pages["notes"] = notes_page(notes, meta)
    pages["checks"] = checks_page(st, meta)
    pages["ratios"] = ratios_page(st, meta)
    return {k: wrap(v) for k, v in pages.items()}
