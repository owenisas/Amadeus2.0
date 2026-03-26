import subprocess
from pathlib import Path

import pytest

from agent_runner.android_adapter import AndroidAdapter
from agent_runner.models import BoundingBox, DeviceInfo, ScreenState, VisionDecision


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def make_adapter() -> AndroidAdapter:
    return AndroidAdapter(
        appium_url="http://127.0.0.1:4723",
        device_serial="emulator-5554",
        adb_path="/tmp/adb",
    )


def test_wait_for_stable_ui_returns_after_repeated_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()
    adapter._driver = object()
    clock = FakeClock()
    signatures = iter(["screen-a", "screen-b", "screen-b", "screen-b", "screen-b"])

    monkeypatch.setattr("agent_runner.android_adapter.time.monotonic", clock.monotonic)
    monkeypatch.setattr("agent_runner.android_adapter.time.sleep", clock.sleep)
    monkeypatch.setattr(adapter, "_ui_stability_signature", lambda: next(signatures))

    adapter.wait_for_stable_ui(2.0)

    assert 0.75 <= clock.now < 2.0


def test_adb_command_uses_default_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()
    observed: dict[str, float] = {}

    def fake_run(command, *, check, capture_output, text, timeout):
        observed["timeout"] = timeout
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr("agent_runner.android_adapter.subprocess.run", fake_run)

    result = adapter.adb_command(["shell", "getprop"])

    assert result.returncode == 0
    assert observed["timeout"] == AndroidAdapter.ADB_TIMEOUT_SECONDS


def test_adb_timeout_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()

    def fake_run(command, *, check, capture_output, text, timeout):
        raise subprocess.TimeoutExpired(command, timeout=timeout)

    monkeypatch.setattr("agent_runner.android_adapter.subprocess.run", fake_run)

    with pytest.raises(RuntimeError, match="adb command timed out"):
        adapter.adb_command(["shell", "getprop"])


def test_is_package_installed_returns_false_for_missing_package(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()

    def fake_adb(args, *, check, timeout=None):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(adapter, "_adb", fake_adb)

    assert adapter.is_package_installed("com.example.missing") is False


def test_is_package_installed_retries_and_raises_for_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()
    calls = {"count": 0}

    def fake_adb(args, *, check, timeout=None):
        calls["count"] += 1
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="error: device offline")

    monkeypatch.setattr(adapter, "_adb", fake_adb)
    monkeypatch.setattr("agent_runner.android_adapter.time.sleep", lambda seconds: None)

    with pytest.raises(RuntimeError, match="adb failed while checking whether com.facebook.katana is installed"):
        adapter.is_package_installed("com.facebook.katana")

    assert calls["count"] == 3


