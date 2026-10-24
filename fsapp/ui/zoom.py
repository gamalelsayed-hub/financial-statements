"""Zoom for every screen: Ctrl + mouse wheel, Ctrl + = / Ctrl + - / Ctrl + 0, or the toolbar buttons.

The level scales the program font and the few font sizes written in style sheets (through pt()); it is saved and
restored next time.
"""
from PySide6.QtCore import QEvent, QObject, QSettings, Qt
from PySide6.QtWidgets import QApplication

MIN, MAX, STEP = 0.7, 2.0, 0.1
_state = {"zoom": None, "base": None, "listeners": []}


def level():
    if _state["zoom"] is None:
        try:
            _state["zoom"] = min(MAX, max(MIN, float(QSettings().value("zoom", 1.0))))
        except (TypeError, ValueError):
            _state["zoom"] = 1.0
    return _state["zoom"]


def pt(size):
    """A font size in points, scaled by the zoom level (for style sheets)."""
    return f"{size * level():.1f}pt"


def apply():
    app = QApplication.instance()
    if app is None:
        return
    if _state["base"] is None:
        _state["base"] = app.font().pointSizeF() or 10.0
    f = app.font()
    f.setPointSizeF(_state["base"] * level())
    app.setFont(f)
    # widgets with their own style sheet ignore setFont: a general rule reaches them too (their own font-size
    # rules, written with pt(), still win)
    app.setStyleSheet(f"QWidget {{ font-size: {_state['base'] * level():.1f}pt; }}")


def set_level(z):
    z = round(min(MAX, max(MIN, z)), 2)
    if z == level():
        return
    _state["zoom"] = z
    QSettings().setValue("zoom", z)
    apply()
    for fn in list(_state["listeners"]):
        try:
            fn()
        except RuntimeError:          # the window was closed
            _state["listeners"].remove(fn)


def zoom_in():
    set_level(level() + STEP)


def zoom_out():
    set_level(level() - STEP)


def reset():
    set_level(1.0)


def on_change(fn):
    """fn() is called after the level changes (to rebuild screens that use pt())."""
    _state["listeners"].append(fn)


class _WheelFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and event.modifiers() & Qt.ControlModifier:
            (zoom_in if event.angleDelta().y() > 0 else zoom_out)()
            return True
        return False


def install():
    """Call once after the QApplication exists."""
    app = QApplication.instance()
    if app is None or getattr(app, "_zoom_filter", None):
        return
    app._zoom_filter = _WheelFilter(app)
    app.installEventFilter(app._zoom_filter)
    apply()
