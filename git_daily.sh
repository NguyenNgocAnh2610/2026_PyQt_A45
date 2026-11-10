#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

DEFAULT_BRANCH="main"
DEFAULT_REMOTE_URL="https://github.com/NguyenNgocAnh2610/2026_PyQt_A45.git"

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

# Wrapper chạy git tại ROOT_DIR kèm safe.directory để không bị lỗi
# "detected dubious ownership" khi project nằm trên phân vùng dùng chung (/mnt/work)
git_repo() {
    git -C "$ROOT_DIR" -c safe.directory="$ROOT_DIR" "$@"
}

usage() {
    cat <<EOF
=====================================================================
  QUẢN LÝ GIT HÀNG NGÀY - PROJECT GUI (GIÁ THỬ A45 - ĐỀ TÀI 2026)
=====================================================================
Cách dùng trên Ubuntu/Linux:
  bash ./git_daily.sh <lệnh> [tham số]

Các lệnh chính:
  init                      Khởi tạo/cấu hình Git cho project (nhánh $DEFAULT_BRANCH)
  status | -s               Xem trạng thái file, nhánh hiện tại và remote
  remote [GitHub URL]       Cập nhật remote origin (mặc định: $DEFAULT_REMOTE_URL)
  commit [-y] "nội dung"    Stage toàn bộ thay đổi và tạo commit (-y để bỏ qua hỏi xác nhận)
  pull   | -p               Lấy thay đổi mới từ GitHub về (fast-forward)
  push                      Đẩy nhánh hiện tại lên GitHub (origin)
  sync   [-y] "nội dung"    Gộp nhanh: Commit -> Pull -> Push trong 1 lệnh
  diff   | -d               Xem chi tiết các dòng code vừa sửa chưa commit
  log    | -l               Xem lịch sử 15 commit gần nhất
  fix-ignore                Bỏ theo dõi các file đã lỡ commit nhưng nằm trong .gitignore
  help   | -h               Hiển thị hướng dẫn này

Ví dụ:
  bash ./git_daily.sh status
  bash ./git_daily.sh commit "Hoàn thiện giao diện đăng nhập PySide6"
  bash ./git_daily.sh push
  bash ./git_daily.sh sync "Cập nhật giao diện chính và style dark.qss"
EOF
}

require_git() {
    command -v git >/dev/null 2>&1 || err "Không tìm thấy Git. Hãy cài Git (sudo apt install git) rồi thử lại."
}

ensure_repo_config() {
    # Thử thêm safe.directory vào global config nếu có quyền ghi
    git config --global --get-all safe.directory 2>/dev/null | grep -Fxq "$ROOT_DIR" ||
        git config --global --add safe.directory "$ROOT_DIR" 2>/dev/null || true

    # Tắt theo dõi quyền thực thi file (tránh lỗi lệch chmod 777 trên ổ dùng chung Windows/Ubuntu)
    git_repo config core.fileMode false 2>/dev/null || true
    # Chuẩn hóa xuống dòng khi làm việc song song Windows & Linux
    git_repo config core.autocrlf input 2>/dev/null || true
}

require_repo() {
    require_git
    local prefix
    prefix="$(git_repo rev-parse --show-prefix 2>/dev/null)" ||
        err "Chưa có Git repository. Hãy chạy: bash ./git_daily.sh init"
    [[ -z "$prefix" ]] ||
        err "Project này đang nằm bên trong một Git repository khác. Hãy chạy script ở đúng thư mục gốc project."
    ensure_repo_config
}

require_origin() {
    if ! git_repo remote get-url origin >/dev/null 2>&1; then
        err "Chưa cấu hình remote origin. Hãy chạy: bash ./git_daily.sh remote $DEFAULT_REMOTE_URL"
    fi
}

current_branch() {
    local branch
    branch="$(git_repo branch --show-current)"
    [[ -n "$branch" ]] || err "Đang ở trạng thái detached HEAD; hãy chuyển sang một nhánh (ví dụ: git checkout $DEFAULT_BRANCH)."
    printf '%s' "$branch"
}

cmd_init() {
    require_git
    if git_repo rev-parse --show-prefix >/dev/null 2>&1; then
        require_repo
        info "Project đã là một Git repository."
    else
        git_repo init --initial-branch="$DEFAULT_BRANCH"
        ensure_repo_config
        ok "Đã khởi tạo Git repository trên nhánh $DEFAULT_BRANCH."
    fi

    if ! git_repo remote get-url origin >/dev/null 2>&1; then
        git_repo remote add origin "$DEFAULT_REMOTE_URL"
        ok "Đã tự động gắn remote origin: $DEFAULT_REMOTE_URL"
    fi

    if [[ ! -f "$ROOT_DIR/.gitignore" ]]; then
        warn "Không tìm thấy file .gitignore. Hãy tạo .gitignore trước khi commit."
    else
        ok "Đã cấu hình Git hoàn tất (core.fileMode=false, core.autocrlf=input)."
    fi
}

