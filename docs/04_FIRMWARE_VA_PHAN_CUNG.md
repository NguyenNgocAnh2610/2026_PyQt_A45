# Firmware CPU, bo con và phần cứng giá thử

Từ lệnh PC ghi vào thanh ghi CPU tới rơ-le, MUX, DAC, ADC: vòng lặp chính của CPU, bus nội bộ tới bo con, ngoại vi trên bo CPU, chế độ HMI, stack Modbus slave, cách điều khiển một đầu ra, đề xuất sửa firmware, bảng phân bổ bit A45 (để đi dây) và firmware các bo con.

- Khung truyền và bản đồ thanh ghi PC ↔ CPU: [02 Giao thức](02_GIAO_THUC_MODBUS.md).
- Mã nguồn firmware đã đối chiếu (chỉ đọc, ngoài repo): `D:\project\2026_DT_Chinh\ref\ref_AHung\A34_Phao37\Program\` → `CPUv1.0` (2026-11-18), `CPUv1.1 For DK_QDT` (đang dùng), `RLMatrixv1.0`, `RLMUXv1.0`, `RLPWv1.0` (2026-11-19).
- Mục 1–8 viết theo CPUv1.0; **CPUv1.1 giữ nguyên vòng lặp**, chỉ thêm gửi `Matrix[0..1]` tới bo matrix ID 6 (FC16) và 4 cổng UART nhận riêng ([02 Giao thức](02_GIAO_THUC_MODBUS.md) mục 3.1). Tham chiếu dạng `file:dòng` theo CPUv1.0.
- Firmware bo con đã đối chiếu (mục 11). Chặng cuối "rơ-le nào nối tới chân giắc nào" nằm trên sơ đồ mạch, không suy ra được từ mã.

## Mục lục

- [1. Bức tranh tổng thể](#1-bức-tranh-tổng-thể)
- [2. Vòng lặp chính (`main.c:207–341`) và thời gian](#2-vòng-lặp-chính-mainc207341-và-thời-gian)
- [3. Bus nội bộ USART1: CPU làm Master tới các bo con](#3-bus-nội-bộ-usart1-cpu-làm-master-tới-các-bo-con)
- [4. Ngoại vi trực tiếp trên bo CPU](#4-ngoại-vi-trực-tiếp-trên-bo-cpu)
- [5. `Mode ≠ 1` (mặt máy HMI) và khi MCU khởi động lại: lưu ý an toàn](#5-mode--1-mặt-máy-hmi-và-khi-mcu-khởi-động-lại-lưu-ý-an-toàn)
- [6. Stack Modbus slave (`MIddleware/Modbus_slave`)](#6-stack-modbus-slave-middlewaremodbus_slave)
- [7. Hướng dẫn: điều khiển một đầu ra rơ-le (ví dụ một nguồn cấp)](#7-hướng-dẫn-điều-khiển-một-đầu-ra-rơ-le-ví-dụ-một-nguồn-cấp)
- [8. Hành vi khác cần lưu ý](#8-hành-vi-khác-cần-lưu-ý)
- [9. Đề xuất sửa firmware](#9-đề-xuất-sửa-firmware)
- [10. Phân bổ bit giá thử A45 (giả định, để đi dây)](#10-phân-bổ-bit-giá-thử-a45-giả-định-để-đi-dây)
- [11. Firmware bo con (đã đối chiếu 2026-11-19)](#11-firmware-bo-con-đã-đối-chiếu-2026-11-19)

## 1. Bức tranh tổng thể

```text
PC ──FC06/FC16 (USART2, ID 9; A45: 11)──► mod_buf_to_write[]  (ngắt SysTick 1 ms: ghi ngay vào mảng, trả ACK ngay)
                                       │
                vòng lặp main(): nếu mod_buf_to_write[1] (Mode) == 1 → memcpy → Modbus_DO
                                       │
     ┌─ SW01  (index 9)  ──FC06──► SW_board         ID 1, reg 0 ─► rơ-le/tiếp điểm tín hiệu
     ├─ SW02  (index 10) ──FC06──► SW_board         ID 1, reg 1 ─► (bit → rơ-le do bo SW quyết định)
     ├─ MUX   (index 11) ──FC06──► MUX_board        ID 2, reg 0 ─► chọn điểm đo đưa về ADC của CPU
     ├─ Power (index 12) ──FC06──► RelayPower_board ID 3, reg 0 ─► rơ-le nguồn
     ├─ DAC_val (7) ─► DAC1 chân PA4 trên CPU (mức analog DUY NHẤT PC tạo ra)
     ├─ DOUT    (8) ─► 10 chân GPIO trên CPU
     └─ DataO1/2 (encoder), DataO3 (SSI), CDT + DataT (UART) ─► ngoại vi trên CPU
