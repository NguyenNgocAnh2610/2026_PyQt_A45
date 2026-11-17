# AGENTS.md — 2026_PyQt_A45

## Mục tiêu
Phát triển **phần mềm giao diện và điều hành giá thử có thể tái sử dụng cho nhiều giá thử, nhiều đối tượng kiểm tra** bằng **Python + PySide6**, kết hợp **Qt Widgets** (cửa sổ, biểu mẫu, bảng, đồ thị) và **QML/Qt Quick** (dashboard, LED, nút điều khiển, HMI). **A45 / khối 1101K-10 là cấu hình triển khai đầu tiên, không phải giới hạn của kiến trúc.** Phần mềm trao đổi lệnh và dữ liệu với phần cứng qua **UART/Modbus**.

## Định hướng tái sử dụng và mở rộng
- **Ưu tiên thay cấu hình khi chuyển giá thử**: tên/ID hệ thống và đối tượng, danh mục tín hiệu, nhóm hiển thị, đơn vị, giới hạn, bài/bước kiểm tra, phụ thuộc và dữ liệu mô phỏng nằm trong `configs/<gia_thu>/`. Dùng `main.py --profile <duong_dan_system.json>`; không sao chép toàn bộ ứng dụng cho mỗi giá thử.
- **UI và bộ chạy bài dùng chung**: nhận profile/backend qua tham số; không rải điều kiện theo tên `A45`, `1101K`, ID bài cụ thể hoặc số lượng cố định 24 bài/40 kênh trong Widgets/QML/bộ chạy bài. ID ổn định dùng làm khóa; tên tiếng Việt chỉ dùng hiển thị. Bộ lọc/trang đang xem không được đổi bài đang chạy hoặc phát lệnh phần cứng.
- **Tách đặc thù thiết bị**: thao tác nghiệp vụ mới triển khai ở `device.py`; định dạng, thanh ghi, kiểu dữ liệu và scale ở protocol/định nghĩa thiết bị; I/O ở `communication.py`. UI chỉ gọi API backend. Các mảng và màn hình STM32 chuyên dụng được phép theo đúng hợp đồng STM32, không biến bản đồ đó thành mặc định cho mọi giá thử.
- **Cấu hình không thay thế mã xử lý**: thêm giá thử dùng các capability sẵn có chủ yếu bằng JSON; thiết bị/giao thức/capability mới cần triển khai và kiểm thử bộ xử lý tương ứng. Không cho JSON chứa Python, `eval`, hoặc mã thực thi tùy ý. Không tuyên bố mọi phần cứng đều chỉ cần thay JSON.
- **Giữ API ổn định, mở rộng khi có nhu cầu thật**: tái sử dụng component, model và thao tác đã có; tránh tạo lớp/plugin/package trống hoặc một framework tổng quát trước khi có tình huống sử dụng. Khi tách module, giữ trách nhiệm rõ ràng và cập nhật nơi gọi, mock, test, tài liệu cùng đợt.
- **Không phá cấu hình cũ**: thay đổi lõi phải kiểm tra A45 và cấu hình thứ hai (`alternative_profile` trong `tests/test_bench.py`). Khi đổi schema/hợp đồng không tương thích, nêu cách chuyển đổi hoặc báo lỗi rõ phiên bản không hỗ trợ; không âm thầm diễn giải dữ liệu cũ theo nghĩa mới.
- **Phạm vi đã có**: chọn một profile khi khởi động; UI/bộ chạy bài đã được thử với cấu hình hệ thống thứ hai trong mô phỏng. Chưa có chuyển profile nóng khi đang chạy, quản lý nhiều giá thử vật lý đồng thời hay bộ chạy bài trên phần cứng thật. Đây là hướng mở rộng, không phải tính năng đã hoàn tất.

