#!/usr/bin/env pwsh
# ==============================================================================
# QUAN LY GIT HANG NGAY - PROJECT GUI (GIA THU A45 - DE TAI 2026) - WINDOWS 11
# Tuong duong voi git_daily.sh tren Ubuntu (dung ASCII de tuong thich moiencoding)
# Cach dung: .\git_daily.ps1 <option> [commit_message]
# ==============================================================================

$ErrorActionPreference = "Stop"

$ROOT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location -LiteralPath $ROOT_DIR

$DEFAULT_BRANCH = "main"
$DEFAULT_REMOTE_URL = "https://github.com/NguyenNgocAnh2610/2026_PyQt_A45.git"
$APP_DIRS = @("src", "assets", "main.py")

function info($msg) { Write-Host "[INFO] " -ForegroundColor Blue -NoNewline; Write-Host $msg }
function ok($msg)   { Write-Host "[OK] " -ForegroundColor Green -NoNewline; Write-Host $msg }
function warn($msg) { Write-Host "[WARN] " -ForegroundColor Yellow -NoNewline; Write-Host $msg }
function err($msg)  { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

function git_run {
    & git -C $ROOT_DIR -c "safe.directory=$ROOT_DIR" @args
    if ($LASTEXITCODE -ne 0) { err "Lenh git that bai: git $($args -join ' ')" }
}

function git_out {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $res = & git -C $ROOT_DIR -c "safe.directory=$ROOT_DIR" @args 2>$null
    $ErrorActionPreference = $old
    return ($res -join "`n").Trim()
}

function git_ok {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & git -C $ROOT_DIR -c "safe.directory=$ROOT_DIR" @args 2>$null *> $null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old
    return ($code -eq 0)
}

function usage {
    Write-Host @"
================================================================================
  QUAN LY GIT HANG NGAY - PROJECT GUI (GIA THU A45 - DE TAI 2026)
================================================================================
Cach dung: .\git_daily.ps1 <option> [commit_message]

Cac lenh thuong dung:
  status       | -s    Kiem tra trang thai repo, nhanh, doi chieu SHA voi GitHub
  pull         | -p    [Dau ngay / Chuyen may] Kiem tra sach & pull --ff-only
  branch       | -b    Dam bao dang o nhanh '$DEFAULT_BRANCH' va doi chieu SHA voi origin
  start        | --start Chay gop 'branch' + 'pull' de san sang lam viec dau ngay
  pull-discard | -d    [TH1] Vut bo toan bo code sua nhap va lay lai ban chuan tu GitHub
  pull-keep    | -k    [TH2] Tu dong stash -> pull ban moi nhat -> stash pop
  push-all     | -a    Stage toan bo thay doi, commit va push len GitHub
  push-gui             Chi stage code giao dien (src/, assets/, main.py), commit & push
  commit       | -c    Chi stage va tao commit o may local (chua push)
  push                 Day cac commit local hien tai len origin/$DEFAULT_BRANCH

Tien ich khac:
  init                 Khoi tao/cau hinh Git cho project (nhanh $DEFAULT_BRANCH)
  remote [URL]         Xem hoac cap nhat remote origin
  diff                 Xem chi tiet cac dong code vua sua chua commit
  log          | -l    Xem lich su 15 commit gan nhat
  fix-ignore           Bo theo doi cac file da lo commit nhung nam trong .gitignore
  help         | -h    Hien thi huong dan nay
"@
}

function require_git {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        err "Khong tim thay Git. Hay cai Git (winget install Git.Git) roi thu lai."
    }
}

function ensure_repo_config {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    $safe = & git config --global --get-all safe.directory 2>$null
    if (-not ($safe -contains $ROOT_DIR)) { & git config --global --add safe.directory $ROOT_DIR 2>$null }
    & git -C $ROOT_DIR -c "safe.directory=$ROOT_DIR" config core.fileMode false 2>$null
    & git -C $ROOT_DIR -c "safe.directory=$ROOT_DIR" config core.autocrlf input 2>$null
    $ErrorActionPreference = $old
}

