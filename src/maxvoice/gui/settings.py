from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..config import UserConfig, VADConfig
from ..paths import audio_dir
from ..refine import AVAILABLE_REFINE
from ..stt import AVAILABLE_STT
from ..typing_speed import TypingSpeed
from .hotkey_edit import HotkeyEdit

# Uniform unit across all languages — the internal math normalizes each
# language's "word" differently (see typing_speed.CHARS_PER_WORD), so
# showing "WPM" everywhere is fine and reads consistently.
_LANG_FIELDS = [
    ("English", "english"),
    ("Chinese", "chinese"),
    ("Hindi",   "hindi"),
    ("Telugu",  "telugu"),
    ("Tamil",   "tamil"),
]

_FIELD_WIDTH = 120  # consistent spinbox/combo column width across all groups


class HelpButton(QToolButton):
    """Small round '?' affordance — opens a QMessageBox on click."""

    def __init__(self, title: str, body: str, parent=None) -> None:
        super().__init__(parent)
        self.setText("?")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("Click for help")
        self.setFixedSize(18, 18)
        self.setStyleSheet(
            "QToolButton {"
            " border: 1px solid #b8b8b8;"
            " border-radius: 9px;"
            " color: #8a8a8a;"
            " font-weight: 600;"
            " padding: 0;"
            " }"
            "QToolButton:hover { color: #222; border-color: #444; }"
        )
        self._title = title
        self._body = body
        self.clicked.connect(self._show)

    def _show(self) -> None:
        QMessageBox.information(self, self._title, self._body)


def _with_help(widget: QWidget, title: str, body: str) -> QWidget:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    row.addWidget(widget)
    row.addWidget(HelpButton(title, body))
    row.addStretch(1)
    wrap = QWidget()
    wrap.setLayout(row)
    return wrap


def _tune_form(form: QFormLayout) -> None:
    """Right-align labels + keep fields at their natural size so the
    input column lines up vertically across every group."""
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
    form.setHorizontalSpacing(14)
    form.setVerticalSpacing(8)


_HELP_MAX_PAUSE = (
    "Max natural pause",
    "How long a silence in the middle of your speech still counts as "
    "\"talking\".\n\n"
    "Normal sentence breaks and breathing are 0.5–1 second. Anything "
    "longer looks like thinking/distraction and is excluded from the "
    "\"voice cost\" used to compute time saved.\n\n"
    "Lower (e.g. 1500 ms): more silence excluded → saved time looks "
    "higher.\n"
    "Higher (e.g. 3000 ms): more silence kept in → saved time looks "
    "lower (more conservative).\n\n"
    "Default 2500 ms intentionally leans conservative — a number you "
    "can defend is more useful than an optimistic one.",
)

_HELP_MIN_ACTIVE = (
    "Minimum active speech",
    "If voice-activity detection finds less actual speech than this in a "
    "recording, time saved is reported as 0 for that record.\n\n"
    "Guards against a mostly-silent clip + a brief \"hello\" showing "
    "inflated savings, and against STT hallucinations on blank audio.\n\n"
    "Default 0.5 s. Raise if you see suspiciously large savings on very "
    "short clips.",
)

_HELP_THRESHOLD = (
    "Speech detection sensitivity",
    "How confident the detector must be that a sound is speech (0–1 "
    "scale).\n\n"
    "Lower (e.g. 0.4): more sensitive — catches soft speech, but may "
    "include noise.\n"
    "Higher (e.g. 0.6): stricter — only clear speech, may miss whispers.\n\n"
    "Default 0.5 works for most rooms.",
)

_HELP_MIN_SEG = (
    "Minimum speech segment",
    "Ignore any speech-like sound shorter than this. Filters out coughs, "
    "clicks, keyboard taps.\n\n"
    "Default 250 ms. Lower only if very brief words (like \"OK\") are "
    "being dropped — rarely needed.",
)

