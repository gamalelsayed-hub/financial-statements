import os
import sys

from PySide6.QtCore import Qt, QMarginsF, QSettings, QSizeF
from PySide6.QtGui import QAction, QColor, QFont, QPageLayout, QPageSize, QPdfWriter, QTextDocument, QTextOption
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QMainWindow,
    QMessageBox, QPushButton, QSpinBox, QStackedWidget, QStyledItemDelegate, QTableWidget,
    QTableWidgetItem, QTabWidget, QTextBrowser, QToolBar, QVBoxLayout, QWidget,
)

from .. import classifier, engine, importer, reports
from ..categories import BY_KEY, CATEGORIES, GROUP_NAMES, full_label
from ..export_excel import export as export_excel
from ..i18n import lang, set_lang, t

CAT_ROLE = Qt.UserRole + 1
GROUP_COLORS = {"CA": "#1d6fb8", "NCA": "#12355b", "CL": "#b54708", "NCL": "#93370d", "EQ": "#6941c6",
                "REV": "#067647", "EXP": "#b42318", "EXCL": "#667085"}


def resource_path(*parts):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    return os.path.join(base, *parts)


def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# ---------------------------------------------------------------- column mapping
class MappingDialog(QDialog):
    def __init__(self, rows, first, mapping, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.setWindowTitle(t("map_title"))
        self.resize(1000, 640)
        lay = QVBoxLayout(self)
        help_ = QLabel(t("map_help"))
        help_.setWordWrap(True)
        lay.addWidget(help_)

        grid = QGridLayout()
        width = len(rows[0]) if rows else 0
        self.combos = {}
        for i, role in enumerate(importer.ROLES):
            cb = QComboBox()
            cb.addItem(t("not_available"), None)
            for c in range(width):
                hdr = self._header_hint(c, first)
                cb.addItem(f"{t('column')} {col_letter(c)}" + (f" — {hdr}" if hdr else ""), c)
            if mapping.get(role) is not None:
                cb.setCurrentIndex(mapping[role] + 1)
            self.combos[role] = cb
            grid.addWidget(QLabel(t("role_" + role)), i // 4 * 2, i % 4)
            grid.addWidget(cb, i // 4 * 2 + 1, i % 4)
        lay.addLayout(grid)

        row = QHBoxLayout()
        row.addWidget(QLabel(t("first_row")))
        self.first = QSpinBox()
        self.first.setRange(1, max(1, len(rows)))
        self.first.setValue(first + 1)
        self.first.valueChanged.connect(self._highlight)
        row.addWidget(self.first)
        row.addStretch()
        lay.addLayout(row)

        self.table = QTableWidget(min(len(rows), 60), width)
        self.table.setHorizontalHeaderLabels([col_letter(c) for c in range(width)])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r in range(self.table.rowCount()):
            for c in range(width):
                v = rows[r][c]
                self.table.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
        self.table.resizeColumnsToContents()
        lay.addWidget(self.table, 1)
        self._highlight()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(t("ok"))
        bb.button(QDialogButtonBox.Cancel).setText(t("cancel"))
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _header_hint(self, c, first):
        parts = []
        for r in range(max(0, first - 3), first):
            v = self.rows[r][c]
            if v is not None and str(v).strip():
                parts.append(str(v).strip())
        return " / ".join(parts)[:40]

    def _highlight(self):
        f = self.first.value() - 1
        for r in range(self.table.rowCount()):
            color = QColor("#eef4fb") if r < f else QColor("white")
            for c in range(self.table.columnCount()):
                it = self.table.item(r, c)
                if it:
                    it.setBackground(color)

    def mapping(self):
        return {role: cb.currentData() for role, cb in self.combos.items() if cb.currentData() is not None}

    def first_row(self):
        return self.first.value() - 1

    def _accept(self):
        m = self.mapping()
        has_close = "cd" in m or "cc" in m
        has_open_mov = ("od" in m or "oc" in m) and ("md" in m or "mc" in m)
        if "name" not in m or not (has_close or has_open_mov):
            QMessageBox.warning(self, t("warning"), t("need_name_amounts"))
            return
        self.accept()


# ---------------------------------------------------------------- import page
class ImportPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        self.help = QLabel()
        self.help.setWordWrap(True)
        self.help.setStyleSheet("font-size: 11pt; padding: 6px; background:#eef4fb; border-radius:6px;")
        lay.addWidget(self.help)

        btns = QHBoxLayout()
        self.btn_file = QPushButton()
        self.btn_file.setMinimumHeight(40)
        self.btn_file.setStyleSheet("font-size: 11pt; font-weight: 600;")
        self.btn_file.clicked.connect(self.choose_file)
        self.btn_sample = QPushButton()
        self.btn_sample.clicked.connect(lambda: self.load_file(resource_path("sample", "sample_trial_balance.xlsx")))
        self.btn_template = QPushButton()
        self.btn_template.clicked.connect(self.save_template)
        btns.addWidget(self.btn_file, 2)
        btns.addWidget(self.btn_sample, 1)
        btns.addWidget(self.btn_template, 1)
        lay.addLayout(btns)

        form = QFormLayout()
        self.company = QLineEdit()
        self.period = QLineEdit()
        self.months = QSpinBox()
        self.months.setRange(1, 24)
        self.months.setValue(12)
        self.lbl_company, self.lbl_period, self.lbl_months = QLabel(), QLabel(), QLabel()
        form.addRow(self.lbl_company, self.company)
        form.addRow(self.lbl_period, self.period)
        form.addRow(self.lbl_months, self.months)
        lay.addLayout(form)

        self.summary = QTextBrowser()
        lay.addWidget(self.summary, 1)
        self.btn_next = QPushButton()
        self.btn_next.setMinimumHeight(38)
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(lambda: self.win.go(1))
        lay.addWidget(self.btn_next)
        self.retranslate()

    def retranslate(self):
        self.help.setText(t("import_help"))
        self.btn_file.setText(t("choose_file"))
        self.btn_sample.setText(t("load_sample"))
        self.btn_template.setText(t("download_template"))
        self.lbl_company.setText(t("company"))
        self.lbl_period.setText(t("period"))
        self.lbl_months.setText(t("months"))
        self.btn_next.setText(t("next_classify"))
        if self.win.accounts:
            self.show_summary()
        else:
            self.summary.setHtml(f"<p style='color:#667085'>{t('no_file')}</p>")

    def choose_file(self):
        start = QSettings().value("last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, t("choose_file"), start,
                                              "Excel / CSV (*.xlsx *.xlsm *.csv *.txt)")
        if path:
            QSettings().setValue("last_dir", os.path.dirname(path))
            self.load_file(path)

    def load_file(self, path):
        try:
            rows = importer.read_table(path)
        except Exception as e:  # noqa: BLE001 - shown to the user
            QMessageBox.critical(self, t("error"), t("read_error", e=e))
            return
        first, mapping = importer.guess_mapping(rows)
        dlg = MappingDialog(rows, first, mapping, self)
        if dlg.exec() != QDialog.Accepted:
            return
        accounts = importer.build_accounts(rows, dlg.first_row(), dlg.mapping())
        if not accounts:
            QMessageBox.warning(self, t("warning"), t("no_data_rows"))
            return
        if not self.company.text().strip():
            title = next((str(v) for r in rows[:dlg.first_row()] for v in r if importer.is_text(v)), "")
            self.company.setText(title.split(" - ")[0][:80] if title else os.path.splitext(os.path.basename(path))[0])
        self.win.set_accounts(accounts, path)

    def show_summary(self):
        w = self.win
        leaves = [a for a in w.accounts if a.category != "exclude"]
        totals, problems = importer.validate(leaves)
        a = "right" if lang() == "ar" else "left"
        html = f"<h3>{t('loaded_summary', n=len(w.accounts), f=os.path.basename(w.source))}</h3>"
        if w.parent_count:
            html += f"<p style='color:#1d6fb8'>{t('parents_excluded', n=w.parent_count)}</p>"
        html += f"<table border='1' cellspacing='0' cellpadding='5' dir='{'rtl' if lang() == 'ar' else 'ltr'}'>"
        html += f"<tr><th></th><th>{t('debit')}</th><th>{t('credit')}</th><th></th></tr>"
        for d, c, lbl in (("od", "oc", "opening"), ("md", "mc", "movement"), ("cd", "cc", "closing")):
            diff = totals[d] - totals[c]
            res = (f"<span style='color:#067647'>{t('balanced')}</span>" if abs(diff) < 0.5
                   else f"<span style='color:#b42318'>{t('difference', d=reports.fmt(diff, 2))}</span>")
            html += (f"<tr><td align='{a}'><b>{t(lbl)}</b></td><td align='right'>{reports.fmt(totals[d], 2)}</td>"
                     f"<td align='right'>{reports.fmt(totals[c], 2)}</td><td>{res}</td></tr>")
        html += "</table>"
        rows_bad = [p for p in problems if p[0] == "row"]
        if rows_bad:
            html += f"<p style='color:#b54708'>{t('row_problems', n=len(rows_bad))}</p><ul>"
            html += "".join(f"<li>{p[1]} — {p[2]} ({reports.fmt(p[3], 2)})</li>" for p in rows_bad[:15]) + "</ul>"
        self.summary.setHtml(html)
        self.btn_next.setEnabled(True)

    def save_template(self):
        path, _ = QFileDialog.getSaveFileName(self, t("download_template"), "trial_balance_template.xlsx", "Excel (*.xlsx)")
        if not path:
            return
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.sheet_view.rightToLeft = lang() == "ar"
        ws.append([t("role_code"), t("role_name"), t("role_od"), t("role_oc"), t("role_md"), t("role_mc"),
                   t("role_cd"), t("role_cc")])
        for col, wdt in zip("ABCDEFGH", (14, 36, 16, 16, 16, 16, 16, 16)):
            ws.column_dimensions[col].width = wdt
        wb.save(path)
        QMessageBox.information(self, t("info"), t("exported", p=path))


# ---------------------------------------------------------------- classification page
class CategoryDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        cb = QComboBox(parent)
        cb.addItem(t("unclassified"), None)
        last_group = None
        for c in CATEGORIES:
            if c.group != last_group:
                if last_group is not None:
                    cb.insertSeparator(cb.count())
                last_group = c.group
            cb.addItem(full_label(c.key, lang()), c.key)
        cb.setMaxVisibleItems(25)
        cb.activated.connect(lambda _=None, e=cb: (self.commitData.emit(e), self.closeEditor.emit(e)))
        return cb

    def setEditorData(self, editor, index):
        key = index.data(CAT_ROLE)
        i = editor.findData(key) if key else 0
        editor.setCurrentIndex(max(0, i))
        editor.showPopup()

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentData(), CAT_ROLE)


class ClassifyPage(QWidget):
    COLS = ["col_code", "col_name", "col_closing", "col_movement", "col_category"]

    def __init__(self, win):
        super().__init__()
        self.win = win
        self._loading = False
        lay = QVBoxLayout(self)
        self.help = QLabel()
        self.help.setWordWrap(True)
        self.help.setStyleSheet("padding: 6px; background:#eef4fb; border-radius:6px;")
        lay.addWidget(self.help)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.textChanged.connect(self.apply_filter)
        self.only_unc = QCheckBox()
        self.only_unc.toggled.connect(self.apply_filter)
        self.bulk = QComboBox()
        self.btn_apply = QPushButton()
        self.btn_apply.clicked.connect(self.apply_selected)
        bar.addWidget(self.search, 2)
        bar.addWidget(self.only_unc)
        bar.addWidget(self.bulk, 2)
        bar.addWidget(self.btn_apply)
        lay.addLayout(bar)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.SelectedClicked | QAbstractItemView.DoubleClicked |
                                   QAbstractItemView.EditKeyPressed)
        self.table.setItemDelegateForColumn(4, CategoryDelegate(self.table))
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.itemChanged.connect(self.on_item_changed)
        lay.addWidget(self.table, 1)

        bottom = QHBoxLayout()
        self.count = QLabel()
        self.btn_suggest = QPushButton()
        self.btn_suggest.clicked.connect(self.auto_suggest)
        self.btn_save = QPushButton()
        self.btn_save.clicked.connect(self.save_mapping)
        self.btn_load = QPushButton()
        self.btn_load.clicked.connect(self.load_mapping)
        self.btn_go = QPushButton()
        self.btn_go.setMinimumHeight(38)
        self.btn_go.setStyleSheet("font-weight:700; background:#12355b; color:white; padding:0 18px;")
        self.btn_go.clicked.connect(self.confirm)
        bottom.addWidget(self.count)
        bottom.addStretch()
        for b in (self.btn_suggest, self.btn_save, self.btn_load, self.btn_go):
            bottom.addWidget(b)
        lay.addLayout(bottom)
        self.retranslate()

    def retranslate(self):
        self.help.setText(t("classify_help"))
        self.search.setPlaceholderText(t("search"))
        self.only_unc.setText(t("only_unclassified"))
        self.btn_apply.setText(t("apply_selected"))
        self.btn_suggest.setText(t("auto_suggest"))
        self.btn_save.setText(t("save_mapping"))
        self.btn_load.setText(t("load_mapping"))
        self.btn_go.setText(t("confirm_generate"))
        self.table.setHorizontalHeaderLabels([t(c) for c in self.COLS])
        self.bulk.clear()
        last = None
        for c in CATEGORIES:
            if c.group != last and last is not None:
                self.bulk.insertSeparator(self.bulk.count())
            last = c.group
            self.bulk.addItem(full_label(c.key, lang()), c.key)
        self.bulk.setMaxVisibleItems(25)
        self.refresh_labels()

    def load(self):
        self._loading = True
        accs = self.win.accounts
        self.table.setRowCount(len(accs))
        for r, a in enumerate(accs):
            code = QTableWidgetItem(a.code)
            code.setFlags(code.flags() & ~Qt.ItemIsEditable)
            name = QTableWidgetItem(a.name)
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(r, 0, code)
            self.table.setItem(r, 1, name)
            for c, val in ((2, a.close_net), (3, a.mov_net)):
                it = QTableWidgetItem()
                it.setData(Qt.UserRole, val)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, it)
            cat = QTableWidgetItem()
            cat.setData(CAT_ROLE, a.category)
            self.table.setItem(r, 4, cat)
        self._loading = False
        self.refresh_labels()
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)

    def refresh_labels(self):
        self._loading = True
        for r in range(self.table.rowCount()):
            for c in (2, 3):
                it = self.table.item(r, c)
                v = it.data(Qt.UserRole) or 0.0
                it.setText("-" if abs(v) < 0.005 else f"{abs(v):,.2f} {t('dr') if v > 0 else t('cr')}")
            it = self.table.item(r, 4)
            key = it.data(CAT_ROLE)
            if key:
                it.setText(full_label(key, lang()))
                it.setForeground(QColor(GROUP_COLORS[BY_KEY[key].group]))
                it.setBackground(QColor("#f2f4f7") if key == "exclude" else QColor(0, 0, 0, 0))
            else:
                it.setText(t("unclassified"))
                it.setForeground(QColor("#b42318"))
                it.setBackground(QColor("#fee4e2"))
        self._loading = False
        self.update_count()

    def on_item_changed(self, item):
        if self._loading or item.column() != 4:
            return
        self.win.accounts[item.row()].category = item.data(CAT_ROLE)
        self.refresh_labels()
        self.apply_filter()

    def update_count(self):
        accs = self.win.accounts
        done = sum(1 for a in accs if a.category)
        self.count.setText(t("classified_count", a=done, b=len(accs)))

    def apply_filter(self):
        q = self.search.text().strip().lower()
        only = self.only_unc.isChecked()
        for r, a in enumerate(self.win.accounts):
            hide = (q and q not in a.name.lower() and q not in a.code.lower()) or (only and a.category)
            self.table.setRowHidden(r, bool(hide))

    def apply_selected(self):
        key = self.bulk.currentData()
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        for r in rows:
            self.win.accounts[r].category = key
            self._loading = True
            self.table.item(r, 4).setData(CAT_ROLE, key)
            self._loading = False
        self.refresh_labels()
        self.apply_filter()

    def auto_suggest(self):
        for a in self.win.accounts:
            if not a.category:
                a.category = classifier.suggest(a.name)
        self.load()
        self.apply_filter()

    def save_mapping(self):
        path, _ = QFileDialog.getSaveFileName(self, t("save_mapping"), "classification.json", "JSON (*.json)")
        if path:
            classifier.export_mapping(self.win.accounts, path)
            QMessageBox.information(self, t("info"), t("exported", p=path))

    def load_mapping(self):
        path, _ = QFileDialog.getOpenFileName(self, t("load_mapping"), "", "JSON (*.json)")
        if not path:
            return
        try:
            n = classifier.apply_mapping(self.win.accounts, classifier.import_mapping(path))
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, t("error"), t("read_error", e=e))
            return
        self.load()
        QMessageBox.information(self, t("info"), t("mapping_applied", n=n))

    def confirm(self):
        missing = [a for a in self.win.accounts if not a.category]
        if missing:
            QMessageBox.warning(self, t("warning"), t("unclassified_left", n=len(missing)))
            self.only_unc.setChecked(True)
            return
        classifier.save_memory(self.win.accounts)
        self.win.generate()
        self.win.go(2)


