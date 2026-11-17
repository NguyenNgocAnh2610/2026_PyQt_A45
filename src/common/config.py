"""Application identity and repository-relative resources."""
from pathlib import Path

APP_NAME = "GIÁ THỬ"
APP_VERSION = "1.0.0"
TESTBENCH_MODEL = "A45"
# Stable storage namespace: changing display/model labels must not lose settings.
SETTINGS_ORGANIZATION = "A54"
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"

# Choices only: no physical baudrate is selected until configured explicitly.
SERIAL_BAUDRATES = (1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200)
MAX_MONITOR_CHANNELS = 6
