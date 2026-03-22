from __future__ import annotations

import json
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Footer, Header, Input, RichLog, Static

from agent_runner.cli import _format_live_event
from agent_runner.config import get_app_config
from agent_runner.session_controller import SessionController


class CommandSubmitted(Message):
    def __init__(self, command: str) -> None:
        super().__init__()
        self.command = command


class AgentSessionTui(App[None]):
    CSS = """
    Screen {
        layout: vertical;
    }
    #body {
        height: 1fr;
    }
    #left, #right {
        width: 34;
        min-width: 28;
    }
    #center {
        width: 1fr;
    }
    #log {
        height: 1fr;
    }
    #command_bar {
        height: auto;
        padding: 0 1 1 1;
        border-top: solid $accent 20%;
        background: $surface;
    }
    #hint {
        height: 2;
        color: $text;
        padding: 0 1 0 1;
    }
    #command {
        margin-top: 0;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("c", "clear_log", "Clear log"),
        ("x", "interrupt", "Interrupt"),
        ("y", "toggle_yolo", "Toggle YOLO"),
        ("i", "toggle_infinite", "Toggle infinite"),
    ]

    def __init__(self, controller: SessionController) -> None:
        super().__init__()
        self.controller = controller
        self._last_active_event_count = 0
        self._last_notification_count = 0
        self._preferred_app_name: str | None = None
        self._yolo_mode_enabled = False
        self._infinite_mode_enabled = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Static("", id="tasks")
                yield Static("", id="jobs")
                yield Static("", id="notifications")
            with Vertical(id="center"):
                yield RichLog(id="log", wrap=True, markup=False, highlight=False)
            with Vertical(id="right"):
                yield Static("", id="runtime")
                yield Static("", id="state")
        with Vertical(id="command_bar"):
            yield Static("", id="hint")
            yield Input(placeholder="Type a goal directly, or use /help", id="command")
        yield Footer()

    def on_mount(self) -> None:
        log = self.query_one("#log", RichLog)
        try:
            result = self.controller.ensure_appium_running()
            if result.get("started"):
                log.write(f"[startup] Appium started automatically. log={result.get('log_path')}")
        except Exception as exc:
            log.write(f"[startup_error] {exc}")
        self.controller.start_background_services(scheduler=True, notifications=True)
        self.set_interval(1.0, self.refresh_panels)
        self.refresh_panels()
        self._update_hint("")
        self.query_one("#command", Input).focus()

    def on_unmount(self) -> None:
        self.controller.close()

    def action_refresh(self) -> None:
        self.refresh_panels()

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_toggle_yolo(self) -> None:
        self._yolo_mode_enabled = not self._yolo_mode_enabled
        self.query_one("#log", RichLog).write(
            f"[toggle] yolo={'on' if self._yolo_mode_enabled else 'off'}"
        )
        self.refresh_panels()

    def action_toggle_infinite(self) -> None:
        self._infinite_mode_enabled = not self._infinite_mode_enabled
        self.query_one("#log", RichLog).write(
            f"[toggle] infinite={'on' if self._infinite_mode_enabled else 'off'}"
        )
        self.refresh_panels()

    def action_interrupt(self) -> None:
        log = self.query_one("#log", RichLog)
        try:
            response = self.controller.interrupt_active_job()
            log.write("[interrupt] requested")
            log.write(json.dumps(response, indent=2, sort_keys=True))
        except Exception as exc:
            log.write(f"[interrupt_error] {exc}")
        self.refresh_panels()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.post_message(CommandSubmitted(event.value.strip()))
        event.input.value = ""
        self._update_hint("")

    def on_input_changed(self, event: Input.Changed) -> None:
        self._update_hint(event.value)

    def on_command_submitted(self, message: CommandSubmitted) -> None:
        if not message.command:
            return
        log = self.query_one("#log", RichLog)
        try:
            is_command = message.command.startswith("/")
            response = self._execute_command(message.command)
            log.write(f"[{'command' if is_command else 'prompt'}] {message.command}")
            log.write(json.dumps(response, indent=2, sort_keys=True))
        except Exception as exc:
            log.write(f"[command_error] {message.command}")
            log.write(str(exc))
        self.refresh_panels()

    def refresh_panels(self) -> None:
        self._update_runtime()
        self._update_tasks()
        self._update_jobs()
        self._update_notifications()
        self._update_state()
        self._append_live_events()

    def _update_runtime(self) -> None:
        payload = self.controller.runtime_payload()
        lines = [
            "Runtime",
            f"Device: {payload['device_serial']}",
            f"Provider: {payload['model_provider']}",
            f"Model: {payload['vision_model']}",
            f"ADB: {payload['adb_status']}",
            f"Appium: {payload['appium_status']}",
            f"Notif access: {'ready' if payload['notification_listener_enabled'] else 'missing'}",
            f"YOLO: {'on' if self._yolo_mode_enabled else 'off'}",
            f"Infinite: {'on' if self._infinite_mode_enabled else 'off'}",
            f"Active: {self._active_status_label(payload.get('active_job'))}",
        ]
        self.query_one("#runtime", Static).update("\n".join(lines))
        self.sub_title = f"{payload['device_serial']} | {payload['model_provider']}:{payload['vision_model']}"

    def _update_tasks(self) -> None:
        tasks = self.controller.tasks_payload()[:8]
        lines = ["Tasks"]
        if not tasks:
            lines.append("No tasks")
        for task in tasks:
            lines.append(f"{task['task_id']}")
            lines.append(f"  {task['status']} | {task['app_name']}")
        self.query_one("#tasks", Static).update("\n".join(lines))

    def _update_jobs(self) -> None:
        jobs = self.controller.jobs_payload()[:8]
        lines = ["Jobs"]
        if not jobs:
            lines.append("No jobs")
        for job in jobs:
            lines.append(f"{job['job_id']}")
            lines.append(f"  {'on' if job['enabled'] else 'off'} | next {job['next_run_at'] or '-'}")
        self.query_one("#jobs", Static).update("\n".join(lines))

    def _update_notifications(self) -> None:
        notifications = self.controller.notifications_payload(limit=5)
        lines = ["Notifications"]
        if not notifications:
            lines.append("No events")
        for notification in notifications:
            lines.append(f"{notification.get('event_type')} | {notification.get('package_name', '-')}")
            text = notification.get("title") or notification.get("text") or notification.get("detail") or ""
            if text:
                lines.append(f"  {str(text)[:60]}")
        self.query_one("#notifications", Static).update("\n".join(lines))

    def _update_state(self) -> None:
        payload = self.controller.device_state_payload()
        screen = payload.get("screen") or {}
        lines = ["State"]
        if payload.get("screen_error"):
            lines.append(f"Error: {payload['screen_error']}")
        if screen:
            lines.extend(
                [
                    f"App: {screen.get('package_name')}",
                    f"Activity: {screen.get('activity_name')}",
                    f"Visible: {', '.join(list(screen.get('visible_text') or [])[:6])}",
                    f"Clickable: {', '.join(list(screen.get('clickable_text') or [])[:6])}",
                    f"Screenshot: {screen.get('screenshot_path')}",
                    f"Hierarchy: {screen.get('hierarchy_path')}",
                ]
            )
        self.query_one("#state", Static).update("\n".join(lines))

    def _append_live_events(self) -> None:
        log = self.query_one("#log", RichLog)
        active = self.controller.active_job_payload()
        if active:
            events = list(active.get("events") or [])
            while self._last_active_event_count < len(events):
                line = _format_live_event(events[self._last_active_event_count])
                if line:
                    log.write(line)
                self._last_active_event_count += 1
        else:
            self._last_active_event_count = 0
        notifications = self.controller.notifications_payload(limit=200)
        while self._last_notification_count < len(notifications):
            event = notifications[self._last_notification_count]
            log.write(f"[notification] {event.get('event_type')} {event.get('package_name', '')} {event.get('title') or event.get('text') or ''}".strip())
            self._last_notification_count += 1

    def _execute_command(self, raw: str) -> dict[str, Any]:
        if not raw.startswith("/"):
            app_name = self._resolve_prompt_app_name()
            return self.controller.start_session(
                app_name=app_name,
                goal=raw,
                max_steps=self._step_budget(),
                yolo_mode=self._yolo_mode_enabled,
            )

        command, _, remainder = raw.removeprefix("/").partition(" ")
        command = command.strip().casefold()
        remainder = remainder.strip()
        if command == "help":
            app_name = self._preferred_app_name or self.controller.infer_app_name() or "<set with /app>"
            return {
                "commands": [
                    "/run <app> | <goal>",
                    "/task <app> | <goal>",
                    "/resume <task-id>",
                    "/interrupt",
                    "/cancel <task-id>",
                    "/model show",
                    "/model gemini [model-name]",
                    "/model lmstudio [model-name]",
                    "/tool <tool> | <json-args>",
                    "/job add <name> | <cron> | <app> | <goal>",
                    "/job enable <job-id>",
                    "/job disable <job-id>",
                    "/yolo [on|off|toggle]",
                    "/infinite [on|off|toggle]",
                    "/app <app-name>",
                    "/app clear",
                    "/open",
                ],
                "direct_prompt": (
                    f"Type a goal directly to start an agent run on {app_name} "
                    f"(yolo={'on' if self._yolo_mode_enabled else 'off'}, "
                    f"infinite={'on' if self._infinite_mode_enabled else 'off'})"
                ),
            }
        if command == "app":
            target = remainder.strip()
            if not target:
                raise ValueError("Use /app <app-name> or /app clear.")
            if target.casefold() == "clear":
                self._preferred_app_name = None
                return {"preferred_app_name": None}
            get_app_config(target)
            self._preferred_app_name = target
            return {"preferred_app_name": self._preferred_app_name}
        if command == "yolo":
            state = self._apply_toggle_command("yolo", remainder)
            self._yolo_mode_enabled = state
            return {"yolo_mode": state}
        if command == "infinite":
            state = self._apply_toggle_command("infinite", remainder)
            self._infinite_mode_enabled = state
            return {"infinite_mode": state, "max_steps": self._step_budget()}
        if command == "model":
            return self._execute_model_command(remainder)
        if command == "run":
            app_name, goal = self._split_pipe(remainder, 2)
            return self.controller.start_session(
                app_name=app_name,
                goal=goal,
                max_steps=self._step_budget(),
                yolo_mode=self._yolo_mode_enabled,
            )
        if command == "task":
            app_name, goal = self._split_pipe(remainder, 2)
            return self.controller.start_task(
                app_name=app_name,
                goal=goal,
                max_steps=self._step_budget(),
                yolo_mode=self._yolo_mode_enabled,
            )
        if command == "resume":
            return self.controller.resume_task(task_id=remainder, max_steps=None, yolo_mode=None)
        if command == "interrupt":
            if remainder:
                raise ValueError("/interrupt does not take arguments.")
            return self.controller.interrupt_active_job()
        if command == "cancel":
            return self.controller.cancel_task(task_id=remainder)
        if command == "tool":
            tool_name, payload = self._split_pipe(remainder, 2)
            args = json.loads(payload or "{}")
            app_name = args.pop("_app", None)
            return self.controller.run_tool(tool_name=tool_name, app_name=app_name, arguments=args)
        if command == "job":
            return self._execute_job_command(remainder)
        if command == "open":
            payload = self.controller.device_state_payload()
            screen = payload.get("screen") or {}
            return {
                "run_dir": (self.controller.active_job_payload() or {}).get("run_dir"),
                "screenshot_path": screen.get("screenshot_path"),
                "hierarchy_path": screen.get("hierarchy_path"),
            }
        raise ValueError(f"Unknown command '/{command}'. Use /help.")

    def _execute_job_command(self, raw: str) -> dict[str, Any]:
        subcommand, _, remainder = raw.partition(" ")
        subcommand = subcommand.strip().casefold()
        remainder = remainder.strip()
        if subcommand == "add":
            name, cron, app_name, goal = self._split_pipe(remainder, 4)
            return self.controller.create_job(
                name=name,
                app_name=app_name,
                goal=goal,
                cron=cron,
                max_steps=self._step_budget(),
                yolo_mode=self._yolo_mode_enabled,
            )
        if subcommand == "enable":
            return self.controller.update_job(job_id=remainder, enabled=True)
        if subcommand == "disable":
            return self.controller.update_job(job_id=remainder, enabled=False)
        raise ValueError(f"Unknown job subcommand '{subcommand}'.")

    def _execute_model_command(self, raw: str) -> dict[str, Any]:
        subcommand, _, remainder = raw.partition(" ")
        subcommand = subcommand.strip().casefold() or "show"
        remainder = remainder.strip()
        if subcommand == "show":
            return self.controller.runtime_payload()
        if subcommand == "gemini":
            return self.controller.update_model_settings(
                model_provider="gemini",
                gemini_model=(remainder or None),
            )
        if subcommand == "lmstudio":
            return self.controller.update_model_settings(
                model_provider="lmstudio",
                lmstudio_model=(remainder or None),
            )
        raise ValueError("Use /model show, /model gemini [model-name], or /model lmstudio [model-name].")

    @staticmethod
    def _split_pipe(value: str, parts: int) -> list[str]:
        items = [item.strip() for item in value.split("|", maxsplit=parts - 1)]
        if len(items) != parts or any(not item for item in items):
            raise ValueError("Command arguments must use '|' separators.")
        return items

    def _resolve_prompt_app_name(self) -> str:
        if self._preferred_app_name:
            return self._preferred_app_name
        inferred = self.controller.infer_app_name()
        if inferred:
            return inferred
        raise ValueError("No app context is set. Use /app <app-name> or a slash command with an explicit app.")

    def _update_hint(self, value: str) -> None:
        hint = self._hint_for(value)
        self.query_one("#hint", Static).update(hint)

    def _hint_for(self, value: str) -> str:
        text = value.strip()
        if not text:
            app_name = self._preferred_app_name or self.controller.infer_app_name() or "<app>"
            return (
                f"Direct prompt -> agent on {app_name}. "
                f"yolo={'on' if self._yolo_mode_enabled else 'off'} "
                f"infinite={'on' if self._infinite_mode_enabled else 'off'}. "
                "Slash commands: /run, /task, /interrupt, /model, /tool, /job, /app, /yolo, /infinite, /help"
            )
        if not text.startswith("/"):
            app_name = self._preferred_app_name or self.controller.infer_app_name() or "<set with /app>"
            return (
                f"Enter to send direct goal to {app_name}. "
                f"Current toggles: yolo={'on' if self._yolo_mode_enabled else 'off'}, "
                f"infinite={'on' if self._infinite_mode_enabled else 'off'}."
            )
        command = text.removeprefix("/").split(" ", 1)[0].casefold()
        hints = {
            "": "/run <app> | <goal>   /task <app> | <goal>   /tool <tool> | <json>   /yolo toggle   /infinite toggle",
            "help": "/help shows all commands. Plain text sends a direct goal to the current app context.",
            "run": "/run <app> | <goal>",
            "task": "/task <app> | <goal>",
            "resume": "/resume <task-id>",
            "interrupt": "/interrupt stops the active session, task, or scheduled job cleanly",
            "cancel": "/cancel <task-id>",
            "model": "/model show   /model gemini [model-name]   /model lmstudio [model-name]",
            "tool": "/tool <tool-name> | <json-args>. Add \"_app\":\"settings\" inside args when needed.",
            "job": "/job add <name> | <cron> | <app> | <goal>   /job enable <job-id>   /job disable <job-id>",
            "app": "/app <app-name> to pin direct prompts, or /app clear",
            "yolo": "/yolo on | /yolo off | /yolo toggle",
            "infinite": "/infinite on | /infinite off | /infinite toggle",
            "open": "/open returns latest run_dir, screenshot_path, and hierarchy_path",
        }
        if command in hints:
            return hints[command]
        matches = [name for name in hints if name and name.startswith(command)]
        if matches:
            return " / ".join(f"/{name}" for name in matches)
        return "Unknown slash command. Use /help."

    def _step_budget(self) -> int:
        return 0 if self._infinite_mode_enabled else 12

    @staticmethod
    def _active_status_label(active_job: dict[str, Any] | None) -> str:
        if not active_job:
            return "idle"
        label = str(active_job.get("job_type") or "running")
        if active_job.get("interrupt_requested"):
            return f"{label} (interrupting)"
        return label

    def _apply_toggle_command(self, name: str, raw_value: str) -> bool:
        token = raw_value.strip().casefold() or "toggle"
        current = self._yolo_mode_enabled if name == "yolo" else self._infinite_mode_enabled
        if token == "toggle":
            return not current
        if token in {"on", "true", "1", "yes"}:
            return True
        if token in {"off", "false", "0", "no"}:
            return False
        raise ValueError(f"Use /{name} on, /{name} off, or /{name} toggle.")


def serve_tui(runtime) -> None:
    controller = SessionController(runtime)
    app = AgentSessionTui(controller)
    app.run()