function require_repo {
    require_git
    if (-not (git_ok rev-parse --show-prefix)) { err "Chua co Git repository. Hay chay: .\git_daily.ps1 init" }
    if (git_out rev-parse --show-prefix) { err "Hay chay script o dung thu muc goc project." }
    ensure_repo_config
}

function require_origin {
    if (-not (git_ok remote get-url origin)) {
        err "Chua cau hinh remote origin. Hay chay: .\git_daily.ps1 remote $DEFAULT_REMOTE_URL"
    }
}

function current_branch {
    $b = git_out branch --show-current
    if (-not $b) { err "Dang o trang thai detached HEAD; hay chay: .\git_daily.ps1 branch" }
    return $b
}

function has_unpushed($branch) {
    if (-not (git_ok rev-parse --verify HEAD)) { return $false }
    if (-not (git_ok show-ref --verify --quiet "refs/remotes/origin/$branch")) { return $true }
    return [bool](git_out log "origin/$branch..HEAD" --oneline)
}

function cmd_init {
    require_git
    if (git_ok rev-parse --show-prefix) {
        require_repo
        info "Project da la mot Git repository."
    } else {
        git_run init "--initial-branch=$DEFAULT_BRANCH"
        ensure_repo_config
        ok "Da khoi tao Git repository tren nhanh $DEFAULT_BRANCH."
    }
    if (-not (git_ok remote get-url origin)) {
        git_run remote add origin $DEFAULT_REMOTE_URL
        ok "Da tu dong gan remote origin: $DEFAULT_REMOTE_URL"
    }
    if (-not (Test-Path "$ROOT_DIR\.gitignore")) {
        warn "Khong tim thay file .gitignore. Hay tao .gitignore truoc khi commit."
    } else {
        ok "Da cau hinh Git hoan tat (core.fileMode=false, core.autocrlf=input)."
    }
}

function cmd_remote($url) {
    require_repo
    if (-not $url) { $url = $DEFAULT_REMOTE_URL }
    if (git_ok remote get-url origin) {
        git_run remote set-url origin $url; ok "Da cap nhat remote origin."
    } else {
        git_run remote add origin $url; ok "Da them remote origin."
    }
    info "Remote hien tai: $(git_out remote get-url origin)"
}

function cmd_status {
    require_repo
    info "=== 1. Trang thai project GUI ($ROOT_DIR) ==="
    git_run status -sb; Write-Host ""

    info "=== 2. Commit gan nhat & Doi chieu SHA ==="
    if (git_ok rev-parse --verify HEAD) {
        $b = git_out branch --show-current
        if (-not $b) { $b = "detached HEAD" }
        $localSha = git_out rev-parse HEAD
        git_run log -n 1 --oneline --decorate
        Write-Host "  - SHA tai may nay (HEAD)         : $localSha ($b)"
        if (git_ok rev-parse --verify "origin/$DEFAULT_BRANCH") {
            $originSha = git_out rev-parse "origin/$DEFAULT_BRANCH"
            Write-Host ("  - SHA da biet cua origin/{0,-7} : {1}" -f $DEFAULT_BRANCH, $originSha)
            if ($localSha -eq $originSha) { ok "SHA local trung khop voi origin/$DEFAULT_BRANCH." }
            else { warn "SHA local KHAC voi origin/$DEFAULT_BRANCH (hay chay '.\git_daily.ps1 pull' hoac 'push')." }
        }
    } else { warn "Chua co commit nao trong repository." }

    Write-Host ""
    info "=== 3. Remote origin ==="
    if (git_ok remote get-url origin) { git_run remote -v }
    else { warn "Chua co remote origin. Hay chay: .\git_daily.ps1 remote" }
}

