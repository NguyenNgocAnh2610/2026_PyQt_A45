"""Application identity and repository-relative resources."""
from pathlib import Path

APP_NAME = "GIÁ THỬ"
APP_VERSION = "1.0.0"
TESTBENCH_MODEL = "A45"
# Stable storage namespace: changing display/model labels must not lose settings.
SETTINGS_ORGANIZATION = "A54"
ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"
