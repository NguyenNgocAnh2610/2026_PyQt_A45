# Gọi Antigravity CLI

## Tìm công cụ và xác minh cú pháp

Trên PowerShell, tìm executable qua môi trường hiện tại.

```powershell
Get-Command agy -ErrorAction SilentlyContinue | Format-List Name,Source,Definition
agy --help
```

Nếu PATH của terminal chưa cập nhật, dùng đường dẫn tuyệt đối do người dùng
cung cấp hoặc đã xác minh trong cấu hình dự án. Tên executable có thể là
`agy.exe`. Ghi đường dẫn riêng của máy vào tài liệu dự án hoặc giữ trong
ngữ cảnh phiên. Khi làm trên hệ điều hành khác, dùng cơ chế tìm lệnh tương ứng.

Đọc help của executable đang chạy trước khi chọn flag. Trên bản đã kiểm tra
ở dự án thử nghiệm, `--print` có alias `-p` và `--prompt`, chạy một prompt và
trả phản hồi về terminal. `--output-format` hỗ trợ `text`, `json`, `stream-json`.
`--print-timeout` mặc định `0s`, chờ turn hoàn tất. Kiểm tra lại các giá trị này
khi đổi bản CLI hoặc có thông báo flag không hợp lệ.

## Giao một task

Ví dụ dưới đây áp dụng khi help đã xác nhận `--print`. Chạy từ gốc dự án,
điền file giao việc bằng yêu cầu cụ thể trước khi gửi prompt.

```powershell
agy --print 'Đọc AGENTS.md áp dụng cho dự án và orchestration/task_for_agy.md. Thực hiện task trong phạm vi đã giao, giữ thay đổi sẵn có của người dùng và ghi kết quả vào mục Kết quả thực thi. Báo rõ lỗi hoặc giới hạn còn lại.'
```

Nếu dự án có vị trí task hoặc tên mục kết quả riêng, điều chỉnh prompt theo
file thực tế. Khi gọi bằng đường dẫn tuyệt đối, dùng toán tử `&` của PowerShell.
Truyền prompt như đối số dữ liệu có quoting phù hợp với shell. Giữ nội dung
task dài trong file để tránh lỗi escape và dễ review.

Tái sử dụng thiết lập model/agent của người dùng khi chưa có yêu cầu đổi.
Các chế độ quyền thao tác tuân theo môi trường và quyền của task. Nếu có lỗi
phê duyệt/sandbox, xử lý bằng luồng cấp quyền hiện có hoặc báo vướng mắc.

## Theo dõi và thu kết quả

- Giữ session/process ID do công cụ terminal trả để theo dõi tiến trình thực tế.
- Khi nhận lỗi khởi chạy, đọc thông báo và kiểm tra executable/flag/cwd liên quan.
- Khi CLI báo đăng nhập, quota hoặc lỗi dịch vụ, ghi đúng loại lỗi. Chỉ retry
  khi có căn cứ lỗi tạm thời, đồng thời kiểm tra file đã thay đổi để tránh làm
  lại thao tác có tác dụng phụ.
- Nếu nghi tiến trình chờ nhập quyền, kiểm tra output và trạng thái session.
  Dùng tương tác terminal khi có thể và trong phạm vi quyền đã được giao.
- Nếu CLI chỉ mở IDE/chat, theo dõi kết quả agent bằng cơ chế được công cụ
  cung cấp. Kết quả nghiệm thu cần có output và thay đổi thực tế đối chiếu task.
- Trước khi Codex sửa trực tiếp, bảo đảm phiên agy đã kết thúc hoặc được dừng.

Sau khi agent hoàn thành, Codex review và chạy kiểm tra bằng môi trường dự án.
Exit code, nội dung phản hồi, diff và kết quả test đều là dữ liệu cần đối chiếu.
