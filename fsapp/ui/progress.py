"""Progress window with a counter and a percentage for uploads, imports and exports."""
from PySide6.QtCore import Qt


class Progress:
    """A progress window with a counter and a percentage for every upload / load / send.
    Call the object with (done, total, text="") from inside a loop, or .step(percent, text) between the phases of
    a job that has no loop. Use it in a with-block: the window closes and the cursor comes back even on errors."""

    def __init__(self, parent, title):
        from PySide6.QtWidgets import QApplication, QProgressDialog
        self.dlg = QProgressDialog(title, None, 0, 100, parent)
        self.dlg.setWindowTitle("جاري العمل...")
        self.dlg.setWindowModality(Qt.WindowModal)
        self.dlg.setMinimumDuration(0)
        self.dlg.setAutoClose(False)
        self.dlg.setAutoReset(False)
        self.dlg.setMinimumWidth(480)
        self.title = title
        self.dlg.setValue(0)
        self.dlg.show()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._cursor = True
        QApplication.processEvents()

    def __call__(self, done, total, text=""):
        from PySide6.QtWidgets import QApplication
        total = max(total, 1)
        pct = min(100, int(done * 100 / total))
        self.dlg.setMaximum(100)
        self.dlg.setValue(pct)
        self.dlg.setLabelText(f"{self.title}\n{done} من {total}  ({pct}%)" + (f"\n{text}" if text else ""))
        QApplication.processEvents()

    def step(self, pct, text=""):
        from PySide6.QtWidgets import QApplication
        pct = max(0, min(100, int(pct)))
        self.dlg.setValue(pct)
        self.dlg.setLabelText(f"{self.title}\n{text}  ({pct}%)" if text else f"{self.title}  ({pct}%)")
        QApplication.processEvents()

    def close(self):
        from PySide6.QtWidgets import QApplication
        self.dlg.close()
        if self._cursor:
            QApplication.restoreOverrideCursor()
            self._cursor = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False
