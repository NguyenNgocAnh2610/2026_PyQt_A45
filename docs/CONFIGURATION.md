# Cấu hình profile giá thử (tham chiếu schema)

Tài liệu tham chiếu **duy nhất** cho các trường JSON của một profile. Quy trình
từng bước khi tạo giá thử mới: [CHUYEN_GIA_THU_MOI.md](CHUYEN_GIA_THU_MOI.md).
Ý nghĩa thanh ghi STM32: [STM32_MODBUS_PC.md](STM32_MODBUS_PC.md).

## Tổng quan

Mỗi giá thử là một thư mục `configs/<gia_thu>/`, chọn khi khởi động:

```powershell
conda run -n qt_env python main.py --profile configs/a45/system.json
```

Không có `--profile` thì dùng `DEFAULT_PROFILE` (`src/common/testing.py`, hiện là A45).
Chỉ một profile mỗi lần chạy; chưa đổi profile khi đang chạy.

| File | Nội dung |
|---|---|
| `system.json` | Giá thử, tín hiệu, bài tự kiểm tra; trỏ tới 3 file còn lại |
| File đối tượng (A45: `1101k.json`) | Khối được kiểm tra: trình tự, bài, bước, dải cho phép |
| `hardware.json` | Adapter bộ chạy bài và ánh xạ tín hiệu ↔ thanh ghi |
| `mock.json` | Dữ liệu mô phỏng |

Quy ước chung:
- Mọi file có `"schema_version": 1`; file con phải nằm trong thư mục profile.
- `id` dùng chữ Latin và **cố định** (khóa lưu dữ liệu); `label`/`name` tiếng Việt chỉ để hiển thị, đổi tự do.
- JSON không chứa mã thực thi, biểu thức hay `eval`.
- `src/common/profiles.py` kiểm tra toàn bộ khi nạp, lỗi báo kèm vị trí và ứng dụng không mở.

## system.json

| Trường | Ý nghĩa |
|---|---|
| `id`, `name`, `subtitle` | Mã giá thử; tên và dòng phụ hiển thị trên màn hình chính |
| `target_file`, `hardware_file`, `fixtures_file` | Tên file con trong cùng thư mục |
| `signals` | Danh mục mọi tín hiệu; thứ tự = thứ tự hiển thị |
| `status_signals` | Vai trò chung `ready`/`output`/`fault` → ID tín hiệu (không bắt buộc đủ ba) |
| `diagnostics` | Bài **tự kiểm tra giá thử**, cùng cấu trúc với bài kiểm tra khối; không được trống |
| `monitor_channels` | (Tùy chọn) tối đa 6 kênh cho đồ thị "Quan sát tín hiệu" |

### Tín hiệu (`signals[]`)

```json
{"id": "xp1_50", "label": "XP1 · chân 50", "group": "Đáp ứng khối", "unit": "V",
 "kind": "number", "source": "measured", "decimals": 2, "stale_ms": 1000,
 "chart": true, "states": {}}
```

| Trường | Ý nghĩa |
|---|---|
| `kind` | `number`, `boolean` hoặc `state` |
| `source` | `measured`: số đo thật; `derived`: giá trị yêu cầu/lệnh gửi xuống (không dùng cho số đo); `confirmed`: trạng thái xác nhận |
| `unit` | Đơn vị; `checks` phải dùng đúng đơn vị này |
| `decimals` | 0–6, chỉ ảnh hưởng hiển thị |
| `stale_ms` | > 0; mẫu cũ hơn thì hết hạn và không được dùng để đánh giá |
| `states` | Với `boolean`/`state`: `{"0": {"label": "TẮT", "color": "#8194a7"}, ...}` |
| `chart` | Cờ cũ, không còn quyết định đồ thị (dùng `monitor_channels`) |

### `monitor_channels[]`

`{"id", "label", "kind": "analog" | "pwm", "unit"}`; `id` duy nhất, `label`/`unit` không trống.
Đây chỉ là danh mục hiển thị, không phải ánh xạ thanh ghi. Dữ liệu đồ thị hiện là
**demo** (`src/common/monitor.py`), không dùng để đánh giá. Bỏ khóa → 4 kênh demo; `[]` → không có kênh.

## File đối tượng (bài và bước)

| Trường | Ý nghĩa |
|---|---|
| `id`, `name`, `version` | Mã khối, tên khối hiển thị, phiên bản cấu hình |
| `source_file`, `source_paragraphs` | Tài liệu gốc và **nguyên văn** các đoạn yêu cầu (truy vết) |
| `limitations` | Giới hạn đã biết của cấu hình |
| `sequences` | Trình tự chuẩn bị/kết thúc dùng chung (adapter `stm32`) |
| `tests` | Danh sách bài |

