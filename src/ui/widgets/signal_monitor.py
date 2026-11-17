"""Analog/PWM monitor UI. The backend owns samples and simulation state."""
from collections import deque
import time

from PySide6.QtCore import Qt, QPointF, QMargins
from PySide6.QtGui import QColor, QPainter, QPen, QFont
from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QFrame,
    QStackedWidget, QPushButton,
)
from src.common.monitor import PwmPreview


class SignalMonitor(QWidget):
    def __init__(self, parent=None, *, channels=(), backend=None):
        super().__init__(parent)
        self.backend = backend
        self.channels = tuple(dict(channel) for channel in channels)
        self._points = deque(maxlen=200)
        self._origin = time.monotonic()
        self.setObjectName('signalMonitor')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        controls = QHBoxLayout()
        self.kind_combo = QComboBox()
        self.kind_combo.addItem('Analog', 'analog')
        self.kind_combo.addItem('PWM', 'pwm')
        self.kind_combo.setAccessibleName('Loại tín hiệu quan sát')
        self.kind_combo.setFixedWidth(112)
        controls.addWidget(self.kind_combo)
        self.channel_combo = QComboBox()
        self.channel_combo.setAccessibleName('Kênh quan sát')
        self.channel_combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.channel_combo.setMinimumContentsLength(6)
        self.channel_combo.setMinimumWidth(130)
        controls.addWidget(self.channel_combo, 1)
        layout.addLayout(controls)
        summary = QHBoxLayout()
        self.source_label = QLabel('MÔ PHỎNG')
        self.source_label.setObjectName('monitorSource')
        self.source_label.setToolTip('Dữ liệu tổng hợp để thiết kế giao diện; chưa phải dữ liệu phần cứng.')
        summary.addWidget(self.source_label)
        self.value_label = QLabel('—')
        self.value_label.setObjectName('monitorValue')
        self.value_label.setAlignment(Qt.AlignRight)
        self.value_label.setWordWrap(True)
        summary.addWidget(self.value_label, 1)
        layout.addLayout(summary)
        self.pages = QStackedWidget()
        canvas = QFrame()
        canvas.setObjectName('monitorEmpty')
        content = QVBoxLayout(canvas)
        content.setAlignment(Qt.AlignCenter)
        caption = QLabel('Chưa cấu hình kênh quan sát')
        caption.setObjectName('monitorCaption')
        caption.setAlignment(Qt.AlignCenter)
        content.addWidget(caption)
        self.hint = QLabel()
        self.hint.setObjectName('monitorHint')
        self.hint.setWordWrap(True)
        self.hint.setAlignment(Qt.AlignCenter)
        content.addWidget(self.hint)
        self.pages.addWidget(canvas)
        self.chart = QChart()
        self.chart.setBackgroundBrush(QColor('#111f31'))
        self.chart.setBackgroundRoundness(0)
        self.chart.setPlotAreaBackgroundBrush(QColor('#0b1b2b'))
        self.chart.setPlotAreaBackgroundVisible(True)
        self.chart.setMargins(QMargins(0, 0, 0, 0))
        self.chart.legend().hide()
        self.series = QLineSeries()
        self.series.setPen(QPen(QColor('#58d8e9'), 2))
        self.chart.addSeries(self.series)
        self.x_axis = QValueAxis()
        self.y_axis = QValueAxis()
        self.x_axis.setTickCount(4)
        self.x_axis.setLabelFormat('%.0f s')
        self.x_axis.setRange(0, 5)
        self.y_axis.setTickCount(4)
        for axis in (self.x_axis, self.y_axis):
            font = QFont('Segoe UI')
            font.setPixelSize(13)
            axis.setLabelsFont(font)
            axis.setLabelsColor(QColor('#8da9bf'))
            axis.setGridLineColor(QColor('#263e52'))
            axis.setLinePenColor(QColor('#36566f'))
        self.chart.addAxis(self.x_axis, Qt.AlignBottom)
        self.chart.addAxis(self.y_axis, Qt.AlignLeft)
        self.series.attachAxis(self.x_axis)
        self.series.attachAxis(self.y_axis)
        self.view = QChartView(self.chart)
        self.view.setObjectName('trendView')
        self.view.setBackgroundBrush(QColor('#111f31'))
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setMinimumHeight(125)
        self.pages.addWidget(self.view)
        layout.addWidget(self.pages, 1)
        footer = QHBoxLayout()
        self.note = QLabel('Dữ liệu mô phỏng theo thời gian')
        self.note.setObjectName('monitorSource')
        self.note.setWordWrap(True)
        footer.addWidget(self.note, 1)
        self.toggle = QPushButton('Tạm dừng')
        self.toggle.setObjectName('monitorToggle')
        self.toggle.clicked.connect(self._toggle)
        footer.addWidget(self.toggle)
        layout.addLayout(footer)
        self.kind_combo.currentTextChanged.connect(self._describe)
        self.channel_combo.currentIndexChanged.connect(self._reset_channel)
        if backend is not None:
            backend.monitor_changed.connect(self.refresh)
        self._describe()

    def _describe(self):
        previous = self.channel_combo.currentData()
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        channels = [c for c in self.channels if c['kind'] == self.kind_combo.currentData()]
        for channel in channels:
            self.channel_combo.addItem(channel['label'], channel['id'])
        if not channels:
            self.channel_combo.addItem('Chưa cấu hình kênh', None)
        self.channel_combo.setEnabled(bool(channels))
        self.channel_combo.setCurrentIndex(max(0, self.channel_combo.findData(previous)))
        self.channel_combo.blockSignals(False)
        self.hint.setText('Chọn các kênh ' + self.kind_combo.currentText() + ' quan trọng để hiển thị.')
        self._reset_channel()

    def _reset_channel(self):
        self._points.clear()
        self.series.clear()
        self._origin = time.monotonic()
        self.x_axis.setLabelFormat('%.0f s')
        self.x_axis.setRange(0, 5)
        self.refresh()

    def _toggle(self):
        if self.backend is not None:
            self.backend.set_monitor_simulation(not self.backend.monitor_enabled)

    def refresh(self):
        definition = next((c for c in self.channels if c['id'] == self.channel_combo.currentData()), None)
        enabled = self.backend is not None and self.backend.monitor_enabled
        self.toggle.setEnabled(self.backend is not None and not self.backend.closed and bool(definition))
        self.toggle.setText('Tạm dừng' if enabled else 'Mô phỏng')
        self.source_label.setText('MÔ PHỎNG' if enabled else 'MÔ PHỎNG · ĐÃ DỪNG')
        self.pages.setCurrentIndex(1 if definition and self.backend is not None else 0)
        sample = self.backend.monitor_samples.get(definition['id']) if self.backend is not None and definition else None
        valid = sample and sample.quality == 'valid' and sample.source == 'monitor_demo' and time.monotonic() - sample.timestamp <= 1
        if not enabled or not valid:
            self.value_label.setText('—')
            self._points.clear()
            self.series.clear()
            self._origin = time.monotonic()
            return
        if definition['kind'] == 'pwm':
            frame = sample.value
            if not isinstance(frame, PwmPreview):
                self.value_label.setText('Chưa có dữ liệu dạng xung')
                self.series.clear()
                return
            self.value_label.setText(f'f: {frame.frequency_hz:g} Hz  ·  D: {frame.duty_percent:.1f}%')
            self.series.replace([QPointF(x, y) for x, y in frame.points])
            self.x_axis.setLabelFormat('%.1f ms')
            self.x_axis.setRange(0, frame.window_ms)
            self.y_axis.setRange(frame.low - .5, frame.high + .5)
            self.y_axis.setLabelFormat('%.1f V')
            self.note.setText('Dạng xung mô phỏng · 4 chu kỳ')
            return
        self.value_label.setText(f"{sample.value:.2f} {definition['unit']}")
        point = (max(0, sample.timestamp - self._origin), sample.value)
        if not self._points or self._points[-1][0] != point[0]:
            self._points.append(point)
        self.series.replace([QPointF(x, y) for x, y in self._points])
        end = max(5, point[0])
        self.x_axis.setRange(max(0, end - 20), end)
        self.y_axis.setRange(0, 5)
        self.y_axis.setLabelFormat('%.1f')
        self.note.setText('Mô phỏng analog · trục thời gian (s)')
