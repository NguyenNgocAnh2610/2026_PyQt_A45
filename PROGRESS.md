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
- Mục "Cần kiểm khi lên phần cứng thật" bên dưới là danh sách điểm giả định phải kiểm khi đi dây/chạy mạch.
- Người dùng cho phép dùng skill `multi-agent-orchestrator` cho cả việc code và ngoài code.

## Hiện trạng
- **Đã có:**
  - Login → MainWindow (Widgets + QML), 3 chế độ chạy, lưu phiên nguyên tử.
  - Profile JSON dùng chung, kèm validator tập trung.
  - Kết nối COM thật (Modbus RTU/UART) để chẩn đoán, màn hình hai mảng STM32.
  - Bộ chạy bài 1101K qua hai mảng STM32 (adapter `stm32`).
  - Mô phỏng chạy trên **cổng COM ảo**: cùng `SerialConnection`/`Device` như COM thật, khung
    Modbus RTU + CRC thật, slave giả lập theo FreeModbus, mô phỏng vòng lặp CPU (`loop_ms` giả định 50 ms).
    Khi ghép mạch thật chỉ khác client Modbus.
  - Tạm dừng/Tiếp tục thật trong backend (cả adapter stm32 và mock):
    - Tạm dừng = về an toàn, lần chạy ghi PAUSED (không tính kết quả); tiếp tục = chạy lại bài từ đầu.
    - Phiên đang tạm dừng mà tắt app sẽ được ghi là gián đoạn.
  - Dashboard giữ giá trị cuối: số đo kèm PASS/FAIL, yêu cầu kèm ACK, cùng bài/bước · giờ; xóa khi đo lại/Phiên mới.
  - Ánh xạ phần cứng theo phiếu xác nhận 2026-11-18: rơ-le nguồn 12 kênh, 2 bo matrix 8×4 (bo 2 cần sửa FW CPU), DOUT,
    MUX số kênh; ngắt trước đóng sau, liên động AC 36/22 V, nhập tay tần số, kiểm trị tuyệt đối, dừng lượt khi P01/P02 FAIL;
    tự kiểm tra D01 truyền thông, D02 chu kỳ vòng lặp CPU.
- **Kết quả mô phỏng tự động A45:** 24/24 PASS (bỏ trống tần số → "có giá trị mặc định chưa đo"). Tự kiểm tra: D01, D02 PASS,
  D03 BLOCKED (chưa định nghĩa).
- **Chưa có:** đường chạy bài trên mạch thật (`production_ready=false`); ánh xạ
  `hardware.stm32_io` toàn bộ là `assumed`; phần cứng chưa đi dây; chưa thử trên mạch thật.
- Adapter `mock` + giao thức A45 v1 cũ chỉ còn cho cấu hình thứ hai trong test và
  chẩn đoán cũ (phụ lục A `docs/STM32_MODBUS_PC.md`).

## Đang làm
- Không có việc dở. Đợt 2026-11-18 (áp dụng phiếu xác nhận) đã xong, chờ người dùng xem và đi dây theo mục 9.10.

## Cần kiểm khi lên phần cứng thật
Ánh xạ trong `configs/a45/hardware.json` → `stm32_io` là **bảng phân bổ để đi dây** (2026-11-18, theo phiếu xác nhận;
bảng ở `docs/STM32_MODBUS_PC.md` mục 9.10). Mọi mục `assumed`. Khi lên mạch, kiểm từng điểm, đạt thì đổi `verified`.

Bo matrix
1. Bit nào ứng với điểm giao nào. Đang giả định bit = (đầu ra − 1) × 8 + (đầu vào − 1). Sai thì phải tính lại đầu vào
   nào để trống vì HMI (đang để trống 1/5/7 của matrix 1). Kiểm: ghi từng bit `SW01`/`SW02`, đo thông mạch.
