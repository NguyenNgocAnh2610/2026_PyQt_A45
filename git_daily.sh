#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

DEFAULT_BRANCH="main"
DEFAULT_REMOTE_URL="https://github.com/NguyenNgocAnh2610/2026_PyQt_A45.git"
APP_DIRS=("src" "assets" "main.py")

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
================================================================================
  QUẢN LÝ GIT HÀNG NGÀY - PROJECT GUI (GIÁ THỬ A45 - ĐỀ TÀI 2026)
================================================================================
Cách dùng: ./git_daily.sh <option> [commit_message]
   (hoặc: bash ./git_daily.sh <option> [commit_message])

Các lệnh dùng thường xuyên (Quy trình hằng ngày trên cả hai máy - không submodule):
  status       | -s    Kiểm tra trạng thái repo, nhánh, đối chiếu SHA với GitHub
  pull         | -p    [Đầu ngày / Chuyển máy] Kiểm tra sạch & pull --ff-only
  branch       | -b    Đảm bảo đang ở nhánh '$DEFAULT_BRANCH' và đối chiếu SHA với origin
  start        | --start Chạy gộp 'branch' + 'pull' để sẵn sàng làm việc đầu ngày
  pull-discard | -d    [TH1] Vứt bỏ toàn bộ code sửa nháp (kể cả commit nháp chưa push)
                       ở máy này và lấy lại bản chuẩn 100% từ GitHub
  pull-keep    | -k    [TH2] Quên pull mà đã sửa code: tự động stash -> pull bản mới
                       nhất từ GitHub -> lấy lại (stash pop) phần code vừa sửa
  push-all     | -a    Stage toàn bộ thay đổi trong project, commit và push lên GitHub
  push-gui             Chỉ stage code giao diện (src/, assets/, main.py), commit & push
  commit       | -c    Chỉ stage và tạo commit ở máy local (chưa push)
  push                 Đẩy các commit local hiện tại lên origin/$DEFAULT_BRANCH

Các lệnh tiện ích khác:
  init                 Khởi tạo/cấu hình Git cho project (nhánh $DEFAULT_BRANCH)
  remote [URL]         Xem hoặc cập nhật remote origin
  diff                 Xem chi tiết các dòng code vừa sửa chưa commit
  log          | -l    Xem lịch sử 15 commit gần nhất
  fix-ignore           Bỏ theo dõi các file đã lỡ commit nhưng nằm trong .gitignore
  help         | -h    Hiển thị hướng dẫn này

Ví dụ thực tế:
  ./git_daily.sh status
  ./git_daily.sh start
  ./git_daily.sh pull
  ./git_daily.sh pull-discard          # (hoặc: ./git_daily.sh -d)
  ./git_daily.sh pull-keep             # (hoặc: ./git_daily.sh -k)
  ./git_daily.sh push-all "Cập nhật giao diện đăng nhập và bảng điều khiển"
  ./git_daily.sh -a "Fix lỗi hiển thị dark.qss"
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
        err "Chưa có Git repository. Hãy chạy: ./git_daily.sh init"
    [[ -z "$prefix" ]] ||
        err "Project này đang nằm bên trong một Git repository khác. Hãy chạy script ở đúng thư mục gốc project."
    ensure_repo_config
}

require_origin() {
    if ! git_repo remote get-url origin >/dev/null 2>&1; then
        err "Chưa cấu hình remote origin. Hãy chạy: ./git_daily.sh remote $DEFAULT_REMOTE_URL"
    fi
}

current_branch() {
    local branch
    branch="$(git_repo branch --show-current)"
    [[ -n "$branch" ]] || err "Đang ở trạng thái detached HEAD; hãy chạy: ./git_daily.sh branch"
    printf '%s' "$branch"
}

# ------------------------------------------------------------------------------
# INIT & REMOTE: Khởi tạo và cấu hình repository
# ------------------------------------------------------------------------------
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