## Tài liệu và hiện trạng cần nắm
| Nguồn | Vai trò |
| --- | --- |
| `AGENTS.md` | Quy tắc và định hướng phát triển lâu dài |
| `PROGRESS.md` | Hiện trạng, quyết định gần nhất, việc tiếp theo và vấn đề còn mở; nhật ký duy nhất |
| `README.md` | Cài đặt, chạy ứng dụng, preview và cách sử dụng |
| `docs/STM32_MODBUS_PC.md` | Tài liệu duy nhất về giao tiếp Modbus RTU PC ↔ STM32: hai mảng, quy tắc giao dịch, bộ chạy bài, simulator; phụ lục A45 v1 cũ |
| `docs/CONFIGURATION.md` | Tham chiếu schema profile JSON và hiện trạng profile A45 |
| `docs/CHUYEN_GIA_THU_MOI.md` | Quy trình từng bước chuyển sang giá thử/khối mới; cập nhật khi profile, adapter hoặc tiêu chí đánh giá thay đổi |
| `docs/PHAN_TICH_GIAO_THUC_VA_LUONG_CODE.md`, `docs/BAI_KIEM_TRA_1101K.md` | Tài liệu nguồn MCU và yêu cầu đo; **giữ nguyên nội dung**, chỗ hiệu chỉnh ghi ở tài liệu khác |

Tổ chức tài liệu: ở gốc repo chỉ giữ `README.md`, `AGENTS.md`, `CLAUDE.md`, `PROGRESS.md`; mọi tài liệu tham khảo đặt trong `docs/`. Mỗi nội dung chỉ nằm ở **một** tài liệu, nơi khác liên kết tới; chỉ sửa tài liệu khi nội dung tương ứng thực sự thay đổi.

Đối chiếu tài liệu với mã đang có trước khi sửa. Nếu các nguồn mâu thuẫn, nêu rõ và cập nhật tài liệu bị lỗi thời khi đã đủ căn cứ; không tự đổi yêu cầu đo/hợp đồng firmware để làm code chạy. Giao thức A45 v1 (phụ lục A của `docs/STM32_MODBUS_PC.md`) chỉ là đề xuất/simulator cũ; không dùng để suy ra giao thức STM32 hiện tại. Mã simulator cũ vẫn có nơi sử dụng, chỉ loại bỏ khi đã thay thế các phụ thuộc và kiểm thử liên quan.

## Cấu trúc định hướng
Cấu trúc dưới đây gồm phần đã triển khai và định hướng mở rộng. Hiện chạy bằng `main.py`, Login nằm tại `src/ui/widgets/login_page.py`, preview trong `tests/`. Đã có backend/device/communication/protocol, hai mảng STM32 Modbus RTU, simulator và dashboard QML; chỉ bổ sung module khi có tính năng, không tạo module rỗng. Xem `PROGRESS.md` để biết hiện trạng mới nhất và `docs/STM32_MODBUS_PC.md` khi làm firmware/truyền thông.

```text
2026_PyQt_A45/
├── main.py                 # Điểm khởi chạy: Login → MainWindow
├── requirements.txt
├── README.md
├── AGENTS.md
├── PROGRESS.md             # Tiến trình, lịch sử ngắn và bàn giao phiên làm việc
├── .backup/                # Bản nén toàn project trước thay đổi lớn, không đưa vào Git
├── configs/<gia_thu>/      # Profile hệ thống, đối tượng, phần cứng và dữ liệu mock
├── docs/                   # Đặc tả cấu hình, giao thức và hướng dẫn tích hợp
├── assets/
│   ├── styles/
│   │   ├── common.qss      # Style chung toàn ứng dụng Qt Widgets
│   │   └── <page>.qss      # Style riêng từng trang, ví dụ login.qss
│   └── images/             # Logo, ảnh, biểu tượng
├── src/
│   ├── __init__.py
│   ├── common/             # Hằng số, enum, cấu hình, kiểu dữ liệu và tiện ích dùng chung
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py   # Cửa sổ chính, sidebar, điều hướng
│   │   ├── qml/            # Màn hình và component HMI bằng QML
│   │   └── widgets/        # Các trang/widget Qt Widgets, gồm Login và trang đo kiểm
│   ├── backend.py          # QObject, Signal/Slot, trạng thái và điều phối yêu cầu UI
│   ├── device.py           # API nghiệp vụ điều khiển/đọc trạng thái thiết bị
│   ├── communication.py    # Kết nối và truyền nhận UART/Modbus, worker bất đồng bộ
│   ├── protocol.py         # Khung lệnh, mã lệnh, ánh xạ register, encode/decode
│   ├── simulator.py        # Thiết bị giả, không truy cập phần cứng
│   └── storage.py          # Lưu/đọc phiên, checkpoint nguyên tử ngoài GUI thread
└── tests/                  # Unit/integration test, mock thiết bị, chạy thử UI độc lập
```

