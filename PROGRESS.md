# Tiến trình phát triển A45

Cập nhật: 2026-11-18. Nhật ký duy nhất của dự án; đọc cùng AGENTS.md trước khi làm.
Chi tiết kỹ thuật nằm trong `docs/` (bản đồ tài liệu: README.md); file này chỉ ghi
hiện trạng, quyết định, việc tiếp theo và lịch sử.

## Bắt đầu phiên làm việc tiếp theo
- Kiểm tra `git status`: phần lớn mã và tài liệu **chưa commit**. Giữ nguyên thay đổi có sẵn.
- Thay đổi lớn/rủi ro: backup ZIP toàn project vào `.backup/` và kiểm tra trước khi sửa (AGENTS.md).
- Giá thử mới dùng lại phần cứng/khung truyền STM32 CPUv1.0 (người dùng xác nhận).
  PC là Master của **một** STM32 Slave (ID 9); MCU tự điều phối các bo phía dưới.
  Bản đồ mặc định theo CPUv1.0, chỉ sửa khi phát sinh. Giao tiếp: `docs/STM32_MODBUS_PC.md`.
- Mục "Rà soát 1101K ↔ CPUv1.0" bên dưới là danh sách cần hỏi phần cứng/firmware.
- Người dùng cho phép dùng skill `multi-agent-orchestrator` cho cả việc code và ngoài code.

## Hiện trạng
- **Đã có:**
  - Login → MainWindow (Widgets + QML), 3 chế độ chạy, lưu phiên nguyên tử.
  - Profile JSON dùng chung, kèm validator tập trung.
  - Kết nối COM thật (Modbus RTU/UART) để chẩn đoán, màn hình hai mảng STM32.
  - Bộ chạy bài 1101K qua hai mảng STM32 (adapter `stm32`) với simulator mức thanh ghi.
  - Tạm dừng/Tiếp tục thật trong backend (cả adapter stm32 và mock):
    - Tạm dừng = về an toàn, lần chạy ghi PAUSED (không tính kết quả); tiếp tục = chạy lại bài từ đầu.
    - Phiên đang tạm dừng mà tắt app sẽ được ghi là gián đoạn.
  - Dashboard giữ giá trị cuối: số đo kèm PASS/FAIL, yêu cầu kèm ACK, cùng bài/bước · giờ; xóa khi đo lại/Phiên mới.
- **Kết quả mô phỏng tự động A45:** 13 PASS (P02–P09, P13–P15, P18, P19), 11 BLOCKED → "Chưa đầy đủ".
- **Chưa có:** đường chạy bài trên mạch thật (`production_ready=false`); ánh xạ
  `hardware.stm32_io` toàn bộ là `assumed`; chưa thử trên mạch thật.
- Adapter `mock` + giao thức A45 v1 cũ chỉ còn cho cấu hình thứ hai trong test và
  chẩn đoán cũ (phụ lục A `docs/STM32_MODBUS_PC.md`).

## Đang làm
- Không có việc dở.

## Rà soát 1101K ↔ CPUv1.0 (cần xác nhận với phần cứng/firmware)
Các lỗi demo cũ đã sửa ngày 2026-11-17:
- P01/P02 không có lệnh cấp nguồn (`actions: []`); P03–P24 không cấp nguồn cho khối.
- Số đo mock trả theo mã bài, không theo lệnh đã gửi.
- Bộ chạy bài đi mailbox A45 v1, không dùng hai mảng của MCU.
- Chưa có ánh xạ tín hiệu ↔ thanh ghi.
- Điều kiện chung nhóm V và xung 43/44XP1 chưa được mô hình hóa.

Các điểm CPUv1.0 chưa đáp ứng hoặc chưa rõ. Mỗi điểm đang là chỗ giữ `assumed` hoặc
`unsupported` trong `configs/a45/hardware.json` → `stm32_io`:
1. Nguồn AC 3 pha ~36 V/1000 Hz: `Power` CPUv1.0 không có bit AC (đang giữ bit0).
   Ai chuyển 36 V → 22 V sau 2 phút? P01 vẫn BLOCKED vì thiếu dung sai và không đo được tần số.