### `sequences`

```json
"power_all": {"basis": "GIẢ ĐỊNH, chưa xác minh: …", "actions": [{"signal": "dc_27v", "value": 1}]}
```

`basis` bắt buộc: căn cứ tài liệu, hoặc ghi rõ "GIẢ ĐỊNH". Bài tham chiếu bằng
`preparation`/`cleanup`. Cleanup luôn kết thúc bằng `safe_state` của `hardware.json`.

### Bài (`tests[]`)

| Trường | Ý nghĩa |
|---|---|
| `id`, `number`, `name`, `group`, `source` | Mã bài cố định, số thứ tự, tên, nhóm hiển thị, tham chiếu tài liệu |
| `dependencies` | ID bài phải PASS trước trong phiên; không được vòng; chưa PASS → SKIPPED |
| `independence` | `mock_only` / `verified` / `unknown` (`unknown` + có bài FAIL trước → BLOCKED) |
| `preparation`, `cleanup` | Adapter `stm32`: ID trong `sequences`. Adapter `mock`: `mock_baseline` / `mock_safe` |
| `issues` | Điểm chưa chốt; có issue ở bài hoặc bước → **BLOCKED**, không gửi lệnh |
| `steps` | Danh sách bước |

### Bước (`steps[]`)

```json
{"id": "S01", "title": "Kích thích +3 V vào 40XP1", "capability": "stimulate_measure",
 "actions": [{"signal": "set_40", "value": 3}],
 "wait_ms": 250, "timing_basis": "Thời gian demo; chưa xác minh phần cứng",
 "checks": [{"signal": "xp1_50", "nominal": 8.5, "tolerance": 0.2, "unit": "V"}],
 "issues": []}
```

| Trường | Ý nghĩa |
|---|---|
| `capability` | Phải có trong `hardware.capabilities` (hiện: `stimulate_measure`, `diagnose`) |
| `actions` | Lệnh `{signal, value}`; cộng dồn qua các bước trong cùng bài |
| `wait_ms` | Thời gian chờ ổn định trước khi đo; `timing_basis` ghi nguồn gốc (tiêu chuẩn hay demo) |
| `checks` | Phép đo `{signal, nominal, tolerance, unit}`; không được trống |

Quy tắc đánh giá (`evaluate()` trong `src/backend.py`):
- Đạt khi số đo nằm trong khoảng đóng `[nominal − tolerance, nominal + tolerance]`.
- `nominal` hoặc `tolerance` = `null` → "Chưa đánh giá", không bao giờ PASS.
- Mẫu thiếu, lỗi hoặc hết hạn → ERROR. Mẫu phải mới hơn thời điểm hết chờ ổn định.
- Hiện chỉ hỗ trợ dải đối xứng; dải lệch hay so sánh hai tín hiệu cần sửa mã.

Hệ số ×1/×10/×60 (Cài đặt) chỉ rút ngắn thời gian chờ trong mô phỏng và được lưu
vào phiên; không đổi timeout giao dịch.

## hardware.json

| Trường | Ý nghĩa |
|---|---|
| `adapter` | `stm32`: bộ chạy bài ghi/đọc hai mảng STM32 CPUv1.0. `mock`: khung A45 v1 cũ |
| `production_ready` | Bắt buộc `false` (chưa có đường chạy mạch thật) |
| `capabilities` | Loại thao tác bước được dùng |
| `serial` | Gợi ý cổng/baud/parity/stop/slave cho chẩn đoán |
| `stm32_io` | Ánh xạ tín hiệu ↔ thanh ghi (adapter `stm32`) |
| `registers`, `wire_signals` | Giao thức A45 v1 cũ; validator vẫn bắt buộc `wire_signals` liệt kê **mọi** tín hiệu (ID 1–65535 duy nhất, tối đa 80 tín hiệu) |
| `unresolved` | Ghi chú các điểm chưa xác minh |

### `stm32_io`

```json
"stm32_io": {
  "slave": 9, "mux_register": "MUX", "mux_settle_ms": 20,
  "session":    {"Mode": 1, "Plan": 2},
  "safe_state": {"DAC_val": 0, "DOUT": 0, "SW01": 0, "SW02": 0, "MUX": 0, "Power": 0},
  "outputs": {
    "dc_27v": {"kind": "bit", "register": "Power", "bit": 1, "on_value": 1, "status": "assumed"},
    "set_40": {"kind": "analog", "register": "DAC_val", "route": [{"register": "SW02", "bit": 3}],
               "scale": -0.005, "offset": 0, "min": -3.5, "max": 3.5,
               "count_min": -1083, "count_max": 1045, "status": "assumed"},
    "set_43": {"status": "unsupported", "reason": "…"}
  },
  "inputs": {
    "xp1_50": {"kind": "adc", "register": "ADC3_val", "signed": true, "scale": 0.01, "offset": 0,
               "mux": 14, "status": "assumed"},
    "ready":  {"kind": "link", "status": "assumed"}
  }
}
```

