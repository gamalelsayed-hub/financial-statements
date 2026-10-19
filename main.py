import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from fsapp.i18n import set_lang
from fsapp.ui.system_window import launch


def main():
    QCoreApplication.setOrganizationName("FSApp")
    QCoreApplication.setApplicationName("FinancialStatements")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.RightToLeft)
    if sys.platform == "win32":
        app.setFont(QFont("Segoe UI", 10))
    set_lang("ar")
    launch()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
