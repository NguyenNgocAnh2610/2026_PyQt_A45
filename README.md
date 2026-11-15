# Hybrid Testbench — A45

Ứng dụng Python + PySide6 cho giá thử A45. Hiện có trang đăng nhập và cửa sổ chính mẫu; chưa tích hợp UART/Modbus hoặc xác thực production.

Quy trình Codex điều phối Antigravity, hiện trạng và tiến độ nằm trong
[orchestration/](orchestration/README.md); quy tắc kỹ thuật nằm tại [AGENTS.md](AGENTS.md).

## Chạy ứng dụng

Chạy từ thư mục gốc, luôn dùng môi trường đã tạo:

```powershell
conda activate qt_env
python -m pip install -r requirements.txt
python main.py
```

Đăng nhập demo: `admin` / `123456`. Không sử dụng thông tin demo trong production.
Khi chạy `main.py`, “Ghi nhớ đăng nhập” lưu **tên đăng nhập** sau khi xác thực
thành công bằng QSettings (`A45` / `Hybrid Testbench`), không lưu mật khẩu.
Bỏ chọn sẽ xóa tên đã lưu. Preview độc lập và gallery không ghi cấu hình người dùng.

## Preview và kiểm thử

```powershell
python -m tests.preview_login
python -m tests.preview_widgets
python -m tests.preview_main
python -m unittest discover -s tests -v
```

Nếu không activate được trong shell, dùng `conda run -n qt_env python ...`.

## Giao diện đăng nhập

Login dùng nguyên ảnh `assets/images/login.png` làm nền, các nhãn và điều khiển
Qt thật phủ đúng vị trí trên ảnh. Cửa sổ cố định khoảng 1280 × 720; khi khởi tạo
sẽ thu nhỏ theo vùng màn hình khả dụng (Qt logical pixels), chừa chỗ cho khung
cửa sổ. Không kéo giãn/phóng to cửa sổ Login. Trong gallery, dùng thanh cuộn
nếu vùng preview nhỏ hơn trang.

`login_page.py` đặt tọa độ theo ảnh gốc 1672 × 941. `login.qss` giữ màu sắc,
font và các trạng thái hover/focus/pressed; giá trị `px` của QSS riêng được
`prepare_page_style()` đổi theo property `styleScale`, cả ở ứng dụng và gallery.
`common.qss` vẫn là theme nền và không bị đổi kích thước theo Login.
Đổi ảnh nền sang bố cục khác cần cập nhật tọa độ điều khiển tương ứng.

“Quên mật khẩu?” và “Hỗ trợ” mở hướng dẫn tại chỗ; chưa có dịch vụ đặt lại mật
khẩu hoặc địa chỉ liên hệ cấu hình. Xác thực hiện vẫn là demo.

Hai hộp thoại trợ giúp dùng lớp `InformationDialog` nhỏ ngay trong
`login_page.py`; style cũng nằm cuối `login.qss`. Hộp thoại có icon, nội dung,
vùng lưu ý và nút “Đã hiểu”, mở bất đồng bộ và đóng bằng Enter/Esc. Đây là
thành phần riêng của Login nên không tạo thêm module UI/QSS/preview độc lập.

### Quản lý nhãn và nội dung

| Phạm vi | Nơi chỉnh |
|---|---|
| Tên ứng dụng, phiên bản và mã giá thử dùng toàn hệ thống | `src/common/config.py`: `APP_NAME`, `APP_VERSION`, `TESTBENCH_MODEL` |
| Tiêu đề/miêu tả có thể đổi khi dùng giao diện cho giá thử khác | `LoginBrandText` ở đầu `src/ui/widgets/login_page.py` |

Các nhãn phổ thông như “Tên đăng nhập”, “Mật khẩu”, placeholder, tooltip và
thông báo xác thực được viết trực tiếp tại widget/logic sử dụng. Chỉ tách hằng
số khi nội dung cần cấu hình theo giá thử hoặc được dùng thực sự trên nhiều UI.
Không thay `APP_NAME`/`SETTINGS_ORGANIZATION` chỉ để đổi nhãn quảng bá, vì chúng
cũng định danh nơi lưu QSettings hiện tại.

Chụp một kích thước cụ thể, độc lập với màn hình hiện tại:

```powershell
python -m tests.preview_login --width 1280 --capture captures/login.png
python -m tests.preview_login --width 960 --capture captures/login_compact.png
```

