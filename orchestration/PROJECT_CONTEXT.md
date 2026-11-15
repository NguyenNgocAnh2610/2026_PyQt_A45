# Hiện trạng và quyết định dự án

Nguồn kiểm chứng: code trong workspace và AGENTS.md; tài liệu này được cập
nhật khi có thay đổi thực tế, không phải danh sách tính năng đã cam kết làm.

## Đã triển khai

| Thành phần | File và vai trò |
|---|---|
| Khởi chạy | `main.py`: QApplication, theme, Login → MainWindow; xác thực demo |
| Cấu hình | `src/common/config.py`: tên ứng dụng, phiên bản, mã giá thử, namespace QSettings, assets |
| Style loader | `src/common/styles.py`: common/page QSS, `styleScale`, `@ASSETS@`, trạng thái widget |
| Login | `src/ui/widgets/login_page.py`: nền ảnh, điều khiển thật, xác thực qua callback nhanh, `login_success(str)` |
| Hộp thoại Login | `InformationDialog` cùng file Login, dùng cuối `login.qss`; không tách module/preview riêng |
| Cửa sổ chính | `src/ui/main_window.py`: shell mẫu, chưa có điều hướng/phép đo |
| Theme | `assets/styles/common.qss`; Login ghi đè có phạm vi ở `assets/styles/login.qss` |
| Gallery | `tests/preview_widgets.py`, `tests/widget_samples.py`: tìm mẫu, quét QSS, reload, liên kết UI qua `PAGE_PREVIEWS` |
| Preview/test | `tests/preview_login.py`, `tests/preview_main.py`, `tests/test_login.py`, `tests/test_preview_widgets.py` |

Hiện chưa có `backend.py`, `device.py`, `communication.py`, `protocol.py`, QML
hoặc file Qt Designer `.ui`. Chỉ tạo chúng khi tính năng cụ thể cần đến.
Giao diện hiện tại được viết bằng Python/Qt Widgets.

## Các quyết định cần giữ

- Login dùng ảnh nguyên `assets/images/login.png`, tọa độ gốc 1672 × 941,
  cửa sổ cố định mục tiêu rộng 1280 và tự chọn nhỏ hơn khi khởi tạo để vừa màn
  hình. Widget và QSS riêng cùng tỷ lệ; hộp thoại trợ giúp có cỡ chữ độc lập.
- `LoginBrandText` chỉ gom nội dung có thể đổi theo từng giá thử. Các nhãn
  phổ thông như tên đăng nhập/mật khẩu/tooltip để trực tiếp tại nơi dùng.
  Nội dung cấu hình dùng trên nhiều UI thuộc `src/common/`.
- Thành phần phụ riêng một trang giữ cùng trang và QSS tương ứng. Không tách
  nhiều file chỉ vì có thể tái sử dụng trong tương lai.
- Mỗi trang mới có `create_preview()` trả về widget với dữ liệu/backend giả,
  không tạo QApplication/event loop/hardware. `main()` trong file preview ở
  `tests/` tạo QApplication, nạp theme và hiển thị; gallery gọi cùng factory.
- QSS mới tự được quét; UI thật cần đăng ký factory rõ ràng. Không tự import
  mọi module Python để tìm UI. `src/` không import ngược `tests/`.
- Xác thực hiện là demo; callback đồng bộ chỉ phù hợp xử lý nhanh. Xác thực
  từ xa cần API bất đồng bộ khi thực sự triển khai. Không gọi dịch vụ chậm
  hoặc đọc thiết bị trong `_try_login()`.
- Ghi nhớ chỉ lưu tên đăng nhập qua QSettings sau thành công; preview/test
  không ghi cấu hình người dùng. Thay tên/namespace lưu trữ là thay đổi có
  ảnh hưởng dữ liệu cấu hình, cần đánh giá riêng.

## Kiến trúc phần cứng khi triển khai

UI gửi yêu cầu qua API QObject/Signal/Slot của backend. Backend quản lý trạng
thái xác nhận/đang chờ/chưa biết/hết hạn và thông báo UI. Device diễn đạt thao
tác nghiệp vụ, protocol định nghĩa khung/register, communication sở hữu I/O
và timeout. Một thành phần sở hữu serial, giao dịch tuần tự; không chờ trên
GUI thread. Mất kết nối phải làm dữ liệu cũ trở thành không hiện thời.

Chưa xác định giao thức chi tiết, register, baudrate, thiết bị và tiêu chí
đạt/không đạt. Không suy ra các thông số đó từ ảnh UI hay dữ liệu mô phỏng.

## Điểm cần biết khi nhận task mới

Workspace đang có thay đổi chưa commit và tài nguyên chưa track từ giai đoạn
thiết kế Login/gallery; giữ nguyên và kiểm tra lại mỗi lần giao việc.
Lần kiểm tra thiết lập điều phối thấy `APP_NAME = "GIÁ THỬ"`, mã giá thử `A45`
và `SETTINGS_ORGANIZATION = "A54"`; đây là giá trị hiện tại do người dùng đang
chỉnh. Không tự sửa chúng hoặc đồng bộ README khi chưa được giao task liên quan.

Hiện chưa có yêu cầu tính năng đầu tiên sau khi thiết lập điều phối. Không
tự chọn thêm trang đo kiểm, authentication production hay tầng phần cứng.
