# Quy trình chuyển phần mềm sang giá thử mới

Hướng dẫn từng bước khi dùng lại phần mềm cho một giá thử hoặc khối kiểm tra
khác (tên khối, bài, tín hiệu, dải cho phép thay đổi). Tài liệu này chỉ nêu
**quy trình**. Ý nghĩa từng trường JSON xem [CONFIGURATION.md](CONFIGURATION.md);
thanh ghi STM32 xem [STM32_MODBUS_PC.md](STM32_MODBUS_PC.md). Sẽ bổ sung dần khi
phần mềm hoàn thiện (mục 9).

## 1. Xác định mức độ thay đổi

| Tình huống | Cần làm |
|---|---|
| Vẫn dùng STM32 CPUv1.0 (cùng bản đồ thanh ghi); chỉ khác khối/bài/tín hiệu/dải | Tạo profile JSON mới (mục 2–4), sửa vài nhãn Login (mục 6) |
| Cần tiêu chí khác `nominal ± tolerance`, hoặc thao tác chưa có (xung, đo tần số, UART/SSI…) | JSON + sửa mã (mục 7) |
| MCU hoặc bản đồ thanh ghi khác CPUv1.0 | JSON + sửa mã tầng giao thức/thiết bị (mục 7) |

Gom đủ tài liệu trước khi làm: danh sách bài đo, sơ đồ chân, bản đồ thanh ghi,
hệ số đo/DAC, trình tự cấp/ngắt nguồn. Thông số chưa biết thì ghi lại; **không
lấy thông số của giá thử cũ áp sang**.

## 2. Tạo thư mục profile

1. Sao chép `configs/a45/` thành `configs/<gia_thu_moi>/`. **Không sửa `configs/a45/`**: test hồi quy dựa vào nó.
2. Đổi tên file đối tượng (`1101k.json` → ví dụ `khoi_xyz.json`) và cập nhật `target_file` trong `system.json`.
3. Đưa tài liệu bài đo gốc vào `docs/` (ví dụ `docs/BAI_KIEM_TRA_<KHOI>.md`) để truy vết.

## 3. Điền cấu hình (theo thứ tự)

| Bước | File | Việc cần làm | Tham chiếu |
|---|---|---|---|
| 3.1 | `system.json` | `id`, `name`, `subtitle`; khai báo **mọi** tín hiệu (đo, lệnh, trạng thái) với đơn vị đúng; `status_signals`; bài tự kiểm tra `diagnostics` | CONFIGURATION → system.json |
| 3.2 | File đối tượng | `id`, `name`, `version`; chép **nguyên văn** tài liệu vào `source_paragraphs`; `sequences` (chuẩn bị/kết thúc, ghi `basis`); từng bài/bước với `actions`, `wait_ms`, `checks` (`nominal`, `tolerance`) | CONFIGURATION → File đối tượng |
| 3.3 | `hardware.json` | Mỗi tín hiệu dùng trong `actions`/`checks`/`sequences` có mục `stm32_io`: bit rơ-le, DAC + định tuyến, kênh ADC + mã MUX. Mục chưa đo kiểm để `assumed`; mục phần cứng không làm được để `unsupported` + `reason`. Thêm tín hiệu mới vào `wire_signals` | CONFIGURATION → hardware.json |
| 3.4 | `mock.json` | `stm32_cases`: "khi các lệnh X đang bật thì khối trả Y" (dữ liệu demo, độc lập với dải tiêu chuẩn) | CONFIGURATION → mock.json |

Nguyên tắc khi điền:
- **Dải cho phép = `nominal ± tolerance`.** Tài liệu thiếu hoặc mâu thuẫn → để `tolerance: null` và ghi vào `issues`. Bài sẽ BLOCKED; không tự điền số để bài chạy được.
- Giữ `id` tín hiệu/bài ổn định; đổi tên hiển thị thì sửa `label`/`name`.
- Chỉ đổi `status` thành `verified` sau khi đã đo kiểm trên mạch thật.

## 4. Nạp, chạy mô phỏng và kiểm tra

```powershell
conda run -n qt_env python main.py --profile configs/<gia_thu_moi>/system.json
conda run -n qt_env python -m tests.preview_main --profile configs/<gia_thu_moi>/system.json
conda run -n qt_env python -B -m unittest discover -s tests
```

1. **Nạp profile**: nếu cấu hình sai, ứng dụng báo lỗi kèm vị trí và không mở. Lỗi thường gặp:

| Thông báo | Nguyên nhân |
|---|---|
| `P07/S01: Chưa ánh xạ tín hiệu yêu cầu set_41` | Thiếu mục trong `stm32_io.outputs` |
| `Chưa ánh xạ tín hiệu đo …` | Thiếu mục trong `stm32_io.inputs` |
| `set_12: Trùng SW01.bit0 với set_4` | Hai lệnh dùng chung một bit |
| `… cần hai mức khác nhau trên cùng một DAC` | Hai kích thích analog khác mức cùng lúc |
| `… ngoài dải …` / `mã DAC … ngoài giới hạn` | Giá trị vượt `min/max` hoặc giới hạn DAC |
| `Đơn vị không khớp tín hiệu` | `unit` của check khác đơn vị tín hiệu |
| `wire_signals phải ánh xạ duy nhất toàn bộ tín hiệu` | Tín hiệu mới chưa có trong `wire_signals` |
| `preparation/cleanup phải là ID trong target.sequences` | Sai tên trình tự |