2. DC +27, ±15, ±12, ±5 V: CPUv1.0 chỉ có 24/12/5/3,3 V, không có cực âm, không có 15 V.
   Đang giữ bit1/3/2/4, giả định một bit bật cả cặp ±.
3. Đo dòng AC/DC: không có kênh dòng; đang giả định cảm biến 1 V/A → ADC4 qua MUX 1/2.
4. Điện áp AC từng pha: ADC đo DC/100 (giả định có bộ chuyển RMS, ADC0, MUX 3–5).
   **Không đo được tần số** → `hz_A/B/C` unsupported.
5. Kích thích analog 22/32/40/41/42/54XP1 (0,02…±3 V): chỉ có 1 DAC PA4.
   - Đang giả định −5 mV/mã, mã 0 → 0 V, định tuyến SW02.bit1–6.
   - Cần hệ số tầng ra thật, mức điện thực tế của DAC_val=0 và bit định tuyến.
   - Mỗi thời điểm chỉ có một mức analog.
6. Xung vuông 10 kHz 4,5 Vpp tại 43/44XP1: bộ phát encoder ≤ 250 Hz → unsupported,
   **P10/P11/P12 BLOCKED**. Cần PWM/timer phần cứng hoặc firmware mới.
7. Lệnh mức tại 4 (27 V), 12, 13 (5 V), 15, 23XP1: đang giữ SW01.bit0–4,
   tránh bit 5/6/7/12/14 mà HMI CPUv1.0 dùng.
8. Đo 13 chân XP1:
   - MUX CPUv1.0 dạng bit (bit1 = R+); mã kênh 6–18 và thời gian ổn định 20 ms là giả định.
   - 34/37/48XP1 (0,1–0,45 V, dung sai ±0,05 V) đọc ADC4 ±7,5 V, độ phân giải 0,01 V: sát dung sai.
   - Các chân ±9 V đọc ADC3 ±12 V.
9. MCU không có tín hiệu fault/bảo vệ, không xác nhận đã thực thi, không có timestamp mẫu; Mode ở DI luôn 0.
10. Cần xác nhận `Plan` khi chạy bài (đang dùng 2 = Test) và safe_state (mọi thanh ghi = 0).
11. Trình tự cấp/ngắt nguồn (`sequences`): đang bật mọi nguồn trong một lần ghi `Power`.
    Cleanup ghi DAC=0 trước khi ngắt định tuyến (theo thứ tự địa chỉ); cần xác nhận cách này chấp nhận được.
12. P21: ±3 V tại 54XP1 chưa đưa vào action (giữ issue). Tự kiểm tra D02/D03 chưa được định nghĩa.

## Tiếp theo
- Hỏi phần cứng/firmware 12 điểm trên; điền bit/kênh/hệ số thật vào `stm32_io`
  (chỉ đổi thành `verified` sau khi đo kiểm).
- Ghép RS485, đọc DI bằng màn hình hai mảng, đối chiếu số đo, thử mất cáp/timeout.
- Thiết kế đường chạy bài trên mạch thật (điều kiện: `docs/STM32_MODBUS_PC.md` mục 10).
- Tùy chọn: hiển thị giá trị yêu cầu đã ACK trên dashboard (hiện "Chưa biết" với adapter stm32).

## Vấn đề còn mở
- File chưa xóa, chờ người dùng xem xét:
  - `tests/preview_protocol.py`: preview giao thức A45 v1 cũ, vẫn chạy được.
  - `Giao diện kiểm tra tự động neon xanh.png`: bản thiết kế giao diện tham chiếu.
  - `cmd`, `git_daily.ps1`, `git_daily.sh`: tiện ích Git cá nhân, chưa rõ còn dùng không.
  - `captures/*.png`: ảnh đối chiếu preview.
