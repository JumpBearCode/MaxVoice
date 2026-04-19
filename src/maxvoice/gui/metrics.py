from datetime import date, datetime, timedelta

from PyQt6.QtCharts import (
    QBarCategoryAxis,
    QChart,
    QChartView,
    QLineSeries,
    QValueAxis,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import QDialog, QPushButton, QVBoxLayout

from .. import db, pricing
from ..db import EASTERN


def _compute_daily(n: int) -> list[tuple[date, float, float]]:
    today = datetime.now(EASTERN).date()
    start = today - timedelta(days=n - 1)
    since = datetime.combine(start, datetime.min.time(), tzinfo=EASTERN)
    rows = db.recordings_since(since)

    buckets: dict[date, list[float]] = {}
    for r in rows:
        d = r.created_at.astimezone(EASTERN).date() if r.created_at.tzinfo else r.created_at.date()
        cost = pricing.total_cost(
            r.stt_model, r.refine_model, r.duration_seconds,
            r.raw_text, r.refined_text,
        )
        b = buckets.setdefault(d, [0.0, 0.0])
        b[0] += cost
        b[1] += r.saved_seconds

    out: list[tuple[date, float, float]] = []
    for i in range(n):
        d = start + timedelta(days=i)
        cost, saved = buckets.get(d, [0.0, 0.0])
        out.append((d, cost, saved))
    return out


def _line_chart(title: str, labels: list[str], values: list[float], label_fmt: str) -> QChart:
    chart = QChart()
    chart.setTitle(title)
    chart.legend().setVisible(False)

    series = QLineSeries()
    series.setPointsVisible(True)
    for i, v in enumerate(values):
        series.append(float(i), float(v))
    chart.addSeries(series)

    x_axis = QBarCategoryAxis()
    x_axis.append(labels)
    chart.addAxis(x_axis, Qt.AlignmentFlag.AlignBottom)
    series.attachAxis(x_axis)

    y_axis = QValueAxis()
    y_max = max(values) if values else 0.0
    y_axis.setRange(0.0, y_max * 1.2 if y_max > 0 else 1.0)
    y_axis.setLabelFormat(label_fmt)
    chart.addAxis(y_axis, Qt.AlignmentFlag.AlignLeft)
    series.attachAxis(y_axis)

    return chart


def _cumulative(values: list[float]) -> list[float]:
    out: list[float] = []
    total = 0.0
    for v in values:
        total += v
        out.append(total)
    return out


class MetricsDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MaxVoice Metrics — last 7 days")
        self.resize(760, 640)

        self._cumulative = False

        layout = QVBoxLayout(self)
        self.toggle_btn = QPushButton("Mode: Daily  (click for Cumulative)")
        self.toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self.toggle_btn)

        self.saved_view = QChartView()
        self.saved_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.cost_view = QChartView()
        self.cost_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        layout.addWidget(self.saved_view, 1)
        layout.addWidget(self.cost_view, 1)

        self.reload()

    def _on_toggle(self) -> None:
        self._cumulative = not self._cumulative
        self.toggle_btn.setText(
            "Mode: Cumulative  (click for Daily)"
            if self._cumulative
            else "Mode: Daily  (click for Cumulative)"
        )
        self.reload()

    def reload(self) -> None:
        days = _compute_daily(7)
        labels = [d.strftime("%a %m/%d") for d, _, _ in days]
        saved_minutes = [s / 60.0 for _, _, s in days]
        costs = [c for _, c, _ in days]

        if self._cumulative:
            saved_minutes = _cumulative(saved_minutes)
            costs = _cumulative(costs)

        suffix = "cumulative" if self._cumulative else "daily"
        self.saved_view.setChart(
            _line_chart(f"Saved time — minutes ({suffix})", labels, saved_minutes, "%.1f")
        )
        self.cost_view.setChart(
            _line_chart(f"Cost — USD ({suffix})", labels, costs, "$%.4f")
        )
