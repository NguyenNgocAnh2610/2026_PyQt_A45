# Quy trình chuyển phần mềm sang giá thử mới

Hướng dẫn từng bước khi dùng lại phần mềm cho một giá thử hoặc khối kiểm tra
khác (tên khối, bài, tín hiệu, dải cho phép thay đổi). Tài liệu này chỉ nêu
**quy trình**. Ý nghĩa từng trường JSON xem [06 Cấu hình](06_CAU_HINH_PROFILE.md);
thanh ghi STM32 xem [02 Giao thức](02_GIAO_THUC_MODBUS.md). Sẽ bổ sung dần khi
phần mềm hoàn thiện (mục 9).

## Mục lục

- [1. Xác định mức độ thay đổi](#1-xác-định-mức-độ-thay-đổi)
- [2. Tạo thư mục profile](#2-tạo-thư-mục-profile)
- [3. Điền cấu hình (theo thứ tự)](#3-điền-cấu-hình-theo-thứ-tự)
  - [3a. Phân bổ bit khi phần cứng chưa đi dây](#3a-phân-bổ-bit-khi-phần-cứng-chưa-đi-dây)
- [4. Nạp, chạy mô phỏng và kiểm tra](#4-nạp-chạy-mô-phỏng-và-kiểm-tra)
- [5. Ghép mạch thật](#5-ghép-mạch-thật)
- [6. Nhãn cố định trong mã](#6-nhãn-cố-định-trong-mã)
- [7. Khi JSON không đủ — phải sửa mã](#7-khi-json-không-đủ--phải-sửa-mã)
- [8. Danh sách kiểm tra nhanh](#8-danh-sách-kiểm-tra-nhanh)
- [9. Giới hạn hiện tại và lịch sử tài liệu](#9-giới-hạn-hiện-tại-và-lịch-sử-tài-liệu)

## 1. Xác định mức độ thay đổi

| Tình huống | Cần làm |
|---|---|
| Vẫn dùng STM32 CPUv1.0 hoặc CPUv1.1 (bản đồ đã có trong `CPU_MAPS`); chỉ khác khối/bài/tín hiệu/dải/bo con | Tạo profile JSON mới (mục 2–4), chọn `hardware.cpu_map`, sửa vài nhãn Login (mục 6) |
| Cần tiêu chí khác `nominal ± tolerance`, hoặc thao tác chưa có (xung, đo tần số, UART/SSI…) | JSON + sửa mã (mục 7) |
| MCU hoặc bản đồ thanh ghi chưa có trong `CPU_MAPS` | JSON + thêm bản đồ/sửa mã tầng giao thức (mục 7) |

Gom đủ tài liệu trước khi làm: danh sách bài đo, sơ đồ chân, bản đồ thanh ghi,
hệ số đo/DAC, trình tự cấp/ngắt nguồn. Thông số chưa biết thì ghi lại; **không
lấy thông số của giá thử cũ áp sang**. Cách làm đã dùng cho A45: lập một phiếu hỏi
tạm trong `docs/` (mỗi mục có phương án gợi ý), người phụ trách phần cứng điền, rồi
chuyển kết quả vào JSON và xóa phiếu.

## 2. Tạo thư mục profile

1. Sao chép `configs/a45/` thành `configs/<gia_thu_moi>/`. **Không sửa `configs/a45/`**: test hồi quy dựa vào nó.
2. Đổi tên file đối tượng (`1101k.json` → ví dụ `khoi_xyz.json`) và cập nhật `target_file` trong `system.json`.
3. Đưa tài liệu bài đo gốc vào `docs/nguon/` (ví dụ `docs/nguon/BAI_KIEM_TRA_<KHOI>.md`, giữ nguyên nội dung) để truy vết; thêm vào `docs/README.md`.

## 3. Điền cấu hình (theo thứ tự)

| Bước | File | Việc cần làm | Tham chiếu |
|---|---|---|---|
| 3.1 | `system.json` | `id`, `name`, `subtitle`; khai báo **mọi** tín hiệu (đo, lệnh, trạng thái) với đơn vị đúng; `status_signals`; bài tự kiểm tra `diagnostics` | 06 Cấu hình → system.json |
| 3.2 | File đối tượng | `id`, `name`, `version`; chép **nguyên văn** tài liệu vào `source_paragraphs`; `sequences` (chuẩn bị/kết thúc, ghi `basis`); từng bài/bước với `actions`, `wait_ms`, `checks` (`nominal`, `tolerance`) | 06 Cấu hình → File đối tượng |
| 3.3a | `hardware.json` | **Đọc firmware CPU** để chọn `cpu_map` (so `System_Register.h`: index `Matrix`/`CDT`, kích thước mảng) và slave ID (CPUv1.1: 8 + công tắc ID). Đọc firmware bo con: slave ID, mỗi thanh ghi điều khiển gì, có kiểm giới hạn không (ví dụ RLMUX không kiểm kênh < 32 → đặt `mux_layout.channels`) | 02 Giao thức mục 3.1, 04 Firmware mục 11 |
| 3.3 | `hardware.json` | Mỗi tín hiệu dùng trong `actions`/`checks`/`sequences` có mục `stm32_io`. **Phân bổ bit** (mục 3a): rơ-le nguồn và lệnh bật/tắt là output `bit`; chân nhận nhiều mức đi qua bo matrix (`matrix_boards` + `sources`); đo qua MUX (số kênh) vào ADC; số đo ngoài nhập tay là input `manual`. Mục chưa đo kiểm để `assumed`; mục phần cứng không làm được để `unsupported` + `reason`. Thêm tín hiệu mới vào `wire_signals` | 06 Cấu hình → hardware.json |
| 3.4 | `mock.json` | `stm32_cases`: "khi các lệnh X đang bật thì khối trả Y" (dữ liệu demo, độc lập với dải tiêu chuẩn). `stm32_timing.loop_ms` = chu kỳ vòng lặp MCU; `hardware.json` → `stm32_io.di_update_ms` ≥ 2 × giá trị này | 06 Cấu hình → mock.json |

### 3a. Phân bổ bit khi phần cứng chưa đi dây

1. Liệt kê mọi nguồn/tín hiệu cần đưa vào khối và mọi mức mỗi chân cần nhận (tra `actions` của mọi bài).
2. Mức cố định (nguồn, ±3 V, 27 V, đất, xung…) lấy từ nguồn ngoài qua rơ-le; DAC chỉ cho mức nhỏ thay đổi theo bài.
3. **Tránh các bit firmware tự bật khi `Mode ≠ 1`/reset** (`hmi_forced_bits`, xem [04 Firmware](04_FIRMWARE_VA_PHAN_CUNG.md) mục 5). Với bo matrix, quy đổi các bit đó ra (đầu vào, đầu ra) và để trống đầu vào tương ứng, để MCU reset không đưa nguồn ra chân.
4. Đặt `interlocks` cho các nguồn không được bật cùng lúc; bước đổi nguồn sẽ được ngắt trước đóng sau (`break_ms`).
5. Bo/thanh ghi mà firmware CPU chưa chuyển tiếp: khai báo `extra_write_registers` và ghi "cần sửa FW" trong `unresolved`; muốn khóa thì đặt bo đó `unsupported`.
6. Ghi bảng phân bổ vào [04 Firmware](04_FIRMWARE_VA_PHAN_CUNG.md) mục 10 (hoặc mục tương ứng của giá thử mới) để người đi dây làm theo, và ghi các điểm cần kiểm vào PROGRESS.

Nguyên tắc khi điền:
- **Dải cho phép = `nominal ± tolerance`.** Tài liệu thiếu hoặc mâu thuẫn → để `tolerance: null` và ghi vào `issues`. Bài sẽ BLOCKED; không tự điền số để bài chạy được. Giá trị do người có thẩm quyền chỉ định tạm thì điền kèm `basis` ghi rõ "tạm, ai chỉ định, ngày".
- Số đo bằng thiết bị ngoài (oxilo…) dùng input `manual`; bỏ trống thì kết quả ghi "mặc định, chưa đo".
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
| `… không có nguồn … nối tới chân này` | Mức yêu cầu không có đầu vào matrix tương ứng và chân không có DAC |
| `… bị HMI CPU tự bật, không được dùng` | Output dùng bit trong `hmi_forced_bits` |
| `Liên động: không được bật đồng thời …` | Vi phạm `interlocks` |
| `Đơn vị không khớp tín hiệu` | `unit` của check khác đơn vị tín hiệu |
| `wire_signals phải ánh xạ duy nhất toàn bộ tín hiệu` | Tín hiệu mới chưa có trong `wire_signals` |
| `preparation/cleanup phải là ID trong target.sequences` | Sai tên trình tự |

2. **Chạy mô phỏng**: Kết nối (Mô phỏng) → "Kiểm tra tự động" → Bắt đầu. Xem bài nào PASS hoặc BLOCKED và lý do. Chi tiết → Hai mảng STM32 cho xem các word đã ghi/đọc.
3. **Hồi quy**: toàn bộ test phải đạt (profile A45 và cấu hình thứ hai không bị ảnh hưởng).
4. Ghi các điểm chưa chốt và kết quả vào `PROGRESS.md`.

## 5. Ghép mạch thật

1. Mở COM ở chế độ Modbus RTU: phần mềm tự đọc FC03; phải thấy "Sẵn sàng · COM THẬT". Sai slave → kiểm công tắc ID
   và `stm32_io.slave`.
2. Chạy **Tự kiểm tra** (D01, D02). D02 cho chu kỳ vòng lặp CPU thật: chỉnh `di_update_ms` (≥ 2 chu kỳ), `break_ms`,
   ngưỡng D02 và `stm32_timing.loop_ms` theo số đo. Chu kỳ lớn bất thường thường do CPU gửi tới bo không lắp
   (+100 ms mỗi khung gửi tới bo vắng; A45 với CPUv1.1 gốc ≈ 360–380 ms, [04 Firmware](04_FIRMWARE_VA_PHAN_CUNG.md) mục 2).
3. Dùng trang **Test Modbus** kiểm từng rơ-le nguồn, từng điểm giao matrix, từng kênh MUX bằng đồng hồ; đo bảng DAC.
   Mục nào đúng thì đổi `status` thành `verified` (bo matrix, DAC, output, input).
4. Bài đo chạy trên mạch thật khi mọi mục nó dùng đã `verified` và D02 đạt; có hộp thoại xác nhận trước mỗi lượt.
   Chi tiết: [05 Vận hành mục 3](05_VAN_HANH_GIAO_DIEN.md).

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
| Firmware CPU có bản đồ thanh ghi mới | Thêm một `CpuMap` vào `CPU_MAPS` (`src/common/stm32.py`: tên thanh ghi DO/DI, `bench_writable`, kích thước mảng, `forwards`) kèm test; profile chọn bằng `hardware.cpu_map` |
| MCU/giao thức khác hẳn (không phải hai mảng Modbus) | Thêm adapter (`protocol.py`, `device.py`, `profiles.py`), xem [03 Luồng Modbus](03_LUONG_MODBUS_TRONG_CODE.md) mục 14 |
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
- [ ] `mock.json`: `stm32_cases` độc lập với dải tiêu chuẩn; `stm32_timing.loop_ms` khớp chu kỳ vòng lặp MCU (khi đã đo được).
- [ ] Ứng dụng mở được với `--profile`; chạy mô phỏng tự động; đã xem lý do BLOCKED.
- [ ] Toàn bộ test đạt.
- [ ] Sửa nhãn Login nếu cần; cập nhật `PROGRESS.md`.

## 9. Giới hạn hiện tại và lịch sử tài liệu

Giới hạn (2026-11-18):
- Chạy trên mạch thật mở theo từng bài (`verified`); chưa có bài đo nào được kiểm trên mạch.
- Một profile mỗi lần khởi động; chưa đổi profile khi đang chạy.
- Tiêu chí chỉ có dạng `nominal ± tolerance` (có thể so trị tuyệt đối).
- Thao tác: bật/tắt bit, chọn nguồn qua bo matrix, một mức DAC tại một thời điểm, đo ADC qua MUX, nhập tay.
- Bo matrix chỉ hỗ trợ bố cục `out*8+in` (8 đầu vào).
- Bản đồ thanh ghi chọn trong `CPU_MAPS` (CPUv1.0, CPUv1.1); firmware khác phải thêm bản đồ vào `src/common/stm32.py` kèm test.
- `wire_signals` của giao thức cũ vẫn bắt buộc.

Lịch sử:
- 2026-11-18: bản đầu tiên.
- 2026-11-18: chuẩn hóa tài liệu; chỉ giữ quy trình, phần schema chuyển về 06_CAU_HINH_PROFILE.md.
- 2026-11-18: thêm mục 3a (phân bổ bit, bo matrix, tránh bit HMI, liên động), nhập tay, giá trị tạm có `basis`.
- 2026-11-21: đổi tên thành `07_CHUYEN_GIA_THU_MOI.md`, thêm mục lục, tham chiếu theo bộ tài liệu 01–07.
- 2026-11-19: thêm bước 3.3a (đọc firmware chọn `cpu_map`, slave, giới hạn bo con); mục 5 thành quy trình ghép mạch thật
  (xác minh FC03, D02, Test Modbus, `verified`).
