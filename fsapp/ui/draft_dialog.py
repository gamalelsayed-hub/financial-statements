"""Window for the draft financial statements: header/signature, checks, line mapping, export to Excel / PDF."""
import base64
import os
import tempfile

from PySide6.QtCore import QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from ..system import calc
from ..system import draft as DR
from ..system import draft_export as DX
from ..system.defaults import BS_SECTIONS, SECTION_NAMES

OPTS = {"legal_form": ("draft_legal_form", "(شركة ذات مسؤولية محدودة)"), "currency": ("draft_currency", "ريال سعودي"),
        "sign_title": ("draft_sign_title", "المدير المالي"), "sign_name": ("draft_sign_name", "")}


class MappingDialog(QDialog):
    """FS item → draft line, with the current value to help choosing."""

    def __init__(self, parent, ctx, end):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle("ربط بنود البرنامج ببنود المسودة")
        self.resize(900, 640)
        lay = QVBoxLayout(self)
        note = QLabel("كل بند من بنود البرنامج يظهر في المسودة تحت البند المختار هنا. الاختيار يُحفظ في ملف الشركة.")
        note.setWordWrap(True)
        lay.addWidget(note)
        mapping = DR.load_map(ctx)
        bs, is_ = ctx.bs_figures([end], 2)["items"], ctx.is_figures([end], ytd=True)["items"]
        items = [i for i in ctx.fs_order if i in mapping]
        self.table = QTableWidget(len(items), 4)
        self.table.setHorizontalHeaderLabels(["بند البرنامج", "القسم", "الرصيد", "بند المسودة"])
        self.table.verticalHeader().setVisible(False)
        self.combos = {}
        for r, item in enumerate(items):
            sec = ctx.fs_section.get(item, "")
            value = bs.get(item, is_.get(item, 0.0))
            for c, text in enumerate((item, SECTION_NAMES.get(sec, sec), f"{value:,.0f}")):
                it = QTableWidgetItem(text)
                it.setFlags(it.flags() & ~Qt.ItemIsEditable)
                if c == 2:
                    it.setTextAlignment(Qt.AlignAbsolute | Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, it)
            cb = QComboBox()
            lines = DR.BS_LINES if sec in BS_SECTIONS else DR.IS_LINES
            for key, label, *_ in lines:
                cb.addItem(label, key)
            cb.setCurrentIndex(max(0, cb.findData(mapping[item])))
            self.table.setCellWidget(r, 3, cb)
            self.combos[item] = cb
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(3, 300)
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        b = QPushButton("↩ الرجوع للربط الافتراضي")
        b.clicked.connect(self.reset)
        row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        bb = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Save).setText("حفظ")
        bb.button(QDialogButtonBox.Cancel).setText("إلغاء")
        bb.accepted.connect(self.save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def reset(self):
        for item, cb in self.combos.items():
            sec = self.ctx.fs_section.get(item, "")
            cb.setCurrentIndex(max(0, cb.findData(DR.default_line(item, sec, self.ctx.fs_role.get(item, "")))))

    def save(self):
        DR.save_map(self.ctx.db, {item: cb.currentData() for item, cb in self.combos.items()})
        self.accept()


class DraftDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.db = win.db
        self.setWindowTitle("مسودة القوائم المالية")
        self.resize(760, 620)
        lay = QVBoxLayout(self)
        self.period = QLabel()
        self.period.setStyleSheet("font-weight:700; color:#12355b;")
        self.period.setWordWrap(True)
        lay.addWidget(self.period)
        f = QFormLayout()
        self.fields = {}
        for key, label in (("legal_form", "الشكل القانوني (تحت اسم الشركة):"), ("currency", "العملة:"),
                           ("sign_title", "صفة الموقّع:"), ("sign_name", "اسم الموقّع:")):
            setting, default = OPTS[key]
            e = QLineEdit(self.db.setting(setting, default))
            self.fields[key] = e
            f.addRow(label, e)
        logo_row = QHBoxLayout()
        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(120, 60)
        self.logo_lbl.setStyleSheet("border:1px solid #d0d5dd; background:white;")
        self.logo_lbl.setAlignment(Qt.AlignCenter)
        logo_row.addWidget(self.logo_lbl)
        for text, fn in (("اختيار الشعار", self.pick_logo), ("حذف", self.clear_logo)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            logo_row.addWidget(b)
        logo_row.addStretch()
        f.addRow("الشعار:", logo_row)
        lay.addLayout(f)
        lay.addWidget(QLabel("المراجعة قبل التصدير:"))
        self.checks = QPlainTextEdit()
        self.checks.setReadOnly(True)
        lay.addWidget(self.checks, 1)
        row = QHBoxLayout()
        for text, fn in (("🔗 ربط البنود", self.edit_mapping), ("📊 تصدير Excel", lambda: self.export("xlsx")),
                         ("📄 تصدير PDF", lambda: self.export("pdf"))):
            b = QPushButton(text)
            b.setMinimumHeight(34)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        self.show_logo()
        self.refresh()

    # ---------------------------------------------------------------- data
    def end(self):
        return self.win.current_period()

    def refresh(self):
        end = self.end()
        ctx = self.win.ctx
        if not end:
            self.period.setText("لا توجد بيانات — ارفع ميزان شهر أولًا.")
            self.dr = None
            return
        self.dr = DR.build(ctx, end)
        labels = DX.period_labels(self.dr, ctx)
        self.period.setText(f"الفترة: من {labels['start']} إلى {labels['end']}   |   المقارنة: "
                            f"{labels['comp'] or 'لا توجد'}\n(لتغيير الفترة اختر «الفترة المنتهية في» من الشريط العلوي)")
        t = DR.bs_totals(self.dr.cur.bs)
        lines = [f"إجمالي الموجودات: {t['assets']:,.0f}", f"إجمالي المطلوبات وحقوق الشركاء: {t['le']:,.0f}",
                 f"صافي الدخل: {DR.is_totals(self.dr.cur.is_)['ni']:,.0f}"]
        if self.dr.cf_cur:
            lines.append(f"رصيد النقد آخر المدة: {self.dr.cf_cur['close']:,.0f} (التدفقات تطابق: "
                         f"{'نعم' if abs(self.dr.cf_cur['diff']) <= 1 else 'لا'})")
        lines.append("")
        lines += self.dr.checks or ["✔ لا توجد ملاحظات — القوائم متوازنة والتدفقات تطابق النقد."]
        self.checks.setPlainText("\n".join(lines))

    def opts(self):
        return {k: e.text().strip() for k, e in self.fields.items()}

    def save_opts(self):
        for k, e in self.fields.items():
            self.db.set_setting(OPTS[k][0], e.text().strip())

    # ---------------------------------------------------------------- logo
    def logo_bytes(self):
        try:
            return base64.b64decode(self.db.setting("draft_logo", "") or "")
        except ValueError:
            return b""

    def show_logo(self):
        data = self.logo_bytes()
        pix = QPixmap()
        if data and pix.loadFromData(data):
            self.logo_lbl.setPixmap(pix.scaled(110, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo_lbl.setPixmap(QPixmap())
            self.logo_lbl.setText("بدون شعار")

    def pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, "الشعار", os.path.expanduser("~"), "صور (*.png *.jpg *.jpeg)")
        if path:
            with open(path, "rb") as fh:
                self.db.set_setting("draft_logo", base64.b64encode(fh.read()).decode("ascii"))
            self.show_logo()

    def clear_logo(self):
        self.db.set_setting("draft_logo", "")
        self.show_logo()

    # ---------------------------------------------------------------- actions
    def edit_mapping(self):
        if not self.end():
            return
        if MappingDialog(self, self.win.ctx, self.end()).exec() == QDialog.Accepted:
            self.win.ctx = calc.Ctx(self.db)
            self.refresh()

    def export(self, fmt):
        if not self.dr:
            return
        self.save_opts()
        name = f"{self.win.ctx.company} - مسودة القوائم المالية - {calc.month_label(self.end())}"
        name = name.replace("/", "-").replace(":", " ")
        start = QSettings().value("last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getSaveFileName(self, "حفظ المسودة", os.path.join(start, f"{name}.{fmt}"),
                                              "Excel (*.xlsx)" if fmt == "xlsx" else "PDF (*.pdf)")
        if not path:
            return
        try:
            if fmt == "xlsx":
                DX.to_excel(self.dr, self.win.ctx, path, self.opts())
            else:
                logo = ""
                data = self.logo_bytes()
                if data:
                    logo = os.path.join(tempfile.mkdtemp(prefix="fs-"), "logo.png")
                    with open(logo, "wb") as fh:
                        fh.write(data)
                DX.to_pdf(self.dr, self.win.ctx, path, self.opts(), logo)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "خطأ", f"تعذر التصدير:\n{e}")
            return
        QSettings().setValue("last_dir", os.path.dirname(path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
