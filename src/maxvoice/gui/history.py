from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from .. import db, pricing


class HistoryDialog(QDialog):
    COLS = ["Time", "Duration", "Active", "STT", "Refine", "Saved (s)", "Cost", "Text"]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MaxVoice History")
        self.resize(900, 500)

        layout = QVBoxLayout(self)
        self.table = QTableWidget(0, len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        self.table.horizontalHeader().setSectionResizeMode(
            len(self.COLS) - 1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)

        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.reload)
        layout.addWidget(refresh)

        self.reload()

    def reload(self) -> None:
        rows = db.all_recordings(limit=500)
        total_saved = sum(r.saved_seconds for r in rows)
        total_cost = sum(
            pricing.total_cost(
                r.stt_model, r.refine_model, r.duration_seconds, r.raw_text, r.refined_text
            )
            for r in rows
        )
        self.setWindowTitle(
            f"MaxVoice History — {len(rows)} records, "
            f"saved ≈ {total_saved:.1f}s, cost ≈ ${total_cost:.4f}"
        )
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            text = r.refined_text or r.raw_text
            cost = pricing.total_cost(
                r.stt_model, r.refine_model, r.duration_seconds, r.raw_text, r.refined_text
            )
            active = r.active_speech_seconds
            cells = [
                r.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                f"{r.duration_seconds:.1f}s",
                f"{active:.1f}s" if active is not None else "—",
                r.stt_model,
                r.refine_model or "—",
                f"{r.saved_seconds:.1f}",
                f"${cost:.5f}",
                text,
            ]
            for j, c in enumerate(cells):
                item = QTableWidgetItem(c)
                item.setToolTip(c)
                if j < len(cells) - 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(i, j, item)
