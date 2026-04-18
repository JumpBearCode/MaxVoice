from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from ..config import UserConfig
from ..refine import AVAILABLE_REFINE
from ..stt import AVAILABLE_STT
from ..typing_speed import TypingSpeed
from .hotkey_edit import HotkeyEdit

# (label shown in UI, attribute on TypingSpeed, unit suffix shown next to spinbox)
_LANG_FIELDS = [
    ("English",  "english", "WPM"),
    ("Chinese",  "chinese", "字/min"),
    ("Hindi",    "hindi",   "WPM"),
    ("Telugu",   "telugu",  "WPM"),
    ("Tamil",    "tamil",   "WPM"),
]


class SettingsDialog(QDialog):
    def __init__(self, cfg: UserConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MaxVoice Settings")
        self.setMinimumWidth(460)
        self._cfg = cfg.model_copy()

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.hotkey_edit = HotkeyEdit(cfg.hotkey)
        form.addRow("Hotkey (toggle)", self.hotkey_edit)

        self.stt_combo = QComboBox()
        for cls in AVAILABLE_STT:
            self.stt_combo.addItem(cls.label, cls.name)
        self._select_by_data(self.stt_combo, cfg.stt_model)
        form.addRow("STT model (layer 1)", self.stt_combo)

        self.refine_enabled = QCheckBox("Enable")
        self.refine_enabled.setChecked(cfg.refine_enabled)
        form.addRow("Refinement (layer 2)", self.refine_enabled)

        self.refine_combo = QComboBox()
        for cls in AVAILABLE_REFINE:
            self.refine_combo.addItem(cls.label, cls.name)
        self._select_by_data(self.refine_combo, cfg.refine_model)
        form.addRow("Refinement model", self.refine_combo)

        self.language_hint = QLineEdit(cfg.language_hint)
        self.language_hint.setPlaceholderText("blank = auto. e.g. zh, en, hi")
        form.addRow("Language hint", self.language_hint)

        self.auto_paste = QCheckBox("Auto-paste to cursor (fallback: clipboard)")
        self.auto_paste.setChecked(cfg.auto_paste)
        form.addRow("Output", self.auto_paste)

        layout.addLayout(form)

        speed_box = QGroupBox("Typing speed (used to estimate time saved)")
        speed_form = QFormLayout(speed_box)
        defaults = TypingSpeed()
        self.speed_spins: dict[str, QSpinBox] = {}
        for label, attr, unit in _LANG_FIELDS:
            spin = QSpinBox()
            spin.setRange(5, 300)
            spin.setValue(getattr(cfg.typing_speed, attr))
            spin.setSuffix(f"  {unit}")
            self.speed_spins[attr] = spin
            row_label = f"{label}  (default {getattr(defaults, attr)} {unit})"
            speed_form.addRow(row_label, spin)
        layout.addWidget(speed_box)
        layout.addWidget(QLabel(
            "Other scripts (Latin, Cyrillic, etc.) fall back to English speed."
        ))

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def _select_by_data(combo: QComboBox, value: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _save(self) -> None:
        self._cfg.hotkey = self.hotkey_edit.text() or self._cfg.hotkey
        self._cfg.stt_model = self.stt_combo.currentData()
        self._cfg.refine_model = self.refine_combo.currentData()
        self._cfg.refine_enabled = self.refine_enabled.isChecked()
        self._cfg.language_hint = self.language_hint.text().strip()
        self._cfg.typing_speed = TypingSpeed(
            **{attr: spin.value() for attr, spin in self.speed_spins.items()}
        )
        self._cfg.auto_paste = self.auto_paste.isChecked()
        self.accept()

    def result_config(self) -> UserConfig:
        return self._cfg