def test_launch_app_wakes_device_if_asleep(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()
    adb_calls: list[list[str]] = []
    launched: list[tuple[str, str | None]] = []

    class FakeDriver:
        def start_activity(self, package_name, activity):
            launched.append((package_name, activity))

    def fake_adb(args, *, check, timeout=None):
        adb_calls.append(args)
        if args == ["shell", "dumpsys", "power"]:
            return subprocess.CompletedProcess(args, 0, stdout="mWakefulness=Asleep", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    adapter._driver = FakeDriver()
    monkeypatch.setattr(adapter, "connect", lambda: None)
    monkeypatch.setattr(adapter, "wait_for_stable_ui", lambda seconds: None)
    monkeypatch.setattr(adapter, "_adb", fake_adb)
    monkeypatch.setattr("agent_runner.android_adapter.time.sleep", lambda seconds: None)

    adapter.launch_app("com.example.app", ".MainActivity")

    assert ["shell", "input", "keyevent", "224"] in adb_calls
    assert ["shell", "wm", "dismiss-keyguard"] in adb_calls
    assert ["shell", "input", "keyevent", "82"] in adb_calls
    assert launched == [("com.example.app", ".MainActivity")]


def test_launch_app_skips_wake_when_device_already_awake(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()
    adb_calls: list[list[str]] = []
    launched: list[tuple[str, str | None]] = []

    class FakeDriver:
        def start_activity(self, package_name, activity):
            launched.append((package_name, activity))

    def fake_adb(args, *, check, timeout=None):
        adb_calls.append(args)
        if args == ["shell", "dumpsys", "power"]:
            return subprocess.CompletedProcess(args, 0, stdout="mWakefulness=Awake", stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    adapter._driver = FakeDriver()
    monkeypatch.setattr(adapter, "connect", lambda: None)
    monkeypatch.setattr(adapter, "wait_for_stable_ui", lambda seconds: None)
    monkeypatch.setattr(adapter, "_adb", fake_adb)

    adapter.launch_app("com.example.app", ".MainActivity")

    assert ["shell", "input", "keyevent", "224"] not in adb_calls
    assert launched == [("com.example.app", ".MainActivity")]


def test_resolve_tap_box_snaps_to_nearby_clickable_component() -> None:
    adapter = make_adapter()
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.fivesurveys.mobile",
        activity_name=".MainActivity",
    )
    state = ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=["Qualification", "Which languages do you speak?", "English", "Spanish"],
        clickable_text=["English", "Spanish"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=[
            {
                "component_type": "button",
                "label": "Next",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.4296, "y": 0.9225, "width": 0.1407, "height": 0.0629},
            }
        ],
    )

    requested = BoundingBox(x=0.5, y=0.96, width=0.1, height=0.1)

    resolved = adapter._resolve_tap_box(requested, state)

    assert resolved.to_dict() == {"x": 0.4296, "y": 0.9225, "width": 0.1407, "height": 0.0629}


def test_resolve_tap_box_prefers_visible_button_over_underlying_cards() -> None:
    adapter = make_adapter()
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.fivesurveys.mobile",
        activity_name=".MainActivity",
    )
    state = ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=["Qualification", "Which languages do you speak?", "English", "Spanish"],
        clickable_text=["Take Survey", "Spanish", "Next"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=[
            {
                "component_type": "touch_target",
                "label": "5 | (110)",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.0713, "y": 0.95, "width": 0.4176, "height": 0.05},
            },
            {
                "component_type": "touch_target",
                "label": "4.5 | (39)",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.5111, "y": 0.95, "width": 0.4176, "height": 0.05},
            },
            {
                "component_type": "touch_target",
                "label": "Qualification overlay",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.0, "y": 0.0333, "width": 1.0, "height": 0.9667},
            },
            {
                "component_type": "button",
                "label": "Next",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.4296, "y": 0.9225, "width": 0.1407, "height": 0.0629},
            },
        ],
    )

    requested = BoundingBox(x=0.5, y=0.96, width=0.4, height=0.06)

    resolved = adapter._resolve_tap_box(requested, state)

    assert resolved.to_dict() == {"x": 0.4296, "y": 0.9225, "width": 0.1407, "height": 0.0629}


def test_perform_tap_uses_resolved_component_box(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()
    captured: dict[str, int] = {}

    class FakeDriver:
        def execute_script(self, script, payload):
            captured["x"] = payload["x"]
            captured["y"] = payload["y"]

    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.fivesurveys.mobile",
        activity_name=".MainActivity",
    )
    state = ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=["Qualification"],
        clickable_text=["Next"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=[
            {
                "component_type": "button",
                "label": "Next",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.4296, "y": 0.9225, "width": 0.1407, "height": 0.0629},
            }
        ],
    )
    decision = VisionDecision(
        screen_classification="question",
        goal_progress="acting",
        next_action="tap",
        target_box=BoundingBox(x=0.5, y=0.96, width=0.1, height=0.1),
        confidence=0.8,
        reason="Tap next.",
        risk_level="low",
    )
    adapter._driver = FakeDriver()
    monkeypatch.setattr(adapter, "connect", lambda: None)
    monkeypatch.setattr(adapter, "wait_for_stable_ui", lambda seconds: None)

    adapter.perform(decision, state)

    assert captured == {"x": 539, "y": 2289}


def test_perform_swipe_uses_bounded_region_from_target_box(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()
    captured: dict[str, object] = {}

    class FakeDriver:
        def execute_script(self, script, payload):
            captured["script"] = script
            captured["payload"] = payload

    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.facebook.katana",
        activity_name=".LoginActivity",
    )
    state = ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=["Marketplace"],
        clickable_text=["For you"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=[],
    )
    decision = VisionDecision(
        screen_classification="facebook_marketplace_feed",
        goal_progress="advancing_feed",
        next_action="swipe",
        target_box=BoundingBox(x=0.08, y=0.28, width=0.84, height=0.34),
        confidence=0.8,
        reason="Scroll slightly.",
        risk_level="low",
    )
    adapter._driver = FakeDriver()
    monkeypatch.setattr(adapter, "connect", lambda: None)
    monkeypatch.setattr(adapter, "wait_for_stable_ui", lambda seconds: None)

    adapter.perform(decision, state)

    assert captured["script"] == "mobile: swipeGesture"
    assert captured["payload"] == {
        "left": 86,
        "top": 672,
        "width": 907,
        "height": 816,
        "direction": "up",
        "percent": 0.30600000000000005,
    }


