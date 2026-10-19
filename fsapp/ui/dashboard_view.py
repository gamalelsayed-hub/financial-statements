"""Dashboard screen: cards, alerts, charts and the working-capital analysis."""
from PySide6.QtCharts import (QBarCategoryAxis, QBarSeries, QBarSet, QChart, QChartView, QHorizontalBarSeries,
                              QHorizontalStackedBarSeries, QLineSeries, QValueAxis)
from PySide6.QtCore import QMargins, QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QPageLayout, QPageSize, QPainter, QPdfWriter, QPen
from PySide6.QtWidgets import (QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
                               QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem, QToolTip,
                               QVBoxLayout, QWidget)

from ..system import dashboard, render
from ..system import reports as R

NAVY = "#12355b"
# categorical slots 1-3 (validated reference palette), fixed order
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
STATUS = {"good": "#067647", "warn": "#b54708", "bad": "#b42318", "info": "#344054"}
STATUS_ICON = {"good": "✓", "warn": "⚠", "bad": "⛔", "info": "•"}
SECTION_ACCENT = {"profit": "#2a78d6", "cash": "#1baf7a", "wc": "#eb6834"}
SHORT_BUCKETS = {
    "الكاش من الأرباح (صافي الربح + الإهلاك + المخصصات)": "الأرباح + الإهلاك والمخصصات",
    "العملاء وعهد المبيعات (زيادة = كاش محبوس)": "العملاء",
    "المخزون والبضاعة بالطريق": "المخزون والبضاعة بالطريق",
    "الموردون": "الموردون",
    "رأس المال العامل الآخر": "رأس المال العامل الآخر",
    "الأصول والاستثمارات": "الأصول والاستثمارات",
    "التسهيلات القصيرة والاعتمادات": "التسهيلات القصيرة",
    "الملاك": "الملاك",
    "القروض الطويلة والتزامات أخرى": "القروض الطويلة",
}


def _scale(values):
    m = max((abs(v) for v in values if v is not None), default=0)
    if m >= 1e6:
        return 1e6, "بالمليون"
    if m >= 1e4:
        return 1e3, "بالألف"
    return 1, ""


def _fmt(v):
    return "—" if v is None else f"{v:,.0f}"