# ------------------------------------------------------------------------------
# STATUS: Kiểm tra trạng thái và đối chiếu SHA với origin/main
# ------------------------------------------------------------------------------
cmd_status() {
    require_repo
    info "=== 1. Trạng thái project GUI ($ROOT_DIR) ==="
    git_repo status -sb
    printf '\n'

    info "=== 2. Commit gần nhất & Đối chiếu SHA ==="
    if git_repo rev-parse --verify HEAD >/dev/null 2>&1; then
        local local_sha origin_sha branch
        branch="$(git_repo branch --show-current)"
        local_sha="$(git_repo rev-parse HEAD)"
        git_repo log -n 1 --oneline --decorate
        printf '  - SHA tại máy này (HEAD)         : %s (%s)\n' "$local_sha" "${branch:-detached HEAD}"

        if git_repo rev-parse --verify "origin/$DEFAULT_BRANCH" >/dev/null 2>&1; then
            origin_sha="$(git_repo rev-parse "origin/$DEFAULT_BRANCH")"
            printf '  - SHA đã biết của origin/%-7s : %s\n' "$DEFAULT_BRANCH" "$origin_sha"
            if [[ "$local_sha" == "$origin_sha" ]]; then
                ok "SHA local trùng khớp với origin/$DEFAULT_BRANCH."
            else
                warn "SHA local KHÁC với origin/$DEFAULT_BRANCH (hãy chạy './git_daily.sh pull' hoặc './git_daily.sh push')."
            fi
        fi
    else
        warn "Chưa có commit nào trong repository."
    fi

    printf '\n'
    info "=== 3. Remote origin ==="
    if git_repo remote get-url origin >/dev/null 2>&1; then
        git_repo remote -v
    else
        warn "Chưa có remote origin. Hãy chạy: ./git_daily.sh remote"
    fi
}

# ------------------------------------------------------------------------------
# BRANCH: Đảm bảo đang ở nhánh main chuẩn trước khi làm việc
# ------------------------------------------------------------------------------
cmd_branch() {
    require_repo
    require_origin
    info "Chuẩn bị nhánh '$DEFAULT_BRANCH'..."

    git_repo fetch origin

    if git_repo show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH"; then
        git_repo switch "$DEFAULT_BRANCH"
    else
        info "Tạo tracking branch '$DEFAULT_BRANCH' từ 'origin/$DEFAULT_BRANCH'..."
        git_repo switch -c "$DEFAULT_BRANCH" --track "origin/$DEFAULT_BRANCH"
    fi

    local local_sha origin_sha
    local_sha="$(git_repo rev-parse HEAD)"
    if git_repo show-ref --verify --quiet "refs/remotes/origin/$DEFAULT_BRANCH"; then
        origin_sha="$(git_repo rev-parse "origin/$DEFAULT_BRANCH")"
        printf '  - SHA local (%s)        : %s\n' "$DEFAULT_BRANCH" "$local_sha"
        printf '  - SHA origin/%-12s : %s\n' "$DEFAULT_BRANCH" "$origin_sha"
    fi
    ok "Đang ở nhánh '$DEFAULT_BRANCH'."
}

# ------------------------------------------------------------------------------
# E1. ĐẦU NGÀY / CHUYỂN MÁY: pull
# ------------------------------------------------------------------------------
cmd_pull() {
    require_repo
    require_origin
    local branch
    branch="$(current_branch)"

    info "[Đầu ngày / Chuyển máy] Kiểm tra trạng thái trước khi cập nhật..."

    if [[ -n "$(git_repo status --porcelain)" ]]; then
        git_repo status -sb
        printf '\n'
        warn "Gợi ý xử lý nhanh:"
        warn "  1. Nếu muốn GIỮ LẠI code đang sửa và pull bản mới : ./git_daily.sh pull-keep    (hoặc: ./git_daily.sh -k)"
        warn "  2. Nếu muốn VỨT BỎ code nháp và lấy bản chuẩn     : ./git_daily.sh pull-discard (hoặc: ./git_daily.sh -d)"
        err "Working tree đang có thay đổi chưa lưu! Chỉ chạy 'pull' khi không có thay đổi dở dang."
    fi

    info "Đang chạy: git pull --ff-only origin $branch..."
    if git_repo ls-remote --exit-code --heads origin "$branch" >/dev/null 2>&1; then
        git_repo pull --ff-only origin "$branch"
        local local_sha origin_sha
        local_sha="$(git_repo rev-parse HEAD)"
        origin_sha="$(git_repo rev-parse "origin/$branch")"
        printf '  - SHA local (%s)  : %s\n' "$branch" "$local_sha"
        printf '  - SHA origin/%s : %s\n' "$branch" "$origin_sha"
        ok "Cập nhật đầu ngày hoàn tất! Code tại máy này đã đồng bộ chuẩn với GitHub."
    else
        warn "Nhánh '$branch' chưa tồn tại trên remote origin (có thể chưa push lần đầu)."
    fi
}

