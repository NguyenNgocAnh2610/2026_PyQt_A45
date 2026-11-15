"""Run with python -m unittest discover -s tests."""
import unittest
import tempfile
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit

from src.common.styles import apply_theme
from src.ui.widgets.login_page import InformationDialog, LoginPage, USERNAME_SETTING, fitted_canvas_width


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self):
        self.calls = []
        self.temp = tempfile.TemporaryDirectory()
        self.settings_path = str(Path(self.temp.name) / "login.ini")
        self.settings = QSettings(self.settings_path, QSettings.IniFormat)

        def authenticate(user, password):
            self.calls.append((user, password))
            return user == "admin" and password == "123456"

        self.page = LoginPage(authenticate, settings=self.settings, canvas_width=1280)
        self.spy = QSignalSpy(self.page.login_success)

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()
        self.settings.sync()
        self.temp.cleanup()

    def test_empty_fields_do_not_call_authentication(self):
        QTest.mouseClick(self.page.login_button, Qt.LeftButton)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.page.status_label.property("state"), "error")

    def test_rejected_password_is_cleared(self):
        self.page.username_edit.setText("admin")
        self.page.password_edit.setText("wrong")
        QTest.mouseClick(self.page.login_button, Qt.LeftButton)
        self.assertEqual(self.spy.count(), 0)
        self.assertEqual(self.page.password_edit.text(), "")

    def test_enter_emits_normalized_username(self):
        self.page.username_edit.setText(" admin ")
        self.page.password_edit.setText("123456")
        QTest.keyClick(self.page.password_edit, Qt.Key_Return)
        self.assertEqual(self.spy.count(), 1)
        self.assertEqual(self.spy.at(0), ["admin"])
        self.assertEqual(self.page.status_label.property("state"), "success")

    def test_authentication_errors_are_generic(self):
        def fail(*args):
            raise RuntimeError("private database details")

        self.page.authenticate = fail
        self.page.username_edit.setText("admin")
        self.page.password_edit.setText("password")
        QTest.mouseClick(self.page.login_button, Qt.LeftButton)
        self.assertEqual(self.spy.count(), 0)
        self.assertNotIn("private", self.page.status_label.text())

    def test_password_visibility_toggle(self):
        self.page.password_edit.setText("demo text")
        QTest.mouseClick(self.page.toggle_password, Qt.LeftButton)
        self.assertEqual(self.page.password_edit.echoMode(), QLineEdit.Normal)
        self.assertEqual(self.page.toggle_password.accessibleName(), "Ẩn mật khẩu")
        self.assertEqual(self.page.password_edit.text(), "demo text")
        QTest.mouseClick(self.page.toggle_password, Qt.LeftButton)
        self.assertEqual(self.page.password_edit.echoMode(), QLineEdit.Password)

    def test_remember_persists_only_username_after_success(self):
        self.page.remember.setChecked(True)
        self.page.username_edit.setText(" admin ")
        self.page.password_edit.setText("123456")
        self.page.login_button.click()
        saved = QSettings(self.settings_path, QSettings.IniFormat)
        self.assertEqual(saved.allKeys(), [USERNAME_SETTING])
        self.assertEqual(saved.value(USERNAME_SETTING), "admin")
        self.assertNotIn("123456", Path(self.settings_path).read_text(encoding="utf-8"))
        reopened = LoginPage(self.page.authenticate, settings=saved, canvas_width=1280)
        try:
            self.assertEqual(reopened.username_edit.text(), "admin")
            self.assertTrue(reopened.remember.isChecked())
            self.assertEqual(reopened.password_edit.text(), "")
            reopened.remember.setChecked(False)
            self.assertFalse(saved.contains(USERNAME_SETTING))
        finally:
            reopened.close()
            reopened.deleteLater()

    def test_failed_auth_does_not_save_username(self):
        self.page.remember.setChecked(True)
        self.page.username_edit.setText("admin")
        self.page.password_edit.setText("wrong")
        self.page.login_button.click()
        self.assertEqual(self.settings.allKeys(), [])

    def test_success_clears_and_hides_password(self):
        self.page.username_edit.setText("admin")
        self.page.password_edit.setText("123456")
        self.page.toggle_password.click()
        self.page.login_button.click()
        self.assertEqual(self.page.password_edit.text(), "")
        self.assertEqual(self.page.password_edit.echoMode(), QLineEdit.Password)
        self.assertFalse(self.page.toggle_password.isChecked())

    def test_keyboard_navigation_and_editing_clear_old_error(self):
        self.page.show()
        self.page.activateWindow()
        self.app.processEvents()
        self.page.username_edit.setFocus()
        QTest.keyClick(self.page.username_edit, Qt.Key_Return)
        self.assertTrue(self.page.password_edit.hasFocus())
        QTest.keyClick(self.page.password_edit, Qt.Key_Tab)
        self.assertTrue(self.page.toggle_password.hasFocus())
        QTest.keyClick(self.page.toggle_password, Qt.Key_Tab)
        self.assertTrue(self.page.remember.hasFocus())
        self.page.login_button.click()
        self.assertTrue(self.page.username_edit.hasFocus())
        self.assertTrue(self.page.status_label.text())
        QTest.keyClicks(self.page.username_edit, "admin")
        self.assertEqual(self.page.status_label.text(), "")

    def test_help_buttons_open_real_dialogs_without_authentication(self):
        for button, title in ((self.page.forgot_button, "Quên mật khẩu"),
                              (self.page.support_button, "Hỗ trợ sử dụng")):
            with self.subTest(title=title):
                button.click()
                self.app.processEvents()
                dialogs = [d for d in self.page.findChildren(InformationDialog) if d.isVisible()]
                self.assertEqual(len(dialogs), 1)
                self.assertEqual(dialogs[0].windowTitle(), title)
                dialogs[0].close()
                self.app.processEvents()
        self.assertEqual(self.calls, [])

    def test_help_dialog_closes_with_keyboard_and_reopens_without_duplicates(self):
        self.page.show()
        self.page.support_button.click()
        self.app.processEvents()
        dialog = self.page._information_dialog
        self.page.support_button.click()
        self.assertIs(self.page._information_dialog, dialog)
        QTest.keyClick(dialog.accept_button, Qt.Key_Return)
        self.assertIsNone(self.page._information_dialog)
        self.assertTrue(self.page.isVisible())
        self.page.forgot_button.click()
        self.app.processEvents()
        QTest.keyClick(self.page._information_dialog, Qt.Key_Escape)
        self.assertIsNone(self.page._information_dialog)
        self.assertTrue(self.page.isVisible())
        self.page.support_button.click()
        dialog = self.page._information_dialog
        self.page.close()
        self.assertIsNone(self.page._information_dialog)
        self.assertFalse(dialog.isVisible())
        self.assertEqual(self.calls, [])

    def test_dialog_type_size_is_independent_of_login_canvas(self):
        small = LoginPage(lambda *_: False, canvas_width=960)
        try:
            small.support_button.click()
            self.page.support_button.click()
            self.app.processEvents()
            first = small._information_dialog.findChild(QLabel, "informationTitle")
            second = self.page._information_dialog.findChild(QLabel, "informationTitle")
            self.assertEqual(first.font().pixelSize(), 23)
            self.assertEqual(first.font().pixelSize(), second.font().pixelSize())
        finally:
            small.close()
            small.deleteLater()

    def test_fixed_canvas_controls_stay_inside_at_smaller_screen_sizes(self):
        for available in (QSize(1920, 1080), QSize(1366, 768), QSize(1024, 768), QSize(1280, 720)):
            width = fitted_canvas_width(available)
            page = LoginPage(lambda *_: False, canvas_width=width)
            try:
                self.assertLessEqual(page.width(), available.width() - 40)
                self.assertLessEqual(page.height(), available.height() - 79)
                initial = page.size()
                page.resize(1800, 1100)
                self.assertEqual(page.size(), initial)
                for control in (page.username_edit, page.password_edit, page.toggle_password,
                                page.remember, page.login_button, page.support_button):
                    self.assertTrue(page.rect().contains(control.geometry()))
                self.assertTrue(page.password_edit.geometry().contains(page.toggle_password.geometry()))
                self.assertFalse(page.status_label.geometry().intersects(page.login_button.geometry()))
            finally:
                page.close()
                page.deleteLater()
