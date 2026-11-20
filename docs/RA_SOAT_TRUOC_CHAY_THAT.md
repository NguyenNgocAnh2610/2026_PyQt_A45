# Rà soát trước khi chạy trên mạch thật — A45 / 1101K-10

> **Tài liệu tạm** (2026-11-19): báo cáo để người dùng đọc và quyết định trước khi sửa. Sau khi có quyết định, nội dung
> được chuyển vào `docs/STM32_MODBUS_PC.md` / `PROGRESS.md` rồi xóa file này (như phiếu xác nhận lần trước).
> Chưa sửa mã. Firmware chỉ đọc; mọi thay đổi firmware dưới đây là **đề xuất** để anh/chị tự làm trong bản mới.

Nguồn đã đọc lại:
- Firmware `ref_AHung\A34_Phao37\Program`: `CPUv1.1 For DK_QDT\Src\main.c`, `Inc\System_Register.h`, `RLMatrixv1.0`,
  `RLMUXv1.0`, `RLPWv1.0`.
- `docs/BAI_KIEM_TRA_1101K.md`, `configs/a45/*.json`, mã PC (`src/backend.py`, `src/device.py`, `src/protocol.py`).

Phần cứng theo anh/chị:
- 1 CPU (slave 11, đã thử);
- 4 RLMatrix 8 vào × 4 ra;
- 4 RLMUX, mỗi bo 2 kênh 32 vào → 1 ra;
- 1 RLPW 12 rơ-le.

---

## 0. Kết luận nhanh

1. **Không cắm cùng lúc nhiều bo cùng loại vào bus của CPU khi firmware bo con chưa đổi.** Firmware cố định slave ID
   trong mã (`#define SLAVE_ADDRESS`, không đọc công tắc):
   - mọi RLMatrix đều là ID 6;
   - mọi RLMUX đều là ID 2.

   Khi 4 bo cùng ID cùng nằm trên bus:
   - cả 4 bo nhận cùng một lệnh và đóng **cùng số rơ-le**, nên chân XP1 trên bo khác bị nối nguồn ngoài ý muốn;
   - cả 4 bo trả lời cùng lúc, gây va chạm trên bus.
2. **Giữ nguyên 100% firmware** (CPU và bo con), cắm **1 RLMatrix + 1 RLMUX + RLPW**:
   - chạy được **15/24 bài**: P01–P09, P13, P15, P17–P19;
   - **9 bài không chạy được**: P10–P12, P14, P16, P20–P24. Các bài này cần thêm chân XP1 điều khiển độc lập, mà
     1 bo matrix chỉ có 4 đầu ra.
3. **Để chạy đủ 24/24** có hai hướng, xem mục 3:
   - **A (khuyến nghị):** đổi một hằng số ID trong firmware RLMatrix (không đổi logic), và CPU thêm 3 lệnh gửi.
   - **B:** không sửa firmware nào, dùng tính năng "phát UART" có sẵn của CPUv1.1 qua các cổng RS422. Hướng này còn
     rủi ro về điện và chậm.
4. **RLMUX:** 1101K chỉ cần 18 điểm đo, nên **1 bo RLMUX là đủ**. Ba bo còn lại để ngoài bus (hoặc xem mục 3.4).
5. **Phần mềm PC phải sửa trước khi chạy thật** (mục 6). Điểm quan trọng nhất về an toàn: `break_ms` = 150 ms
   **ngắn hơn chu kỳ vòng lặp CPU** (≈ 370 ms). Khi đó lệnh "ngắt" và lệnh "đóng" có thể lọt vào cùng một vòng, và
   CPU gửi xuống bo matrix một lần, mở và đóng rơ-le **đồng thời**. Ví dụ đổi một chân từ +3 V sang −3 V thì có thể
   chập trong lúc rơ-le chuyển.

---

## 1. Phần cứng và firmware thực tế (đã đọc mã)

