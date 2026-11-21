# Tiến trình phát triển A45

Cập nhật: 2026-11-19. Nhật ký duy nhất của dự án; đọc cùng AGENTS.md trước khi làm.
Chi tiết kỹ thuật nằm trong `docs/` (bản đồ tài liệu: README.md); file này chỉ ghi
hiện trạng, quyết định, việc tiếp theo và lịch sử.

## Bắt đầu phiên làm việc tiếp theo
- Kiểm tra `git status`; giữ nguyên thay đổi có sẵn của người dùng.
- Thay đổi lớn/rủi ro: backup ZIP toàn project vào `.backup/` và kiểm tra trước khi sửa (AGENTS.md).
- Phần cứng thật (người dùng xác nhận 2026-11-19): CPU **CPUv1.1 For DK_QDT** (slave **11** = 8 + công tắc ID, đã đọc
  được bằng "Đọc thử Modbus"), 4 bo RLMatrix 8×4, 4 bo RLMUX 2×32 (A45 cần 1), 1 bo RLPW 12 rơ-le, mạch đo dòng; không
  có bo switch. Chưa đi dây. Firmware: `D:\project\2026_DT_Chinh\ref\ref_AHung\A34_Phao37\Program\`.
  Tài liệu: `docs/README.md` (mục lục). Bản đồ CPUv1.1: `docs/02_GIAO_THUC_MODBUS.md` mục 3.1; đề xuất sửa firmware và
  bảng đi dây: `docs/04_FIRMWARE_VA_PHAN_CUNG.md` mục 9, 10.
- Mục "Cần kiểm khi lên phần cứng thật" bên dưới là danh sách điểm giả định phải kiểm khi đi dây/chạy mạch.
- Người dùng cho phép dùng skill `multi-agent-orchestrator` cho cả việc code và ngoài code.

## Hiện trạng
- **Đã có:**
  - Login → MainWindow (Widgets + QML), 3 chế độ chạy, lưu phiên nguyên tử.
  - Profile JSON dùng chung, kèm validator tập trung.
  - Kết nối COM thật (Modbus RTU/UART); mở Modbus RTU tự xác minh CPU bằng FC03 → "Sẵn sàng · COM THẬT".
  - Bản đồ thanh ghi theo firmware (`hardware.cpu_map`: CPUv1.0 / CPUv1.1), màn hình hai mảng theo bản đồ.
  - Bộ chạy bài 1101K qua hai mảng STM32 (adapter `stm32`) trên COM ảo và **COM thật có cổng chặn**: tự kiểm tra chạy
    ngay; bài đo chỉ khi mọi ánh xạ nó dùng `verified` + D02 đạt + người vận hành xác nhận.
  - Trang **Test Modbus**: lấy quyền/về an toàn/trả HMI, 12 rơ-le nguồn, lưới matrix từng bo, MUX, DAC, DOUT, đọc ADC,
    thanh ghi thô (tự đọc định kỳ), nhật ký khung xuất file; cùng luật an toàn với bộ chạy bài.
  - Mô phỏng chạy trên **cổng COM ảo**: cùng `SerialConnection`/`Device` như COM thật, khung
    Modbus RTU + CRC thật, slave giả lập theo FreeModbus, mô phỏng vòng lặp CPU (`loop_ms` giả định 50 ms).
    Khi ghép mạch thật chỉ khác client Modbus.
  - Tạm dừng/Tiếp tục thật trong backend (cả adapter stm32 và mock):
    - Tạm dừng = về an toàn, lần chạy ghi PAUSED (không tính kết quả); tiếp tục = chạy lại bài từ đầu.
    - Phiên đang tạm dừng mà tắt app sẽ được ghi là gián đoạn.
  - Dashboard giữ giá trị cuối: số đo kèm PASS/FAIL, yêu cầu kèm ACK, cùng bài/bước · giờ; xóa khi đo lại/Phiên mới.
  - Ánh xạ phần cứng (2026-11-19): RLPW 12 rơ-le, 4 bo RLMatrix (ID 6 có sẵn; ID 7–9 cần sửa FW), mọi lệnh mức qua matrix
    (không cần driver DOUT), RLMUX số kênh (chặn ≥ 32); ngắt trước đóng sau, liên động AC 36/22 V, nhập tay tần số, kiểm trị
    tuyệt đối, dừng lượt khi P01/P02 FAIL; tự kiểm tra D01 truyền thông, D02 chu kỳ vòng lặp CPU.
- **Kết quả mô phỏng tự động A45:** 24/24 PASS (bỏ trống tần số → "có giá trị mặc định chưa đo"). Tự kiểm tra: D01, D02 PASS,
  D03 BLOCKED (chưa định nghĩa).
- **Chưa có:** ánh xạ `hardware.stm32_io` toàn bộ là `assumed` (nên trên mạch thật mới chạy được tự kiểm tra);
  phần cứng chưa đi dây; firmware chưa sửa cho bo matrix 2–4; chưa chạy tự kiểm tra/bài đo nào trên mạch thật
  (`production_ready=false`).
- Adapter `mock` + giao thức A45 v1 cũ chỉ còn cho cấu hình thứ hai trong test và
  chẩn đoán cũ (phụ lục A `docs/02_GIAO_THUC_MODBUS.md`).

## Đang làm
- 2026-11-19: báo cáo rà soát trước khi chạy thật `docs/bao_cao/2026-11-19_RA_SOAT_TRUOC_CHAY_THAT.md` (tạm, chờ người dùng trả lời mục 9;
  chưa sửa mã). Phát hiện chính:
  - 4 RLMatrix cùng ID 6, 4 RLMUX cùng ID 2 (cố định trong firmware) → chỉ cắm 1 bo mỗi loại; firmware giữ nguyên chạy
    được 15/24 bài;
  - `break_ms` 150 < chu kỳ CPU ≈ 370 ms → ngắt-trước-đóng-sau không được đảm bảo trên mạch thật;
  - "Trả về HMI" để nguồn đóng.

## Cần kiểm khi lên phần cứng thật
Ánh xạ trong `configs/a45/hardware.json` → `stm32_io` là **bảng phân bổ để đi dây** (cập nhật 2026-11-19 cho CPUv1.1 + 4 bo
matrix; bảng ở `docs/04_FIRMWARE_VA_PHAN_CUNG.md` mục 10). Mọi mục `assumed`. Kiểm từng điểm bằng trang **Test Modbus** + đồng hồ,
đạt thì đổi `verified` (bài đo trên mạch thật chỉ chạy khi mọi mục nó dùng đã `verified`).

Ngay khi nối mạch
1. Chạy **Tự kiểm tra** trên COM thật: D01 phải PASS; D02 cho chu kỳ vòng lặp CPU. CPUv1.1 mỗi vòng vẫn gửi 1 khung tới
   HMI ID 4 và 2 khung tới bo switch ID 1 (đều không lắp), mỗi khung chờ hết `t_timeout` 100 ms → ước tính **≈ 360–380
   ms/vòng** (bảng ở 04_FIRMWARE_VA_PHAN_CUNG mục 2; ước tính cũ 250–350 ms là thiếu) > ngưỡng 75 ms → D02 FAIL, bài đo bị chặn
   cho tới khi sửa firmware (`04_FIRMWARE_VA_PHAN_CUNG` mục 9 bước 3, còn ≈ 60–70 ms) hoặc nâng `di_update_ms`/`break_ms`/ngưỡng D02 theo số đo.

Bo matrix
2. Rơ-le RL(k+1) nối đầu vào nào với đầu ra nào (firmware chỉ biết bit k → RL k+1; giả định k = (ra−1)×8 + (vào−1)).
   Kiểm: Test Modbus → bấm từng ô, đo thông mạch; sai thì sửa `matrix_boards`.
3. Bo ID 7–9 **cần sửa firmware**: CPU gửi `Matrix2_0…Matrix4_1` (index 31–36) tới ID 7/8/9; build RLMatrix với
   `SLAVE_ADDRESS` 7/8/9 (hiện cố định 0x06 → 4 bo cùng ID sẽ xung đột). Chưa sửa thì 32/54/43/44XP1 và mọi lệnh mức
   (4/12/13/15/23XP1) không điều khiển được trên mạch thật (P10–P12, P14, P16, P20–P24).

Bo MUX
4. Đã xác nhận từ firmware: byte thấp = kênh MUX1, byte cao = MUX2, kênh 31 = hở hết, **không kiểm < 32** (phần mềm chặn).
   Còn phải kiểm: hai đầu ra MUX vào ADC nào (giả định MUX1 → ADC3); thêm bo MUX 2–4 thì cần ID riêng như bo matrix.

Đo lường
5. Kênh ADC và hệ số mạch đo dòng/áp AC/DC (giả định 1 V/A, 0,1 V/V, qua MUX1 kênh 13–17). Áp AC phải ra DC tỉ lệ RMS.
6. `ADC3` ±12 V, bước 0,01 V cho chân nhỏ 34/37/48XP1 (0,1–0,45 V, dung sai ±0,05 V): sát; người dùng chấp nhận một lần đọc.

Kích thích
7. DAC: giả định tầng có trừ 1,62 V, `V_XP1 = −DAC_val × 1,55 mV`. Đo bảng 5 điểm (`DAC_val` −1000…1000) rồi sửa
   `stm32_io.dac`; offset vài mV là lớn so với 0,02 V của P04.
8. 43/44XP1 đang dùng chung một nguồn xung (đầu vào 4 của bo ID 7); chưa rõ cùng pha, ngược pha hay hai nguồn.

Nguồn
9. `Power` bit 1/2/4/6 (AC 22 V, +27, −15, −12 V) bị nút HMI bật/tắt khi `Mode ≠ 1`; bit 7–9 để trống vì bị ép bật.

Firmware (người dùng cho phép sửa, chưa sửa; đề xuất cụ thể ở 04_FIRMWARE_VA_PHAN_CUNG mục 9)
10. - Slave ID riêng cho từng bo con; CPU gửi bo matrix 2–4; bỏ gửi tới bo switch/HMI không lắp.
    - FW-03: reset/`Mode ≠ 1` → HMI tự bật VDD1–3; PC không phát hiện được MCU reset.
    - FW-04: `Error_M` (lỗi bo con) không báo lên PC; ACK không chứng minh rơ-le đã đóng.
    - FW-05: `REG_HOLDING_NREGS = 128` > mảng (50 word ở CPUv1.1) → ghi ngoài vùng đè RAM. PC tự chặn.
    - FW-06: `Plan = 2`; `Plan = 0` cấu hình lại GPIO mỗi vòng. FW-07: không có watchdog khi mất PC.
    - RLMUX không kiểm kênh < 32; `main.c` ghi bit 31 vào biến 16 bit.

Bài kiểm tra (giá trị tạm do người dùng chỉ định 2026-11-18, ghi ở `basis` của từng check)
11. NG-03 áp 22 ± 2 V; P12/P17 dung sai thiếu = ±0,2 V; P20 kiểm trị tuyệt đối; P22–P24 dấu tạm (50XP1 dương, 49XP1 âm);
    NG-07 đo dòng khởi động tại 1 s; mỗi bước chờ 250 ms.
12. Giữ đúng tài liệu nhưng còn nghi vấn: P16 đo 26XP1 (P14 dùng 25XP1), P18 −0,3 V, P23 "không có CX3" nhưng vẫn cấp 5 V.

## Tiếp theo
- Người dùng: mở COM thật → "Sẵn sàng · COM THẬT" → chạy Tự kiểm tra (D01/D02), gửi lại chu kỳ D02 đo được.
- Sửa firmware theo `docs/04_FIRMWARE_VA_PHAN_CUNG.md` mục 9 (slave ID bo con, bo matrix 2–4, bỏ gửi bo vắng); chạy lại D02.
- Đi dây theo `docs/04_FIRMWARE_VA_PHAN_CUNG.md` mục 10; kiểm từng rơ-le/điểm giao/kênh bằng Test Modbus; đo bảng DAC; đổi `verified` từng mục.
- Xác nhận dấu P22–P24 và các dung sai tạm. Bổ sung bài tự kiểm tra (D03 ADC…) khi người dùng yêu cầu.

## Vấn đề còn mở
- File chưa xóa, chờ người dùng xem xét:
  - `tests/preview_protocol.py`: preview giao thức A45 v1 cũ, vẫn chạy được.
  - `Giao diện kiểm tra tự động neon xanh.png`: bản thiết kế giao diện tham chiếu.
  - `cmd`, `git_daily.ps1`, `git_daily.sh`: tiện ích Git cá nhân, chưa rõ còn dùng không.
  - `captures/*.png`: ảnh đối chiếu preview.
- `docs/TECHNICAL_REVIEW.md` không còn trên đĩa từ trước; không tự khôi phục.
- Firmware (CPU v1.0/v1.1, RLMatrix, RLMUX, RLPW) ở `D:\project\2026_DT_Chinh\ref\ref_AHung\A34_Phao37\Program\`
  (thư mục cũ `D:\project\2026_DT_Chinh\Program\` đã chuyển). Sơ đồ mạch các bo con chưa có (cần cho bảng RL → điểm giao).
- Hộp thoại "Hai mảng STM32" vẫn mở từ Chi tiết kết nối; trang Test Modbus có cùng bảng (tab Thanh ghi CPU).
- `tests/preview_main.py`: thêm `--state manual` (chụp hộp thoại nhập tay); các trạng thái khác tự bỏ trống nhập tay.
- Orchestrator: ngân sách mềm trong `.agent-orchestrator/config.json` (Codex 160k, Antigravity 120k/ngày, trần 30k/60k mỗi
  việc) nhỏ so với mức dùng thật (Codex 40–150k token cho một việc nhỏ). Người dùng quyết định có nâng không.
- Worktree tạm `../GUI-wt-fwreview` (detached, chỉ có file task) có thể xóa bằng `git worktree remove`.
- `tests/preview_main.py --scenario` vẫn liệt kê `stale`/`protection`; với adapter stm32 backend sẽ từ chối.
- Khi đang tạm dừng, màn hình chẩn đoán hai mảng vẫn bị khóa (backend coi là đang bận).
- Nút "Tạm dừng" của đồ thị demo trùng tên với nút Tạm dừng quy trình; cân nhắc đổi tên.
- Ví dụ CRC trong `docs/nguon/PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md` sai (giữ nguyên file nguồn).
  - Khung đúng ghi ở `docs/02_GIAO_THUC_MODBUS.md` mục 6.
  - Thêm: FC03 bo HMI `04 03 00 00 00 05` có CRC đúng là `85 9C`, không phải `84 5C`.
- Hai backend cùng một thư mục lưu có thể xung đột ghi (Windows "Access is denied") khi
  phiên còn đang lưu; thực tế chỉ chạy một ứng dụng, test đã tách cho đúng cách dùng.

## Kiểm chứng gần nhất
- 2026-11-19 tối, rà nguyên tắc "PC chỉ nói chuyện với CPU": `python -B -m unittest discover -s tests` đạt **163/163**
  (thêm: gửi tới ID bo con 1/2/3/4/6/7 bị từ chối, không khung nào rời PC; mọi khung lấy quyền điều khiển đi tới slave
  11; ô CPU slave chỉ đọc). Chưa chạy trên mạch thật.
- 2026-11-19 tối, trải nghiệm Test Modbus: `python -B -m unittest discover -s tests` đạt **161/161** (thêm 2 test trong
  `tests/test_real_bench.py`: đọc nền không khóa nút/không đổi dòng trạng thái và lệnh bấm trong lúc đọc được gửi sau;
  nhãn đường đi qua CPU). Preview `--state modbus` đã xem. Chưa chạy trên mạch thật.
- 2026-11-19, CPUv1.1 + chạy thật + Test Modbus: `python -B -m unittest discover -s tests` đạt **159/159** (trước khi sửa
  148/148). Test mới (`tests/test_real_bench.py`, cổng "thật" là COM ảo nối simulator CPUv1.1 slave 11, vòng lặp 50 ms):
  - mở Modbus RTU → FC03 xác minh, không ghi gì → "Sẵn sàng · COM THẬT"; sai slave → "Không có phản hồi STM32 (slave 11)";
  - tự kiểm tra trên "mạch thật" cần xác nhận, D01/D02 PASS, phiên `simulation: false`, `time_scale` 1.0;
  - bài đo bị chặn khi chưa `verified`/chưa D02, không ghi gì; P02 với ánh xạ `verified` chạy được, chờ không chia ×60;
  - công cụ: lấy quyền, ngắt trước đóng sau (≥ `break_ms`), liên động, chặn MUX ≥ 32 (cả ghi thô), ghi thô làm trạng thái
    "chưa biết", trang Test Modbus bấm ô matrix/rơ-le/MUX/Về an toàn.
  - `tests/test_stm32_modbus.py`: bản đồ CPUv1.1 khớp `System_Register.h` (Matrix 18–19, CDT 20, DataR1..4 20–42).

  Preview: trang Test Modbus (`--state modbus`), hộp thoại hai mảng (DO 31 / DI 43, slave 11), chạy tự động ×10 24/24 PASS.
  Chưa chạy trên mạch thật.
- 2026-11-18, áp dụng phiếu xác nhận: `python -B -m unittest discover -s tests` đạt **147/147** (trước khi sửa 138/138);
  `tests.test_stm32_bench` chạy lại thêm 2 lần đều đạt (test có phụ thuộc thời gian thực). Test mới:
  - kiểu `pin`/bo matrix: chọn một nguồn, nhả khi `null`, DAC, không có nguồn → lỗi, một DAC, liên động AC 36/22 V;
  - không output nào dùng bit HMI ép bật; ngắt trước đóng sau (P01 đổi 36 → 22 V cách ≥ `break_ms`, không lúc nào cả hai);
  - validator: bit HMI, chân ở hai bo, thanh ghi mở rộng sai, MUX an toàn sai, kênh idle, bước đo không check, `absolute`;
  - simulator: chập hai nguồn → không khớp case, lượng tử DAC, thanh ghi mở rộng, nhiễu ADC2 theo vòng lặp;
  - runner: P02, 24/24 PASS tự động, bo unsupported → BLOCKED không ghi gì, P01 FAIL dừng cả lượt, nhập tay (có nhập,
    bỏ trống → mặc định, tạm dừng khi đang chờ), D01/D02 đo chu kỳ ≈ `loop_ms`.

  Preview: hộp thoại nhập tay (`--state manual`), chạy tự động ×10 → 24/24 PASS, preview hai mảng. Chưa thử trên mạch thật.
- 2026-11-18, cổng COM ảo: `python -B -m unittest discover -s tests` đạt **138/138** (thêm 14 test trong
  `tests/test_virtual_port.py`):
  - CRC theo vector chuẩn;
  - slave FreeModbus: im lặng khi sai CRC/slave, exception 01/02/03;
  - độ trễ vòng lặp CPU;
  - SerialConnection qua COM ảo: đọc/ghi, exception, timeout đóng cổng, rút cáp;
  - bộ chạy bài P02 qua COM ảo; thời gian chờ quá ngắn → FAIL.

  Preview hai mảng hiện khung TX/RX; preview chạy tự động: 13 PASS / 11 BLOCKED như trước.
  Chưa thử trên mạch thật.
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
- 2026-11-21: tổ chức lại `docs/` (chỉ tài liệu; backup `.backup/GUI_2026-11-21_09-00-34_UTC+07_before-docs-reorg.zip`,
  958 file, kiểm tra OK).
  - Mục lục chung `docs/README.md` (danh sách, thứ tự đọc theo vai trò, quy ước tên/tham chiếu/mục lục). Mỗi file có
    `## Mục lục`.
  - `STM32_MODBUS_PC.md` + `LUONG_CODE_VA_MODBUS.md` tách/gom thành `01_KIEN_TRUC_PHAN_MEM`, `02_GIAO_THUC_MODBUS`,
    `03_LUONG_MODBUS_TRONG_CODE`, `04_FIRMWARE_VA_PHAN_CUNG`, `05_VAN_HANH_GIAO_DIEN`; bỏ phần trùng (sơ đồ tầng, mô tả kiểu
    output/input đã có ở schema, mô tả COM ảo hai nơi). `CONFIGURATION.md` → `06_CAU_HINH_PROFILE.md`,
    `CHUYEN_GIA_THU_MOI.md` → `07_CHUYEN_GIA_THU_MOI.md`; tài liệu nguồn → `docs/nguon/` (nội dung giữ nguyên); báo cáo rà
    soát → `docs/bao_cao/2026-11-19_RA_SOAT_TRUOC_CHAY_THAT.md`.
  - Bảng đổi số mục cũ `STM32_MODBUS_PC` → mới: 1–4 → 02 (giữ số), 5.1 → 02 mục 5, 11 → 02 mục 6, 5.2 → 01 mục 8,
    6/6.1/10 → 05 mục 1/2/3, 7 → 03 mục 4, 8 → 03 mục 7, 12 → 03 mục 16, 9.N → 04 mục N. Các mục lịch sử bên dưới vẫn ghi
    tên/số mục cũ.
  - Sửa chỗ lỗi thời: ví dụ khung A45 (slave 11, CRC tính lại), kích thước mảng CPUv1.1, ô CPU slave cố định, hàng "bản đồ
    thanh ghi khác" trong 07. Cập nhật tham chiếu ở AGENTS, CLAUDE, README, `hardware.json` (ghi chú), một comment test.
  - Kiểm: script kiểm liên kết/anchor 0 lỗi; `unittest discover` **163/163**.
- 2026-11-19 khuya: thêm tài liệu `docs/LUONG_CODE_VA_MODBUS.md` (chỉ tài liệu, không sửa mã).
  - Nội dung: luồng code tổng; chuỗi hàm truyền/nhận Modbus (`Device._request_stm32` → `SerialConnection` →
    `_read_done`/`_write_done` → `Device._stm32_received` → `_bench_result` / `Backend._stm32_completed`); cách đặt log
    (Python `logging`, `QT_LOGGING_RULES`); khung sườn `sendRawRequest` để tùy biến khung.
  - Script ví dụ (FC06 Mode=1 rồi FC03) và ví dụ ánh xạ (`dc_27v` → `[(12, [4])]`, `xp1_50` → MUX 0x1F08) đã chạy thử
    trên COM ảo. Khung sườn `raw_request` và log Qt `qt.modbus*` chưa chạy thử.
  - Sửa dòng lỗi thời "không có polling tự động" ở `STM32_MODBUS_PC.md` mục 5.1; thêm liên kết ở README, CLAUDE.md.
- 2026-11-19 tối: rà luồng PC → CPU → bo con.
  - Đúng sẵn: bộ chạy bài và xác minh khi mở cổng chỉ dùng `stm32_io.slave`; chỉ ghi thanh ghi CPU (`bench_writable` +
    thanh ghi mở rộng); bo con do CPU gửi tiếp.
  - Lỗ hổng đã bịt: trang Test Modbus, bảng thanh ghi và ô ID trên thanh kết nối cho nhập slave tùy ý (có thể gửi thẳng
    tới ID bo con). Nay `Backend.check_cpu_slave()` chặn ở backend; các ô ID chỉ hiển thị CPU slave. "Đọc thử" (chỉ đọc)
    vẫn cho ID tùy ý để dò ID bo CPU.
- 2026-11-19 tối: trang Test Modbus hết nháy khi tự đọc.
  - Nguyên nhân: mỗi lượt đọc 500 ms khóa rồi mở lại mọi nút (`serial_read_pending`), dòng trạng thái đổi "Đang chờ…" ↔
    "Đã đọc…", nhãn số đọc nhiều dòng đổi độ cao.
  - Sửa: đọc nền `request_stm32(background=True)` + `Backend.stm32_foreground_busy`; lệnh công cụ xếp hàng sau lượt đọc
    nền; ô số đọc cố định font đơn cách, chỉ vẽ lại khi đổi; chọn chu kỳ tự đọc.
  - Nhãn: tab "Điều khiển qua CPU", dòng "Đường đi lệnh" và tiêu đề nhóm ghi thanh ghi CPU → bo con (`CpuMap.forwards`).
  - Sửa ước tính chu kỳ D02 từ firmware: ≈ 360–380 ms (STM32_MODBUS_PC mục 9.2).
  - Backup: `.backup/GUI_2026-11-19_18-53-02_UTC+07_before-modbus-ui-flicker.zip` (96 file, CRC OK). 161/161 test.
- 2026-11-19: chuyển sang phần cứng thật theo firmware người dùng cung cấp (`ref_AHung\A34_Phao37\Program`).
  - Lỗi người dùng gặp ("kiểm tra kết nối" khi chạy tự kiểm tra/tự động trên COM thật): do khóa chỉ-mô-phỏng có chủ đích,
    cộng sai slave (9 thay vì 11) và sai bản đồ (CPUv1.0: index 18 là CDT; CPUv1.1: index 18 là Matrix[0]).
  - Bản đồ thanh ghi theo profile (`CpuMap`, `CPU_MAPS`, `hardware.cpu_map`); A45 = CPUv1.1, slave 11.
  - Ánh xạ: 4 bo RLMatrix (ID 6 qua Matrix0/1; ID 7–9 qua đề xuất FW index 31–36), lệnh mức chuyển từ DOUT sang matrix,
    RLMUX `channels: 32` (chặn ghi kênh ≥ 32 ở mọi đường), bỏ bo switch khỏi safe_state.
  - Chạy thật có cổng chặn (xác minh FC03 khi mở cổng, `real_run_blockers`, `stm32_unverified`, `confirm_real`, chờ không
    chia hệ số), trang Test Modbus (`Backend.tool_*`, `src/ui/widgets/modbus_test.py`), bảng thanh ghi theo bản đồ có tự đọc.
  - Tài liệu: STM32_MODBUS_PC mục 1, 2.1, 3.1 (mới), 6, 6.1 (mới), 7, 9.9, 9.10, 9.11 (mới), 10; CONFIGURATION; README;
    CHUYEN_GIA_THU_MOI (3.3a, mục 5); AGENTS (hiện trạng chạy thật); CLAUDE.
  - Backup: `.backup/GUI_2026-11-19_17-41-21_UTC+07_before-cpuv11-real-bench-modbus-tool.zip`. 159/159 test.
- 2026-11-19: sửa skill `multi-agent-orchestrator` (trước đây chưa giao việc được lần nào). Đã thử thật Antigravity (`agy` 1.5.11)
  và Codex (`codex-cli` 0.169.0): đọc repo, chạy `tests.test_virtual_port` (15 OK), đọc thư mục ngoài repo, ghi file.
  - Lỗi gốc: `agy -p --mode accept-edits` chỉ duyệt sửa file, mọi lệnh shell bị từ chối âm thầm; tài khoản không có
    `--mode auto`. Sửa: `--sandbox` + file `--settings` riêng mỗi lần chạy với quy tắc `command(<lệnh đúng nguyên văn>)`
    (Windows bắt khớp chính xác) và `read_file(<thư mục>)`; không dùng `--add-dir` (đổi thư mục làm việc → test chạy sai chỗ).
  - Script trước coi `status: SUCCESS` là đạt dù có `denied_actions` và câu trả lời rỗng; nay kiểm cả hai, đọc lỗi/tin nhắn
    cuối của Codex, ghi `problems`/`response` vào report.
  - Codex: đóng stdin (tránh treo); `--read-only` (không cần worktree sạch, so `git status` sau khi chạy);
    `--allow-command`, `--read-dir`; sổ token đặt lại mỗi ngày; model `strong` của Antigravity đổi thành `gemini-4-argon-high`
    (`gemini-3.1-pro-high` không có trong `agy models`).
- 2026-11-18: sửa lỗi người dùng báo: nhập tay tần số ở P01 (có nhập hay bỏ trống) đều ra ERROR "Mẫu thiếu, lỗi hoặc hết
  hạn". Nguyên nhân: số đo tự động của cùng bước (áp 3 pha, dòng) đọc trước khi hộp thoại hiện, quá `stale_ms` (1 s) khi
  người vận hành trả lời. Sửa: giữ nguyên các số đo đó lúc mở hộp thoại và đánh giá theo thời điểm đọc (`_manual_frozen`).
  Test hồi quy trả lời sau 2,5 s; 148/148 test.
- 2026-11-18: áp dụng phiếu xác nhận `docs/CAN_XAC_NHAN_TAM.md` (đã xóa sau khi chuyển hết nội dung vào cấu hình, tài liệu
  và mục "Cần kiểm khi lên phần cứng thật").
  - Cấu hình A45: rơ-le nguồn 12 kênh (mỗi cực DC một rơ-le, AC 36/22 V hai rơ-le có liên động), 2 bo matrix 8×4 qua
    `matrix_boards`/`sources`, lệnh mức trên `DOUT`, DAC ±1,5 V, MUX số kênh 2 bank, `di_update_ms` 100 → 150, `break_ms`.
  - Lõi: output `pin`, `off_value`/`null`, ngắt trước đóng sau, `interlocks`, `hmi_forced_bits`, `extra_write_registers`
    (`SW03`/`SW04` = đề xuất sửa FW), input `manual` + hộp thoại `src/ui/widgets/manual_input.py`, `loop_probe` (D02),
    check `absolute`, bài `stop_on_fail`, bước `stimulate` không đo.
  - 24 bài theo quyết định của người dùng (P01 3 bước, P21 hai bước, dung sai/dấu tạm có `basis`), không còn `issues`.
  - Tài liệu: STM32_MODBUS_PC mục 7, 8, 9.9, **9.10 (bảng đi dây)**, 10; CONFIGURATION; CHUYEN_GIA_THU_MOI mục 3a; README; CLAUDE.
  - Backup: `.backup/GUI_2026-11-18_23-11-36_UTC+07_before-apply-questionnaire.zip`. 147/147 test.
- 2026-11-18: rà soát firmware CPUv1.0 từ mã nguồn, gộp vào `docs/STM32_MODBUS_PC.md` mục 9 (luồng PC → CPU → bo con, vòng lặp
  và thời gian, bus USART1, chân DOUT/DIN/DAC/ADC, HMI mode/reset, stack slave, hướng dẫn điều khiển một rơ-le).
  Sửa trong tài liệu: SSI Enable là bit 15 (không phải bit 8); cập nhật lại các mục COM ảo bị mất khi tài liệu được viết lại.
  Chỉ sửa tài liệu, không sửa mã.
- 2026-11-18: mô phỏng STM32 = cổng COM ảo (`src/virtual_port.py`, `Stm32RtuSlave`, vòng lặp CPU `loop_ms`).
  - Bỏ đường mô phỏng đi tắt trong `Device`.
  - Kịch bản lỗi tạo trên đường truyền; timeout đóng COM ảo như cổng thật.
  - Đo chờ `di_update_ms + mux_settle_ms` kể từ ACK ghi cuối.
  - Màn hình hai mảng hiện khung RTU TX/RX.
  - Sửa lỗi `MainWindow._shutdown_ready`: `QTimer.singleShot` thiếu context làm lỗi rò sang test sau khi cửa sổ đã bị xóa.
  - Backup: `.backup/GUI_2026-11-18_06-57-11_UTC+07_before-virtual-com-port.zip` (807 file, CRC OK).
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
