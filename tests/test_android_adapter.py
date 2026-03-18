import subprocess

import pytest

from agent_runner.android_adapter import AndroidAdapter


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
