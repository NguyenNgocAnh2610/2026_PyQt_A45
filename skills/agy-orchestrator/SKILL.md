---
name: agy-orchestrator
description: Coordinate software implementation with Codex as technical lead and Antigravity CLI (agy) as implementer. Use when the user requests agy delegation, lead-led feature development, or reviewing and repairing work delegated to agy across a repository.
---

# Codex và Antigravity

Điều phối yêu cầu phát triển phần mềm từ thiết kế đến nghiệm thu. Codex chịu
trách nhiệm giải pháp, phạm vi giao việc và kết quả cuối cùng. Ưu tiên giao phần
triển khai phù hợp cho agy. Codex có thể trực tiếp xử lý phần quan trọng/phức
tạp, công việc tạo skill, hoặc tiếp quản khi agy lỗi, hết quota hay thiếu khả
năng thực thi. Ghi rõ người thực thi và lý do tiếp quản trong kết quả.

## 1. Đọc dự án và xác định phạm vi

- Đọc AGENTS.md áp dụng cho workspace và các thư mục sắp sửa, hướng dẫn chạy,
  code và test liên quan. Lấy kiến trúc, môi trường, package manager và lệnh
  kiểm tra từ dự án hiện tại.
- Đọc tài liệu hiện trạng/tiến độ nếu dự án có. Đối chiếu code khi tài liệu
  khác thực tế, giữ yêu cầu mới nhất của người dùng làm căn cứ.
- Kiểm tra git status/diff và các file mới liên quan. Ghi nhận thay đổi sẵn có
  để đánh giá phần agy thực sự tạo ra sau khi chạy.
- Trình bày ngắn kết quả cần đạt, file dự kiến sửa, API/hành vi và cách kiểm
  chứng. Tiếp tục theo quyền đã có, chỉ hỏi khi thiếu thông tin quyết định.
- Chia công việc theo kết quả có thể nghiệm thu. Phân công quyền sửa file rõ
  ràng khi dùng chung workspace, tránh hai bên ghi cùng một file đồng thời.

## 2. Chuẩn bị task cụ thể

Dùng file giao việc của dự án nếu đã có. Khi cần khởi tạo file mới, dùng
[mẫu task](assets/task-template.md) và điền bằng thông tin đã kiểm tra.
Với dự án chưa quy định vị trí, có thể dùng `orchestration/task_for_agy.md`.
Điền các phần áp dụng và bỏ phần thừa để task vừa đủ cho yêu cầu hiện tại.

Task cần mô tả hành vi mong đợi, phạm vi file, thay đổi người dùng cần giữ,
thiết kế/API, môi trường chạy, tiêu chí nghiệm thu và kiểm tra liên quan.
Truyền các quy tắc từ AGENTS.md cùng giới hạn quyền thao tác cho agy.
Ghi tóm tắt task cũ vào tiến độ trước khi dùng lại file giao việc.

## 3. Giao agy và theo dõi

Đọc [hướng dẫn CLI](references/agy-cli.md) trước khi gọi agy lần đầu trong
phiên hoặc khi gặp lỗi khởi chạy. Xác minh executable và flag bằng help thực
tế. Gọi từ thư mục dự án với đường dẫn task rõ ràng trong prompt.

Ghi lệnh đã chạy và theo dõi tiến trình đến khi nhận kết quả hoặc lỗi xác
định. Khi công cụ trả session ID, tiếp tục poll session theo API công cụ và
cập nhật người dùng khi có thay đổi. Kiểm tra output và diff để xác định
công việc đã được thực hiện.

Nếu đang có sửa file, hãy chờ tiến trình kết thúc hoặc dừng nó có kiểm soát
trước khi tiếp quản. Với lỗi quyền, đăng nhập hoặc quota, xác định nguyên nhân
và xử lý trong phạm vi được phép. Khi đủ thông tin để Codex tiếp tục phần đã
được giao, tiếp quản và báo rõ tình trạng agy.

## 4. Review và sửa đến khi đạt

- Đọc các file thay đổi và file mới, đối chiếu với task và nền thay đổi ban đầu.
- Kiểm tra API hiện có, các đường chạy thực tế, quy tắc kiến trúc của dự án,
  xử lý lỗi, vòng đời tài nguyên và độ gọn của giải pháp.
- Tự chạy các kiểm tra phù hợp với thay đổi bằng môi trường dự án quy định.
  Thêm test khi yêu cầu dự án hoặc nguy cơ hồi quy cụ thể cần đến.
- Với thay đổi UI, chạy preview/chụp ảnh nếu công cụ cho phép và kiểm tra
  tương tác liên quan. Ghi rõ phần desktop, DPI hoặc phần cứng còn chưa thử.

Nếu còn lỗi, bổ sung bước tái hiện, file liên quan, kết quả mong đợi và test
cần chạy lại vào task rồi giao sửa. Chọn sửa trực tiếp khi vấn đề phức tạp
hoặc agy tiếp tục lặp cùng lỗi và Codex có thể giải quyết. Kết thúc vòng sửa
khi đáp ứng tiêu chí, hoặc khi có vướng mắc cụ thể cần đầu vào/quyền mới.
Khi bị vướng, ghi rõ phần đã làm và bước cần thiết để tiếp tục.

## 5. Nghiệm thu và cập nhật

Codex quyết định hoàn thành sau review và kiểm chứng. Cập nhật file tiến độ
đang có hoặc tóm tắt kết quả cho người dùng. Cập nhật hiện trạng/hướng dẫn
dự án khi thay đổi làm nội dung đó cần điều chỉnh.

Bàn giao các file đã sửa, hành vi mới, người thực thi, lệnh và kết quả kiểm
tra thực tế, cùng phần chưa kiểm chứng. Phân biệt kết quả agy báo với kiểm
tra Codex đã tự chạy. Giữ các hành động tác động hệ thống ngoài phạm vi task
theo quyền cụ thể mà người dùng đã cấp.
