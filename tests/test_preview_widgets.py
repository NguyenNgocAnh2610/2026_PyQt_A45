"""Gallery integration tests; all filesystem changes use temporary assets."""
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtTest import QSignalSpy, QTest
from PySide6.QtWidgets import QApplication, QPushButton

from src.common.config import ASSETS_DIR
from src.common.styles import apply_theme
from src.ui.widgets.login_page import LoginPage
from tests.preview_widgets import PAGE_PREVIEWS, PagePreview, WidgetGallery


class GalleryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.assets = Path(self.temp.name) / "assets"
        shutil.copytree(ASSETS_DIR / "styles", self.assets / "styles")
        shutil.copytree(ASSETS_DIR / "images" / "icons", self.assets / "images" / "icons")
        shutil.copy2(ASSETS_DIR / "images" / "login.png", self.assets / "images" / "login.png")
        self.gallery = WidgetGallery(self.assets)

    def tearDown(self):
        self.gallery.close()
        self.gallery.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
        self.temp.cleanup()
        apply_theme(self.app)

    def wait_for(self, predicate):
        for _ in range(100):
            if predicate():
                return
            QTest.qWait(50)
        self.fail(
            f"Timed out waiting for gallery filesystem update: {self.gallery.current_key}; "
            f"{self.gallery.hint.text()}; {self.gallery.notice.text()}; "
            f"QSS tail: {self.gallery.qss_view.toPlainText()[-100:]!r}"
        )

    def select(self, key):
        for group_index in range(self.gallery.tree.topLevelItemCount()):
            group = self.gallery.tree.topLevelItem(group_index)
            for index in range(group.childCount()):
                item = group.child(index)
                if item.data(0, Qt.UserRole) == key:
                    self.gallery.tree.setCurrentItem(item)
                    return item
        self.fail(f"Missing entry: {key}")

    def test_every_registered_page_and_widget_can_be_constructed(self):
        for key in self.gallery.entries:
            with self.subTest(key=key):
                self.select(key)
                self.assertIsNotNone(self.gallery.preview_widget, self.gallery.hint.text())

    def test_search_supports_vietnamese_and_qt_class_names(self):
        buttons = self.select("widget:buttons")
        self.gallery.search.setText("nut bam")
        self.assertFalse(buttons.isHidden())
        self.gallery.search.setText("QPushButton")
        self.assertFalse(buttons.isHidden())
        self.gallery.search.setText("QLineEdit")
        self.assertTrue(buttons.isHidden())
        self.assertFalse(self.select("widget:inputs").isHidden())

    def test_nested_qss_is_discovered_renamed_and_removed_automatically(self):
        folder = self.assets / "styles" / "new_page"
        folder.mkdir()
        path = folder / "board.qss"
        path.write_text("QPushButton { color: red; }", encoding="utf-8")
        self.wait_for(lambda: "qss:new_page/board.qss" in self.gallery.entries)
        self.select("qss:new_page/board.qss")
        self.assertIsNotNone(self.gallery.preview_widget)
        renamed = path.rename(folder / "renamed.qss")
        self.wait_for(lambda: "qss:new_page/renamed.qss" in self.gallery.entries
                      and "qss:new_page/board.qss" not in self.gallery.entries)
        renamed.unlink()
        self.wait_for(lambda: "qss:new_page/renamed.qss" not in self.gallery.entries)

    def test_real_login_auth_and_atomic_qss_reload_preserve_input(self):
        self.select("page:src/ui/widgets/login_page.py")
        login = self.gallery.preview_widget
        self.assertIsInstance(login, LoginPage)
        login.username_edit.setText("admin")
        login.password_edit.setText("123456")
        spy = QSignalSpy(login.login_success)
        QTest.mouseClick(login.login_button, Qt.LeftButton)
        self.assertEqual(spy.count(), 1)
        global_style = self.app.styleSheet()
        path = self.assets / "styles" / "login.qss"
        updated = path.read_text(encoding="utf-8") + "\n/* atomic save */"
        replacement = path.with_suffix(".tmp")
        replacement.write_text(updated, encoding="utf-8")
        replacement.replace(path)
        # QTextDocument removes a leading UTF-8 BOM from displayed text.
        self.wait_for(lambda: self.gallery.qss_view.toPlainText() == updated.lstrip("\ufeff"))
        self.assertIs(self.gallery.preview_widget, login)
        self.assertEqual(login.username_edit.text(), "admin")
        self.assertEqual(self.app.styleSheet(), global_style)
        # Ensure watching was restored after the editor replaced the file.
        updated += "\n/* subsequent save */"
        path.write_text(updated, encoding="utf-8")
        self.wait_for(lambda: self.gallery.qss_view.toPlainText() == updated.lstrip("\ufeff"))
        self.select("widget:buttons")
        self.assertEqual(self.gallery.preview_widget.styleSheet(), "")

    def test_common_theme_reload_updates_application_without_rebuilding_preview(self):
        original = self.gallery.preview_widget
        path = self.assets / "styles" / "common.qss"
        style = path.read_text(encoding="utf-8") + "\nQLabel { color: #abcdef; }"
        path.write_text(style, encoding="utf-8")
        self.wait_for(lambda: "#abcdef" in self.app.styleSheet())
        self.assertIs(self.gallery.preview_widget, original)

    def test_missing_and_invalid_utf8_styles_recover(self):
        self.select("page:src/ui/widgets/login_page.py")
        path = self.assets / "styles" / "login.qss"
        original = path.read_bytes()
        path.unlink()
        self.wait_for(lambda: self.gallery.preview_widget is None)
        self.assertIn("Không thể mở preview", self.gallery.hint.text())
        path.write_bytes(b"\xff\xfe")
        self.wait_for(lambda: "UnicodeDecodeError" in self.gallery.hint.text())
        path.write_bytes(original)
        self.wait_for(lambda: isinstance(self.gallery.preview_widget, LoginPage))

    def test_broken_factory_does_not_break_navigation(self):
        def fail(_assets):
            raise RuntimeError("Broken demo")

        broken = PagePreview("Broken", None, fail, "demo_broken.py", "")
        with patch("tests.preview_widgets.PAGE_PREVIEWS", PAGE_PREVIEWS + (broken,)):
            self.gallery.rescan()
            self.select("page:demo_broken.py")
            self.assertIsNone(self.gallery.preview_widget)
            self.assertIn("Broken demo", self.gallery.hint.text())
            self.select("widget:buttons")
            self.assertIsNotNone(self.gallery.preview_widget)

    def test_main_close_only_closes_embedded_preview(self):
        self.gallery.show()
        item = self.select("page:src/ui/main_window.py")
        preview = self.gallery.preview_widget
        button = preview.findChild(QPushButton, "closeWorkspace")
        QTest.mouseClick(button, Qt.LeftButton)
        self.wait_for(lambda: preview.isHidden())
        self.assertTrue(self.gallery.isVisible())
        self.gallery.tree.itemClicked.emit(item, 0)
        self.assertIsNot(self.gallery.preview_widget, preview)
        self.assertFalse(self.gallery.preview_widget.isHidden())


if __name__ == "__main__":
    unittest.main()
