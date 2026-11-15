# File giao việc hiện tại cho Antigravity

Trạng thái: **Chờ yêu cầu** — CHƯA giao thực thi.
Mã task: Chưa cấp.
Người thiết kế/nghiệm thu: Codex.
Người thực thi dự kiến: agy; Codex có thể tiếp quản theo quy trình.

File này là mẫu chờ tính năng đầu tiên; không triển khai các chỗ chưa điền.
Codex điền lại nội dung cụ thể rồi đổi trạng thái thành **Sẵn sàng** trước
khi gọi CLI. Các trạng thái: Chờ yêu cầu → Sẵn sàng → Đang làm → Chờ review
→ Cần sửa (nếu có) → Hoàn thành. Có thể ghi **Vướng mắc** kèm nguyên nhân.

## 1. Bối cảnh và yêu cầu

- Đọc đầy đủ `AGENTS.md` tại gốc trước khi sửa.
- Đọc `orchestration/README.md` và `orchestration/PROJECT_CONTEXT.md`.
- Yêu cầu nguyên văn và kết quả mong muốn: [Codex điền theo task].
- Trong phạm vi: [điền]. Ngoài phạm vi: [điền các thay đổi dễ bị làm quá].
- Các giả định đã thống nhất và thông tin còn thiếu: [điền].

## 2. Phạm vi file và nền thay đổi hiện tại

| File cụ thể | Đọc / sửa / tạo | Thay đổi cần làm | Thay đổi sẵn có phải giữ |
|---|---|---|---|
| [Codex điền] | | | |

Đọc file trước khi sửa. Không reset/clean, không tự commit/push, không sửa
ngoài phạm vi hoặc ghi đè thay đổi người dùng. Không tạo module rỗng, tầng
trung gian hay dependency nếu không cần thiết để hoàn thành task.

## 3. Thiết kế kỹ thuật

- Class/hàm/API, tham số/giá trị trả về: [điền tên, kiểu và trách nhiệm].
- Signal/Slot/Property cần thêm, kiểu dữ liệu và chủ sở hữu: [điền hoặc không áp dụng].
- Luồng UI → backend → device → communication/protocol: [điền nếu liên quan].
- Trạng thái ban đầu, xác nhận, pending, lỗi, stale/mất kết nối: [điền nếu liên quan].
- Timeout, worker, hủy yêu cầu, đóng ứng dụng: [điền nếu liên quan].
- Nạp common QSS, phạm vi objectName/property, style riêng: [điền].
- Preview độc lập và đăng ký `PAGE_PREVIEWS`: [điền nếu có UI].
- Tương thích API đang dùng và dữ liệu cấu hình: [điền].

UI không I/O UART/Modbus; không polling/chờ/xử lý nặng trên GUI thread.
Backend là nguồn trạng thái duy nhất; gửi lệnh thành công không đồng nghĩa
thiết bị đã xác nhận. Một chủ sở hữu serial tuần tự hóa giao dịch; không tự
retry lệnh tác động thiết bị. Không tự đổi register, baudrate hay giao thức.
Không đặt mật khẩu thật trong code/log. Hằng số chỉ tách khi cần cấu hình theo
giá thử hoặc dùng thực sự xuyên module; widget phụ của một trang giữ gọn tại trang.

## 4. Tiêu chí nghiệm thu và kiểm thử

- Hành vi thành công: [điền điều kiện có thể quan sát].
- Đầu vào sai/lỗi/timeout/mất kết nối: [điền ca thực sự liên quan].
- Bàn phím/resize/style/cleanup: [điền ca UI liên quan].
- Test tự động cần thêm/sửa: [điền file và ý nghĩa, không test chỉ lặp implementation].
- Lệnh kiểm tra cụ thể: [điền]. Mọi lệnh Python phải dùng môi trường `qt_env`.

```powershell
conda run -n qt_env python -m unittest discover -s tests -v
```

Không có `qt_env` hoặc thiếu dependency: báo rõ, không chuyển Python/base hay
tự tạo lại môi trường. Chỉ dùng mock/preview khi chưa có thiết bị và quyền thao
tác; không khẳng định test phần cứng thật. Không tuyên bố hoàn thành nếu còn lỗi.

## 5. Vòng sửa sau audit

- Lỗi Codex phát hiện, file/dòng, bước tái hiện, kết quả mong đợi: [điền].
- Chỉ sửa các lỗi này và phần cần thiết liên quan; giữ các hành vi đã nghiệm thu.
- Test cần chạy lại: [điền].

## 6. Kết quả agy cần trả

Ghi vào mục này khi thực thi: file đã tạo/sửa, giải thích ngắn thiết kế, lệnh
đã chạy và kết quả thực tế, lỗi còn lại, giới hạn chưa kiểm chứng. Đặt trạng
thái **Chờ review**, để Codex kiểm tra độc lập và cập nhật PROGRESS.md.

Kết quả hiện tại: Chưa gọi agy, chưa có tính năng được giao.
