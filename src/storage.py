"""Atomic session checkpoints; workers never reference Qt widgets or models."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import uuid

from PySide6.QtCore import QObject, QSaveFile, QIODevice, QTimer, Signal


def read_session(path):
    """Never resume an interrupted process from disk."""
    data = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Session must be an object')
    if data.get('state') in ('running', 'stopping', 'paused'):
        data['state'] = 'interrupted'
        data['verdict'] = 'ERROR'
        data['recovery_note'] = 'Phiên chưa kết thúc; không tự tiếp tục hoặc phát lại lệnh.'
    return data


def _scan(folder):
    recovered = []
    try:
        for path in sorted(folder.glob('*.json'))[-100:]:
            try:
                old = read_session(path)
                if old.get('state') == 'interrupted':
                    recovered.append(old['id'])
            except (OSError, ValueError, KeyError):
                continue
    except OSError:
        pass
    return recovered


def _write(folder, snapshot):
    sid = snapshot['id']
    uuid.UUID(sid)
    folder.mkdir(parents=True, exist_ok=True)
    content = json.dumps(snapshot, ensure_ascii=False, indent=2, allow_nan=False).encode('utf-8')
    file = QSaveFile(str(folder / f'{sid}.json'))
    if not file.open(QIODevice.WriteOnly):
        raise OSError(file.errorString())
    if file.write(content) != len(content) or not file.commit():
        raise OSError(file.errorString())


class SessionStore(QObject):
    changed = Signal(str)
    idle = Signal()
    recovered = Signal(object)

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self.folder = Path(folder)
        self.status = 'Chưa có phiên'
        self.pending = None
        self.future = None
        self.operation = None
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='bench-storage')
        self.closed = False
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self._collect)
        # Only immutable snapshots/paths cross threads. Completion is polled on
        # the GUI thread, avoiding QObject/QRunnable ownership races on Windows.

    @property
    def busy(self):
        return self.future is not None or self.pending is not None

    def scan(self):
        if self.closed or self.busy:
            return
        self.operation = 'scan'
        self.future = self.executor.submit(_scan, self.folder)
        self.timer.start()

    def save(self, snapshot):
        if self.closed:
            return
        self.pending = snapshot
        self._status('Đang lưu…')
        if self.future is None:
            self._start_write()

    def _status(self, text):
        self.status = text
        self.changed.emit(text)

    def _start_write(self):
        snapshot, self.pending = self.pending, None
        self.operation = 'write'
        self.future = self.executor.submit(_write, self.folder, snapshot)
        self.timer.start()

    def _collect(self):
        if self.future is None or not self.future.done():
            return
        operation = self.operation
        future, self.future = self.future, None
        try:
            result = future.result()
        except Exception as error:
            if operation == 'write':
                self._status(f'Lỗi lưu: {error}')
            else:
                self.recovered.emit([])
        else:
            if operation == 'scan':
                self.recovered.emit(result)
            elif self.pending is None:
                self._status('Đã lưu')
        if self.pending is not None:
            self._start_write()
        else:
            self.timer.stop()
            self.idle.emit()

    def close(self):
        if self.busy:
            raise RuntimeError('Drain session checkpoints before closing storage')
        self.closed = True
        self.timer.stop()
        self.executor.shutdown(wait=False)