function cmd_branch {
    require_repo; require_origin
    info "Chuan bi nhanh '$DEFAULT_BRANCH'..."
    git_run fetch origin

    if (git_ok show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH") {
        git_run switch $DEFAULT_BRANCH
    } elseif (git_ok show-ref --verify --quiet "refs/remotes/origin/$DEFAULT_BRANCH") {
        info "Tao tracking branch '$DEFAULT_BRANCH' tu 'origin/$DEFAULT_BRANCH'..."
        git_run switch -c $DEFAULT_BRANCH --track "origin/$DEFAULT_BRANCH"
    } else {
        git_run switch -C $DEFAULT_BRANCH
    }

    if ((git_ok rev-parse --verify HEAD) -and (git_ok show-ref --verify --quiet "refs/remotes/origin/$DEFAULT_BRANCH")) {
        Write-Host "  - SHA local ($DEFAULT_BRANCH)        : $(git_out rev-parse HEAD)"
        Write-Host ("  - SHA origin/{0,-12} : {1}" -f $DEFAULT_BRANCH, (git_out rev-parse "origin/$DEFAULT_BRANCH"))
    }
    ok "Dang o nhanh '$DEFAULT_BRANCH'."
}

function cmd_pull {
    require_repo; require_origin
    $b = current_branch
    info "[Dau ngay / Chuyen may] Kiem tra trang thai truoc khi cap nhat..."

    if (git_out status --porcelain) {
        git_run status -sb; Write-Host ""
        warn "Goi y: 1. Giu code dang sua: .\git_daily.ps1 -k | 2. Vut bo code nhap: .\git_daily.ps1 -d"
        err "Working tree dang co thay doi chua luu! Chi chay 'pull' khi khong co thay doi do dang."
    }

    info "Dang chay: git pull --ff-only origin $b..."
    if (git_ok ls-remote --exit-code --heads origin $b) {
        git_run pull --ff-only origin $b
        Write-Host "  - SHA local ($b)  : $(git_out rev-parse HEAD)"
        Write-Host "  - SHA origin/$b : $(git_out rev-parse "origin/$b")"
        ok "Cap nhat dau ngay hoan tat! Code tai may nay da dong bo chuan voi GitHub."
    } else {
        warn "Nhanh '$b' chua ton tai tren remote origin (co the chua push lan dau)."
    }
}

function cmd_pull_discard($extra) {
    require_repo; require_origin
    warn "[TH1] CANH BAO: XOA BO toan bo sua doi nhap (ke ca commit chua push) de quay ve ban chuan tren GitHub!"
    if (-not ($extra -and $extra[0] -in @("-y", "--yes"))) {
        $ans = Read-Host "Ban co chac chan muon vut bo thay doi va pull lai? (go 'y' de dong y)"
        if ($ans -notin @("y", "Y")) { info "Da huy thao tac."; exit 0 }
    }

    info "[TH1] 1. Tai thong tin moi nhat tu GitHub (git fetch origin)..."
    git_run fetch origin
    if (git_ok rev-parse --verify HEAD) { git_run restore --staged --worktree . }
    git_run clean -fd

    info "[TH1] 2. Dua nhanh '$DEFAULT_BRANCH' ve ban chuan origin/$DEFAULT_BRANCH..."
    if (git_ok show-ref --verify --quiet "refs/heads/$DEFAULT_BRANCH") { git_run switch -f $DEFAULT_BRANCH }
    else { git_run switch -c $DEFAULT_BRANCH --track "origin/$DEFAULT_BRANCH" }
    git_run reset --hard "origin/$DEFAULT_BRANCH"

    cmd_pull
    ok "[TH1] Da bo toan bo ban nhap cu va dong bo lai chuan 100% tu GitHub!"
}