2. **Chạy mô phỏng**: Kết nối (Mô phỏng) → "Kiểm tra tự động" → Bắt đầu. Xem bài nào PASS hoặc BLOCKED và lý do. Chi tiết → Hai mảng STM32 cho xem các word đã ghi/đọc.
3. **Hồi quy**: toàn bộ test phải đạt (profile A45 và cấu hình thứ hai không bị ảnh hưởng).
4. Ghi các điểm chưa chốt và kết quả vào `PROGRESS.md`.

## 5. Ghép mạch thật

Hiện **chưa có** đường chạy bài trên mạch thật. Trước đó phải đáp ứng
[STM32_MODBUS_PC.md mục 10](STM32_MODBUS_PC.md#10-điều-kiện-trước-khi-chạy-bài-trên-mạch-thật):
chốt ánh xạ, liên động, trình tự nguồn/dừng; đọc thử FC03 và đối chiếu số đo
bằng màn hình hai mảng.

## 6. Nhãn cố định trong mã

| Vị trí | Nội dung |
|---|---|
| `src/common/config.py` → `TESTBENCH_MODEL` | Mã giá thử ở chân trang hộp thoại Login |
| `src/ui/widgets/login_page.py` → `LoginBrandText` | Tiêu đề/mô tả trang Login |
| `assets/images/login.png` | Ảnh nền Login (nếu có chữ riêng của giá thử cũ) |
| `src/common/testing.py` → `DEFAULT_PROFILE` | Profile mở khi không truyền `--profile` |

**Không đổi** `SETTINGS_ORGANIZATION`: đổi sẽ làm mất cài đặt đã lưu. Tên giá thử
và tên khối trên màn hình chính đã lấy từ JSON.

## 7. Khi JSON không đủ — phải sửa mã

| Nhu cầu | Nơi sửa |
|---|---|
| MCU/bản đồ thanh ghi khác CPUv1.0 | Bản đồ hiện là enum dùng chung trong `src/common/stm32.py` (đổi sẽ ảnh hưởng A45) → tách bản đồ theo profile hoặc thêm adapter (`protocol.py`, `device.py`, `profiles.py`) |
| Tiêu chí dải lệch (min/max), "< X", so sánh hai tín hiệu | `evaluate()` trong `src/backend.py` + validator `profiles.py` + test |
| Thao tác mới (phát xung, đo tần số, UART/SSI…) | Hợp đồng → `protocol.py`/`device.py`/`communication.py` → simulator → test → backend |
| Chạy bài trên mạch thật | Xem mục 5 và quy tắc trong `AGENTS.md` |

Khi sửa mã: backup ZIP toàn project vào `.backup/` (theo AGENTS.md) → sửa → test →
cập nhật tài liệu liên quan và `PROGRESS.md`.

## 8. Danh sách kiểm tra nhanh

- [ ] Có tài liệu bài đo, sơ đồ chân, bản đồ thanh ghi; đã liệt kê thông số chưa biết.
- [ ] Tạo `configs/<gia_thu_moi>/`, không sửa `configs/a45/`; tài liệu gốc đưa vào `docs/`.
- [ ] `system.json`: `id`/`name`, `target_file`, đủ tín hiệu với đơn vị đúng.
- [ ] File đối tượng: `source_paragraphs` nguyên văn; đủ bài/bước; chỗ thiếu ghi `issues`.
- [ ] `sequences` có `basis`.
- [ ] `hardware.json`: mọi tín hiệu có `stm32_io` (`assumed`/`unsupported`); cập nhật `wire_signals`.
- [ ] `mock.json`: `stm32_cases` độc lập với dải tiêu chuẩn.
- [ ] Ứng dụng mở được với `--profile`; chạy mô phỏng tự động; đã xem lý do BLOCKED.
- [ ] Toàn bộ test đạt.
- [ ] Sửa nhãn Login nếu cần; cập nhật `PROGRESS.md`.

## 9. Giới hạn hiện tại và lịch sử tài liệu

Giới hạn (2026-11-18):
- Bộ chạy bài chỉ chạy với simulator; chưa có đường chạy mạch thật.
- Một profile mỗi lần khởi động; chưa đổi profile khi đang chạy.
- Tiêu chí chỉ có dạng `nominal ± tolerance`.
- Thao tác: bật/tắt bit, một mức DAC tại một thời điểm, đo ADC qua MUX.
- Bản đồ thanh ghi STM32 dùng chung cho mọi profile (theo CPUv1.0).
- `wire_signals` của giao thức cũ vẫn bắt buộc.

Lịch sử:
- 2026-11-18: bản đầu tiên.
- 2026-11-18: chuẩn hóa tài liệu; chỉ giữ quy trình, phần schema chuyển về CONFIGURATION.md.