ADC 5 kênh + điện trở + DIN + encoder ─► Modbus_DI ─memcpy cuối vòng─► mod_buf_to_read ─FC03─► PC
```

Hiểu đúng ba loại tín hiệu PC ghi xuống:
- **Cấp nguồn / cấp tín hiệu dạng bit** (`Power`, `SW01`, `SW02`, `MUX`): CPU **không giải mã từng bit**. Nó chuyển **nguyên 16 bit** sang bo con bằng FC06 ở **mọi vòng lặp** (`main.c:246–261`). Bit nào đóng rơ-le nào là do firmware và mạch của bo con.
- **Tín hiệu analog** (`DAC_val`): chỉ có **một** DAC trên chân `PA4` của CPU. Giá thử A45 đưa DAC vào một đầu vào của bo matrix rơ-le, rồi đóng điểm giao tới chân `XP1` cần (kiểu `pin` trong `stm32_io`, mục 10). Các mức cố định (±3 V, 27 V, 5 V, đất, xung) lấy từ nguồn ngoài có sẵn qua rơ-le, không dùng DAC.
- **ADC là đầu vào đo, không phải đầu ra.** `ADC0…ADC4_val` là 5 kênh đo điện áp **của CPU**, mỗi kênh có dải cố định. Điểm nào trên khối được đưa vào ADC thì do giá trị `MUX` gửi xuống bo MUX quyết định. PC chỉ đọc ADC bằng FC03, không "tạo ADC".

## 2. Vòng lặp chính (`main.c:207–341`) và thời gian

| # | Việc | Mã | Thời gian (ước tính) |
|---|---|---|---|
| 1 | Đọc `Mode = mod_buf_to_write[1]`. Nếu `= 1`: chép **toàn bộ** 29 word sang `Modbus_DO`, rồi FC16 tới HMI (ID 4, reg 4 = 0, tắt LED) + `Delay(10)`. Nếu `≠ 1`: `HMI_processing()` (mục 5) | `main.c:212–224` | ~2 ms + 10 ms |
| 2 | FC06 → SW (ID 1) reg 0 = `SW01`; FC06 → SW reg 1 = `SW02`; `Delay(10)` | `main.c:246–248` | ~4 ms + 10 ms |
| 3 | FC06 → MUX (ID 2) reg 0 = `MUX`; `Delay(10)` | `main.c:253–254` | ~2 ms + 10 ms |
| 4 | FC06 → RelayPower (ID 3) reg 0 = `Power`; `Delay(10)` | `main.c:260–261` | ~2 ms + 10 ms |
| 5 | `Plan == 0` → `GPIO_Configuration()` **mỗi vòng**; `Plan == 1` → `Encoder_GPIO_Config()` mỗi vòng | `main.c:271–278` | |
| 6 | Nạp encoder từ `DataO1/DataO2`, tự xóa `mod_buf_to_write[13..14]` | `main.c:281–295` | |
| 7 | SSI: `En = DataO3 bit15`, byte = `bit0–7` | `main.c:297–305` | |
| 8 | `ADC_process()`: quy đổi 5 kênh áp, đo điện trở tự chuyển thang | `main.c:308`, `654–739` | 1–5 ms |
| 9 | `DAC_Out(1.62 − DAC_val/1000 × 1.55)` | `main.c:310` | |
| 10 | Đọc 10 DIN, xuất 10 DOUT (trừ chân đang dùng cho encoder/SSI) | `main.c:314–326` | |
| 11 | Chép `Modbus_DI` → `mod_buf_to_read` (đây là lúc PC thấy số đo mới) | `main.c:336` | |
| 12 | Nhận/phát UART ngoại vi | `main.c:338–339` | |

- **Chu kỳ bình thường ≈ 50–60 ms (ước tính, chưa đo)**: 4 × `Delay(10)` + 5 giao dịch nội bộ + ADC.
  - **Mỗi bo con không trả lời làm vòng lặp dài thêm 100 ms cho mỗi giao dịch** (timeout `t_timeout = 100`, `System_Register.h:5`). Ví dụ thiếu bo SW: +200 ms mỗi vòng.
  - Không có retry.
  - **CPUv1.1 trên giá thử A45** (`main.c:222–360`, Mode = 1). Mỗi vòng CPU làm master, gửi lần lượt và **chờ trả lời**
    (vòng `while` tới khi nhận đủ 8 byte hoặc quá `t_timeout`):

    | Khung | Bo | Lắp? | Thời gian |
    |---|---|---|---|
    | FC16 tắt LED | HMI ID 4 | không | 100 ms chờ + `Delay(10)` |
    | FC06 `SW01`, FC06 `SW02` | switch ID 1 | không | 2 × 100 ms chờ + `Delay(10)` |
    | FC16 `Matrix0/1` | RLMatrix ID 6 | có | ~3 ms + `Delay(10)` |
    | FC06 `MUX` | RLMUX ID 2 | có | ~2 ms + `Delay(10)` |
    | FC06 `Power` | RLPW ID 3 | có | ~2 ms + `Delay(10)` |
    | ADC, DAC, DIN/DOUT, UART ngoại vi | trong CPU | | vài ms |

    Ước tính **≈ 360–380 ms/vòng**, trong đó 300 ms là chờ 3 khung không ai trả lời. Sửa firmware bỏ gửi bo vắng
    (mục 9) → **≈ 60–70 ms**. Thêm bo matrix 2–4 có lắp: mỗi bo +~13 ms; có trong firmware mà không lắp: +110 ms.
    Bo có lắp nhưng sai ID / đứt dây A-B cũng tốn đủ 100 ms như bo vắng. Đây là ước tính từ mã nguồn; D02 cho số thật.
- **Yêu cầu từ PC được phục vụ trong ngắt**, độc lập với vòng lặp: `eMBPoll()` chạy trong `SysTick_Handler` mỗi 1 ms (`stm32f4xx_it.c:232`). ACK về gần như ngay, kể cả khi vòng lặp đang chờ bo con.
- **Hệ quả cho PC**:
  - Lệnh ghi được ACK có thể chờ tới gần một vòng lặp mới được chép; sau đó bo con mới nhận.
  - ADC đọc ở bước 8 và DI chép ở bước 11 của vòng lặp đó. Vì vậy số đo phản ánh lệnh mới sau **tối đa ~2 vòng** (≈ 120 ms nếu vòng 60 ms).
  - Bộ chạy bài chờ `di_update_ms + mux_settle_ms = 150 + 20 ms` kể từ ACK ghi cuối ([03 Luồng Modbus](03_LUONG_MODBUS_TRONG_CODE.md) mục 4; nâng từ 100 ms ngày 2026-11-18 cho có dư). **Phải đo chu kỳ vòng lặp thật** bằng bài tự kiểm tra D02 rồi chỉnh `di_update_ms`, `break_ms`, ngưỡng của D02 và `mock.json` → `stm32_timing.loop_ms` (đang giả định 50 ms).
- Rơ-le đóng ở bước 2–4, ADC đọc ở bước 8, cách khoảng 10–30 ms trong cùng vòng. Thời gian ổn định của khối sau khi cấp nguồn vẫn do `wait_ms` của từng bước bài đo.

## 3. Bus nội bộ USART1: CPU làm Master tới các bo con

| Bo con | ID | Khung CPU gửi **mỗi vòng** | Lấy từ | Ví dụ (CRC đúng) |
|---|---|---|---|---|
| `SW_board` | `0x01` | FC06 reg `0x0000` | `SW01` (index 9) | `SW01 = 0x0008` → `01 06 00 00 00 08 88 0C` |
| `SW_board` | `0x01` | FC06 reg `0x0001` | `SW02` (index 10) | `SW02 = 0` → `01 06 00 01 00 00 D8 0A` |
| `MUX_board` | `0x02` | FC06 reg `0x0000` | `MUX` (index 11) | `MUX = 14` → `02 06 00 00 00 0E 08 3D` |
| `RelayPower_board` | `0x03` | FC06 reg `0x0000` | `Power` (index 12) | `Power = 0x0002` → `03 06 00 00 00 02 09 E9` |
| `HMI_board` | `0x04` | Mode = 1: FC16 reg 4 = 0 (tắt LED). Mode ≠ 1: FC03 đọc 5 thanh ghi | — | `04 10 00 04 00 01 02 00 00 98 84` |

- Phần cứng: `USART1` `PA9` TX / `PA10` RX, chân hướng RS485 `PA8`, 115200 8N1 (`usart.c:44–45`, `main.h:38–39`). Hàm tự viết `MBMasterWriteRegister` / `…MultiRegister` / `…ReadHoldingRegister` (`main.c:742–924`) chạy kiểu **chặn**: gửi khung rồi chờ đủ 8 byte hoặc hết 100 ms.
- **Giá trị 16 bit được chuyển nguyên vẹn**, không đảo, không che bit. Khung được **gửi lại ở mọi vòng** dù giá trị không đổi (~17–20 lần/giây), nên bo con khởi động lại cũng nhận lại trạng thái sau ≤ 1 vòng.
- Kiểm tra phản hồi: chỉ so ID, FC và CRC; **không so địa chỉ/giá trị echo** (`main.c:801–817`). Bo con trả exception (5 byte) thì CPU chờ tới hết 100 ms.
- **Lỗi bo con không được báo lên PC**: kết quả lưu ở `Error_M[ID]` (`main.c:99`, `790–816`) nhưng không được dùng hay chép vào DI. Vì vậy ACK của CPU **không chứng minh rơ-le đã đóng**, PASS/FAIL phải dựa vào số đo.

## 4. Ngoại vi trực tiếp trên bo CPU

| Nhóm | Chi tiết (mã nguồn) |
|---|---|
| `DOUT` bit 0–9 | `PE5, PE6, PC13, PC14, PC3, PA0, PA1, PA2, PA3, PA5` (`gpio_all.h:14–52`). Bit 5–7 bị encoder chiếm khi đang phát xung; bit 1–3 bị SSI chiếm khi `SSI.En = 1` (`main.c:318–325`) |
| `DIN` bit 0–9 | `PE7, PE8, PE9, PE10, PE11, PE12, PE13, PE14, PE15, PB10` (`gpio_all.h:81–120`), pull-up, kích mức thấp |
| `DAC_val` | DAC1 `PA4`: `V = 1,62 − DAC_val/1000 × 1,55` (`main.c:310`), cập nhật mỗi vòng. Firmware **tự kẹp** mã DAC trong `0–4095` (`adc.c:135–145`), nên mã ngoài khoảng ≈ `−1083…+1045` bị bão hòa mà không báo lỗi. **`DAC_val = 0` cho 1,62 V tại PA4, không phải 0 V**; điện áp thật tại `XP1` phụ thuộc tầng khuếch đại sau PA4 (chưa đo) |
| ADC 5 kênh | ADC1 + DMA quét liên tục (`adc.c:77–82`). `ADC0` ch9 `PB1` ×62,5 (±100 V); `ADC1` ch8 `PB0` ×30,3 (±50 V); `ADC2` ch14 `PC4` ×14,5 (±24 V); `ADC3` ch15 `PC5` ×8,33 (±12 V); `ADC4` ch7 `PA7` ×4,55 (±7,5 V). `V = (offset − raw × gain) × hệ số`, gửi `int16 = V × 100`. Offset hiệu chỉnh cứng `1,63/1,64/1,635/1,62/1,65` (`main.c:661–677`). Mỗi vòng lấy 1 giá trị DMA mới nhất, **không lấy trung bình** |
| Điện trở | ch6 `PA6`, chuyển thang bằng `PE0–PE4`, mỗi bước `Delay(1)` (`main.c:679–739`) |

## 5. `Mode ≠ 1` (mặt máy HMI) và khi MCU khởi động lại: lưu ý an toàn

- Khi khởi động, firmware xóa `mod_buf_to_write` về 0 (`main.c:200–203`), tức `Mode = 0`. Lúc đó **`HMI_processing()` điều khiển** (`main.c:345–464`) và vẫn gửi xuống bo con ở mọi vòng:
  - `Power` bit 7–9 (VDD1–3) **luôn bật**; bit 1/2/4/6 (24/12/5/3,3 V) theo nút mặt máy;
  - `SW01` bit 12, 14 và `SW02` bit 0, 12 luôn bật; `SW01` bit 5–7 theo OUT1–3 hoặc encoder;
  - `MUX` bit 1 (R+) bật.
- Do đó **`safe_state` của PC chỉ giữ được khi `Mode = 1`**. Nếu PC ghi `Mode = 0`, hoặc MCU bị reset (sụt nguồn, nạp lại), giá thử chuyển sang trạng thái mặc định của HMI, **không phải tắt hết**.
- PC **không phát hiện được** việc MCU reset: `Mode` ở DI luôn 0, không có boot ID hay bộ đếm. Đề xuất firmware ở mục 9.
- Ý nghĩa bit `Power` trong tài liệu (bit1 24 V, bit2 12 V, bit4 5 V, bit6 3,3 V, bit7–9 VDD1–3) **chỉ đến từ mã HMI của CPU**. Rơ-le thật ứng với từng bit trên bo RelayPower của giá thử mới vẫn phải xác nhận.

## 6. Stack Modbus slave (`MIddleware/Modbus_slave`)

- Khởi tạo `eMBInit(MB_RTU, 9, …, 115200, MB_PAR_NONE)` (`main.c:169`), `USART2`, chân hướng `PD7` (`main.h:55–56`, `portserial.c:44–53`). T3.5 cố định 1,75 ms vì baud > 19200 (`mbrtu.c:101`).
- Địa chỉ trên khung = chỉ số mảng: `usRegAddress++` (`mbfuncholding.c:87/123/183`) rồi trừ `usRegHoldingStart = 1` (`port.c:72`).
- FC03 đọc `mod_buf_to_read`, FC06/FC16 ghi `mod_buf_to_write` (`port.c:65–98`). Firmware cũng bật FC17 (đọc DI + ghi DO trong một lần), FC01/05/15 (coil) và FC04. FC04 chỉ trả hằng `0x0304` (`port.c:39–60`), không có dữ liệu.
- **Giới hạn địa chỉ sai so với kích thước mảng**:
  - `REG_HOLDING_NREGS = 128` (`main.c:58–59`), trong khi `mod_buf_to_write` / `mod_buf_to_read` chỉ có **32** phần tử (`main.h:33–34`).
  - Vì vậy firmware **không trả exception** với địa chỉ 32–127: FC03 trả nội dung RAM lân cận, còn **FC06/FC16 ghi đè RAM khác của MCU**.
  - Exception 02 chỉ xảy ra khi `địa chỉ + số lượng > 128`. Exception 03 khi số lượng ngoài `1–125` (FC03) hoặc `1–120` (FC16).
  - Index 29–31 của mảng ghi có tồn tại nhưng không được chép sang `Modbus_DO` (`DOsize = 29`). Index 0 ghi được ở mức firmware.
- **Phần mềm PC tự chặn**: chỉ ghi/đọc trong bản đồ của profile (CPUv1.0: ghi 1–28, đọc 1–29; CPUv1.1: ghi 1–30, đọc 1–42) qua `stm32_write_words`, `make_read_unit`. Ngoại lệ: bộ chạy bài và công cụ Test Modbus được ghi index 31–36 vì profile A45 khai báo chúng là **đề xuất sửa firmware** (mục 9); mảng CPUv1.1 có 50 word nên không đè RAM. Slave trong COM ảo ([03 Luồng Modbus](03_LUONG_MODBUS_TRONG_CODE.md) mục 7) cố ý chặt hơn firmware (exception 02 ngoài vùng khai báo) để bắt lỗi phía PC.
- ACK được tạo ngay trong ngắt, nghĩa là mảng đã được ghi. Lệnh chỉ được thực thi ở vòng lặp kế tiếp (mục 2).

## 7. Hướng dẫn: điều khiển một đầu ra rơ-le (ví dụ một nguồn cấp)

1. **Xác định phần cứng** (không có trong mã CPU). Lập bảng: đầu ra nằm trên bo nào (RelayPower ID 3 / SW ID 1 / hay chân `DOUT` của CPU), **bit nào** của thanh ghi bo đó, mức `1` là đóng hay nhả, và tiếp điểm nối tới **chân giắc nào** (`XP1-…`). Nguồn: sơ đồ nguyên lý và firmware bo con.
2. **Tra chặng CPU** (cố định trong firmware):

   | Bo | Thanh ghi bo con | Index DO PC ghi | Tên |
   |---|---|---|---|
   | RelayPower (RLPW, ID 3) | reg 0 | 12 | `Power` |
   | SW (ID 1, không có trên A45) | reg 0 / reg 1 | 9 / 10 | `SW01` / `SW02` |
   | MUX (RLMUX, ID 2) | reg 0 | 11 | `MUX` |
   | RLMatrix ID 6 (chỉ CPUv1.1) | reg 0 / reg 1 | 18 / 19 | `Matrix0` / `Matrix1` |
   | Chân CPU | — | 8 | `DOUT` bit 0–9 |

3. **Khai báo phía PC** (không sửa code):
   - `system.json`: tín hiệu lệnh (`kind: "boolean"`, `source: "derived"`, đơn vị).
   - `hardware.json` → `stm32_io.outputs.<id>`: `{"kind": "bit", "register": "Power", "bit": n, "on_value": 1, "status": "assumed", "note": "rơ-le K?, chân XP?"}`. `safe_state` đã có `Power = 0`. Validator chặn bit trùng và thanh ghi bị cấm.
   - Bài đo dùng `{"signal": "<id>", "value": 1}` trong `actions`, hoặc trong `sequences` nếu là nguồn chung.
4. **Thử trên COM ảo**: chạy bài; trong **Hai mảng STM32**, dòng "Khung RTU gần nhất" phải thấy, ví dụ bật bit 1: `0B 06 00 0C 00 02 C8 A2` (A45, slave 11; CPUv1.0 slave 9: `09 06 00 0C 00 02 C9 40`). Khi đó CPU thật sẽ gửi tiếp `03 06 00 00 00 02 09 E9` tới bo RelayPower.
5. **Thử trên mạch thật** (trang Test Modbus làm sẵn các bước này: [05 Vận hành](05_VAN_HANH_GIAO_DIEN.md) mục 2), không tải, từng bước:
   - mở COM, đọc FC03;
   - ghi `Mode = 1, Plan = 2` (FC16 A45: `0B 10 00 01 00 02 04 00 01 00 02 C3 BA`; CPUv1.0: `09 10 00 01 00 02 04 00 01 00 02 C8 02`);
   - ghi `Power = 1 << n`, đo bằng đồng hồ tại tiếp điểm hoặc chân giắc;
   - có thể gắn máy dò Modbus vào bus USART1 để thấy khung `03 06 00 00 …` lặp lại mỗi vòng;
   - ghi `Power = 0` để kiểm tra rơ-le nhả.

   ACK không đủ làm bằng chứng, vì CPU không báo lỗi bo con (mục 3).
6. Đạt thì đổi `status` thành `"verified"` và ghi kết quả đo vào `note`/PROGRESS.
7. **Khi đầu ra không nằm trong 4 thanh ghi được chuyển tiếp** (bo matrix thứ hai, thanh ghi khác của bo RelayPower, hoặc cần nhiều hơn 16 rơ-le): **phải sửa firmware CPU** (đề xuất cho A45: mục 9).
   - Ví dụ: thêm `MBMasterWriteRegister(<ID>, <reg>, Modbus_DO.<word>, t_timeout)` vào vòng lặp. `DataO4`/`DataO5` (index 16–17) đang dự phòng; index 29–31 có trong mảng nhưng phải tăng `DOsize` để được chép sang `Modbus_DO`.
   - Mỗi lệnh thêm khoảng 2 ms (cộng `Delay` nếu có) vào chu kỳ vòng lặp. Sau đó đo lại bằng D02 và cập nhật `di_update_ms`.
8. **Bo matrix 8×4**: mỗi đầu vào mang một nguồn, mỗi đầu ra là một chân. Khai báo bo trong `matrix_boards` thay vì từng bit; khi biết bảng bit thật của bo, chỉ cần sửa `registers`/`layout` hoặc số đầu vào/ra trong JSON.

## 8. Hành vi khác cần lưu ý

- `Plan = 0` **không gọi hàm SelfTest** nào: nó gọi `GPIO_Configuration()` ở **mọi vòng** (cấu hình lại GPIO liên tục). `Plan = 1` gọi `Encoder_GPIO_Config()` mỗi vòng. Bộ chạy bài dùng `Plan = 2`.
- `CDT` `bit8 = 1` làm MCU phát chuỗi RS232/RS422 **lặp lại ở mỗi vòng** và xóa bộ đệm nhận `RevData`; phải xóa `bit8` về 0 để dừng. Payload tối đa 20 byte. SSI/encoder và DOUT/UART dùng chung một số chân.
- `DataO1`/`DataO2` (encoder) là lệnh tự xóa: không gửi lặp định kỳ, không retry. Chu kỳ tối thiểu 4 ms (≤ 250 Hz).
- `memcpy` ở đầu vòng lặp có thể chạy xen với một lệnh FC16 đang được ghi trong ngắt. Khi đó một lệnh ghi nhiều thanh ghi có thể có hiệu lực chia ra hai vòng (hiếm, vòng sau sẽ đúng).

## 9. Đề xuất sửa firmware

Người dùng cho phép sửa firmware CPU (và bo con) cho phù hợp, nhưng **chưa sửa**. Đề xuất dưới đây chỉ là tài liệu;
phần mềm PC không đụng vào thư mục firmware. Ba mục đầu là **bắt buộc** để dùng đủ 4 bo matrix trên mạch thật:

1. **Mỗi bo con một slave ID riêng.** RLMatrix/RLMUX/RLPW đặt `SLAVE_ADDRESS` cố định trong `User/Include/main.h`
   (`0x06`/`0x02`/`0x03`) và không đọc công tắc. Bốn bo matrix cùng ID sẽ cùng trả lời một khung → xung đột bus.
   Build mỗi bo một bản: matrix **6, 7, 8, 9**; MUX **2** (thêm bo MUX thì 12, 13, 14); nguồn **3**. (Bus USART1 của CPU
   tách khỏi bus PC, nên ID trùng với slave 11 của CPU cũng không sao, nhưng nên tránh cho dễ dò.)
2. **CPU gửi thêm bo matrix 2–4.** Trong `DataOutTypeDef` (CPUv1.1) thêm sau `DataT[10]` (index 31–36):
   ```c
   uint16_t Matrix2[2];   // index 31–32 → RLMatrix ID 7
   uint16_t Matrix3[2];   // index 33–34 → RLMatrix ID 8
   uint16_t Matrix4[2];   // index 35–36 → RLMatrix ID 9
   ```
   và trong vòng lặp, ngay sau `MBMasterWriteMultiRegister(Matrix_board_add, 0, 2, Modbus_DO.Matrix, t_timeout)`:
   ```c
   MBMasterWriteMultiRegister(0x07, 0, 2, Modbus_DO.Matrix2, t_timeout);
   MBMasterWriteMultiRegister(0x08, 0, 2, Modbus_DO.Matrix3, t_timeout);
   MBMasterWriteMultiRegister(0x09, 0, 2, Modbus_DO.Matrix4, t_timeout);
   Delay(t_delay);
   ```
   `memcpy(&Modbus_DO, &mod_buf_to_write, sizeof(Modbus_DO))` tự chép thêm các word này (mảng có 50 word). Bản đồ đã khai
   báo sẵn trong `hardware.json` → `extra_write_registers`; sửa firmware xong chỉ cần đổi `status` các bo sau khi kiểm.
3. **Bỏ gửi tới bo không lắp.** CPUv1.1 vẫn gửi `SW01`/`SW02` tới bo switch ID 1 và FC16 tới HMI ID 4 mỗi vòng; mỗi giao
   dịch không ai trả lời làm vòng lặp chậm thêm **100 ms** (`t_timeout`). Thiếu bo switch: +200 ms/vòng; thiếu HMI: +100 ms.
   Xóa (hoặc bọc `#if`) các dòng `MBMasterWriteRegister(SW_board_add, …)` và lệnh tắt LED HMI nếu không lắp HMI.
   Kiểm bằng bài tự kiểm tra **D02** trước và sau khi sửa.
