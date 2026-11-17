"""Shared, hardware-independent contracts for configured test benches."""
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs"
DEFAULT_PROFILE = CONFIG_DIR / "a45" / "system.json"
POLL_MS = 200
STALE_MS = 1000
TRANSACTION_TIMEOUT_MS = 1000
OPERATION_TIMEOUT_MS = 2500


class Mode(str, Enum):
    SELF = "Tự kiểm tra giá thử"
    MANUAL = "Kiểm tra bằng tay"
    AUTO = "Kiểm tra tự động"


class Result(str, Enum):
    PENDING = "Chưa chạy"
    RUNNING = "Đang chạy"
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    ABORTED = "ABORTED"


@dataclass(frozen=True)
class Sample:
    value: Any = None
    timestamp: float = 0.0
    quality: str = "unknown"
    source: str = "mock"


@dataclass(frozen=True)
class Profile:
    system: dict
    target: dict
    hardware: dict
    fixtures: dict
    path: Path

    @property
    def signals(self):
        return self.system["signals"]

    @property
    def tests(self):
        return self.target["tests"]

    @property
    def diagnostics(self):
        return self.system["diagnostics"]


SCENARIOS = {
    "normal": "Bình thường",
    "fail": "Một phép đo không đạt",
    "slow": "Phản hồi chậm",
    "timeout": "Timeout giao dịch",
    "disconnect": "Mất kết nối khi chạy",
    "stale": "Dữ liệu hết hạn",
    "protection": "Lỗi bảo vệ",
    "stop_timeout": "Không xác nhận dừng",
}
# CPUv1.0 has no fault flag and no sample timestamp: 'protection'/'stale'
# cannot be represented on the two-bank runner.
STM32_SCENARIOS = {k: v for k, v in SCENARIOS.items() if k not in ("protection", "stale")}
READY_SIMULATION = "Sẵn sàng · MÔ PHỎNG"
