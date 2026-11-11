# AGENTS.md — 2026_PyQt_A45

## Mục tiêu
Phát triển phần mềm giá thử A45 bằng **Python + PySide6**, kết hợp **Qt Widgets** (cửa sổ, biểu mẫu, bảng, đồ thị) và **QML/Qt Quick** (dashboard, LED, nút điều khiển, HMI). Phần mềm trao đổi lệnh và dữ liệu với phần cứng qua **UART/Modbus**.

## Cấu trúc định hướng
Cấu trúc dưới đây gồm phần đã triển khai và định hướng mở rộng. Hiện chạy bằng `main.py`, Login nằm tại `src/ui/widgets/login_page.py`, preview trong `tests/`. Chưa tạo các module backend/phần cứng và QML; chỉ bổ sung khi có tính năng, không tạo module rỗng.

```text
2026_PyQt_A45/
├── main.py                 # Điểm khởi chạy: Login → MainWindow
├── requirements.txt
├── README.md
├── AGENTS.md
├── assets/
│   ├── styles/
│   │   ├── common.qss      # Style chung toàn ứng dụng Qt Widgets
│   │   └── <page>.qss      # Style riêng từng trang, ví dụ login.qss
│   └── images/             # Logo, ảnh, biểu tượng
├── src/
│   ├── __init__.py
│   ├── common/             # Hằng số, enum, cấu hình, kiểu dữ liệu và tiện ích dùng chung
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py   # Cửa sổ chính, sidebar, điều hướng
│   │   ├── qml/            # Màn hình và component HMI bằng QML
│   │   └── widgets/        # Các trang/widget Qt Widgets, gồm Login và trang đo kiểm
│   ├── backend.py          # QObject, Signal/Slot, trạng thái và điều phối yêu cầu UI
│   ├── device.py           # API nghiệp vụ điều khiển/đọc trạng thái phần cứng A45
│   ├── communication.py    # Kết nối và truyền nhận UART/Modbus, worker bất đồng bộ
│   └── protocol.py         # Khung lệnh, mã lệnh, ánh xạ register, encode/decode
└── tests/                  # Unit/integration test, mock thiết bị, chạy thử UI độc lập
```

## Quy tắc phát triển
1. **Giữ cấu trúc gọn**: chỉ thêm file/thư mục khi có nhu cầu thực; không tạo nhiều lớp trung gian không cần thiết.
2. **Tách UI và phần cứng**: UI xử lý hiển thị, tương tác, điều hướng và kiểm tra dữ liệu nhập cục bộ; yêu cầu nghiệp vụ/phần cứng đi qua API backend. Không đọc/ghi UART/Modbus trực tiếp trong QML/Widgets.
3. **Một nguồn trạng thái**: `backend.py` quản lý trạng thái thiết bị, thông báo bằng `Signal`/`Property`. Phân biệt trạng thái đã xác nhận, yêu cầu đang chờ và dữ liệu chưa biết/hết hạn. Không coi gửi lệnh thành công là thiết bị đã đổi trạng thái; khi mất kết nối, không hiển thị dữ liệu cũ như trạng thái hiện thời.
4. **Phân định trách nhiệm**: `device.py` diễn đạt thao tác nghiệp vụ; `protocol.py` định nghĩa giao thức; `communication.py` thực hiện I/O và timeout. Không lặp logic giữa các tầng.
5. **Không chặn GUI thread**: truyền nhận, chờ phản hồi, polling và các phép xử lý nặng phải bất đồng bộ hoặc chạy trong worker; cập nhật widget trên main thread.
6. **Định nghĩa chung đặt tại `src/common/`**: tên ứng dụng, cấu hình mặc định, enum trạng thái, kiểu dữ liệu và tiện ích dùng xuyên module. Tránh import vòng và giá trị hard-code rải rác.
7. **Kiểm thử từng phần**: UI có thể preview với backend giả; protocol và truyền thông phải test được không cần phần cứng. Bổ sung test khi thêm tính năng hoặc sửa lỗi.
8. **An toàn giao tiếp**: một thành phần sở hữu cổng serial và tuần tự hóa giao dịch; quản lý timeout, lỗi/gián đoạn và kiểm tra phản hồi. Không tự động retry lệnh tác động phần cứng nếu chưa xác định an toàn. Khi đóng ứng dụng, dừng polling, kết thúc worker và đóng kết nối có kiểm soát; không chờ vô hạn trên GUI thread.
9. **Mở rộng theo tính năng**: chỉ tách `backend.py`, `device.py` hoặc `communication.py` thành package khi chúng quá lớn hoặc xuất hiện nhiều thiết bị/giao thức độc lập; giữ ổn định API mà UI đang dùng.

