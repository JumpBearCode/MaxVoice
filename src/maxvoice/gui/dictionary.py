from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..config import DictionaryEntry, UserConfig

_INTRO = (
    "Words and phrases the speech model often gets wrong for you.\n"
    "• <b>Written</b> — the spelling you want to see (e.g. <i>Claude Code</i>).\n"
    "• <b>Heard as</b> (optional) — what the model tends to produce instead "
    "(e.g. <i>cloud code</i>). Add one row per likely misrecognition.\n\n"
    "These are <b>soft hints</b>: the model decides based on context, so "
    "genuine uses of the \"heard as\" phrase are not force-replaced."
)


class DictionaryDialog(QDialog):
    COLS = ["Written (correct)", "Heard as (optional)"]

    def __init__(self, cfg: UserConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MaxVoice Dictionary")
        self.resize(560, 420)
        self._cfg = cfg.model_copy(deep=True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        intro = QLabel(_INTRO)
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        intro.setStyleSheet("color: #444;")
        layout.addWidget(intro)

        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        for entry in self._cfg.dictionary:
            self._append_row(entry.written, entry.spoken)

        row_buttons = QHBoxLayout()
        add_btn = QPushButton("Add row")
        add_btn.clicked.connect(lambda: self._append_row("", ""))
        remove_btn = QPushButton("Remove selected")
        remove_btn.clicked.connect(self._remove_selected)
        row_buttons.addWidget(add_btn)
        row_buttons.addWidget(remove_btn)
        row_buttons.addStretch(1)
        layout.addLayout(row_buttons)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _append_row(self, written: str, spoken: str) -> None:
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(written))
        self.table.setItem(r, 1, QTableWidgetItem(spoken))

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def _save(self) -> None:
        entries: list[DictionaryEntry] = []
        for r in range(self.table.rowCount()):
            written_item = self.table.item(r, 0)
            spoken_item = self.table.item(r, 1)
            written = (written_item.text() if written_item else "").strip()
            spoken = (spoken_item.text() if spoken_item else "").strip()
            if not written:
                continue
            entries.append(DictionaryEntry(written=written, spoken=spoken))
        self._cfg.dictionary = entries
        self.accept()

    def result_config(self) -> UserConfig:
        return self._cfg
