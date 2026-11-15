# Điều phối dự án 2026_PyQt_A45

Quy trình tái sử dụng được đóng gói trong
[skill agy-orchestrator](../skills/agy-orchestrator/SKILL.md). Bản dùng thử
đang lưu tại `skills/agy-orchestrator/` trong repository. Có thể yêu cầu Codex
đọc file đó bằng đường dẫn và áp dụng cho task hiện tại. AGENTS.md cũng dẫn
đến skill khi nhận công việc điều phối. Tên `$agy-orchestrator` dùng được
khi client đã nạp skill vào danh sách khả dụng.

Ví dụ yêu cầu dùng bản thử nghiệm trong repository hiện tại.

```text
Đọc skills/agy-orchestrator/SKILL.md và áp dụng quy trình đó để triển khai [yêu cầu tính năng].
```

Khi đưa sang global, chuyển cả thư mục skill vào vị trí skill cá nhân mà
client đang dùng. Các tài liệu trong `orchestration/` tiếp tục quản lý thông
tin riêng của dự án. Skill lấy môi trường và kiến trúc từ AGENTS.md đang áp dụng.

Codex giữ vai trò Tech Lead/System Architect: phân tích yêu cầu, xác định API và
phạm vi thay đổi, giao việc cho Antigravity CLI (`agy`), review và tự chạy kiểm
thử trước khi nghiệm thu. Codex có thể trực tiếp xử lý phần quan trọng/phức tạp,
hoặc tiếp quản khi agy hết quota, không khả dụng hay không giải quyết được lỗi;
ghi rõ lý do và người thực thi trong tiến độ.

## Tài liệu cần đọc

1. [AGENTS.md](../AGENTS.md) ở thư mục gốc là nguồn quy tắc kỹ thuật.
2. [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md) ghi hiện trạng và các quyết định đã chốt.
3. [PROGRESS.md](PROGRESS.md) ghi trạng thái công việc, kiểm chứng và vướng mắc.
4. [task_for_agy.md](task_for_agy.md) là yêu cầu thực thi hiện tại.

Tài liệu điều phối bổ sung cách làm việc, không thay thế AGENTS.md. Khi ngữ cảnh
thay đổi, kiểm tra code và yêu cầu mới nhất của người dùng; không dựa vào mô tả
cũ để khẳng định một tính năng đã tồn tại.

Chỉ dùng một file giao việc hiện tại tại `orchestration/task_for_agy.md`, không
tạo bản trùng ở gốc. Đây là cách tổ chức tập trung theo yêu cầu của chủ dự án.
Không tạo thêm backlog, biên bản, thư mục hay module rỗng khi chưa có nhu cầu.

## Quy trình 5 bước cho mỗi tính năng/sửa lỗi

### 1. Đọc ngữ cảnh và thiết kế

- Đọc AGENTS.md, tiến độ và các file UI/style/test liên quan.
- Xem `git status --short`, `git diff` và file chưa track có liên quan để nhận
  biết thay đổi sẵn có. Ghi nhận trước khi giao việc; không reset/clean/ghi đè
  thay đổi của người dùng. Không coi toàn bộ diff sau chạy là do agy tạo.
- Trình bày ngắn giải pháp: file sửa/tạo, API/class/signal/slot nếu cần, dữ liệu
  giả hay thật và tiêu chí nghiệm thu. Tiếp tục trong phạm vi đã được giao;
  chỉ hỏi khi thiếu lựa chọn ảnh hưởng thực sự đến thiết kế/hardware.
- Chia task theo kết quả kiểm chứng được. Mặc định một bên viết code tại một
  thời điểm trên workspace chung; Codex không sửa cùng file khi agy đang chạy.

### 2. Viết file giao việc

Điền đầy đủ `task_for_agy.md`: mã task, yêu cầu người dùng, file được sửa, các
thay đổi sẵn có cần giữ, API và kiểu dữ liệu, trạng thái/timeout/cleanup nếu có,
preview/test, điều kiện hoàn thành và nơi ghi kết quả. Dùng đường dẫn thực.
Chỉ giao khi trạng thái task là **Sẵn sàng**; không thực thi phần mẫu chưa điền.
Trước khi ghi đè task cũ, ghi tóm tắt kết quả và giới hạn vào PROGRESS.md.

### 3. Gọi agy qua terminal

Chạy từ gốc repository, kiểm tra công cụ trước:

```powershell
Get-Command agy -ErrorAction SilentlyContinue
agy --help
```

