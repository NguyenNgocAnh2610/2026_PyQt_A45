# Worktree, tránh xung đột và chuyển hai máy

**Mặc định: chạy tuần tự** trên workspace sạch; giữ mọi thay đổi của người dùng. Trước tác vụ kiểm tra `git status --short` và diff liên quan. Nếu repo có thay đổi chưa commit, phải tránh ghi đè.

**Song song:** tạo branch/worktree riêng trên cùng máy (chỉ khi git repo đã chuẩn bị và người dùng cho phép):

```bash
git worktree add ../repo-antigravity -b agent/T-101-antigravity
git worktree add ../repo-codex -b agent/T-102-codex
```

Chạy orchestrator CLI tại root của worktree tương ứng, nghĩa là skill và config phải tồn tại trên branch đã checkout, hoặc dùng tuyệt đối đường dẫn script của repo gốc nhưng `--project-root` chỉ đúng worktree. Mỗi task chỉ được phép sửa file đã định. Claude xem diff hai nhánh, test, rồi cherry-pick hoặc merge theo quy trình repo; **không merge tự động**. Không để hai workers viết cùng file `PROGRESS.md`.

**Hai máy:** coi code + `AGENTS.md` + `PROGRESS.md` + skill + config chung là dữ liệu versioned; không đồng bộ token ledger/log/secret; `git pull --ff-only` trước phiên mới. Chỉ có một orchestrator viết branch chính trong một thời điểm. Nếu hai máy làm song song, sử dụng hai branch và PR. Không ghi checkpoint chưa xác minh vào trạng thái hoàn thành.