| Bo | Số bo | Slave ID trong firmware | ID đặt bằng | CPU gửi gì mỗi vòng (CPUv1.1) |
|---|---|---|---|---|
| CPU | 1 | 11 = 8 + công tắc ID | công tắc trên bo | — (PC là master của CPU) |
| RLMatrix v1.0 | 4 | **0x06 cố định** (`main.h:34`) | hằng số trong mã | FC16 `Matrix0/1` (DO 18–19) → ID 6 |
| RLMUX v1.0 | 4 | **0x02 cố định** (`main.h:20`) | hằng số trong mã | FC06 `MUX` (DO 11) → ID 2 |
| RLPW v1.0 | 1 | 0x03 cố định | hằng số trong mã | FC06 `Power` (DO 12) → ID 3 |
| (bo switch) | 0 | — | — | 2 × FC06 `SW01/SW02` → ID 1, không ai trả lời, chờ 2 × 100 ms |
| (bo HMI) | 0 | — | — | FC16 → ID 4, không ai trả lời, chờ 100 ms |

Bảng trên cho thấy firmware CPUv1.1 hiện chỉ điều khiển được:
- **1 bo matrix** (32 rơ-le);
- **1 bo MUX** (MUX1 + MUX2);
- **RLPW** (12 rơ-le);
- các chân riêng của CPU: DAC `PA4`, 10 DOUT, 5 ADC, 10 DIN.

Ngoài ra, CPU chỉ chuyển lệnh xuống bo con **một lần mỗi vòng lặp**. Phản hồi PC nhận được (ACK) chỉ cho biết CPU đã
nhận lệnh. CPU cũng không báo lên PC bo con có trả lời hay không (`Error_M` không có trong DI).

Khi `Mode ≠ 1` (vừa bật nguồn, CPU reset, hoặc PC ghi `Mode=0`), CPU chạy mã HMI (`main.c:376–512`):
- **RLPW RL8, RL9, RL10 (bit 7–9) tự đóng.**
- Bit 1/2/4/6 theo nút HMI. Không có bo HMI nên các bit này giữ 0.
- **Các bit Power khác giữ nguyên giá trị PC ghi lần cuối.**

---

## 2. Nhu cầu của 24 bài so với phần cứng

### 2.1. Chân phải cấp tín hiệu (13 chân, qua bo matrix)

| Chân XP1 | Mức cần | Bài | Bo (phân bổ hiện tại) |
|---|---|---|---|
| 40, 41, 42 | DAC nhỏ, ±3 V, 0 (đất) | P04–P09, P12, P17–P19, mục V | ID 6 |
| 22 | ±3 V, 0 | P10, P13, P15 | ID 6 |
| 32 | ±3 V, 0 | P11, P14, P16 | ID 7 |
| 54 | ±3 V | P21 | ID 7 |
| 43, 44 | xung 10 kHz 4,5 Vpp | P10–P12 | ID 7 |
| 4 | +27 V (điều kiện chung mục V) | P20–P24 | ID 8 |
| 12, 15 | 0 (đất) | P22, P20 | ID 8 |
| 13 | +5 V | P23, P24 | ID 8 |
| 23 | 0 (đất) | P21 | ID 9 |

Ví dụ P10 cần cùng lúc: 43 và 44 có xung, 22 ở ±3 V. Mục V cần cùng lúc: 4 = 27 V, 40/41/42 = đất, cộng 1–2 chân
riêng của từng bài.
- Một bo matrix chỉ có **4 đầu ra**, nên không đủ.
- RLPW còn trống bit 7–9, nhưng các bit này bị **tự đóng** khi CPU ở chế độ HMI. Đưa 27 V hay 5 V qua đó nghĩa là
  cấp vào khối ngay lúc bật nguồn. Không nên dùng.
- DOUT của CPU là chân logic 3,3 V, cần thêm mạch rơ-le. Không thuộc phần cứng hiện có.

### 2.2. Điểm đo (18 điểm, qua MUX → ADC)

| Điểm đo | Số | Bài |
|---|---|---|
| XP1 14, 25, 26, 29, 34, 37, 48, 49, 50, 51, 52, 56, 63 | 13 | P03–P24 |
| Dòng AC, dòng DC, áp pha A/B/C | 5 | P01, P02 |
| Tần số A/B/C | — | P01, người vận hành nhập từ oxilo |

18 ≤ 32 kênh của **một** MUX nên **một bo RLMUX là đủ**.

