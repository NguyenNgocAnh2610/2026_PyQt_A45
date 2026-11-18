"""Configurable workspace. Device state and verdicts belong to Backend."""
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QDateTime, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QLineEdit, QScrollArea, QSplitter, QTreeWidget,
    QTreeWidgetItem, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextBrowser, QFormLayout, QMessageBox, QSizePolicy, QButtonGroup,
)
from PySide6.QtQuickWidgets import QQuickWidget

from src.backend import Backend
from src.common.config import APP_NAME, ASSETS_DIR
from src.common.styles import apply_page_style, set_state
from src.common.testing import Mode, SCENARIOS
from src.common.profiles import specification_issues
from src.ui.widgets.connection_bar import ConnectionBar
from src.ui.widgets.signal_monitor import SignalMonitor
from src.ui.widgets.navigation_stack import NavigationStack
from src.ui.widgets.manual_input import ManualInputDialog


STATUS_TEXT = {'PAUSED': 'Tạm dừng'}


def panel(title):
    box = QFrame()
    box.setProperty('panel', True)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(8)
    if title:
        label = QLabel(title)
        label.setProperty('panelTitle', True)
        layout.addWidget(label)
    return box, layout


class MainWindow(QMainWindow):
    closed = Signal()

    def __init__(self, username, parent=None, *, backend=None, profile=None, storage_dir=None, assets_dir=ASSETS_DIR):
        super().__init__(parent)
        self.setObjectName('workspace')
        self.backend = backend or Backend(profile, username, storage_dir, self)
        self.assets_dir = Path(assets_dir)
        self._closing = False
        self._tree_mode = None
        self._table_signature = None
        self._details_html = None
        self._messages = {}
        self._error_state = ('', '')
        self.setWindowTitle(f"{APP_NAME} — {self.backend.profile.system['name']} · MÔ PHỎNG")
        self.resize(1560, 940)
        self.setMinimumSize(1120, 680)
        available = self.screen().availableGeometry()
        self.resize(min(1560, available.width() - 32), min(940, available.height() - 56))
        self._build_ui(username)
        apply_page_style(self, 'main', self.assets_dir)
        self.backend.changed.connect(self.refresh)
        self.backend.shutdown_ready.connect(self._shutdown_ready)
        self._manual_dialog = None
        self.backend.manual_input_changed.connect(self._manual_input_changed)
        self.clock = QTimer(self)
        self.clock.setInterval(1000)
        self.clock.timeout.connect(self._clock)
        self.clock.start()
        self._clock()
        self.refresh()

    def _build_ui(self, username):
        root = QWidget()
        root.setObjectName('workspaceRoot')
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        header = QFrame()
        header.setObjectName('header')
        row = QHBoxLayout(header)
        row.setContentsMargins(18, 8, 18, 8)
        brand = QVBoxLayout()
        name = QLabel(self.backend.profile.system['name'])
        name.setObjectName('brand')
        brand.addWidget(name)
        sub = QLabel(self.backend.profile.system.get('subtitle', 'TESTBENCH'))
        sub.setObjectName('brandSub')
        brand.addWidget(sub)
        row.addLayout(brand)
        heading = QLabel('Không gian kiểm tra')
        self.page_heading = heading
        heading.setObjectName('heading')
        title = QVBoxLayout()
        title.setSpacing(3)
        title.addWidget(heading)
        subtitle = QLabel('Thiết lập phiên · Theo dõi · Kết quả')
        self.page_subtitle = subtitle
        subtitle.setObjectName('workspaceSubtitle')
        title.addWidget(subtitle)
        row.addSpacing(20)
        row.addLayout(title)
        row.addStretch()
        self.mode_badge = QLabel()
        self.mode_badge.setObjectName('simulation')
        row.addWidget(self.mode_badge)
        user_label = QLabel(username)
        user_label.setObjectName('workspaceUser')
        row.addWidget(user_label)
        self.time_label = QLabel()
        self.time_label.setObjectName('workspaceClock')
        row.addWidget(self.time_label)
        outer.addWidget(header)
        self.connection_bar = ConnectionBar(self.backend)
        self.connection_bar.notice.connect(self._notify)
        outer.addWidget(self.connection_bar)
        body = QHBoxLayout()
        body.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(178)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(8, 22, 8, 16)
        self.nav_buttons = []
        self.navigation = QButtonGroup(self)
        self.navigation.setExclusive(True)
        self.page_titles = {
            0: ('Không gian kiểm tra', 'Thiết lập phiên · Theo dõi · Kết quả'),
            1: ('Cài đặt', 'Cấu hình hệ thống và mô phỏng'),
            2: ('Tổng quan', 'Không gian tổng quan hệ thống'),
            3: ('Lịch sử', 'Không gian tra cứu phiên kiểm tra'),
            4: ('In / Xuất file', 'Không gian báo cáo và xuất dữ liệu'),
        }
        for text, page in [('⌂  Tổng quan', 2), ('▣  Kiểm tra', 0), ('◷  Lịch sử', 3), ('▤  In / Xuất file', 4), ('⚙  Cài đặt', 1)]:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self.navigation.addButton(button, page)
            button.clicked.connect(lambda checked=False, p=page: self._navigate(p))
            self.nav_buttons.append((button, page))
            nav.addWidget(button)
        nav.addStretch()
        footnote = QLabel()
        self.context_note = footnote
        footnote.setObjectName('sidebarFootnote')
        footnote.setWordWrap(True)
        nav.addWidget(footnote)
        close_button = QPushButton('Đóng ứng dụng')
        close_button.setObjectName('closeWorkspace')
        close_button.clicked.connect(self.close)
        nav.addWidget(close_button)
        body.addWidget(sidebar)
        self.pages = NavigationStack()
        self.pages.addWidget(self._workspace())
        self.pages.addWidget(self._settings())
        for index in (2, 3, 4):
            self.pages.addWidget(self._placeholder(self.page_titles[index][0]))
        body.addWidget(self.pages, 1)
        outer.addLayout(body, 1)
        self._navigate(0)
        self.connection_bar.mode_changed.connect(self.refresh)

    def _workspace(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        config, content = panel('')
        fields = QHBoxLayout()
        self.bench_combo = QComboBox()
        self.bench_combo.addItem(self.backend.profile.system['name'])
        self.target_combo = QComboBox()
        self.target_combo.addItem(self.backend.profile.target['name'])
        self.mode_combo = QComboBox()
        self.mode_combo.addItems([m.value for m in Mode])
        self.mode_combo.setCurrentText(self.backend.mode.value)
        self.mode_combo.currentTextChanged.connect(self._configure)
        self.serial_edit = QLineEdit()
        self.serial_edit.setPlaceholderText('Nhập serial của khối')
        self.serial_edit.setMaxLength(128)
        for title, widget in [('Giá thử', self.bench_combo), ('Đối tượng kiểm tra', self.target_combo), ('Chế độ', self.mode_combo), ('Số serial', self.serial_edit)]:
            col = QVBoxLayout()
            col.setSpacing(4)
            field_label = QLabel(title)
            field_label.setProperty('fieldLabel', True)
            col.addWidget(field_label)
            col.addWidget(widget)
            fields.addLayout(col, 1)
        content.addLayout(fields)
        actions = QHBoxLayout()
        self.notice = QLabel('Kết quả MÔ PHỎNG · Các mục chưa đủ đặc tả không được tính PASS')
        self.notice.setObjectName('notice')
        self.notice.setWordWrap(True)
        actions.addWidget(self.notice, 1)
        self.start_button = QPushButton('▶  Bắt đầu kiểm tra')
        self.start_button.setObjectName('startButton')
        self.start_button.clicked.connect(self._start)
        self.pause_button = QPushButton('❚❚  Tạm dừng')
        self.pause_button.setObjectName('pauseButton')
        self.pause_button.clicked.connect(self._toggle_pause)
        self.new_button = QPushButton('↺  Phiên mới')
        self.new_button.setObjectName('newSessionButton')
        self.new_button.clicked.connect(self._new_session)
        for button in (self.start_button, self.pause_button, self.new_button):
            button.setCursor(Qt.PointingHandCursor)
            actions.addWidget(button)
        content.addLayout(actions)
        layout.addWidget(config)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        interior = QWidget()
        inside = QVBoxLayout(interior)
        inside.setContentsMargins(0, 0, 0, 0)
        inside.setSpacing(12)
        upper = QSplitter(Qt.Horizontal)
        upper.setHandleWidth(12)
        upper.setChildrenCollapsible(False)
        tests_box, tests_layout = panel('Danh sách bài kiểm tra')
        tests_box.setMinimumWidth(270)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['Bài kiểm tra', 'Kết quả'])
        self.tree.setColumnWidth(0, 245)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Fixed)
        self.tree.setColumnWidth(1, 110)
        self.tree.setAlternatingRowColors(True)
        self.tree.setIndentation(14)
        self.tree.currentItemChanged.connect(self._selected)
        tests_layout.addWidget(self.tree, 1)
        self.details = QTextBrowser()
        self.details.setMinimumHeight(85)
        self.details.setMaximumHeight(110)
        tests_layout.addWidget(self.details)
        self.running_label = QLabel()
        self.running_label.setObjectName('runningBanner')
        self.running_label.setWordWrap(True)
        tests_layout.addWidget(self.running_label)
        self.progress = QProgressBar()
        self.counts = QLabel()
        self.counts.setObjectName('runCounts')
        self.counts.setWordWrap(True)
        tests_layout.addWidget(self.progress)
        tests_layout.addWidget(self.counts)
        upper.addWidget(tests_box)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        signals_box, signals_layout = panel('Trạng thái & giá trị đo')
        filters = QHBoxLayout()
        self.group_combo = QComboBox()
        self.group_combo.addItems(['Tất cả'] + list(dict.fromkeys(s['group'] for s in self.backend.profile.signals)))
        self.group_combo.currentTextChanged.connect(self._filter_signals)
        self.related_combo = QComboBox()
        self.related_combo.addItems(['Toàn giá thử', 'Liên quan bài đang chạy', 'Liên quan bài đang xem'])
        self.related_combo.setCurrentIndex(2)
        self.related_combo.currentIndexChanged.connect(self._filter_signals)
        for combo in (self.group_combo, self.related_combo):
            combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            combo.setMinimumContentsLength(6)
            combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        follow = QPushButton('Theo dõi bài chạy')
        follow.setObjectName('followRunningTest')
        follow.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        follow.setToolTip('Chuyển đến bài kiểm tra đang chạy trong danh sách.')
        follow.clicked.connect(self._follow)
        filters.addWidget(self.group_combo, 1)
        filters.addWidget(self.related_combo, 1)
        filters.addWidget(follow)
        signals_layout.addLayout(filters)
        self.qml = QQuickWidget()
        self.qml.setClearColor(QColor('#111f31'))
        self.qml.setResizeMode(QQuickWidget.SizeRootObjectToView)
        self.qml.rootContext().setContextProperty('benchSignals', self.backend.signal_model)
        self.qml.rootContext().setContextProperty('statusCount', len(self.backend.signal_model.pinned))
        self.qml.setSource(QUrl.fromLocalFile(str(Path(__file__).parent / 'qml' / 'SignalDashboard.qml')))
        self.qml.setMinimumSize(460, 188)
        self.qml.statusChanged.connect(self._qml_status)
        signals_layout.addWidget(self.qml, 1)
        right_layout.addWidget(signals_box, 1)
        lower = QSplitter(Qt.Horizontal)
        lower.setHandleWidth(12)
        lower.setChildrenCollapsible(False)
        plot_box, plot_layout = panel('Quan sát tín hiệu')
        plot_box.setMinimumWidth(286)
        self.monitor = SignalMonitor(backend=self.backend, channels=self.backend.monitor_channels)
        plot_layout.addWidget(self.monitor, 1)
        lower.addWidget(plot_box)
        result_box, result_layout = panel('Kết quả kiểm tra')
        self.verdict = QLabel('Chưa có phiên')
        self.verdict.setObjectName('verdict')
        result_layout.addWidget(self.verdict)
        self.result_table = QTableWidget(0, 5)
        self.result_table.setHorizontalHeaderLabels(['Lần / Bước / Tín hiệu', 'Giá trị', 'Giới hạn', 'Kết quả', 'Chi tiết'])
        self.result_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.result_table.setAlternatingRowColors(True)
        self.result_table.verticalHeader().hide()
        self.result_table.verticalHeader().setDefaultSectionSize(34)
        self.result_table.setShowGrid(False)
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.result_table.horizontalHeader().setStretchLastSection(True)
        self.result_table.setMinimumHeight(130)
        result_layout.addWidget(self.result_table, 1)
        save_row = QHBoxLayout()
        save = QPushButton('▣  Lưu lại kết quả')
        save.clicked.connect(self.backend.save_again)
        self.save_label = QLabel()
        self.save_label.setWordWrap(True)
        save_row.addWidget(save)
        save_row.addWidget(self.save_label, 1)
        result_layout.addLayout(save_row)
        lower.addWidget(result_box)
        lower.setSizes([340, 560])
        right_layout.addWidget(lower, 1)
        upper.addWidget(right)
        upper.setSizes([330, 1000])
        inside.addWidget(upper, 1)
        scroll.setWidget(interior)
        layout.addWidget(scroll, 1)
        return page

    def _settings(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        box, layout = panel('⚙  Kết nối và cấu hình mô phỏng')
        form = QFormLayout()
        form.addRow('Thiết bị', QLabel('Chọn kết nối tại thanh COM / baud ở đầu cửa sổ.'))
        self.scenario_combo = QComboBox()
        for key, label in getattr(self.backend, 'scenarios', SCENARIOS).items():
            self.scenario_combo.addItem(label, key)
        self.scenario_combo.currentIndexChanged.connect(lambda: self.backend.configure(scenario=self.scenario_combo.currentData()))
        form.addRow('Kịch bản', self.scenario_combo)
        self.speed_combo = QComboBox()
        for speed in (1.0, 10.0, 60.0):
            self.speed_combo.addItem(f'×{speed:g} — mô phỏng', speed)
        self.speed_combo.currentIndexChanged.connect(lambda: self.backend.configure(time_scale=self.speed_combo.currentData()))
        form.addRow('Tốc độ thời gian', self.speed_combo)
        hardware = QLabel('Modbus RTU thật: CHƯA KHẢ DỤNG\nChưa có bảng thanh ghi và trình tự phần cứng đã xác minh.')
        hardware.setWordWrap(True)
        form.addRow('Phần cứng', hardware)
        for label, value in [('Cấu hình đang dùng', self.backend.profile.path), ('Lưu phiên mô phỏng', self.backend.store.folder)]:
            text = QLabel(str(value))
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(label, text)
        layout.addLayout(form)
        explanation = QTextBrowser()
        issues = [(t, specification_issues(t)) for t in self.backend.profile.tests if specification_issues(t)]
        explanation.setHtml('<h3>Các mục chưa đủ đặc tả</h3>' + ''.join(f"<p><b>{escape(t['id'] + ' · ' + t['name'])}</b><br>{escape('; '.join(i))}</p>" for t, i in issues)
            + '<p>Thời gian ổn định, chuẩn bị/kết thúc và tính độc lập của các bài hiện chỉ được mô phỏng. Tự kiểm tra giá thử là bộ demo riêng.</p>')
        layout.addWidget(explanation, 1)
        outer.addWidget(box, 1)
        return page

    def _navigate(self, index):
        if index not in self.page_titles:
            return
        self.pages.navigate(index)
        title, subtitle = self.page_titles[index]
        self.page_heading.setText(title)
        self.page_subtitle.setText(subtitle)
        for button, page in self.nav_buttons:
            button.setChecked(page == index)

    def _placeholder(self, title):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)
        box, content = panel('')
        content.setContentsMargins(32, 32, 32, 32)
        content.addStretch()
        for text, name in [
            ('KHÔNG GIAN LÀM VIỆC', 'placeholderEyebrow'),
            (title, 'placeholderTitle'),
            ('Giao diện chi tiết sẽ được bổ sung ở bước tiếp theo.', 'placeholderHint'),
        ]:
            label = QLabel(text)
            label.setObjectName(name)
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)
            content.addWidget(label)
        content.addStretch()
        layout.addWidget(box)
        return page

    def _clock(self):
        self.time_label.setText(QDateTime.currentDateTime().toString('HH:mm:ss\ndd/MM/yyyy'))

    def _configure(self):
        self.backend.configure(mode=self.mode_combo.currentText())

    def _start(self):
        if self.backend.busy:
            if not self.backend.stopping:
                self.backend.stop()
            return
        if self.backend.mode != Mode.SELF and not self.serial_edit.text().strip():
            self._notify('Chưa nhập số serial', 'Vui lòng nhập số serial của khối trước khi bắt đầu kiểm tra.')
            self.serial_edit.setFocus()
            return
        if not self.connection_bar.simulation_selected or not self.backend.can_start:
            self._notify('Giá thử chưa sẵn sàng', 'Hãy kết nối giá thử và kiểm tra trạng thái sẵn sàng trước khi bắt đầu.')
            return
        self.backend.configure(serial_number=self.serial_edit.text())
        if not self.backend.start():
            self._notify('Chưa thể bắt đầu', self.backend.message)

    def _toggle_pause(self):
        if self.backend.paused:
            if not self.backend.resume():
                self._notify('Chưa thể tiếp tục', self.backend.message)
        else:
            self.backend.pause()

    def _manual_input_changed(self):
        request = self.backend.manual_request
        dialog = self._manual_dialog
        if dialog is not None and (request is None or request['token'] != dialog.token):
            self._manual_dialog = None
            dialog.withdraw()
        if request is not None and self._manual_dialog is None and not self._closing:
            dialog = ManualInputDialog(request, self)
            dialog.submitted.connect(self._manual_submitted)
            dialog.finished.connect(lambda _, d=dialog: setattr(self, '_manual_dialog', None)
                                    if self._manual_dialog is d else None)
            self._manual_dialog = dialog
            dialog.open()

    def _manual_submitted(self, token, values):
        request = self.backend.manual_request
        if request is None or request['token'] != token:
            return  # The run moved on (stop/pause/error); ignore the late answer.
        self._manual_dialog = None  # The dialog closes itself after sending.
        try:
            self.backend.submit_manual(values)
        except ValueError as error:
            self._notify('Giá trị nhập không hợp lệ', str(error))

    def _new_session(self):
        if not self.backend.new_session():
            self._notify('Chưa thể tạo phiên mới', self.backend.message)

    def _notify(self, title, text):
        key = (title, text)
        if key in self._messages:
            self._messages[key].raise_()
            return
        box = QMessageBox(QMessageBox.Warning, title, text, QMessageBox.Ok, self)
        box.setObjectName('workspaceMessage')
        box.setTextFormat(Qt.PlainText)
        box.setWindowModality(Qt.WindowModal)
        box.setAttribute(Qt.WA_DeleteOnClose)
        self._messages[key] = box
        box.finished.connect(lambda _: self._messages.pop(key, None))
        box.open()

    def _selected(self, item, previous):
        if item and item.data(0, Qt.UserRole):
            self.backend.select_test(item.data(0, Qt.UserRole))

    def _follow(self):
        if self.backend.test and self.backend.test['id'] in self.tree_items:
            item = self.tree_items[self.backend.test['id']]
            self.tree.setCurrentItem(item)
            self.tree.scrollToItem(item)

    def _filter_signals(self, *args):
        b = self.backend
        model = b.signal_model
        model.filter_group = self.group_combo.currentText()
        model.only_related = self.related_combo.currentIndex() != 0
        test = b.test if self.related_combo.currentIndex() == 1 else next((t for t in b.tests if t['id'] == b.selected_id), None)
        if self.related_combo.currentIndex() == 0:
            test = b.test if b.busy else None
        related = {c['signal'] for s in test['steps'] for c in s['checks'] + s['actions']} if test else set()
        model.refresh(b.samples, related)
        root = self.qml.rootObject()
        if root is not None:
            count = sum(s['id'] not in model.pinned
                        and (model.filter_group == 'Tất cả' or s['group'] == model.filter_group)
                        and (not model.only_related or s['id'] in related)
                        for s in b.profile.signals)
            if root.property('measurementCount') != count:
                root.setProperty('measurementCount', count)

    def refresh(self):
        b = self.backend
        mode_text = self.connection_bar.adapter.currentText()
        badge = 'MÔ PHỎNG' if self.connection_bar.simulation_selected else mode_text.upper()
        self.mode_badge.setText(badge)
        self.mode_badge.setToolTip(self.connection_bar.status.text())
        self.setWindowTitle(f"{APP_NAME} — {b.profile.system['name']} · {badge}")
        self.context_note.setText('DỮ LIỆU MÔ PHỎNG' if self.connection_bar.simulation_selected else f'{badge}\n{b.connection}')
        self.running_label.setText(b.message)
        self.progress.setValue(b.progress)
        self.progress.setFormat('%p% bài đã xử lý')
        statuses = [a['status'] for a in b.session['attempts']] if b.session else []
        self.counts.setText(f"{b.session['processed'] if b.session else 0}/{len(b.session['planned']) if b.session else 0}  ·  ✓ {statuses.count('PASS')}  ✕ {statuses.count('FAIL') + statuses.count('ERROR')}  ·  Chặn/bỏ {statuses.count('BLOCKED') + statuses.count('SKIPPED')}")
        self.start_button.setText(('Đang dừng…' if b.stopping else '■  Dừng kiểm tra') if b.busy else
                                 {Mode.SELF: '▶  Bắt đầu tự kiểm tra', Mode.MANUAL: '▶  Thực hiện bài', Mode.AUTO: '▶  Bắt đầu kiểm tra'}[b.mode])
        self.start_button.setToolTip('Kết thúc hẳn lượt kiểm tra; không tiếp tục lượt đã dừng.' if b.busy else 'Bắt đầu thực hiện kiểm tra.')
        state = 'running' if b.busy else 'idle'
        if self.start_button.property('state') != state:
            set_state(self.start_button, state)
        self.start_button.setEnabled(not b.stopping if b.busy else not b.closed and (b.session is None or b.mode == Mode.MANUAL))
        if b.paused:
            pause = ('▶  Tiếp tục', 'paused', True,
                     'Chạy lại bài đang dở từ đầu rồi tiếp tục các bài còn lại.')
        elif b.pause_requested:
            pause = ('Đang tạm dừng…', 'pausing', False, 'Đang đưa đầu ra về trạng thái an toàn.')
        else:
            pause = ('❚❚  Tạm dừng', 'idle', b.can_pause,
                     'Hoàn tất giao dịch đang dở và đưa đầu ra về trạng thái an toàn; '
                     'bài đang chạy sẽ chạy lại từ đầu khi tiếp tục.')
        self.pause_button.setText(pause[0])
        if self.pause_button.property('state') != pause[1]:
            set_state(self.pause_button, pause[1])
        self.pause_button.setEnabled(pause[2])
        self.pause_button.setToolTip(pause[3])
        banner = 'paused' if b.paused or b.pause_requested else 'running' if b.busy else 'idle'
        if self.running_label.property('state') != banner:
            set_state(self.running_label, banner)
        self.new_button.setEnabled(not b.busy and not b.store.busy)
        self.mode_combo.setEnabled(not b.busy and b.session is None)
        self.serial_edit.setEnabled(not b.busy and b.session is None and b.mode != Mode.SELF)
        self.target_combo.setEnabled(not b.busy and b.session is None and b.mode != Mode.SELF)
        self.bench_combo.setEnabled(not b.busy and b.session is None)
        self.scenario_combo.setEnabled(not b.busy)
        self.speed_combo.setEnabled(not b.busy and b.session is None)
        self.mode_combo.blockSignals(True)
        self.mode_combo.setCurrentText(b.mode.value)
        self.mode_combo.blockSignals(False)
        self.save_label.setText(b.store.status)
        errors = (b.connection if b.connection.startswith('Lỗi') else '',
                  b.store.status if b.store.status.startswith('Lỗi lưu') else '')
        for title, error, previous in zip(('Lỗi kết nối', 'Không lưu được kết quả'), errors, self._error_state):
            if error and error != previous:
                self._notify(title, error + '\n' + b.message)
        self._error_state = errors
        self.verdict.setText('Tạm dừng' if b.paused else b.session['verdict'] if b.session else 'Chưa có phiên')
        set_state(self.verdict, 'success' if self.verdict.text() == 'PASS' else 'error' if self.verdict.text() in ('FAIL', 'ERROR') else 'warning')
        if self._tree_mode != b.mode:
            self._tree_mode = b.mode
            self.tree.blockSignals(True)
            self.tree.clear()
            self.tree_items = {}
            groups = {}
            for test in b.tests:
                if test['group'] not in groups:
                    groups[test['group']] = QTreeWidgetItem(self.tree, [test['group']])
                item = QTreeWidgetItem(groups[test['group']], [test['id'] + ' · ' + test['name'], 'Chưa chạy'])
                item.setData(0, Qt.UserRole, test['id'])
                item.setToolTip(0, test['name'])
                self.tree_items[test['id']] = item
            self.tree.expandAll()
            if b.selected_id not in self.tree_items:
                b.selected_id = b.tests[0]['id']
            self.tree.setCurrentItem(self.tree_items[b.selected_id])
            self.tree.blockSignals(False)
        latest = {a['test_id']: a['status'] for a in b.session['attempts']} if b.session else {}
        if b.selected_id in self.tree_items and self.tree.currentItem() is not self.tree_items[b.selected_id]:
            self.tree.blockSignals(True)
            self.tree.setCurrentItem(self.tree_items[b.selected_id])
            self.tree.blockSignals(False)
        for test in b.tests:
            item = self.tree_items[test['id']]
            status = latest.get(test['id'], 'Chưa đủ đặc tả' if specification_issues(test) else 'Chưa chạy')
            status = STATUS_TEXT.get(status, status)
            item.setText(1, status)
            item.setForeground(1, QColor('#42eea3' if status == 'PASS' else '#ff8995' if status in ('FAIL', 'ERROR') else '#e7bd71'))
            font = item.font(0)
            font.setBold(b.busy and b.test is not None and test['id'] == b.test['id'])
            item.setFont(0, font)
        test = next((t for t in b.tests if t['id'] == b.selected_id), None)
        if test:
            html = f"<b>{escape(test['source'])} · {escape(test['name'])}</b><br>" + '<br>'.join(escape(s['id'] + ' · ' + s['title']) for s in test['steps'])
            if specification_issues(test):
                html += '<p style="color:#ffcb80">' + escape('; '.join(specification_issues(test))) + '</p>'
            if html != self._details_html:
                self.details.setHtml(html)
                self._details_html = html
        self._filter_signals()
        self._render_results()
        if b.recovered:
            self.notice.setText(f'Phát hiện {len(b.recovered)} phiên gián đoạn; không tự tiếp tục. Kết quả hiện tại là MÔ PHỎNG.')

    def _render_results(self):
        b = self.backend
        attempts = [a for a in b.session['attempts'] if a['test_id'] == b.selected_id] if b.session else []
        signature = repr(attempts)
        if signature == self._table_signature:
            return
        self._table_signature = signature
        rows = []
        for i, attempt in enumerate(attempts, 1):
            rows.append([f"Lần {i} · {attempt['test_id']}", '—', '—', STATUS_TEXT.get(attempt['status'], attempt['status']),attempt['reason'] or ('Đã xác nhận kết thúc' if attempt['cleanup_confirmed'] else 'Chưa xác nhận kết thúc')])
            for m in attempt['measurements']:
                limit = 'Chưa chốt' if m['nominal'] is None or m['tolerance'] is None else f"{m['nominal']:g} ± {m['tolerance']:g} {m['unit']}"
                rows.append([f"{i}/{m['step_id']} · {b.definitions[m['signal']]['label']}", f"{m['value']:g} {m['unit']}" if m['value'] is not None else '—', limit, m['status'], m['reason']])
        self.result_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, value in enumerate(row):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if c == 3:
                    item.setForeground(QColor('#39ec9a' if value == 'PASS' else '#ffb875'))
                self.result_table.setItem(r, c, item)

    def _qml_status(self, status):
        if status == QQuickWidget.Error:
            self.notice.setText('Không nạp được QML: ' + '; '.join(e.toString() for e in self.qml.errors()))

    def closeEvent(self, event):
        self.pages.finish_transition()
        if self.backend.closed or not self.backend.busy:
            if not self.backend.closed:
                self.backend.shutdown()
            if not self.backend.closed:
                self._closing = True
                event.ignore()
                return
            self.clock.stop()
            self.closed.emit()
            event.accept()
        else:
            event.ignore()
            self._closing = True
            self.backend.shutdown()

    def _shutdown_ready(self):
        if self._closing:
            QTimer.singleShot(0, self, self.close)  # Context: dropped if the window is gone.