## Quy tắc phát triển
1. **Giữ cấu trúc gọn**: chỉ thêm file/thư mục khi có nhu cầu thực; không tạo nhiều lớp trung gian không cần thiết.
2. **Tách UI và phần cứng**: UI xử lý hiển thị, tương tác, điều hướng và kiểm tra dữ liệu nhập cục bộ; yêu cầu nghiệp vụ/phần cứng đi qua API backend. Không đọc/ghi UART/Modbus trực tiếp trong QML/Widgets.
3. **Một nguồn trạng thái**: `backend.py` quản lý trạng thái thiết bị, thông báo bằng `Signal`/`Property`. Phân biệt trạng thái đã xác nhận, yêu cầu đang chờ và dữ liệu chưa biết/hết hạn. Không coi gửi lệnh thành công là thiết bị đã đổi trạng thái; khi mất kết nối, không hiển thị dữ liệu cũ như trạng thái hiện thời.
4. **Phân định trách nhiệm**: `device.py` diễn đạt thao tác nghiệp vụ; `protocol.py` định nghĩa giao thức; `communication.py` thực hiện I/O và timeout. Không lặp logic giữa các tầng.
5. **Không chặn GUI thread**: truyền nhận, chờ phản hồi, polling và các phép xử lý nặng phải bất đồng bộ hoặc chạy trong worker; cập nhật widget trên main thread.
6. **Định nghĩa chung đặt tại `src/common/`**: tên ứng dụng, cấu hình mặc định, enum trạng thái, kiểu dữ liệu và tiện ích dùng xuyên module. Tránh import vòng và giá trị hard-code rải rác.
7. **Kiểm thử từng phần**: UI có thể preview với backend giả; protocol và truyền thông phải test được không cần phần cứng. Bổ sung test khi thêm tính năng hoặc sửa lỗi.
8. **An toàn giao tiếp**: một thành phần sở hữu cổng serial và tuần tự hóa giao dịch; quản lý timeout, lỗi/gián đoạn và kiểm tra phản hồi. Không tự động retry lệnh tác động phần cứng nếu chưa xác định an toàn. Khi đóng ứng dụng, dừng polling, kết thúc worker và đóng kết nối có kiểm soát; không chờ vô hạn trên GUI thread.
9. **Mở rộng theo tính năng**: chỉ tách `backend.py`, `device.py` hoặc `communication.py` thành package khi chúng quá lớn hoặc xuất hiện nhiều thiết bị/giao thức độc lập; giữ ổn định API mà UI đang dùng.
10. **Dọn file sau mỗi đợt phát triển**: chỉ giữ các file cần thiết cho chạy ứng dụng, phát triển, kiểm thử và tài liệu. Xóa file trung gian, script/test dùng một lần đã hết mục đích, kết quả thử tạm, cache và file xác định chắc chắn không còn cần thiết. Trước khi xóa phải kiểm tra nội dung, nơi tham chiếu và phụ thuộc; không xóa test hồi quy, mock hoặc preview còn được dùng chỉ vì nằm trong `tests/`. File chưa rõ có cần giữ hay không **không được xóa**; liệt kê đường dẫn và lý do phân vân trong báo cáo để người dùng xem xét. Ghi ngắn kết quả dọn dẹp và các mục còn chờ xem xét trong `PROGRESS.md`.

