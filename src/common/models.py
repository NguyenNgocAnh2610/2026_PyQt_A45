"""Read-only signal model shared by QML and Widgets."""
import time

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from src.common.testing import Sample

QUALITY_TEXT = {"valid": "Hiện thời", "unknown": "Chưa biết", "stale": "Hết hạn", "error": "Lỗi"}
VERDICT_COLOR = {"PASS": "#3ee6a0", "FAIL": "#ff6b81", "Chưa đánh giá": "#f2c26b", "ACK": "#8ab4ff"}
LIVE_COLOR = "#38dcf0"
IDLE_COLOR = "#5f758a"


class SignalModel(QAbstractListModel):
    """One row per profile signal.

    A live, valid sample is shown as current. Otherwise the last value from a
    test (``history``, owned by Backend) stays visible, labelled with its
    test/step, time and verdict (PASS/FAIL/… for measurements, ACK for
    acknowledged requests), so it is never mistaken for a current reading.
    """
    fields = ("signalId", "label", "group", "kind", "display", "unit", "quality", "stateColor", "highlight",
              "cardVisible", "sourceLabel", "pinned", "subtitle", "verdict", "live", "recorded")

    def __init__(self, definitions, parent=None, pinned=()):
        super().__init__(parent)
        self.definitions = definitions
        self.samples = {}
        self.history = {}
        self.related = set()
        self.filter_group = "Tất cả"
        self.only_related = False
        self.pinned = set(pinned)

    def roleNames(self):
        return {Qt.UserRole + n + 1: name.encode() for n, name in enumerate(self.fields)}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.definitions)

    @staticmethod
    def _format(item, value):
        if item["kind"] == "number":
            return f"{value:.{item['decimals']}f}", {}
        state = item["states"].get(str(int(value)), {})
        return state.get("label", str(value)), state

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.definitions):
            return None
        item = self.definitions[index.row()]
        sample = self.samples.get(item["id"], Sample())
        quality = sample.quality
        if quality == "valid" and (time.monotonic() - sample.timestamp) * 1000 > item["stale_ms"]:
            quality = "stale"
        live = quality == "valid"
        record = None if live else self.history.get(item["id"])
        quality_text = QUALITY_TEXT.get(quality, quality)
        verdict = ""
        if live:
            display, state = self._format(item, sample.value)
            color = state.get("color", LIVE_COLOR)
            subtitle = "Hiện thời"
        elif record is not None:
            display, state = self._format(item, record["value"])
            verdict = record["status"]
            color = VERDICT_COLOR.get(verdict, IDLE_COLOR)
            subtitle = f"{record['test_id']}/{record['step_id']} · {record['at']}"
            quality_text = "Yêu cầu đã ACK (chưa xác nhận đầu ra)" if verdict == "ACK" else "Giá trị đã lưu"
        else:
            display, color, subtitle = "—", IDLE_COLOR, quality_text
        source = {"derived": "Yêu cầu", "confirmed": "Xác nhận",
                  "measured": "Đo · thiết bị" if sample.source in ("device", "stm32") else "Đo · mô phỏng"}[item["source"]]
        if item["source"] == "derived":
            subtitle = "Yêu cầu · " + subtitle
        visible = item["id"] in self.pinned or ((self.filter_group == "Tất cả" or item["group"] == self.filter_group)
                                                and (not self.only_related or item["id"] in self.related))
        values = (item["id"], item["label"], item["group"], item["kind"], display, item["unit"], quality_text,
                  color, item["id"] in self.related, visible, source, item["id"] in self.pinned,
                  subtitle, verdict, live, record is not None)
        return values[role - Qt.UserRole - 1] if Qt.UserRole < role <= Qt.UserRole + len(values) else None

    def refresh(self, samples, related=None):
        self.samples = samples
        if related is not None:
            self.related = related
        if self.definitions:
            self.dataChanged.emit(self.index(0), self.index(len(self.definitions) - 1), list(self.roleNames()))
