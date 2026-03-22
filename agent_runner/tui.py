from __future__ import annotations

import json
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Footer, Header, Input, RichLog, Static

from agent_runner.cli import _format_live_event
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
    #command {
        dock: bottom;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("c", "clear_log", "Clear log"),
    ]

    def __init__(self, controller: SessionController) -> None:
        super().__init__()
        self.controller = controller
        self._last_active_event_count = 0
        self._last_notification_count = 0

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
        yield Input(placeholder="run settings | Open Wi-Fi   |   job add Nightly | */15 * * * * | settings | Inspect Wi-Fi", id="command")
        yield Footer()

    def on_mount(self) -> None:
        self.controller.start_background_services(scheduler=True, notifications=True)
        self.set_interval(1.0, self.refresh_panels)
        self.refresh_panels()

    def on_unmount(self) -> None:
        self.controller.close()

    def action_refresh(self) -> None:
        self.refresh_panels()

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.post_message(CommandSubmitted(event.value.strip()))
        event.input.value = ""

    def on_command_submitted(self, message: CommandSubmitted) -> None:
        if not message.command:
            return
        log = self.query_one("#log", RichLog)
        try:
            response = self._execute_command(message.command)
            log.write(f"[command] {message.command}")
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
            f"Active: {payload['active_job']['job_type'] if payload['active_job'] else 'idle'}",
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
        command, _, remainder = raw.partition(" ")
        command = command.strip().casefold()
        remainder = remainder.strip()
        if command == "run":
            app_name, goal = self._split_pipe(remainder, 2)
            return self.controller.start_session(app_name=app_name, goal=goal, max_steps=12, yolo_mode=False)
        if command == "runyolo":
            app_name, goal = self._split_pipe(remainder, 2)
            return self.controller.start_session(app_name=app_name, goal=goal, max_steps=12, yolo_mode=True)
        if command == "task":
            app_name, goal = self._split_pipe(remainder, 2)
            return self.controller.start_task(app_name=app_name, goal=goal, max_steps=12, yolo_mode=False)
        if command == "resume":
            return self.controller.resume_task(task_id=remainder, max_steps=None, yolo_mode=None)
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
            kind = remainder.casefold()
            payload = self.controller.device_state_payload()
            screen = payload.get("screen") or {}
            return {
                "run_dir": (self.controller.active_job_payload() or {}).get("run_dir"),
                "screenshot_path": screen.get("screenshot_path"),
                "hierarchy_path": screen.get("hierarchy_path"),
            }
        raise ValueError(f"Unknown command '{command}'.")

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
                max_steps=12,
                yolo_mode=False,
            )
        if subcommand == "enable":
            return self.controller.update_job(job_id=remainder, enabled=True)
        if subcommand == "disable":
            return self.controller.update_job(job_id=remainder, enabled=False)
        raise ValueError(f"Unknown job subcommand '{subcommand}'.")

    @staticmethod
    def _split_pipe(value: str, parts: int) -> list[str]:
        items = [item.strip() for item in value.split("|", maxsplit=parts - 1)]
        if len(items) != parts or any(not item for item in items):
            raise ValueError("Command arguments must use '|' separators.")
        return items


def serve_tui(runtime) -> None:
    controller = SessionController(runtime)
    app = AgentSessionTui(controller)
    app.run()