4. Thêm bo MUX 2–4 (nếu cần nhiều hơn 64 điểm đo): thêm `MUX2..MUX4` (index 37–39) và gửi tới ID 12–14. A45 hiện chỉ
   dùng 18 kênh của một bo nên **chưa cần**.
5. **Sửa giới hạn vùng thanh ghi** (`REG_HOLDING_NREGS` 128 → bằng kích thước mảng) để không ghi đè RAM.
6. Bo RLMUX: kiểm `MUX1_val < 32`, `MUX2_val < 32` trước khi tra `Mux_Decoder` (hiện đọc tràn bảng → rơ-le ngẫu nhiên).
7. Đưa `Error_M` của từng bo con và **bộ đếm vòng lặp** lên DI; **echo `Mode`** và **boot ID** để PC phát hiện MCU reset.
8. Trạng thái mặc định an toàn khi khởi động (không tự bật VDD1–3); watchdog tự ngắt đầu ra khi mất PC.
9. Version/map ID, sample counter/timestamp, cờ `ready`/`fault`/`interlock`, độ dài chuỗi UART nhận được.
10. Lỗi nhỏ: `main.c` đặt bit 31 cho `Modbus_DO.MUX` (biến 16 bit), câu lệnh không có tác dụng.

## 10. Phân bổ bit giá thử A45 (giả định, để đi dây)

