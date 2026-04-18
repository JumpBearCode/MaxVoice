from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QLineEdit

# Map Qt key names to pynput's GlobalHotKeys string format.
_QT_MODIFIERS = [
    (Qt.KeyboardModifier.ControlModifier, "<ctrl>"),
    (Qt.KeyboardModifier.AltModifier, "<alt>"),
    (Qt.KeyboardModifier.MetaModifier, "<cmd>"),
    (Qt.KeyboardModifier.ShiftModifier, "<shift>"),
]


def _key_to_str(key: int) -> str:
    # Letters / digits come through as uppercase ASCII codes.
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        return chr(key).lower()
    if Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
        return chr(key)
    for k in range(Qt.Key.Key_F1, Qt.Key.Key_F24 + 1):
        if key == k:
            return f"<f{k - Qt.Key.Key_F1 + 1}>"
    specials = {
        int(Qt.Key.Key_Space): "<space>",
        int(Qt.Key.Key_Tab): "<tab>",
        int(Qt.Key.Key_Return): "<enter>",
        int(Qt.Key.Key_Escape): "<esc>",
    }
    return specials.get(int(key), "")


class HotkeyEdit(QLineEdit):
    """Click to focus, then press a key combo — it's stored in pynput format
    (e.g. `<alt_r>+q`, `<ctrl>+<shift>+<space>`)."""

    captured = pyqtSignal(str)

    def __init__(self, initial: str = "", parent=None) -> None:
        super().__init__(initial, parent)
        self.setReadOnly(True)
        self.setPlaceholderText("Click and press your desired hotkey")

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        mods = e.modifiers()
        key = e.key()

        # Ignore standalone modifier presses — wait for a real key.
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
            Qt.Key.Key_Shift,
        ):
            return

        parts = [token for qmod, token in _QT_MODIFIERS if mods & qmod]
        key_str = _key_to_str(key)
        if not key_str:
            return
        parts.append(key_str)
        value = "+".join(parts)
        self.setText(value)
        self.captured.emit(value)
