conda create --name qt_env
conda activate qt_env
pyuic6 -x main_window.ui -o main_window.py

# 1. Đầu ngày hoặc khi vừa chuyển máy:
./git_daily.sh start
# (hoặc: ./git_daily.sh pull)

# 2. Trường hợp 1: Sửa nháp không hợp lý, muốn vứt bỏ hết và lấy lại bản chuẩn trên GitHub:
./git_daily.sh pull-discard
# hoặc viết tắt:
./git_daily.sh -d

# 3. Trường hợp 2: Quên chưa pull mà đã sửa code — muốn GIỮ LẠI phần vừa sửa:
./git_daily.sh pull-keep
# hoặc viết tắt:
./git_daily.sh -k

# 4. Cuối buổi / sau khi hoàn thành tính năng, đẩy toàn bộ lên GitHub:
./git_daily.sh push-all "Cập nhật git_daily.sh thêm pull-discard, pull-keep, push-all"
# hoặc viết tắt:
./git_daily.sh -a "Cập nhật git_daily.sh thêm pull-discard, pull-keep, push-all"