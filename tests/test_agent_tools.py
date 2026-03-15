from pathlib import Path

import pytest

from agent_runner.agent_tools import AgentToolExecutor
from agent_runner.config import APP_REGISTRY
from agent_runner.models import DeviceInfo, ScreenState
from agent_runner.skill_manager import SkillManager


class FakeAdapter:
    def __init__(self) -> None:
        self.device_serial = "emulator-5554"
        self.launched: list[tuple[str, str | None]] = []
        self.commands: list[list[str]] = []

    def capture_state(self, run_dir: Path) -> ScreenState:
        device = DeviceInfo(
            serial=self.device_serial,
            width=1080,
            height=2400,
            density=420,
            orientation="portrait",
            package_name="com.android.settings",
            activity_name=".Settings",
        )
        return ScreenState(
            screenshot_path=run_dir / "fake.png",
            hierarchy_path=run_dir / "fake.xml",
            screenshot_sha256="hash",
            xml_source="<hierarchy />",
            visible_text=["Settings"],
            clickable_text=["Network & internet"],
            package_name=device.package_name,
            activity_name=device.activity_name,
            device=device,
            components=[],
        )

    def launch_app(self, package_name: str, activity: str | None = None) -> None:
        self.launched.append((package_name, activity))

    def perform(self, decision, state) -> None:
        return None

    def wait_for_stable_ui(self, seconds: float) -> None:
        return None

    def adb_command(self, args: list[str], *, check: bool = False):
        self.commands.append(args)

        class Result:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return Result()


def test_tool_executor_bootstraps_and_reads_skill(tmp_path: Path) -> None:
    executor = AgentToolExecutor(
        android_adapter=FakeAdapter(),
        skill_manager=SkillManager(tmp_path / "skills"),
    )

    bootstrap = executor.execute(
        tool_name="bootstrap_skill",
        arguments={"app_name": "demoapp", "package_name": "com.example.demo"},
        run_dir=tmp_path / "runs",
        current_state=None,
        app=None,
        skill=None,
    )
    assert bootstrap.ok is True

    read_result = executor.execute(
        tool_name="read_skill",
        arguments={"app_name": "demoapp", "file_name": "SKILL.md"},
        run_dir=tmp_path / "runs",
        current_state=None,
        app=None,
        skill=None,
    )
    assert read_result.ok is True
    assert "com.example.demo" in read_result.output["content"]


def test_tool_executor_blocks_dangerous_adb(tmp_path: Path) -> None:
    executor = AgentToolExecutor(
        android_adapter=FakeAdapter(),
        skill_manager=SkillManager(tmp_path / "skills"),
    )

    with pytest.raises(ValueError, match="Blocked adb command"):
        executor.execute(
            tool_name="adb_shell",
            arguments={"command": "shell reboot"},
            run_dir=tmp_path / "runs",
            current_state=None,
            app=APP_REGISTRY["settings"],
            skill=None,
        )


def test_tool_executor_writes_skill_json(tmp_path: Path) -> None:
    executor = AgentToolExecutor(
        android_adapter=FakeAdapter(),
        skill_manager=SkillManager(tmp_path / "skills"),
    )
    executor.execute(
        tool_name="bootstrap_skill",
        arguments={"app_name": "demoapp", "package_name": "com.example.demo"},
        run_dir=tmp_path / "runs",
        current_state=None,
        app=None,
        skill=None,
    )

    result = executor.execute(
        tool_name="write_skill_file",
        arguments={
            "app_name": "demoapp",
            "file_name": "state.json",
            "json_payload": {"app": "demoapp", "last_successful_screen": "screen-1"},
        },
        run_dir=tmp_path / "runs",
        current_state=None,
        app=None,
        skill=None,
    )

    assert result.ok is True
    assert '"last_successful_screen": "screen-1"' in (
        tmp_path / "skills" / "demoapp" / "state.json"
    ).read_text(encoding="utf-8")