| Khóa | Quy tắc |
|---|---|
| `slave` | 1–247 |
| `session` | Ghi đầu mỗi bài; bắt buộc `"Mode": 1` |
| `safe_state` | Giá trị an toàn cho **mọi** thanh ghi mà output dùng (gồm MUX) |
| `mux_register`, `mux_settle_ms` | Thanh ghi chọn kênh đo; thời gian chờ sau khi đổi kênh |
| Tên thanh ghi | Theo `WriteRegister`/`ReadRegister` (`src/common/stm32.py`). Chỉ được ghi `BENCH_WRITABLE`, không DataO1/DataO2/DataO3/CDT/DataT/Null |
| Output `bit` | Đặt bit khi action đúng `on_value` (mức tiếp điểm cấp: 1, 27, 5, 0 V…); tắt bằng `safe_state`. Không hai output chung một bit |
| Output `analog` | Mã DAC = round((giá trị − offset) / scale), bật các bit `route`. Ngoài `min/max` hoặc `count_min/count_max` → lỗi, không kẹp giá trị. Hai mức khác nhau cùng lúc trên một DAC → lỗi |
| Input `adc` | Giá trị = (int16 nếu `signed`) × `scale` + `offset`; `mux` = mã ghi vào `mux_register` trước khi đọc (`null` nếu không cần). Cặp (`mux`, thanh ghi) không trùng |
| Input `link` | = 1 khi FC03 hợp lệ |
| `status` | `assumed` (chưa đo kiểm) / `verified` (**chỉ sau khi đo kiểm thật**) / `unsupported` + `reason` (bài dùng tín hiệu này → BLOCKED) |
| `note`, `*_note` | Ghi chú tự do |

Mọi tín hiệu dùng trong `actions`, `checks` và `sequences` phải có mục trong
`stm32_io`. Khi nạp, validator chạy thử chuỗi safe_state → chuẩn bị → từng bước
của mọi bài để bắt bit trùng, xung đột DAC hoặc giá trị ngoài dải.

## mock.json

| Khóa | Adapter | Nội dung |
|---|---|---|
| `stm32_cases` | `stm32` | `[{when: {tín hiệu yêu cầu: giá trị}, after_ms?, measure: {tín hiệu đo: giá trị}}]` |
| `cases` | `mock` | `{"<test_id>/<step_id>": {tín hiệu đo: giá trị}}` cho mọi bước |

Với `stm32_cases`, simulator chọn case khớp nhiều điều kiện `when` nhất (và đã đủ
`after_ms` thời gian mô phỏng kể từ khi kích thích bật) cho kênh MUX đang đọc;
không khớp thì trả 0. Số liệu là **demo**: không chép dải tiêu chuẩn để tạo PASS.

## Hiện trạng profile A45 / khối 1101K-10

Tài liệu nguồn: [BAI_KIEM_TRA_1101K.md](BAI_KIEM_TRA_1101K.md). Điểm chưa đủ đặc tả (giữ `issues`):

| Bài | Cần xác minh |
|---|---|
| P01 | Chuyển/đáp ứng 36 V → 22 V; thiếu dung sai điện áp; ý nghĩa kiểm tra từng pha |
| P12 | Dung sai nhánh +8,5 V |
| P16 | Đầu ra 26XP1 được ghi cho kênh II |
| P17 | Dung sai nhánh +9 V |
| P20–P24 | Điều kiện kích thích ứng với từng cực tính `±` |
| P21 | Điều kiện ±3 V tại 54XP1 |
| P23–P24 | Có/không CX3 nhưng cùng ghi 5 V tại 13XP1 |

Thêm vào đó, P10/P11/P12 dùng xung 10 kHz và P01 dùng đo tần số, là hai việc
CPUv1.0 không làm được (`unsupported`). Chạy tự động mô phỏng: **13 PASS,
11 BLOCKED → "Chưa đầy đủ"**. PASS mô phỏng không có nghĩa bài sẵn sàng chạy phần
cứng: ánh xạ `stm32_io` và các trình tự `sequences` vẫn là giả định. Tự kiểm tra:
D01 chỉ kiểm tra FC03; D02/D03 BLOCKED.

Cấu hình thứ hai `alternative_profile` (`tests/test_bench.py`, trạm nhiệt demo,
adapter `mock`) kiểm tra rằng UI và bộ chạy bài không phụ thuộc tên A45.
