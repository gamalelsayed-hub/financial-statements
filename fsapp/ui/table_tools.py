"""Frozen first column for tables: the label column stays in place when scrolling sideways, the header row stays
in place when scrolling down (Qt's header already does that inside the table's own scroll area).

A second view sharing the table's model is laid over the first column (Qt's "frozen column" technique), so styles,
selection and sorting follow the table.
"""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView
from shiboken6 import isValid


class FrozenColumn(QObject):
    def __init__(self, table, columns=1):
        super().__init__(table)
        self.t, self.n = table, columns
        v = self.view = QTableView(table)
        v.setModel(table.model())
        v.setSelectionModel(table.selectionModel())
        v.setFocusPolicy(Qt.NoFocus)
        v.verticalHeader().hide()
        v.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        v.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        v.setVerticalScrollMode(table.verticalScrollMode())
        v.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        v.setEditTriggers(table.editTriggers())
        v.setSelectionBehavior(table.selectionBehavior())
        v.setWordWrap(table.wordWrap())
        v.setStyleSheet(table.styleSheet() + " QTableView { border: none; border-left: 2px solid #c7d2e0; }")
        v.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        v.horizontalHeader().setDefaultAlignment(table.horizontalHeader().defaultAlignment())
        v.horizontalHeader().setFixedHeight(table.horizontalHeader().height())
        v.setShowGrid(table.showGrid())
        self.sync_columns()
        table.viewport().stackUnder(v)
        table.horizontalHeader().sectionResized.connect(self._col_resized)
        table.verticalHeader().sectionResized.connect(lambda i, _o, h: v.setRowHeight(i, h))
        table.verticalScrollBar().valueChanged.connect(v.verticalScrollBar().setValue)
        v.verticalScrollBar().valueChanged.connect(table.verticalScrollBar().setValue)
        table.model().modelReset.connect(self.sync_columns)
        table.model().columnsInserted.connect(self.sync_columns)
        table.model().rowsInserted.connect(self.sync_rows)
        table.installEventFilter(self)
        for r in range(table.rowCount()):
            v.setRowHeight(r, table.rowHeight(r))
        v.show()
        self.update_geometry()

    def alive(self):
        return isValid(self.t) and isValid(self.view)

    def sync_columns(self, *_):
        if not self.alive():
            return
        for c in range(self.t.columnCount()):
            self.view.setColumnHidden(c, c >= self.n)
            if c < self.n:
                self.view.setColumnWidth(c, self.t.columnWidth(c))
        self.update_geometry()

    def sync_rows(self, *_):
        if not self.alive():
            return
        for r in range(self.t.rowCount()):
            self.view.setRowHeight(r, self.t.rowHeight(r))

    def _col_resized(self, i, _old, size):
        if i < self.n and self.alive():
            self.view.setColumnWidth(i, size)
            self.update_geometry()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Resize, QEvent.Show, QEvent.LayoutDirectionChange):
            self.update_geometry()
        return False

    def update_geometry(self):
        if not self.alive():
            return
        t = self.t
        width = sum(t.columnWidth(c) for c in range(min(self.n, t.columnCount())))
        vp = t.viewport().geometry()
        hh = t.horizontalHeader().height()
        if t.layoutDirection() == Qt.RightToLeft or t.isRightToLeft():
            x = vp.x() + vp.width() - width          # the first column sits on the right
        else:
            x = vp.x()
        self.view.horizontalHeader().setFixedHeight(hh)
        self.view.setGeometry(x, t.frameWidth(), width, vp.height() + hh)
        # hide the overlay when the whole table fits (nothing to scroll sideways)
        self.view.setVisible(t.horizontalScrollBar().maximum() > 0 or t.columnCount() > self.n + 4)


def freeze(table, columns=1):
    """Freeze the first `columns` columns of a QTableWidget/QTableView. Returns the helper (keep a reference)."""
    table._frozen = FrozenColumn(table, columns)
    return table._frozen
