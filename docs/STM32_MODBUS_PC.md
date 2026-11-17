# Giao tiếp PC ↔ STM32 (Modbus RTU)

Tài liệu **duy nhất** về giao tiếp phần cứng: kết nối serial, hai mảng thanh ghi
của STM32 CPUv1.0, cách giao diện chẩn đoán và bộ chạy bài dùng chúng, các quy
tắc an toàn giao dịch. Phụ lục A ghi lại giao thức A45 v1 cũ (không dùng cho MCU).

- Nguồn bản đồ thanh ghi: [PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md](PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md)
  (phân tích từ mã firmware của giá thử trước; giá thử mới dùng lại phần cứng này).
  Mã nguồn C chưa có trên máy; chưa đối chiếu trực tiếp firmware.
- Ánh xạ tín hiệu bài đo ↔ thanh ghi: `configs/a45/hardware.json` → `stm32_io`
  (schema: [CONFIGURATION.md](CONFIGURATION.md#hardwarejson)).
- Điểm phần cứng chưa đáp ứng bài đo 1101K: `PROGRESS.md`, mục "Rà soát 1101K ↔ CPUv1.0".

> Hiện trạng (2026-11-18): đọc/ghi chẩn đoán trên COM thật đã có; **bộ chạy bài
> chỉ chạy với simulator**, `production_ready=false`; chưa thử trên mạch thật.

## 1. Đường truyền và cấu hình serial

| Mục | Giá trị |
|---|---|
| Vai trò | PC = Modbus RTU **Master**; **một** STM32 CPUv1.0 = Slave (USART2). MCU tự điều phối các bo SW/MUX/RelayPower/HMI phía dưới qua USART1; PC không giao tiếp trực tiếp với chúng |
| Vật lý | RS485 hai dây (PD5 TX, PD6 RX, PD7 điều khiển hướng). Cần bộ chuyển USB–RS485; không nối USB–UART TTL trực tiếp vào A/B |
| Mặc định | Slave ID **9**, **115200** baud, **8N1**, không flow control (đổi được trên UI) |
| Timeout | 1000 ms mặc định (chỉnh 100–10000 ms trong Chi tiết); `setNumberOfRetries(0)` |
| Khung/CRC | Qt `QModbusRtuSerialClient` đóng khung RTU, CRC16 Modbus, khoảng lặng frame |

Một `SerialConnection` (`src/communication.py`) sở hữu COM; trạng thái:
`disconnected → connecting → open`, lỗi mở cổng/rút USB → `error`.
**Mở COM thành công chỉ xác nhận cổng mở**; FC03 hợp lệ mới xác nhận slave trả lời.

## 2. Mã hàm và địa chỉ

| Thao tác | FC | Địa chỉ | Số word | Vùng MCU |
|---|---|---|---|---|
| Đọc toàn bộ dữ liệu | 03 | 1 | 29 | `mod_buf_to_read[1..29]` |
| Ghi một ô | 06 | 1…28 | 1 | `mod_buf_to_write[addr]` |
| Ghi một vùng liên tục | 16 (0x10) | 1…28 | không vượt cuối mảng | `mod_buf_to_write[...]` |

- Địa chỉ **zero-based = chỉ số mảng** (firmware cộng 1 rồi trừ 1, triệt tiêu). Không cộng 1, không dùng 40001.
- Index 0 là Null: PC không bao giờ ghi.
- Word truyền byte cao trước; CRC byte thấp trước (Qt xử lý).
- Firmware có FC17 nhưng PC chưa dùng. Ô "Đọc một lần" (FC03/FC04, địa chỉ tùy ý) chỉ phục vụ chẩn đoán thô.

## 3. Hai mảng độc lập

Ghi vào `mod_buf_to_write` (29 word, `Modbus_DO`); đọc từ `mod_buf_to_read`
(30 word, `Modbus_DI`). **Cùng địa chỉ không phải cùng dữ liệu**: ghi địa chỉ 7
đặt DAC, đọc địa chỉ 7 ra ADC0. Enum `WriteRegister`/`ReadRegister` trong
`src/common/stm32.py` là nơi duy nhất định nghĩa bản đồ.

| Index | Ghi (DO) | Đọc (DI) |
|---|---|---|
| 0 | Null | Null |
| 1 | **Mode** (1 = AutoComputer: MCU chạy theo PC) | Mode (firmware luôn trả 0) |
| 2 | Plan (0 SelfTest, 1 Test_EncoderPulse, 2 Test) | Plan |
| 3–5 | Block, Cabinet, Status | Block, Cabinet, Status |
| 6 | DisplayOut | DisplayIN |
| 7 | DAC_val (int16) | ADC0_val (int16/100 V, ±100 V) |
| 8 | DOUT (bit0–9) | ADC1_val (±50 V) |
| 9 | SW01 → bo Switch reg 0 | ADC2_val (±24 V) |
| 10 | SW02 → bo Switch reg 1 | ADC3_val (±12 V) |
| 11 | MUX → bo MUX | ADC4_val (±7,5 V) |
| 12 | Power → bo RelayPower (bit1 24 V, bit2 12 V, bit4 5 V, bit6 3,3 V, bit7–9 VDD1–3) | Ohm_val |
| 13 | DataO1: encoder En/Dir/Period (tự xóa) | DIN (mức raw bit0–9) |
| 14 | DataO2: số xung encoder (tự xóa) | DataI1 encoder_count (int16) |
| 15 | DataO3: SSI En + byte | DataI2 ENCA_cnt |
| 16–17 | DataO4, DataO5 (dự phòng) | DataI3 ENCB_cnt, DataI4 encoder_num_pulse (int16) |
| 18 | CDT (cổng RS232/422, enable bit8, độ dài) | DataI5 SSI Ident |
| 19 | DataT0 | CDN (dự phòng) |
| 20–28 | DataT1…DataT9 | DataR0…DataR8 |
| 29 | — | DataR9 |

Điều kiện bắt buộc: **ghi Mode=1** thì MCU mới chép mảng ghi vào `Modbus_DO` để
thực thi; Mode ≠ 1 thì MCU chạy theo nút bấm mặt máy (HMI).

## 4. Biểu diễn và giải mã (`src/protocol.py`)

- Raw word 0…65535. `encode_int16`/`decode_int16` đổi số có dấu bù hai: ADC raw −567 → −5,67 V.
- DAC_val: công thức tài liệu `V_DAC(PA4) = 1,62 − DAC_val/1000 × 1,55` (giới hạn 0–3,3 V ≈ mã −1083…+1045). Chưa là hiệu chuẩn; hệ số tới chân XP1 đang giả định trong `stm32_io`.
- Ohm_val: 2 bit cao chọn Ω/kΩ/MΩ/quá thang; 14 bit thấp /100. `decode_stm32` trả Ω, quá thang trả `None` (không trả 0).
- DIN giữ mức raw (pull-up, kích mức thấp), không tự đảo.
- DataT/DataR: **byte thấp trước bên trong mỗi word** (khác thứ tự trên dây). Bytes `11 22 00 44` → words `0x2211, 0x4400`. Dùng `pack_data_t`/`unpack_data_r`. CDN chưa có nghĩa độ dài, luôn giữ đủ 20 byte.
- Encoder: `encode_encoder(period_ms, pulses)`, chu kỳ bội 4 ms, 4…16380 ms (≤ 250 Hz).

## 5. Quy tắc giao dịch và trạng thái

- **Một giao dịch tại một thời điểm**, I/O bất đồng bộ theo event loop Qt, không chặn GUI.
- **Không retry** ghi hay đọc. Timeout hoặc phản hồi không hợp lệ → đóng COM, phải kết nối lại (RTU không có transaction ID; tránh nhận nhầm frame muộn). Modbus exception được báo riêng.
- Ghi: FC06 kiểm tra echo địa chỉ + giá trị, FC16 kiểm tra địa chỉ + số lượng, qua `rawResult()` ([Qt: `result()` không hợp lệ với request ghi](https://doc.qt.io/qt-6/qmodbusreply.html#result)). **ACK chỉ là biên nhận**, không xác nhận đầu ra vật lý; mất ACK thì kết quả là chưa biết, không gửi lại.
- Đọc: chỉ cập nhật mảng đọc sau FC03 hợp lệ (đúng slave, địa chỉ 1, 29 word). Dữ liệu đọc hết hiệu lực khi lỗi, ngắt, đổi nguồn/Slave ID hoặc quá 2000 ms (hạn hiển thị phía PC; MCU không có timestamp/sample counter nên không chứng minh được tuổi ADC hay tính nguyên tử).
- Không tự ghi khi mở COM, đổi nguồn, kết nối lại hay mở lại ứng dụng; không ghi cả mảng zero; không gửi lại lệnh encoder.
- Hiện **không có polling**. Nếu thêm: chỉ FC03, bỏ lượt khi đang có giao dịch, dừng khi ngắt/đóng; không poll bằng cách ghi mảng DO.
- Chẩn đoán và bộ chạy bài dùng chung một kênh: mỗi request mang nhãn `diag`/`bench`; khi bộ chạy bài đang chạy, thao tác chẩn đoán bị từ chối.
- Nút Dừng qua Modbus **không thay thế** dừng khẩn/bảo vệ phần cứng.

## 6. Sử dụng trên giao diện (chẩn đoán)

1. Thanh Kết nối: chọn **Modbus RTU** (hoặc **UART** để mở cổng serial thuần), COM, baudrate → **Kết nối**. Quét COM không mở cổng.
2. **8N1 · Chi tiết**: chỉnh data bits/parity/stop bits/timeout trước khi nối; **Đọc một lần** FC03/FC04 theo Slave ID, địa chỉ zero-based thập phân, số thanh ghi. UART hiển thị byte nhận được dạng hex.
3. **Hai mảng STM32 · Giả lập / COM thật** (`src/ui/widgets/stm32_registers.py`):
   - Mặc định **GIẢ LẬP**, không cần COM. Để nối mạch: mở COM Modbus RTU, bỏ chọn giả lập, chọn Slave ID, **đọc FC03 trước**.
   - Sửa ô chỉ sửa **bản nháp**; ô chưa nhập không bao giờ được gửi. Chọn vùng rồi gửi (FC06/16); giá trị được chụp lúc gửi.
   - Đổi nguồn giả lập/thật **không tự gửi** bản nháp. Khi bộ chạy bài chạy, bảng DI hiển thị lần đọc mới nhất của nó (chỉ xem).
4. **Ngắt** luôn hủy giao dịch đang chờ và giải phóng cổng.

Ví dụ API (trong event loop Qt, gọi giao dịch kế khi giao dịch trước xong):

```python
from src.common.stm32 import WriteRegister as WO
backend.stage_stm32(WO.Mode, [1, 2])                      # chỉ sửa bản nháp
backend.request_stm32(simulation=True, slave=9)           # FC03
backend.request_stm32(simulation=True, slave=9, address=1, count=2)  # FC16 Mode+Plan
```

## 7. Bộ chạy bài qua hai mảng (`hardware.adapter = "stm32"`)

Bộ tuần tự `Device.bench_*` (`src/device.py`) chạy từng giao dịch một, không retry:

```text
Kết nối mô phỏng → FC03 (không ghi gì)
prepare          → FC03 → ghi safe_state đầy đủ (Mode=1, Plan=2 trước; mọi
                   nguồn/định tuyến/MUX/DAC tắt) → ghi trình tự chuẩn bị
apply (mỗi bước) → chỉ ghi các word khác ảnh DO đã ACK (cộng dồn trong bài)
chờ ổn định      → wait_ms (×N chỉ trong mô phỏng)
measure          → mỗi tín hiệu đo: ghi MUX = mã kênh → chờ mux_settle_ms
                   → FC03 → word × scale → so nominal ± tolerance
finish           → cleanup → safe_state (dừng tay cũng đi qua bước này)
```

- Ánh xạ `Stm32IoMap` đọc từ `stm32_io`: output kiểu `bit` (rơ-le/tiếp điểm) hoặc `analog` (DAC + bit định tuyến); input kiểu `adc` (thanh ghi + mã MUX) hoặc `link` (= FC03 hợp lệ).
- Bộ chạy bài chỉ được ghi `BENCH_WRITABLE`: Mode, Plan, Block, Cabinet, Status, DisplayOut, DAC_val, DOUT, SW01, SW02, MUX, Power, DataO4, DataO5. **Không bao giờ** ghi DataO1/DataO2, DataO3, CDT, DataT hoặc index 0.
- ACK được lưu vào `attempt.transactions` với ghi chú "chưa xác nhận đầu ra vật lý". PASS/FAIL chỉ đến từ số đo FC03 sau thời gian ổn định.
- Lỗi/timeout giữa chừng → ERROR; ảnh DO coi là **chưa biết**; không gửi lại, không tự ghi safe_state sau lỗi.
- Một DAC: hai mức analog khác nhau cùng lúc bị validator từ chối; cùng mức (0 V vào 40/41/42XP1) được phép.
- Mục `unsupported` (xung 10 kHz, đo tần số, fault…) → bài BLOCKED trước khi gửi bất kỳ lệnh nào.
- Tạm dừng: chuỗi đang chạy được thay bằng finish (giao dịch đã gửi vẫn hoàn tất trước) → safe_state; lần chạy ghi PAUSED; tiếp tục chạy lại bài từ prepare. Trong lúc tạm dừng không gửi gì xuống MCU.
- CPUv1.0 không có cờ sẵn sàng/bảo vệ: "Sẵn sàng" = FC03 hợp lệ; "Bảo vệ" hiển thị "Chưa biết".
- Chạy mạch thật chưa có: runner luôn chạy với simulator.

## 8. Simulator (`src/simulator.py` → `Stm32Simulator`)

- Hai vùng nhớ độc lập; Mode DI luôn 0; DataO1/DataO2 tự xóa khi Mode DO = 1 (như firmware).
- Khi chưa chọn kênh MUX: số đo cố định độc lập với lệnh (phục vụ màn hình chẩn đoán).
- Khi bộ chạy bài chọn kênh MUX: ADC trả phản hồi demo từ `mock.json` → `stm32_cases`, theo **kích thích đọc ngược từ DO đã ghi** (Mode ≠ 1 thì coi như không có kích thích). Sai bit/định tuyến → sai số đo → FAIL. `after_ms` mô phỏng đáp ứng theo thời gian.
- Kịch bản lỗi cho adapter stm32: `fail`, `slow`, `timeout` (khi apply), `stop_timeout` (khi finish), `disconnect` (khi đo). `stale`/`protection` không áp dụng.
- **Không mô phỏng**: tín hiệu điện, timing RTU, vòng quét USART1, dạng sóng encoder, race xóa RevData.

## 9. Lưu ý firmware CPUv1.0 và đề xuất bổ sung

Hành vi cần giữ khi dùng CPUv1.0:
- Plan=0 gọi SelfTest/cấu hình lại GPIO: chọn có chủ đích, không mặc định.
- CDT bit8 bật làm MCU phát RS232/RS422 **lặp mỗi vòng quét** và xóa RevData; xóa bit8 để dừng. Payload ≤ 20 byte. SSI/encoder và DOUT/UART dùng chung một số chân.
- Encoder DataO1/DataO2 là lệnh tự xóa: không gửi định kỳ, không retry.

Đề xuất bổ sung firmware (chưa gán địa chỉ, cần thống nhất với phía MCU trước):
version/map ID, boot ID, sample counter/timestamp, command ID với trạng thái
accepted/completed/error, cờ ready/fault/interlock, chiều dài RX, chụp RX
nguyên tử, watchdog khi mất PC, khả năng phát xung ≥ 10 kHz và đo tần số.

## 10. Điều kiện trước khi chạy bài trên mạch thật

1. Chốt ánh xạ `stm32_io` (bit, kênh, hệ số, MUX) và các điểm thiếu của bài đo; mục nào đã đo kiểm mới đổi `status` thành `verified`.
2. Chốt giới hạn điện, liên động, watchdog, trình tự cấp/ngắt nguồn và trình tự dừng.
3. Ghép RS485, đọc FC03 bằng màn hình hai mảng, đối chiếu số đo; thử mất cáp/timeout; ghi từng vùng có chủ đích.
4. Thiết kế đường chạy thật (chọn COM, xác nhận người vận hành, khóa an toàn) với test tương ứng; không bật bằng cách bỏ validator hoặc đổi một cờ cấu hình.

## 11. Ví dụ khung và hiệu chỉnh CRC

CRC16/Modbus (init FFFF, poly A001, byte thấp trước) tính lại cho thấy ba ví dụ
trong tài liệu phân tích có CRC sai. Khung đúng:

```text
FC03 đọc DI 1–29        : 09 03 00 01 00 1D D5 4B
FC06 ghi Mode=1         : 09 06 00 01 00 01 18 82
FC16 ACK start 1, n=28  : 09 10 00 01 00 1C 91 48
```

PC để Qt sinh CRC; không dùng chuỗi hard-code để giao tiếp.

## 12. Kiểm thử

```powershell
conda run -n qt_env python -m tests.preview_stm32                    # hai mảng, giả lập
conda run -n qt_env python -B -m unittest tests.test_stm32_modbus -v  # chẩn đoán, ACK, timeout
conda run -n qt_env python -B -m unittest tests.test_stm32_bench -v   # ánh xạ, simulator, bộ chạy bài
conda run -n qt_env python -B -m unittest tests.test_serial_connection -v
```

Test tự động không mở COM thật.

## Phụ lục A. Giao thức A45 v1 cũ (không dùng cho MCU)

Đề xuất của dự án trước khi có tài liệu CPUv1.0. **Không yêu cầu firmware hiện
tại thực hiện**, không bọc vào giao dịch STM32. Còn tồn tại vì:
- adapter `mock` của bộ chạy bài (cấu hình thứ hai `alternative_profile` trong `tests/test_bench.py`);
- validator vẫn bắt buộc `hardware.wire_signals` liệt kê mọi tín hiệu (1–80 kênh, ID duy nhất);
- `SerialConnection.exchange_frame()` và preview `tests.preview_protocol`.

Tóm tắt (chi tiết là mã: `src/common/wire.py`, `WireCodec` trong `src/protocol.py`,
`SimulatedController` trong `src/simulator.py`, test `tests/test_wire_protocol.py`):
- Khung: `A5 5A | version 01 | node | opcode | flags | session u32 | sequence u32 | length u16 | payload | CRC-16/CCITT-FALSE`, big-endian, tối đa 1042 byte.
- Lệnh: HELLO 0x01, SNAPSHOT 0x02, PREPARE 0x10, APPLY 0x11, FINISH 0x12; lỗi flags=03 + mã u16.
- Qua Modbus: COMMIT 0x0FFF, request mailbox 0x1000, response mailbox 0x2000 (522 thanh ghi mỗi vùng).

Bản đầy đủ cũ (`COMMUNICATION_PROTOCOL.md`, `MODBUS_CONTRACT.md`) đã gộp vào tài
liệu này ngày 2026-11-18; bản gốc còn trong
`.backup/GUI_2026-11-18_00-15-14_UTC+07_before-docs-consolidation.zip`.
Chỉ loại bỏ hẳn phần A45 v1 khi đã thay thế adapter mock và các test liên quan.
