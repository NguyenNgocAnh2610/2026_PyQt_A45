# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**`AGENTS.md` là bộ quy tắc bắt buộc của project** (kiến trúc, an toàn giao tiếp, backup, dọn file, quy trình AI sửa mã). Đọc nó và `PROGRESS.md` (nhật ký/hiện trạng duy nhất) trước khi sửa. Mỗi đợt sửa mã phải cập nhật `PROGRESS.md`. Thay đổi lớn/rủi ro: tạo backup ZIP toàn project vào `.backup/` và kiểm tra trước khi sửa (chi tiết trong AGENTS.md). Tài liệu và UI viết tiếng Việt.

## Lệnh thường dùng

Luôn dùng Conda env `qt_env` (không dùng Python hệ thống/base, không tạo env mới).

```powershell
conda run -n qt_env python main.py                                  # Login (demo admin/123456) → MainWindow
conda run -n qt_env python main.py --profile configs/a45/system.json
conda run -n qt_env python -B -m unittest discover -s tests         # toàn bộ test
conda run -n qt_env python -B -m unittest tests.test_stm32_bench -v # một module
conda run -n qt_env python -B -m unittest tests.test_stm32_bench.Stm32RunnerTests.test_p02_writes_power_then_reads_current_and_returns_safe
conda run -n qt_env python -m tests.preview_main --state finished --capture <file.png>  # preview + chụp ảnh
conda run -n qt_env python -m tests.preview_stm32                   # màn hình hai mảng STM32, giả lập
conda run -n qt_env python -m tests.preview_widgets                 # gallery widget/QSS
conda run -n qt_env python -m tests.preview_main --state modbus     # trang Test Modbus trên COM ảo
```

- Không có build, formatter hay linter. Test dùng `unittest` + `PySide6.QtTest`, không mở COM thật.
- Mẹo với `conda run`: không đưa xuống dòng vào `python -c` (lỗi), hãy ghi script ra file. Output tiếng Việt cần `PYTHONIOENCODING=utf-8` nếu không sẽ lỗi cp1252. Script ngoài project cần `PYTHONPATH=.` để import `src`.
- Dùng `-B` để không sinh `__pycache__`; xóa cache sau đợt làm việc (quy tắc dọn file).

## Kiến trúc tổng thể

Ứng dụng giá thử dùng chung cho nhiều giá thử, điều khiển bằng **profile JSON** (`configs/<gia_thu>/`). A45 / khối 1101K-10 là cấu hình đầu tiên. Không rẽ nhánh theo tên `A45`/`1101K`/ID bài trong UI hay bộ chạy bài.

**Profile** (`src/common/profiles.py` nạp + validate tập trung): `system.json` (tín hiệu, `status_signals`, bài tự kiểm tra) tham chiếu `1101k.json` (24 bài/bước, `sequences` chuẩn bị/kết thúc, `issues`), `hardware.json` (`adapter`, `stm32_io`), `mock.json` (dữ liệu mô phỏng). Validator chạy thử toàn bộ chuỗi thao tác của mọi bài khi nạp.

**Tầng** (UI không bao giờ chạm I/O):
- `src/ui/` (Widgets + `qml/SignalDashboard.qml`) → chỉ gọi `Backend`.
- `src/backend.py`: nguồn trạng thái duy nhất (QObject/Signal) và **máy trạng thái chạy bài** điều khiển bằng `_tick` (timer 50 ms): `prepare → apply → settling → sampling → evaluate → finish`, với token/epoch để bỏ phản hồi trễ. `pause()` chạy finish (về an toàn) rồi vào phase `paused`, lần chạy ghi `PAUSED` (không tính verdict/progress), `resume()` chạy lại bài từ đầu. `measurement_history` giữ giá trị cuối cho dashboard (không dùng đánh giá). `evaluate()` là hàm thuần tính PASS/FAIL/ERROR/"Chưa đánh giá".
- `src/device.py`: thao tác nghiệp vụ. Có bộ tuần tự `bench_*` (một giao dịch tại một thời điểm, không retry) và đường chẩn đoán; mỗi request mang nhãn chủ `diag`/`bench`.
- `src/protocol.py`: codec thuần. `Stm32IoMap` ánh xạ tín hiệu logic ↔ word thanh ghi; cũng chứa codec khung A45 v1 cũ.
- `src/communication.py`: `SerialConnection` (Qt `QModbusRtuSerialClient`, sở hữu COM, timeout) và hàng đợi `Communication` của đường A45 v1 cũ.
- `src/simulator.py`: `Stm32Simulator` (mức thanh ghi, mô phỏng vòng lặp chính CPU `loop_ms`), `Stm32RtuSlave` (khung RTU byte như FreeModbus) và `SimulatedController` (A45 v1 cũ).
- `src/virtual_port.py`: **mô phỏng = cổng COM ảo**. `VirtualRtuClient` thay `QModbusRtuSerialClient` trong một `SerialConnection` thứ hai (`Device.virtual_connection`). Bộ chạy bài và chẩn đoán đi cùng một đường code cho cả mô phỏng và COM thật; lỗi mô phỏng được tạo trên đường truyền (`VirtualLine`). Đừng thêm nhánh "simulation" đi tắt trong `Device`.
- `src/storage.py`: checkpoint phiên JSON nguyên tử trong worker.

