from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap


def _dot_icon(color: str) -> QIcon:
    # macOS menu bar is 22pt tall; Retina needs 2x. Use 44x44 and a thick border
    # so the dot is visible on both light and dark menu bars.
    pm = QPixmap(44, 44)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(QColor("#000000"))
    p.drawEllipse(6, 6, 32, 32)
    p.end()
    return QIcon(pm)


def idle_icon() -> QIcon:
    return _dot_icon("#cccccc")


def recording_icon() -> QIcon:
    return _dot_icon("#ff3b30")


def transcribing_icon() -> QIcon:
    return _dot_icon("#ff9500")
