"""Sales reps evaluation screen: the cards board, the ranking, a full report for each rep, collections and
customers' balance check, invoices, and the data (report uploads, rep settings, commissions, weights)."""
import os

from PySide6.QtCore import QMarginsF, QRectF, QSettings, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSpinBox, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget)

from .. import importer
from ..system import calc, render
from ..system import rep_data as D
from ..system import reps as RP
from .progress import Progress
from .zoom import pt

NAVY = "#12355b"
GRADE_COLORS = {"ممتاز": ("#dcfae6", "#067647"), "جيد جداً": ("#e8f5e1", "#3b6d11"), "جيد": ("#fef7c3", "#854d0e"),
                "مقبول": ("#fdead7", "#b54708"), "ضعيف": ("#fee4e2", "#b42318"), RP.NOT_RATED: ("#eaecf0", "#475467")}
SHORT = {"roi": "العائد"}
KIND_LABEL = {"items": "الأصناف بالمندوب", "customers": "العملاء بالمندوب"}


def _num(v, f="n"):
    if v is None:
        return "—"
    if f == "%":
        return f"{v * 100:,.1f}%"
    if f == "x":
        return f"{v:,.1f}"
    return f"{v:,.0f}"


def _btn(text, fn):
    b = QPushButton(text)
    b.setMinimumHeight(32)
    b.clicked.connect(fn)
    return b


def _ask(parent, text):
    return QMessageBox.question(parent, "تأكيد", text) == QMessageBox.Yes


def _months_choice(parent, title, default):
    """Pick a month (year + month)."""
    from .system_window import MonthDialog
    d = MonthDialog(parent, title, default)
    return d.period() if d.exec() == QDialog.Accepted else None


class RangeDialog(QDialog):
    """From month – to month (a sales file for several months)."""

    def __init__(self, parent, title, first, last):
        super().__init__(parent)
        self.setWindowTitle(title)
        f = QFormLayout(self)
        self.boxes = []
        for label, p in (("من شهر:", first), ("إلى شهر:", last)):
            h = QHBoxLayout()
            y, m = QSpinBox(), QComboBox()
            y.setRange(2000, 2100)
            y.setValue(int(p[:4]))
            m.addItems(calc.MONTHS_AR)
            m.setCurrentIndex(int(p[5:7]) - 1)
            h.addWidget(m)
            h.addWidget(y)
            f.addRow(label, h)
            self.boxes.append((y, m))
        note = QLabel("ملف شهر واحد: نفس الشهر في الخانتين. الملف المجمّع لعدة شهور يدخل في أي فترة تحتويه كاملًا، "
                      "ولا ينقسم على الشهور (التقارير لا تفصّله إلا لو رفعت كل شهر لوحده).")
        note.setWordWrap(True)
        f.addRow(note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)

    def months(self):
        a, b = [f"{y.value():04d}-{m.currentIndex() + 1:02d}" for y, m in self.boxes]
        return (a, b) if a <= b else (b, a)