**Hai adapter của bộ chạy bài** (`hardware.adapter`):
- `stm32` (profile A45): ghi/đọc hai mảng STM32 qua Modbus RTU FC03/06/16, 115200 8N1. Bản đồ theo firmware chọn bằng `hardware.cpu_map` (`CPU_MAPS` trong `src/common/stm32.py`): A45 = **CPUv1.1** (slave 11 = 8 + công tắc ID, DO 31 word với `Matrix0/1` ở 18–19 và `CDT` ở 20, DI 43 word); CPUv1.0 (slave 9, DO 29 / DI 30) là mặc định cho profile không khai báo. DO và DI **độc lập**: cùng địa chỉ không phải đọc lại giá trị đã ghi. Địa chỉ zero-based = chỉ số mảng. Đừng dùng `WriteRegister`/`ReadRegister` (chỉ là CPUv1.0) cho code theo profile; dùng `cpu_map.write_index()`.
  - Mở COM thật ở chế độ Modbus RTU → `bench_connect(simulation=False)` (FC03) → `READY_REAL`. Tự kiểm tra chạy ngay; bài đo bị chặn bởi `real_run_blockers()` (ánh xạ chưa `verified`, D02 chưa đạt) và cần `start(confirm_real=True)`. Thời gian chờ thật không chia `time_scale`.
  - PC chỉ nói chuyện với CPU: `Backend.check_cpu_slave()` từ chối mọi request stm32 tới slave khác `stm32_io.slave`; bo con chỉ điều khiển bằng thanh ghi CPU (`CpuMap.forwards` ghi CPU gửi tiếp tới bo nào).
  - Trang Test Modbus (`src/ui/widgets/modbus_test.py`) gọi `Backend.tool_*`: hàng đợi ghi một giao dịch/lần, dùng chung `Stm32IoMap` (liên động, ngắt trước đóng sau, MUX < 32), lỗi → ảnh DO "chưa biết".
  - Mỗi bài: FC03 → safe_state (Mode=1 trước) → chuẩn bị → ghi diff DO từng bước (vừa nhả vừa đóng rơ-le thì ngắt trước, chờ `break_ms`, rồi đóng) → chờ → ghi MUX (số kênh) → FC03 → giải mã → so dung sai → safe_state. Input `manual` hỏi người vận hành (`Backend.manual_request`/`submit_manual`, bỏ trống = giá trị chuẩn có nhãn "mặc định, chưa đo").
  - Ánh xạ A45 là bảng phân bổ để đi dây (`docs/STM32_MODBUS_PC.md` mục 9.10): rơ-le nguồn RLPW là output `bit`, mọi chân XP1 (cả lệnh mức) đi qua 4 bo RLMatrix (`matrix_boards`, output `pin`). Bo ID 6 dùng `Matrix0/1`; bo ID 7–9 dùng `Matrix2_0…Matrix4_1` (index 31–36) là **đề xuất sửa firmware**, khai báo trong `extra_write_registers`. Không gán output vào `hmi_forced_bits`. Không có bo switch.
  - Runner không bao giờ ghi DataO1/DataO2 (encoder tự xóa), DataO3, CDT/DataT, index 0 (`BENCH_WRITABLE` + thanh ghi mở rộng của profile).
  - ACK chỉ là biên nhận, không xác nhận đầu ra. Lỗi giữa chừng → ERROR, ảnh DO thành "chưa biết", không tự ghi lại.
  - Tín hiệu `unsupported` trong `stm32_io` làm bài BLOCKED trước khi gửi gì.
  - Simulator trả số đo theo kích thích đọc ngược từ DO đã ghi (`mock.json` `stm32_cases`), không theo mã bài.
  - Đo chỉ đọc FC03 khi đã qua `stm32_io.di_update_ms + mux_settle_ms` kể từ ACK ghi cuối (MCU cần ~2 vòng lặp để DI phản ánh lệnh).
