from __future__ import annotations

import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from agent_runner.android_adapter import AndroidAdapter
from agent_runner.agent_tools import AgentToolExecutor
from agent_runner.config import get_app_config, list_app_configs
from agent_runner.event_queue import EventQueue
from agent_runner.job_manager import JobManager
from agent_runner.models import JobRecord, RunContext, RunResult, ScreenState, TaskRecord
from agent_runner.notifications import NotificationMonitor, notification_listener_enabled
from agent_runner.orchestrator import Orchestrator
from agent_runner.run_payload import build_run_payload
from agent_runner.skill_manager import SkillManager
from agent_runner.task_manager import TaskManager
from agent_runner.utils import ensure_directory
from agent_runner.vision_agent import VisionAgent


NOTIFICATION_COMPONENT = "com.amadeus.nativeagent/com.amadeus.nativeagent.service.AgentNotificationListenerService"


@dataclass(slots=True)
class SessionJob:
    job_type: str
    app_name: str
    goal: str
    device_serial: str
    started_at: float
    status: str = "running"
    task_id: str | None = None
    job_id: str | None = None
    step_budget: int | None = None
    yolo_mode: bool = False
    run_dir: str | None = None
    last_reason: str | None = None
    latest_state: dict[str, Any] | None = None
    payload: dict[str, Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_type": self.job_type,
            "app_name": self.app_name,
            "goal": self.goal,
            "device_serial": self.device_serial,
            "started_at": self.started_at,
            "status": self.status,
            "task_id": self.task_id,
            "job_id": self.job_id,
            "step_budget": self.step_budget,
            "yolo_mode": self.yolo_mode,
            "run_dir": self.run_dir,
            "last_reason": self.last_reason,
            "latest_state": self.latest_state,
            "payload": self.payload,
            "events": self.events[-100:],
        }