Đã xác minh executable tại `C:\Users\anh\AppData\Local\agy\bin\agy.exe`.
Phiên terminal Codex hiện có thể gọi trực tiếp đường dẫn này. Help của bản
đang cài hỗ trợ `--print` (alias `-p`, `--prompt`) để chạy một prompt và trả
kết quả. Khi task đã được điền, có thể giao bằng lệnh sau từ gốc repository.

```powershell
& 'C:\Users\anh\AppData\Local\agy\bin\agy.exe' --print 'Hãy đọc AGENTS.md và orchestration/task_for_agy.md, thực hiện yêu cầu trong phạm vi task và ghi kết quả vào mục 6 của file giao việc.'
```

Help cũng có `--output-format` với `text`, `json`, `stream-json` và
`--print-timeout` (mặc định `0s`, chờ turn hoàn tất). Việc đăng nhập, quota và
khả năng thực thi agent sẽ được kiểm chứng khi giao task đầu tiên.

Chỉ dùng subcommand/flag thực sự xuất hiện trong help của bản đang cài.
Không mặc định `--file` hay `-p` tồn tại. Nếu help có subcommand chat/agent,
đọc tiếp help của subcommand đó. Prompt phải yêu cầu đọc AGENTS.md và
`orchestration/task_for_agy.md`, chỉ làm trong phạm vi task.

Nếu tên lệnh không có trong PATH, kiểm tra đường dẫn cài cụ thể đã biết hoặc
dùng đường dẫn tuyệt đối do người dùng cung cấp. Không tự cài/cấu hình lại công
cụ hay dùng executable khác mà đoán là tương đương. Không tự bật chế độ bỏ qua
phê duyệt/sandbox. Ghi lệnh thực tế và kết quả vào PROGRESS.md.

Nếu CLI chỉ mở IDE/chat và trả về ngay, việc tiến trình launcher kết thúc không
có nghĩa là agent đã hoàn thành. Chỉ nghiệm thu khi có kết quả thực thi và diff
thực tế; không báo thành công chỉ dựa vào exit code. Chờ/poll có giới hạn và
cập nhật người dùng trong lúc chạy. Nếu agy không dùng được, Codex tiếp tục
phần đã được giao nếu đủ thông tin và báo rõ việc tiếp quản.

### 4. Review và kiểm thử độc lập

- Đọc từng file đã thay đổi; đối chiếu phạm vi task và thay đổi sẵn có, gồm cả
  file mới chưa track. `git diff --check` để kiểm tra lỗi khoảng trắng.
- Review theo AGENTS.md: UI → backend → device → communication/protocol; một
  nguồn trạng thái; không I/O/chờ trên GUI thread; timeout và cleanup hữu hạn;
  không tự retry lệnh tác động thiết bị; không giả định giao thức/địa chỉ.
- Theme chung nạp ở QApplication, QSS riêng có phạm vi; preview dùng dữ liệu
  giả. Chỉ tách hằng số theo nhu cầu cấu hình/dùng chung thực tế.
- Tự chạy test phù hợp trong `qt_env`. Chạy bộ regression khi thay đổi có ảnh
  hưởng chung hoặc cần nghiệm thu tổng thể:

```powershell
conda run -n qt_env python -m unittest discover -s tests -v
conda run -n qt_env python -m tests.preview_login
conda run -n qt_env python -m tests.preview_widgets
```

Kiểm thử không cần desktop có thể dùng `QT_QPA_PLATFORM=offscreen` trong shell
chỉ chạy test. Preview tương tác chạy ở shell bình thường; không coi offscreen
là bằng chứng đã kiểm tra desktop/DPI. Không chạy Python hệ thống/base.

Ghi rõ lỗi review/test vào task, chuyển sang **Cần sửa** và giao lại agy bằng
cú pháp đã xác minh. Sau sửa chạy lại phần liên quan. Nếu cùng lỗi lặp lại,
agy hết quota hoặc không tiến triển, Codex chẩn đoán và tiếp quản; không lặp
CLI vô hạn. Không yêu cầu người dùng xác nhận lại các sửa lỗi trong phạm vi.

### 5. Cập nhật và bàn giao

Chỉ Codex chuyển task sang **Hoàn thành** sau audit. Cập nhật PROGRESS.md với
người thực thi, file sửa, lệnh và kết quả kiểm thử, giới hạn còn lại. Nếu có
thay đổi kiến trúc đã chốt, cập nhật PROJECT_CONTEXT.md; nếu đổi cách chạy,
cập nhật README dự án. Báo ngắn kết quả, lệnh chạy và phần chưa kiểm chứng.

Không tự commit/push hoặc thao tác thiết bị thật nếu chưa được giao quyền
tương ứng. Các thông số phần cứng chưa có phải được cấu hình/TODO rõ ràng.