- `docs/TECHNICAL_REVIEW.md` không còn trên đĩa từ trước; không tự khôi phục.
- Mã nguồn C của firmware chưa có trên máy; chưa đối chiếu C trực tiếp.
- `tests/preview_main.py --scenario` vẫn liệt kê `stale`/`protection`; với adapter stm32 backend sẽ từ chối.
- Khi đang tạm dừng, màn hình chẩn đoán hai mảng vẫn bị khóa (backend coi là đang bận).
- Nút "Tạm dừng" của đồ thị demo trùng tên với nút Tạm dừng quy trình; cân nhắc đổi tên.
- Hai backend cùng một thư mục lưu có thể xung đột ghi (Windows "Access is denied") khi
  phiên còn đang lưu; thực tế chỉ chạy một ứng dụng, test đã tách cho đúng cách dùng.

## Kiểm chứng gần nhất
- 2026-11-18, tạm dừng + giữ giá trị: `python -B -m unittest discover -s tests` đạt
  **124/124**. Test mới gồm:
  - tạm dừng về safe_state, không ghi gì khi đang tạm dừng, tiếp tục chạy lại từ prepare, verdict PASS;
  - dừng hoặc ngắt khi đang tạm dừng → ABORTED, không ghi thêm;
  - giá trị đã lưu (PASS, ACK) trên model, xóa khi Phiên mới;
  - tạm dừng/tiếp tục với adapter mock.

  Đã xem ảnh preview ba trạng thái finished/paused/running. Chưa thử trên mạch thật.
- 2026-11-18, chuẩn hóa tài liệu: chỉ sửa/di chuyển file md và một chuỗi `basis` trong
  `configs/a45/1101k.json`. Đã chạy lại toàn bộ test (kết quả ở mục Lịch sử).
- 2026-11-17, bộ chạy bài STM32: `python -B -m unittest discover -s tests` đạt
  **120/120**; preview màn hình chính đã xem. Chưa thử trên mạch thật.

## Lịch sử ngắn
- 2026-11-18: nút Tạm dừng/Tiếp tục (logic thật trong backend), giữ giá trị tín hiệu sau khi bài xong,
  làm mới giao diện (nút có gradient/trạng thái, LED có quầng sáng, thẻ số đo chữ lớn + chip kết quả).
  Preview thêm `--state paused`. Backup: `.backup/GUI_2026-11-18_00-32-58_UTC+07_before-pause-and-signal-history.zip`.
  124/124 test.
- 2026-11-18: chuẩn hóa tài liệu.
  - Backup trước khi sửa: `.backup/GUI_2026-11-18_00-15-14_UTC+07_before-docs-consolidation.zip` (756 file, CRC OK).
  - Gộp `COMMUNICATION_PROTOCOL.md` và `MODBUS_CONTRACT.md` vào `docs/STM32_MODBUS_PC.md`; A45 v1 thành phụ lục A.
  - `CONFIGURATION.md` thành tham chiếu schema duy nhất; `CHUYEN_GIA_THU_MOI.md` chỉ còn quy trình.
  - README nhận phần sử dụng giao diện; rút gọn PROGRESS.
  - Chuyển `PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md` (giữ nguyên) và `Bai kiem tra.md`
    (→ `docs/BAI_KIEM_TRA_1101K.md`, giữ nguyên nội dung) vào `docs/`.
  - Thêm quy tắc tổ chức tài liệu vào AGENTS.md.
- 2026-11-18: thêm `docs/CHUYEN_GIA_THU_MOI.md`; cho phép dùng skill điều phối cho mọi loại việc.
- 2026-11-17: rà soát 24 bài 1101K; chuyển bộ chạy bài sang hai mảng STM32 (adapter stm32,
  map CPUv1.0 dạng giả định, simulator mức thanh ghi); 120/120 test.
  Backup: `.backup/GUI_2026-11-17_23-09-52_UTC+07_before-stm32-bench-runner.zip`.
- 2026-11-17: thêm quy tắc backup ZIP trước thay đổi lớn và quy tắc dọn file (đã xóa 103 file tạm/cache).
- 2026-11-17: chuyển giao tiếp MCU sang Modbus RTU chuẩn, hai mảng, màn hình đọc/ghi;
  sửa xác minh ACK ghi bằng `rawResult()`; 103/103 test.
- 2026-11-17: kết nối serial thật (74/74); giao thức A45 v1 và giả lập byte (90/90);
  sửa lớp phủ chuyển trang bị kẹt; lập nhật ký duy nhất này.
