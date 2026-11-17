# Định tuyến task: độ phức tạp + hậu quả

## Trình tự đánh giá
1. **Risk gate trước**: Nếu đụng tới secrets, auth, permission, data loss, destructive schema changes, production deploy, firmware/điều khiển phần cứng thật, điện áp/thiết bị, bảo mật hoặc thay đổi giao thức có hậu quả: **CRITICAL → Claude**, dù sửa một dòng. Chỉ được giao worker lập phương án/read-only nếu không lộ dữ liệu nhạy cảm.
2. Nếu không critical, đánh giá: phạm vi thay đổi, độ bất định, phụ thuộc xuyên module, độ khó test, khả năng rollback. Mỗi tiêu chí 0–2 điểm (0 thấp, 2 cao).
3. 0–3: SIMPLE → Antigravity. 4–6: MODERATE → Codex. 7–10: COMPLEX → Claude. Claude được nâng mức nếu task không thể xác minh hoặc có hệ quả kiến trúc.
4. Nếu worker/model không khả dụng hoặc quota thiếu: **không tự dùng worker ngoài quyền**, chuyển hướng có giải thích. Với task rất đơn giản mà delegation overhead cao, Claude có thể làm trực tiếp.

## Model tier theo mục tiêu
- fast: thao tác đơn giản, prompt ngắn, thay đổi nhỏ.
- balanced: phát triển, test, debug liên module.
- strong: nghiên cứu kiến trúc, review quan trọng, rủi ro và độ bất định cao.
- Các model ID thuộc **cấu hình runtime**, không cố định trong skill. Không được tự phỏng đoán tier có quota cao hơn.
- Claude session: sử dụng model hiện tại nếu đủ chất lượng; khi cần model mạnh hơn, đề xuất người dùng dùng `/model` hoặc đổi phiên. Có thể dùng Claude subagents nội bộ nếu thích hợp, nhưng phải xem chúng là tác vụ tiêu token/quota của Claude.

## Quyền hạn
- Claude: task planning, route, cross-module integration, risk review, progress, acceptance.
- Antigravity: task scope rất cụ thể, review nhẹ, test khi được phép; không quản lý repo.
- Codex: implementation/debug có kiểm thử; không tự nhận task mới.
- Cả hai worker: không push, không commit, không đổi cấu trúc/lộ credentials hoặc ghi PROGRESS.md (Claude giữ quyền này).

## Ví dụ xuyên dự án
- Sửa tooltip, lỗi chính tả UI, đơn vị test cục bộ: SIMPLE/Antigravity.
- Thêm API endpoint + validation + tests, refactor service, lỗi async: MODERATE/Codex.
- Chọn ranh giới service, migration DB production, thay đổi bootloader, control loop thời gian thực, tác động hardware: COMPLEX/CRITICAL/Claude.