class SessionController:
    IDLE_CAPTURE_TTL_SECONDS = 2.0
    SCHEDULER_POLL_SECONDS = 5.0
    APPIUM_AUTOSTART_COOLDOWN_SECONDS = 15.0
    APPIUM_START_TIMEOUT_SECONDS = 12.0

    def __init__(self, runtime) -> None:
        self.runtime = runtime
        self.model_provider = runtime.model_provider
        self.gemini_model = runtime.gemini_model
        self.lmstudio_model = runtime.lmstudio_model
        self.adapter = AndroidAdapter(
            appium_url=runtime.appium_url,
            device_serial=runtime.device_serial,
            adb_path=runtime.adb_path,
            android_sdk_root=runtime.android_sdk_root,
        )
        self.skill_manager = SkillManager(runtime.skills_dir, runtime.system_skill_file)
        self.tool_executor = AgentToolExecutor(android_adapter=self.adapter, skill_manager=self.skill_manager)
        self.task_manager = TaskManager(runtime.runs_dir / "tasks")
        self.job_manager = JobManager(runtime.runs_dir / "jobs")
        self.event_queue = EventQueue(runtime.runs_dir)
        self.session_run_dir = ensure_directory(runtime.runs_dir / "session-live")
        self.appium_log_path = self.event_queue.root / "appium.log"
        self._lock = threading.RLock()
        self._active_job: SessionJob | None = None
        self._last_job: SessionJob | None = None
        self._idle_state: ScreenState | None = None
        self._idle_state_at: float = 0.0
        self._notifications: list[dict[str, Any]] = []
        self._notification_monitor: NotificationMonitor | None = None
        self._scheduler_thread: threading.Thread | None = None
        self._scheduler_stop = threading.Event()
        self._appium_process: subprocess.Popen[bytes] | None = None
        self._last_appium_start_attempt_at: float = 0.0

    def close(self) -> None:
        self.stop_background_services()
        self.adapter.close()

    def start_background_services(self, *, scheduler: bool = False, notifications: bool = False) -> None:
        if notifications and self._notification_monitor is None:
            self._notification_monitor = NotificationMonitor(
                adb_path=self.runtime.adb_path,
                device_serial=self.runtime.device_serial,
                on_event=self._handle_notification_event,
            )
            self._notification_monitor.start()
        if scheduler and (self._scheduler_thread is None or not self._scheduler_thread.is_alive()):
            self._scheduler_stop.clear()
            self._scheduler_thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self._scheduler_thread.start()

    def ensure_appium_running(self, *, force: bool = False) -> dict[str, Any]:
        status = self._appium_status()
        if status == "ready":
            return {"status": status, "started": False, "log_path": str(self.appium_log_path)}
        now = time.time()
        if not force and (now - self._last_appium_start_attempt_at) < self.APPIUM_AUTOSTART_COOLDOWN_SECONDS:
            return {"status": status, "started": False, "log_path": str(self.appium_log_path)}
        appium_binary = shutil.which("appium")
        if not appium_binary:
            raise RuntimeError("Appium is not installed or not on PATH.")
        env = os.environ.copy()
        if self.runtime.android_sdk_root:
            env.setdefault("ANDROID_SDK_ROOT", self.runtime.android_sdk_root)
            env.setdefault("ANDROID_HOME", self.runtime.android_sdk_root)
        ensure_directory(self.event_queue.root)
        with self.appium_log_path.open("ab") as handle:
            self._appium_process = subprocess.Popen(
                [appium_binary],
                stdout=handle,
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True,
            )
        self._last_appium_start_attempt_at = now
        deadline = time.time() + self.APPIUM_START_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self._appium_process.poll() is not None:
                raise RuntimeError(f"Appium exited early. Check {self.appium_log_path}.")
            if self._appium_status() == "ready":
                return {"status": "ready", "started": True, "log_path": str(self.appium_log_path)}
            time.sleep(0.5)
        raise RuntimeError(f"Appium did not become ready within {self.APPIUM_START_TIMEOUT_SECONDS:.0f}s. Check {self.appium_log_path}.")

    def stop_background_services(self) -> None:
        self._scheduler_stop.set()
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=1)
            self._scheduler_thread = None
        if self._notification_monitor:
            self._notification_monitor.stop()
            self._notification_monitor = None

    def runtime_payload(self) -> dict[str, Any]:
        return {
            "device_serial": self.runtime.device_serial,
            "appium_url": self.runtime.appium_url,
            "model_provider": self.model_provider,
            "vision_model": self._active_model_name(),
            "gemini_model": self.gemini_model,
            "lmstudio_model": self.lmstudio_model,
            "lmstudio_base_url": self.runtime.lmstudio_base_url,
            "runs_dir": str(self.runtime.runs_dir),
            "event_queue_path": str(self.event_queue.path),
            "notification_listener_enabled": notification_listener_enabled(
                adb_path=self.runtime.adb_path,
                device_serial=self.runtime.device_serial,
                component_name=NOTIFICATION_COMPONENT,
            ),
            "adb_status": self._adb_status(),
            "appium_status": self._appium_status(),
            "active_job": self.active_job_payload(),
        }

    def update_model_settings(
        self,
        *,
        model_provider: str,
        gemini_model: str | None = None,
        lmstudio_model: str | None = None,
    ) -> dict[str, Any]:
        normalized = model_provider.strip().casefold()
        if normalized not in {"gemini", "lmstudio"}:
            raise ValueError("model_provider must be 'gemini' or 'lmstudio'.")
        if gemini_model is not None:
            model = gemini_model.strip()
            if not model:
                raise ValueError("gemini_model must not be empty.")
            self.gemini_model = model
        if lmstudio_model is not None:
            model = lmstudio_model.strip()
            if not model:
                raise ValueError("lmstudio_model must not be empty.")
            self.lmstudio_model = model
        self.model_provider = normalized
        return self.runtime_payload()

    def apps_payload(self) -> list[dict[str, Any]]:
        return [
            {
                "name": app.name,
                "package_name": app.package_name,
                "launch_activity": app.launch_activity,
                "default_goal_hint": app.default_goal_hint,
            }
            for app in list_app_configs()
        ]

    def tools_payload(self) -> list[dict[str, Any]]:
        return [tool.to_dict() for tool in self.tool_executor.list_tools()]

    def tasks_payload(self) -> list[dict[str, Any]]:
        return [task.to_dict() for task in self.task_manager.list_tasks(device_serial=self.runtime.device_serial)]

    def jobs_payload(self) -> list[dict[str, Any]]:
        return [job.to_dict() for job in self.job_manager.list_jobs(device_serial=self.runtime.device_serial)]

    def notifications_payload(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._notifications[-limit:])

    def active_job_payload(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active_job is not None:
                return self._active_job.to_dict()
            if self._last_job is not None:
                return self._last_job.to_dict()
        return None

    def task_payload(self, task_id: str) -> dict[str, Any]:
        return self.task_manager.load_task(task_id).to_dict()

    def job_payload(self, job_id: str) -> dict[str, Any]:
        return self.job_manager.load_job(job_id).to_dict()

    def start_task(self, *, app_name: str, goal: str, max_steps: int, yolo_mode: bool) -> dict[str, Any]:
        self._assert_no_active_job()
        app = get_app_config(app_name)
        task = self.task_manager.create_task(
            app=app,
            device_serial=self.runtime.device_serial,
            goal=goal,
            yolo_mode=yolo_mode,
            step_budget=max_steps,
        )
        self.task_manager.mark_running(task)
        self.event_queue.append(
            "task_started",
            {"task_id": task.task_id, "app_name": task.app_name, "goal": task.goal, "device_serial": task.device_serial},
        )
        self._launch_task_thread(task)
        return {"accepted": True, "task": task.to_dict()}

    def start_session(self, *, app_name: str, goal: str, max_steps: int, yolo_mode: bool) -> dict[str, Any]:
        self._assert_no_active_job()
        app = get_app_config(app_name)
        with self._lock:
            self._active_job = SessionJob(
                job_type="session",
                app_name=app.name,
                goal=goal,
                device_serial=self.runtime.device_serial,
                started_at=time.time(),
                step_budget=max_steps,
                yolo_mode=yolo_mode,
            )
            self._last_job = self._active_job
        thread = threading.Thread(target=self._run_session, args=(app.name, goal, max_steps, yolo_mode), daemon=True)
        thread.start()
        return {"accepted": True, "session": self.active_job_payload()}

    def resume_task(self, *, task_id: str, max_steps: int | None, yolo_mode: bool | None) -> dict[str, Any]:
        self._assert_no_active_job()
        task = self.task_manager.load_task(task_id)
        if task.device_serial != self.runtime.device_serial:
            raise RuntimeError(
                f"Task '{task.task_id}' is bound to device {task.device_serial}, but the current runtime device is {self.runtime.device_serial}."
            )
        if not self.task_manager.can_resume(task):
            raise RuntimeError(f"Task '{task.task_id}' is not resumable from status '{task.status}'.")
        if max_steps is not None:
            task.step_budget = max_steps
        if yolo_mode is not None:
            task.yolo_mode = yolo_mode
        self.task_manager.save_task(task)
        self.task_manager.mark_running(task)
        self.event_queue.append(
            "task_started",
            {"task_id": task.task_id, "app_name": task.app_name, "goal": task.goal, "device_serial": task.device_serial},
        )
        self._launch_task_thread(task)
        return {"accepted": True, "task": task.to_dict()}

    def cancel_task(self, *, task_id: str) -> dict[str, Any]:
        with self._lock:
            if self._active_job and self._active_job.task_id == task_id and self._active_job.status == "running":
                raise RuntimeError("Cannot cancel a task while it is actively executing in the current session.")
        task = self.task_manager.cancel_task(task_id)
        self.event_queue.append("task_finished", {"task_id": task.task_id, "status": task.status, "reason": task.last_reason})
        return {"task": task.to_dict()}

    def create_job(
        self,
        *,
        name: str,
        app_name: str,
        goal: str,
        cron: str,
        max_steps: int,
        yolo_mode: bool,
    ) -> dict[str, Any]:
        job = self.job_manager.create_job(
            name=name,
            app=get_app_config(app_name),
            device_serial=self.runtime.device_serial,
            goal=goal,
            cron=cron,
            yolo_mode=yolo_mode,
            step_budget=max_steps,
        )
        return {"job": job.to_dict()}

    def update_job(
        self,
        *,
        job_id: str,
        name: str | None = None,
        goal: str | None = None,
        cron: str | None = None,
        max_steps: int | None = None,
        yolo_mode: bool | None = None,
        enabled: bool | None = None,
    ) -> dict[str, Any]:
        job = self.job_manager.update_job(
            job_id,
            name=name,
            goal=goal,
            cron=cron,
            step_budget=max_steps,
            yolo_mode=yolo_mode,
            enabled=enabled,
        )
        return {"job": job.to_dict()}

    def run_tool(self, *, tool_name: str, app_name: str | None, arguments: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._active_job and self._active_job.status == "running":
                raise RuntimeError("A task is currently running on this device. Wait for it to finish before direct control.")
        app = get_app_config(app_name) if app_name else None
        bundle = self.skill_manager.load_skill(app) if app else None
        current_state = None
        if tool_name in {"tap", "swipe", "run_script"}:
            current_state = self._capture_idle_state(force_refresh=True)
        with self.adapter.session_lock():
            result = self.tool_executor.execute(
                tool_name=tool_name,
                arguments=arguments,
                run_dir=self.session_run_dir,
                current_state=current_state,
                app=app,
                skill=bundle,
            )
            capture_error = None
            try:
                state = result.captured_state or (
                    self.adapter.capture_state(self.session_run_dir) if result.refresh_state else None
                )
            except Exception as exc:
                state = None
                capture_error = str(exc)
        if state is not None:
            with self._lock:
                self._idle_state = state
                self._idle_state_at = time.time()
        payload = {
            "tool_name": result.tool_name,
            "ok": result.ok,
            "output": result.output,
            "error": result.error,
            "captured_state": state.summary() if state else None,
        }
        if capture_error:
            payload["capture_error"] = capture_error
        return payload

    def device_state_payload(self) -> dict[str, Any]:
        error = None
        try:
            screen = self._current_state_summary()
        except Exception as exc:
            screen = None
            error = str(exc)
        return {
            "device_serial": self.runtime.device_serial,
            "screen": screen,
            "screen_error": error,
            "active_job": self.active_job_payload(),
        }

    def screenshot_bytes(self) -> tuple[bytes, str]:
        with self._lock:
            if self._active_job and self._active_job.latest_state:
                path = Path(str(self._active_job.latest_state.get("screenshot_path") or ""))
                if path.exists():
                    return (path.read_bytes(), "image/png")
            if self._idle_state and self._idle_state.screenshot_path.exists():
                return (self._idle_state.screenshot_path.read_bytes(), "image/png")
        state = self._capture_idle_state(force_refresh=False)
        if state is None or not state.screenshot_path.exists():
            raise RuntimeError("No screenshot is available yet.")
        return (state.screenshot_path.read_bytes(), "image/png")

    def _launch_task_thread(self, task: TaskRecord) -> None:
        with self._lock:
            if self._active_job and self._active_job.status == "running":
                raise RuntimeError("A task is already running on this device.")
            self._active_job = SessionJob(
                job_type="task",
                app_name=task.app_name,
                goal=task.goal,
                device_serial=task.device_serial,
                started_at=time.time(),
                task_id=task.task_id,
                step_budget=task.step_budget,
                yolo_mode=task.yolo_mode,
            )
            self._last_job = self._active_job
        thread = threading.Thread(target=self._run_task, args=(task.task_id,), daemon=True)
        thread.start()

    def _run_task(self, task_id: str) -> None:
        task = self.task_manager.load_task(task_id)
        context = self._build_context(task.app_name, task.goal, max_steps=task.step_budget, yolo_mode=task.yolo_mode)
        result = self._execute_run(context)
        task = self.task_manager.record_run_result(task, result)
        payload = self._build_payload(result, context, extra={
            "task_id": task.task_id,
            "task_status": task.status,
            "run_status": result.status,
            "total_steps": task.total_steps,
            "device_serial": task.device_serial,
            "app_name": task.app_name,
            "goal": task.goal,
            "completion_criteria": task.completion_criteria,
        })
        event_type = "task_finished" if task.status == "completed" else "task_blocked"
        self.event_queue.append(
            event_type,
            {"task_id": task.task_id, "status": task.status, "reason": result.reason, "run_dir": str(result.run_dir)},
        )
        with self._lock:
            if self._active_job and self._active_job.task_id == task.task_id:
                self._active_job.status = task.status
                self._active_job.last_reason = result.reason
                self._active_job.run_dir = str(result.run_dir)
                self._active_job.payload = payload
                self._last_job = self._active_job
                self._active_job = None

    def _run_session(self, app_name: str, goal: str, max_steps: int, yolo_mode: bool) -> None:
        context = self._build_context(app_name, goal, max_steps=max_steps, yolo_mode=yolo_mode)
        result = self._execute_run(context)
        payload = self._build_payload(result, context)
        with self._lock:
            if self._active_job and self._active_job.job_type == "session":
                self._active_job.status = result.status
                self._active_job.last_reason = result.reason
                self._active_job.run_dir = str(result.run_dir)
                self._active_job.payload = payload
                self._last_job = self._active_job
                self._active_job = None

    def _run_scheduled_job(self, job_id: str) -> None:
        job = self.job_manager.load_job(job_id)
        with self._lock:
            self._active_job = SessionJob(
                job_type="scheduled_job",
                app_name=job.app_name,
                goal=job.goal,
                device_serial=job.device_serial,
                started_at=time.time(),
                job_id=job.job_id,
                step_budget=job.step_budget,
                yolo_mode=job.yolo_mode,
            )
            self._last_job = self._active_job
        self.event_queue.append(
            "job_started",
            {"job_id": job.job_id, "name": job.name, "app_name": job.app_name, "goal": job.goal, "device_serial": job.device_serial},
        )
        context = self._build_context(job.app_name, job.goal, max_steps=job.step_budget, yolo_mode=job.yolo_mode)
        result = self._execute_run(context)
        job = self.job_manager.record_run_result(job, result)
        payload = self._build_payload(result, context, extra={"job_id": job.job_id, "job_name": job.name})
        self.event_queue.append(
            "job_finished",
            {
                "job_id": job.job_id,
                "name": job.name,
                "status": result.status,
                "reason": result.reason,
                "run_dir": str(result.run_dir),
            },
        )
        with self._lock:
            if self._active_job and self._active_job.job_id == job.job_id:
                self._active_job.status = result.status
                self._active_job.last_reason = result.reason
                self._active_job.run_dir = str(result.run_dir)
                self._active_job.payload = payload
                self._last_job = self._active_job
                self._active_job = None

    def _execute_run(self, context: RunContext) -> RunResult:
        orchestrator = Orchestrator(
            android_adapter=self.adapter,
            tool_executor=self.tool_executor,
            vision_agent=VisionAgent(
                self.runtime.gemini_api_key,
                self._active_model_name(),
                provider=self.model_provider,
                lmstudio_base_url=self.runtime.lmstudio_base_url,
                lmstudio_api_key=self.runtime.lmstudio_api_key,
            ),
            skill_manager=self.skill_manager,
            runs_dir=self.runtime.runs_dir,
            event_callback=self._handle_event,
        )
        try:
            return orchestrator.run(context)
        except Exception as exc:
            run_dir = context.run_dir if context.run_dir != Path(".") else self.session_run_dir
            return RunResult(status="error", reason=str(exc), steps=len(context.action_history), run_dir=run_dir)
        finally:
            self.adapter.close()

    def _build_context(self, app_name: str, goal: str, *, max_steps: int, yolo_mode: bool) -> RunContext:
        return RunContext(
            app=get_app_config(app_name),
            goal=goal,
            run_dir=Path("."),
            exploration_enabled=True,
            max_steps=max_steps,
            yolo_mode=yolo_mode,
        )

    def _build_payload(self, result: RunResult, context: RunContext, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = build_run_payload(
            result,
            context,
            extra={
                "context_log_path": str(result.run_dir / "agent_context.jsonl"),
                **(extra or {}),
            },
        )
        return payload

    def _handle_event(self, event: dict[str, Any]) -> None:
        enriched = {"timestamp": time.time(), **event}
        with self._lock:
            active = self._active_job
            if active is not None:
                active.events.append(enriched)
                if event.get("type") == "run_started":
                    active.run_dir = str(event.get("run_dir") or "")
                state = event.get("state")
                if isinstance(state, dict):
                    active.latest_state = state
                    self.event_queue.append(
                        "task_state",
                        {
                            "task_id": active.task_id,
                            "job_id": active.job_id,
                            "job_type": active.job_type,
                            "app_name": active.app_name,
                            "run_dir": active.run_dir,
                            "package_name": state.get("package_name"),
                            "activity_name": state.get("activity_name"),
                            "visible_text": list(state.get("visible_text") or [])[:10],
                            "screenshot_path": state.get("screenshot_path"),
                            "hierarchy_path": state.get("hierarchy_path"),
                        },
                    )

    def _handle_notification_event(self, event: dict[str, Any]) -> None:
        payload = {"timestamp": time.time(), **event}
        with self._lock:
            self._notifications.append(payload)
            self._notifications = self._notifications[-200:]
        event_type = str(event.get("event_type") or "")
        if event_type in {"notification_posted", "notification_removed"}:
            self.event_queue.append(event_type, payload)

    def _assert_no_active_job(self) -> None:
        with self._lock:
            if self._active_job and self._active_job.status == "running":
                raise RuntimeError("A task is already running on this device.")

    def _current_state_summary(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active_job and self._active_job.latest_state:
                return dict(self._active_job.latest_state)
        state = self._capture_idle_state(force_refresh=False)
        if state is None:
            return None
        summary = state.summary()
        summary["screenshot_path"] = str(state.screenshot_path)
        summary["hierarchy_path"] = str(state.hierarchy_path)
        return summary

    def _capture_idle_state(self, *, force_refresh: bool) -> ScreenState | None:
        with self._lock:
            if self._active_job and self._active_job.status == "running":
                return self._idle_state
            if not force_refresh and self._idle_state and (time.time() - self._idle_state_at) <= self.IDLE_CAPTURE_TTL_SECONDS:
                return self._idle_state
        with self.adapter.session_lock():
            state = self.adapter.capture_state(self.session_run_dir)
        with self._lock:
            self._idle_state = state
            self._idle_state_at = time.time()
        return state

    def _active_model_name(self) -> str:
        return self.lmstudio_model if self.model_provider == "lmstudio" else self.gemini_model

    def _scheduler_loop(self) -> None:
        while not self._scheduler_stop.is_set():
            try:
                due_jobs = self.job_manager.due_jobs(device_serial=self.runtime.device_serial)
                if due_jobs and not self._active_job:
                    try:
                        self.task_manager.ensure_device_available(self.runtime.device_serial)
                    except RuntimeError:
                        due_jobs = []
                    if due_jobs:
                        job = due_jobs[0]
                        thread = threading.Thread(target=self._run_scheduled_job, args=(job.job_id,), daemon=True)
                        thread.start()
            except Exception:
                pass
            self._scheduler_stop.wait(self.SCHEDULER_POLL_SECONDS)

    def _adb_status(self) -> str:
        command = [self.runtime.adb_path, "devices"]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
        except Exception:
            return "unavailable"
        return "connected" if self.runtime.device_serial in completed.stdout else "disconnected"

    def _appium_status(self) -> str:
        url = self.runtime.appium_url.rstrip("/") + "/status"
        try:
            with urlopen(url, timeout=3) as response:
                return "ready" if response.status == HTTPStatus.OK else "unavailable"
        except (URLError, TimeoutError, ValueError):
            return "unavailable"