cmd_status() {
    require_repo
    info "Thư mục project: $ROOT_DIR"
    info "Trạng thái nhánh và file:"
    git_repo status -sb

    printf '\n'
    if git_repo rev-parse --verify HEAD >/dev/null 2>&1; then
        info "Commit gần nhất:"
        git_repo log -n 1 --oneline --decorate
    fi

    printf '\n'
    if git_repo remote get-url origin >/dev/null 2>&1; then
        info "Remote origin:"
        git_repo remote -v
    else
        warn "Chưa có remote origin. Hãy chạy: bash ./git_daily.sh remote"
    fi
}

cmd_remote() {
    require_repo
    local url="${1:-$DEFAULT_REMOTE_URL}"

    if git_repo remote get-url origin >/dev/null 2>&1; then
        git_repo remote set-url origin "$url"
        ok "Đã cập nhật remote origin."
    else
        git_repo remote add origin "$url"
        ok "Đã thêm remote origin."
    fi
    info "Remote hiện tại: $(git_repo remote get-url origin)"
}

cmd_commit() {
    require_repo
    local auto_yes=false
    if [[ "${1:-}" == "-y" || "${1:-}" == "--yes" ]]; then
        auto_yes=true
        shift
    fi

    local message="${*:-}"

    git_repo add -A
    if git_repo diff --cached --quiet; then
        info "Không có thay đổi nào cần commit."
        return 0
    fi

    info "Các file sẽ được đưa vào commit:"
    git_repo status --short
    printf '\n'
    git_repo diff --cached --stat

    if [[ -z "$message" ]]; then
        if [[ -t 0 ]]; then
            printf '\n'
            read -r -p "Nhập nội dung commit: " message
        fi
        [[ -n "$message" ]] || err 'Thiếu nội dung commit. Ví dụ: bash ./git_daily.sh commit "Cập nhật giao diện"'
    fi

    if [[ "$auto_yes" == false && -t 0 ]]; then
        local confirm
        printf '\n'
        read -r -p "Tạo commit với nội dung \"$message\"? [y/N]: " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            info "Đã hủy commit; các file vẫn đang được stage."
            return 0
        fi
    fi

    git_repo commit -m "$message"
    ok "Đã tạo commit thành công."
}

cmd_pull() {
    require_repo
    require_origin
    local branch
    branch="$(current_branch)"

    if [[ -n "$(git_repo status --porcelain)" ]]; then
        err "Đang có thay đổi chưa commit. Hãy chạy 'bash ./git_daily.sh commit' trước khi pull."
    fi

    info "Đang kiểm tra và kéo code mới từ origin/$branch..."
    if git_repo ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
        git_repo pull --ff-only origin "$branch"
        ok "Đã cập nhật code mới nhất từ origin/$branch."
    else
        warn "Nhánh '$branch' chưa tồn tại trên remote origin (có thể chưa push lần đầu)."
    fi
}

cmd_push() {
    require_repo
    require_origin
    local branch
    branch="$(current_branch)"

    info "Đang đẩy nhánh '$branch' lên origin..."
    git_repo push -u origin "$branch"
    ok "Đã push thành công lên origin/$branch."
}

cmd_sync() {
    require_repo
    require_origin
    cmd_commit "$@"
    if [[ -n "$(git_repo status --porcelain)" ]]; then
        warn "Vẫn còn thay đổi chưa commit, dừng bước pull/push."
        return 1
    fi
    cmd_pull
    cmd_push
}

cmd_diff() {
    require_repo
    if git_repo diff --quiet && git_repo diff --cached --quiet; then
        info "Không có thay đổi nào so với commit gần nhất."
    else
        git_repo diff HEAD
    fi
}

cmd_log() {
    require_repo
    if git_repo rev-parse --verify HEAD >/dev/null 2>&1; then
        info "Lịch sử commit gần đây:"
        git_repo log --oneline --graph --decorate -n 15
    else
        info "Chưa có commit nào trong repository."
    fi
}

cmd_fix_ignore() {
    require_repo
    info "Đang kiểm tra các file đã bị track nhưng nằm trong .gitignore..."
    local ignored_tracked
    ignored_tracked="$(git_repo ls-files -ci --exclude-standard)"
    if [[ -z "$ignored_tracked" ]]; then
        ok "Không có file nào trong .gitignore bị theo dõi nhầm."
        return 0
    fi

    warn "Các file sau đang bị Git theo dõi dù đã nằm trong .gitignore:"
    printf '%s\n' "$ignored_tracked"
    while IFS= read -r -d '' file; do
        git_repo rm --cached -- "$file" >/dev/null
    done < <(git_repo ls-files -ci --exclude-standard -z)
    ok "Đã bỏ theo dõi các file trong .gitignore (file trên máy vẫn được giữ nguyên)."
    git_repo status --short
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
    commit|-c|--commit)
        cmd_commit "$@"
        ;;
    pull|-p|--pull)
        cmd_pull
        ;;
    push|--push)
        cmd_push
        ;;
    sync|--sync)
        cmd_sync "$@"
        ;;
    diff|-d|--diff)
        cmd_diff
        ;;
    log|-l|--log)
        cmd_log
        ;;
    fix-ignore|--fix-ignore)
        cmd_fix_ignore
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        usage >&2
        err "Lệnh không hợp lệ: $ACTION"
        ;;
esac
