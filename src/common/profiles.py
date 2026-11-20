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
             "Chỉ hỗ trợ mock (A45 v1 cũ) hoặc stm32 (hai mảng CPU STM32)")
    from src.common.stm32 import cpu_map_for
    try:
        cpu_map = cpu_map_for(hardware)
    except ValueError as error:
        raise ProfileError(f"hardware.cpu_map: {error}") from error
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
        _validate_stm32_io(hardware.get("stm32_io"), signals, cpu_map)
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
            _require(isinstance(test.get("stop_on_fail", False), bool), tid, "stop_on_fail phải là true/false")
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
                # Only a pure stimulate/hold step may have no measurement.
                _require(isinstance(step.get("checks"), list)
                         and (bool(step["checks"]) or step["capability"] == "stimulate"), where, "Bước không có phép đo")
                for check in step["checks"]:
                    sid = check.get("signal")
                    _require(sid in signals, where, f"Tín hiệu đo không tồn tại: {sid}")
                    _require(check.get("unit") == signals[sid]["unit"], where, "Đơn vị không khớp tín hiệu")
                    nominal, tolerance = check.get("nominal"), check.get("tolerance")
                    _require(nominal is None or _number(nominal), where, "nominal sai")
                    _require(tolerance is None or (_number(tolerance) and tolerance >= 0), where, "tolerance phải >= 0 hoặc null")
                    _require(isinstance(check.get("absolute", False), bool), where, "absolute phải là true/false")
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
        # null = open the contact (release the pin / switch the relay off).
        _require("value" in action and (action["value"] is None or _number(action["value"])), where,
                 "Giá trị yêu cầu không hợp lệ")


def _int(value, low, high):
    return type(value) is int and low <= value <= high


