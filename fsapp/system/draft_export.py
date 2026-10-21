"""Draft financial statements → Excel (editable, totals as formulas) and PDF (the company's printed layout).

Layout rules: totals are highlighted; a note (title, accounts and total) is never split across pages unless it is
longer than a whole page, and a section heading never stays alone at the bottom of a page.
"""
import html

from . import draft as DR

TITLES = {"fp": "قائمة المركز المالي كما في {end}", "is": "قائمة الدخل الشامل من {start} إلى {end}",
          "cf": "قائمة التدفقات النقدية من {start} إلى {end}"}
SHEETS = {"fp": "المركز المالي", "is": "قائمة الدخل", "cf": "التدفقات النقدية"}
NUM = '#,##0;(#,##0);"-"'
NAVY, SUB_FILL, TOT_FILL, HEAD_FILL = "12355B", "EEF2F7", "D5E3F2", "F4F6F9"
NOTE_SECTIONS = {"is": "إيضاحات قائمة الدخل", "bs": "إيضاحات قائمة المركز المالي"}


def period_labels(dr, ctx, key="fp"):
    """Column dates; the income statement and cash flows have a comparative only when the previous year exists."""
    first = ctx.ytd_months(dr.end)[0]
    y, m = map(int, first.split("-"))
    has = {"fp": dr.comp is not None, "is": bool(dr.comp and dr.comp.is_ is not None), "cf": dr.cf_comp is not None,
           "notes": dr.comp is not None}[key]
    return {"start": f"1/{m}/{y}", "end": DR.date_label(dr.end),
            "cur": DR.date_label(dr.end), "comp": DR.date_label(dr.comp.end) if has else ""}


def money(v):
    if v is None:
        return ""
    if abs(v) < 0.5:
        return "-"
    s = f"{abs(v):,.0f}"
    return f"‎({s})‎" if v < 0 else s


