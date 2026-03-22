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
                name="reset_app",
                description="Force-stop an app and relaunch it to a clean state using an optional activity.",
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
            AgentToolSpec(
                name="save_script",
                description=(
                    "Save a reusable automation script under the app skill. "
                    "A script is a JSON object with 'name', 'description', and 'steps' (list of actions). "
                    "Each step has 'action' (tap/type/swipe/back/home/wait/launch_app/reset_app/run_script), "
                    "and optional 'target_label', 'input_text', 'submit_after_input', 'package_name', "
                    "'wait_seconds', 'script_name', 'only_if_activity_name', and 'only_if_visible_text'. "
                    "Use conditional fields for prompts that only appear sometimes so scripts can normalize to "
                    "a clean start state before continuing."
                ),
                requires_state=False,
                mutates_device=False,
                mutates_skills=True,
            ),
            AgentToolSpec(
                name="run_script",
                description=(
                    "Execute a previously saved automation script by name. "
                    "The script's steps are replayed in order against the current device state."
                ),
                requires_state=True,
                mutates_device=True,
                mutates_skills=False,
            ),
            AgentToolSpec(
                name="list_scripts",
                description="List all saved automation scripts for the current app.",
                requires_state=False,
                mutates_device=False,
                mutates_skills=False,
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
            "reset_app": self._reset_app,
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
            "save_script": self._save_script,
            "run_script": self._run_script,
            "list_scripts": self._list_scripts,
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

    def _reset_app(
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
            raise ValueError("reset_app requires package_name.")
        activity = arguments.get("activity")
        self.android_adapter.reset_app(package_name, str(activity) if activity else None)
        return ToolExecutionResult(
            tool_name="reset_app",
            ok=True,
            output={"package_name": package_name, "activity": activity},
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

    def _save_script(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        app_name = str(arguments.get("app_name") or (app.name if app else skill.app_name if skill else ""))
        script_name = str(arguments.get("script_name") or "")
        if not app_name or not script_name:
            raise ValueError("save_script requires app_name and script_name.")
        script_data = arguments.get("script") or arguments
        if isinstance(script_data, str):
            script_data = json.loads(script_data)
        # Ensure required fields
        if "steps" not in script_data:
            raise ValueError("save_script requires a 'steps' list in the script payload.")
        script = {
            "name": script_name,
            "description": str(script_data.get("description", "")),
            "steps": script_data["steps"],
        }
        path = self.skill_manager.save_script(app_name, script_name, script)
        return ToolExecutionResult(
            tool_name="save_script",
            ok=True,
            output={"app_name": app_name, "script_name": script_name, "path": str(path)},
        )

    def _run_script(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        app_name = str(arguments.get("app_name") or (app.name if app else skill.app_name if skill else ""))
        script_name = str(arguments.get("script_name") or "")
        if not app_name or not script_name:
            raise ValueError("run_script requires app_name and script_name.")
        script = self.skill_manager.read_script(app_name, script_name)
        steps = script.get("steps", [])
        if not steps:
            return ToolExecutionResult(
                tool_name="run_script",
                ok=True,
                output={"app_name": app_name, "script_name": script_name, "steps_executed": 0, "message": "Script has no steps."},
            )
        executed = 0
        skipped = 0
        last_state = current_state
        previous_action = ""
        for step in steps:
            action = str(step.get("action", "")).strip()
            if not action:
                continue
            if previous_action == "wait" or self._script_step_needs_fresh_state(step) or last_state is None:
                last_state = self.android_adapter.capture_state(run_dir)
            if not self._script_step_matches(step, last_state):
                skipped += 1
                previous_action = action
                continue
            if action == "launch_app":
                pkg = str(step.get("package_name") or (app.package_name if app else ""))
                if pkg:
                    self.android_adapter.launch_app(pkg, step.get("activity"))
            elif action == "reset_app":
                pkg = str(step.get("package_name") or (app.package_name if app else ""))
                if pkg:
                    self.android_adapter.reset_app(pkg, step.get("activity"))
            elif action == "tap":
                label = step.get("target_label")
                target_box = BoundingBox.from_dict(step.get("target_box"))
                if label and last_state:
                    # Look up the label in current screen components
                    for component in last_state.components:
                        if str(component.get("label", "")).casefold() == label.casefold():
                            target_box = BoundingBox.from_dict(component.get("target_box"))
                            break
                if target_box is None:
                    raise ValueError(
                        f"Script step 'tap' requires target_box or a resolvable target_label. Step: {json.dumps(step)}"
                    )
                self.android_adapter.perform(
                    VisionDecision(
                        screen_classification="script_tap",
                        goal_progress="scripted",
                        next_action="tap",
                        target_box=target_box,
                        confidence=1.0,
                        reason=f"Script step: tap {label or 'target'}",
                        risk_level="low",
                        target_label=label,
                    ),
                    last_state or self.android_adapter.capture_state(run_dir),
                )
            elif action == "type":
                text = str(step.get("input_text") or step.get("text") or "")
                submit = bool(step.get("submit_after_input", False))
                if text:
                    self.android_adapter.perform(
                        VisionDecision(
                            screen_classification="script_type",
                            goal_progress="scripted",
                            next_action="type",
                            target_box=None,
                            confidence=1.0,
                            reason=f"Script step: type '{text[:30]}'",
                            risk_level="low",
                            input_text=text,
                            submit_after_input=submit,
                        ),
                        last_state or self.android_adapter.capture_state(run_dir),
                    )
            elif action == "swipe":
                self.android_adapter.perform(
                    VisionDecision(
                        screen_classification="script_swipe",
                        goal_progress="scripted",
                        next_action="swipe",
                        target_box=None,
                        confidence=1.0,
                        reason="Script step: swipe",
                        risk_level="low",
                    ),
                    last_state or self.android_adapter.capture_state(run_dir),
                )
            elif action == "back":
                self.android_adapter.perform(
                    VisionDecision(
                        screen_classification="script_back",
                        goal_progress="scripted",
                        next_action="back",
                        target_box=None,
                        confidence=1.0,
                        reason="Script step: back",
                        risk_level="low",
                    ),
                    last_state or self.android_adapter.capture_state(run_dir),
                )
            elif action == "home":
                self.android_adapter.perform(
                    VisionDecision(
                        screen_classification="script_home",
                        goal_progress="scripted",
                        next_action="home",
                        target_box=None,
                        confidence=1.0,
                        reason="Script step: home",
                        risk_level="low",
                    ),
                    last_state or self.android_adapter.capture_state(run_dir),
                )
            elif action == "wait":
                wait_secs = float(step.get("wait_seconds", 2.0))
                self.android_adapter.wait_for_stable_ui(wait_secs)
            elif action == "run_script":
                # Nested script execution
                nested_name = str(step.get("script_name", ""))
                if nested_name:
                    self._run_script(
                        {"app_name": app_name, "script_name": nested_name},
                        run_dir=run_dir,
                        current_state=last_state,
                        app=app,
                        skill=skill,
                    )
            executed += 1
            # Recapture state after each mutating action
            if action not in {"wait"}:
                last_state = self.android_adapter.capture_state(run_dir)
            previous_action = action
        return ToolExecutionResult(
            tool_name="run_script",
            ok=True,
            output={
                "app_name": app_name,
                "script_name": script_name,
                "steps_executed": executed,
                "steps_skipped": skipped,
                "total_steps": len(steps),
            },
            refresh_state=True,
        )

    def _list_scripts(
        self,
        arguments: dict[str, Any],
        *,
        run_dir: Path,
        current_state: ScreenState | None,
        app: AppConfig | None,
        skill: SkillBundle | None,
    ) -> ToolExecutionResult:
        app_name = str(arguments.get("app_name") or (app.name if app else skill.app_name if skill else ""))
        if not app_name:
            raise ValueError("list_scripts requires app_name.")
        scripts = self.skill_manager.list_scripts(app_name)
        return ToolExecutionResult(
            tool_name="list_scripts",
            ok=True,
            output={"app_name": app_name, "scripts": scripts},
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

    def _script_step_needs_fresh_state(self, step: dict[str, Any]) -> bool:
        action = str(step.get("action", "")).strip()
        return action in {"tap", "type", "swipe", "back", "home", "run_script"} or any(
            key in step for key in ("only_if_activity_name", "only_if_visible_text")
        )

    def _script_step_matches(self, step: dict[str, Any], state: ScreenState | None) -> bool:
        if state is None:
            return True
        expected_activity = str(step.get("only_if_activity_name") or "").strip()
        if expected_activity and state.activity_name != expected_activity:
            return False
        text_filters = step.get("only_if_visible_text")
        if not text_filters:
            return True
        if isinstance(text_filters, str):
            needles = [text_filters]
        else:
            needles = [str(value) for value in text_filters if str(value).strip()]
        if not needles:
            return True
        haystacks = [
            *state.visible_text,
            *state.clickable_text,
            *[
                str(component.get("label", ""))
                for component in state.components
                if str(component.get("label", "")).strip()
            ],
        ]
        lowered_haystacks = [entry.casefold() for entry in haystacks]
        return any(
            needle.casefold() in haystack
            for needle in needles
            for haystack in lowered_haystacks
        )