Cập nhật 2026-11-19 cho phần cứng thật: CPUv1.1 (slave 11), **4 bo RLMatrix 8×4, bo RLMUX 2×32, bo RLPW 12 rơ-le, không
có bo switch**. Phần cứng chưa đi dây, nên đây là bảng **đề xuất để đi dây theo**; mọi mục là `assumed` trong
`hardware.json` → `stm32_io` (nguồn chính, tài liệu này chỉ tóm tắt). Điểm cần kiểm: PROGRESS.md, mục "Cần kiểm khi lên
phần cứng thật".

**Nguyên tắc**
- Nguồn và tín hiệu (AC 36/22 V, DC ±, ±3 V, 27 V, 5 V, xung 10 kHz, đất) do bo/nguồn ngoài tạo sẵn; phần mềm chỉ
  **đóng rơ-le** đưa chúng vào chân. DAC chỉ dùng cho mức nhỏ biến đổi. Lệnh mức (27V-KOM, CX3, CX4, ОТКЛ) cũng đi qua
  bo matrix, nên **không cần mạch driver cho DOUT**.
- Đất chung cho toàn giá thử, không cần đo vi sai. Bảo vệ phần cứng: atomat tổng, cầu chì từng nguồn; MCU không có
  watchdog khi mất PC.