## Sao lưu trước thay đổi lớn
- **Bắt buộc backup trước khi sửa** trong các đợt cập nhật lớn, refactor nhiều file, đổi cấu trúc/schema/giao thức, thay hoặc xóa nhóm mã chức năng; chủ động backup cả khi đánh giá thay đổi có rủi ro hoặc cần một mốc quay lại. Không đợi sửa xong mới sao lưu. Sửa nhỏ chỉ về tài liệu không bắt buộc tạo bản nén nếu không có rủi ro tương ứng.
- Nén **toàn bộ project tại thời điểm trước thay đổi** thành ZIP trong `.backup/` ở thư mục gốc. Bao gồm mã nguồn, cấu hình, assets, test, tài liệu, file ẩn, `.git`, các file chưa commit/chưa được Git theo dõi và file đang bị `.gitignore` bỏ qua. **Chỉ loại chính thư mục `.backup/`** để tránh nén lồng các bản sao lưu. Không dùng riêng `git archive`/commit thay cho bản sao đầy đủ của working tree; không âm thầm bỏ file không đọc được hoặc nằm ngoài danh sách Git.
- Tên file ghi rõ ngày, giờ đến giây theo giờ Việt Nam (UTC+07), kèm mục đích: `<ten_project>_YYYY-MM-DD_HH-mm-ss_UTC+07_before-<mo_ta_ngan>.zip`. Ví dụ: `GUI_2026-11-17_14-30-05_UTC+07_before-refactor-modbus.zip`. Nếu trùng tên, thêm mili giây hoặc hậu tố tăng dần; **không ghi đè backup cũ**.
- Dùng công cụ giữ được file/thư mục ẩn; kiểm tra danh sách nguồn để không bỏ sót `.git`, `.gitignore` hoặc file chưa theo dõi. Nếu dùng Python phải chạy trong Conda `qt_env`. Trong lúc nén không sửa project; nếu phát hiện file nguồn thay đổi, phải tạo lại bản sao nhất quán trước khi tiếp tục.
- Sau khi nén, mở/đọc kiểm tra ZIP: danh sách file và đường dẫn tương đối phải khớp nguồn (trừ `.backup/`), có các file chính và kiểm tra toàn vẹn/CRC thành công. File nén lỗi hoặc chưa đủ không được coi là backup hợp lệ. Nếu tạo/kiểm tra backup thất bại, báo rõ nguyên nhân và **chưa thực hiện thay đổi lớn** cho tới khi có bản hợp lệ.
- Ghi đường dẫn backup, thời điểm, lý do và kết quả kiểm tra ngắn gọn vào `PROGRESS.md` trước khi sửa mã; không tạo nhật ký backup thứ hai. `.backup/` phải được bỏ qua trong Git và **không thuộc diện dọn file tạm**. Không tự xóa, ghi đè hoặc luân chuyển backup cũ nếu người dùng chưa yêu cầu.
- Khi cần phục hồi, giải nén vào thư mục riêng để đối chiếu trước; không tự đè lên working tree đang có thay đổi. Bản sao trong `.backup/` là mốc phục hồi mã cục bộ, không thay thế lịch sử Git hoặc bản sao ngoài máy khi cần bảo vệ khỏi hỏng ổ đĩa.

## Cấu hình, bài kiểm tra và kết quả đo
- Dùng cấu trúc hiện có: `system.json` tham chiếu file đối tượng, phần cứng và fixtures trong thư mục profile. Định nghĩa schema/kiểm tra cấu hình tập trung tại `src/common/profiles.py`; không lặp validator ở từng widget. Đường dẫn cấu hình con phải nằm trong thư mục profile; đường dẫn tài nguyên dựa trên vị trí project, không dựa vào thư mục chạy tùy ý.
- Kiểm tra cấu hình trước khi chạy: schema version, ID duy nhất, tham chiếu tín hiệu/bài/bước, phụ thuộc không vòng, capability có bộ xử lý, đơn vị, giới hạn, số hữu hạn và thời gian hợp lệ. Khóa mới phải có ý nghĩa, giá trị mặc định hoặc lỗi thiếu rõ ràng; cập nhật loader, cấu hình mẫu, test và tài liệu cùng nhau.
- Giữ nguyên yêu cầu nguồn, đơn vị, điều kiện kích thích, trình tự, thời gian ổn định và dung sai. Chỗ thiếu hoặc mâu thuẫn phải ghi `issues`/TODO và giữ trạng thái chưa đánh giá/BLOCKED; không tự điền thông số để có PASS. Giá trị demo phải ghi rõ là demo.
- PASS/FAIL do backend/bộ đánh giá tính từ mẫu hợp lệ, đúng đơn vị và đúng thời điểm sau ổn định. Mẫu thiếu, lỗi, hết hạn, giá trị yêu cầu hoặc ACK không được thay cho số đo. Không làm tròn số để thay đổi kết luận; làm tròn chỉ phục vụ hiển thị.
- Tách tự kiểm tra giá thử khỏi kiểm tra đối tượng. Tuân thủ phụ thuộc giữa bài; không suy luận hai bài độc lập trên phần cứng từ việc chạy được độc lập trong mock. Hủy, lỗi giao tiếp, thiếu đặc tả và đo ngoài dung sai phải có trạng thái phân biệt, không gộp thành PASS.
- Đổi tên hiển thị không được làm mất dữ liệu cũ: giữ ID, namespace QSettings và định danh lưu phiên ổn định. Không tự đổi `SETTINGS_ORGANIZATION` chỉ vì thấy tên khác A45; nếu cần đổi phải có phương án chuyển dữ liệu.