def test_perform_type_uses_target_box_and_active_element_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()
    calls: list[tuple[str, object]] = []

    class FakeActiveElement:
        def clear(self):
            calls.append(("clear", None))

        def send_keys(self, text):
            calls.append(("send_keys", text))

    class FakeSwitchTo:
        @property
        def active_element(self):
            return FakeActiveElement()

    class FakeDriver:
        switch_to = FakeSwitchTo()

        def execute_script(self, script, payload):
            calls.append(("tap", payload))

    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.facebook.katana",
        activity_name=".activity.react.ImmersiveReactActivity",
    )
    state = ScreenState(
        screenshot_path=Path("/tmp/fake.png"),
        hierarchy_path=Path("/tmp/fake.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=["Hi, is this available?", "Send"],
        clickable_text=["Hi, is this available?", "Send"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=[
            {
                "component_type": "text_input",
                "label": "Hi, is this available?",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.09, "y": 0.72, "width": 0.64, "height": 0.03},
            }
        ],
    )
    decision = VisionDecision(
        screen_classification="facebook_message_composer",
        goal_progress="drafting_reply",
        next_action="type",
        target_box=BoundingBox(x=0.09, y=0.72, width=0.64, height=0.03),
        confidence=0.9,
        reason="Replace the default message.",
        risk_level="low",
        input_text="Hi, I'm interested in the monitor. Is it still available?",
        submit_after_input=False,
    )
    adapter._driver = FakeDriver()
    monkeypatch.setattr(adapter, "connect", lambda: None)
    monkeypatch.setattr(adapter, "wait_for_stable_ui", lambda seconds: None)
    monkeypatch.setattr("agent_runner.android_adapter.time.sleep", lambda seconds: None)
    monkeypatch.setattr(adapter, "_adb", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("adb fallback should not be used")))

    adapter.perform(decision, state)

    assert calls[0][0] == "tap"
    assert ("clear", None) in calls
    assert ("send_keys", "Hi, I'm interested in the monitor. Is it still available?") in calls


def test_retry_tap_alternatives_tries_multiple_methods_until_state_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = make_adapter()
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.fivesurveys.mobile",
        activity_name=".MainActivity",
    )
    before_state = ScreenState(
        screenshot_path=Path("/tmp/before.png"),
        hierarchy_path=Path("/tmp/before.xml"),
        screenshot_sha256="abc",
        xml_source="<hierarchy />",
        visible_text=["Qualification", "Enter your birthday"],
        clickable_text=["Next"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=[
            {
                "component_type": "button",
                "label": "Next",
                "enabled": True,
                "clickable": True,
                "target_box": {"x": 0.4296, "y": 0.9225, "width": 0.1407, "height": 0.0629},
            }
        ],
    )
    after_state = ScreenState(
        screenshot_path=Path("/tmp/after.png"),
        hierarchy_path=Path("/tmp/after.xml"),
        screenshot_sha256="def",
        xml_source="<hierarchy><node text='Question 2' /></hierarchy>",
        visible_text=["Question 2"],
        clickable_text=["Continue"],
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=[],
    )
    calls: list[str] = []
    states = iter([before_state, after_state])

    monkeypatch.setattr(adapter, "_resolve_tap_box", lambda requested, state: BoundingBox(0.4296, 0.9225, 0.1407, 0.0629))
    monkeypatch.setattr(adapter, "_execute_tap_method", lambda method_name, tap_box, state: calls.append(method_name))
    monkeypatch.setattr(adapter, "wait_for_stable_ui", lambda seconds: None)
    monkeypatch.setattr(adapter, "capture_state", lambda run_dir: next(states))

    next_state, attempts = adapter.retry_tap_alternatives(
        BoundingBox(0.5, 0.94, 0.15, 0.15),
        before_state,
        Path("/tmp"),
    )

    assert calls == ["appium_raw", "adb_resolved"]
    assert attempts[-1]["changed"] is True
    assert next_state.visible_text == ["Question 2"]


def test_detects_appium_unavailable_error() -> None:
    assert AndroidAdapter._is_appium_unavailable_error(
        "HTTPConnectionPool(host='127.0.0.1', port=4723): Failed to establish a new connection: [Errno 61] Connection refused"
    )