### 2.3. Bài nào chạy được với firmware giữ nguyên

| Bài | Chạy được với 1 bo matrix? | Lý do |
|---|---|---|
| P01, P02 | Có | Chỉ dùng RLPW và đo |
| P03 | Có | Chỉ đo |
| P04–P06, P17–P19 | Có | DAC vào 40/41/42 (bo ID 6). **Cần tầng DAC ra mức âm**, xem mục 5.1 |
| P07–P09 | Có | ±3 V vào 40/41/42 |
| P13, P15 | Có | 22XP1 (bo ID 6) |
| P10, P11, P12 | Không | Cần 43/44 (xung), 32 |
| P14, P16 | Không | Cần 32 |
| P20–P24 | Không | Cần 4 (27 V), 12/13/15/23, 54 |

---

## 3. Cách mở rộng lên 4 bo matrix

### 3.1. Hướng A — đổi ID bo matrix (khuyến nghị)

- **Bo RLMatrix:** **chỉ đổi** `#define SLAVE_ADDRESS 0x06` thành `0x07`, `0x08`, `0x09` rồi build ra 3 file hex.
  Không đổi dòng logic nào.
- **CPU:** thêm 3 lệnh `MBMasterWriteMultiRegister(0x07/0x08/0x09, 0, 2, …)` lấy dữ liệu từ DO 31–36. Mảng
  `mod_buf_to_write` đã có 50 word nên phải mở rộng struct `Modbus_DO`. Đoạn C mẫu ở `docs/STM32_MODBUS_PC.md`
  mục 9.9.
- **Phần mềm PC:** gần như đã sẵn (`extra_write_registers` Matrix2_0…Matrix4_1). Chỉ còn đổi trạng thái sau khi đo
  kiểm.
- **Đổi lại:** mỗi bo matrix có lắp tốn thêm khoảng 13 ms mỗi vòng. Nếu đồng thời bỏ 3 khung tới HMI/bo switch không
  lắp thì vòng lặp còn khoảng 100 ms thay vì 370 ms.

### 3.2. Hướng B — không sửa firmware nào, dùng "phát UART" của CPUv1.1

CPUv1.1 đã có sẵn tính năng này (`main.c:676–770`):
- PC ghi `DataT0…9` (20 byte) và `CDT`, trong đó bit 0–7 = độ dài, bit 8 = bật, bit 11–14 = chọn cổng RS422_1…4.
- **Mỗi vòng**, CPU phát nguyên các byte đó ra các cổng được chọn, ở 115200 baud (mặc định khi khởi động).

Cách dùng:
- Mỗi bo matrix 2–4 (vẫn là ID 6) nối vào **một cổng RS422 riêng**, tức là một bus riêng nên không xung đột.
- PC tự dựng khung Modbus `06 10 00 00 00 02 04 … CRC` (13 byte) trong `DataT` và bật đúng một cổng.

Ràng buộc và rủi ro:
- **Điện:** trong mã không có chân bật/tắt driver RS422 (`USART_WriteBuff` phát thô). Nếu driver RS422 của CPU luôn
  bật, khung trả lời 8 byte của bo matrix sẽ **tranh đường dây** với driver CPU mỗi vòng. Phải xem sơ đồ cổng RS422
  của CPU trước. Cần cáp nối cặp TX của RS422 sang A/B của bo.
- **Chỉ một buffer cho mọi cổng**, nên mỗi lần chỉ đổi được một bo. Mỗi lần đổi mất khoảng 2 vòng (≈ 0,8 s). Bài nào
  phải đổi 2–3 bo thì chậm thêm vài giây.
- **Không có xác nhận nào từ bo:** giống hướng A về mặt "ACK chỉ là CPU đã nhận", nhưng ở đây không có cả kiểm tra
  của CPU.
- **Thêm việc cho phần mềm PC:** thêm một "kênh phụ" mới, và mở quyền ghi `CDT`/`DataT`, hiện đang bị cấm để an toàn.
  Đây là thay đổi lớn hơn hướng A.

### 3.3. Hướng C — chạy 15/24 ngay, chưa sửa gì

