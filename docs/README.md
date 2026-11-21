# Mục lục tài liệu kỹ thuật

Mọi tài liệu tham khảo của project nằm trong `docs/`. Ở gốc repo chỉ có `README.md` (cài đặt, chạy), `AGENTS.md` (quy tắc
bắt buộc), `CLAUDE.md` (hướng dẫn cho AI) và `PROGRESS.md` (hiện trạng, việc tiếp theo, lịch sử — nhật ký duy nhất).

## Danh sách tài liệu

| File | Nội dung | Đọc khi |
|---|---|---|
| [01_KIEN_TRUC_PHAN_MEM.md](01_KIEN_TRUC_PHAN_MEM.md) | Thư mục, các tầng, khởi động, ai sở hữu ai, máy trạng thái chạy bài, giao diện cập nhật, nơi lưu dữ liệu, **muốn sửa X thì vào đâu** | Bắt đầu đọc code |
| [02_GIAO_THUC_MODBUS.md](02_GIAO_THUC_MODBUS.md) | Hợp đồng Modbus RTU PC ↔ CPU STM32: đường truyền, mã hàm, khung byte, hai mảng thanh ghi (CPUv1.0/CPUv1.1), mã hóa dữ liệu, quy tắc giao dịch, ví dụ CRC; phụ lục giao thức A45 v1 cũ | Làm việc với khung truyền, thanh ghi |
| [03_LUONG_MODBUS_TRONG_CODE.md](03_LUONG_MODBUS_TRONG_CODE.md) | Hàm gửi (TX) và nhận (RX), bộ chạy bài và các loại thao tác, ví dụ một bước đo, COM ảo, log, debug, tùy biến khung, kiểm thử | Sửa/debug phần truyền nhận |
| [04_FIRMWARE_VA_PHAN_CUNG.md](04_FIRMWARE_VA_PHAN_CUNG.md) | Firmware CPU (vòng lặp, chu kỳ, bus tới bo con, ngoại vi, chế độ HMI, stack slave), điều khiển một đầu ra, đề xuất sửa firmware, **bảng phân bổ bit A45 để đi dây**, firmware bo con | Đi dây, sửa firmware, chỉnh thời gian chờ |
| [05_VAN_HANH_GIAO_DIEN.md](05_VAN_HANH_GIAO_DIEN.md) | Thanh kết nối, bảng hai mảng thanh ghi, trang Test Modbus, điều kiện chạy trên mạch thật | Vận hành, kiểm từng rơ-le/kênh |
| [06_CAU_HINH_PROFILE.md](06_CAU_HINH_PROFILE.md) | Tham chiếu schema các file JSON trong `configs/<giá_thử>/`, quy tắc đánh giá, hiện trạng profile A45 | Sửa cấu hình, bài đo |
| [07_CHUYEN_GIA_THU_MOI.md](07_CHUYEN_GIA_THU_MOI.md) | Quy trình từng bước chuyển phần mềm sang giá thử/khối mới | Làm giá thử mới |

Tài liệu nguồn (**giữ nguyên nội dung**, chỗ sai được hiệu chỉnh ở tài liệu khác):

| File | Nội dung |
|---|---|
| [nguon/BAI_KIEM_TRA_1101K.md](nguon/BAI_KIEM_TRA_1101K.md) | 24 bài kiểm tra khối 1101K-10 (yêu cầu đo gốc) |
| [nguon/PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md](nguon/PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md) | Phân tích firmware CPUv1.0 của giá thử cũ (ví dụ CRC trong đó có chỗ sai, xem 02 mục 6) |

Báo cáo theo ngày (ảnh chụp tại thời điểm viết, không cập nhật về sau; kết luận còn hiệu lực đã/sẽ chuyển vào 01–07 hoặc
`PROGRESS.md`):

| File | Nội dung |
|---|---|
| [bao_cao/2026-11-19_RA_SOAT_TRUOC_CHAY_THAT.md](bao_cao/2026-11-19_RA_SOAT_TRUOC_CHAY_THAT.md) | Rà soát trước khi chạy mạch thật: đủ phần cứng cho 24 bài chưa, hướng mở rộng 4 bo matrix, đề xuất sửa PC/firmware, câu hỏi chờ trả lời |

## Thứ tự đọc theo vai trò

- **Người vận hành:** 05 → (khi cần) 04 mục 10 (bảng đi dây).
- **Người sửa code PC:** 01 → 03 → 02 (tra khung/thanh ghi khi cần) → 06.
- **Người đi dây / sửa firmware:** 04 → 02 mục 3 (bản đồ thanh ghi) → 05 mục 2 (trang Test Modbus để kiểm).
- **Người làm giá thử mới:** 07 → 06 → 04.

## Quy ước

- **Một nội dung chỉ ở một nơi.** Tài liệu khác liên kết tới, không chép lại. Ví dụ: schema JSON chỉ ở 06; cấu trúc byte của
  khung chỉ ở 02; chuỗi hàm trong code chỉ ở 01/03; firmware chỉ ở 04.
- **Tên file:** `NN_TEN_KHONG_DAU.md`, số `NN` theo thứ tự đọc; tài liệu nguồn trong `nguon/` giữ nguyên tên; báo cáo trong
  `bao_cao/` đặt `YYYY-MM-DD_TEN.md`.
- **Tham chiếu chéo:** ghi dạng "[04 Firmware](04_FIRMWARE_VA_PHAN_CUNG.md) mục 2". Trong cùng file chỉ ghi "mục 2".
- **Mục lục:** mỗi tài liệu dài có `## Mục lục` ngay sau phần giới thiệu; thêm/đổi tiêu đề thì cập nhật mục lục (liên kết
  dạng anchor của GitHub: chữ thường, bỏ dấu câu, khoảng trắng thành `-`).
- Viết tiếng Việt. Số dòng mã (`file.py:123`) chỉ đúng tại ngày viết; tìm theo tên hàm khi mã đã đổi.
- Lịch sử đổi tên: 2026-11-21 gom `STM32_MODBUS_PC.md` + `LUONG_CODE_VA_MODBUS.md` thành 01–05; `CONFIGURATION.md` →
  06; `CHUYEN_GIA_THU_MOI.md` → 07; tài liệu nguồn vào `nguon/`; báo cáo rà soát vào `bao_cao/`.
