#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ -t 1 ]]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

info() { printf '%b[INFO]%b %s\n' "$BLUE" "$NC" "$*"; }
ok()   { printf '%b[OK]%b %s\n' "$GREEN" "$NC" "$*"; }
warn() { printf '%b[WARN]%b %s\n' "$YELLOW" "$NC" "$*"; }
err()  { printf '%b[ERROR]%b %s\n' "$RED" "$NC" "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
Cách dùng trên Ubuntu/Linux: bash ./git_daily.sh <lệnh> [tham số]
Ubuntu/Linux: chạy các lệnh bên dưới trong Terminal tại thư mục project.
Windows 11: dùng PowerShell và file git_daily.ps1.

Các lệnh:
  init                     Khởi tạo Git trong thư mục project, dùng nhánh main
  status | -s              Xem trạng thái, nhánh hiện tại và remote
  remote <GitHub URL>      Thêm hoặc cập nhật remote tên origin
  commit "nội dung"        Stage toàn bộ thay đổi và tạo commit
  pull                     Lấy thay đổi mới về (chỉ fast-forward, không ghi đè)
  push                     Đẩy nhánh hiện tại lên origin
  help | -h                Hiển thị hướng dẫn

Ví dụ:
  bash ./git_daily.sh init
  bash ./git_daily.sh remote https://github.com/NguyenNgocAnh2610/2026_PyQt_A45.git
  bash ./git_daily.sh status
  bash ./git_daily.sh commit "Thêm giao diện đăng nhập"
  bash ./git_daily.sh push
EOF
}

require_git() {
    command -v git >/dev/null 2>&1 || err "Không tìm thấy Git. Hãy cài Git rồi mở lại Terminal."
}

require_repo() {
    require_git
    local prefix
    prefix="$(git -C "$ROOT_DIR" rev-parse --show-prefix 2>/dev/null)" ||
        err "Chưa có Git repository. Hãy chạy: bash ./git_daily.sh init"
    [[ -z "$prefix" ]] ||
        err "Project này đang nằm bên trong một Git repository khác. Hãy chạy script ở đúng thư mục gốc project."
}

require_origin() {
    git remote get-url origin >/dev/null 2>&1 ||
        err "Chưa cấu hình remote origin. Tạo repository trên GitHub rồi chạy: bash ./git_daily.sh remote <GitHub URL>"
}

cmd_init() {
    require_git
    if git -C "$ROOT_DIR" rev-parse --show-prefix >/dev/null 2>&1; then
        require_repo
        info "Project đã là một Git repository."
    else
        git -C "$ROOT_DIR" init --initial-branch=main
        ok "Đã khởi tạo Git repository trên nhánh main."
    fi

    if [[ ! -f "$ROOT_DIR/.gitignore" ]]; then
        err "Không tìm thấy .gitignore. Hãy khôi phục file .gitignore đi kèm project trước khi commit."
    fi
    info "Hãy kiểm tra git status trước khi commit để chắc chắn không có file riêng tư."
}

cmd_status() {
    require_repo
    info "Trạng thái project:"
    git status -sb

    if git remote get-url origin >/dev/null 2>&1; then
        printf '\n'
        info "Remote origin:"
        git remote -v
    else
        warn "Chưa có remote origin. Tạo repository trên GitHub rồi chạy: bash ./git_daily.sh remote <GitHub URL>"
    fi
}

cmd_remote() {
    require_repo
    local url="${1:-}"
    [[ -n "$url" ]] ||     err "Thiếu URL. Ví dụ: bash ./git_daily.sh remote https://github.com/NguyenNgocAnh2610/2026_PyQt_A45.git"

    if git remote get-url origin >/dev/null 2>&1; then
        git remote set-url origin "$url"
        ok "Đã cập nhật remote origin."
    else
        git remote add origin "$url"
        ok "Đã thêm remote origin."
    fi
    info "Remote: $(git remote get-url origin)"
}

cmd_commit() {
    require_repo
    local message="${1:-}"
    [[ -n "$message" ]] || err 'Thiếu nội dung commit. Ví dụ: bash ./git_daily.sh commit "Sửa giao diện đăng nhập"'

    git add -A
    if git diff --cached --quiet; then
        info "Không có thay đổi nào cần commit."
        return
    fi

    info "Các file sẽ được đưa vào commit:"
    git status --short
    git diff --cached --check
    local confirm
    read -r -p "Tạo commit với các file trên? [y/N]: " confirm
    [[ "$confirm" == "y" || "$confirm" == "Y" ]] || {
        info "Đã hủy commit; các file vẫn đang được stage."
        return
    }
    git commit -m "$message"
}

cmd_pull() {
    require_repo
    require_origin
    if [[ -n "$(git status --porcelain)" ]]; then
        err "Đang có thay đổi chưa commit. Hãy commit trước khi pull để tránh mất hoặc xung đột dữ liệu."
    fi
    git pull --ff-only
}

cmd_push() {
    require_repo
    require_origin
    local branch
    branch="$(git branch --show-current)"
    [[ -n "$branch" ]] || err "Đang ở detached HEAD; hãy chuyển sang một nhánh trước khi push."
    git push -u origin "$branch"
}

ACTION="${1:-help}"
shift || true

case "$ACTION" in
    init)
        cmd_init
        ;;
    status|-s|--status)
        cmd_status
        ;;
    remote|--remote)
        cmd_remote "${1:-}"
        ;;
    commit)
        cmd_commit "${1:-}"
        ;;
    pull|-p|--pull)
        cmd_pull
        ;;
    push|--push)
        cmd_push
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        usage >&2
        err "Lệnh không hợp lệ: $ACTION"
        ;;
esac
