# Vận hành trên giao diện

Cách dùng các màn hình chẩn đoán (thanh kết nối, hai mảng thanh ghi, trang Test Modbus) và điều kiện để chạy bài trên mạch thật. Quy trình ghép mạch cho giá thử mới: [07 Chuyển giá thử](07_CHUYEN_GIA_THU_MOI.md) mục 5.

## Mục lục

- [1. Kết nối và bảng hai mảng thanh ghi](#1-kết-nối-và-bảng-hai-mảng-thanh-ghi)
- [2. Trang "Test Modbus" (`src/ui/widgets/modbus_test.py`)](#2-trang-test-modbus-srcuiwidgetsmodbus_testpy)
- [3. Điều kiện chạy trên mạch thật (đã có trong phần mềm)](#3-điều-kiện-chạy-trên-mạch-thật-đã-có-trong-phần-mềm)

## 1. Kết nối và bảng hai mảng thanh ghi

1. Thanh Kết nối: chọn **Modbus RTU** (hoặc **UART** để mở cổng serial thuần), COM, baudrate → **Kết nối**. Thao tác quét danh sách COM (`available_serial_ports()`) không mở hay thăm dò cổng. Với profile adapter `stm32`, mở cổng Modbus RTU xong phần mềm **tự đọc một FC03** tới slave của profile (không ghi gì): trả lời hợp lệ → **"Sẵn sàng · COM THẬT"**; không trả lời → "Không có phản hồi STM32 (slave N)" kèm gợi ý kiểm tra công tắc ID, dây A/B, baud; cổng đóng sau timeout như mọi giao dịch lỗi.
2. **8N1 · Chi tiết**: chỉnh data bits/parity/stop bits/timeout trước khi nối; **Đọc một lần** `FC03`/`FC04` theo Slave ID, địa chỉ zero-based thập phân, số thanh ghi. Chế độ UART hiển thị byte nhận được dạng hex.
3. **Hai mảng STM32 · Giả lập / COM thật** (`src/ui/widgets/stm32_registers.py`):
   - Bảng tên thanh ghi theo bản đồ của profile (`hardware.cpu_map`; A45 = CPUv1.1, DI đọc 1–42). Rê chuột lên tên thanh ghi để xem lưu ý (Matrix, CDT, encoder…). Có **Tự đọc mỗi … ms** (chỉ đọc FC03, tự dừng khi ẩn).
   - Mặc định **GIẢ LẬP** qua COM ảo ([03 Luồng Modbus](03_LUONG_MODBUS_TRONG_CODE.md) mục 7), không cần COM thật. Để nối mạch thật: mở COM ở chế độ Modbus RTU, bỏ chọn giả lập (ô "CPU slave" cố định theo `stm32_io.slave`, không sửa được), bấm **đọc FC03 trước**.
   - Ghi `MUX` có kênh ≥ 32 bị **từ chối** trước khi gửi (firmware RLMUX không kiểm giới hạn).
   - Sửa ô trên bảng ghi chỉ sửa **bản nháp** (`backend.stm32.mod_buf_to_write`); những ô chưa nhập không bao giờ được gửi. Chọn vùng địa chỉ rồi bấm gửi (`FC06`/`FC16`); giá trị được chụp tại thời điểm gửi.
   - Đổi nguồn giả lập/thật **không tự gửi** bản nháp. Khi bộ chạy bài đang chạy, bảng DI hiển thị lần đọc mới nhất của bộ chạy bài (chỉ xem).
   - Dòng **Khung RTU gần nhất** hiện TX/RX dạng hex của nguồn đang chọn. Khung được dựng lại từ PDU và CRC tính lại (Qt không cho lấy byte thô); dùng để đối chiếu với máy dò Modbus.
4. **Ngắt** luôn hủy giao dịch đang chờ và giải phóng cổng serial.

Ví dụ gọi API trong mã (chạy theo event loop Qt, chỉ gọi giao dịch kế tiếp sau khi giao dịch trước đã hoàn tất):

```python
mode = backend.cpu_map.write_index("Mode")              # = 1
backend.stage_stm32(mode, [1, 2])                         # chỉ sửa bản nháp (Mode=1, Plan=2)
backend.request_stm32(simulation=True)                    # đọc FC03 (slave theo profile, DI 1..N)
backend.request_stm32(simulation=True, address=1, count=2)  # ghi FC16 Mode+Plan
```

## 2. Trang "Test Modbus" (`src/ui/widgets/modbus_test.py`)

Mục riêng trên thanh bên trái, ba tab. Bị khóa khi bộ chạy bài đang chạy; bộ chạy bài cũng không bắt đầu khi công cụ còn
lệnh đang chờ. Chọn **COM ảo** để thử trước, **COM thật** khi cổng đã mở ở chế độ Modbus RTU.

- **Điều khiển qua CPU** (cùng `Stm32IoMap` với bộ chạy bài). PC **không** nói chuyện với bo con: PC ghi thanh ghi
  của CPU (slave 11), mỗi vòng lặp CPU tự gửi tiếp xuống bus riêng của nó (`CpuMap.forwards`: `Power` → RLPW ID 3,
  `Matrix0/1` → RLMatrix ID 6, `MUX` → RLMUX ID 2). Dòng "Đường đi lệnh" và tiêu đề từng nhóm ghi rõ thanh ghi CPU và
  bo nhận; bo profile không dùng (bo switch) ghi "không lắp". "CPU slave" là ID của CPU, không phải của bo con.
  - **Phần mềm ép nguyên tắc này**: `Backend.check_cpu_slave()` từ chối mọi yêu cầu FC03/06/16 (đọc, ghi thô, công cụ)
    tới slave khác `stm32_io.slave`; ô "CPU slave" ở trang này, ở bảng thanh ghi và ô "ID CPU" trên thanh kết nối chỉ
    hiển thị, không sửa được (đổi trong `hardware.json`). Bộ chạy bài và bước xác minh khi mở cổng vốn chỉ dùng
    `stm32_io.slave`. Ngoại lệ duy nhất: "Đọc thử" trong Chi tiết kết nối (chỉ đọc FC03/04, ID tùy ý) để dò ID của bo
    CPU khi không có phản hồi.
  - **Lấy quyền điều khiển**: ghi `Mode=1`, `Plan=2` và toàn bộ trạng thái an toàn. Sau đó trạng thái đầu ra "đã biết"
    (theo ACK); mọi nút điều khiển mới mở. Trên COM thật có hộp thoại xác nhận.
  - **Về an toàn**: ghi lại toàn bộ trạng thái an toàn (dùng được cả khi trạng thái chưa biết). **Trả về HMI**: `Mode=0`
    (CPU tự bật VDD1–3; có xác nhận).
  - **Rơ-le nguồn**: 12 nút RL1–RL12 có tên tín hiệu; RL8–10 (bit 7–9, HMI ép bật) bị khóa. Liên động AC 36/22 V áp như
    bộ chạy bài; đóng nguồn trên COM thật phải xác nhận.
  - **Bo matrix**: một tab mỗi bo (ID 6; ID 7–9 ghi "cần sửa FW"), lưới đầu ra × đầu vào. Bấm ô = nối chân với nguồn đó
    (nhả nguồn cũ, chờ `break_ms`, rồi đóng); cột "Hở" = nhả. Ô DAC dùng giá trị "Mức DAC". Rê chuột lên ô để xem
    thanh ghi/bit.
  - **MUX**: chọn kênh cho từng bank (31 = hở hết), ghi rồi tự đọc lại sau `di_update_ms + mux_settle_ms`; hiển thị giá
    trị của tín hiệu gán cho kênh đó.
  - **DAC** (V theo hệ số giả định) và **DOUT** bit 0–9.
  - **Giá trị CPU đọc được**: ADC0–4 (V), điện trở, DIN, giờ cập nhật; nút Đọc và tự đọc (200–5000 ms, mặc định 500).
    Tự đọc là **đọc nền** (`request_stm32(background=True)`): không khóa nút, không đổi dòng trạng thái; lệnh bấm trong
    lúc đọc được xếp hàng và gửi ngay khi lượt đọc trả về (lượt đọc lỗi → hủy lệnh chưa gửi, đầu ra không đổi). Ô số cố
    định, chỉ vẽ lại khi giá trị đổi. Đọc nhanh hơn chu kỳ vòng lặp CPU (D02) chỉ lặp lại số cũ.
  - Lỗi/timeout giữa chuỗi: dừng, **không tự gửi lại**, trạng thái đầu ra thành "chưa biết". Ghi thanh ghi thô ở tab bên
    cạnh cũng làm trạng thái thành "chưa biết". ACK không chứng minh rơ-le đã đóng: kiểm bằng đồng hồ/đo ngược.
- **Thanh ghi CPU**: bảng hai mảng như hộp thoại ở bước 3 phía trên, theo bản đồ của profile. Tự đọc cũng là đọc nền;
  bấm "Gửi" trong lúc đọc nền thì lệnh ghi được gửi ngay sau lượt đọc.
- **Nhật ký**: các thao tác của công cụ và khung RTU TX/RX (cả COM ảo và COM thật, 500 khung gần nhất), xuất ra `.txt`.

Quy trình kiểm một rơ-le / một điểm giao matrix / một kênh MUX trên mạch: [04 Firmware](04_FIRMWARE_VA_PHAN_CUNG.md) mục 7, 10; đạt thì đổi `status`
mục tương ứng trong `hardware.json` thành `verified`.

## 3. Điều kiện chạy trên mạch thật (đã có trong phần mềm)

Phần mềm cho phép chạy trên COM thật khi đã xác minh CPU (FC03 lúc mở cổng). Điều kiện được **kiểm trong code**, không
bật bằng một cờ:

1. **Tự kiểm tra** (D01 truyền thông, D02 chu kỳ vòng lặp): chạy được ngay sau khi xác nhận; chỉ ghi trạng thái an toàn.
2. **Bài đo**: chỉ chạy khi
   - mọi ánh xạ bài dùng (output/pin, bo matrix, DAC, input) đã `verified` trong `hardware.json`
     (`profiles.stm32_unverified`);
   - D02 đạt **trên chính kết nối thật này** và chu kỳ đo được ≤ `di_update_ms / 2`;
   - người vận hành xác nhận hộp thoại "Chạy trên MẠCH THẬT".
3. Trên mạch thật: thời gian chờ **không** chia hệ số mô phỏng; phiên ghi `simulation: false`, `cpu_map`, sự kiện xác nhận.
   Lỗi giữa chừng → ERROR, không tự ghi lại trạng thái an toàn (dùng "Về an toàn" ở trang Test Modbus).
4. Trước khi đổi `verified`: dùng trang Test Modbus kiểm từng rơ-le nguồn, từng điểm giao matrix, từng kênh MUX bằng đồng
   hồ; đo bảng DAC; đối chiếu ADC với đồng hồ chuẩn; thử rút cáp/timeout; chạy D02 sau khi sửa firmware ([04 Firmware](04_FIRMWARE_VA_PHAN_CUNG.md) mục 9).
5. `production_ready` vẫn `false`: profile chưa được phê duyệt toàn bộ; việc mở từng bài dựa vào `verified` từng mục.
