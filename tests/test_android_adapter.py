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


def test_detects_appium_unavailable_error() -> None:
    assert AndroidAdapter._is_appium_unavailable_error(
        "HTTPConnectionPool(host='127.0.0.1', port=4723): Failed to establish a new connection: [Errno 61] Connection refused"
    )