2. Bo matrix 2 (và 3–4 nếu thêm) **cần sửa firmware CPU**: tăng `DOsize`, gửi `SW03`/`SW04` (index 29/30) tới bo ID mới
   (đề xuất 5). ID các bo con có thể đổi theo số bo. Chưa sửa thì 32/54/43/44XP1 không điều khiển được (P10–P12, P14, P16,
   P21 cần chúng). Muốn khóa các bài này: đặt `matrix_boards[1].status = "unsupported"`.

Bo MUX
3. Word `MUX` chọn 2 kênh thế nào (giả định byte thấp = MUX1, byte cao = MUX2), hai đầu ra vào ADC nào (giả định MUX1 →
   `ADC3`), kênh nào hở hết.
4. Kênh 31 (`Mux1.32` = `0x0000`) có thật sự hở hết không (đang dùng làm an toàn, `safe_state.MUX = 0x1F1F`).
5. Bo MUX nhận số kênh 0–31 hay mẫu rơ-le (đang giả định số kênh, bo tự tra `Mux_Decoder`). Mã HMI của CPU đặt `MUX`
   bit 1 = 2, tức chọn kênh 2 khi `Mode ≠ 1` (vô hại vì chỉ là đo).

Đo lường
6. Kênh ADC và hệ số module đo dòng/áp AC/DC (giả định 1 V/A, 0,1 V/V, qua MUX1 kênh 13–17). Module áp AC phải ra DC tỉ lệ RMS.
7. `ADC3` ±12 V, bước 0,01 V cho chân nhỏ 34/37/48XP1 (0,1–0,45 V, dung sai ±0,05 V): sát; người dùng chấp nhận một lần đọc.

Kích thích
8. DAC: giả định tầng có trừ 1,62 V, `V_XP1 = −DAC_val × 1,55 mV`. Đo bảng 5 điểm (`DAC_val` −1000…1000) rồi sửa
   `stm32_io.dac`; offset vài mV là lớn so với 0,02 V của P04.
9. `DOUT` bit 0–4 cần tầng driver/rơ-le cho 4/12/13/15/23XP1.
10. 43/44XP1 đang dùng chung một nguồn xung (đầu vào 4 của matrix 2); chưa rõ hai chân cần cùng pha, ngược pha hay hai nguồn.

Nguồn
11. `Power` bit 1/2/4/6 (đang gán AC 22 V, +27, −15, −12 V) bị nút HMI bật/tắt khi `Mode ≠ 1`. Bit 7–9 để trống vì bị ép bật.
    Kiểm trên mạch hoặc sửa FW (mặc định an toàn khi khởi động).

Firmware CPU (người dùng cho phép sửa sau, chưa sửa; đề xuất ở STM32_MODBUS_PC mục 9.9)
12. - FW-01 chu kỳ vòng lặp: đo bằng bài tự kiểm tra **D02**; `di_update_ms` đã nâng 100 → 150 ms, `break_ms` 150 ms, ngưỡng
      D02 ≤ 75 ms (= `di_update_ms`/2). Đổi một số thì đổi cả ba và `mock.json` `stm32_timing.loop_ms`.
    - FW-03: reset/`Mode ≠ 1` → HMI tự bật bit (mục 11 và bo matrix ở mục 1); PC không phát hiện được MCU reset.
    - FW-04: `Error_M` (lỗi bo con) không báo lên PC; ACK không chứng minh rơ-le đã đóng.
    - FW-05: firmware nhận tới 128 thanh ghi trong khi mảng có 32 → ghi ngoài vùng đè RAM. PC tự chặn.
    - FW-06: `Plan = 2`; `Plan = 0` cấu hình lại GPIO mỗi vòng.
    - FW-07: không có watchdog khi mất PC; người dùng chấp nhận, dùng dừng khẩn/atomat/cầu chì phần cứng.
    - `main.c:464` ghi bit 31 vào biến 16 bit (không tác dụng).