def _validate_stm32_io(io, signals, cpu_map):
    """Structure of the runner map for one CPU firmware; semantics stay 'assumed'."""
    from src.common.stm32 import IO_STATUSES
    where = "hardware.stm32_io"
    _require(isinstance(io, dict), where, "Thiếu ánh xạ thanh ghi cho adapter stm32")
    extra = io.get("extra_write_registers", {})
    _require(isinstance(extra, dict), where, "extra_write_registers phải là object")
    last = cpu_map.array_words - 1
    for name, address in extra.items():
        # Proposed CPU firmware extension: only room left in the firmware arrays.
        _require(not cpu_map.has_write(name) and _int(address, cpu_map.write_count, last), where,
                 f"Thanh ghi mở rộng {name} phải có tên mới và index {cpu_map.write_count}–{last} ({cpu_map.name})")
    _require(len(set(extra.values())) == len(extra), where, "Index thanh ghi mở rộng bị trùng")
    writable = set(cpu_map.bench_writable) | set(extra)
    _require(_int(io.get("slave"), 1, 247), where, "slave phải từ 1 đến 247")
    _require(io.get("mux_register") in writable, where, "mux_register không hợp lệ")
    for key in ("mux_settle_ms", "di_update_ms", "break_ms"):
        _require(_number(io.get(key, 0)) and io.get(key, 0) >= 0, where, f"{key} không hợp lệ")
    layout = io.get("mux_layout", {})
    banks, bank_bits = layout.get("banks", 1), layout.get("bank_bits", 16)
    _require(isinstance(layout, dict) and _int(banks, 1, 16) and _int(bank_bits, 1, 16) and banks * bank_bits <= 16,
             f"{where}.mux_layout", "banks × bank_bits phải ≤ 16 bit")
    # RLMUX firmware indexes Mux_Decoder[32] without a bounds check: a channel
    # >= channels would drive random relays, so the limit is mandatory.
    channels = layout.get("channels", 1 << bank_bits)
    _require(_int(channels, 1, 1 << bank_bits), f"{where}.mux_layout", "channels phải từ 1 tới 2^bank_bits")
    _require(_int(layout.get("idle_channel", 0), 0, channels - 1), f"{where}.mux_layout", "idle_channel ngoài dải")
    for key in ("session", "safe_state"):
        block = io.get(key)
        _require(isinstance(block, dict) and block, f"{where}.{key}", "Thiếu thanh ghi")
        for name, value in block.items():
            _require(name in writable, f"{where}.{key}", f"Bộ chạy bài không được ghi {name}")
            _require(_int(value, 0, 0xFFFF), f"{where}.{key}", f"{name} phải là word 0–65535")
    _require(io["session"].get("Mode") == 1, f"{where}.session", "Mode phải bằng 1 (AutoComputer)")
    _require(io["mux_register"] in io["safe_state"], f"{where}.safe_state", "Thiếu thanh ghi MUX")
    forced = io.get("hmi_forced_bits", {})
    _require(isinstance(forced, dict) and all(isinstance(v, list) for v in forced.values()), where,
             "hmi_forced_bits phải là {thanh ghi: [bit]}")
    owners = {}

    def claim(register, bit, sid):
        _require(register in writable, sid, f"register {register} không hợp lệ")
        _require(register in io["safe_state"], sid, f"{register} phải có trong safe_state")
        _require(_int(bit, 0, 15), sid, "bit phải từ 0 đến 15")
        # Firmware turns these on by itself after a reset / when Mode != 1.
        _require(bit not in forced.get(register, []), sid, f"{register}.bit{bit} bị HMI CPU tự bật, không được dùng")
        _require((register, bit) not in owners, sid, f"Trùng {register}.bit{bit} với {owners.get((register, bit))}")
        owners[(register, bit)] = sid

    dac = io.get("dac")
    if dac is not None:
        _require(isinstance(dac, dict) and dac.get("register") == "DAC_val", f"{where}.dac",
                 "DAC phải dùng DAC_val")
        _require(all(_number(dac.get(k)) for k in ("scale", "offset", "min", "max")) and dac["scale"] != 0
                 and dac["min"] < dac["max"], f"{where}.dac", "scale/offset/min/max không hợp lệ")
        _require(_int(dac.get("count_min"), -32768, 32767) and _int(dac.get("count_max"), -32768, 32767)
                 and dac["count_min"] < dac["count_max"], f"{where}.dac", "count_min/count_max không hợp lệ")
    sources = io.get("sources", {})
    _require(isinstance(sources, dict), where, "sources phải là object")
    for name, source in sources.items():
        _require(isinstance(source, dict) and (source.get("dac") is True or _number(source.get("value"))),
                 f"{where}.sources.{name}", "Nguồn phải có value hoặc dac: true")
        _require(source.get("dac") is not True or dac is not None, f"{where}.sources.{name}", "Thiếu khối dac")
    outputs = io.get("outputs", {})
    pins = set()
    for board in io.get("matrix_boards", []):
        bid = f"{where}.matrix_boards[{board.get('id')}]"
        _require(isinstance(board, dict) and _int(board.get("id"), 1, 247), bid, "Thiếu id bo")
        size = board.get("size", {})
        _require(_int(size.get("inputs"), 1, 16) and _int(size.get("outputs"), 1, 16), bid, "size không hợp lệ")
        _require(board.get("layout") == "out*8+in" and size["inputs"] == 8, bid, "Chỉ hỗ trợ layout out*8+in (8 đầu vào)")
        registers = board.get("registers")
        _require(isinstance(registers, list) and len(registers) * 16 >= size["inputs"] * size["outputs"], bid,
                 "Không đủ thanh ghi cho mọi điểm giao")
        _require(board.get("status") in IO_STATUSES, bid, "status không hợp lệ")
        if board["status"] == "unsupported":
            _require(isinstance(board.get("reason"), str) and board["reason"], bid, "Thiếu lý do unsupported")
        inputs, outs = board.get("inputs"), board.get("outputs")
        _require(isinstance(inputs, dict) and isinstance(outs, dict) and outs, bid, "Thiếu inputs/outputs")
        _require(all(k.isdigit() and 1 <= int(k) <= size["inputs"] and v in sources for k, v in inputs.items()), bid,
                 "Đầu vào phải là số 1–N và tên nguồn trong sources")
        _require(sum(bool(sources[v].get("dac")) for v in inputs.values()) <= 1, bid, "Một bo chỉ nối DAC vào một đầu vào")
        for number, sid in outs.items():
            _require(number.isdigit() and 1 <= int(number) <= size["outputs"], bid, "Đầu ra phải là số 1–N")
            _require(sid in signals and sid not in pins and sid not in outputs, bid,
                     f"Chân {sid} không có hoặc đã nối ở nơi khác")
            pins.add(sid)
            if board["status"] == "unsupported":
                continue
            for input_number in inputs:
                index = (int(number) - 1) * size["inputs"] + int(input_number) - 1
                claim(registers[index // 16], index % 16, sid)
    for sid, entry in outputs.items():
        _require(sid in signals and isinstance(entry, dict), sid, "Output không khớp tín hiệu")
        _require(entry.get("status") in IO_STATUSES, sid, "status không hợp lệ")
        if entry["status"] == "unsupported":
            _require(isinstance(entry.get("reason"), str) and entry["reason"], sid, "Thiếu lý do unsupported")
            continue
        _require(entry.get("kind") == "bit", sid, "Output ngoài bo matrix phải là kind bit")
        claim(entry.get("register"), entry.get("bit"), sid)
        _require(_number(entry.get("on_value")), sid, "Thiếu on_value")
        _require("off_value" not in entry or (_number(entry["off_value"]) and entry["off_value"] != entry["on_value"]),
                 sid, "off_value phải là số khác on_value")
    for group in io.get("interlocks", []):
        _require(isinstance(group, list) and len(group) >= 2 and all(s in outputs or s in pins for s in group),
                 f"{where}.interlocks", "Nhóm liên động phải gồm ≥ 2 output đã ánh xạ")
    read_slots = set()
    for sid, entry in io.get("inputs", {}).items():
        _require(sid in signals and isinstance(entry, dict), sid, "Input không khớp tín hiệu")
        _require(entry.get("status") in IO_STATUSES, sid, "status không hợp lệ")
        if entry["status"] == "unsupported":
            _require(isinstance(entry.get("reason"), str) and entry["reason"], sid, "Thiếu lý do unsupported")
            continue
        kind = entry.get("kind")
        if kind in ("link", "manual"):
            continue
        if kind == "loop_probe":
            _require(_int(entry.get("duration_ms"), 100, 60000) and _int(entry.get("poll_ms"), 1, 1000), sid,
                     "duration_ms/poll_ms không hợp lệ")
            continue
        _require(kind == "adc" and cpu_map.has_read(entry.get("register"))
                 and entry["register"] != "Null", sid, f"Input phải là adc với register DI hợp lệ ({cpu_map.name})")
        _require(isinstance(entry.get("signed"), bool), sid, "Thiếu signed")
        _require(_number(entry.get("scale")) and entry["scale"] != 0 and _number(entry.get("offset", 0)), sid,
                 "scale/offset không hợp lệ")
        mux, bank = entry.get("mux"), entry.get("mux_bank", 0)
        _require(mux is None or (_int(mux, 0, channels - 1) and mux != layout.get("idle_channel", 0)), sid,
                 "mux phải là số kênh (khác kênh an toàn) hoặc null")
        _require(_int(bank, 0, banks - 1), sid, "mux_bank ngoài dải")
        _require((mux, bank, entry["register"]) not in read_slots, sid, "Trùng kênh MUX/ADC")
        read_slots.add((mux, bank, entry["register"]))


def _validate_stm32_plan(profile):
    """Every stimulus/measurement is mapped and every step's image encodes."""
    from src.protocol import Stm32IoMap, UnsupportedSignal
    from src.common.stm32 import cpu_map_for
    io = profile.hardware["stm32_io"]
    sequences = profile.target["sequences"]
    io_map = Stm32IoMap(io, cpu_map_for(profile.hardware))
    _require(io["safe_state"][io["mux_register"]] == io_map.mux_word(), "hardware.stm32_io.safe_state",
             f"MUX an toàn phải là {io_map.mux_word()} (mọi bank ở idle_channel)")
    for name, sequence in sequences.items():
        for action in sequence["actions"]:
            _require(action["signal"] in io_map.outputs, f"sequences.{name}", f"Chưa ánh xạ {action['signal']}")
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
                _require(action["signal"] in io_map.outputs, f"{test['id']}/{label}",
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
    timing = profile.fixtures.get("stm32_timing", {})
    _require(isinstance(timing, dict) and _number(timing.get("loop_ms", 0)) and timing.get("loop_ms", 0) >= 0,
             "fixtures.stm32_timing", "loop_ms không hợp lệ")
    cases = profile.fixtures.get("stm32_cases", [])
    _require(isinstance(cases, list), "fixtures.stm32_cases", "Phải là danh sách")
    for index, case in enumerate(cases):
        where = f"fixtures.stm32_cases[{index}]"
        _require(isinstance(case, dict) and isinstance(case.get("when"), dict)
                 and isinstance(case.get("measure"), dict) and case["measure"], where, "Thiếu when/measure")
        _require(all(s in io_map.outputs and _number(v) for s, v in case["when"].items()), where, "when sai")
        _require(all(s in io["inputs"] and _number(v) for s, v in case["measure"].items()), where, "measure sai")
        _require(_number(case.get("after_ms", 0)) and case.get("after_ms", 0) >= 0, where, "after_ms không hợp lệ")


def specification_issues(test):
    return test["issues"] + [issue for step in test["steps"] for issue in step["issues"]]


def stm32_unsupported(profile, test):
    """Reasons the CPUv1.0 map cannot run this test (empty for mock adapter)."""
    if profile.hardware.get("adapter") != "stm32":
        return []
    actions, signals = _test_io(profile, test)
    return stm32_io_map(profile).unsupported(actions, signals)


def stm32_io_map(profile):
    from src.protocol import Stm32IoMap
    from src.common.stm32 import cpu_map_for
    return Stm32IoMap(profile.hardware["stm32_io"], cpu_map_for(profile.hardware))


def _test_io(profile, test):
    sequences = profile.target["sequences"]
    actions = sequences[test["preparation"]]["actions"] + sequences[test["cleanup"]]["actions"]
    actions += [a for step in test["steps"] for a in step["actions"]]
    signals = [c["signal"] for step in test["steps"] for c in step["checks"]]
    return actions, signals


def stm32_unverified(profile, test):
    """Mapping entries a test uses that were not checked on the bench yet.

    Real-hardware runs are allowed only when this is empty (AGENTS.md)."""
    if profile.hardware.get("adapter") != "stm32":
        return ["adapter mock không có đường chạy mạch thật"]
    actions, signals = _test_io(profile, test)
    return stm32_io_map(profile).verification(actions, signals)
