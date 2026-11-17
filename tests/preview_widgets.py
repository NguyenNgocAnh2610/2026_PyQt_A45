"""UI dictionary: python -m tests.preview_widgets [--capture directory]."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Callable
import unicodedata

from PySide6.QtCore import QFileSystemWatcher, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QPlainTextEdit,
    QPushButton, QScrollArea, QSplitter, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from src.common.config import ASSETS_DIR, TESTBENCH_MODEL
from src.common.styles import apply_theme, prepare_page_style
from tests.preview_login import create_preview as create_login_preview
from tests.preview_main import create_preview as create_main_preview
from tests.widget_samples import SAMPLES, create_sample, create_stylesheet_sample


@dataclass(frozen=True)
class PagePreview:
    title: str
    stylesheet: str | None  # Relative to assets/styles; None means common only.
    factory: Callable[[Path], QWidget]
    source: str
    usage: str


# Explicit opt-in: return a fresh widget with demo data, without QApplication,
# an event loop, or hardware access. Never auto-import discovered Python files.
PAGE_PREVIEWS = (
    PagePreview(
        "Login", "login.qss", create_login_preview,
        "src/ui/widgets/login_page.py",
        "python -m tests.preview_login\n\n"
        "Demo: admin / 123456. Thành công chỉ đổi thông báo trong preview.\n"
        "Preview không ghi cấu hình; main.py chỉ lưu tên đăng nhập khi chọn ghi nhớ.\n\n"
        "from tests.preview_login import create_preview\n"
        "page = create_preview()  # Sau khi đã tạo QApplication và nạp theme",
    ),
    PagePreview(
        "Cửa sổ chính", "main.qss", create_main_preview,
        "src/ui/main_window.py",
        "python -m tests.preview_main\n\n"
        "Ba chế độ mô phỏng; 24 bài 1101K; cấu hình và kết quả preview dùng thư mục tạm.\n"
        "Chọn lại mục để mở lại preview.",
    ),
)


@dataclass(frozen=True)
class Entry:
    key: str
    title: str
    keywords: str
    stylesheet: Path
    usage: str
    sample: str | None = None
    page: PagePreview | None = None


def search_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
    return "".join(char for char in normalized if not unicodedata.combining(char))


class WidgetGallery(QMainWindow):
    """Developer preview window; application UI stays in src/ui."""

    def __init__(self, assets_dir: Path = ASSETS_DIR):
        super().__init__()
        self.assets_dir = Path(assets_dir).resolve()
        self.styles_dir = self.assets_dir / "styles"
        self.entries: dict[str, Entry] = {}
        self.current_key: str | None = None
        self.preview_widget: QWidget | None = None
        self.setWindowTitle(f"{TESTBENCH_MODEL} — Từ điển giao diện")
        self.resize(1440, 960)
        self.setMinimumSize(960, 640)
        self._build_ui()
        self.reload_timer = QTimer(self)
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(200)
        self.reload_timer.timeout.connect(self.rescan)
        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._schedule_reload)
        self.watcher.directoryChanged.connect(self._schedule_reload)
        self.rescan()

    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(20, 20, 20, 20)
        header = QHBoxLayout()
        title = QLabel(f"Từ điển giao diện {TESTBENCH_MODEL}")
        title.setProperty("role", "title")
        header.addWidget(title)
        header.addStretch()
        refresh = QPushButton("Quét lại")
        refresh.clicked.connect(self.rescan)
        header.addWidget(refresh)
        layout.addLayout(header)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        splitter = QSplitter()
        layout.addWidget(splitter, 1)
        sidebar = QWidget()
        navigation = QVBoxLayout(sidebar)
        navigation.setContentsMargins(0, 0, 12, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm widget, trang, file QSS…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter_entries)
        navigation.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._selection_changed)
        self.tree.itemClicked.connect(self._reopen_closed_preview)
        navigation.addWidget(self.tree)
        splitter.addWidget(sidebar)
        detail = QWidget()
        content = QVBoxLayout(detail)
        content.setContentsMargins(12, 0, 0, 0)
        self.entry_title = QLabel()
        self.entry_title.setProperty("role", "title")
        content.addWidget(self.entry_title)
        self.metadata = QLabel()
        self.metadata.setWordWrap(True)
        self.metadata.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content.addWidget(self.metadata)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        content.addWidget(self.hint)
        self.tabs = QTabWidget()
        content.addWidget(self.tabs, 1)
        self.preview_area = QScrollArea()
        self.preview_area.setWidgetResizable(True)
        self.tabs.addTab(self.preview_area, "Giao diện")
        self.qss_view = QPlainTextEdit()
        self.qss_view.setReadOnly(True)
        self.tabs.addTab(self.qss_view, "QSS")
        self.usage_view = QPlainTextEdit()
        self.usage_view.setReadOnly(True)
        self.tabs.addTab(self.usage_view, "Cách dùng")
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 1120])

    def _schedule_reload(self, _path: str) -> None:
        self.reload_timer.start()

    def _sync_watcher(self, files: list[Path]) -> None:
        # Watch directories too: editors often replace files by rename on save.
        paths = {self.assets_dir, self.assets_dir.parent}
        if self.styles_dir.is_dir():
            paths.add(self.styles_dir)
            paths.update(path for path in self.styles_dir.rglob("*") if path.is_dir())
        paths.update(files)
        desired = {str(path) for path in paths if path.exists()}
        watched = set(self.watcher.files()) | set(self.watcher.directories())
        if watched - desired:
            self.watcher.removePaths(sorted(watched - desired))
        if desired - watched:
            self.watcher.addPaths(sorted(desired - watched))

    def rescan(self) -> None:
        self.reload_timer.stop()
        previous = self.current_key
        try:
            files = sorted(
                (path for path in self.styles_dir.rglob("*")
                 if path.is_file() and path.suffix.lower() == ".qss"),
                key=lambda path: path.as_posix().casefold(),
            )
            self._sync_watcher(files)
        except OSError as error:
            self.notice.setText(f"Không thể quét thư mục style: {error}")
            return
        common = self.styles_dir / "common.qss"
        try:
            apply_theme(QApplication.instance(), self.assets_dir)
            self.notice.setText(
                f"{len(files)} file QSS • Tự cập nhật khi lưu QSS • Preview dùng dữ liệu mô phỏng"
            )
        except (OSError, UnicodeError) as error:
            self.notice.setText(f"Không thể nạp common.qss; giữ theme trước đó. {error}")
        self.entries = {}
        self.tree.blockSignals(True)
        self.tree.clear()
        widgets = QTreeWidgetItem(self.tree, ["WIDGET DÙNG CHUNG"])
        pages = QTreeWidgetItem(self.tree, ["TRANG UI / QSS RIÊNG"])
        for group in (widgets, pages):
            group.setFlags(group.flags() & ~Qt.ItemIsSelectable)
        for key, title, aliases, usage in SAMPLES:
            self._add_entry(widgets, Entry(f"widget:{key}", title, aliases, common, usage, sample=key))
        registered = set()
        for page in PAGE_PREVIEWS:
            if page.stylesheet:
                registered.add(page.stylesheet)
            self._add_entry(pages, Entry(
                f"page:{page.source}", page.title, page.source,
                self.styles_dir / page.stylesheet if page.stylesheet else common,
                page.usage, page=page,
            ))
        for path in files:
            relative = path.relative_to(self.styles_dir).as_posix()
            if relative == "common.qss" or relative in registered:
                continue
            self._add_entry(pages, Entry(
                f"qss:{relative}", relative, relative, path,
                "Chưa liên kết UI thật. Bộ mẫu chỉ thể hiện selector khớp với widget mẫu.\n"
                "Selector objectName/property riêng cần đúng UI tương ứng.\n\n"
                "Để liên kết: tạo create_preview(assets_dir=ASSETS_DIR) trong tests/preview_<trang>.py,\n"
                "sau đó thêm PagePreview vào PAGE_PREVIEWS trong tests/preview_widgets.py.\n"
                "Factory trả về widget mới, dùng dữ liệu giả và không tạo QApplication.\n"
                "Hàm main() của preview độc lập tạo QApplication, nạp theme rồi gọi factory.",
            ))
        self.tree.expandAll()
        selected = None
        for group in (widgets, pages):
            for index in range(group.childCount()):
                item = group.child(index)
                if item.data(0, Qt.UserRole) == previous:
                    selected = item
        selected = selected or widgets.child(0)
        self.tree.setCurrentItem(selected)
        self.tree.blockSignals(False)
        self._filter_entries(self.search.text())
        self._show_entry(selected.data(0, Qt.UserRole), rebuild=False)

    def _add_entry(self, group: QTreeWidgetItem, entry: Entry) -> None:
        self.entries[entry.key] = entry
        item = QTreeWidgetItem(group, [entry.title])
        item.setData(0, Qt.UserRole, entry.key)
        item.setToolTip(0, str(entry.stylesheet))

    def _filter_entries(self, query: str) -> None:
        words = search_text(query).split()
        for index in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(index)
            visible = False
            for child_index in range(group.childCount()):
                item = group.child(child_index)
                entry = self.entries[item.data(0, Qt.UserRole)]
                text = search_text(f"{entry.title} {entry.keywords} {entry.stylesheet.name}")
                matches = all(word in text for word in words)
                item.setHidden(not matches)
                visible = visible or matches
            group.setHidden(not visible)

    def _selection_changed(self, current, _previous) -> None:
        if current and current.data(0, Qt.UserRole):
            self._show_entry(current.data(0, Qt.UserRole))

    def _reopen_closed_preview(self, item, _column) -> None:
        if (item.data(0, Qt.UserRole) == self.current_key
                and self.preview_widget is not None and self.preview_widget.isHidden()):
            self._show_entry(self.current_key)

    def _clear_preview(self) -> None:
        old = self.preview_area.takeWidget()
        self.preview_widget = None
        if old is not None:
            if hasattr(old, "closed"):
                old.closed.connect(old.deleteLater)
                old.hide()
                old.close()
                return
            old.close()
            old.deleteLater()

    def _show_entry(self, key: str, rebuild: bool = True) -> None:
        entry = self.entries[key]
        changed = self.current_key != key
        self.current_key = key
        self.entry_title.setText(entry.title)
        source = entry.page.source if entry.page else "Bộ widget mẫu"
        self.metadata.setText(f"UI: {source}\nQSS: {entry.stylesheet}")
        self.usage_view.setPlainText(entry.usage)
        self.hint.setText(
            "UI thật với dữ liệu demo. Sửa Python cần khởi động lại preview."
            if entry.page else
            "Thử trực tiếp chuột và bàn phím; xem tab Cách dùng để áp dụng."
            if entry.sample else
            "Chưa liên kết UI: selector tên/property riêng có thể không tác động lên bộ mẫu."
        )
        self.qss_view.clear()
        try:
            stylesheet = entry.stylesheet.read_text(encoding="utf-8")
            self.qss_view.setPlainText(stylesheet)
            if rebuild or changed or self.preview_widget is None:
                self._clear_preview()
                if entry.page:
                    widget = entry.page.factory(self.assets_dir)
                elif entry.sample:
                    widget = create_sample(entry.sample)
                else:
                    widget = create_stylesheet_sample()
                widget.setWindowFlags(Qt.Widget)
                self.preview_widget = widget
                self.preview_area.setWidget(widget)
            is_common = entry.stylesheet == self.styles_dir / "common.qss"
            self.preview_widget.setStyleSheet(
                "" if is_common else prepare_page_style(self.preview_widget, stylesheet, self.assets_dir)
            )
        except Exception as error:
            # A broken preview factory must not take down the whole dictionary.
            self._clear_preview()
            self.hint.setText(f"Không thể mở preview: {type(error).__name__}: {error}")

    def closeEvent(self, event) -> None:
        self.reload_timer.stop()
        self.watcher.blockSignals(True)
        self._clear_preview()
        super().closeEvent(event)


def create_gallery(assets_dir: Path = ASSETS_DIR) -> WidgetGallery:
    return WidgetGallery(assets_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path)
    args = parser.parse_args()
    app = QApplication(sys.argv)
    apply_theme(app)
    gallery = create_gallery()
    if args.capture:
        args.capture.mkdir(parents=True, exist_ok=True)
        pages = {"widgets": gallery, "login": create_login_preview(), "main": create_main_preview()}
        for name, page in pages.items():
            page.show()
            app.processEvents()
            if not page.grab().save(str(args.capture / f"{name}.png")):
                raise RuntimeError(f"Could not capture {name}")
            if name == "login":
                compact = create_login_preview(canvas_width=960)
                compact.show()
                app.processEvents()
                if not compact.grab().save(str(args.capture / "login_minimum.png")):
                    raise RuntimeError("Could not capture login_minimum")
                compact.close()
            page.close()
        return 0
    gallery.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