## Giao tiếp, mô phỏng và phần cứng thật
- PC là Master, STM32 CPUv1.0 là Slave USART2, dùng Modbus RTU FC03/06/16. Hai mảng `mod_buf_to_write` và `mod_buf_to_read` độc lập; cùng địa chỉ không có nghĩa là đọc lại giá trị vừa ghi. Kích thước/enum ở `src/common/stm32.py`, hợp đồng chi tiết ở `docs/STM32_MODBUS_PC.md`.
- Mảng ghi là bản nháp yêu cầu; chụp dữ liệu khi gửi. ACK chỉ xác nhận giao dịch nhận lệnh, không tự copy sang mảng đọc hoặc xác nhận đầu ra. Không tự ghi cả mảng zero, gửi lại lệnh encoder hoặc gửi bản nháp khi mở COM/đổi nguồn/kết nối lại.
- Mở COM, slave trả lời, dữ liệu hợp lệ và thiết bị sẵn sàng chạy bài là các trạng thái khác nhau. Hủy phản hồi trễ của phiên/nguồn cũ; mất cáp, đổi thiết bị/ID hoặc hết hạn phải vô hiệu hóa trạng thái hiện thời. Khi thêm polling chỉ đọc, tuần tự hóa với thao tác ghi và dừng có kiểm soát.
- Byte order, signed/unsigned, scale, bitfield, địa chỉ zero-based và timeout phải có định nghĩa rõ và test không cần mạch. Qt xử lý khung/CRC RTU của đường thật; không bọc giao thức A45 v1 cũ vào MCU hiện tại. Nếu MCU chưa cung cấp timestamp, chiều dài RX hay xác nhận hoàn thành thì giữ là chưa biết, không tự suy ra.
- Tách rõ nguồn thật, simulator giao tiếp và demo đồ thị. Không âm thầm chuyển sang mock khi COM lỗi; không dùng demo để kết luận bài đo. Hệ số tăng tốc chỉ áp dụng chờ trong mô phỏng, không rút ngắn thời gian yêu cầu hoặc timeout trên mạch thật.
- Simulator cần test cả thành công, sai phản hồi, timeout, mất kết nối và trạng thái cũ theo phạm vi thay đổi; không tạo số đo bằng cách lấy tiêu chuẩn mong muốn trong bộ đánh giá. Ghi rõ phần chưa mô phỏng như timing RTU, tín hiệu điện hoặc race trong MCU.
- Đọc/ghi chẩn đoán thật đã có. Bộ chạy bài A45 dùng `adapter=stm32` (hai mảng, ánh xạ `hardware.stm32_io` đang `assumed`) nhưng chỉ chạy với simulator, `production_ready=false`. Chỉ mở chạy bài thật sau khi đã chốt ánh xạ, giới hạn, liên động, trình tự chuẩn bị/dừng và có kiểm chứng thực tế; không bật bằng cách bỏ validator hoặc đổi một cờ cấu hình.

