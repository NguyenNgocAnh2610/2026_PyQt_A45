"""Page reveal animation that leaves Widgets and Qt Quick pages alive."""
from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer
from PySide6.QtWidgets import QFrame, QGraphicsOpacityEffect, QStackedWidget


class NavigationStack(QStackedWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Animate a cover, not the pages: Qt Quick keeps its own rendering path.
        self.cover = QFrame(self)
        self.cover.setObjectName('navigationCover')
        self.cover.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.cover.setFocusPolicy(Qt.NoFocus)
        self.effect = QGraphicsOpacityEffect(self.cover)
        self.cover.setGraphicsEffect(self.effect)
        self.transition = QPropertyAnimation(self.effect, b'opacity', self)
        self.transition.setDuration(160)
        self.transition.setEasingCurve(QEasingCurve.OutCubic)
        self.transition.finished.connect(self.finish_transition)
        # Qt Quick may suspend the shared animation clock while its page is
        # hidden/re-exposed. Never leave an opaque cover waiting on that clock.
        self.transition_deadline = QTimer(self)
        self.transition_deadline.setSingleShot(True)
        self.transition_deadline.timeout.connect(self.finish_transition)
        self.cover.hide()

    def navigate(self, index):
        if not 0 <= index < self.count() or index == self.currentIndex():
            return
        self.finish_transition()
        self.setCurrentIndex(index)
        if self.isVisible():
            self.cover.setGeometry(self.rect())
            self.cover.raise_()
            self.effect.setOpacity(0.85)
            self.cover.show()
            self.transition.setStartValue(0.85)
            self.transition.setEndValue(0.0)
            self.transition.start()
            self.transition_deadline.start(self.transition.duration() + 50)

    def finish_transition(self):
        self.transition_deadline.stop()
        self.transition.stop()
        self.cover.hide()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.cover.setGeometry(self.rect())

    def hideEvent(self, event):
        self.finish_transition()
        super().hideEvent(event)
