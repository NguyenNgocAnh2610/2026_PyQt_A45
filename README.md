# Hybrid Testbench — A45

Phần mềm giao diện và điều hành giá thử bằng Python + PySide6 (Qt Widgets + QML),
dùng chung cho nhiều giá thử thông qua **profile JSON**. Cấu hình đầu tiên là
**A45 / khối 1101K-10** (24 tham số). PC là Modbus RTU Master điều khiển một
STM32 **CPUv1.1** (Slave 11); CPU điều khiển tiếp các bo matrix rơ-le, MUX và rơ-le nguồn.
Bộ chạy bài chạy trên COM ảo (STM32 giả lập, khung Modbus RTU thật) và trên COM thật có
kiểm soát (tự kiểm tra ngay; bài đo khi ánh xạ đã đo kiểm). Có trang **Test Modbus** để
kiểm từng rơ-le/kênh.

## Tài liệu

| Tài liệu | Nội dung |
|---|---|
| [AGENTS.md](AGENTS.md) | Quy tắc phát triển bắt buộc (kiến trúc, an toàn giao tiếp, backup, quy trình) |
| [PROGRESS.md](PROGRESS.md) | Hiện trạng, việc tiếp theo, vấn đề mở — nhật ký duy nhất |
| [docs/README.md](docs/README.md) | **Mục lục tài liệu kỹ thuật** (01–07, tài liệu nguồn, báo cáo) và thứ tự đọc theo vai trò |

Nguyên tắc: mỗi nội dung chỉ nằm ở **một** tài liệu, các tài liệu khác liên kết tới.

## Cài đặt và chạy

Luôn dùng Conda env `qt_env`:

```powershell
conda activate qt_env
python -m pip install -r requirements.txt
python main.py                                        # profile mặc định A45
python main.py --profile configs/a45/system.json      # chọn profile
```

Nếu shell không activate được, dùng `conda run -n qt_env python ...`.

Đăng nhập demo: `admin` / `123456` (chỉ để demo). "Ghi nhớ đăng nhập" chỉ lưu
**tên đăng nhập** bằng QSettings (namespace `A54` / `GIÁ THỬ` trong
`src/common/config.py`). Giữ namespace ổn định khi đổi tên giá thử.

## Sử dụng

### Kết nối
- **Mô phỏng** → Kết nối: mở **COM ảo** tới STM32 giả lập, chỉ đọc FC03 để xác nhận, không ghi.
  Mọi giao dịch đi qua đúng đường code của COM thật, với khung Modbus RTU, CRC, timeout và độ trễ
  vòng lặp MCU. Khi có lỗi (timeout, mất cáp), COM ảo tự đóng như cổng thật, nên phải Kết nối lại.