## Lưu phiên, vòng đời và trải nghiệm sử dụng
- `storage.py` chịu trách nhiệm I/O lưu trữ; dùng snapshot độc lập, ghi nguyên tử ngoài GUI thread. Phiên phải truy vết được profile/phiên bản, đối tượng/serial, nguồn mô phỏng hay thật, từng lần thử, số đo, giới hạn và trạng thái kết thúc. Không sửa ngược kết quả cũ khi đổi cấu hình hiện tại.
- Khi lỗi lưu, giữ dữ liệu trong bộ nhớ và báo lỗi/lưu lại; không báo đã lưu thành công hoặc mất phiên âm thầm. Phiên dở sau khởi động lại được đánh dấu gián đoạn, không tự tiếp tục thao tác hay phát lại lệnh phần cứng.
- Khi đóng trang/ứng dụng, quản lý rõ quyền sở hữu QObject, timer, worker, cổng và callback. Không tạo kết nối Signal/timer trùng khi mở lại trang; không cập nhật widget đã bị hủy. Chờ kết thúc có thời hạn và bất đồng bộ.
- Tái sử dụng UI/component và theme; widget phải nhận backend/profile thay vì tự tạo kết nối thiết bị. `src/` không import `tests/`. Preview dùng UI thật với dữ liệu giả, không mở COM hoặc ghi đè cài đặt/phiên của người dùng.
- Kiểm tra bàn phím, resize và DPI khi sửa UI; trạng thái bận/lỗi/mất kết nối phải rõ. Không hiện hộp thoại lỗi lặp theo mỗi vòng polling. Không tự thêm camera, xuất báo cáo hoặc trang mới chỉ vì có tên trong menu định hướng.

## Quy trình thêm giá thử hoặc đối tượng mới
1. Đọc yêu cầu, xác định phần dùng lại và phần đặc thù; ghi thông số chưa biết, không lấy thông số A45 áp sang thiết bị khác.
2. Tạo/chỉnh profile trong `configs/<gia_thu>/`: hệ thống, đối tượng, tín hiệu, bài/bước, đơn vị, điều kiện và dữ liệu mock độc lập. Với đối tượng khác cùng giá thử, ưu tiên dùng lại phần cấu hình phù hợp.
3. Nếu capability/giao thức chưa có, định nghĩa hợp đồng rồi triển khai tại device/protocol/communication; chỉ thêm UI chuyên dụng khi thao tác thực sự cần.
4. Validate profile, preview bằng `--profile`, kiểm tra mô phỏng thành công/lỗi và hồi quy A45/cấu hình thứ hai. Không sửa UI theo tên hệ thống để làm test đi qua.
5. Ghép thiết bị thật trong phạm vi đã cho phép, đối chiếu dữ liệu và trạng thái thực tế rồi mới nối bộ chạy bài. Cập nhật hướng dẫn, giới hạn và `PROGRESS.md`; không ghi một định hướng chưa triển khai thành tính năng đã có.

## Môi trường và chạy thử
- **Luôn chạy Python trong môi trường Conda `qt_env` đã có**, gồm ứng dụng, preview, test và công cụ Python. Kích hoạt bằng `conda activate qt_env`; không tự tạo lại môi trường hoặc dùng Python hệ thống/base.
- Chạy từ thư mục gốc:
  ```powershell
  conda activate qt_env
  python main.py
  ```
- Nếu shell không hỗ trợ activate, dùng `conda run -n qt_env python <script.py>`; nếu vẫn lỗi, báo rõ thay vì đổi môi trường. Khi cần cài dependency, dùng `python -m pip` trong `qt_env`.
- Preview bằng `python -m tests.preview_login` và `python -m tests.preview_widgets`; chạy test tự động bằng `python -m unittest discover -s tests -v`. Kiểm tra trường trống, đăng nhập sai/đúng, hiện mật khẩu, bàn phím và resize. Test hiện dùng `unittest` và `PySide6.QtTest`, chưa đặt ngưỡng coverage. Test tự động dùng tên `test_*.py`, mock thiết bị và kiểm tra cả timeout/mất kết nối.
- Chạy cấu hình khác bằng `python main.py --profile configs/<gia_thu>/system.json`; preview màn hình chính bằng `python -m tests.preview_main --profile ...`; thử hai mảng STM32 bằng `python -m tests.preview_stm32` (giả lập).
- Chạy kiểm thử phù hợp phần thay đổi; khi sửa lõi dùng chung/giao thức/bộ chạy bài cần kiểm tra hồi quy liên quan và bộ test toàn dự án. Chỉ sửa tài liệu thì kiểm tra nội dung, đường dẫn và tính nhất quán; không ghi là đã chạy lại test nếu chưa chạy. Có thể dùng `python -B` để không tạo bytecode trong đợt kiểm thử/dọn file.
- Dependency mới phải có nhu cầu cụ thể và được cập nhật trong `requirements.txt`; không tự thay phiên bản Python/Qt hay tạo môi trường mới để né lỗi. Test tự động mặc định không mở cổng hoặc điều khiển mạch thật.