# ------------------------------------------------------------------ Excel
def to_excel(dr, ctx, path, opts):
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.pagebreak import Break

    labels = period_labels(dr, ctx)
    blocks, notes = DR.statements(dr, ctx)
    wb = openpyxl.Workbook()
    thin, double = Side(style="thin", color="7F8FA6"), Side(style="double", color=NAVY)
    fill = {k: PatternFill("solid", fgColor=c) for k, c in (("navy", NAVY), ("sub", SUB_FILL), ("tot", TOT_FILL),
                                                             ("head", HEAD_FILL))}
    white, navy_bold = Font(bold=True, color="FFFFFF"), Font(bold=True, color=NAVY)
    center = Alignment(horizontal="center", vertical="center")

    def setup(ws, widths):
        ws.sheet_view.rightToLeft = True
        ws.sheet_view.showGridLines = False
        ws.page_setup.orientation = "portrait"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.print_options.horizontalCentered = True
        ws.page_margins.left = ws.page_margins.right = 0.5
        for col, w in zip("ABCD", widths):
            ws.column_dimensions[col].width = w

    def header(ws, title):
        for r, (text, font) in enumerate(((dr.company, Font(bold=True, size=14, color=NAVY)),
                                          (opts.get("legal_form", ""), Font(size=10, color="475467")),
                                          ("", None), (title, Font(bold=True, size=12)),
                                          (opts.get("currency", "ريال سعودي"), Font(size=10, color="475467"))), start=1):
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
            ws.cell(r, 1, text or None)
            if font:
                ws.cell(r, 1).font = font
            ws.cell(r, 1).alignment = Alignment(horizontal="right")

    def style_row(ws, r, kind):
        for col in range(1, 5):
            c = ws.cell(r, col)
            if kind == "sub":
                c.fill, c.font = fill["sub"], Font(bold=True)
                c.border = Border(top=thin)
            elif kind == "tot":
                c.fill, c.font = fill["tot"], navy_bold
                c.border = Border(top=thin, bottom=double)

    for i, (key, rows) in enumerate(blocks):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = SHEETS[key]
        setup(ws, (54, 8, 17, 17))
        lab = period_labels(dr, ctx, key)
        header(ws, TITLES[key].format(**lab))
        ws.append([])
        ws.append(["البيان", "إيضاح", lab["comp"], lab["cur"]])
        for c in ws[ws.max_row]:
            c.fill, c.font, c.alignment = fill["navy"], white, center
        ws.cell(ws.max_row, 1).alignment = Alignment(horizontal="right", vertical="center")
        ws.freeze_panes = ws.cell(ws.max_row + 1, 1)
        refs, since = {}, []
        for label, note, cur, comp, kind in rows:
            if kind == "blank":
                ws.append([])
                continue
            ws.append([label, note or None, comp, cur])
            r = ws.max_row
            refs[label] = r
            ws.cell(r, 2).alignment = center
            if kind == "hdr":
                ws.cell(r, 1).font = Font(bold=True, underline="single", color=NAVY)
                since = []
                continue
            if kind == "item":
                since.append(r)
            formula = _formula(key, label, refs, since)
            for col in ("C", "D"):
                cell = ws[f"{col}{r}"]
                cell.number_format = NUM
                if formula and cell.value is not None:
                    cell.value = "=" + formula.format(c=col)
            style_row(ws, r, kind)
        ws.append([])
        ws.append([])
        for text in (opts.get("sign_title", ""), opts.get("sign_name", "")):
            ws.append([None, None, None, text or None])
            ws.cell(ws.max_row, 4).font = Font(bold=True)

    # notes: one block per note, never split across a printed page
    ws = wb.create_sheet("الإيضاحات")
    setup(ws, (13, 47, 17, 17))
    header(ws, "إيضاحات حول القوائم المالية")
    rows_per_page, used = 46, 6
    last_kind = None
    for no, title, kind, rows, t1, t2 in DR.note_tables(dr, ctx, notes):
        need = len(rows) + 4 + (2 if kind != last_kind else 0)
        if used + need > rows_per_page and used > 6:
            ws.row_breaks.append(Break(id=ws.max_row))
            used = 0
        if kind != last_kind:
            ws.append([])
            ws.append([NOTE_SECTIONS[kind]])
            ws.cell(ws.max_row, 1).font = Font(bold=True, size=12, underline="single", color=NAVY)
            last_kind = kind
        ws.append([])
        ws.append([f"إيضاح ({no})  —  {title}"])
        r = ws.max_row
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        ws.cell(r, 1).fill, ws.cell(r, 1).font = fill["navy"], white
        ws.append(["رقم الحساب", "اسم الحساب", labels["comp"] if t2 is not None else "", labels["cur"]])
        for c in ws[ws.max_row]:
            c.fill, c.font, c.alignment = fill["head"], Font(bold=True), center
        first = ws.max_row + 1
        for code, name, v1, v2 in rows:
            ws.append([code or None, name, v2, v1])
            ws.cell(ws.max_row, 3).number_format = ws.cell(ws.max_row, 4).number_format = NUM
            ws.cell(ws.max_row, 1).alignment = center
        last = ws.max_row
        ws.append(["", "الإجمالي", f"=SUM(C{first}:C{last})" if t2 is not None else None, f"=SUM(D{first}:D{last})"])
        style_row(ws, ws.max_row, "tot")
        for col in (3, 4):
            ws.cell(ws.max_row, col).number_format = NUM
        used += need
    if dr.checks:
        ws = wb.create_sheet("ملاحظات المراجعة")
        ws.sheet_view.rightToLeft = True
        ws.column_dimensions["A"].width = 120
        for c in dr.checks:
            ws.append([c])
    wb.save(path)
    return path