# ================================================================== cards
class RepCard(QFrame):
    def __init__(self, r, ev, on_report):
        super().__init__()
        self.setObjectName("card")
        self.setStyleSheet("QFrame#card { background:white; border:2px solid %s; border-radius:8px; }"
                           "QLabel { border:none; background:transparent; }" % NAVY)
        self.setMinimumWidth(330)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 6)
        v.setSpacing(2)
        head = QFrame()
        head.setStyleSheet(f"background:{NAVY}; border-top-left-radius:6px; border-top-right-radius:6px;")
        hh = QHBoxLayout(head)
        name = QLabel(r.name)
        name.setStyleSheet(f"color:white; font-weight:700; font-size:{pt(12)};")
        rank = QLabel(f"#{r.rank}" if r.rank else "—")
        rank.setStyleSheet(f"color:white; font-weight:700; font-size:{pt(12)};")
        hh.addWidget(name, 1)
        hh.addWidget(rank)
        v.addWidget(head)
        bg, fg = GRADE_COLORS.get(r.grade, GRADE_COLORS[RP.NOT_RATED])
        sc = QFrame()
        sc.setStyleSheet(f"background:{bg};")
        sh = QHBoxLayout(sc)
        score = QLabel(_num(r.score, "x") if r.score is not None else "—")
        score.setStyleSheet(f"color:{fg}; font-weight:800; font-size:{pt(22)};")
        g = QLabel(r.grade)
        g.setStyleSheet(f"color:{fg}; font-weight:700; font-size:{pt(13)};")
        sub = QLabel(f"الكود {r.code} · {r.nationality}")
        sub.setStyleSheet(f"color:#475467; font-size:{pt(8.5)};")
        sh.addWidget(score)
        sh.addWidget(g)
        sh.addStretch()
        sh.addWidget(sub)
        v.addWidget(sc)
        grid = QGridLayout()
        grid.setContentsMargins(10, 4, 10, 0)
        grid.setVerticalSpacing(3)
        row = 0
        for k, label, wt in ev.weights_used():
            if not r.parts:
                break
            got, top = r.parts.get(k, 0.0), wt * 100
            lb = QLabel(f"درجة {SHORT.get(k, label)}")
            lb.setStyleSheet(f"color:{NAVY}; font-weight:600; font-size:{pt(9)};")
            val = QLabel(f"{got:,.1f} / {top:,.0f}")
            val.setStyleSheet(f"color:{NAVY}; font-weight:700; font-size:{pt(9)};")
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(int(1000 * got / top) if top else 0)
            bar.setTextVisible(False)
            bar.setFixedHeight(9)
            bar.setStyleSheet("QProgressBar { background:#eaecf0; border:none; border-radius:4px; }"
                              "QProgressBar::chunk { background:#3b8b3b; border-radius:4px; }")
            grid.addWidget(lb, row, 0)
            grid.addWidget(val, row, 1)
            grid.addWidget(bar, row, 2)
            row += 1
        target = r.target_m * ev.n
        lines = [("صافي المبيعات", _num(r.net)), ("تحقيق التارجت", _num(RP.safe_div(r.net, target), "%") if target else "—"),
                 ("مجمل الربح", _num(r.gp)), ("الهامش", _num(r.margin, "%")),
                 ("تكلفة المندوب", _num(r.rep_cost)), ("العمولة (خارج التكلفة)", _num(r.commission)),
                 ("صافي المساهمة", _num(r.contribution)), ("العائد لكل ريال", _num(r.roi, "x")),
                 ("التحصيل", _num(r.collected) if r.collected else "—"),
                 ("نسبة التحصيل", _num(r.coll_rate, "%")), ("المتأخر من الرصيد", _num(r.overdue_share, "%")),
                 ("الفواتير / متوسطها", f"{r.inv_count:,} / {_num(r.avg_invoice)}" if r.inv_count else "—")]
        top_item = max(r.items.items(), key=lambda kv: kv[1][1] - kv[1][2])[1][0] if r.items else ""
        if top_item:
            lines.append(("أكثر صنف ربحًا", top_item))
        for label, value in lines:
            a, b = QLabel(label), QLabel(value)
            a.setStyleSheet(f"color:#475467; font-size:{pt(9)};")
            b.setStyleSheet(f"color:{'#b42318' if value.startswith('-') else '#101828'}; font-weight:700; font-size:{pt(9)};")
            b.setWordWrap(True)
            grid.addWidget(a, row, 0)
            grid.addWidget(b, row, 1, 1, 2)
            row += 1
        v.addLayout(grid)
        rb = QPushButton("📄 تقرير المندوب")
        rb.setStyleSheet("margin:4px 10px 0 10px;")
        rb.clicked.connect(lambda: on_report(r.code))
        v.addWidget(rb)