class Card(QFrame):
    def __init__(self, title, value, line1, line2, accent):
        super().__init__()
        self.setStyleSheet(f"QFrame {{ background: white; border: 1px solid #e4e7ec; border-radius: 8px; "
                           f"border-right: 4px solid {accent}; }} QLabel {{ border: none; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 8, 12, 8)
        t = QLabel(title)
        t.setStyleSheet("color:#475467; font-size:9.5pt;")
        val = QLabel(_fmt(value) if not isinstance(value, str) else value)
        val.setStyleSheet(f"color:{NAVY}; font-size:17pt; font-weight:700;")
        if isinstance(value, (int, float)) and value < 0:
            val.setStyleSheet("color:#b42318; font-size:17pt; font-weight:700;")
        l1, l2 = QLabel(line1), QLabel(line2)
        for lbl in (l1, l2):
            lbl.setStyleSheet("color:#475467; font-size:9pt;")
            lbl.setWordWrap(True)
        for w in (t, val, l1, l2):
            v.addWidget(w)
        self.setMinimumHeight(118)


class DashboardPage(QScrollArea):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setWidgetResizable(True)
        self.setStyleSheet("QScrollArea { background: #f5f7fa; border: none; }")
        self.data = None
        self.box = None

    # ---------------------------------------------------------------- building
    def load(self):
        ctx, params = self.win.ctx, self.win.params()
        self.data = dashboard.compute(ctx, params.end) if (ctx and params) else None
        box = QWidget()
        box.setStyleSheet("background: #f5f7fa;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 10, 14, 14)
        lay.setSpacing(10)
        if not self.data:
            lbl = QLabel("لا توجد بيانات بعد — ارفع ميزان شهر من شاشة «البيانات الشهرية».")
            lbl.setStyleSheet("color:#667085; font-size:12pt; padding:30px;")
            lay.addWidget(lbl)
            lay.addStretch()
            self.setWidget(box)
            return
        d = self.data
        lay.addLayout(self._header(ctx.company, d))
        for key, title in (("profit", "الربحية — الشهر المعروض"), ("cash", "النقد والتمويل — الشهر المعروض"),
                           ("wc", "رأس المال العامل — الشهر المعروض (الأيام على أساس 30 يوم)")):
            lay.addWidget(self._section_title(title))
            grid = QGridLayout()
            grid.setSpacing(10)
            for i, (t, v, l1, l2) in enumerate(d["cards"][key]):
                grid.addWidget(Card(t, v, l1, l2, SECTION_ACCENT[key]), 0, i)
            lay.addLayout(grid)
        lay.addWidget(self._section_title("الخلاصة والتنبيهات"))
        lay.addWidget(self._alerts(d["alerts"]))
        lay.addWidget(self._section_title("الرسوم البيانية"))
        ch = d["charts"]
        n = len([v for v in ch["profit"][0][1] if v is not None])
        months = ch["months"][:n]

        def cut(series):
            return [(name, vals[:n]) for name, vals in series]

        charts = [
            self._bar_chart("المبيعات ومجمل الربح وصافي الربح — شهريًا", months, cut(ch["profit"])),
            self._bar_chart("الربح مقابل الكاش التشغيلي — شهريًا", months, cut(ch["cash_vs_profit"])),
            self._line_chart("النقد مقابل التسهيلات القصيرة والقروض الطويلة", months, cut(ch["funding"])),
            self._line_chart("رأس المال العامل: العملاء والمخزون والموردون", months, cut(ch["wc"])),
            self._cash_moves_chart("حركة الكاش من بداية السنة: من أين جاء وأين صُرف", ch["cash_moves"]),
            self._hbar_chart("مبيعات الفروع من بداية السنة", ch["branches"]),
        ]
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, c in enumerate(charts):
            if c is not None:
                grid.addWidget(c, i // 2, i % 2)
        lay.addLayout(grid)
        lay.addWidget(self._section_title(f"تحليل رأس المال العامل — نهاية {d['wc_first']} مقابل نهاية {d['label']}"))
        lay.addWidget(self._wc_table(d))
        reading = QLabel("<b>القراءة</b><br>" + "<br>".join("• " + r for r in d["reading"]))
        reading.setWordWrap(True)
        reading.setStyleSheet("background:white; border:1px solid #e4e7ec; border-radius:8px; padding:10px; "
                              "color:#1d2433; font-size:10pt;")
        lay.addWidget(reading)
        lay.addStretch()
        self.box = box
        self.setWidget(box)

    def _header(self, company, d):
        h = QHBoxLayout()
        v = QVBoxLayout()
        t = QLabel(f"لوحة التحكم — {company}")
        t.setStyleSheet(f"color:{NAVY}; font-size:16pt; font-weight:700;")
        sub = QLabel(f"الشهر المعروض: {d['label']}   |   آخر شهر مُدخل: {d['last']}   |   "
                     "غيّر الشهر من «الفترة المنتهية في» أعلى الشاشة")
        sub.setStyleSheet("color:#475467;")
        v.addWidget(t)
        v.addWidget(sub)
        h.addLayout(v, 1)
        if d["fails"] is not None:
            ok = d["fails"] == 0
            chip = QLabel("✓ المطابقات سليمة: الميزانية والتدفقات متوازنة" if ok else
                          f"⚠ {d['fails']} فحص يحتاج مراجعة — افتح «تشخيص الخلل»")
            chip.setStyleSheet(f"color:white; background:{STATUS['good'] if ok else STATUS['bad']}; "
                               "border-radius:12px; padding:6px 12px; font-weight:700;")
            h.addWidget(chip)
        for text, fn in (("📄 PDF", self.export_pdf), ("📊 Excel", self.export_excel)):
            b = QPushButton(text)
            b.setMinimumHeight(32)
            b.clicked.connect(fn)
            h.addWidget(b)
        return h

    @staticmethod
    def _section_title(text):
        lbl = QLabel(text)
        lbl.setStyleSheet(f"color:{NAVY}; font-size:12pt; font-weight:700; margin-top:6px;")
        return lbl

    @staticmethod
    def _alerts(alerts):
        w = QFrame()
        w.setStyleSheet("QFrame { background:white; border:1px solid #e4e7ec; border-radius:8px; } QLabel { border:none; }")
        v = QVBoxLayout(w)
        for level, text in alerts:
            lbl = QLabel(f"{STATUS_ICON[level]}  {text}")
            lbl.setWordWrap(True)
            lbl.setStyleSheet(f"color:{STATUS[level]}; font-size:10.5pt; padding:2px;")
            v.addWidget(lbl)
        return w

    # ---------------------------------------------------------------- charts
    def _chart(self, title):
        chart = QChart()
        chart.setTitle(title)
        f = QFont()
        f.setPointSize(10)
        f.setBold(True)
        chart.setTitleFont(f)
        chart.setTitleBrush(QColor(NAVY))
        chart.legend().setAlignment(Qt.AlignBottom)
        chart.setMargins(QMargins(4, 4, 4, 4))
        chart.setBackgroundRoundness(8)
        return chart

    def _view(self, chart):
        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setLayoutDirection(Qt.LeftToRight)
        view.setMinimumHeight(310)
        view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        return view

    @staticmethod
    def _value_axis(values, unit):
        ax = QValueAxis()
        ax.setLabelFormat("%.1f" if unit == "بالمليون" else "%.0f")
        ax.setTitleText(unit)
        ax.setGridLineColor(QColor("#eaecf0"))
        ax.setLabelsColor(QColor("#475467"))
        lo = min([v for v in values if v is not None] + [0])
        hi = max([v for v in values if v is not None] + [0])
        pad = (hi - lo) * 0.08 or 1
        ax.setRange(lo - (pad if lo < 0 else 0), hi + pad)
        ax.applyNiceNumbers()
        return ax

    @staticmethod
    def _month_axis(months):
        ax = QBarCategoryAxis()
        ax.append(months)
        f = QFont()
        f.setPointSize(8)
        ax.setLabelsFont(f)
        ax.setLabelsColor(QColor("#475467"))
        return ax

    @staticmethod
    def _tip(text):
        QToolTip.showText(QCursor.pos(), text)

    def _bar_chart(self, title, months, series):
        chart = self._chart(title)
        all_vals = [v for _, vals in series for v in vals]
        div, unit = _scale(all_vals)
        bs = QBarSeries()
        for i, (name, vals) in enumerate(series):
            s = QBarSet(name)
            s.setColor(QColor(SERIES[i % 3]))
            s.setBorderColor(QColor("white"))
            for v in vals:
                s.append((v or 0) / div)
            s.hovered.connect(lambda st, idx, n=name, vv=vals: st and self._tip(f"{n} — {months[idx]}: {_fmt(vv[idx])}"))
            bs.append(s)
        bs.setBarWidth(0.75)
        chart.addSeries(bs)
        ax = self._month_axis(months)
        chart.addAxis(ax, Qt.AlignBottom)
        bs.attachAxis(ax)
        ay = self._value_axis([(v or 0) / div for v in all_vals], unit)
        chart.addAxis(ay, Qt.AlignLeft)
        bs.attachAxis(ay)
        return self._view(chart)

    def _line_chart(self, title, months, series):
        chart = self._chart(title)
        all_vals = [v for _, vals in series for v in vals]
        div, unit = _scale(all_vals)
        ax = self._month_axis(months)
        chart.addAxis(ax, Qt.AlignBottom)
        ay = self._value_axis([(v or 0) / div for v in all_vals], unit)
        chart.addAxis(ay, Qt.AlignLeft)
        for i, (name, vals) in enumerate(series):
            s = QLineSeries()
            s.setName(name)
            pen = QPen(QColor(SERIES[i % 3]))
            pen.setWidth(2)
            s.setPen(pen)
            s.setPointsVisible(True)
            for j, v in enumerate(vals):
                if v is not None:
                    s.append(QPointF(j, v / div))
            s.hovered.connect(lambda pt, st, n=name, vv=vals: st and self._tip(
                f"{n} — {months[max(0, min(len(months) - 1, round(pt.x())))]}: "
                f"{_fmt(vv[max(0, min(len(vv) - 1, round(pt.x())))])}"))
            chart.addSeries(s)
            s.attachAxis(ax)
            s.attachAxis(ay)
        return self._view(chart)

    def _cash_moves_chart(self, title, moves):
        chart = self._chart(title)
        # categories run bottom-up, so reverse to read the list from the top
        names = ["= التغير في النقد"] + list(reversed([SHORT_BUCKETS.get(n, n) for n, _ in moves]))
        bucket_vals = [v for _, v in moves]
        vals = [sum(bucket_vals)] + list(reversed(bucket_vals))
        div, unit = _scale(vals)
        src, use, total = QBarSet("مصدر للنقد"), QBarSet("استخدام للنقد"), QBarSet("التغير في النقد")
        src.setColor(QColor(SERIES[0]))
        use.setColor(QColor(SERIES[1]))
        total.setColor(QColor("#98a2b3"))
        for i, v in enumerate(vals):
            is_total = i == 0
            total.append(v / div if is_total else 0)
            src.append(0 if is_total else max(v, 0) / div)
            use.append(0 if is_total else min(v, 0) / div)
        for s in (src, use, total):
            s.setBorderColor(QColor("white"))
            s.hovered.connect(lambda st, idx: st and self._tip(f"{names[idx]}: {_fmt(vals[idx])}"))
        series = QHorizontalStackedBarSeries()
        series.append(src)
        series.append(use)
        series.append(total)
        series.setBarWidth(0.7)
        chart.addSeries(series)
        ay = QBarCategoryAxis()
        ay.append(names)
        chart.addAxis(ay, Qt.AlignLeft)
        series.attachAxis(ay)
        ax = self._value_axis([v / div for v in vals], unit)
        chart.addAxis(ax, Qt.AlignBottom)
        series.attachAxis(ax)
        v = self._view(chart)
        v.setMinimumHeight(360)
        return v

    def _hbar_chart(self, title, items):
        if not items:
            return None
        chart = self._chart(title)
        items = list(reversed(items))
        names = [n for n, _ in items]
        vals = [v for _, v in items]
        div, unit = _scale(vals)
        s = QBarSet("صافي المبيعات")
        s.setColor(QColor(SERIES[0]))
        for v in vals:
            s.append(v / div)
        s.hovered.connect(lambda st, idx: st and self._tip(f"{names[idx]}: {_fmt(vals[idx])}"))
        series = QHorizontalBarSeries()
        series.append(s)
        series.setBarWidth(0.7)
        chart.addSeries(series)
        chart.legend().hide()
        ay = QBarCategoryAxis()
        ay.append(names)
        chart.addAxis(ay, Qt.AlignLeft)
        series.attachAxis(ay)
        ax = self._value_axis([v / div for v in vals], unit)
        chart.addAxis(ax, Qt.AlignBottom)
        series.attachAxis(ax)
        v = self._view(chart)
        v.setMinimumHeight(360)
        return v

    # ---------------------------------------------------------------- working capital table
    @staticmethod
    def _wc_table(d):
        rows = d["wc_rows"]
        t = QTableWidget(len(rows), 5)
        t.setHorizontalHeaderLabels(["البند", f"نهاية {d['wc_first']}", f"نهاية {d['label']}", "التغير", "التغير %"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.setStyleSheet(f"QHeaderView::section {{ background:{NAVY}; color:white; font-weight:600; padding:4px; }}")
        for r, (label, a, z, f) in enumerate(rows):
            t.setItem(r, 0, QTableWidgetItem(label))
            ch = None if a is None or z is None else z - a
            pc = None if a in (None, 0) or z is None else (z - a) / abs(a)
            for c, (v, ff) in enumerate(((a, f), (z, f), (ch, f), (pc, "%")), start=1):
                it = QTableWidgetItem(render.cell_text(v, "d" if ff == "d" else ff))
                it.setTextAlignment(Qt.AlignAbsolute | Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, it)
            if r == 3:
                for c in range(5):
                    t.item(r, c).setBackground(QColor("#f2f5f9"))
                    fnt = t.item(r, c).font()
                    fnt.setBold(True)
                    t.item(r, c).setFont(fnt)
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, 5):
            t.setColumnWidth(c, 150)
        t.setFixedHeight(t.horizontalHeader().height() + sum(t.rowHeight(r) for r in range(len(rows))) + 6)
        return t

    # ---------------------------------------------------------------- export
    def export_pdf(self):
        if not self.box:
            return
        name = f"{self.win.ctx.company} - لوحة التحكم - {self.data['label']}".replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(self, "حفظ PDF", f"{name}.pdf", "PDF (*.pdf)")
        if not path:
            return
        pix = self.box.grab()
        writer = QPdfWriter(path)
        writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(8, 8, 8, 8),
                                         QPageLayout.Millimeter))
        writer.setResolution(150)
        page = writer.pageLayout().paintRectPixels(writer.resolution())
        scale = page.width() / pix.width()
        src_h = page.height() / scale
        painter = QPainter(writer)
        y = 0.0
        while y < pix.height():
            h = min(src_h, pix.height() - y)
            painter.drawPixmap(QRectF(0, 0, page.width(), h * scale), pix, QRectF(0, y, pix.width(), h))
            y += src_h
            if y < pix.height():
                writer.newPage()
        painter.end()
        QMessageBox.information(self, "معلومة", f"تم الحفظ في:\n{path}")

    def export_excel(self):
        if not self.data:
            return
        name = f"{self.win.ctx.company} - لوحة التحكم - {self.data['label']}".replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(self, "حفظ Excel", f"{name}.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        render.write_excel([dashboard_report(self.data)], self.win.ctx.company, path)
        QMessageBox.information(self, "معلومة", f"تم الحفظ في:\n{path}")


def dashboard_report(d):
    """The dashboard as a report (for Excel export)."""
    blocks = []
    titles = {"profit": "الربحية", "cash": "النقد والتمويل", "wc": "رأس المال العامل"}
    for key, title in titles.items():
        rows = [R.Row(t, [v, l1, l2]) for t, v, l1, l2 in d["cards"][key]]
        blocks.append(R.Table(["البند", "القيمة", "", ""], rows, [None, "t", "t"], title=title))
    blocks.append(R.Table(["الخلاصة والتنبيهات"], [R.Row(text) for _, text in d["alerts"]], title="التنبيهات"))
    ch = d["charts"]
    rows = [R.Row(name, vals) for name, vals in ch["profit"] + ch["cash_vs_profit"][1:] + ch["funding"] + ch["wc"]]
    blocks.append(R.Table(["البند"] + ch["months"], rows, title="بيانات الرسوم الشهرية"))
    blocks.append(R.Table(["البند", "المبلغ"], [R.Row(n, [v]) for n, v in ch["cash_moves"]], title="حركة الكاش من بداية السنة"))
    if ch["branches"]:
        blocks.append(R.Table(["الفرع", "صافي المبيعات"], [R.Row(n, [v]) for n, v in ch["branches"]],
                              title="مبيعات الفروع من بداية السنة"))
    rows = []
    for label, a, z, f in d["wc_rows"]:
        ch_ = None if a is None or z is None else z - a
        rows.append(R.Row(label, [a, z, ch_], fmt=f))
    blocks.append(R.Table(["البند", f"نهاية {d['wc_first']}", f"نهاية {d['label']}", "التغير"], rows,
                          title="تحليل رأس المال العامل"))
    blocks += [R.Para("• " + r) for r in d["reading"]]
    return R.Report("dashboard", "لوحة التحكم", d["label"], blocks)