def _formula(key, label, refs, since):
    """Excel formula (with {c} for the column) for a total row, so the draft stays consistent when edited."""
    def ref(lbl):
        return f"{{c}}{refs[lbl]}" if lbl in refs else "0"
    if key == "fp":
        special = {"إجمالي الموجودات": ("إجمالي الموجودات المتداولة", "إجمالي الموجودات غير المتداولة"),
                   "إجمالي المطلوبات": ("إجمالي المطلوبات المتداولة", "إجمالي المطلوبات غير المتداولة"),
                   "إجمالي المطلوبات وحقوق الشركاء": ("إجمالي المطلوبات", "إجمالي حقوق الشركاء")}
        if label in special:
            return "+".join(ref(x) for x in special[label])
        if label.startswith("إجمالي") and since:
            return f"SUM({{c}}{since[0]}:{{c}}{since[-1]})"
        return None
    if key == "is":
        L = DR.IS_LABEL
        rules = {
            "مجمل الربح": f"{ref(L['sales'])}-{ref(L['cogs'])}",
            "إجمالي المصروفات": f"{ref(L['selling'])}+{ref(L['admin'])}",
            "صافي الدخل من العمليات الرئيسية": f"{ref('مجمل الربح')}-{ref('إجمالي المصروفات')}",
            "صافي الدخل بعد المصاريف التمويلية": f"{ref('صافي الدخل من العمليات الرئيسية')}-{ref(L['finance'])}",
            "صافي الربح قبل الزكاة": f"{ref('صافي الدخل بعد المصاريف التمويلية')}+{ref(L['invest'])}+{ref(L['other'])}",
            "صافي الدخل": f"{ref('صافي الربح قبل الزكاة')}-{ref(L['zakat'])}",
        }
        return rules.get(label)
    return None


# ------------------------------------------------------------------ PDF
ROW_BG = {"sub": "#eef2f7", "tot": "#d5e3f2"}


def _page_head(dr, opts, title, currency, logo_html):
    # Qt lays table columns left to right: the logo cell first (left), the company cell last (right)
    return (f'<table width="100%" cellspacing="0" cellpadding="0"><tr>'
            f'<td width="40%" align="left">{logo_html}</td>'
            f'<td width="60%" align="right" dir="rtl"><span style="font-size:10.5pt; color:#12355b;"><b>'
            f'{html.escape(dr.company)}</b></span><br/><span style="font-size:9pt; color:#475467;">'
            f'{html.escape(opts.get("legal_form", ""))}</span></td></tr></table>'
            '<table width="100%" cellspacing="0" cellpadding="0" style="margin-top:4px;"><tr>'
            '<td bgcolor="#12355b" style="font-size:2px;">&nbsp;</td></tr></table>'
            f'<p dir="rtl" align="right" style="font-size:12pt; margin:8px 0 0 0;"><b>{html.escape(title)}</b></p>'
            f'<p dir="rtl" align="right" style="font-size:9pt; color:#475467; margin:0 0 8px 0;">{html.escape(currency)}</p>')


def _signature(opts):
    if not (opts.get("sign_title") or opts.get("sign_name")):
        return ""
    return ('<table width="100%" style="margin-top:28px;"><tr><td width="40%" align="left" dir="rtl" '
            f'style="font-size:11pt;"><b>{html.escape(opts.get("sign_title", ""))}<br/>'
            f'{html.escape(opts.get("sign_name", ""))}</b></td><td width="60%"></td></tr></table>')


def _cells(values, kind, widths):
    bg = f' bgcolor="{ROW_BG[kind]}"' if kind in ROW_BG else ""
    style = "font-weight:bold;" + ("color:#12355b; text-decoration: underline;" if kind == "tot" else "") \
        if kind in ROW_BG else ""
    return "".join(f'<td width="{w}" align="center"{bg} style="{style}">{money(v)}</td>' for v, w in zip(values, widths))