function cmd_pull_keep {
    require_repo; require_origin
    $b = current_branch
    info "[TH2] Cat tam (stash), pull ban moi tu GitHub va ghep lai..."

    if (git_ok ls-remote --exit-code --heads origin $b) {
        git_run fetch origin $b
        # Neu da lo tao commit local chua push (do chay -c hoac -a truoc khi pull),
        # dua cac commit do ve lai working tree de stash va pull --ff-only sach se
        if ((git_ok rev-parse --verify HEAD) -and (git_ok rev-parse --verify "origin/$b")) {
            $unpushed = git_out log "origin/$b..HEAD" --oneline
            $behind   = git_out log "HEAD..origin/$b" --oneline
            if ($unpushed -and $behind) {
                $base = git_out merge-base HEAD "origin/$b"
                if ($base) {
                    info "[TH2] Phat hien commit local chua push khi tren GitHub co ban moi; gop commit nhap ve working tree..."
                    git_run reset --soft $base
                }
            }
        }
    }

    $stashed = $false
    if (git_out status --porcelain) {
        $msg = "auto-stash-gui-$(Get-Date -Format 'yyyyMMdd_HHmmss')"
        info "[TH2] 1. Dang stash cac thay doi ($msg)..."
        git_run stash push -u -m $msg
        $stashed = $true
    } else { info "[TH2] 1. Working tree sach, khong can stash." }

    info "[TH2] 2. Dang pull ban moi nhat tu GitHub..."
    cmd_pull

    if ($stashed) {
        info "[TH2] 3. Dang lay lai (git stash pop) phan code vua sua..."
        $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
        & git -C $ROOT_DIR -c "safe.directory=$ROOT_DIR" stash pop
        $code = $LASTEXITCODE; $ErrorActionPreference = $old
        if ($code -ne 0) {
            warn "Phat hien xung dot giua ban tren GitHub va ban dang sua -> Uu tien giu ban code vua sua o may nay..."
            git_run checkout --theirs -- .
            git_run reset HEAD
            git_run stash drop
        }
    }
    ok "[TH2] Da cap nhat code moi tu GitHub va khoi phuc lai phan code ban dang sua!"
}

function cmd_push_all($extra) {
    require_repo; require_origin
    $msg = if ($extra -and ($extra -join " ").Trim()) { ($extra -join " ").Trim() } else { "Update GUI project" }
    $b = current_branch

    info "Dang kiem tra va stage toan bo thay doi..."
    git_run add -A

    if (-not (git_ok diff --cached --quiet)) {
        git_run status -s; Write-Host ""; git_run diff --cached --stat; Write-Host ""
        git_run commit -m $msg
        info "Dang push len origin/$b..."
        git_run push -u origin $b
        ok "Hoan tat commit va push toan bo project len GitHub (origin/$b)!"
    } elseif (has_unpushed $b) {
        info "Dang push cac commit co san o local len origin/$b..."
        git_run push -u origin $b
        ok "Push hoan tat len origin/$b!"
    } else {
        ok "Khong co thay doi moi can commit hoac push."
    }
}

function cmd_push_gui($extra) {
    require_repo; require_origin
    $msg = if ($extra -and ($extra -join " ").Trim()) { ($extra -join " ").Trim() } else { "Update GUI source and assets" }
    $b = current_branch
    $paths = @($APP_DIRS | Where-Object { Test-Path "$ROOT_DIR\$_" })

    info "Dang kiem tra thay doi nhom giao dien ($($APP_DIRS -join ' '))..."
    if ($paths.Count -gt 0) { git_run add -- @paths }

    if ($paths.Count -gt 0 -and -not (git_ok diff --cached --quiet -- @paths)) {
        git_run status -s -- @paths
        git_run commit -m $msg -- @paths
        info "Dang push len origin/$b..."
        git_run push -u origin $b
        ok "Da commit va push code giao dien ($($paths -join ' ')) thanh cong!"
    } elseif (has_unpushed $b) {
        info "Dang push cac commit co san o local len origin/$b..."
        git_run push -u origin $b
        ok "Push hoan tat!"
    } else {
        info "Khong co thay doi nao trong ($($paths -join ' ')) de commit."
    }
}