## Môi trường và chạy thử
- **Luôn chạy Python trong môi trường Conda `qt_env` đã có**, gồm ứng dụng, preview, test và công cụ Python. Kích hoạt bằng `conda activate qt_env`; không tự tạo lại môi trường hoặc dùng Python hệ thống/base.
- Chạy từ thư mục gốc:
  ```powershell
  conda activate qt_env
  python main.py
  ```
- Nếu shell không hỗ trợ activate, dùng `conda run -n qt_env python <script.py>`; nếu vẫn lỗi, báo rõ thay vì đổi môi trường. Khi cần cài dependency, dùng `python -m pip` trong `qt_env`.
- Preview bằng `python -m tests.preview_login` và `python -m tests.preview_widgets`; chạy test tự động bằng `python -m unittest discover -s tests -v`. Kiểm tra trường trống, đăng nhập sai/đúng, hiện mật khẩu, bàn phím và resize. Test hiện dùng `unittest` và `PySide6.QtTest`, chưa đặt ngưỡng coverage. Test tự động dùng tên `test_*.py`, mock thiết bị và kiểm tra cả timeout/mất kết nối.

## Style và quy ước code
- Dùng UTF-8, thụt lề Python 4 dấu cách, `snake_case` cho hàm/biến và `PascalCase` cho lớp. Giữ tiếng Việt hiển thị đúng; chưa có formatter/linter được cấu hình.
- `assets/styles/common.qss` là nền style chung toàn project cho Qt Widgets: font, màu nền/chữ, input, button, bảng và các trạng thái dùng chung. Đã được nạp qua `src/common/styles.py`; `login.qss` chỉ chứa phần riêng của Login.
- Nạp `common.qss` ở cấp `QApplication` trước; QSS riêng từng trang chỉ bổ sung/ghi đè phần đặc thù, không sao chép lại toàn bộ style chung. Preview độc lập cũng phải nạp cùng nền style. QSS không có cơ chế kế thừa/import như CSS web; dựa vào cascade của Qt và phạm vi áp dụng.
- Giới hạn selector riêng bằng `objectName` hoặc dynamic property để tránh ảnh hưởng trang khác. Hạn chế `setStyleSheet()` rải rác trong Python; ưu tiên property cho trạng thái và giữ quy tắc hiển thị trong QSS.
- QSS chỉ áp dụng cho Qt Widgets; QML cần theme/component riêng, giữ nhất quán với bảng màu và kích thước chung khi tích hợp.
- Không đưa mật khẩu thật vào code/log; thông tin đăng nhập demo chỉ dùng để preview.

## Commit và pull request
- Lịch sử dùng tiêu đề ngắn tiếng Việt hoặc tiếng Anh, chưa có chuẩn bắt buộc. Viết rõ hành vi thay đổi, ví dụ `Sửa nút hiện mật khẩu`; giữ mỗi commit tập trung.
- PR nêu thay đổi, cách kiểm tra, giới hạn chưa kiểm chứng và issue liên quan nếu có; thêm ảnh chụp khi thay đổi giao diện.

## Quy trình khi AI chỉnh sửa code
- Đọc các file liên quan trước khi sửa; ưu tiên thay đổi nhỏ, tương thích cấu trúc hiện có.
- Với UI mới: thiết kế trang/component → preview độc lập → nối backend → tích hợp menu.
- Với lệnh phần cứng mới: định nghĩa giao thức/địa chỉ → triển khai device và communication → test với mock → nối backend/UI → kiểm tra với thiết bị thật.
- Chỉ kiểm tra với thiết bị thật khi có thiết bị và được phép thao tác; nếu chưa thực hiện, ghi rõ giới hạn, không khẳng định đã xác minh.
- Không tự ý đổi giao thức, địa chỉ thanh ghi, baudrate hoặc giả định trạng thái thiết bị; những thông số chưa có phải để cấu hình/TODO rõ ràng.
- Sau thay đổi, nêu file đã sửa, cách chạy thử và giới hạn chưa kiểm chứng.

