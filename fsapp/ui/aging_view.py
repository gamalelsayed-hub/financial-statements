"""Customers and suppliers screen: full lists with filters, sorting and export of the filtered list."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

from ..system import aging as AG
from ..system import render
from ..system import reports as R
from ..system.calc import month_label
from .table_tools import freeze
from .zoom import pt

NAVY = "#12355b"
ALL = "الكل"


class AgingList(QWidget):
    """One list (customers or suppliers). Subclasses define columns, filters and row values."""
    TITLE = ""
    COLUMNS = []      # (header, key, fmt) fmt: t | n | % | d
    FILTERS = []      # (label, field) choices are filled from the data
    DEFAULT_SORT = ""  # key of the amount column sorted highest first by default

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.rows = []
        self.visible = []
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("بحث بالاسم أو الرقم...")
        self.search.textChanged.connect(self.apply)
        bar.addWidget(self.search, 2)
        self.filters = {}
        for label, field in self.FILTERS:
            bar.addWidget(QLabel(label))
            cb = QComboBox()
            cb.setMinimumWidth(110)
            cb.currentIndexChanged.connect(self.apply)
            self.filters[field] = cb
            bar.addWidget(cb, 1)
        self.only_over = QCheckBox(self.ONLY_LABEL)
        self.only_over.toggled.connect(self.apply)
        bar.addWidget(self.only_over)
        lay.addLayout(bar)
        bottom_bar = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setStyleSheet(f"color:{NAVY}; font-weight:700; padding:4px;")
        bottom_bar.addWidget(self.summary, 1)
        clear = QPushButton("مسح الفلاتر")
        clear.clicked.connect(self.clear_filters)
        bottom_bar.addWidget(clear)
        for text, fn in (("📊 تصدير Excel", lambda: self.export("xlsx")), ("📄 تصدير PDF", lambda: self.export("pdf"))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            bottom_bar.addWidget(b)
        lay.addLayout(bottom_bar)
        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self.COLUMNS])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(f"QHeaderView::section {{ background:{NAVY}; color:white; font-weight:600; padding:4px; }}")
        header = self.table.horizontalHeader()
        header.setSectionsClickable(True)
        header.setSortIndicatorShown(True)
        header.sectionClicked.connect(self.sort_by)
        self.sort_key = self.DEFAULT_SORT
        self.sort_desc = True
        freeze(self.table, 2)          # number and name stay visible when scrolling sideways
        lay.addWidget(self.table, 1)

    # ---- data
    def load(self):
        params = self.win.params()
        self.period = params.end if params else None
        self.rows = [self.enrich(r) for r in self.win.db.aging(self.TABLE, self.period)] if self.period else []
        for field, cb in self.filters.items():
            cur = cb.currentText()
            cb.blockSignals(True)
            cb.clear()
            values = sorted({str(r.get(field) or "").strip() or "—" for r in self.rows})
            cb.addItems([ALL] + values)
            i = cb.findText(cur)
            cb.setCurrentIndex(max(0, i))
            cb.blockSignals(False)
        self.apply()

    def clear_filters(self):
        self.search.clear()
        for cb in self.filters.values():
            cb.setCurrentIndex(0)
        self.only_over.setChecked(False)

    def matches(self, r):
        q = self.search.text().strip().lower()
        if q and q not in (str(r.get("name") or "") + " " + str(r.get("no") or "")).lower():
            return False
        for field, cb in self.filters.items():
            v = cb.currentText()
            if v != ALL and (str(r.get(field) or "").strip() or "—") != v:
                return False
        return not self.only_over.isChecked() or r["_flag"]

    def sort_by(self, col):
        """Amount columns sort highest first on the first click; a second click reverses."""
        key, fmt = self.COLUMNS[col][1], self.COLUMNS[col][2]
        if key == self.sort_key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_key, self.sort_desc = key, fmt != "t"
        self.apply()

    def _sorted(self, rows):
        fmt = next((f for _, k, f in self.COLUMNS if k == self.sort_key), "n")

        def key(r):
            v = r.get(self.sort_key)
            if fmt == "t":
                return str(v or "")
            return v if isinstance(v, (int, float)) else float("-inf")

        return sorted(rows, key=key, reverse=self.sort_desc)

    def apply(self):
        self.visible = self._sorted([r for r in self.rows if self.matches(r)])
        t = self.table
        t.setRowCount(len(self.visible))
        bold = QFont()
        bold.setBold(True)
        for i, r in enumerate(self.visible):
            for c, (_, key, fmt) in enumerate(self.COLUMNS):
                v = r.get(key)
                text = render.cell_text(v, fmt) if fmt != "t" else ("" if v is None else str(v))
                it = QTableWidgetItem(text)
                if fmt != "t":
                    it.setTextAlignment(Qt.AlignAbsolute | Qt.AlignRight | Qt.AlignVCenter)
                if key == "_status":
                    it.setForeground(QColor("#b42318" if r["_flag"] else "#067647"))
                    it.setFont(bold)
                t.setItem(i, c, it)
        col = next((i for i, c in enumerate(self.COLUMNS) if c[1] == self.sort_key), 0)
        t.horizontalHeader().setSortIndicator(col, Qt.DescendingOrder if self.sort_desc else Qt.AscendingOrder)
        t.resizeColumnsToContents()
        t.setColumnWidth(1, min(max(t.columnWidth(1), 200), 320))
        self.summary.setText(self.summary_text())

    def filter_text(self):
        parts = [f"{label} {cb.currentText()}" for (label, field), cb in zip(self.FILTERS, self.filters.values())
                 if cb.currentText() != ALL]
        if self.only_over.isChecked():
            parts.append(self.ONLY_LABEL)
        if self.search.text().strip():
            parts.append(f"بحث: {self.search.text().strip()}")
        return "، ".join(parts) or "بدون فلتر"

    def export(self, fmt):
        if not self.visible:
            QMessageBox.information(self, "معلومة", "لا توجد صفوف للتصدير.")
            return
        rows = [R.Row(str(r.get(self.COLUMNS[0][1]) or ""), [r.get(k) for _, k, _ in self.COLUMNS[1:]])
                for r in self.visible]
        table = R.Table([c[0] for c in self.COLUMNS], rows, [f for _, _, f in self.COLUMNS[1:]])
        rep = R.Report(self.TABLE, self.TITLE, f"{month_label(self.period)} — {self.filter_text()}",
                       [R.Para(self.summary_text()), table])
        company = self.win.ctx.company
        name = f"{company} - {self.TITLE} - {month_label(self.period)}".replace("/", "-")
        path, _ = QFileDialog.getSaveFileName(self, "حفظ", f"{name}.{fmt}",
                                              "Excel (*.xlsx)" if fmt == "xlsx" else "PDF (*.pdf)")
        if not path:
            return
        if fmt == "xlsx":
            render.write_excel([rep], company, path)
        else:
            from .system_window import write_pdf
            write_pdf(render.reports_html([rep], company), path, landscape=True)
        QMessageBox.information(self, "معلومة", f"تم الحفظ في:\n{path}")


class CustomersList(AgingList):
    TABLE = "customers"
    TITLE = "قائمة العملاء وأعمار أرصدتهم"
    ONLY_LABEL = "المطلوب مطابقتهم فقط"
    DEFAULT_SORT = "_total"
    FILTERS = [("المنطقة:", "region"), ("الفرع:", "branch"), ("المندوب:", "rep"), ("النوع:", "ctype"),
               ("التصنيف:", "cls"), ("المطابقة:", "_status")]
    COLUMNS = [("رقم العميل", "no", "t"), ("اسم العميل", "name", "t"), ("الفرع", "branch", "t"), ("المندوب", "rep", "t"),
               ("الإجمالي", "_total", "n"), ("المتأخر", "_over", "n"), ("طلب المطابقة", "_status", "t"),
               ("نسبة المتأخر", "_over_pct", "%"), ("ضمن المدة", "_within", "n"),
               ("0 - 30", "b0", "n"), ("31 - 60", "b1", "n"), ("61 - 90", "b2", "n"), ("91 - 120", "b3", "n"),
               ("أكثر من 120", "b4", "n"), ("النوع", "ctype", "t"), ("التصنيف", "cls", "t"), ("المنطقة", "region", "t"),
               ("ضمان بنكي", "guarantee", "n")]

    def enrich(self, r):
        r = dict(r)
        r["rep"] = (r.get("rep") or "").strip()
        r["_total"] = AG.customer_total(r)
        r["_over"] = AG.customer_overdue(r)
        r["_within"] = r["_total"] - r["_over"]
        r["_over_pct"] = r["_over"] / r["_total"] if abs(r["_total"]) > 0.005 else None
        r["_flag"] = r["_over"] > 0.005
        r["_status"] = "مطلوب مطابقة" if r["_flag"] else "لا"
        return r

    def summary_text(self):
        v = self.visible
        tot = sum(r["_total"] for r in v)
        over = sum(r["_over"] for r in v)
        need = sum(1 for r in v if r["_flag"])
        return (f"العملاء: {len(v)} من {len(self.rows)}   |   الرصيد: {tot:,.0f}   |   المتأخر: {over:,.0f}"
                f" ({(over / tot if tot else 0):.0%})   |   مطلوب مطابقة: {need} عميل"
                "   |   المتأخر: العهدة أكثر من 30 يوم، وغيرها أكثر من 60 يوم")


class SuppliersList(AgingList):
    TABLE = "suppliers"
    TITLE = "قائمة الموردين وأعمار أرصدتهم"
    ONLY_LABEL = "المتجاوزون لفترة الائتمان فقط"
    DEFAULT_SORT = "_total_base"
    FILTERS = [("النوع:", "_type"), ("العملة:", "currency"), ("الحالة:", "_status")]
    COLUMNS = [("رقم المورد", "no", "t"), ("اسم المورد", "name", "t"), ("النوع", "_type", "t"), ("العملة", "currency", "t"),
               ("فترة الائتمان (يوم)", "credit", "d"), ("الإجمالي بالعملة المحلية", "_total_base", "n"),
               ("المتجاوز بالعملة المحلية", "_over_base", "n"), ("الحالة", "_status", "t"),
               ("الإجمالي", "_total", "n"), ("المتجاوز لفترة الائتمان", "_over", "n"), ("نسبة المتجاوز", "_over_pct", "%"),
               ("0 - 30", "b0", "n"), ("31 - 60", "b1", "n"), ("61 - 90", "b2", "n"), ("91 - 120", "b3", "n"),
               ("أكثر من 120", "b4", "n"), ("سعر الصرف", "_rate", "x"), ("رقم الحساب", "account", "t")]

    def load(self):
        self.rate_map = AG.rates(self.win.db)
        self.base = self.win.ctx.base_currency if self.win.ctx else "SAR"
        super().load()

    def enrich(self, r):
        r = dict(r)
        r["_type"] = AG.supplier_type(r.get("no"))
        r["_total"] = AG.supplier_total(r)
        r["_over"] = AG.supplier_overdue(r)
        r["_over_pct"] = r["_over"] / r["_total"] if abs(r["_total"]) > 0.005 else None
        rate = AG.supplier_rate(r, self.rate_map, self.base)
        r["_rate"] = rate
        r["_total_base"] = None if rate is None else r["_total"] * rate
        r["_over_base"] = None if rate is None else r["_over"] * rate
        r["_flag"] = r["_over"] > 0.005 or rate is None
        r["_status"] = ("بدون سعر صرف" if rate is None else "متجاوز لفترة الائتمان" if r["_over"] > 0.005
                        else "ضمن فترة الائتمان")
        return r

    def summary_text(self):
        v = self.visible
        tot = sum(r["_total_base"] or 0 for r in v)
        over = sum(r["_over_base"] or 0 for r in v)
        n_over = sum(1 for r in v if r["_over"] > 0.005)
        no_rate = sum(1 for r in v if r["_rate"] is None)
        by_type = "، ".join(f"{t} {sum(r['_total_base'] or 0 for r in v if r['_type'] == t):,.0f}"
                            for t in AG.SUPPLIER_TYPES if any(r["_type"] == t for r in v))
        return (f"الموردون: {len(v)} من {len(self.rows)}   |   الإجمالي: {tot:,.0f} {self.base} ({by_type})   |   "
                f"المتجاوز: {over:,.0f} ({(over / tot if tot else 0):.0%}) لدى {n_over} مورد"
                + (f"   |   ⚠ {no_rate} بدون سعر صرف" if no_rate else ""))


class AgingPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        self.head = QLabel()
        self.head.setStyleSheet(f"color:{NAVY}; font-size:{pt(12)}; font-weight:700;")
        lay.addWidget(self.head)
        self.tabs = QTabWidget()
        self.customers = CustomersList(win)
        self.suppliers = SuppliersList(win)
        self.tabs.addTab(self.customers, "العملاء")
        self.tabs.addTab(self.suppliers, "الموردون")
        lay.addWidget(self.tabs)

    def load(self):
        params = self.win.params()
        label = month_label(params.end) if params else "—"
        self.head.setText(f"أعمار العملاء والموردين — {label}   (غيّر الشهر من «الفترة المنتهية في» أعلى الشاشة؛ "
                          "ارفع الأعمار من «البيانات الشهرية»)")
        self.customers.load()
        self.suppliers.load()
