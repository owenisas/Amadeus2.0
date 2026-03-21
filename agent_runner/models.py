from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class BoundingBox:
    x: float
    y: float
    width: float
    height: float

    def clamp(self) -> "BoundingBox":
        return BoundingBox(
            x=min(max(self.x, 0.0), 1.0),
            y=min(max(self.y, 0.0), 1.0),
            width=min(max(self.width, 0.0), 1.0),
            height=min(max(self.height, 0.0), 1.0),
        )

    def center(self) -> tuple[float, float]:
        box = self.clamp()
        return (box.x + (box.width / 2.0), box.y + (box.height / 2.0))

    def to_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "BoundingBox | None":
        if not payload:
            return None
        required = {"x", "y", "width", "height"}
        if not required.issubset(payload):
            return None
        return cls(
            x=float(payload["x"]),
            y=float(payload["y"]),
            width=float(payload["width"]),
            height=float(payload["height"]),
        )


@dataclass(slots=True)
class DeviceInfo:
    serial: str
    width: int
    height: int
    density: int | None
    orientation: str
    package_name: str
    activity_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "serial": self.serial,
            "width": self.width,
            "height": self.height,
            "density": self.density,
            "orientation": self.orientation,
            "package_name": self.package_name,
            "activity_name": self.activity_name,
        }


@dataclass(slots=True)
class ScreenState:
    screenshot_path: Path
    hierarchy_path: Path
    screenshot_sha256: str
    xml_source: str
    visible_text: list[str]
    clickable_text: list[str]
    package_name: str
    activity_name: str
    device: DeviceInfo
    components: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "screenshot_path": str(self.screenshot_path),
            "hierarchy_path": str(self.hierarchy_path),
            "visible_text": self.visible_text[:40],
            "clickable_text": self.clickable_text[:25],
            "components": self.components[:20],
            "package_name": self.package_name,
            "activity_name": self.activity_name,
            "device": self.device.to_dict(),
        }


@dataclass(slots=True)
class VisionDecision:
    screen_classification: str
    goal_progress: str
    next_action: str
    target_box: BoundingBox | None
    confidence: float
    reason: str
    risk_level: str
    input_text: str | None = None
    submit_after_input: bool = False
    target_label: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    requires_user_approval: bool = False

    @classmethod
    def stop(
        cls,
        reason: str,
        risk_level: str = "low",
        *,
        goal_progress: str = "blocked",
        requires_user_approval: bool = False,
    ) -> "VisionDecision":
        return cls(
            screen_classification="unknown",
            goal_progress=goal_progress,
            next_action="stop",
            target_box=None,
            confidence=1.0,
            reason=reason,
            risk_level=risk_level,
            requires_user_approval=requires_user_approval,
        )

    @classmethod
    def tool(
        cls,
        *,
        tool_name: str,
        tool_arguments: dict[str, Any] | None,
        reason: str,
        screen_classification: str = "tool_request",
        goal_progress: str = "tooling",
        confidence: float = 0.8,
        risk_level: str = "low",
        target_label: str | None = None,
    ) -> "VisionDecision":
        return cls(
            screen_classification=screen_classification,
            goal_progress=goal_progress,
            next_action="tool",
            target_box=None,
            confidence=confidence,
            reason=reason,
            risk_level=risk_level,
            target_label=target_label,
            tool_name=tool_name,
            tool_arguments=tool_arguments or {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "screen_classification": self.screen_classification,
            "goal_progress": self.goal_progress,
            "next_action": self.next_action,
            "target_box": self.target_box.to_dict() if self.target_box else None,
            "confidence": self.confidence,
            "reason": self.reason,
            "risk_level": self.risk_level,
            "input_text": self.input_text,
            "submit_after_input": self.submit_after_input,
            "target_label": self.target_label,
            "tool_name": self.tool_name,
            "tool_arguments": self.tool_arguments,
            "requires_user_approval": self.requires_user_approval,
        }


@dataclass(slots=True)
class SafetyVerdict:
    allowed: bool
    reason: str


@dataclass(slots=True)
class ActionRecord:
    step: int
    action: str
    reason: str
    allowed: bool
    package_name: str
    activity_name: str
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    tool_output: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "step": self.step,
            "action": self.action,
            "reason": self.reason,
            "allowed": self.allowed,
            "package_name": self.package_name,
            "activity_name": self.activity_name,
            "tool_name": self.tool_name,
            "tool_arguments": self.tool_arguments,
            "tool_output": self.tool_output,
        }


@dataclass(slots=True)
class AgentToolSpec:
    name: str
    description: str
    requires_state: bool
    mutates_device: bool
    mutates_skills: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "requires_state": self.requires_state,
            "mutates_device": self.mutates_device,
            "mutates_skills": self.mutates_skills,
        }


@dataclass(slots=True)
class ToolExecutionResult:
    tool_name: str
    ok: bool
    output: dict[str, Any]
    refresh_state: bool = False
    captured_state: ScreenState | None = None
    error: str | None = None


@dataclass(slots=True)
class AppConfig:
    name: str
    package_name: str
    launch_activity: str | None
    allowed_actions: list[str]
    blocked_keywords: list[str]
    high_risk_signatures: list[str]
    manual_login_tokens: list[str]
    default_goal_hint: str


@dataclass(slots=True)
class SkillBundle:
    app_name: str
    app_dir: Path
    instructions: str
    screens: dict[str, Any]
    selectors: dict[str, Any]
    state: dict[str, Any]
    memory: str


@dataclass(slots=True)
class RunContext:
    app: AppConfig
    goal: str
    run_dir: Path
    exploration_enabled: bool
    max_steps: int
    yolo_mode: bool = False
    action_history: list[ActionRecord] = field(default_factory=list)


@dataclass(slots=True)
class RunResult:
    status: str
    reason: str
    steps: int
    run_dir: Path
    last_state: ScreenState | None = None
    notice: str | None = None
