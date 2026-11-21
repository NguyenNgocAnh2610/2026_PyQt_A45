# Cấu hình profile giá thử (tham chiếu schema)

Tài liệu tham chiếu **duy nhất** cho các trường JSON của một profile. Quy trình
từng bước khi tạo giá thử mới: [07 Chuyển giá thử](07_CHUYEN_GIA_THU_MOI.md).
Ý nghĩa thanh ghi STM32: [02 Giao thức](02_GIAO_THUC_MODBUS.md).

## Mục lục

- [Tổng quan](#tổng-quan)
- [system.json](#systemjson)
  - [Tín hiệu (`signals[]`)](#tín-hiệu-signals)
  - [`monitor_channels[]`](#monitor_channels)
- [File đối tượng (bài và bước)](#file-đối-tượng-bài-và-bước)
  - [`sequences`](#sequences)
  - [Bài (`tests[]`)](#bài-tests)
  - [Bước (`steps[]`)](#bước-steps)
- [hardware.json](#hardwarejson)
  - [`stm32_io`](#stm32_io)
- [mock.json](#mockjson)
- [Hiện trạng profile A45 / khối 1101K-10](#hiện-trạng-profile-a45--khối-1101k-10)

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
| `stop_on_fail` | Tùy chọn (`true`/`false`). Bài FAIL thì về an toàn rồi **dừng cả lượt** (dùng cho bài nguồn P01/P02) |
| `notes` | Tùy chọn. Ghi chú tự do (ví dụ điểm còn nghi vấn nhưng người dùng giữ đúng tài liệu) |
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
| `capability` | Phải có trong `hardware.capabilities` (hiện: `stimulate_measure`, `stimulate`, `diagnose`) |
| `actions` | Lệnh `{signal, value}`; cộng dồn qua các bước trong cùng bài. `value: null` = nhả tiếp điểm/hở chân; output nguồn có `off_value` thì `value: 0` cũng là nhả |
| `wait_ms` | Thời gian chờ ổn định trước khi đo; `timing_basis` ghi nguồn gốc (tiêu chuẩn hay demo) |
| `checks` | Phép đo `{signal, nominal, tolerance, unit, absolute?, basis?}`. Chỉ bước `capability: "stimulate"` (giữ/chuyển trạng thái, ví dụ giữ 36 V đủ 2 phút) được để trống |

Quy tắc đánh giá (`evaluate()` trong `src/backend.py`):
- Đạt khi số đo nằm trong khoảng đóng `[nominal − tolerance, nominal + tolerance]`.
- `absolute: true`: so `|số đo|` (chấp nhận cả hai dấu, ví dụ P20).
- `nominal` hoặc `tolerance` = `null` → "Chưa đánh giá", không bao giờ PASS.
- Mẫu thiếu, lỗi hoặc hết hạn → ERROR. Mẫu phải mới hơn thời điểm hết chờ ổn định.
- Giá trị nhập tay bị bỏ trống (input `manual`): ghi `nominal` với chất lượng `default`, vẫn đánh giá nhưng lý do ghi "mặc định, chưa đo"; phiên có `defaults_used: true`.
- `basis` (tùy chọn): nguồn gốc dung sai/dấu, bắt buộc ghi khi giá trị do người dùng chỉ định tạm.
- Hiện chỉ hỗ trợ dải đối xứng; dải lệch hay so sánh hai tín hiệu cần sửa mã.

Hệ số ×1/×10/×60 (Cài đặt) chỉ rút ngắn thời gian chờ trong mô phỏng và được lưu
vào phiên; không đổi timeout giao dịch.

## hardware.json

| Trường | Ý nghĩa |
|---|---|
| `adapter` | `stm32`: bộ chạy bài ghi/đọc hai mảng STM32. `mock`: khung A45 v1 cũ |
| `cpu_map` | Bản đồ thanh ghi của firmware CPU: `CPUv1.0` (mặc định) hoặc `CPUv1.1` (A45, có `Matrix0/1` ở index 18–19, `CDT` ở 20, DI 1–42). Danh sách trong `src/common/stm32.py` → `CPU_MAPS` |
| `production_ready` | Bắt buộc `false`: profile chưa được phê duyệt toàn bộ. Chạy bài trên mạch thật mở **từng bài** khi mọi ánh xạ bài dùng là `verified` (xem `stm32_io` → `status`) |
| `capabilities` | Loại thao tác bước được dùng |
| `serial` | Gợi ý cổng/baud/parity/stop/slave cho chẩn đoán |
| `stm32_io` | Ánh xạ tín hiệu ↔ thanh ghi (adapter `stm32`) |
| `registers`, `wire_signals` | Giao thức A45 v1 cũ; validator vẫn bắt buộc `wire_signals` liệt kê **mọi** tín hiệu (ID 1–65535 duy nhất, tối đa 80 tín hiệu) |
| `unresolved` | Ghi chú các điểm chưa xác minh |

### `stm32_io`

```json
"stm32_io": {
  "slave": 11, "mux_register": "MUX", "mux_settle_ms": 20, "di_update_ms": 150, "break_ms": 150,
  "mux_layout": {"banks": 2, "bank_bits": 8, "channels": 32, "idle_channel": 31},
  "extra_write_registers": {"Matrix2_0": 31, "Matrix2_1": 32},
  "session":    {"Mode": 1, "Plan": 2},
  "safe_state": {"DAC_val": 0, "DOUT": 0, "MUX": 7967, "Power": 0, "Matrix0": 0, "Matrix1": 0,
                 "Matrix2_0": 0, "Matrix2_1": 0},
  "hmi_forced_bits": {"Power": [7, 8, 9]},
  "interlocks": [["ac_36v", "ac_22v"]],
  "dac": {"register": "DAC_val", "scale": -0.00155, "offset": 0, "min": -1.5, "max": 1.5,
          "count_min": -1000, "count_max": 1000, "status": "assumed"},
  "sources": {"P3V": {"value": 3}, "GND": {"value": 0}, "DAC": {"dac": true}, "PULSE": {"value": 4.5}},
  "matrix_boards": [
    {"id": 6, "registers": ["Matrix0", "Matrix1"], "size": {"inputs": 8, "outputs": 4}, "layout": "out*8+in",
     "status": "assumed", "inputs": {"1": "P3V", "3": "DAC", "4": "GND"}, "outputs": {"1": "set_40"}}
  ],
  "outputs": {
    "ac_36v": {"kind": "bit", "register": "Power", "bit": 0, "on_value": 1, "off_value": 0, "status": "assumed"},
    "dc_27v": {"kind": "bit", "register": "Power", "bit": 2, "on_value": 1, "off_value": 0, "status": "assumed"}
  },
  "inputs": {
    "xp1_50":    {"kind": "adc", "register": "ADC3_val", "signed": true, "scale": 0.01, "offset": 0,
                  "mux": 8, "mux_bank": 0, "status": "assumed"},
    "hz_A":      {"kind": "manual", "prompt": "Tần số pha A đo trên oxilo", "status": "assumed"},
    "diag_loop": {"kind": "loop_probe", "duration_ms": 2000, "poll_ms": 10, "status": "assumed"},
    "ready":     {"kind": "link", "status": "assumed"}
  }
}
```

| Khóa | Quy tắc |
|---|---|
| `slave` | 1–247 |
| `session` | Ghi đầu mỗi bài; bắt buộc `"Mode": 1` |
| `safe_state` | Giá trị an toàn cho **mọi** thanh ghi mà output dùng. `MUX` phải bằng word "mọi bank ở `idle_channel`" |
| `mux_register`, `mux_settle_ms` | Thanh ghi chọn kênh đo; thời gian ổn định analog sau khi đổi kênh |
| `mux_layout` | Tùy chọn, mặc định 1 bank 16 bit, idle 0. Word MUX = OR các bank, mỗi bank `bank_bits` bit chứa **số kênh**; bank không đo giữ `idle_channel` (kênh hở hết). `channels` = số kênh hợp lệ mỗi bank (RLMUX: 32); mọi ghi MUX có kênh ≥ `channels` bị chặn vì firmware bo MUX không kiểm giới hạn |
| `di_update_ms` | Tùy chọn, mặc định 0. Thời gian để lệnh đã ACK lên tới DI: vòng lặp MCU chuyển lệnh xuống bo con, đọc ADC, chép DI. Số đo chỉ được đọc khi đã qua `di_update_ms + mux_settle_ms` kể từ ACK ghi cuối. Đặt ≥ 2 × chu kỳ vòng lặp MCU đo được (bài tự kiểm tra D02) |
| `break_ms` | Tùy chọn, mặc định = `di_update_ms`. Ngắt trước đóng sau: khi một bước vừa nhả vừa đóng rơ-le, ghi phần nhả, chờ `break_ms` kể từ ACK, rồi mới ghi phần đóng |
| `extra_write_registers` | Tùy chọn. Thanh ghi DO **đề xuất sửa firmware** (tên mới, index từ cuối bản đồ tới cuối mảng firmware: CPUv1.0 29–31, CPUv1.1 31–49). Bộ chạy bài, công cụ Test Modbus và COM ảo dùng; ghi rõ "cần sửa FW" trong `unresolved` |
| Tên thanh ghi | Theo bản đồ `cpu_map` hoặc `extra_write_registers`. Chỉ được ghi `bench_writable` của bản đồ + thanh ghi mở rộng, không DataO1/DataO2/DataO3/CDT/DataT/Null |
| `hmi_forced_bits` | Bit firmware tự bật khi `Mode ≠ 1`/reset; validator cấm mọi output dùng các bit này |
| `interlocks` | Tùy chọn. Nhóm output không được bật cùng lúc; ảnh DO vi phạm → lỗi khi nạp/khi chạy |
| `dac` | Tùy chọn. Mã = round((giá trị − offset) / scale) vào `DAC_val`. Ngoài `min/max` hoặc `count_min/count_max` → lỗi, không kẹp. Hai chân cần hai mức khác nhau cùng lúc → lỗi |
| `sources` | Nguồn có sẵn đưa vào đầu vào bo matrix: `{value}` (mức cố định, đất = 0) hoặc `{dac: true}` |
| `matrix_boards[]` | Bo matrix rơ-le: `id`, `registers` (đủ `inputs × outputs` bit), `size`, `layout` (hiện chỉ `out*8+in`), `status`, `inputs {số: nguồn}`, `outputs {số: tín hiệu}`. Mỗi đầu ra sinh một output kiểu `pin`. Bo `unsupported` (+ `reason`) làm mọi bài dùng chân của nó BLOCKED |
| Output `pin` | Sinh từ `matrix_boards`. Action nhả mọi điểm giao của chân rồi đóng **một** đầu vào có `value` bằng giá trị yêu cầu, hoặc đầu vào DAC nếu không có mức sẵn; `null` = hở mạch. Không có nguồn phù hợp → lỗi |
| Output `bit` | Đặt bit khi action đúng `on_value` (mức tiếp điểm cấp: 1, 27, 5, 0 V…); nhả bằng `off_value` (tùy chọn), `null` hoặc `safe_state`. Không hai output chung một bit |
| Input `adc` | Giá trị = (int16 nếu `signed`) × `scale` + `offset`; `mux` = **số kênh** trong bank `mux_bank` (khác `idle_channel`; `null` nếu không cần). Bộ (`mux`, `mux_bank`, thanh ghi) không trùng |
| Input `link` | = 1 khi FC03 hợp lệ |
| Input `manual` | Người vận hành nhập (`prompt`); không đọc qua FC03 |
| Input `loop_probe` | Tự kiểm tra chu kỳ vòng lặp CPU: đọc FC03 mỗi `poll_ms` trong `duration_ms` |
| `status` | `assumed` (chưa đo kiểm) / `verified` (**chỉ sau khi đo kiểm thật**) / `unsupported` + `reason` (bài dùng tín hiệu này → BLOCKED). Áp cho output, input, từng bo matrix và khối `dac`. Trên mạch thật, bài chỉ chạy khi mọi mục nó dùng là `verified` |
| `note`, `*_note` | Ghi chú tự do |

Mọi tín hiệu dùng trong `actions`, `checks` và `sequences` phải có mục trong
`stm32_io`. Khi nạp, validator chạy thử chuỗi safe_state → chuẩn bị → từng bước
của mọi bài để bắt bit trùng, bit HMI, xung đột DAC, vi phạm liên động hoặc giá trị
không có nguồn.

## mock.json

| Khóa | Adapter | Nội dung |
|---|---|---|
| `stm32_cases` | `stm32` | `[{when: {tín hiệu yêu cầu: giá trị}, after_ms?, measure: {tín hiệu đo: giá trị}}]` |
| `stm32_timing` | `stm32` | Tùy chọn. `{loop_ms, note}`: chu kỳ vòng lặp chính MCU mà COM ảo mô phỏng (0 = áp dụng tức thì). Lấy theo số đo trên mạch thật |
| `cases` | `mock` | `{"<test_id>/<step_id>": {tín hiệu đo: giá trị}}` cho mọi bước |

Với `stm32_cases`, simulator chọn case khớp nhiều điều kiện `when` nhất (và đã đủ
`after_ms` thời gian mô phỏng kể từ khi kích thích bật) cho kênh MUX đang đọc;
không khớp thì trả 0. Mức DAC khớp trong phạm vi nửa bước DAC. Số liệu là **demo**:
không chép dải tiêu chuẩn để tạo PASS.

## Hiện trạng profile A45 / khối 1101K-10

Tài liệu nguồn: [nguon/BAI_KIEM_TRA_1101K.md](nguon/BAI_KIEM_TRA_1101K.md). Các điểm chưa đủ đặc tả
đã được người dùng chốt tạm ngày 2026-11-18 (phiếu xác nhận); giá trị tạm ghi ở `basis`
của từng check, điểm còn nghi vấn ở `notes` của bài. Không còn `issues`.

| Bài | Đã chốt (tạm) |
|---|---|
| P01 | Rơ-le 1 (36 V) → đo dòng sau 1 s → giữ đủ 2 phút → ngắt rơ-le 1, đóng rơ-le 2 (22 V). Áp 22 ± 2 V; tần số nhập tay; `stop_on_fail` |
| P02 | Mỗi cực DC một rơ-le; `stop_on_fail` |
| P10–P12 | Xung 10 kHz từ bo tạo xung có sẵn qua rơ-le |
| P12, P17 | Dung sai nhánh còn thiếu = ±0,2 V |
| P16, P18, P23 | Giữ đúng tài liệu (26XP1; −0,3 V; cấp 5 V vào 13XP1), còn nghi vấn |
| P20 | Kiểm trị tuyệt đối U(50XP1) = 8,5 ± 0,2 V (`absolute`) |
| P21 | Hai bước ±3 V tại 54XP1 → 49XP1 = ±8,5 V |
| P22–P24 | Dấu tạm: 50XP1 dương, 49XP1 âm |

Chạy tự động mô phỏng: **24/24 PASS** (bỏ trống tần số thì ghi "có giá trị mặc định
chưa đo"). PASS mô phỏng không có nghĩa bài sẵn sàng chạy phần cứng: ánh xạ
`stm32_io` (CPUv1.1 slave 11, 4 bo matrix, bảng phân bổ để đi dây ở
[04 Firmware](04_FIRMWARE_VA_PHAN_CUNG.md) mục 10) và trình tự `sequences` vẫn là giả định; bo matrix
ID 7–9 cần sửa firmware CPU và bo con. Tự kiểm tra: D01 truyền thông (ghi có ACK +
FC03), D02 chu kỳ vòng lặp CPU, D03 chưa định nghĩa (BLOCKED). Trên COM thật: tự kiểm
tra chạy được; bài đo bị chặn cho tới khi các mục nó dùng được đổi `verified`.

Cấu hình thứ hai `alternative_profile` (`tests/test_bench.py`, trạm nhiệt demo,
adapter `mock`) kiểm tra rằng UI và bộ chạy bài không phụ thuộc tên A45.
