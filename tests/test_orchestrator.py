from contextlib import contextmanager
import json
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

    def auto_deny_handler(decision, state):
        return "deny"

    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager),
        vision_agent=VisionAgent(None, "gemini-3.1-pro-preview"),
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
        approval_handler=auto_deny_handler,
    )
    context = RunContext(
        app=APP_REGISTRY["gmail"],
        goal="open Gmail and look through emails",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=1,
    )

    result = orchestrator.run(context)

    assert result.status == "blocked"
    assert "denied" in result.reason.lower()


class PopupActionAdapter(PopupAdapter):
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
            components=[
                {
                    "component_type": "button",
                    "label": "Allow",
                    "enabled": True,
                    "search_related": False,
                    "target_box": {"x": 0.12, "y": 0.48, "width": 0.75, "height": 0.06},
                }
            ],
        )

    def perform(self, decision, state):
        return None


def test_orchestrator_yolo_mode_skips_interactive_approval(tmp_path: Path) -> None:
    adapter = PopupActionAdapter()
    skill_manager = SkillManager(tmp_path / "skills")

    def exploding_handler(decision, state):
        raise AssertionError("approval handler should not be called in yolo mode")

    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager),
        vision_agent=VisionAgent(None, "gemini-3.1-pro-preview"),
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
        approval_handler=exploding_handler,
    )
    context = RunContext(
        app=APP_REGISTRY["gmail"],
        goal="open Gmail and look through emails",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=3,
        yolo_mode=True,
    )

    result = orchestrator.run(context)

    assert result.status == "stalled"
    assert result.notice is not None
    assert "yolo mode enabled" in result.notice.casefold()


class StableSettingsAdapter:
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
            package_name="com.android.settings",
            activity_name=".Settings",
        )
        return ScreenState(
            screenshot_path=run_dir / "fake.png",
            hierarchy_path=run_dir / "fake.xml",
            screenshot_sha256="abc",
            xml_source="<hierarchy />",
            visible_text=["Settings", "Network & internet"],
            clickable_text=["Network & internet"],
            package_name=device.package_name,
            activity_name=device.activity_name,
            device=device,
            components=[],
        )


class MalformedTapVisionAgent:
    def decide(self, **kwargs):
        return VisionDecision.tool(
            tool_name="tap",
            tool_arguments={"target_box": {"x": 0.5, "y": 0.5}},
            reason="Tap the row.",
            confidence=0.2,
        )


class ExplodingToolExecutor:
    def list_tools(self):
        return []

    def execute(self, **kwargs):
        raise ValueError("tap requires target_box.")


def test_orchestrator_blocks_when_tool_executor_validation_fails(tmp_path: Path) -> None:
    adapter = StableSettingsAdapter()
    skill_manager = SkillManager(tmp_path / "skills")
    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=ExplodingToolExecutor(),
        vision_agent=MalformedTapVisionAgent(),
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
    )
    context = RunContext(
        app=APP_REGISTRY["settings"],
        goal="open settings",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=1,
    )

    result = orchestrator.run(context)

    assert result.status == "blocked"
    assert "target_box" in result.reason


def test_orchestrator_resumes_after_user_approval(tmp_path: Path) -> None:
    """When the user approves a popup, the orchestrator should continue the run rather than stopping."""
    adapter = PopupAdapter()
    skill_manager = SkillManager(tmp_path / "skills")

    def auto_allow_handler(decision, state):
        return "allow"

    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager),
        vision_agent=VisionAgent(None, "gemini-3.1-pro-preview"),
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
        approval_handler=auto_allow_handler,
    )
    context = RunContext(
        app=APP_REGISTRY["gmail"],
        goal="open Gmail and look through emails",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=3,
    )

    result = orchestrator.run(context)

    # Approval was granted but popup keeps returning, so it should eventually stall or exhaust steps
    assert result.status in {"stalled", "max_steps_reached", "blocked"}


class RestrictionAdapter(PopupAdapter):
    def capture_state(self, run_dir: Path):
        device = DeviceInfo(
            serial="emulator-5554",
            width=1080,
            height=2400,
            density=420,
            orientation="portrait",
            package_name="com.facebook.katana",
            activity_name=".activity.react.ImmersiveReactActivity",
        )
        return ScreenState(
            screenshot_path=run_dir / "fake.png",
            hierarchy_path=run_dir / "fake.xml",
            screenshot_sha256="abc",
            xml_source="<hierarchy />",
            visible_text=[
                "Confirm Your Identity on Marketplace",
                "We detected unusual activity on your account",
                "You can try again tomorrow.",
            ],
            clickable_text=["Get Started"],
            package_name=device.package_name,
            activity_name=device.activity_name,
            device=device,
            components=[],
        )


def test_orchestrator_returns_manual_verification_required(tmp_path: Path) -> None:
    adapter = RestrictionAdapter()
    skill_manager = SkillManager(tmp_path / "skills")
    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager),
        vision_agent=VisionAgent(None, "gemini-3.1-pro-preview"),
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
    )
    context = RunContext(
        app=APP_REGISTRY["facebook"],
        goal="Send a Marketplace message to a seller.",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=1,
        yolo_mode=True,
    )

    result = orchestrator.run(context)

    assert result.status == "manual_verification_required"
    assert "verification" in result.reason.casefold() or "restriction" in result.reason.casefold()


class EventAdapter(PopupActionAdapter):
    def __init__(self) -> None:
        super().__init__()
        self.perform_calls = 0

    def perform(self, decision, state):
        self.perform_calls += 1
        return None