- Cắm CPU, RLPW, **1 RLMatrix**, **1 RLMUX**. Các bo matrix/MUX khác **rút khỏi bus của CPU**.
- Phần mềm đánh dấu bo ID 7–9 là "không có", để 9 bài kia hiện **BLOCKED** kèm lý do rõ (mục 6, điểm 5).

**Đề xuất:** làm C trước để dựng và kiểm phần cứng, đồng thời quyết định A hoặc B cho 9 bài còn lại.

### 3.4. Bốn bo MUX

1101K không cần thêm bo MUX.

Nếu sau này cần: có thể để nhiều bo cùng ID 2 trên bus mà **không** sửa firmware, với điều kiện đầu ra của mỗi bo vào
**một ADC riêng** của CPU. Khi đó các bo cùng chọn một số kênh, mỗi bo đo một điểm khác nhau vào ADC khác nhau. Không
được nối chung đầu ra của hai bo. Va chạm khung trả lời vẫn còn, nhưng CPU không dùng phản hồi.

---

## 4. Chu kỳ vòng lặp CPU và an toàn khi chuyển rơ-le (quan trọng)

Với firmware CPUv1.1 giữ nguyên, ước tính mỗi vòng **L ≈ 360–380 ms**: 300 ms chờ HMI và bo switch không lắp, cộng
5 × 10 ms `Delay`, cộng các khung có trả lời và phần ADC (`STM32_MODBUS_PC` mục 9.2). D02 sẽ cho số thật.

| Tham số | Hiện tại | Phải thỏa | Hậu quả nếu sai |
|---|---|---|---|
| `break_ms` (ngắt trước, chờ, rồi đóng) | 150 ms | **> L + thời gian nhả rơ-le**, khoảng ≥ L + 80 ms ≈ 450 ms | CPU chỉ chép lệnh ở đầu vòng. Lệnh "ngắt" và "đóng" gửi cách nhau 150 ms có thể bị gộp, rơ-le mở và đóng cùng lúc. Có thể chập +3/−3 V trên một chân, hoặc AC 36/22 V |
| `di_update_ms` (chờ số đo mới sau ACK) | 150 ms | ≥ 2 L ≈ 750–800 ms | Đọc phải số của trạng thái cũ, dẫn tới FAIL sai |
| Ngưỡng D02 | `di_update_ms`/2 = 75 ms | Theo `di_update_ms` mới | D02 FAIL thì mọi bài đo bị chặn (đúng như thiết kế) |

Ghi chú:
- Thời gian ổn định của khối (`wait_ms` 250 ms) đang tính từ ACK. Rơ-le đóng muộn tối đa L sau ACK. Vì phép đo đến
  sau `wait_ms` + `di_update_ms` (≥ 2 L), khối vẫn có ít nhất `wait_ms` + L để ổn định. Vậy là đạt.
- Với L ≈ 370 ms, một lượt 24 bài mất khoảng **6–8 phút** (riêng P01 đã 2 phút). Chấp nhận được. Nếu bỏ gửi bo vắng
  (mục 7) thì nhanh hơn khoảng 3 lần.
- Hiện phần mềm chỉ kiểm chu kỳ D02 so với `di_update_ms`, **chưa kiểm so với `break_ms`**. Phải thêm (mục 6, điểm 1).

---

## 5. Đo lường và kích thích: cần anh/chị xác nhận phần cứng

### 5.1. DAC

Firmware chỉ ra điện áp tại chân `PA4` của CPU, trong dải 0–3,3 V: `V_PA4 = 1,62 − DAC_val/1000 × 1,55`.
- Các bài cần mức **âm**: P05 −0,6 V, P17 −0,4 V, P18 −0,3 V. Cấu hình đang giả định có tầng trừ 1,62 V, cho
  `V_XP1 = −DAC_val × 1,55 mV`.
- **Nếu không có tầng này**, `PA4` nối thẳng qua matrix chỉ cho 0–3,3 V, nên các bước mức âm không làm được.
- Phải đo bảng 5 điểm để hiệu chuẩn. P04 cần 0,02 V với dung sai ±0,05 V: lệch offset vài chục mV là đủ làm FAIL.

### 5.2. ADC