class Board(QScrollArea):
    """KPIs of the company + one card per rep, ordered by score."""

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.setWidgetResizable(True)
        self.box = None
        self.last = None
        self.cols = 0

    def _columns(self):
        return max(1, min(4, (self.viewport().width() - 20) // 360))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.last and self._columns() != self.cols:
            self.show_eval(*self.last)

    def show_eval(self, ev, title):
        self.last = (ev, title)
        box = QWidget()
        box.setStyleSheet("background:#f5f7fa;")
        v = QVBoxLayout(box)
        t = QLabel(title)
        t.setStyleSheet(f"color:{NAVY}; font-size:{pt(16)}; font-weight:800;")
        v.addWidget(t)
        tot = ev.totals()
        kp = QGridLayout()
        kpis = [("صافي المبيعات", _num(tot["net"])), ("مجمل الربح", _num(tot["gp"])), ("هامش الشركة", _num(tot["margin"], "%")),
                ("تحقيق التارجت", _num(tot["ach"], "%")), ("تكلفة المناديب", _num(tot["cost"])),
                ("صافي المساهمة", _num(tot["contribution"])), ("التحصيل", _num(tot["collected"])),
                ("نسبة التحصيل", _num(tot["coll_rate"], "%"))]
        for i, (label, value) in enumerate(kpis):
            f = QFrame()
            f.setStyleSheet("QFrame { background:white; border:1px solid #d0d5dd; border-radius:6px; }"
                            "QLabel { border:none; }")
            fv = QVBoxLayout(f)
            a, b = QLabel(label), QLabel(value)
            a.setStyleSheet(f"color:white; background:{NAVY}; padding:3px; font-weight:600; font-size:{pt(9)};")
            a.setAlignment(Qt.AlignCenter)
            b.setStyleSheet(f"color:{NAVY}; font-weight:800; font-size:{pt(14)};")
            b.setAlignment(Qt.AlignCenter)
            fv.addWidget(a)
            fv.addWidget(b)
            kp.addWidget(f, i // 4, i % 4)
        v.addLayout(kp)
        for n in ev.notes:
            lbl = QLabel(n)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color:#b54708; font-weight:600;" if n.startswith("⚠") else "color:#475467;")
            v.addWidget(lbl)
        w = "، ".join(f"{label} {wt * 100:.0f}%" for _, label, wt in ev.weights_used())
        lbl = QLabel(f"الأوزان: {w} — الكروت مرتبة حسب الدرجة.")
        lbl.setStyleSheet("color:#475467;")
        v.addWidget(lbl)
        grid = QGridLayout()
        grid.setSpacing(12)
        cols = self.cols = self._columns()
        for i, r in enumerate(ev.ordered()):
            grid.addWidget(RepCard(r, ev, self.page.open_report), i // cols, i % cols, Qt.AlignTop)
        v.addLayout(grid)
        v.addStretch()
        self.setWidget(box)
        self.box = box

    def export_pdf(self, path):
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


# ================================================================== data and settings
class DataTab(QWidget):
    REP_COLS = [("code", "الكود"), ("name", "المندوب"), ("nationality", "الجنسية (سعودي / مقيم)"),
                ("salary", "الراتب الشهري"), ("target", "التارجت الشهري"), ("other", "تكاليف أخرى شهرية"),
                ("active", "يدخل التقييم (1/0)"), ("note", "ملاحظات")]
    SETTINGS = [("rep_w_sales", "وزن تحقيق تارجت المبيعات %", 100), ("rep_w_profit", "وزن تحقيق تارجت الربح %", 100),
                ("rep_w_coll", "وزن التحصيل %", 100), ("rep_w_roi", "وزن العائد لكل ريال تكلفة %", 100),
                ("rep_w_margin", "وزن الهامش %", 100), ("rep_cap", "الحد الأقصى للتحقيق %", 100),
                ("rep_roi_cap", "الحد الأقصى للعائد (مضاعف المتوسط)", 1), ("rep_iqama", "تكلفة الإقامة السنوية للمقيم", 1),
                ("rep_insurance", "التأمين الصحي السنوي للمندوب", 1)]

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.win = page.win
        lay = QVBoxLayout(self)
        note = QLabel("ارفع تقارير النظام: الأصناف بالمندوب والعملاء بالمندوب (لشهر أو لعدة شهور)، وتقرير الفواتير وسندات "
                      "القبض (تتقسم على الشهور من التاريخ). رصيد العملاء آخر كل شهر يُؤخذ من «أعمار العملاء» في "
                      "«البيانات الشهرية»، ومنه نسبة التحصيل والمتأخر.")
        note.setWordWrap(True)
        note.setStyleSheet("padding:6px; background:#eef4fb; border-radius:6px;")
        lay.addWidget(note)
        bar = QHBoxLayout()
        for text, fn in (("📥 الأصناف أو العملاء بالمندوب", self.import_sales), ("📥 تقرير الفواتير", self.import_invoices),
                         ("📥 سندات القبض", self.import_receipts), ("📥 بيانات المناديب (Excel)", self.import_reps),
                         ("📥 العمولات الشهرية (Excel)", self.import_commissions)):
            bar.addWidget(_btn(text, fn))
        bar.addStretch()
        lay.addLayout(bar)
        files = QGroupBox("الملفات المرفوعة")
        fv = QVBoxLayout(files)
        self.files = QTableWidget(0, 4)
        self.files.setHorizontalHeaderLabels(["الملف", "الفترة", "عدد السطور", "الإجمالي"])
        self.files.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.files.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.files.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.files.verticalHeader().setVisible(False)
        self.files.setMaximumHeight(170)
        self.files.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        fv.addWidget(self.files)
        fv.addWidget(_btn("🗑 حذف الملف المحدد", self.delete_file), 0, Qt.AlignLeft)
        lay.addWidget(files)
        reps = QGroupBox("المناديب (الراتب = الأساسي + السكن + البدلات قبل الاستقطاعات)")
        rv = QVBoxLayout(reps)
        self.table = QTableWidget(0, len(self.REP_COLS))
        self.table.setHorizontalHeaderLabels([h for _, h in self.REP_COLS])
        self.table.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setMinimumHeight(230)
        rv.addWidget(self.table)
        h = QHBoxLayout()
        h.addWidget(_btn("＋ مندوب", self.add_rep))
        h.addWidget(_btn("📤 تصدير نموذج المناديب والعمولات", self.export_template))
        h.addStretch()
        h.addWidget(_btn("💾 حفظ المناديب", self.save_reps))
        rv.addLayout(h)
        lay.addWidget(reps, 1)
        sg = QGroupBox("الأوزان والإعدادات")
        sl = QGridLayout(sg)
        self.spins = {}
        for i, (key, label, scale) in enumerate(self.SETTINGS):
            sp = QDoubleSpinBox()
            sp.setRange(0, 10_000_000)
            sp.setDecimals(1 if scale == 100 else 2)
            self.spins[key] = (sp, scale)
            sl.addWidget(QLabel(label), i // 3, (i % 3) * 2)
            sl.addWidget(sp, i // 3, (i % 3) * 2 + 1)
        self.prefix = QLineEdit()
        sl.addWidget(QLabel("أول أرقام حسابات العملاء في السندات"), 3, 0)
        sl.addWidget(self.prefix, 3, 1)
        sl.addWidget(_btn("💾 حفظ الإعدادات", self.save_settings), 3, 5)
        lay.addWidget(sg)

    # ---------------- show
    def load(self):
        db = self.win.db
        files = [(KIND_LABEL[k], a, b, n, s, ("sales", k, a, b)) for k, a, b, n, s in db.rep_sales_files()]
        for table, label in (("invoices", "الفواتير"), ("receipts", "سندات القبض")):
            for p, (n, s) in sorted(db.monthly_counts(table).items()):
                files.append((label, p, p, n, s, (table, p)))
        com = db.commissions()
        for p in sorted(com):
            files.append(("العمولات", p, p, len(com[p]), sum(com[p].values()), ("commission", p)))
        self.files.setRowCount(len(files))
        for r, (label, a, b, n, s, key) in enumerate(files):
            per = calc.month_label(a) if a == b else f"{calc.month_label(a)} — {calc.month_label(b)}"
            for c, v in enumerate((label, per, f"{n:,}", _num(s))):
                it = QTableWidgetItem(v)
                it.setData(Qt.UserRole, key)
                self.files.setItem(r, c, it)
        reps = list(db.reps().values())
        self.table.setRowCount(len(reps))
        for r, rec in enumerate(reps):
            for c, (k, _) in enumerate(self.REP_COLS):
                v = rec.get(k)
                if k in ("salary", "target", "other"):
                    v = f"{v or 0:,.0f}"
                self.table.setItem(r, c, QTableWidgetItem("" if v is None else str(v)))
        self.table.resizeColumnsToContents()
        for key, (sp, scale) in self.spins.items():
            sp.setValue(db.setting_float(key) * scale)
        self.prefix.setText(str(db.setting("rep_cust_prefix") or "114"))

    # ---------------- reading files
    def _open(self, title):
        start = QSettings().value("last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getOpenFileName(self, title, start, "Excel / CSV (*.xlsx *.xlsm *.csv *.txt)")
        if not path:
            return None
        QSettings().setValue("last_dir", os.path.dirname(path))
        try:
            with Progress(self, f"قراءة {os.path.basename(path)}") as bar:
                bar.step(10, "جاري القراءة")
                rows = importer.read_table(path)
                bar.step(100, f"{len(rows)} سطر")
                return rows
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "تنبيه", f"تعذر قراءة الملف:\n{e}")
            return None

    def _ensure_reps(self, rows):
        """New rep codes found in a sales file are added to the reps list (the main account 4000 is left out)."""
        have = self.win.db.reps()
        new = {}
        for r in rows:
            if r["rep"] not in have and r["rep"] not in new:
                main = r["rep"] == "4000" or "رئيسي" in (r["rep_name"] or "")
                new[r["rep"]] = {"code": r["rep"], "name": r["rep_name"], "nationality": "مقيم", "salary": 0.0,
                                 "target": 0.0, "other": 0.0, "active": 0 if main else 1, "note": ""}
        if new:
            self.win.db.save_reps(list(new.values()), replace=False)
        return len(new)

    def import_sales(self):
        rows = self._open("تقرير الأصناف أو العملاء بالمندوب")
        if rows is None:
            return
        try:
            kind, recs = D.parse_rep_sales(rows)
        except ValueError as e:
            QMessageBox.warning(self, "تنبيه", str(e))
            return
        import datetime
        today = datetime.date.today()
        last = self.page.end_month() or f"{today.year:04d}-{today.month:02d}"
        d = RangeDialog(self, f"{KIND_LABEL[kind]}: لأي فترة؟", last[:5] + "01", last)
        if d.exec() != QDialog.Accepted:
            return
        a, b = d.months()
        self.win.db.save_rep_sales(kind, a, b, recs)
        n_new = self._ensure_reps(recs)
        total = sum(r["net"] for r in recs)
        reps = len({r["rep"] for r in recs})
        msg = f"تم حفظ {KIND_LABEL[kind]}: {len(recs):,} سطر، {reps} مندوب، صافي المبيعات {total:,.0f}."
        if n_new:
            msg += f"\nأُضيف {n_new} مندوب جديد لقائمة المناديب — أكمل الراتب والتارجت والجنسية."
        QMessageBox.information(self, "تم", msg)
        self.page.reload()

    def _monthly(self, title, parser, saver, label):
        rows = self._open(title)
        if rows is None:
            return
        try:
            by, info = parser(rows)
        except ValueError as e:
            QMessageBox.warning(self, "تنبيه", str(e))
            return
        p, share = D.dominant(by)
        if not p:
            QMessageBox.warning(self, "تنبيه", "الملف فاضي.")
            return
        if share >= 0.9:
            month = _months_choice(self, f"{label} لأي شهر؟ (الملف شهر واحد تقريبًا)", p)
            if not month:
                return
            by = D.merge_into(by, month)
        elif not _ask(self, f"الملف فيه {len(by)} شهر — يتقسم على الشهور حسب التاريخ ويستبدل بيانات كل شهر منها؟"):
            return
        saver(by)
        n = sum(len(v) for v in by.values())
        msg = f"تم حفظ {label}: {n:,} سطر — " + "، ".join(f"{calc.month_label(k)} ({len(v)})" for k, v in sorted(by.items()))
        if info["fixed_dates"]:
            msg += (f"\nصُحّح {info['fixed_dates']:,} تاريخ قلب فيه Excel اليوم والشهر "
                    "(مثل 10/02 اللي المقصود بيه 2 أكتوبر).")
        QMessageBox.information(self, "تم", msg)
        self.page.reload()

    def import_invoices(self):
        self._monthly("تقرير الفواتير", D.parse_invoices, self.win.db.save_invoices, "الفواتير")

    def import_receipts(self):
        self._monthly("سندات القبض", D.parse_receipts, self.win.db.save_receipts, "سندات القبض")

    def import_reps(self):
        rows = self._open("بيانات المناديب")
        if rows is None:
            return
        try:
            recs = D.parse_reps(rows)
        except ValueError as e:
            QMessageBox.warning(self, "تنبيه", str(e))
            return
        self.win.db.save_reps(recs, replace=False)
        QMessageBox.information(self, "تم", f"تم حفظ بيانات {len(recs)} مندوب.")
        self.page.reload()

    def import_commissions(self):
        rows = self._open("العمولات الشهرية (كود المندوب + عمود لكل شهر بعنوان 2026-01 ...)")
        if rows is None:
            return
        try:
            by = D.parse_commissions(rows)
        except ValueError as e:
            QMessageBox.warning(self, "تنبيه", str(e))
            return
        for p, amounts in by.items():
            self.win.db.save_commissions(p, amounts)
        total = sum(sum(v.values()) for v in by.values())
        QMessageBox.information(self, "تم", f"تم حفظ العمولات لـ {len(by)} شهر، الإجمالي {total:,.0f}.")
        self.page.reload()

    def delete_file(self):
        r = self.files.currentRow()
        if r < 0:
            return
        key = self.files.item(r, 0).data(Qt.UserRole)
        if not _ask(self, f"حذف {self.files.item(r, 0).text()} — {self.files.item(r, 1).text()}؟"):
            return
        db = self.win.db
        if key[0] == "sales":
            db.delete_rep_sales(key[1], key[2], key[3])
        elif key[0] == "commission":
            db.save_commissions(key[1], {})
        else:
            db.delete_monthly(key[0], key[1])
        self.page.reload()

    # ---------------- reps and settings
    def add_rep(self):
        self.table.insertRow(self.table.rowCount())
        self.table.setItem(self.table.rowCount() - 1, 6, QTableWidgetItem("1"))

    def save_reps(self):
        out = []
        for r in range(self.table.rowCount()):
            g = lambda c: (self.table.item(r, c).text().strip() if self.table.item(r, c) else "")  # noqa: E731
            code = g(0)
            if not code:
                continue
            out.append({"code": code, "name": g(1), "nationality": g(2) or "مقيم",
                        "salary": importer.to_number(g(3)) or 0.0, "target": importer.to_number(g(4)) or 0.0,
                        "other": importer.to_number(g(5)) or 0.0, "active": 0 if g(6) in ("0", "لا") else 1,
                        "note": g(7)})
        self.win.db.save_reps(out)
        QMessageBox.information(self, "تم", f"تم حفظ {len(out)} مندوب.")
        self.page.reload()

    def save_settings(self):
        db = self.win.db
        ws = sum(self.spins[k][0].value() for k in ("rep_w_sales", "rep_w_profit", "rep_w_coll", "rep_w_roi", "rep_w_margin"))
        if abs(ws - 100) > 0.05 and not _ask(self, f"مجموع الأوزان {ws:.1f}% وليس 100%. الأوزان تتوزع بنسبتها. حفظ؟"):
            return
        for key, (sp, scale) in self.spins.items():
            db.set_setting(key, sp.value() / scale)
        db.set_setting("rep_cust_prefix", self.prefix.text().strip() or "114")
        self.page.reload()

    def export_template(self):
        start = QSettings().value("last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getSaveFileName(self, "تصدير", os.path.join(start, "المناديب والعمولات.xlsx"), "Excel (*.xlsx)")
        if not path:
            return
        import openpyxl
        from openpyxl.styles import Font, PatternFill
        db = self.win.db
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "المناديب"
        ws.sheet_view.rightToLeft = True
        ws.append([h for _, h in self.REP_COLS])
        for rec in db.reps().values():
            ws.append([rec.get(k) for k, _ in self.REP_COLS])
        com = db.commissions()
        months = sorted(com) or [self.page.end_month() or "2026-01"]
        w2 = wb.create_sheet("العمولات")
        w2.sheet_view.rightToLeft = True
        w2.append(["كود", "المندوب"] + months)
        for code, rec in db.reps().items():
            w2.append([code, rec["name"]] + [com.get(m, {}).get(code) for m in months])
        for w in (ws, w2):
            for c in w[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = PatternFill("solid", fgColor="12355B")
            w.column_dimensions["B"].width = 26
        try:
            wb.save(path)
        except OSError as e:
            QMessageBox.warning(self, "تنبيه", f"تعذر الحفظ (الملف مفتوح؟):\n{e}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))


# ================================================================== the page
class RepsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        from .system_window import ReportView
        self.win = win
        self.ev = None
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("الفترة:"))
        self.mode = QComboBox()
        for text, k in (("من أول السنة حتى", "ytd"), ("الشهر فقط", "month"), ("من شهر محدد حتى", "from")):
            self.mode.addItem(text, k)
        self.start = QComboBox()
        self.end = QComboBox()
        for w in (self.mode, self.start, self.end):
            w.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.mode)
        top.addWidget(self.start)
        top.addWidget(self.end)
        self.rep = QComboBox()
        self.rep.setMinimumWidth(220)
        self.rep.currentIndexChanged.connect(self.show_rep)
        top.addStretch()
        for text, fn in (("📊 Excel (التقارير)", self.export_excel), ("📄 PDF (الصفحة الحالية)", self.export_pdf),
                         ("📚 PDF (كل المناديب)", self.export_all_pdf)):
            top.addWidget(_btn(text, fn))
        lay.addLayout(top)
        self.tabs = QTabWidget()
        self.board = Board(self)
        self.summary = ReportView()
        rep_box = QWidget()
        rv = QVBoxLayout(rep_box)
        rh = QHBoxLayout()
        rh.addWidget(QLabel("المندوب:"))
        rh.addWidget(self.rep)
        rh.addStretch()
        rv.addLayout(rh)
        self.rep_view = ReportView()
        rv.addWidget(self.rep_view, 1)
        self.coll = ReportView()
        self.inv = ReportView()
        self.data = DataTab(self)
        for w, t in ((self.board, "🏆 لوحة المناديب"), (self.summary, "📋 الترتيب"), (rep_box, "📄 تقرير المندوب"),
                     (self.coll, "💰 التحصيل ومطابقة الأرصدة"), (self.inv, "🧾 الفواتير"),
                     (self.data, "⚙ البيانات والإعدادات")):
            self.tabs.addTab(w, t)
        lay.addWidget(self.tabs, 1)

    # ---------------- period
    def end_month(self):
        return self.end.currentData()

    def months(self):
        end = self.end.currentData()
        if not end:
            return []
        mode = self.mode.currentData()
        if mode == "month":
            return [end]
        if mode == "from":
            a = self.start.currentData() or end
            return RP.months_between(min(a, end), end)
        fs = int(self.win.db.setting_float("fiscal_start") or 1)
        y = int(end[:4]) if int(end[5:7]) >= fs else int(end[:4]) - 1
        return RP.months_between(f"{y:04d}-{fs:02d}", end)

    def load(self):
        self.reload()

    def reload(self):
        months = RP.available_months(self.win.db)
        cur_e, cur_s = self.end.currentData(), self.start.currentData()
        for w, cur in ((self.end, cur_e), (self.start, cur_s)):
            w.blockSignals(True)
            w.clear()
            for m in reversed(months):
                w.addItem(calc.month_label(m), m)
            i = w.findData(cur) if cur else -1
            w.setCurrentIndex(i if i >= 0 else (w.count() - 1 if w is self.start else 0))
            w.blockSignals(False)
        self.data.load()
        self.refresh()

    def refresh(self):
        self.start.setVisible(self.mode.currentData() == "from")
        months = self.months()
        if not months:
            self.ev = None
            msg = "لا توجد بيانات مناديب بعد — ارفع التقارير من تبويب «⚙ البيانات والإعدادات»."
            for v in (self.summary, self.rep_view, self.coll, self.inv):
                v.show_message(msg)
            self.board.setWidget(QLabel(msg))
            return
        try:
            with Progress(self, "حساب تقييم المناديب") as bar:
                bar.step(20, "قراءة البيانات")
                self.ev = RP.evaluate(self.win.db, months)
                bar.step(80, "التقارير")
                company = self.win.ctx.company if self.win.ctx else ""
                self.board.show_eval(self.ev, f"لوحة أداء المناديب — {calc.range_label(months)}")
                self.summary.show_report(RP.rpt_summary(self.ev), company)
                self.coll.show_report(RP.rpt_collections(self.ev), company)
                self.inv.show_report(RP.rpt_invoices(self.ev), company)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "تنبيه", f"تعذر حساب التقييم:\n{e}")
            return
        cur = self.rep.currentData()
        self.rep.blockSignals(True)
        self.rep.clear()
        for r in self.ev.ordered():
            self.rep.addItem(f"{'#' + str(r.rank) if r.rank else '—'}  {r.name}", r.code)
        i = self.rep.findData(cur) if cur else 0
        self.rep.setCurrentIndex(max(0, i))
        self.rep.blockSignals(False)
        self.show_rep()

    def show_rep(self):
        code = self.rep.currentData()
        if self.ev and code:
            self.rep_view.show_report(RP.rpt_rep(self.ev, code), self.win.ctx.company if self.win.ctx else "")

    def open_report(self, code):
        i = self.rep.findData(code)
        if i >= 0:
            self.rep.setCurrentIndex(i)
        self.tabs.setCurrentIndex(2)

    # ---------------- export
    def _all_reports(self):
        ev = self.ev
        return [RP.rpt_summary(ev)] + [RP.rpt_rep(ev, r.code) for r in ev.ordered()] + [RP.rpt_collections(ev),
                                                                                         RP.rpt_invoices(ev)]

    def _save_path(self, ext, what):
        company = self.win.ctx.company if self.win.ctx else ""
        name = f"{company} - {what} - {calc.range_label(self.ev.months)}".replace("/", "-").strip(" -")
        start = QSettings().value("last_dir", os.path.expanduser("~"))
        path, _ = QFileDialog.getSaveFileName(self, "حفظ", os.path.join(start, f"{name}.{ext}"),
                                              "PDF (*.pdf)" if ext == "pdf" else "Excel (*.xlsx)")
        return path

    def export_excel(self):
        if not self.ev:
            return
        path = self._save_path("xlsx", "تقييم المناديب")
        if not path:
            return
        try:
            render.write_excel(self._all_reports(), self.win.ctx.company if self.win.ctx else "", path)
        except OSError as e:
            QMessageBox.warning(self, "تنبيه", f"تعذر الحفظ (الملف مفتوح؟):\n{e}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def export_pdf(self):
        if not self.ev:
            return
        i = self.tabs.currentIndex()
        if i == 5:
            return
        path = self._save_path("pdf", ["لوحة المناديب", "ترتيب المناديب", self.rep.currentText().split("  ")[-1],
                                       "التحصيل", "الفواتير"][i])
        if not path:
            return
        if i == 0:
            self.board.export_pdf(path)
        else:
            from .system_window import write_pdf
            company = self.win.ctx.company if self.win.ctx else ""
            rep = [RP.rpt_summary(self.ev), RP.rpt_rep(self.ev, self.rep.currentData()), RP.rpt_collections(self.ev),
                   RP.rpt_invoices(self.ev)][i - 1]
            write_pdf(render.reports_html([rep], company), path, landscape=i in (1, 3, 4))
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def export_all_pdf(self):
        if not self.ev:
            return
        path = self._save_path("pdf", "تقارير المناديب")
        if not path:
            return
        from .system_window import write_pdf
        with Progress(self, "تصدير PDF") as bar:
            bar.step(30, "تجهيز التقارير")
            html = render.reports_html(self._all_reports(), self.win.ctx.company if self.win.ctx else "")
            bar.step(60, "الكتابة")
            write_pdf(html, path, landscape=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
