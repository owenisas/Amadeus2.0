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
        self.resets: list[tuple[str, str | None]] = []
        self.commands: list[list[str]] = []
        self.performed_actions: list[str] = []

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

    def reset_app(self, package_name: str, activity: str | None = None) -> None:
        self.resets.append((package_name, activity))

    def perform(self, decision, state) -> None:
        self.performed_actions.append(decision.next_action)
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


def test_tool_executor_type_accepts_input_text_alias(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    executor = AgentToolExecutor(
        android_adapter=adapter,
        skill_manager=SkillManager(tmp_path / "skills"),
    )

    result = executor.execute(
        tool_name="type",
        arguments={"input_text": "1990", "submit_after_input": False},
        run_dir=tmp_path / "runs",
        current_state=None,
        app=APP_REGISTRY["settings"],
        skill=None,
    )

    assert result.ok is True
    assert result.output["text"] == "1990"
    assert adapter.performed_actions == ["type"]


def test_tool_executor_swipe_accepts_target_box(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    executor = AgentToolExecutor(
        android_adapter=adapter,
        skill_manager=SkillManager(tmp_path / "skills"),
    )

    result = executor.execute(
        tool_name="swipe",
        arguments={"target_box": {"x": 0.08, "y": 0.28, "width": 0.84, "height": 0.34}},
        run_dir=tmp_path / "runs",
        current_state=None,
        app=APP_REGISTRY["settings"],
        skill=None,
    )

    assert result.ok is True
    assert result.output["target_box"] == {"x": 0.08, "y": 0.28, "width": 0.84, "height": 0.34}
    assert adapter.performed_actions == ["swipe"]


def _make_state(
    run_dir: Path,
    *,
    activity_name: str,
    visible_text: list[str],
    clickable_text: list[str],
    components: list[dict] | None = None,
) -> ScreenState:
    device = DeviceInfo(
        serial="emulator-5554",
        width=1080,
        height=2400,
        density=420,
        orientation="portrait",
        package_name="com.facebook.katana",
        activity_name=activity_name,
    )
    return ScreenState(
        screenshot_path=run_dir / "fake.png",
        hierarchy_path=run_dir / "fake.xml",
        screenshot_sha256="hash",
        xml_source="<hierarchy />",
        visible_text=visible_text,
        clickable_text=clickable_text,
        package_name=device.package_name,
        activity_name=device.activity_name,
        device=device,
        components=components or [],
    )


class ScriptAdapter(FakeAdapter):
    def __init__(self, states: list[ScreenState]) -> None:
        super().__init__()
        self.states = states
        self.capture_calls = 0

    def capture_state(self, run_dir: Path) -> ScreenState:
        index = min(self.capture_calls, len(self.states) - 1)
        self.capture_calls += 1
        return self.states[index]


def test_run_script_skips_conditional_back_when_prompt_absent(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs"
    home_state = _make_state(
        run_dir,
        activity_name=".LoginActivity",
        visible_text=["Home, tab 1 of 6", "Marketplace, tab 4 of 6", "Menu, tab 6 of 6"],
        clickable_text=["Marketplace, tab 4 of 6", "Menu, tab 6 of 6"],
        components=[
            {
                "label": "Marketplace, tab 4 of 6",
                "target_box": {"x": 0.5, "y": 0.08375, "width": 0.16666666666666666, "height": 0.055},
            }
        ],
    )
    adapter = ScriptAdapter([home_state, home_state, home_state, home_state, home_state])
    skill_manager = SkillManager(tmp_path / "skills")
    executor = AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager)
    skill_manager.save_script(
        "facebook",
        "open_marketplace_from_menu",
        {
            "name": "open_marketplace_from_menu",
            "description": "Reset and open Marketplace from the home shell.",
            "steps": [
                {
                    "action": "reset_app",
                    "activity": ".activity.FbMainTabActivity",
                    "package_name": "com.facebook.katana",
                },
                {"action": "wait", "wait_seconds": 1},
                {
                    "action": "back",
                    "only_if_activity_name": "com.facebook.messaginginblue.e2ee.cloudbackup.ui.activities.onboardingnux.MibCloudBackupNuxActivity",
                    "only_if_visible_text": ["Restore now", "Restore chat history on this device"],
                },
                {"action": "wait", "wait_seconds": 1},
                {"action": "tap", "target_label": "Marketplace, tab 4 of 6"},
            ],
        },
    )

    result = executor.execute(
        tool_name="run_script",
        arguments={"app_name": "facebook", "script_name": "open_marketplace_from_menu"},
        run_dir=run_dir,
        current_state=home_state,
        app=APP_REGISTRY["facebook"],
        skill=None,
    )

    assert result.ok is True
    assert result.output["steps_executed"] == 4
    assert result.output["steps_skipped"] == 1
    assert adapter.resets == [("com.facebook.katana", ".activity.FbMainTabActivity")]
    assert adapter.performed_actions == ["tap"]


def test_run_script_executes_conditional_back_when_prompt_present(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs"
    backup_state = _make_state(
        run_dir,
        activity_name="com.facebook.messaginginblue.e2ee.cloudbackup.ui.activities.onboardingnux.MibCloudBackupNuxActivity",
        visible_text=["Restore chat history on this device", "Restore now", "More options"],
        clickable_text=["Restore now", "More options"],
    )
    home_state = _make_state(
        run_dir,
        activity_name=".LoginActivity",
        visible_text=["Home, tab 1 of 6", "Marketplace, tab 4 of 6", "Menu, tab 6 of 6"],
        clickable_text=["Marketplace, tab 4 of 6", "Menu, tab 6 of 6"],
        components=[
            {
                "label": "Marketplace, tab 4 of 6",
                "target_box": {"x": 0.5, "y": 0.08375, "width": 0.16666666666666666, "height": 0.055},
            }
        ],
    )
    adapter = ScriptAdapter([backup_state, backup_state, home_state, home_state, home_state, home_state])
    skill_manager = SkillManager(tmp_path / "skills")
    executor = AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager)
    skill_manager.save_script(
        "facebook",
        "open_marketplace_from_menu",
        {
            "name": "open_marketplace_from_menu",
            "description": "Reset and open Marketplace from the home shell.",
            "steps": [
                {
                    "action": "reset_app",
                    "activity": ".activity.FbMainTabActivity",
                    "package_name": "com.facebook.katana",
                },
                {"action": "wait", "wait_seconds": 1},
                {
                    "action": "back",
                    "only_if_activity_name": "com.facebook.messaginginblue.e2ee.cloudbackup.ui.activities.onboardingnux.MibCloudBackupNuxActivity",
                    "only_if_visible_text": ["Restore now", "Restore chat history on this device"],
                },
                {"action": "wait", "wait_seconds": 1},
                {"action": "tap", "target_label": "Marketplace, tab 4 of 6"},
            ],
        },
    )

    result = executor.execute(
        tool_name="run_script",
        arguments={"app_name": "facebook", "script_name": "open_marketplace_from_menu"},
        run_dir=run_dir,
        current_state=backup_state,
        app=APP_REGISTRY["facebook"],
        skill=None,
    )

    assert result.ok is True
    assert result.output["steps_executed"] == 5
    assert result.output["steps_skipped"] == 0
    assert adapter.resets == [("com.facebook.katana", ".activity.FbMainTabActivity")]
    assert adapter.performed_actions == ["back", "tap"]