## Style và quy ước code
- Dùng UTF-8, thụt lề Python 4 dấu cách, `snake_case` cho hàm/biến và `PascalCase` cho lớp. Giữ tiếng Việt hiển thị đúng; chưa có formatter/linter được cấu hình.
- `assets/styles/common.qss` là nền style chung toàn project cho Qt Widgets: font, màu nền/chữ, input, button, bảng và các trạng thái dùng chung. Đã được nạp qua `src/common/styles.py`; `login.qss` chỉ chứa phần riêng của Login.
- Nạp `common.qss` ở cấp `QApplication` trước; QSS riêng từng trang chỉ bổ sung/ghi đè phần đặc thù, không sao chép lại toàn bộ style chung. Preview độc lập cũng phải nạp cùng nền style. QSS không có cơ chế kế thừa/import như CSS web; dựa vào cascade của Qt và phạm vi áp dụng.
- Giới hạn selector riêng bằng `objectName` hoặc dynamic property để tránh ảnh hưởng trang khác. Hạn chế `setStyleSheet()` rải rác trong Python; ưu tiên property cho trạng thái và giữ quy tắc hiển thị trong QSS.
- QSS chỉ áp dụng cho Qt Widgets; QML cần theme/component riêng, giữ nhất quán với bảng màu và kích thước chung khi tích hợp.
- Không đưa mật khẩu thật vào code/log; thông tin đăng nhập demo chỉ dùng để preview.

## Commit và pull request
- Lịch sử dùng tiêu đề ngắn tiếng Việt hoặc tiếng Anh, chưa có chuẩn bắt buộc. Viết rõ hành vi thay đổi, ví dụ `Sửa nút hiện mật khẩu`; giữ mỗi commit tập trung.
- PR nêu thay đổi, cách kiểm tra, giới hạn chưa kiểm chứng và issue liên quan nếu có; thêm ảnh chụp khi thay đổi giao diện.

## Quy trình khi AI chỉnh sửa code
- Đọc `PROGRESS.md` trước khi phát triển. Mỗi đợt sửa mã phải cập nhật file này: đã làm, đang làm, tiếp theo, vấn đề còn mở và kết quả kiểm thử; ghi lịch sử ngắn theo ngày, không tạo nhiều file nhật ký.
- Đầu phiên mới: đọc AGENTS/PROGRESS, kiểm tra `git status`, đọc tài liệu đúng phần việc và mã liên quan. Giữ các thay đổi có sẵn của người dùng; file không tồn tại phải kiểm tra lại hiện trạng, không tự khôi phục bản cũ hoặc giả định nó đã được triển khai.
- Đọc các file liên quan trước khi sửa; ưu tiên thay đổi nhỏ, tương thích cấu trúc hiện có.
- Đánh giá nhu cầu sao lưu trước mỗi đợt sửa; nếu thuộc diện thay đổi lớn/rủi ro, thực hiện mục **Sao lưu trước thay đổi lớn** và xác minh ZIP thành công trước khi chỉnh sửa hoặc xóa mã.
- Với UI mới: thiết kế trang/component → preview độc lập → nối backend → tích hợp menu.
- Với lệnh phần cứng mới: định nghĩa giao thức/địa chỉ → triển khai device và communication → test với mock → nối backend/UI → kiểm tra với thiết bị thật.
- Chỉ kiểm tra với thiết bị thật khi có thiết bị và được phép thao tác; nếu chưa thực hiện, ghi rõ giới hạn, không khẳng định đã xác minh.
- Không tự ý đổi giao thức, địa chỉ thanh ghi, baudrate hoặc giả định trạng thái thiết bị; những thông số chưa có phải để cấu hình/TODO rõ ràng.
- Sau thay đổi, nêu file đã sửa, cách chạy thử và giới hạn chưa kiểm chứng.
- Trước khi bàn giao phiên: cập nhật quyết định đã chốt, việc đang dở (nếu có), bước tiếp theo cụ thể, test đã chạy và giới hạn/điểm cần người dùng quyết định trong PROGRESS. Không ghi đã commit/đã thử phần cứng/đã hoàn tất tính năng nếu chưa có bằng chứng. Không tạo file bàn giao hoặc nhật ký thứ hai trùng nội dung.
