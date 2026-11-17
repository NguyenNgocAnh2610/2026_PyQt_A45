"""Navigation and login lifecycle checks using an independent demo profile."""
import tempfile
import time
import unittest

from PySide6.QtCore import QAbstractAnimation, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from main import ApplicationFlow
from src.common.styles import apply_theme
from tests.test_bench import alternative_profile


class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        apply_theme(cls.app)

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.flow = ApplicationFlow(
            self.app, alternative_profile(), storage_dir=self.folder.name,
        )
        self.flow.login.show()

    def tearDown(self):
        window = self.flow.main_window
        if window is not None:
            window.close()
            deadline = time.monotonic() + 3
            while not window.backend.closed and time.monotonic() < deadline:
                QTest.qWait(20)
            self.assertTrue(window.backend.closed)
            window.deleteLater()
        self.flow.login.close()
        self.flow.login.deleteLater()
        self.flow.deleteLater()
        QTest.qWait(1)
        self.folder.cleanup()

    def login(self):
        page = self.flow.login
        page.username_edit.setText('admin')
        page.password_edit.setText('123456')
        QTest.mouseClick(page.login_button, Qt.LeftButton)
        QTest.qWait(30)
        return self.flow.main_window

    def wait_transition(self, window):
        # Animation frames depend on the GUI event loop/rendering load. Wait for
        # the observed outcome with a bound instead of assuming exactly 200 ms.
        deadline = time.monotonic() + 1
        while window.pages.cover.isVisible() and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertFalse(window.pages.cover.isVisible(),
                         f'page={window.pages.currentIndex()} state={window.pages.transition.state()} '
                         f'time={window.pages.transition.currentTime()} opacity={window.pages.effect.opacity()}')

    def test_authentication_opens_only_one_workspace(self):
        page = self.flow.login
        page.username_edit.setText('admin')
        page.password_edit.setText('wrong')
        page.login_button.click()
        self.assertIsNone(self.flow.main_window)
        self.assertTrue(page.isVisible())
        window = self.login()
        self.assertFalse(page.isVisible())
        self.assertTrue(window.isVisible())
        self.assertEqual(window.pages.currentIndex(), 0)
        self.flow.open_workspace('admin')
        self.assertIs(self.flow.main_window, window)

    def test_all_tabs_select_exclusively_and_preserve_workspace(self):
        window = self.login()
        original = window.pages.widget(0)
        window.serial_edit.setText('DEMO-123')
        window.connection_bar.adapter.setCurrentIndex(2)
        for button, index in window.nav_buttons:
            self.assertTrue(button.isEnabled())
            QTest.mouseClick(button, Qt.LeftButton)
            self.wait_transition(window)
            self.assertEqual(window.pages.currentIndex(), index)
            self.assertEqual(window.navigation.checkedId(), index)
            self.assertEqual(sum(b.isChecked() for b, _ in window.nav_buttons), 1)
            self.assertEqual(window.page_heading.text(), window.page_titles[index][0])
            self.assertFalse(window.pages.cover.isVisible())
        window.navigation.button(0).click()
        self.assertIs(window.pages.widget(0), original)
        self.assertEqual(window.serial_edit.text(), 'DEMO-123')
        self.assertEqual(window.connection_bar.adapter.currentData(), 'uart')
        window.navigation.button(0).click()
        self.assertTrue(window.navigation.button(0).isChecked())

    def test_rapid_navigation_resize_and_close_during_transition(self):
        window = self.login()
        for index in (2, 4, 1, 0, 3):
            window.navigation.button(index).click()
            QTest.qWait(10)
        window.resize(1120, 680)
        self.assertEqual(window.pages.currentIndex(), 3)
        self.assertEqual(window.pages.cover.geometry(), window.pages.rect())
        self.wait_transition(window)
        self.assertFalse(window.pages.cover.isVisible())
        self.assertEqual(window.pages.transition.state(), QAbstractAnimation.Stopped)
        window.navigation.button(2).click()
        self.assertTrue(window.pages.cover.isVisible())
        window.close()
        QTest.qWait(50)
        self.assertFalse(window.isVisible())
        self.assertFalse(window.backend.monitor_enabled)
        self.assertEqual(window.pages.transition.state(), QAbstractAnimation.Stopped)

    def test_transition_deadline_clears_cover_when_animation_clock_stalls(self):
        window = self.login()
        window.navigation.button(2).click()
        window.pages.transition.pause()
        self.assertTrue(window.pages.cover.isVisible())
        self.wait_transition(window)
        self.assertEqual(window.pages.transition.state(), QAbstractAnimation.Stopped)


if __name__ == '__main__':
    unittest.main()