def statement_html(dr, ctx, key, rows):
    """The table of one statement (without the page head)."""
    lab = period_labels(dr, ctx, key)
    out = ['<table width="100%" cellspacing="0" cellpadding="3">',
           # visual order left → right: current, comparative, note, label
           f'<tr><td width="15%" align="center" bgcolor="#12355b"><font color="white"><b>{lab["cur"]}</b></font></td>'
           f'<td width="15%" align="center" bgcolor="#12355b"><font color="white"><b>{lab["comp"]}</b></font></td>'
           '<td width="7%" align="center" bgcolor="#12355b"><font color="white"><b>إيضاح</b></font></td>'
           '<td width="63%" align="right" bgcolor="#12355b" dir="rtl"><font color="white"><b>البيان</b></font></td></tr>']
    for label, note, cur, comp, kind in rows:
        if kind == "blank":
            out.append('<tr><td colspan="4" height="6"></td></tr>')
            continue
        if kind == "hdr":
            out.append('<tr><td></td><td></td><td></td><td align="right" dir="rtl" style="color:#12355b;">'
                       f'<b><u>{html.escape(label)}</u></b></td></tr>')
            continue
        bg = f' bgcolor="{ROW_BG[kind]}"' if kind in ROW_BG else ""
        weight = "font-weight:bold;" + ("color:#12355b;" if kind == "tot" else "") if kind in ROW_BG else ""
        out.append("<tr>" + _cells((cur, comp), kind, ("15%", "15%"))
                   + f'<td width="7%" align="center"{bg}>{note}</td>'
                   f'<td width="63%" align="right" dir="rtl"{bg} style="{weight}">{html.escape(label)}</td></tr>')
    out.append("</table>")
    return "".join(out)


def note_html(no, title, rows, t1, t2, labels, cont=False, with_total=True):
    head = f"({no}) {html.escape(title)}" + ("  — تابع" if cont else "")
    out = [f'<p dir="rtl" align="right" style="margin:10px 0 3px 0; color:#12355b; font-size:10.5pt;"><b>{head}</b></p>',
           '<table width="100%" cellspacing="0" cellpadding="2">'
           f'<tr><td width="16%" align="center" bgcolor="#eef2f7"><b>{labels["cur"]}</b></td>'
           f'<td width="16%" align="center" bgcolor="#eef2f7"><b>{labels["comp"] if t2 is not None else ""}</b></td>'
           '<td width="52%" align="right" dir="rtl" bgcolor="#eef2f7"><b>اسم الحساب</b></td>'
           '<td width="16%" align="center" bgcolor="#eef2f7"><b>رقم الحساب</b></td></tr>']
    for code, name, v1, v2 in rows:
        out.append(f'<tr><td align="center">{money(v1)}</td><td align="center">{money(v2)}</td>'
                   f'<td align="right" dir="rtl">{html.escape(name)}</td><td align="center">{html.escape(code)}</td></tr>')
    if with_total:
        out.append("<tr>" + _cells((t1, t2), "tot", ("16%", "16%"))
                   + f'<td align="right" dir="rtl" bgcolor="{ROW_BG["tot"]}" style="color:#12355b;"><b>الإجمالي</b></td>'
                   f'<td bgcolor="{ROW_BG["tot"]}"></td></tr>')
    out.append("</table>")
    return "".join(out)


def section_html(kind):
    return (f'<p dir="rtl" align="right" style="font-size:12pt; margin:14px 0 2px 0; color:#12355b;"><b><u>'
            f'{NOTE_SECTIONS[kind]}</u></b></p>')