## Từ điển giao diện

`python -m tests.preview_widgets` mở gallery với danh mục tìm kiếm bên trái,
preview tương tác, nội dung QSS và ví dụ cách dùng bên phải. Có thể tìm bằng
tiếng Việt có/không dấu hoặc tên lớp Qt như `QPushButton`.

- Nhóm widget dùng chung minh họa nút, input, lựa chọn, bảng/cây/danh sách,
  tab, progress/slider và nhãn trạng thái/card. Các mẫu ở `tests/widget_samples.py`.
- Nhóm trang dùng đúng `LoginPage` và `MainWindow`, với dữ liệu demo.
- Gallery tự quét `assets/styles/` và thư mục con, cập nhật khi thêm/sửa/đổi tên/xóa
  QSS (kể cả cách lưu bằng thay thế file của editor). Có nút **Quét lại**.
- `common.qss` áp dụng ở cấp ứng dụng. QSS trang chỉ áp dụng trong preview đó.
  Khi tải lại QSS của trang đang xem, giữ nguyên widget và dữ liệu đang nhập.
- QSS chưa liên kết UI vẫn có mục riêng và bộ widget mẫu. Selector theo
  `objectName`/property riêng chỉ thể hiện chính xác khi có UI tương ứng.
- Thay đổi Python hoặc bảng đăng ký cần khởi động lại gallery. QSS không hợp lệ
  về cú pháp được Qt báo trong terminal; gallery không có trình kiểm tra cú pháp QSS.

Preview nằm trong vùng cuộn để giữ kích thước tối thiểu của trang. Để kiểm tra
resize, focus và đóng/mở ở cửa sổ thật, chạy preview độc lập.
Lệnh `python -m tests.preview_widgets --capture captures` vẫn xuất
`widgets.png`, `login.png`, `login_minimum.png` (bản cố định rộng 960) và `main.png`.

### Thêm một trang vào gallery

Mỗi trang có một file `tests/preview_<trang>.py` theo mẫu `tests/preview_login.py`:

```python
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
from src.common.config import ASSETS_DIR
from src.common.styles import apply_theme
# Import lớp UI thật và backend giả của trang tại đây.


def create_preview(assets_dir: Path = ASSETS_DIR):
    # Trả về widget mới, truyền dữ liệu/backend giả và assets_dir nếu cần.
    # Ví dụ với trang đã có:
    from tests.preview_login import create_preview as create_login
    return create_login(assets_dir)


def main() -> int:
    app = QApplication(sys.argv)
    apply_theme(app)
    page = create_preview()
    page.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
```

Import factory và thêm một `PagePreview` vào `PAGE_PREVIEWS` trong
`tests/preview_widgets.py`. Ví dụ khai báo Login hiện có:

```python
PagePreview(
    title="Login",
    stylesheet="login.qss",  # Đường dẫn tương đối trong assets/styles/
    factory=create_login_preview,
    source="src/ui/widgets/login_page.py",
    usage="python -m tests.preview_login",
)
```

Dùng `stylesheet=None` nếu trang chỉ dùng theme chung. Với file Qt Designer
`.ui` sau này, factory tạo lớp UI đã được load/setup từ file đó rồi trả về widget;
gallery vẫn dùng cùng giao diện factory, không tự import hay thực thi file mới.

`create_preview()` không tạo `QApplication`, không chạy event loop, không gọi
`show()` và không mở phần cứng. `main()` chỉ phục vụ chạy độc lập. UI ứng dụng
trong `src/` không import từ `tests/`. Preview có timer/worker phải tự dừng chúng
trong `closeEvent`, vì gallery đóng và giải phóng preview khi chuyển mục.

## Tổ chức code

- `main.py`: luồng Login → MainWindow.
- `src/ui/widgets/login_page.py`: widget đăng nhập, nhận callback xác thực nhanh, không chặn GUI. Xác thực từ xa sau này cần API bất đồng bộ.
- `src/ui/main_window.py`: cửa sổ chính mẫu.
- `src/common/`: cấu hình, đường dẫn tài nguyên và tiện ích style.
- `assets/styles/common.qss`: theme chung Qt Widgets; `login.qss`: tùy chỉnh riêng trang Login.
- `assets/images/`: ảnh nền `login.png` cần thiết cho Login và các icon SVG.
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