- Firmware gửi lên `V × 100` dạng int16, tức độ phân giải 0,01 V.
- Offset của từng kênh ghi cứng 1,62–1,65 V (`main.c` `ADC_process`), không hiệu chỉnh khi chạy.
- Các chân nhỏ của P03–P06 (0,02–0,6 V, ±0,05 V) đang đo qua `ADC3` (±12 V, khoảng 6,7 mV/LSB). Sai offset có thể
  ăn hết dung sai.

**Đề xuất:**
- Nối đầu ra **MUX2 vào `ADC4`** (±7,5 V, khoảng 3,7 mV/LSB) cho các chân nhỏ, giữ MUX1 vào `ADC3` cho ±8,5 V. Chỉ
  cần đổi cấu hình, phần mềm đã hỗ trợ `mux_bank`.
- Đi dây 2 kênh MUX dự phòng vào **GND** và **+3 V chuẩn**, để thêm bài tự kiểm tra **D03** kiểm offset và hệ số ADC
  trước mỗi lượt.

### 5.3. Module đo AC/DC

- Áp pha A/B/C (~22 V AC), dòng AC 3 A, dòng DC: đầu ra của module nối vào kênh MUX/ADC nào? Hệ số bao nhiêu? Đầu ra
  có phải DC tỉ lệ với giá trị hiệu dụng không?
- Cấu hình đang giả định MUX1 kênh 13–17 → `ADC3`, 1 V/A và 0,1 V/V.

### 5.4. Xung 10 kHz

- Lấy từ máy phát ngoài qua đầu vào 4 của bo matrix ID 7. Cần xác nhận 43XP1 và 44XP1 dùng chung một nguồn hay cần
  lệch pha.
- CPU có `Pulse_out` (DataO4/5) trên một chân DOUT, nhưng chỉ 3,3 V, không đạt 4,5 Vpp. Không dùng.

### 5.5. Rủi ro do firmware CPU, phần mềm PC chỉ giảm nhẹ được

- **RL8–RL10 tự đóng khi `Mode ≠ 1`:** để trống, không nối gì. Cấu hình đã như vậy.
- **CPU reset giữa lượt:** CPU về chế độ HMI và PC không biết. Không có watchdog, nên nếu PC treo hoặc rút cáp thì
  rơ-le **giữ nguyên trạng thái**. Cần nút dừng khẩn hoặc ngắt nguồn tay ở giá thử.

---

## 6. Phần mềm PC: đề xuất sửa (chưa làm, chờ duyệt)

| # | Mức | Việc | Ghi chú |
|---|---|---|---|
| 1 | **An toàn** | Chặn chạy thật khi `break_ms` ≤ chu kỳ D02 + biên. Áp cho cả bộ chạy bài và Test Modbus. Thông báo đề xuất giá trị `break_ms`, `di_update_ms` theo D02 | Không tự sửa cấu hình. Anh/chị sửa `hardware.json` theo số đo |
| 2 | **An toàn** | "Trả về HMI": ghi trạng thái an toàn trước, sau đó mới `Mode=0` | Hiện CPU giữ nguyên Power bit 0/3/5/10/11 PC đã ghi, nên nguồn vẫn đóng |
| 3 | **An toàn** | Ngắt kết nối hoặc đóng ứng dụng khi công cụ Test Modbus còn đầu ra đóng: hỏi, rồi ghi "Về an toàn" trước khi đóng cổng | Bộ chạy bài đã tự về an toàn khi dừng hoặc đóng giữa lượt |
| 4 | **An toàn** | Sau lỗi truyền thông giữa bài: cảnh báo nổi bật "đầu ra có thể vẫn đóng", kèm nút **Về an toàn** ở màn hình chính | Giữ nguyên tắc không tự gửi lại; người vận hành bấm |
| 5 | Chức năng | Chế độ "1 bo matrix" (hướng C): bo ID 7–9 thành `unsupported`, nên 9 bài hiện BLOCKED kèm lý do. Tab bo 7–9 trên Test Modbus khóa khi dùng COM thật | Sửa `hardware.json` + nhãn UI |
| 6 | Đo | Đổi cấu hình MUX2 → `ADC4` cho chân nhỏ; thêm D03 (kiểm offset/hệ số ADC) | Sau khi anh/chị xác nhận đi dây |
| 7 | Tiện | Thêm "Cần kiểm" trong Test Modbus: đánh dấu từng rơ-le/ô/kênh đã đo, ghi `verified` vào `hardware.json` (có xác nhận) | Hiện phải sửa JSON bằng tay |
| 8 | Chỉ khi chọn B | Kênh phụ UART: dựng khung FC16 trong `DataT`, bật từng cổng, chờ 2 vòng, đổi bo; mở có kiểm soát quyền ghi `CDT`/`DataT` | Thay đổi lớn, cần test kỹ |

