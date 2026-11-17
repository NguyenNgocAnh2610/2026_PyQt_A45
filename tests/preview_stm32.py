"""Standalone two-bank STM32 preview. Always simulation; never opens COM."""
import argparse
from pathlib import Path
import tempfile

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from src.backend import Backend
from src.common.styles import apply_theme
from src.ui.widgets.stm32_registers import Stm32RegistersDialog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', help='Save a PNG and exit')
    args = parser.parse_args()
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    with tempfile.TemporaryDirectory(prefix='a45_stm32_preview_') as folder:
        backend = Backend(storage_dir=folder)
        dialog = Stm32RegistersDialog(backend)
        # Example draft, not transmitted automatically.
        backend.stage_stm32(1, [1, 2])
        backend.stage_stm32(7, [0xFF9C])
        dialog.show()
        backend.request_stm32(simulation=True)

        def finish():
            backend.shutdown_ready.connect(app.quit)
            backend.shutdown()
            if backend.closed:
                app.quit()

        def capture():
            path = Path(args.capture)
            path.parent.mkdir(parents=True, exist_ok=True)
            if not dialog.grab().save(str(path)):
                raise RuntimeError('Cannot save preview PNG')
            print('STM32 preview captured; no COM opened.')
            finish()

        app.setQuitOnLastWindowClosed(False)
        dialog.finished.connect(finish)
        if args.capture:
            QTimer.singleShot(350, capture)
        app.exec()


if __name__ == '__main__':
    main()