function cmd_commit($extra) {
    require_repo
    $autoYes = $false
    if ($extra -and $extra[0] -in @("-y", "--yes")) {
        $autoYes = $true
        $extra = if ($extra.Count -gt 1) { $extra[1..($extra.Count - 1)] } else { @() }
    }
    $msg = ($extra -join " ").Trim()

    git_run add -A
    if (git_ok diff --cached --quiet) { info "Khong co thay doi nao can commit."; return }

    info "Cac file se duoc dua vao commit:"
    git_run status --short; Write-Host ""; git_run diff --cached --stat

    if (-not $msg) {
        $msg = (Read-Host "`nNhap noi dung commit").Trim()
        if (-not $msg) { err 'Thieu noi dung commit. Vi du: .\git_daily.ps1 commit "Cap nhat giao dien"' }
    }
    if (-not $autoYes) {
        $ans = Read-Host "`nTao commit voi noi dung `"$msg`"? [y/N]"
        if ($ans -notin @("y", "Y")) { info "Da huy commit; cac file van dang duoc stage."; return }
    }
    git_run commit -m $msg
    ok "Da tao commit tai may local thanh cong."
}

function cmd_push($extra) {
    require_repo; require_origin
    if ($extra -and $extra.Count -gt 0) { cmd_push_all $extra; return }
    $b = current_branch
    info "Dang day nhanh '$b' len origin..."
    git_run push -u origin $b
    ok "Da push thanh cong len origin/$b."
}

function cmd_diff {
    require_repo
    if ((git_ok diff --quiet) -and (git_ok diff --cached --quiet)) {
        info "Khong co thay doi nao so voi commit gan nhat."
    } elseif (git_ok rev-parse --verify HEAD) {
        git_run diff HEAD
    } else {
        git_run diff; git_run diff --cached
    }
}

function cmd_log {
    require_repo
    if (git_ok rev-parse --verify HEAD) {
        info "Lich su commit gan day:"
        git_run log --oneline --graph --decorate -n 15
    } else { info "Chua co commit nao trong repository." }
}

function cmd_fix_ignore {
    require_repo
    info "Dang kiem tra cac file da bi track nhung nam trong .gitignore..."
    $ignored = git_out ls-files -ci --exclude-standard
    if (-not $ignored) { ok "Khong co file nao trong .gitignore bi theo doi nham."; return }

    warn "Cac file sau dang bi Git theo doi du da nam trong .gitignore:"
    foreach ($f in ($ignored -split "`n")) {
        if ($f.Trim()) { Write-Host $f.Trim(); git_run rm --cached -- $f.Trim() | Out-Null }
    }
    ok "Da bo theo doi cac file trong .gitignore (file tren may van giu nguyen)."
    git_run status --short
}

# ==============================================================================
# MAIN
# ==============================================================================
$action = if ($args.Count -gt 0 -and $args[0]) { [string]$args[0] } else { "help" }
$rest   = if ($args.Count -gt 1) { @($args[1..($args.Count - 1)]) } else { @() }

switch -Exact ($action) {
    "init"                                                      { cmd_init }
    { $_ -in "status", "-s", "--status" }                       { cmd_status }
    { $_ -in "pull", "-p", "--pull" }                           { cmd_pull }
    { $_ -in "branch", "px4-branch", "-b", "--branch" }         { cmd_branch }
    { $_ -in "start", "--start" }                               { cmd_branch; cmd_pull }
    { $_ -in "pull-discard", "-d", "--pull-discard" }           { cmd_pull_discard $rest }
    { $_ -in "pull-keep", "-k", "--pull-keep" }                 { cmd_pull_keep }
    { $_ -in "push-all", "sync", "-a", "--push-all", "--sync" } { cmd_push_all $rest }
    { $_ -in "push-gui", "push-seeker", "--push-gui", "--push-seeker" } { cmd_push_gui $rest }
    { $_ -in "commit", "-c", "--commit" }                       { cmd_commit $rest }
    { $_ -in "push", "--push" }                                 { cmd_push $rest }
    { $_ -in "remote", "--remote" }                             { cmd_remote ($rest | Select-Object -First 1) }
    { $_ -in "diff", "--diff" }                                 { cmd_diff }
    { $_ -in "log", "-l", "--log" }                             { cmd_log }
    { $_ -in "fix-ignore", "--fix-ignore" }                     { cmd_fix_ignore }
    { $_ -in "help", "-h", "--help" }                           { usage }
    default                                                     { usage; err "Lenh khong hop le: $action" }
}