# ------------------------------------------------------------------------------
# TRƯỜNG HỢP 1: Vứt bỏ toàn bộ code sửa nháp (không hợp lý) và pull lại bản chuẩn
#   Tương đương:
#     git restore . && git clean -fd
#     git fetch origin && git reset --hard origin/main
#     ./git_daily.sh pull
# ------------------------------------------------------------------------------
cmd_pull_discard() {
    require_repo
    require_origin

    warn "[TH1] CẢNH BÁO: Thao tác này sẽ XÓA BỎ toàn bộ các sửa đổi nháp (kể cả commit nháp chưa push) trên máy hiện tại để quay về đúng bản chuẩn trên GitHub!"
    if [[ "${1:-}" != "-y" && "${1:-}" != "--yes" ]]; then
        local confirm
        read -r -p "Bạn có chắc chắn muốn vứt bỏ thay đổi và pull lại? (gõ 'y' để đồng ý): " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            info "Đã hủy thao tác."
            exit 0
        fi
    fi

    info "[TH1] 1. Tải thông tin mới nhất từ GitHub (git fetch origin)..."
    git_repo fetch origin

    info "[TH1] 2. Xóa các thay đổi nháp và file nháp mới tạo (git restore . && git clean -fd)..."
    git_repo restore .
    git_repo clean -fd

    info "[TH1] 3. Đưa nhánh '$DEFAULT_BRANCH' về đúng bản chuẩn trên GitHub (git reset --hard origin/$DEFAULT_BRANCH)..."
    if git_repo show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH"; then
        git_repo switch "$DEFAULT_BRANCH"
    else
        git_repo switch -c "$DEFAULT_BRANCH" --track "origin/$DEFAULT_BRANCH"
    fi
    git_repo reset --hard "origin/$DEFAULT_BRANCH"

    info "[TH1] 4. Kiểm tra đồng bộ lại với GitHub..."
    cmd_pull
    ok "[TH1] Đã bỏ toàn bộ bản nháp cũ và đồng bộ lại chuẩn 100% từ GitHub!"
}

# ------------------------------------------------------------------------------
# TRƯỜNG HỢP 2: Quên chưa pull mà đã sửa code -> Giữ lại code đang sửa
#   Tương đương:
#     git stash push -u -m "code tam tren may 2"
#     ./git_daily.sh pull
#     git stash pop
# ------------------------------------------------------------------------------
cmd_pull_keep() {
    require_repo
    require_origin

    info "[TH2] Quên pull mà đã sửa code — tiến hành cất tạm (stash), pull bản mới và ghép lại..."

    local stashed=0
    if [[ -n "$(git_repo status --porcelain)" ]]; then
        local stash_msg="auto-stash-gui-$(date +%Y%m%d_%H%M%S)"
        info "[TH2] 1. Đang cất tạm (stash -u) các thay đổi đang sửa ($stash_msg)..."
        git_repo stash push -u -m "$stash_msg"
        stashed=1
    else
        info "[TH2] 1. Working tree hiện đang sạch, không cần stash."
    fi

    info "[TH2] 2. Đang pull bản mới nhất từ GitHub..."
    cmd_pull

    if [[ $stashed -eq 1 ]]; then
        info "[TH2] 3. Đang lấy lại (git stash pop) phần code vừa sửa..."
        if ! git_repo stash pop; then
            warn "Có xung đột (conflict) khi ghép code vừa sửa với bản mới trên GitHub!"
            warn "Hãy mở các file bị đánh dấu conflict để xử lý, bản stash vẫn còn lưu trong 'git stash list'."
            exit 1
        fi
    fi

    ok "[TH2] Đã cập nhật code mới từ GitHub và khôi phục lại phần code bạn đang sửa!"
}

