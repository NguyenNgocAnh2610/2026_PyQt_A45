# Token, quota, cost: nguyên tắc không đoán

1. **Usage thật**: CLI có thể báo input/output tokens trên từng lượt. Script cộng các event `turn.completed` (Codex) hoặc `usage` (Antigravity JSON). Nếu dữ liệu vắng: `usage = unknown`, không báo bằng 0.
2. **Quyền dùng còn lại**: subscription quota, rate limit, rolling windows hay credit balance thường **không tương đương** với tổng token đã dùng. `remaining_quota_tokens` chỉ là một giá trị người dùng cập nhật, không phải API kiểm tra quota. Để null khi không biết.
3. **Bảo lưu trước khi chạy**: `estimate_tokens` ≤ `per_task_estimate_cap_tokens`; tổng `observed usage + estimate` ≤ `session_soft_budget_tokens` (local ledger); nếu `remaining_quota_tokens` do người dùng xác thực nhập vào thì estimate ≤ phần còn lại sau usage. Ước tính chỉ là ước tính, có thể bị vượt trong run; không phải hard stop theo từng token.
4. **Đặt timeout và số lượt lặp**. Timeout trong script giới hạn thời gian subprocess; không giới hạn lượng token trước thời điểm timeout. Đầu ra log cục bộ, không đồng bộ Git mặc định.
5. **Cấu hình model per provider**. Chạy `agy models` để chọn slug đúng; Codex dùng model đã được tài khoản và CLI hỗ trợ. Nếu model rỗng, CLI dùng mặc định; báo model thực tế *không xác nhận* trừ khi metadata cho phép.
6. **Claude**: script không đọc quota nội bộ của phiên Claude; Claude cần cân nhắc context còn lại, compact/đổi session nếu cần; không hứa chính xác số token hoặc phí còn lại.
7. **Hai máy**: ledger và tài khoản có thể chung quota nhưng ledger cục bộ không đồng nhất. Nếu dùng đồng thời, tự quản lý ngân sách provider ở cấp tài khoản hoặc dùng quota API chính thức nếu có; đừng cộng hai ledger rồi coi là quota thật.

Khuyến nghị khởi đầu `session_soft_budget_tokens` thấp vừa phải, `remaining_quota_tokens: null`. Không nâng mức giới hạn mà không được người dùng cho phép. Kết quả `doctor` không xác thực quyền truy cập model.
