from contextlib import contextmanager
from pathlib import Path

import pytest

from agent_runner.agent_tools import AgentToolExecutor
from agent_runner.config import APP_REGISTRY
from agent_runner.models import DeviceInfo, RunContext, ScreenState, VisionDecision
from agent_runner.orchestrator import Orchestrator
from agent_runner.skill_manager import SkillManager
from agent_runner.vision_agent import VisionAgent


class ExplodingAdapter:
    def __init__(self) -> None:
        self.device_serial = "emulator-5554"
        self.closed = False

    @contextmanager
    def session_lock(self):
        yield

    def close(self) -> None:
        self.closed = True

    def is_package_installed(self, package_name: str) -> bool:
        return True

    def launch_app(self, package_name: str, activity: str | None) -> None:
        return None

    def capture_state(self, run_dir: Path):
        raise RuntimeError("capture failed")


def test_orchestrator_closes_adapter_on_failure(tmp_path: Path) -> None:
    adapter = ExplodingAdapter()
    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=SkillManager(tmp_path / "skills")),
        vision_agent=VisionAgent(None, "gemini-3.1-pro-preview"),
        skill_manager=SkillManager(tmp_path / "skills"),
        runs_dir=tmp_path / "runs",
    )
    context = RunContext(
        app=APP_REGISTRY["settings"],
        goal="open settings",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=1,
    )

    with pytest.raises(RuntimeError, match="capture failed"):
        orchestrator.run(context)

    assert adapter.closed is True


class PopupAdapter:
    def __init__(self) -> None:
        self.device_serial = "emulator-5554"
        self.closed = False

    @contextmanager
    def session_lock(self):
        yield

    def close(self) -> None:
        self.closed = True

    def is_package_installed(self, package_name: str) -> bool:
        return True

    def launch_app(self, package_name: str, activity: str | None) -> None:
        return None

    def capture_state(self, run_dir: Path):
        device = DeviceInfo(
            serial="emulator-5554",
            width=1080,
            height=2400,
            density=420,
            orientation="portrait",
            package_name="com.google.android.permissioncontroller",
            activity_name="com.android.permissioncontroller.permission.ui.GrantPermissionsActivity",
        )
        return ScreenState(
            screenshot_path=run_dir / "fake.png",
            hierarchy_path=run_dir / "fake.xml",
            screenshot_sha256="abc",
            xml_source="<hierarchy />",
            visible_text=["Allow Gmail to send notifications?", "Allow", "Don't allow"],
            clickable_text=["Allow", "Don't allow"],
            package_name=device.package_name,
            activity_name=device.activity_name,
            device=device,
            components=[],
        )


def test_orchestrator_returns_approval_required_for_popup(tmp_path: Path) -> None:
    adapter = PopupAdapter()
    skill_manager = SkillManager(tmp_path / "skills")
    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager),
        vision_agent=VisionAgent(None, "gemini-3.1-pro-preview"),
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
    )
    context = RunContext(
        app=APP_REGISTRY["gmail"],
        goal="open Gmail and look through emails",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=1,
    )

    result = orchestrator.run(context)

    assert result.status == "approval_required"
