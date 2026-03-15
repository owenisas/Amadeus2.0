from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from agent_runner.models import (
    AgentToolSpec,
    AppConfig,
    BoundingBox,
    ScreenState,
    SkillBundle,
    ToolExecutionResult,
    VisionDecision,
)
from agent_runner.skill_manager import SkillManager


class AgentToolExecutor:
    SAFE_ADB_PATTERNS: tuple[tuple[str, ...], ...] = (
        ("shell", "pm"),
        ("shell", "cmd", "package"),
        ("shell", "dumpsys"),
        ("shell", "getprop"),
        ("shell", "wm"),
        ("shell", "input"),
        ("shell", "am", "start"),
        ("shell", "am", "broadcast"),
        ("shell", "monkey"),
    )
    BLOCKED_ADB_TOKENS = {
        "reboot",
        "recovery",
        "wipe",
        "factory",
        "reset",
        "uninstall",
        "clear",
        "rm",
        "settings",
        "svc",
        "pm uninstall",
    }

    def __init__(self, *, android_adapter, skill_manager: SkillManager) -> None:
        self.android_adapter = android_adapter
        self.skill_manager = skill_manager

    def list_tools(self) -> list[AgentToolSpec]:
        return [
            AgentToolSpec(
                name="capture_state",
                description="Capture a fresh screenshot, hierarchy dump, and parsed screen summary.",
                requires_state=False,
                mutates_device=False,
            ),
            AgentToolSpec(
                name="launch_app",
                description="Launch or foreground an Android app by package name and optional activity.",
                requires_state=False,
                mutates_device=True,
            ),
            AgentToolSpec(
                name="tap",
                description="Tap a normalized target box on the current screen.",
                requires_state=True,
                mutates_device=True,
            ),
            AgentToolSpec(
                name="type",
                description="Type text with optional submit/Enter on the device.",
                requires_state=False,
                mutates_device=True,
            ),
            AgentToolSpec(
                name="swipe",
                description="Swipe vertically through the current screen.",
                requires_state=True,
                mutates_device=True,
            ),
            AgentToolSpec(
                name="back",
                description="Press the Android back action.",
                requires_state=False,
                mutates_device=True,
            ),
            AgentToolSpec(
                name="home",
                description="Press the Android home action.",
                requires_state=False,
                mutates_device=True,
            ),
            AgentToolSpec(
                name="wait",
                description="Wait for the UI to stabilize for a short period.",
                requires_state=False,
                mutates_device=False,
            ),
            AgentToolSpec(
                name="adb_shell",
                description="Run a restricted adb command for package inspection, app launch, dumpsys, or input.",
                requires_state=False,
                mutates_device=True,
            ),
            AgentToolSpec(
                name="read_skill",
                description="Read a skill file such as SKILL.md, screens.json, selectors.json, state.json, or memory.md.",
                requires_state=False,
                mutates_device=False,
                mutates_skills=False,
            ),
            AgentToolSpec(
                name="write_skill_file",
                description="Create or edit a skill file under skills/apps/<app>/ for SKILL.md, screens.json, selectors.json, state.json, or memory.md.",
                requires_state=False,
                mutates_device=False,
                mutates_skills=True,
            ),
            AgentToolSpec(
                name="bootstrap_skill",
                description="Create a new app skill scaffold with default files.",
                requires_state=False,
                mutates_device=False,
                mutates_skills=True,
            ),
        ]

    def execute(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        handlers = {
            "capture_state": self._capture_state,
            "launch_app": self._launch_app,
            "tap": self._tap,
            "type": self._type,
            "swipe": self._swipe,
            "back": self._back,
            "home": self._home,
            "wait": self._wait,
            "adb_shell": self._adb_shell,
            "read_skill": self._read_skill,
            "write_skill_file": self._write_skill_file,
            "bootstrap_skill": self._bootstrap_skill,
        }
        try:
            handler = handlers[tool_name]
        except KeyError as exc:
            supported = ", ".join(sorted(handlers))
            raise ValueError(f"Unknown tool '{tool_name}'. Supported tools: {supported}") from exc
        return handler(arguments, run_dir=run_dir, current_state=current_state, app=app, skill=skill)

    def _capture_state(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        state = self.android_adapter.capture_state(run_dir)
        return ToolExecutionResult(
            tool_name="capture_state",
            ok=True,
            output={"screen": state.summary()},
            captured_state=state,
        )

    def _launch_app(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        package_name = str(arguments.get("package_name") or (app.package_name if app else ""))
        if not package_name:
            raise ValueError("launch_app requires package_name.")
        activity = arguments.get("activity")
        self.android_adapter.launch_app(package_name, str(activity) if activity else None)
        return ToolExecutionResult(
            tool_name="launch_app",
            ok=True,
            output={"package_name": package_name, "activity": activity},
            refresh_state=True,
        )

    def _tap(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        if current_state is None:
            raise ValueError("tap requires a current screen state.")
        box = BoundingBox.from_dict(arguments.get("target_box"))
        if box is None:
            raise ValueError("tap requires target_box.")
        label = arguments.get("target_label")
        self.android_adapter.perform(
            VisionDecision(
                screen_classification="tool_tap",
                goal_progress="acting",
                next_action="tap",
                target_box=box,
                confidence=1.0,
                reason="Agent tool tap.",
                risk_level="low",
                target_label=str(label) if label else None,
            ),
            current_state,
        )
        return ToolExecutionResult(
            tool_name="tap",
            ok=True,
            output={"target_box": box.to_dict(), "target_label": label},
            refresh_state=True,
        )

    def _type(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        text = str(arguments.get("text") or "")
        if not text:
            raise ValueError("type requires text.")
        submit = bool(arguments.get("submit_after_input", False))
        self.android_adapter.perform(
            VisionDecision(
                screen_classification="tool_type",
                goal_progress="acting",
                next_action="type",
                target_box=None,
                confidence=1.0,
                reason="Agent tool type.",
                risk_level="low",
                input_text=text,
                submit_after_input=submit,
            ),
            current_state or self.android_adapter.capture_state(run_dir),
        )
        return ToolExecutionResult(
            tool_name="type",
            ok=True,
            output={"text": text, "submit_after_input": submit},
            refresh_state=True,
        )

    def _swipe(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        state = current_state or self.android_adapter.capture_state(run_dir)
        self.android_adapter.perform(
            VisionDecision(
                screen_classification="tool_swipe",
                goal_progress="acting",
                next_action="swipe",
                target_box=None,
                confidence=1.0,
                reason="Agent tool swipe.",
                risk_level="low",
            ),
            state,
        )
        return ToolExecutionResult(tool_name="swipe", ok=True, output={}, refresh_state=True)

    def _back(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        state = current_state or self.android_adapter.capture_state(run_dir)
        self.android_adapter.perform(
            VisionDecision(
                screen_classification="tool_back",
                goal_progress="acting",
                next_action="back",
                target_box=None,
                confidence=1.0,
                reason="Agent tool back.",
                risk_level="low",
            ),
            state,
        )
        return ToolExecutionResult(tool_name="back", ok=True, output={}, refresh_state=True)

    def _home(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        state = current_state or self.android_adapter.capture_state(run_dir)
        self.android_adapter.perform(
            VisionDecision(
                screen_classification="tool_home",
                goal_progress="acting",
                next_action="home",
                target_box=None,
                confidence=1.0,
                reason="Agent tool home.",
                risk_level="low",
            ),
            state,
        )
        return ToolExecutionResult(tool_name="home", ok=True, output={}, refresh_state=True)

    def _wait(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        seconds = float(arguments.get("seconds", 2.0))
        self.android_adapter.wait_for_stable_ui(seconds)
        return ToolExecutionResult(
            tool_name="wait",
            ok=True,
            output={"seconds": seconds},
            refresh_state=bool(arguments.get("capture_after_wait", True)),
        )

    def _adb_shell(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        raw_command = str(arguments.get("command") or "").strip()
        if not raw_command:
            raise ValueError("adb_shell requires command.")
        args = shlex.split(raw_command)
        if not self._is_safe_adb_command(args):
            raise ValueError(f"Blocked adb command: {raw_command}")
        result = self.android_adapter.adb_command(args, check=False)
        return ToolExecutionResult(
            tool_name="adb_shell",
            ok=result.returncode == 0,
            output={
                "command": raw_command,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            },
            refresh_state=self._adb_command_changes_ui(args),
            error=None if result.returncode == 0 else result.stderr.strip() or result.stdout.strip(),
        )

    def _read_skill(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        app_name = str(arguments.get("app_name") or (app.name if app else skill.app_name if skill else ""))
        file_name = str(arguments.get("file_name") or "SKILL.md")
        if not app_name:
            raise ValueError("read_skill requires app_name when no current app is active.")
        content = self.skill_manager.read_skill_file(app_name, file_name)
        return ToolExecutionResult(
            tool_name="read_skill",
            ok=True,
            output={"app_name": app_name, "file_name": file_name, "content": content},
        )

    def _write_skill_file(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        app_name = str(arguments.get("app_name") or (app.name if app else skill.app_name if skill else ""))
        file_name = str(arguments.get("file_name") or "")
        if not app_name or not file_name:
            raise ValueError("write_skill_file requires app_name and file_name.")
        if "json_payload" in arguments:
            payload = arguments["json_payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            path = self.skill_manager.update_skill_json(app_name, file_name, payload)
        else:
            content = str(arguments.get("content") or "")
            path = self.skill_manager.write_skill_file(app_name, file_name, content)
        return ToolExecutionResult(
            tool_name="write_skill_file",
            ok=True,
            output={"app_name": app_name, "file_name": file_name, "path": str(path)},
        )

    def _bootstrap_skill(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        app_name = str(arguments.get("app_name") or "")
        package_name = str(arguments.get("package_name") or "")
        default_goal_hint = str(
            arguments.get("default_goal_hint")
            or "Explore the app safely and record reusable selectors and screen signatures."
        )
        if not app_name or not package_name:
            raise ValueError("bootstrap_skill requires app_name and package_name.")
        bundle = self.skill_manager.bootstrap_skill(
            app_name=app_name,
            package_name=package_name,
            default_goal_hint=default_goal_hint,
        )
        return ToolExecutionResult(
            tool_name="bootstrap_skill",
            ok=True,
            output={"app_name": bundle.app_name, "path": str(bundle.app_dir)},
        )

    def _is_safe_adb_command(self, args: list[str]) -> bool:
        if not args:
            return False
        lowered = " ".join(args).casefold()
        if any(token in lowered for token in self.BLOCKED_ADB_TOKENS):
            return False
        return any(tuple(args[: len(pattern)]) == pattern for pattern in self.SAFE_ADB_PATTERNS)

    def _adb_command_changes_ui(self, args: list[str]) -> bool:
        return any(
            tuple(args[: len(pattern)]) == pattern
            for pattern in [
                ("shell", "input"),
                ("shell", "am", "start"),
                ("shell", "monkey"),
            ]
        )
