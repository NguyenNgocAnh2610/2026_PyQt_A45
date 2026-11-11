# Hybrid Testbench — A45

Ứng dụng Python + PySide6 cho giá thử A45. Hiện có trang đăng nhập và cửa sổ chính mẫu; chưa tích hợp UART/Modbus hoặc xác thực production.

## Chạy ứng dụng

Chạy từ thư mục gốc, luôn dùng môi trường đã tạo:

```powershell
conda activate qt_env
python -m pip install -r requirements.txt
python main.py
```

Đăng nhập demo: `admin` / `123456`. Không sử dụng thông tin demo trong production. Checkbox ghi nhớ hiện chỉ là giao diện, chưa lưu tài khoản.

## Preview và kiểm thử

```powershell
python -m tests.preview_login
python -m tests.preview_widgets
python -m unittest discover -s tests -v
```

Nếu không activate được trong shell, dùng `conda run -n qt_env python ...`.

## Tổ chức code

- `main.py`: luồng Login → MainWindow.
- `src/ui/widgets/login_page.py`: widget đăng nhập, nhận callback xác thực nhanh, không chặn GUI. Xác thực từ xa sau này cần API bất đồng bộ.
- `src/ui/main_window.py`: cửa sổ chính mẫu.
- `src/common/`: cấu hình, đường dẫn tài nguyên và tiện ích style.
- `assets/styles/common.qss`: theme chung Qt Widgets; `login.qss`: tùy chỉnh riêng trang Login.
- `assets/images/`: logo/ảnh tùy chọn; Login vẫn chạy khi chưa có ảnh.
- `tests/`: test tự động và preview độc lập.

Chưa tạo module phần cứng và QML rỗng; bổ sung khi triển khai tính năng.

## Dùng theme

Gọi `apply_theme(app)` từ `src.common.styles` sau khi tạo `QApplication`; trang dùng `apply_page_style(widget, "login")`. Theme chung được nạp ở cấp ứng dụng, QSS trang ở cấp widget; không import QSS trong QSS.

Đường dẫn icon `@ASSETS@` trong QSS chung được loader đổi thành đường dẫn tuyệt đối, nên tài nguyên không phụ thuộc thư mục chạy.

- Nút: `setProperty("variant", "primary")`, `"danger"` hoặc `"text"`.
- Nhãn: `setProperty("role", "title")` hoặc `"muted"`.
- Card: `QFrame` với `setProperty("role", "card")`.
- Trạng thái đổi lúc chạy: `set_state(label, "success")`, `"warning"`, `"error"`.

Theme gồm input, combobox, spinbox, checkbox/radio, bảng/cây/danh sách, tab, progress, slider, scrollbar và menu. QML sẽ dùng theme riêng khi được tích hợp.
