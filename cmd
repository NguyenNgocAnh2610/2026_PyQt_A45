# ==============================================================================
# HƯỚNG DẪN MÔI TRƯỜNG & LỆNH THƯỜNG DÙNG (PROJECT GUI - ĐỀ TÀI 2026)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Cấu hình môi trường Python / Conda / Qt
# ------------------------------------------------------------------------------
conda create --name qt_env python=3.10
conda activate qt_env
pip install PySide6

# Convert file .ui sang Python (nếu dùng Qt Designer):
# pyside6-uic main_window.ui -o main_window.py
# pyuic6 -x main_window.ui -o main_window.py

# Chạy app:
python main.py

# ==============================================================================
# 2. Quy trình Git hàng ngày trên Ubuntu (git_daily.sh)
# ==============================================================================

# --- [BƯỚC 1: ĐẦU NGÀY HOẶC KHI VỪA CHUYỂN MÁY] ---
# Kiểm tra nhánh main và pull bản mới nhất từ GitHub:
./git_daily.sh start
# (hoặc chỉ pull đơn giản):
./git_daily.sh pull
# (viết tắt):
./git_daily.sh -p

# --- [BƯỚC 2: KIỂM TRA TRẠNG THÁI & THAY ĐỔI TRONG NGÀY] ---
# Kiểm tra file đã sửa, nhánh hiện tại và đối chiếu SHA với GitHub:
./git_daily.sh status
# (viết tắt):
./git_daily.sh -s

# Xem chi tiết các dòng code vừa sửa chưa commit:
./git_daily.sh diff

# Xem cây lịch sử 15 commit gần nhất:
./git_daily.sh log
# (viết tắt):
./git_daily.sh -l

# --- [BƯỚC 3: XỬ LÝ TÌNH HUỐNG KHI ĐANG LÀM VIỆC] ---

# TH1: Sửa nháp không hợp lý, muốn vứt bỏ toàn bộ để lấy lại bản chuẩn 100% trên GitHub:
./git_daily.sh pull-discard
# (viết tắt):
./git_daily.sh -d
# (bỏ qua hỏi xác nhận):
./git_daily.sh -d -y

# TH2: Quên chưa pull mà đã sửa code — muốn GIỮ LẠI phần code vừa sửa:
# (Tự động stash -> pull bản mới -> pop lại code vừa sửa)
./git_daily.sh pull-keep
# (viết tắt):
./git_daily.sh -k

# --- [BƯỚC 4: LƯU & ĐẨY CODE LÊN GITHUB] ---

# Cách 1: Đẩy toàn bộ thay đổi trong project lên GitHub trong 1 lệnh (Khuyên dùng cuối buổi):
./git_daily.sh push-all "Nội dung commit"
# (viết tắt):
./git_daily.sh -a "Nội dung commit"

# Cách 2: Chỉ commit và đẩy riêng nhóm file code giao diện (src/, assets/, main.py):
./git_daily.sh push-gui "Cập nhật giao diện đăng nhập"

# Cách 3: Tạo commit ở máy local trước (chưa đẩy lên GitHub):
./git_daily.sh commit "Nội dung commit"
# (viết tắt):
./git_daily.sh -c "Nội dung commit"

# Đẩy các commit đã tạo ở máy local lên GitHub:
./git_daily.sh push

# --- [BƯỚC 5: KHỞI TẠO & BẢO TRÌ REPOSITORY] ---
# Đảm bảo đang ở đúng nhánh main chuẩn:
./git_daily.sh branch
# (viết tắt):
./git_daily.sh -b

# Khởi tạo repo hoặc kiểm tra cấu hình ban đầu:
./git_daily.sh init

# Cập nhật hoặc đổi link GitHub remote origin:
./git_daily.sh remote https://github.com/NguyenNgocAnh2610/2026_PyQt_A45.git

# Bỏ theo dõi các file lỡ commit nhưng nằm trong .gitignore (giữ nguyên file trên máy):
./git_daily.sh fix-ignore

# Hiển thị menu trợ giúp:
./git_daily.sh help
# (viết tắt):
./git_daily.sh -h


# ==============================================================================
# 3. Quy trình Git hàng ngày trên Windows 11 PowerShell (git_daily.ps1)
# ==============================================================================
# Cấp quyền chạy script PowerShell (chỉ cần chạy 1 lần trên máy Windows):
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# --- [BƯỚC 1: ĐẦU NGÀY HOẶC KHI VỪA CHUYỂN MÁY] ---
.\git_daily.ps1 start
# (hoặc chỉ pull):
.\git_daily.ps1 pull
.\git_daily.ps1 -p

# --- [BƯỚC 2: KIỂM TRA TRẠNG THÁI & THAY ĐỔI TRONG NGÀY] ---
.\git_daily.ps1 status
.\git_daily.ps1 -s
.\git_daily.ps1 diff
.\git_daily.ps1 log
.\git_daily.ps1 -l

# --- [BƯỚC 3: XỬ LÝ TÌNH HUỐNG KHI ĐANG LÀM VIỆC] ---
# TH1: Vứt bỏ toàn bộ code sửa nháp để lấy lại bản chuẩn 100% trên GitHub:
.\git_daily.ps1 pull-discard
.\git_daily.ps1 -d
.\git_daily.ps1 -d -y

# TH2: Quên chưa pull mà đã sửa code (hoặc đã lỡ commit/-a) — GIỮ LẠI phần vừa sửa:
.\git_daily.ps1 pull-keep
.\git_daily.ps1 -k

# --- [BƯỚC 4: LƯU & ĐẨY CODE LÊN GITHUB] ---
# Cách 1: Đẩy toàn bộ thay đổi trong project lên GitHub trong 1 lệnh:
.\git_daily.ps1 push-all "Nội dung commit"
.\git_daily.ps1 -a "Nội dung commit"

# Cách 2: Chỉ commit và đẩy riêng nhóm file code giao diện (src/, assets/, main.py):
.\git_daily.ps1 push-gui "Cập nhật giao diện đăng nhập"

# Cách 3: Tạo commit ở máy local trước rồi push sau:
.\git_daily.ps1 commit "Nội dung commit"
.\git_daily.ps1 -c "Nội dung commit"
.\git_daily.ps1 push

# --- [BƯỚC 5: KHỞI TẠO & BẢO TRÌ REPOSITORY] ---
.\git_daily.ps1 branch
.\git_daily.ps1 -b
.\git_daily.ps1 init
.\git_daily.ps1 remote https://github.com/NguyenNgocAnh2610/2026_PyQt_A45.git
.\git_daily.ps1 fix-ignore
.\git_daily.ps1 help
.\git_daily.ps1 -h