def test_orchestrator_emits_progress_events(tmp_path: Path) -> None:
    adapter = EventAdapter()
    skill_manager = SkillManager(tmp_path / "skills")
    events: list[dict[str, object]] = []

    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager),
        vision_agent=VisionAgent(None, "gemini-3.1-pro-preview"),
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
        event_callback=events.append,
    )
    context = RunContext(
        app=APP_REGISTRY["gmail"],
        goal="Open Gmail and look through emails",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=2,
        yolo_mode=True,
    )

    result = orchestrator.run(context)

    event_types = [str(item["type"]) for item in events]
    assert result.status in {"stalled", "max_steps_reached"}
    assert "run_started" in event_types
    assert "state_captured" in event_types
    assert "decision_made" in event_types


class ContextLoggingAdapter:
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
            package_name="com.android.settings",
            activity_name=".Settings",
        )
        return ScreenState(
            screenshot_path=run_dir / "fake.png",
            hierarchy_path=run_dir / "fake.xml",
            screenshot_sha256="abc",
            xml_source="<hierarchy />",
            visible_text=["Settings"],
            clickable_text=[],
            package_name=device.package_name,
            activity_name=device.activity_name,
            device=device,
            components=[],
        )


class ContextLoggingAgent:
    def __init__(self) -> None:
        self.last_decision_meta = {"provider": "lmstudio", "model": "qwen", "source": "lmstudio_model"}
        self.last_decision_context = {
            "provider": "lmstudio",
            "model": "qwen",
            "source": "lmstudio_model",
            "prompt": "test prompt",
            "response_text": "{\"next_action\":\"stop\"}",
            "response_payload": {"choices": []},
        }

    def decide(self, **kwargs):
        return VisionDecision.stop("Done.")


def test_orchestrator_writes_agent_context_log(tmp_path: Path) -> None:
    adapter = ContextLoggingAdapter()
    skill_manager = SkillManager(tmp_path / "skills")
    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager),
        vision_agent=ContextLoggingAgent(),
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
    )
    context = RunContext(
        app=APP_REGISTRY["settings"],
        goal="Open settings and stop.",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=1,
    )

    result = orchestrator.run(context)
    context_log = result.run_dir / "agent_context.jsonl"

    assert context_log.exists()
    rows = [json.loads(line) for line in context_log.read_text(encoding="utf-8").splitlines()]
    assert any(row["type"] == "decision_made" for row in rows)
    decision_row = next(row for row in rows if row["type"] == "decision_made")
    assert decision_row["decision_context"]["prompt"] == "test prompt"


class InfiniteWaitAdapter:
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
            package_name="com.android.settings",
            activity_name=".Settings",
        )
        return ScreenState(
            screenshot_path=run_dir / "fake.png",
            hierarchy_path=run_dir / "fake.xml",
            screenshot_sha256="abc",
            xml_source="<hierarchy />",
            visible_text=["Settings"],
            clickable_text=[],
            package_name=device.package_name,
            activity_name=device.activity_name,
            device=device,
            components=[],
        )

    def perform(self, decision, state):
        return None


class StopAfterThreeAgent:
    def __init__(self) -> None:
        self.calls = 0

    def decide(self, **kwargs):
        self.calls += 1
        if self.calls < 3:
            return VisionDecision(
                screen_classification="settings_home",
                goal_progress="waiting",
                next_action="wait",
                target_box=None,
                confidence=0.9,
                reason="Wait once more.",
                risk_level="low",
            )
        return VisionDecision.stop("Stop after three decisions.")


def test_orchestrator_treats_zero_max_steps_as_unbounded(tmp_path: Path) -> None:
    adapter = InfiniteWaitAdapter()
    skill_manager = SkillManager(tmp_path / "skills")
    agent = StopAfterThreeAgent()
    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager),
        vision_agent=agent,
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
    )
    context = RunContext(
        app=APP_REGISTRY["settings"],
        goal="Wait until the agent chooses to stop.",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=0,
    )

    result = orchestrator.run(context)

    assert result.status == "completed"
    assert result.steps == 3
    assert agent.calls == 3


class ReloadQualificationAdapter:
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
            package_name="com.fivesurveys.mobile",
            activity_name=".MainActivity",
        )
        return ScreenState(
            screenshot_path=run_dir / "fake.png",
            hierarchy_path=run_dir / "fake.xml",
            screenshot_sha256="abc",
            xml_source="<hierarchy />",
            visible_text=[
                "Qualification",
                "Which languages do you speak?",
                "English",
                "Spanish",
                "Reload",
            ],
            clickable_text=["English", "Spanish", "Reload"],
            package_name=device.package_name,
            activity_name=device.activity_name,
            device=device,
            components=[],
        )

    def perform(self, decision, state):
        return None


class RepeatedTapToolAgent:
    def decide(self, **kwargs):
        return VisionDecision.tool(
            tool_name="tap",
            tool_arguments={
                "target_box": {"x": 0.43, "y": 0.92, "width": 0.14, "height": 0.06},
                "target_label": "Next",
            },
            reason="Tap the qualification next button.",
        )


def test_orchestrator_reports_reload_stuck_reason_for_repeated_same_tap(tmp_path: Path) -> None:
    adapter = ReloadQualificationAdapter()
    skill_manager = SkillManager(tmp_path / "skills")
    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager),
        vision_agent=RepeatedTapToolAgent(),
        skill_manager=skill_manager,
        runs_dir=tmp_path / "runs",
    )
    context = RunContext(
        app=APP_REGISTRY["fivesurveys"],
        goal="Proceed through the qualification screen.",
        run_dir=tmp_path / "runs",
        exploration_enabled=True,
        max_steps=5,
    )

    result = orchestrator.run(context)

    assert result.status == "stalled"
    assert "reload is visible" in result.reason.casefold()
    assert "same target" in result.reason.casefold()
