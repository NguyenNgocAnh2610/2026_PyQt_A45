"""Run with python -m unittest discover -s tests."""
import unittest

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QLineEdit

from src.common.styles import apply_theme
from src.ui.widgets.login_page import LoginPage


class LoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self):
        self.calls = []

        def authenticate(user, password):
            self.calls.append((user, password))
            return user == "admin" and password == "123456"

        self.page = LoginPage(authenticate)
        self.spy = QSignalSpy(self.page.login_success)

    def tearDown(self):
        self.page.close()
        self.page.deleteLater()
        self.app.processEvents()

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
        QTest.mouseClick(self.page.toggle_password, Qt.LeftButton)
        self.assertEqual(self.page.password_edit.echoMode(), QLineEdit.Normal)
        QTest.mouseClick(self.page.toggle_password, Qt.LeftButton)
        self.assertEqual(self.page.password_edit.echoMode(), QLineEdit.Password)