- `mock`: khung A45 v1 cũ (mailbox, `wire_signals`, `cases` theo `test/step`). Chỉ còn cho `alternative_profile` trong `tests/test_bench.py`, là cấu hình thứ hai bắt buộc kiểm tra hồi quy khi sửa lõi.

## Hiện trạng cần nhớ
- Bộ chạy bài chạy trên COM ảo và COM thật có cổng chặn; `production_ready=false`. Mọi mục trong `stm32_io` là `assumed` nên trên mạch thật hiện chỉ tự kiểm tra chạy được. Các điểm phải kiểm khi lên mạch thật nằm trong `PROGRESS.md`, mục "Cần kiểm khi lên phần cứng thật".
- Chỉ đổi `status` thành `verified` sau khi đã đo kiểm thật. Không tự đổi giao thức/địa chỉ/baudrate, không tự điền dung sai để có PASS.
- Tài liệu (mỗi nội dung chỉ ở một nơi; gốc repo chỉ có README/AGENTS/CLAUDE/PROGRESS):
  - `docs/LUONG_CODE_VA_MODBUS.md`: luồng code tổng và chuỗi hàm truyền/nhận Modbus, log/debug, tùy biến khung (cho người tự sửa code; cập nhật khi đổi tên/luồng hàm).
  - `docs/STM32_MODBUS_PC.md`: giao tiếp Modbus duy nhất, phụ lục A là A45 v1 cũ.
  - `docs/CONFIGURATION.md`: schema.
  - `docs/CHUYEN_GIA_THU_MOI.md`: quy trình chuyển giá thử; người dùng muốn tài liệu này được bổ sung dần mỗi khi profile/adapter/tiêu chí thay đổi.
  - Mã nguồn firmware (chỉ đọc, ngoài repo): `D:\project\2026_DT_Chinh\ref\ref_AHung\A34_Phao37\Program\` → `CPUv1.0`, `CPUv1.1 For DK_QDT` (đang dùng), `RLMatrixv1.0`, `RLMUXv1.0`, `RLPWv1.0`; phân tích ở `docs/STM32_MODBUS_PC.md` mục 3.1, 9, 9.11; đề xuất sửa firmware mục 9.9.
  - Tài liệu nguồn giữ nguyên nội dung: `docs/PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md` (firmware CPUv1.0 của giá thử cũ, để tham khảo) và `docs/BAI_KIEM_TRA_1101K.md` (24 bài đo thật).
- Style Qt Widgets: `assets/styles/common.qss` nạp ở cấp `QApplication` qua `src/common/styles.py`; QSS trang chỉ ghi đè phần riêng, chọn bằng `objectName`/dynamic property.


## Multi-Agent Orchestration

Use the multi-agent-orchestrator skill (`.claude/skills/multi-agent-orchestrator`)
for programming tasks and also for non-code tasks (documentation, review,
analysis, research). Delegate only when it clearly saves effort; otherwise
Claude does the task directly and says briefly why.

Responsibilities:
- Claude is the primary orchestrator.
- SIMPLE tasks: Antigravity.
- MODERATE tasks: Codex.
- COMPLEX or CRITICAL tasks: Claude.
- Select models based on complexity and budget.
- Check token budget before delegation.
- Review and verify worker results.
- Follow existing AGENTS.md rules.
- Use PROGRESS.md as the sole progress journal.
- Do not automatically commit or push.
- Ask before high-risk or hardware operations.

Avoid unnecessary agent calls.
Prefer quality, consistency, and token efficiency.