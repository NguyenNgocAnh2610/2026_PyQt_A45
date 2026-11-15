# Tiến độ điều phối

Chỉ đánh dấu hoàn thành khi có kết quả review/kiểm thử. Mỗi task ghi người
thực thi, file thay đổi, lệnh xác minh và phần chưa kiểm chứng. Cập nhật bảng
tổng quan và ghi tóm tắt task cũ trước khi thay file giao việc hiện tại.

## Tổng quan

| Mã | Công việc | Thực thi | Trạng thái |
|---|---|---|---|
| SETUP-001 | Thiết lập tài liệu điều phối, đọc hiện trạng, kiểm tra CLI | Codex | Hoàn thành, đã gọi CLI bằng đường dẫn tuyệt đối |
| SKILL-001 | Đóng gói skill agy-orchestrator dùng thử trong repository | Codex | Hoàn thành đóng gói và kiểm tra cấu trúc |
| NEXT | Tính năng đầu tiên theo quy trình mới | Chưa phân công | Chờ người dùng giao |

## SETUP-001

- Phạm vi: tài liệu `orchestration/`, đường dẫn từ AGENTS.md/README; không đổi
  UI, phần cứng hay cấu hình ứng dụng.
- Đã đọc AGENTS.md, cây file và các entry point/preview/config hiện có.
- Đã tạo README (quy trình), PROJECT_CONTEXT (hiện trạng), task_for_agy (mẫu
  chưa sẵn sàng), PROGRESS (tiến độ); Codex trực tiếp viết vì đây là thiết lập
  điều phối và chưa tìm được agy.
- Kiểm tra ban đầu bằng tên `agy` trong terminal Codex báo CommandNotFoundException.
  Sau khi người dùng cung cấp đường dẫn, đã chạy thành công
  `& 'C:\Users\anh\AppData\Local\agy\bin\agy.exe' --help`, exit code 0.
- Đã xác minh cú pháp `--print` / `-p` chạy prompt qua terminal cùng các lựa chọn
  output và timeout. Lệnh mẫu đã được cập nhật trong README điều phối.
- Đăng nhập, quota và thực thi agent chưa được kiểm chứng, chờ task đầu tiên.
- Regression trong lượt thiết lập: `conda run -n qt_env python -m unittest
  discover -s tests -v` với Qt offscreen và thư mục font Windows: **21 test OK**.
  Đã kiểm tra liên kết tài liệu cục bộ và `git diff --check`.
- Giới hạn: chưa xác minh CLI/agent hoàn tất thực thi, chưa test phần cứng,
  chưa kiểm tra GUI desktop/DPI. Workspace hiện có thay đổi chưa commit do
  giai đoạn phát triển trước và chỉnh sửa người dùng; không coi chúng là
  thay đổi của SETUP-001.

## SKILL-001

- Người dùng yêu cầu đóng gói quy trình điều phối thành skill dùng thử trong
  dự án để chuyển sang global sau khi hoàn thiện.
- Codex trực tiếp viết theo skill-creator. Bản thử nghiệm nằm trong
  `skills/agy-orchestrator/`, gồm SKILL.md, agents/openai.yaml,
  references/agy-cli.md và assets/task-template.md.
- Skill lấy kiến trúc, môi trường và lệnh kiểm thử từ dự án đang làm.
  AGENTS.md dẫn đến skill, README điều phối có ví dụ gọi bằng đường dẫn.
- Đã chạy quick_validate.py trong qt_env với kết quả `Skill is valid!`.
  Metadata UI, các liên kết cục bộ và git diff --check đều hợp lệ.
- Đã tải PyYAML 6.0.3 vào `.tmp/skill-validation-deps` để chạy validator
  bằng Python của qt_env. Dependency kiểm tra này nằm trong thư mục tạm.
- Quy trình task thật qua agy cần được kiểm chứng ở tính năng tiếp theo.
  Bản skill trong `skills/` được gọi bằng đường dẫn hoặc chỉ dẫn AGENTS.md.
  Khả năng xuất hiện trong bộ chọn `$agy-orchestrator` phụ thuộc client nạp skill.

## Ghi nhận cho task tiếp theo

Codex đọc lại hiện trạng → điền task cụ thể → kiểm tra help CLI và giao agy
nếu khả dụng → review/test trong qt_env → cập nhật kết quả. Chưa có lựa chọn
tính năng tiếp theo; không tự triển khai tầng backend hoặc màn hình mới.