_HELP_RETENTION_DAYS = (
    "Voice retention days",
    "Keep every recorded WAV file for at least this many days. Within "
    "this window, files are NEVER deleted — even if the folder has grown "
    "past \"Max audio GB\".\n\n"
    "Why keep WAVs at all? They let the app re-run voice-activity "
    "detection if you change VAD settings, or re-transcribe with a "
    "different STT model in the future. Outside the window, you lose "
    "those abilities for the affected recordings but keep the DB "
    "metadata (text, timing, cost, time saved).\n\n"
    "Default 30 days.",
)

_HELP_MAX_GB = (
    "Max audio GB",
    "When total WAV size exceeds this, the oldest files past the "
    "retention window are deleted until the total is back under the "
    "budget.\n\n"
    "Files inside the retention window are always protected, so if all "
    "your recordings are recent you may briefly go over this budget — "
    "that's expected.\n\n"
    "Default 1.0 GB — comfortable for heavy daily use; on-device STT "
    "plays back at ~115 MB per hour of raw recording.\n\n"
    "Changes take effect immediately when you click OK.",
)


class SettingsDialog(QDialog):
    def __init__(self, cfg: UserConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MaxVoice Settings")
        self.setMinimumWidth(520)
        self._cfg = cfg.model_copy()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        # ---- Top-level settings ----
        form = QFormLayout()
        _tune_form(form)

        self.hotkey_edit = HotkeyEdit(cfg.hotkey)
        self.hotkey_edit.setFixedWidth(_FIELD_WIDTH * 2)
        form.addRow("Hotkey (toggle)", self.hotkey_edit)

        self.stt_combo = QComboBox()
        for cls in AVAILABLE_STT:
            self.stt_combo.addItem(cls.label, cls.name)
        self._select_by_data(self.stt_combo, cfg.stt_model)
        self.stt_combo.setFixedWidth(_FIELD_WIDTH * 2)
        form.addRow("STT model (layer 1)", self.stt_combo)

        self.refine_enabled = QCheckBox("Enable")
        self.refine_enabled.setChecked(cfg.refine_enabled)
        form.addRow("Refinement (layer 2)", self.refine_enabled)

        self.refine_combo = QComboBox()
        for cls in AVAILABLE_REFINE:
            self.refine_combo.addItem(cls.label, cls.name)
        self._select_by_data(self.refine_combo, cfg.refine_model)
        self.refine_combo.setFixedWidth(_FIELD_WIDTH * 2)
        form.addRow("Refinement model", self.refine_combo)

        self.language_hint = QLineEdit(cfg.language_hint)
        self.language_hint.setPlaceholderText("blank = auto. e.g. zh, en, hi")
        self.language_hint.setFixedWidth(_FIELD_WIDTH * 2)
        form.addRow("Language hint", self.language_hint)

        self.auto_paste = QCheckBox("Auto-paste to cursor (fallback: clipboard)")
        self.auto_paste.setChecked(cfg.auto_paste)
        form.addRow("Output", self.auto_paste)

        layout.addLayout(form)

        # ---- Typing speed ----
        speed_box = QGroupBox("Typing speed (used to estimate time saved)")
        speed_form = QFormLayout(speed_box)
        _tune_form(speed_form)
        defaults = TypingSpeed()
        self.speed_spins: dict[str, QSpinBox] = {}
        for label, attr in _LANG_FIELDS:
            spin = QSpinBox()
            spin.setRange(5, 300)
            spin.setValue(getattr(cfg.typing_speed, attr))
            spin.setSuffix("  WPM")
            spin.setFixedWidth(_FIELD_WIDTH)
            self.speed_spins[attr] = spin
            speed_form.addRow(f"{label}  (default {getattr(defaults, attr)})", spin)

        note = QLabel(
            "Other scripts (Latin, Cyrillic, etc.) fall back to English speed."
        )
        note.setStyleSheet("color: #888;")
        note.setWordWrap(True)
        speed_form.addRow(note)

        layout.addWidget(speed_box)

        # ---- Time-saved calibration (VAD) ----
        vad_box = QGroupBox("Time-saved calibration (silence handling)")
        vad_form = QFormLayout(vad_box)
        _tune_form(vad_form)

        self.vad_max_pause = QSpinBox()
        self.vad_max_pause.setRange(200, 10000)
        self.vad_max_pause.setSingleStep(100)
        self.vad_max_pause.setSuffix("  ms")
        self.vad_max_pause.setValue(cfg.vad.max_natural_pause_ms)
        self.vad_max_pause.setFixedWidth(_FIELD_WIDTH)
        vad_form.addRow("Max natural pause", _with_help(self.vad_max_pause, *_HELP_MAX_PAUSE))

        self.vad_min_active = QDoubleSpinBox()
        self.vad_min_active.setRange(0.0, 10.0)
        self.vad_min_active.setSingleStep(0.1)
        self.vad_min_active.setDecimals(2)
        self.vad_min_active.setSuffix("  s")
        self.vad_min_active.setValue(cfg.vad.min_active_speech_seconds)
        self.vad_min_active.setFixedWidth(_FIELD_WIDTH)
        vad_form.addRow("Minimum active speech", _with_help(self.vad_min_active, *_HELP_MIN_ACTIVE))

        self.vad_threshold = QDoubleSpinBox()
        self.vad_threshold.setRange(0.1, 0.9)
        self.vad_threshold.setSingleStep(0.05)
        self.vad_threshold.setDecimals(2)
        self.vad_threshold.setValue(cfg.vad.speech_threshold)
        self.vad_threshold.setFixedWidth(_FIELD_WIDTH)
        vad_form.addRow("Speech detection sensitivity", _with_help(self.vad_threshold, *_HELP_THRESHOLD))

        self.vad_min_seg = QSpinBox()
        self.vad_min_seg.setRange(50, 2000)
        self.vad_min_seg.setSingleStep(50)
        self.vad_min_seg.setSuffix("  ms")
        self.vad_min_seg.setValue(cfg.vad.min_speech_duration_ms)
        self.vad_min_seg.setFixedWidth(_FIELD_WIDTH)
        vad_form.addRow("Minimum speech segment", _with_help(self.vad_min_seg, *_HELP_MIN_SEG))

        layout.addWidget(vad_box)

        # ---- Storage (audio retention) ----
        storage_box = QGroupBox("Storage")
        storage_form = QFormLayout(storage_box)
        _tune_form(storage_form)

        self.retention_days = QSpinBox()
        self.retention_days.setRange(0, 3650)
        self.retention_days.setSuffix("  days")
        self.retention_days.setValue(cfg.retention_days)
        self.retention_days.setFixedWidth(_FIELD_WIDTH)
        storage_form.addRow(
            "Voice retention days",
            _with_help(self.retention_days, *_HELP_RETENTION_DAYS),
        )

        self.max_audio_gb = QDoubleSpinBox()
        self.max_audio_gb.setRange(0.1, 1000.0)
        self.max_audio_gb.setSingleStep(0.5)
        self.max_audio_gb.setDecimals(2)
        self.max_audio_gb.setSuffix("  GB")
        self.max_audio_gb.setValue(cfg.max_audio_gb)
        self.max_audio_gb.setFixedWidth(_FIELD_WIDTH)
        storage_form.addRow(
            "Max audio GB",
            _with_help(self.max_audio_gb, *_HELP_MAX_GB),
        )

        open_btn = QPushButton("Show in Finder")
        open_btn.setFixedWidth(_FIELD_WIDTH)
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(audio_dir())))
        )
        storage_form.addRow("Audio folder", open_btn)

        layout.addWidget(storage_box)

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
        self._cfg.vad = VADConfig(
            max_natural_pause_ms=self.vad_max_pause.value(),
            min_active_speech_seconds=self.vad_min_active.value(),
            speech_threshold=self.vad_threshold.value(),
            min_speech_duration_ms=self.vad_min_seg.value(),
        )
        self._cfg.retention_days = self.retention_days.value()
        self._cfg.max_audio_gb = self.max_audio_gb.value()
        self._cfg.auto_paste = self.auto_paste.isChecked()
        self.accept()

    def result_config(self) -> UserConfig:
        return self._cfg