def pages(dr, ctx, opts, logo_path, measure=None, page_height=None):
    """[(head_title, [html fragments])] — one entry per printed page. With measure(html) → height, notes are kept
    whole on a page and long ones are continued on the next page with their heading repeated."""
    blocks, notes = DR.statements(dr, ctx)
    out = []
    for key, rows in blocks:
        lab = period_labels(dr, ctx, key)
        out.append((TITLES[key].format(**lab), [statement_html(dr, ctx, key, rows), _signature(opts)]))
    labels = period_labels(dr, ctx, "notes")
    title = "إيضاحات حول القوائم المالية"
    items = []          # (fragment, kind header or "", note tuple) in reading order
    last_kind = None
    for t in DR.note_tables(dr, ctx, notes):
        no, ttl, kind, rows, t1, t2 = t
        items.append((section_html(kind) if kind != last_kind else "", t))
        last_kind = kind
    if measure is None:     # no pagination (tests / plain HTML): everything on one "page"
        frags = [sec + note_html(no, ttl, rows, t1, t2, labels) for sec, (no, ttl, kind, rows, t1, t2) in items]
        out.append((title, frags))
        return out
    head_h = measure(_page_head(dr, opts, title, opts.get("currency", ""), _logo(logo_path)))
    avail = page_height - head_h - 8
    page, used, first_page = [], 0.0, len(out)

    def flush():
        nonlocal page, used
        if page:
            out.append((title if len(out) == first_page else title + " (تابع)", page))
        page, used = [], 0.0
    for sec, (no, ttl, kind, rows, t1, t2) in items:
        frag = sec + note_html(no, ttl, rows, t1, t2, labels)
        h = measure(frag)
        if used + h <= avail:
            page.append(frag)
            used += h
            continue
        if h <= avail:              # fits on a fresh page: move the whole note (with its section heading)
            flush()
            page.append(frag)
            used = h
            continue
        # longer than a page: split the accounts, repeating the note heading
        flush()
        chunk, first = [], True
        for i, row in enumerate(rows):
            trial = (sec if first else "") + note_html(no, ttl, chunk + [row], t1, t2, labels, cont=not first,
                                                         with_total=i == len(rows) - 1)
            if measure(trial) > avail and chunk:
                page.append((sec if first else "") + note_html(no, ttl, chunk, t1, t2, labels, cont=not first,
                                                                with_total=False))
                flush()
                chunk, first = [row], False
            else:
                chunk.append(row)
        frag = (sec if first else "") + note_html(no, ttl, chunk, t1, t2, labels, cont=not first)
        page.append(frag)
        used = measure(frag)
    flush()
    return out


def _logo(path):
    return f'<img src="{html.escape(path)}" height="64"/>' if path else ""


CSS = "body { font-size: 10pt; } td { padding: 2px 4px; }"


def _wrap(body):
    return f'<html><head><style>{CSS}</style></head><body dir="rtl">{body}</body></html>'


def to_html(dr, ctx, opts, logo_path=""):
    """All pages as one HTML document (preview / tests)."""
    currency = opts.get("currency", "ريال سعودي")
    parts = []
    for i, (title, frags) in enumerate(pages(dr, ctx, opts, logo_path)):
        brk = ' style="page-break-before: always;"' if i else ""
        parts.append(f"<div{brk}>" + _page_head(dr, opts, title, currency, _logo(logo_path)) + "".join(frags) + "</div>")
    return _wrap("".join(parts))


def to_pdf(dr, ctx, path, opts, logo_path=""):
    """Pages are laid out here (not by Qt) so a note is never split across two pages."""
    import sys

    from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
    from PySide6.QtGui import QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QTextDocument, QTextOption
    writer = QPdfWriter(path)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait,
                                     QMarginsF(16, 12, 16, 12), QPageLayout.Millimeter))
    writer.setResolution(96)
    writer.setTitle(f"{dr.company} — مسودة القوائم المالية")
    rect = writer.pageLayout().paintRectPixels(writer.resolution())
    width, height = rect.width(), rect.height()
    font = QFont("Segoe UI" if sys.platform == "win32" else "DejaVu Sans", 9)

    def document(body):
        doc = QTextDocument()
        doc.documentLayout().setPaintDevice(writer)
        doc.setDefaultFont(font)
        opt = QTextOption()
        opt.setTextDirection(Qt.RightToLeft)
        doc.setDefaultTextOption(opt)
        doc.setDocumentMargin(0)
        doc.setTextWidth(width)
        doc.setHtml(_wrap(body))
        return doc

    def measure(body):
        return document(body).size().height()

    currency = opts.get("currency", "ريال سعودي")
    painter = QPainter(writer)
    try:
        for i, (title, frags) in enumerate(pages(dr, ctx, opts, logo_path, measure, height)):
            if i:
                writer.newPage()
            doc = document(_page_head(dr, opts, title, currency, _logo(logo_path)) + "".join(frags))
            painter.save()
            doc.drawContents(painter, QRectF(QPointF(0, 0), doc.size()))
            painter.restore()
    finally:
        painter.end()
    return path