# ------------------------------------------------------------------------------
# PUSH-ALL (-a): Stage toàn bộ thay đổi trong project, commit và push lên GitHub
# ------------------------------------------------------------------------------
cmd_push_all() {
    require_repo
    require_origin
    local msg="${*:-Update GUI project}"
    local branch
    branch="$(current_branch)"

    info "Đang kiểm tra và stage toàn bộ thay đổi trong project..."
    git_repo add -A

    if ! git_repo diff --cached --quiet; then
        git_repo status -s
        printf '\n'
        git_repo diff --cached --stat
        printf '\n'
        git_repo commit -m "$msg"
        info "Đang push lên origin/$branch..."
        git_repo push -u origin "$branch"
        ok "Hoàn tất commit và push toàn bộ project lên GitHub (origin/$branch)!"
    elif [[ -n "$(git_repo log "origin/$branch..HEAD" --oneline 2>/dev/null)" ]]; then
        info "Không có file mới cần commit, đang push các commit có sẵn ở local lên origin/$branch..."
        git_repo push -u origin "$branch"
        ok "Push hoàn tất lên origin/$branch!"
    else
        ok "Không có thay đổi mới cần commit hoặc push."
    fi
}

# ------------------------------------------------------------------------------
# PUSH-GUI (tương tự push-seeker): Chỉ commit & push code giao diện (src, assets, main.py)
# ------------------------------------------------------------------------------
cmd_push_gui() {
    require_repo
    require_origin
    local msg="${*:-Update GUI source and assets}"
    local branch
    branch="$(current_branch)"

    info "Đang kiểm tra thay đổi trong nhóm file giao diện (${APP_DIRS[*]})..."
    local existing_paths=()
    local item
    for item in "${APP_DIRS[@]}"; do
        [[ -e "$ROOT_DIR/$item" ]] && existing_paths+=("$item")
    done

    if [[ ${#existing_paths[@]} -gt 0 ]]; then
        git_repo add "${existing_paths[@]}"
    fi

    if ! git_repo diff --cached --quiet; then
        git_repo status -s "${existing_paths[@]}"
        git_repo commit -m "$msg"
        info "Đang push lên origin/$branch..."
        git_repo push -u origin "$branch"
        ok "Đã commit và push code giao diện (${existing_paths[*]}) thành công!"
    elif [[ -n "$(git_repo log "origin/$branch..HEAD" --oneline 2>/dev/null)" ]]; then
        info "Đang push các commit có sẵn ở local lên origin/$branch..."
        git_repo push -u origin "$branch"
        ok "Push hoàn tất!"
    else
        info "Không có thay đổi nào trong (${existing_paths[*]}) để commit."
    fi
}

# ------------------------------------------------------------------------------
# COMMIT & PUSH RIÊNG LẺ
# ------------------------------------------------------------------------------
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
        [[ -n "$message" ]] || err 'Thiếu nội dung commit. Ví dụ: ./git_daily.sh commit "Cập nhật giao diện"'
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
    ok "Đã tạo commit tại máy local thành công."
}

cmd_push() {
    require_repo
    require_origin
    # Nếu người dùng truyền kèm message vào lệnh push, chuyển sang push-all cho tiện
    if [[ $# -gt 0 ]]; then
        cmd_push_all "$@"
        return 0
    fi

    local branch
    branch="$(current_branch)"
    info "Đang đẩy nhánh '$branch' lên origin..."
    git_repo push -u origin "$branch"
    ok "Đã push thành công lên origin/$branch."
}

# ------------------------------------------------------------------------------
# CÁC LỆNH TIỆN ÍCH KHÁC: diff, log, fix-ignore
# ------------------------------------------------------------------------------
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

# ==============================================================================
# MAIN
# ==============================================================================
ACTION="${1:-help}"
shift || true

case "$ACTION" in
    init)
        cmd_init
        ;;
    status|-s|--status)
        cmd_status
        ;;
    pull|-p|--pull)
        cmd_pull
        ;;
    branch|px4-branch|-b|--branch)
        cmd_branch
        ;;
    start|--start)
        cmd_branch
        cmd_pull
        ;;
    pull-discard|-d|--pull-discard)
        cmd_pull_discard "$@"
        ;;
    pull-keep|-k|--pull-keep)
        cmd_pull_keep
        ;;
    push-all|sync|-a|--push-all|--sync)
        cmd_push_all "$@"
        ;;
    push-gui|push-seeker|--push-gui|--push-seeker)
        cmd_push_gui "$@"
        ;;
    commit|-c|--commit)
        cmd_commit "$@"
        ;;
    push|--push)
        cmd_push "$@"
        ;;
    remote|--remote)
        cmd_remote "${1:-}"
        ;;
    diff|--diff)
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