- Không dùng `Power` bit 7–9 (firmware tự bật khi `Mode ≠ 1`/reset, mục 5). HMI không ghi `Matrix[]`, nên sau reset bo
  matrix nhận 0 (mọi rơ-le nhả).
- Firmware RLMatrix: bit `k` của 32 bit (`reg0` bit 0–15, `reg1` bit 0–15) → rơ-le **RL(k+1)**. Rơ-le nào nối đầu vào nào
  với đầu ra nào thì nằm trên sơ đồ mạch; phần mềm **giả định** `k = (đầu ra − 1) × 8 + (đầu vào − 1)`. Sai thì chỉ sửa
  `matrix_boards` trong JSON.

**Bo rơ-le nguồn RLPW** (ID 3, `Power`; bit `k` → RL`k+1`)

| Bit | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7–9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|
| Nguồn | AC 36 V | AC 22 V | +27 V | +15 V | −15 V | +12 V | −12 V | **để trống** | +5 V | −5 V |

AC 36 V và AC 22 V có liên động phần mềm (không bao giờ cùng bật); P01 đổi từ 36 sang 22 V theo kiểu ngắt trước đóng sau.

**Bo matrix tín hiệu RLMatrix** (8 đầu vào × 4 đầu ra)

| Bo | Thanh ghi CPU | Đầu vào | Đầu ra |
|---|---|---|---|
| ID 6 (có sẵn trong CPUv1.1) | `Matrix0`, `Matrix1` (index 18–19) | 1 = +3 V, 2 = −3 V, 3 = DAC, 4 = đất; 5–8 dư | 1 = 40XP1, 2 = 41XP1, 3 = 42XP1, 4 = 22XP1 |
| ID 7 (**cần sửa FW**, mục 9) | `Matrix2_0/1` (31–32) | 1 = +3 V, 2 = −3 V, 3 = đất, 4 = xung 10 kHz 4,5 Vpp; 5–8 dư | 1 = 32XP1, 2 = 54XP1, 3 = 43XP1, 4 = 44XP1 |
| ID 8 (**cần sửa FW**) | `Matrix3_0/1` (33–34) | 1 = 27 V, 2 = đất, 3 = 5 V; 4–8 dư | 1 = 4XP1, 2 = 12XP1, 3 = 13XP1, 4 = 15XP1 |
| ID 9 (**cần sửa FW**) | `Matrix4_0/1` (35–36) | 1 = đất; 2–8 dư | 1 = 23XP1; 2–4 dư |