Điểm 1–4 nên làm **trước lần cấp nguồn khối đầu tiên**. Điểm 5–6 làm cùng lúc với lần đi dây.

---

## 7. Firmware CPU: đề xuất (anh/chị sửa trong bản mới nếu đồng ý)

Ưu tiên giữ nguyên. Bảng dưới xếp theo lợi ích trên công sửa:

| Sửa | Lợi ích | Bắt buộc? |
|---|---|---|
| Bỏ khung gửi HMI (ID 4) và bo switch (ID 1) trong vòng lặp | Vòng lặp từ ~370 ms còn ~70 ms; lượt đo nhanh khoảng 3 lần | Không. PC thích nghi được bằng `break_ms`/`di_update_ms` |
| Gửi `Matrix2..4` tới ID 7–9 (kèm đổi `SLAVE_ADDRESS` bo matrix) | Chạy được 24/24 (hướng A) | Có, nếu muốn đủ 24 bài mà không dùng hướng B |
| Ghi `Error_M` của từng bo con lên DI (FW-04) | PC biết bo con có trả lời hay không, thay vì chỉ có ACK của CPU | Không, nhưng rất có ích khi dò lỗi đi dây |
| Watchdog mất PC (FW-07): quá N giây không có lệnh từ PC thì về an toàn | Rơ-le không giữ nguồn khi PC treo | Không, nhưng nên có |

---

## 8. Quy trình chạy thử đề xuất

1. **Không nối khối 1101K.** Cắm CPU, RLPW, 1 RLMatrix (ID 6), 1 RLMUX. Rút các bo matrix/MUX khác khỏi bus CPU.
2. Mở COM (Modbus RTU) và chờ "Sẵn sàng · COM THẬT". Chạy **Tự kiểm tra** rồi ghi lại chu kỳ D02 (L).
3. Sửa `break_ms` và `di_update_ms` theo L (tôi sẽ tính số đề xuất; anh/chị duyệt).
4. Dùng **Test Modbus** và đồng hồ:
   - kiểm từng rơ-le RLPW;
   - kiểm từng ô matrix ID 6;
   - kiểm từng kênh MUX bằng cách đưa áp chuẩn vào;
   - đo DAC 5 điểm.

   Mục nào đạt thì đổi thành `verified`.
5. Nối khối và chạy P01, P02 (dừng cả lượt nếu FAIL). Sau đó chạy P03–P09, P13, P15, P17–P19.
6. Quyết hướng A hoặc B cho P10–P12, P14, P16, P20–P24.

---

## 9. Câu hỏi cần anh/chị trả lời

1. Bo matrix 2–4: chọn **A** (đổi ID + CPU gửi thêm), **B** (cổng RS422, không sửa firmware) hay **C trước rồi tính
   sau**?
2. DAC: có tầng khuếch đại/trừ offset để ra ±1,55 V không, hay `PA4` nối thẳng?
3. Đầu ra MUX1 và MUX2 của bo MUX đang (hoặc sẽ) nối vào ADC nào của CPU? Module đo áp/dòng AC/DC nối vào đâu, hệ số
   bao nhiêu?
4. Bốn bo MUX hiện có cắm cả 4 trên bus CPU không? (1101K chỉ cần 1.)
5. Chỉ khi chọn B: cổng RS422 trên bo CPU dùng IC driver gì, có chân DE (bật/tắt driver) không?
6. 4XP1 "27V-KOM": chỉ cấp trong các bài mục V (như cấu hình hiện tại) hay cấp suốt?
7. Đồng ý làm điểm 1–4 ở mục 6 ngay không?
