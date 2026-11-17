"""Load declarative profiles. No expressions or executable configuration."""
import json
import math
from pathlib import Path

from src.common.testing import DEFAULT_PROFILE, Profile
from src.common.config import MAX_MONITOR_CHANNELS


class ProfileError(ValueError):
    pass


def _require(condition, where, message):
    if not condition:
        raise ProfileError(f"{where}: {message}")


def _read(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ProfileError(f"{path}: {error}") from error
    _require(isinstance(value, dict) and value.get("schema_version") == 1,
             path, "schema_version phải bằng 1")
    return value


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def load_profile(path=DEFAULT_PROFILE):
    path = Path(path).resolve()
    system = _read(path)
    documents = []
    for key in ("target_file", "hardware_file", "fixtures_file"):
        _require(isinstance(system.get(key), str), path, f"Thiếu {key}")
        child = (path.parent / system[key]).resolve()
        _require(child.is_relative_to(path.parent), key, "File phải nằm trong thư mục cấu hình")
        documents.append(_read(child))
    profile = Profile(system, *documents, path)
    validate_profile(profile)
    return profile


def validate_profile(profile):
    try:
        _validate_profile(profile)
    except (KeyError, TypeError, AttributeError) as error:
        raise ProfileError(f"Cấu trúc cấu hình không hợp lệ: {error}") from error


def _validate_profile(profile):
    system, target, hardware = profile.system, profile.target, profile.hardware
    # Presentation metadata for a separate acquisition source, not bench signals.
    channels = system.get('monitor_channels', [])
    _require(isinstance(channels, list) and len(channels) <= MAX_MONITOR_CHANNELS,
             'monitor_channels', f'Chỉ chọn tối đa {MAX_MONITOR_CHANNELS} kênh quan trọng')
    channel_ids = set()
    for channel in channels:
        _require(isinstance(channel, dict), 'monitor_channels', 'Kênh phải là object')
        _require(all(isinstance(channel.get(k), str) and channel[k].strip()
                     for k in ('id', 'label', 'unit')), 'monitor_channels', 'Thiếu id/label/unit')
        _require(channel.get('kind') in ('analog', 'pwm'), 'monitor_channels', 'Chỉ hỗ trợ analog/pwm')
        _require(channel['id'] not in channel_ids, 'monitor_channels', 'ID kênh trùng')
        channel_ids.add(channel['id'])
    for doc, label in ((system, "system"), (target, "target")):
        _require(isinstance(doc.get("id"), str) and isinstance(doc.get("name"), str), label, "Thiếu id/name")
    signals = {}
    _require(isinstance(system.get("signals"), list) and system["signals"], "signals", "Danh sách trống")
    for signal in system["signals"]:
        sid = signal.get("id")
        _require(isinstance(sid, str) and sid and sid not in signals, "signals", f"ID sai/trùng: {sid}")
        _require(signal.get("kind") in ("number", "boolean", "state"), sid, "kind không hỗ trợ")
        _require(all(isinstance(signal.get(k), str) for k in ("label", "group", "unit")), sid, "Thiếu nhãn/nhóm/đơn vị")
        _require(_number(signal.get("stale_ms")) and signal["stale_ms"] > 0, sid, "stale_ms phải > 0")
        _require(isinstance(signal.get("decimals"), int) and 0 <= signal["decimals"] <= 6, sid, "decimals phải từ 0 đến 6")
        _require(signal.get("source") in ("measured", "confirmed", "derived"), sid, "source không hợp lệ")
        _require(isinstance(signal.get("states"), dict), sid, "states phải là object")
        signals[sid] = signal
    capabilities = hardware.get("capabilities", [])
    for role, sid in system.get("status_signals", {}).items():
        _require(role in ("ready", "output", "fault") and sid in signals, "status_signals", f"Vai trò/tín hiệu không hợp lệ: {role}/{sid}")
    _require(isinstance(capabilities, list), "hardware", "capabilities phải là danh sách")
    adapter = hardware.get("adapter")
    _require(adapter in ("mock", "stm32"), "hardware.adapter",
             "Chỉ hỗ trợ mock (A45 v1 cũ) hoặc stm32 (hai mảng CPUv1.0)")
    _require(hardware.get("production_ready") is False, "hardware", "Đường chạy thật chưa được phê duyệt")
    from src.protocol import WireCodec
    from src.common.wire import COMMIT_REGISTER, REQUEST_MAILBOX, RESPONSE_MAILBOX
    _require(hardware.get('registers') == dict(commit=COMMIT_REGISTER,
             request_mailbox=REQUEST_MAILBOX, response_mailbox=RESPONSE_MAILBOX),
             'hardware.registers', 'Địa chỉ mailbox phải đúng hợp đồng A45 v1')
    try:
        WireCodec(profile)  # Legacy A45 v1 diagnostics still use this codec.
    except ValueError as error:
        raise ProfileError(f'hardware.wire_signals: {error}') from error
    sequences = target.get("sequences", {})
    if adapter == "stm32":
        _validate_stm32_io(hardware.get("stm32_io"), signals)
        _require(isinstance(sequences, dict) and sequences, "target.sequences", "Thiếu trình tự chuẩn bị/kết thúc")
        for name, sequence in sequences.items():
            where = f"sequences.{name}"
            _require(isinstance(sequence, dict) and isinstance(sequence.get("basis"), str), where, "Thiếu basis")
            _require(isinstance(sequence.get("actions"), list), where, "actions phải là danh sách")
            _check_actions(sequence["actions"], signals, where)
    for tests, label in ((target.get("tests"), "target.tests"), (system.get("diagnostics"), "system.diagnostics")):
        _require(isinstance(tests, list) and tests, label, "Danh sách bài trống")
        ids = [test.get("id") for test in tests]
        _require(all(isinstance(i, str) and i for i in ids) and len(set(ids)) == len(ids), label, "ID bài sai/trùng")
        graph = {}
        for test in tests:
            tid = test["id"]
            for key in ("name", "group", "source"):
                _require(isinstance(test.get(key), str), tid, f"Thiếu {key}")
            _require(isinstance(test.get("issues"), list), tid, "Thiếu danh sách issues")
            deps = test.get("dependencies")
            _require(isinstance(deps, list) and all(d in ids for d in deps), tid, "Tham chiếu bài phụ thuộc sai")
            graph[tid] = deps
            if adapter == "mock":
                _require(test.get("preparation") == "mock_baseline" and test.get("cleanup") == "mock_safe", tid, "Thiếu chuẩn bị/kết thúc mô phỏng")
            else:
                _require(test.get("preparation") in sequences and test.get("cleanup") in sequences, tid,
                         "preparation/cleanup phải là ID trong target.sequences")
            _require(test.get("independence") in ("mock_only", "verified", "unknown"), tid, "Thiếu chính sách phụ thuộc")
            _require(isinstance(test.get("steps"), list) and test["steps"], tid, "Bài không có bước")
            step_ids = set()
            for step in test["steps"]:
                where = f"{tid}/{step.get('id')}"
                _require(isinstance(step.get("id"), str) and step["id"] not in step_ids, where, "ID bước sai/trùng")
                step_ids.add(step["id"])
                _require(step.get("capability") in capabilities, where, "Phần cứng thiếu khả năng yêu cầu")
                _require(_number(step.get("wait_ms")) and step["wait_ms"] >= 0, where, "wait_ms không hợp lệ")
                _require(isinstance(step.get("issues"), list), where, "Thiếu issues")
                _check_actions(step.get("actions", []), signals, where)
                _require(bool(step.get("checks")), where, "Bước không có phép đo")
                for check in step["checks"]:
                    sid = check.get("signal")
                    _require(sid in signals, where, f"Tín hiệu đo không tồn tại: {sid}")
                    _require(check.get("unit") == signals[sid]["unit"], where, "Đơn vị không khớp tín hiệu")
                    nominal, tolerance = check.get("nominal"), check.get("tolerance")
                    _require(nominal is None or _number(nominal), where, "nominal sai")
                    _require(tolerance is None or (_number(tolerance) and tolerance >= 0), where, "tolerance phải >= 0 hoặc null")
        visited, active = set(), set()

        def visit(tid):
            _require(tid not in active, label, f"Phụ thuộc vòng tại {tid}")
            if tid in visited:
                return
            active.add(tid)
            for dep in graph[tid]:
                visit(dep)
            active.remove(tid)
            visited.add(tid)

        for tid in ids:
            visit(tid)
    if adapter == "stm32":
        _validate_stm32_plan(profile)
        return
    _require(isinstance(profile.fixtures.get("cases"), dict), "fixtures", "Thiếu cases")
    for test in profile.tests + profile.diagnostics:
        for step in test["steps"]:
            key = f"{test['id']}/{step['id']}"
            case = profile.fixtures["cases"].get(key)
            _require(isinstance(case, dict), key, "Thiếu fixture mô phỏng")
            for check in step["checks"]:
                _require(_number(case.get(check["signal"])), key, "Fixture thiếu/sai giá trị đo")


def _check_actions(actions, signals, where):
    for action in actions:
        sid = action.get("signal")
        _require(sid in signals, where, f"Tín hiệu yêu cầu không tồn tại: {sid}")
        _require(_number(action.get("value")), where, "Giá trị yêu cầu không hợp lệ")


def _int(value, low, high):
    return type(value) is int and low <= value <= high


def _validate_stm32_io(io, signals):
    """Structure of the CPUv1.0 runner map; bench semantics stay 'assumed'."""
    from src.common.stm32 import BENCH_WRITABLE, IO_STATUSES, ReadRegister, WriteRegister
    where = "hardware.stm32_io"
    _require(isinstance(io, dict), where, "Thiếu ánh xạ thanh ghi cho adapter stm32")
    writable = {r.name for r in BENCH_WRITABLE}
    _require(_int(io.get("slave"), 1, 247), where, "slave phải từ 1 đến 247")
    _require(io.get("mux_register") in writable, where, "mux_register không hợp lệ")
    _require(_number(io.get("mux_settle_ms")) and io["mux_settle_ms"] >= 0, where, "mux_settle_ms không hợp lệ")
    for key in ("session", "safe_state"):
        block = io.get(key)
        _require(isinstance(block, dict) and block, f"{where}.{key}", "Thiếu thanh ghi")
        for name, value in block.items():
            _require(name in writable, f"{where}.{key}", f"Bộ chạy bài không được ghi {name}")
            _require(_int(value, 0, 0xFFFF), f"{where}.{key}", f"{name} phải là word 0–65535")
    _require(io["session"].get("Mode") == 1, f"{where}.session", "Mode phải bằng 1 (AutoComputer)")
    _require(io["mux_register"] in io["safe_state"], f"{where}.safe_state", "Thiếu thanh ghi MUX")
    owners = {}

    def claim(register, bit, sid):
        _require(register in io["safe_state"], sid, f"{register} phải có trong safe_state")
        _require(_int(bit, 0, 15), sid, "bit phải từ 0 đến 15")
        _require((register, bit) not in owners, sid, f"Trùng {register}.bit{bit} với {owners.get((register, bit))}")
        owners[(register, bit)] = sid

    for sid, entry in io.get("outputs", {}).items():
        _require(sid in signals and isinstance(entry, dict), sid, "Output không khớp tín hiệu")
        _require(entry.get("status") in IO_STATUSES, sid, "status không hợp lệ")
        if entry["status"] == "unsupported":
            _require(isinstance(entry.get("reason"), str) and entry["reason"], sid, "Thiếu lý do unsupported")
            continue
        if entry.get("kind") == "bit":
            _require(entry.get("register") in writable, sid, "register không hợp lệ")
            claim(entry["register"], entry.get("bit"), sid)
            _require(_number(entry.get("on_value")), sid, "Thiếu on_value")
        else:
            _require(entry.get("kind") == "analog" and entry.get("register") == WriteRegister.DAC_val.name, sid,
                     "Output analog phải dùng DAC_val")
            _require(isinstance(entry.get("route"), list) and entry["route"], sid, "Thiếu route")
            for route in entry["route"]:
                _require(isinstance(route, dict) and route.get("register") in writable, sid, "route không hợp lệ")
                claim(route["register"], route.get("bit"), sid)
            _require(all(_number(entry.get(k)) for k in ("scale", "offset", "min", "max")) and entry["scale"] != 0
                     and entry["min"] < entry["max"], sid, "scale/offset/min/max không hợp lệ")
            _require(_int(entry.get("count_min"), -32768, 32767) and _int(entry.get("count_max"), -32768, 32767)
                     and entry["count_min"] < entry["count_max"], sid, "count_min/count_max không hợp lệ")
    read_slots = set()
    for sid, entry in io.get("inputs", {}).items():
        _require(sid in signals and isinstance(entry, dict), sid, "Input không khớp tín hiệu")
        _require(entry.get("status") in IO_STATUSES, sid, "status không hợp lệ")
        if entry["status"] == "unsupported":
            _require(isinstance(entry.get("reason"), str) and entry["reason"], sid, "Thiếu lý do unsupported")
            continue
        if entry.get("kind") == "link":
            continue
        _require(entry.get("kind") == "adc" and entry.get("register") in ReadRegister.__members__
                 and entry["register"] != "Null", sid, "Input phải là adc với register DI hợp lệ")
        _require(isinstance(entry.get("signed"), bool), sid, "Thiếu signed")
        _require(_number(entry.get("scale")) and entry["scale"] != 0 and _number(entry.get("offset", 0)), sid,
                 "scale/offset không hợp lệ")
        mux = entry.get("mux")
        _require(mux is None or _int(mux, 1, 0xFFFF), sid, "mux phải là mã 1–65535 hoặc null")
        _require((mux, entry["register"]) not in read_slots, sid, "Trùng kênh MUX/ADC")
        read_slots.add((mux, entry["register"]))


def _validate_stm32_plan(profile):
    """Every stimulus/measurement is mapped and every step's image encodes."""
    from src.protocol import Stm32IoMap, UnsupportedSignal
    io = profile.hardware["stm32_io"]
    sequences = profile.target["sequences"]
    io_map = Stm32IoMap(io)
    for name, sequence in sequences.items():
        for action in sequence["actions"]:
            _require(action["signal"] in io["outputs"], f"sequences.{name}", f"Chưa ánh xạ {action['signal']}")
    for test in profile.tests + profile.diagnostics:
        image = io_map.safe_image()
        steps = [("preparation", sequences[test["preparation"]]["actions"])]
        steps += [(step["id"], step["actions"]) for step in test["steps"]]
        for step in test["steps"]:
            for check in step["checks"]:
                _require(check["signal"] in io["inputs"], f"{test['id']}/{step['id']}",
                         f"Chưa ánh xạ tín hiệu đo {check['signal']}")
        for label, actions in steps:
            for action in actions:
                _require(action["signal"] in io["outputs"], f"{test['id']}/{label}",
                         f"Chưa ánh xạ tín hiệu yêu cầu {action['signal']}")
            try:
                image = io_map.apply(image, actions)
            except UnsupportedSignal:
                break  # Runner marks the test BLOCKED before sending anything.
            except ValueError as error:
                raise ProfileError(f"{test['id']}/{label}: {error}") from error
        try:
            io_map.apply(io_map.safe_image(), sequences[test["cleanup"]]["actions"])
        except ValueError as error:
            raise ProfileError(f"{test['id']}/cleanup: {error}") from error
    cases = profile.fixtures.get("stm32_cases", [])
    _require(isinstance(cases, list), "fixtures.stm32_cases", "Phải là danh sách")
    for index, case in enumerate(cases):
        where = f"fixtures.stm32_cases[{index}]"
        _require(isinstance(case, dict) and isinstance(case.get("when"), dict)
                 and isinstance(case.get("measure"), dict) and case["measure"], where, "Thiếu when/measure")
        _require(all(s in io["outputs"] and _number(v) for s, v in case["when"].items()), where, "when sai")
        _require(all(s in io["inputs"] and _number(v) for s, v in case["measure"].items()), where, "measure sai")
        _require(_number(case.get("after_ms", 0)) and case.get("after_ms", 0) >= 0, where, "after_ms không hợp lệ")


def specification_issues(test):
    return test["issues"] + [issue for step in test["steps"] for issue in step["issues"]]


def stm32_unsupported(profile, test):
    """Reasons the CPUv1.0 map cannot run this test (empty for mock adapter)."""
    if profile.hardware.get("adapter") != "stm32":
        return []
    from src.protocol import Stm32IoMap
    sequences = profile.target["sequences"]
    actions = sequences[test["preparation"]]["actions"] + sequences[test["cleanup"]]["actions"]
    actions += [a for step in test["steps"] for a in step["actions"]]
    signals = [c["signal"] for step in test["steps"] for c in step["checks"]]
    return Stm32IoMap(profile.hardware["stm32_io"]).unsupported(actions, signals)
