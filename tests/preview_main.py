"""Standalone main window preview: python -m tests.preview_main."""
import sys
import argparse
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from src.common.config import ASSETS_DIR
from src.common.styles import apply_theme
from src.ui.main_window import MainWindow
from src.common.profiles import load_profile
from src.common.testing import Mode, SCENARIOS


def create_preview(assets_dir: Path = ASSETS_DIR, profile=None) -> MainWindow:
    """Match the gallery factory signature; use demo data only."""
    temporary = tempfile.TemporaryDirectory(prefix="a45_preview_")
    window = MainWindow("admin (demo)", profile=profile, storage_dir=temporary.name, assets_dir=assets_dir)
    window._preview_temporary = temporary

    def cleanup():
        if window.backend.closed and not window.backend.store.busy:
            temporary.cleanup()

    window.closed.connect(cleanup)
    window.backend.store.idle.connect(cleanup)
    return window


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--capture", type=Path)
    parser.add_argument("--width", type=int, default=1560)
    parser.add_argument("--height", type=int, default=940)
    parser.add_argument("--state", choices=("idle", "running", "paused", "finished", "stale", "manual"), default="idle",
                        help="manual = P01 tới hộp thoại nhập tần số; các trạng thái khác tự bỏ qua nhập tay")
    parser.add_argument("--scenario", choices=SCENARIOS, default="normal")
    parser.add_argument("--connection", choices=('mock', 'rtu', 'uart'), default='mock',
                        help='Preview lựa chọn kết nối; không tự mở COM')
    parser.add_argument("--connection-details", action='store_true', help='Preview/chụp hộp thoại serial')
    args = parser.parse_args()
    if args.connection != 'mock' and args.state != 'idle':
        parser.error('Preview kết nối thật chỉ dùng --state idle; không tự chạy phần cứng.')
    app = QApplication(sys.argv)
    apply_theme(app)
    window = create_preview(profile=load_profile(args.profile) if args.profile else None)
    window.resize(args.width, args.height)
    window.show()
    window.connection_bar.adapter.setCurrentIndex(window.connection_bar.adapter.findData(args.connection))
    if args.connection_details:
        window.connection_bar._show_details()
    backend = window.backend
    backend.configure(scenario=args.scenario)
    timer = QTimer(window)
    elapsed = 0
    started = False

    if args.state != "manual":
        # Demo operator: leave manual entries empty (nominal, "mặc định, chưa đo").
        backend.manual_input_changed.connect(
            lambda: backend.manual_request and QTimer.singleShot(300, lambda: backend.submit_manual({})))

    def capture():
        nonlocal elapsed, started
        elapsed += 100
        if args.state != "idle" and not started and backend.connection == "Sẵn sàng · MÔ PHỎNG":
            backend.configure(mode=Mode.AUTO if args.state in ("finished", "paused") else Mode.MANUAL,
                              serial_number="DEMO-1101K-001",
                              time_scale=1.0 if args.state == "paused" else 60.0 if args.state == "manual" else 10.0)
            window.serial_edit.setText(backend.serial_number)
            first = "P01" if args.state == "manual" else "P04"
            backend.select_test(first if any(t['id'] == first for t in backend.tests) else backend.tests[0]['id'])
            window._follow()
            backend.start()
            started = True
        ready = args.state == "idle" and elapsed >= 500
        ready |= args.state == "manual" and window._manual_dialog is not None and window._manual_dialog.isVisible()
        ready |= args.state == "running" and started and backend.busy and bool(backend.samples)
        ready |= args.state == "finished" and started and not backend.busy
        if args.state == "paused" and started and backend.phase == "settling" and len(backend.session["attempts"]) >= 5:
            backend.pause()
        ready |= args.state == "paused" and backend.paused
        if args.state == "stale" and started and elapsed >= 1300:
            backend.disconnect_device()
            ready = True
        if args.capture and (ready or elapsed > 60000):
            timer.stop()
            args.capture.parent.mkdir(parents=True, exist_ok=True)
            app.processEvents()
            target = window.connection_bar.details if args.connection_details else window
            if args.state == "manual" and window._manual_dialog is not None:
                target = window._manual_dialog
            if not target.grab().save(str(args.capture)):
                raise RuntimeError("Không lưu được ảnh preview")
            print(f"Captured {args.capture}; state={backend.phase}".encode('ascii', 'backslashreplace').decode('ascii'))
            window.close()

    if args.state != "idle":
        backend.connect_device()
    if args.capture or args.state != "idle":
        timer.timeout.connect(capture)
        timer.start(100)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