Ví dụ: nối 40XP1 với +3 V = bo ID 6, `Matrix0` bit 0 (RL1); 41XP1 với đất = `Matrix0` bit 11 (RL12); 22XP1 với −3 V =
`Matrix1` bit 9 (RL26). Mỗi chân chỉ nối một nguồn; không lệnh = hở mạch.

**DAC**: tầng khuếch đại hệ số 1 có trừ 1,62 V → `V_XP1 = −DAC_val × 1,55 mV` (dải ±1,55 V, bước 1,55 mV; phần mềm
giới hạn ±1,5 V, mã ±1000). Phải đo hiệu chuẩn 5 điểm (`DAC_val` = −1000, −500, 0, 500, 1000) rồi sửa
`stm32_io.dac.scale/offset`.

**MUX RLMUX** (ID 2, 2 kênh × 32 đầu vào). **Đã đối chiếu firmware**: byte thấp của `MUX` = số kênh MUX1 (0–31,
kênh `k` = `Mux1.(k+1)`), byte cao = MUX2; bo tự tra `Mux_Decoder[32]`. Kênh 31 (`Mux1.32` = `0x0000`, hở hết) là trạng
thái an toàn (`safe_state.MUX = 0x1F1F`). Kênh ≥ 32 bị phần mềm chặn. MUX1 → `ADC3` (±12 V, bước 0,01 V) **giả định**:

| Kênh | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15–17 | 18–30 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Điểm đo | 14XP1 | 25 | 26 | 29 | 34 | 37 | 48 | 49 | 50 | 51 | 52 | 56 | 63 | dòng AC | dòng DC | áp pha A/B/C | dư |

Dòng/áp nguồn đi qua mạch đo có sẵn (giả định 1 V/A và 0,1 V/V) vào kênh MUX như các chân khác. Tần số 3 pha nhập tay
từ oxilo.

## 11. Firmware bo con (đã đối chiếu 2026-11-19)

| Bo | Thư mục | Slave | Nhận | Hành vi |
|---|---|---|---|---|
| RLMatrix v1.0 | `RLMatrixv1.0/User` | `0x06` cố định (`main.h`) | `mod_buf_to_write[0..1]` (FC06/FC16 reg 0–1) | Mỗi 1 ms tách 32 bit → 32 chân GPIO RL1–RL32 (`gpio.h`: RL1 = PA3 …); không đọc lại, không báo lỗi |
| RLMUX v1.0 | `RLMUXv1.0/User` | `0x02` cố định | reg 0 | `MUX1_val = reg0 & 0xFF`, `MUX2_val = reg0 >> 8`, tra `Mux_Decoder[32][2]` → 16 rơ-le mỗi kênh; **không kiểm < 32** |
| RLPW v1.0 | `RLPWv1.0/USER` | `0x03` cố định | reg 0 | Bit 0–11 → RL1–RL12 (`gpio.h`); bit 12–15 nối chân khác (không dùng) |

Cả ba dùng FreeModbus slave 115200 8N1, `REG_HOLDING_NREGS = 128`, không có watchdog hay trạng thái an toàn riêng: rơ-le
giữ giá trị ghi cuối cùng (CPU gửi lại mỗi vòng). Chúng không đo gì nên PC chỉ kiểm được đầu ra bằng đo ngược (MUX/ADC
hoặc đồng hồ).
