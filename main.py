import sys

from PySide6.QtCore import QCoreApplication, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from fsapp.i18n import set_lang
from fsapp.ui.main_window import MainWindow


def main():
    QCoreApplication.setOrganizationName("FSApp")
    QCoreApplication.setApplicationName("FinancialStatements")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if sys.platform == "win32":
        app.setFont(QFont("Segoe UI", 10))
    set_lang(QSettings().value("lang", "ar"))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