- **Modbus RTU** → chọn COM, baudrate → Kết nối: mở COM thật, phần mềm tự đọc một FC03 tới
  CPU (slave theo profile, A45 = 11). Có trả lời → **"Sẵn sàng · COM THẬT"**; không trả lời →
  "Không có phản hồi STM32 (slave N)" kèm gợi ý (công tắc ID trên bo CPU, dây A/B, baud).
  **UART** chỉ mở cổng serial thuần. Hướng dẫn: [05 Vận hành mục 1](docs/05_VAN_HANH_GIAO_DIEN.md#1-kết-nối-và-bảng-hai-mảng-thanh-ghi).
- "Đã mở COM" chỉ là đã mở cổng, chưa xác nhận slave trả lời.

### Chạy trên mạch thật
- **Tự kiểm tra giá thử** (D01 truyền thông, D02 chu kỳ vòng lặp CPU): chạy được ngay khi
  "Sẵn sàng · COM THẬT", sau hộp thoại xác nhận; chỉ ghi trạng thái an toàn (mọi rơ-le nhả).
- **Bài đo** chỉ chạy khi mọi ánh xạ bài dùng đã `verified` trong `hardware.json`, D02 đạt
  trên kết nối đó, và người vận hành xác nhận. Thiếu điều kiện nào thì hộp thoại liệt kê rõ.
  Thời gian chờ trên mạch thật không bị chia hệ số mô phỏng. Chi tiết: [05 Vận hành mục 3](docs/05_VAN_HANH_GIAO_DIEN.md).

### Test Modbus
Mục **⇄ Test Modbus** trên thanh bên: lấy quyền điều khiển CPU (Mode=1), bật/tắt từng rơ-le
nguồn, nối chân qua lưới matrix 8×4 của từng bo, chọn kênh MUX rồi đọc ADC, đặt DAC/DOUT,
nút **Về an toàn**, bảng thanh ghi thô (tự đọc định kỳ) và nhật ký khung TX/RX xuất ra file.
Dùng chung luật an toàn với bộ chạy bài (liên động, ngắt trước đóng sau, chặn kênh MUX ≥ 32).
Thử trước trên COM ảo. Chi tiết: [05 Vận hành mục 2](docs/05_VAN_HANH_GIAO_DIEN.md).

### Chạy bài
1. Nhập serial khối (không cần với tự kiểm tra), chọn chế độ: **Tự kiểm tra giá thử**,
   **Kiểm tra bằng tay** (bài đang chọn) hoặc **Kiểm tra tự động** (toàn bộ bài).
2. **Bắt đầu kiểm tra**. Mỗi bài: ghi lệnh xuống STM32 → chờ ổn định → đọc số đo →
   so dải cho phép → về trạng thái an toàn.
3. Nút Bắt đầu chuyển thành **Dừng** (màu đỏ) khi đang chạy; dừng kết thúc lượt
   kiểm tra và đưa về trạng thái an toàn.
4. **Tạm dừng** (màu vàng):
   - Giao dịch đang dở được hoàn tất, rồi đầu ra về trạng thái an toàn. Bài đang chạy được ghi "Tạm dừng", không tính vào kết quả.
   - Bấm **Tiếp tục** (màu xanh): bài đó chạy lại từ đầu, sau đó chạy tiếp các bài còn lại.
   - Nếu bấm giữa hai bài thì dừng ngay. Nếu bài đang ở bước kết thúc thì bài được làm xong rồi mới dừng.
   - Khi đang tạm dừng, bấm Dừng hoặc Ngắt kết nối sẽ kết thúc lượt (ABORTED).

Kết quả: PASS, FAIL, ERROR (lỗi giao tiếp/mẫu), BLOCKED (thiếu đặc tả hoặc phần
cứng chưa đáp ứng), SKIPPED (bài phụ thuộc chưa PASS), ABORTED, Tạm dừng (lần
chạy bị tạm dừng, đã chạy lại). Profile A45 hiện
cho **24/24 PASS mô phỏng** với ánh xạ phần cứng giả định
(chi tiết: [06_CAU_HINH_PROFILE.md](docs/06_CAU_HINH_PROFILE.md#hiện-trạng-profile-a45--khối-1101k-10)).

**Nhập tay**: số đo bằng thiết bị ngoài (ví dụ tần số 3 pha ở P01, đo bằng oxilo)
hiện hộp thoại khi tới bước đó; đầu ra vẫn giữ nguyên trong lúc đo. Để trống hoặc
bấm "Bỏ qua" thì ghi giá trị chuẩn, kết quả ghi rõ "mặc định, chưa đo". P01/P02
(nguồn) FAIL thì dừng cả lượt.

### Màn hình
- Vùng trạng thái/số đo dựng từ danh mục tín hiệu, lọc theo nhóm/bài. Lọc hay chọn
  bài để xem không đổi bài đang chạy; **Theo dõi bài chạy** để quay lại.
- Mỗi ô **giữ giá trị gần nhất** sau khi bài xong (mô phỏng và thật), kèm chip kết
  quả và "bài/bước · giờ".
  - Số đo: PASS / FAIL / Chưa đánh giá.
  - Giá trị yêu cầu: chip **ACK**, nghĩa là MCU đã nhận lệnh, chưa xác nhận đầu ra.
  - Giá trị trực tiếp hiện màu xanh lam với nhãn "Hiện thời"; giá trị đã lưu không bao giờ được ghi là hiện thời.
  - Giá trị lưu được thay khi tín hiệu được đo lại, và xóa khi bấm **Phiên mới**.
- "Quan sát tín hiệu": đồ thị Analog/PWM là **dữ liệu demo** (luôn ghi MÔ PHỎNG),
  không dùng để đánh giá; nút Tạm dừng chỉ dừng nguồn demo của đồ thị.
- **Cài đặt**: kịch bản lỗi mô phỏng và tốc độ thời gian ×1/×10/×60 (chỉ rút ngắn thời gian chờ trong mô phỏng).
- Tổng quan, Lịch sử, In / Xuất file hiện là trang chờ; chưa có camera.
- Thông báo lỗi dùng hộp thoại không chặn, không lặp theo mỗi chu kỳ cập nhật.

### Lưu phiên
Phiên tự lưu dạng JSON tại thư mục dữ liệu người dùng (hiển thị trong Cài đặt),
ghi nguyên tử trong worker. Mỗi phiên có snapshot cấu hình, cờ mô phỏng, từng lần
thử, số đo, giới hạn và các lệnh đã ACK. Lỗi lưu: dữ liệu giữ trong bộ nhớ, có
nút **Lưu lại kết quả**. Phiên dở sau khi tắt máy được đánh dấu gián đoạn, không
tự chạy tiếp. **Phiên mới** không reset phần cứng.

## Kiểm thử và preview

```powershell
python -B -m unittest discover -s tests -v          # toàn bộ test (không mở COM thật)
python -B -m unittest tests.test_stm32_bench -v     # một module
python -m tests.preview_main --state finished --capture captures/main_finished.png
python -m tests.preview_main --profile configs/a45/system.json
python -m tests.preview_stm32                       # màn hình hai mảng, giả lập
python -m tests.preview_login --width 1280 --capture captures/login.png
python -m tests.preview_widgets                     # gallery widget/QSS
```

Preview dùng UI thật với dữ liệu giả, chỉ lưu thư mục tạm, không mở COM và không
ghi cài đặt người dùng.

## Phát triển giao diện

### Tổ chức code
- `main.py`: Login → MainWindow, đọc `--profile`.
- `src/ui/`: `main_window.py`, `widgets/` (Login, thanh kết nối, hai mảng STM32, đồ thị), `qml/SignalDashboard.qml`.
- `src/backend.py`: trạng thái duy nhất và bộ chạy bài; `src/device.py`, `src/protocol.py`,
  `src/communication.py`, `src/simulator.py`: thiết bị, codec, I/O serial, giả lập
  (xem [02 Giao thức](docs/02_GIAO_THUC_MODBUS.md)).
- `src/common/`: cấu hình, profile/validator, bản đồ STM32, model, style. `src/storage.py`: lưu phiên.
- `configs/<gia_thu>/`: profile JSON. `tests/`: test tự động và preview.

### Login
- Nền là ảnh `assets/images/login.png` (gốc 1672 × 941); điều khiển Qt đặt theo tọa độ ảnh trong `login_page.py`.
- Cửa sổ ~1280 × 720, thu nhỏ theo màn hình, không phóng to.
- `login.qss` chứa màu/trạng thái; giá trị `px` co theo property `styleScale` (`prepare_page_style()`). Đổi ảnh nền cần cập nhật tọa độ.
- "Quên mật khẩu?"/"Hỗ trợ" mở `InformationDialog` tại chỗ; xác thực hiện là demo.
- Nhãn đổi theo giá thử: `APP_NAME`, `APP_VERSION`, `TESTBENCH_MODEL` (`src/common/config.py`), `LoginBrandText` (`login_page.py`).
- Không đổi `APP_NAME`/`SETTINGS_ORGANIZATION` chỉ để đổi nhãn, vì chúng định danh nơi lưu QSettings.

### Theme
- Gọi `apply_theme(app)` (`src/common/styles.py`) sau khi tạo `QApplication`; QSS trang dùng `apply_page_style(widget, "login")`.
- `common.qss` là nền chung; QSS trang chỉ ghi đè phần riêng; không import QSS trong QSS.
- `@ASSETS@` trong QSS được đổi thành đường dẫn tuyệt đối.
- Property dùng chung:
  - Nút: `variant` = `primary` / `danger` / `text`.
  - Nhãn: `role` = `title` / `muted`.
  - Card: `QFrame` với `role` = `card`.
  - Trạng thái lúc chạy: `set_state(label, "success" | "warning" | "error")`.
- QML có bảng màu riêng, tương ứng với theme Widgets.

### Gallery (`python -m tests.preview_widgets`)
- Danh mục tìm kiếm (có/không dấu, tên lớp Qt); preview tương tác kèm QSS và ví dụ.
- Tự quét `assets/styles/` khi thêm/sửa/xóa QSS; nút **Quét lại**.
- Thay đổi Python cần khởi động lại gallery.
- `--capture captures` xuất `widgets.png`, `login.png`, `login_minimum.png`, `main.png`.

Thêm một trang:
1. Tạo `tests/preview_<trang>.py` theo mẫu `tests/preview_login.py`. `create_preview()` trả widget mới; nó không tạo `QApplication`, không `show()`, không mở phần cứng.
2. Thêm `PagePreview(title, stylesheet, factory, source, usage)` vào `PAGE_PREVIEWS` trong `tests/preview_widgets.py` (`stylesheet=None` nếu chỉ dùng theme chung).
3. Preview có timer/worker phải tự dừng trong `closeEvent`.
4. `src/` không import `tests/`.