# ---------------------------------------------------------------- statements / analysis
class StatementsPage(QWidget):
    TABS = [("bs", "tab_bs"), ("is", "tab_is"), ("cf", "tab_cf"), ("eq", "tab_eq"),
            ("notes", "tab_notes"), ("checks", "tab_checks")]

    def __init__(self):
        super().__init__()
        lay = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.views = {}
        for key, _ in self.TABS:
            v = QTextBrowser()
            v.setOpenExternalLinks(False)
            self.views[key] = v
            self.tabs.addTab(v, "")
        lay.addWidget(self.tabs)
        self.retranslate()

    def retranslate(self):
        for i, (_, label) in enumerate(self.TABS):
            self.tabs.setTabText(i, t(label))

    def show(self, pages):
        for key, _ in self.TABS:
            self.views[key].setHtml(pages[key])


# ---------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.accounts = []
        self.source = ""
        self.parent_count = 0
        self.statements = None
        self.resize(1250, 820)

        tb = QToolBar()
        tb.setMovable(False)
        tb.setStyleSheet("QToolBar { spacing: 8px; padding: 4px; } QToolButton { padding: 6px 12px; font-weight:600; }")
        self.addToolBar(tb)
        self.act_lang = QAction(self)
        self.act_lang.triggered.connect(self.toggle_lang)
        self.act_xlsx = QAction(self)
        self.act_xlsx.triggered.connect(self.export_xlsx)
        self.act_pdf = QAction(self)
        self.act_pdf.triggered.connect(self.export_pdf)
        tb.addAction(self.act_xlsx)
        tb.addAction(self.act_pdf)
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding, spacer.sizePolicy().verticalPolicy())
        tb.addWidget(spacer)
        tb.addAction(self.act_lang)

        central = QWidget()
        h = QHBoxLayout(central)
        self.nav = QListWidget()
        self.nav.setFixedWidth(220)
        self.nav.setStyleSheet(
            "QListWidget { background:#12355b; color:white; font-size:11pt; border:none; }"
            "QListWidget::item { padding:14px 10px; }"
            "QListWidget::item:selected { background:#1d6fb8; }"
            "QListWidget::item:disabled { color:#8ea3bd; }")
        for _ in range(4):
            self.nav.addItem("")
        self.nav.currentRowChanged.connect(self._nav_changed)
        self.stack = QStackedWidget()
        self.import_page = ImportPage(self)
        self.classify_page = ClassifyPage(self)
        self.statements_page = StatementsPage()
        self.analysis = QTextBrowser()
        for w in (self.import_page, self.classify_page, self.statements_page, self.analysis):
            self.stack.addWidget(w)
        h.addWidget(self.nav)
        h.addWidget(self.stack, 1)
        self.setCentralWidget(central)
        self.retranslate()
        self.update_nav()
        self.nav.setCurrentRow(0)

    # -- navigation
    def update_nav(self):
        enabled = [True, bool(self.accounts), self.statements is not None, self.statements is not None]
        for i, en in enumerate(enabled):
            it = self.nav.item(i)
            flags = it.flags()
            it.setFlags(flags | Qt.ItemIsEnabled if en else flags & ~Qt.ItemIsEnabled)
        self.act_xlsx.setEnabled(self.statements is not None)
        self.act_pdf.setEnabled(self.statements is not None)

    def go(self, i):
        self.update_nav()
        self.nav.setCurrentRow(i)

    def _nav_changed(self, i):
        if i >= 0:
            self.stack.setCurrentIndex(i)

    # -- data flow
    def set_accounts(self, accounts, source):
        parents = importer.mark_parent_accounts(accounts)
        memory = classifier.load_memory()
        for a in accounts:
            a.category = None
        restored = classifier.apply_mapping(accounts, memory) if memory else 0
        for a in accounts:
            if a.category is None:
                a.category = "exclude" if a.code in parents else classifier.suggest(a.name)
        self.parent_count = sum(1 for a in accounts if a.category == "exclude" and a.code in parents)
        self.accounts = accounts
        self.source = source
        self.statements = None
        self.import_page.show_summary()
        self.classify_page.load()
        self.update_nav()
        if restored:
            self.statusBar().showMessage(t("memory_applied", n=restored), 8000)

    def meta(self):
        p = self.import_page
        return {"company": p.company.text().strip() or "—",
                "period": p.period.text().strip() or "—",
                "months": p.months.value()}

    def generate(self):
        self.statements = engine.build(self.accounts, self.meta()["months"])
        self.render()
        self.update_nav()

    def render(self):
        if not self.statements:
            return
        pages = reports.screen_pages(self.statements, self.meta())
        self.statements_page.show(pages)
        self.analysis.setHtml(pages["ratios"])

    # -- language
    def toggle_lang(self):
        set_lang("en" if lang() == "ar" else "ar")
        QSettings().setValue("lang", lang())
        self.retranslate()

    def retranslate(self):
        QApplication.instance().setLayoutDirection(Qt.RightToLeft if lang() == "ar" else Qt.LeftToRight)
        self.setWindowTitle(t("app_title"))
        self.act_lang.setText("🌐 " + t("language"))
        self.act_xlsx.setText("📊 " + t("export_excel"))
        self.act_pdf.setText("📄 " + t("export_pdf"))
        for i, k in enumerate(("step_import", "step_classify", "step_statements", "step_analysis")):
            self.nav.item(i).setText(t(k))
        self.import_page.retranslate()
        self.classify_page.retranslate()
        self.statements_page.retranslate()
        self.render()

    # -- export
    def _default_name(self, ext):
        name = self.meta()["company"].replace("/", "-").strip("— ") or "financial_statements"
        start = QSettings().value("last_dir", os.path.expanduser("~"))
        return os.path.join(start, f"{name} - {t('app_title') if lang() == 'en' else 'القوائم المالية'}.{ext}")

    def export_xlsx(self):
        if not self.statements:
            return
        path, _ = QFileDialog.getSaveFileName(self, t("export_excel"), self._default_name("xlsx"), "Excel (*.xlsx)")
        if not path:
            return
        try:
            export_excel(self.statements, self.meta(), self.accounts, path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, t("error"), str(e))
            return
        QMessageBox.information(self, t("info"), t("exported", p=path))

    def export_pdf(self):
        if not self.statements:
            return
        path, _ = QFileDialog.getSaveFileName(self, t("export_pdf"), self._default_name("pdf"), "PDF (*.pdf)")
        if path:
            write_pdf(reports.full_report(self.statements, self.meta()), path)
            QMessageBox.information(self, t("info"), t("exported", p=path))


def write_pdf(html, path):
    writer = QPdfWriter(path)
    writer.setPageLayout(QPageLayout(QPageSize(QPageSize.A4), QPageLayout.Portrait, QMarginsF(12, 12, 12, 12),
                                     QPageLayout.Millimeter))
    writer.setResolution(96)
    doc = QTextDocument()
    font = QFont("Segoe UI" if sys.platform == "win32" else "DejaVu Sans", 9)
    doc.setDefaultFont(font)
    opt = QTextOption()
    opt.setTextDirection(Qt.RightToLeft if lang() == "ar" else Qt.LeftToRight)
    doc.setDefaultTextOption(opt)
    doc.setHtml(html)
    rect = writer.pageLayout().paintRectPixels(writer.resolution())
    doc.setPageSize(QSizeF(rect.width(), rect.height()))
    doc.print_(writer)