Bài kiểm tra (giá trị tạm do người dùng chỉ định 2026-11-18, ghi ở `basis` của từng check)
13. NG-03 áp 22 ± 2 V; P12/P17 dung sai thiếu = ±0,2 V; P20 kiểm trị tuyệt đối; P22–P24 dấu tạm (50XP1 dương, 49XP1 âm);
    NG-07 đo dòng khởi động tại 1 s; mỗi bước chờ 250 ms.
14. Giữ đúng tài liệu nhưng còn nghi vấn: P16 đo 26XP1 (P14 dùng 25XP1), P18 −0,3 V, P23 "không có CX3" nhưng vẫn cấp 5 V.

## Tiếp theo
- Đi dây theo `docs/STM32_MODBUS_PC.md` mục 9.10; kiểm 14 điểm ở mục trên, đổi `verified` từng mục đã đo.
- Sửa firmware CPU cho bo matrix 2 (`SW03`/`SW04`) và thống nhất cách chọn MUX 2 kênh (mục 9.9).
- Ghép RS485, chạy tự kiểm tra D01/D02 trên mạch, chỉnh `di_update_ms`/`break_ms`/ngưỡng D02 theo chu kỳ đo được.
- Đo hiệu chuẩn DAC 5 điểm; xác nhận dấu P22–P24 và các dung sai tạm.
- Bổ sung bài tự kiểm tra (D03 ADC…) khi người dùng yêu cầu.
- Thiết kế đường chạy bài trên mạch thật (điều kiện: `docs/STM32_MODBUS_PC.md` mục 10).

## Vấn đề còn mở
- File chưa xóa, chờ người dùng xem xét:
  - `tests/preview_protocol.py`: preview giao thức A45 v1 cũ, vẫn chạy được.
  - `Giao diện kiểm tra tự động neon xanh.png`: bản thiết kế giao diện tham chiếu.
  - `cmd`, `git_daily.ps1`, `git_daily.sh`: tiện ích Git cá nhân, chưa rõ còn dùng không.
  - `captures/*.png`: ảnh đối chiếu preview.
- `docs/TECHNICAL_REVIEW.md` không còn trên đĩa từ trước; không tự khôi phục.
- Firmware bo CPU đã đối chiếu ngày 2026-11-18 tại `D:\project\2026_DT_Chinh\Program\CPUv1.0`; **ngày 2026-11-19 thư mục
  này không còn trên máy** (có thể đã chuyển). Firmware và sơ đồ các bo con chưa có.
- `tests/preview_main.py`: thêm `--state manual` (chụp hộp thoại nhập tay); các trạng thái khác tự bỏ trống nhập tay.
- Orchestrator: ngân sách mềm trong `.agent-orchestrator/config.json` (Codex 160k, Antigravity 120k/ngày, trần 30k/60k mỗi
  việc) nhỏ so với mức dùng thật (Codex 40–150k token cho một việc nhỏ). Người dùng quyết định có nâng không.
- Worktree tạm `../GUI-wt-fwreview` (detached, chỉ có file task) có thể xóa bằng `git worktree remove`.
- `tests/preview_main.py --scenario` vẫn liệt kê `stale`/`protection`; với adapter stm32 backend sẽ từ chối.
- Khi đang tạm dừng, màn hình chẩn đoán hai mảng vẫn bị khóa (backend coi là đang bận).
- Nút "Tạm dừng" của đồ thị demo trùng tên với nút Tạm dừng quy trình; cân nhắc đổi tên.
- Ví dụ CRC trong `docs/PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md` sai (giữ nguyên file nguồn).
  - Khung đúng ghi ở `docs/STM32_MODBUS_PC.md` mục 11.
  - Thêm: FC03 bo HMI `04 03 00 00 00 05` có CRC đúng là `85 9C`, không phải `84 5C`.
- Hai backend cùng một thư mục lưu có thể xung đột ghi (Windows "Access is denied") khi
  phiên còn đang lưu; thực tế chỉ chạy một ứng dụng, test đã tách cho đúng cách dùng.

## Kiểm chứng gần nhất
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
