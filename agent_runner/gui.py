from __future__ import annotations

import json
import mimetypes
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent_runner.android_adapter import AndroidAdapter
from agent_runner.agent_tools import AgentToolExecutor
from agent_runner.config import get_app_config, list_app_configs
from agent_runner.models import RunContext, ScreenState, TaskRecord
from agent_runner.orchestrator import Orchestrator
from agent_runner.run_payload import build_run_payload
from agent_runner.session_controller import SessionController, SessionJob
from agent_runner.skill_manager import SkillManager
from agent_runner.task_manager import TaskManager
from agent_runner.utils import ensure_directory
from agent_runner.vision_agent import VisionAgent


ASSETS_DIR = Path(__file__).resolve().parent / "gui_assets"


@dataclass(slots=True)
class GuiJob:
    job_type: str
    app_name: str
    goal: str
    device_serial: str
    started_at: float
    status: str = "running"
    task_id: str | None = None
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
            "step_budget": self.step_budget,
            "yolo_mode": self.yolo_mode,
            "run_dir": self.run_dir,
            "last_reason": self.last_reason,
            "latest_state": self.latest_state,
            "payload": self.payload,
            "events": self.events[-50:],
        }


class DashboardRuntime:
    IDLE_CAPTURE_TTL_SECONDS = 2.0

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
        self.gui_run_dir = ensure_directory(runtime.runs_dir / "gui-live")
        self._lock = threading.RLock()
        self._active_job: GuiJob | None = None
        self._last_job: GuiJob | None = None
        self._idle_state: ScreenState | None = None
        self._idle_state_at: float = 0.0

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

    def active_job_payload(self) -> dict[str, Any] | None:
        with self._lock:
            if self._active_job is not None:
                return self._active_job.to_dict()
            if self._last_job is not None:
                return self._last_job.to_dict()
        return None

    def task_payload(self, task_id: str) -> dict[str, Any]:
        return self.task_manager.load_task(task_id).to_dict()

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
        self._launch_task_thread(task)
        return {"accepted": True, "task": task.to_dict()}

    def resume_task(self, *, task_id: str, max_steps: int | None, yolo_mode: bool | None) -> dict[str, Any]:
        self._assert_no_active_job()
        task = self.task_manager.load_task(task_id)
        if task.device_serial != self.runtime.device_serial:
            raise RuntimeError(
                f"Task '{task.task_id}' is bound to device {task.device_serial}, "
                f"but the current runtime device is {self.runtime.device_serial}."
            )
        if not self.task_manager.can_resume(task):
            raise RuntimeError(f"Task '{task.task_id}' is not resumable from status '{task.status}'.")
        if max_steps:
            task.step_budget = max_steps
        if yolo_mode is not None:
            task.yolo_mode = yolo_mode
        self.task_manager.save_task(task)
        self.task_manager.mark_running(task)
        self._launch_task_thread(task)
        return {"accepted": True, "task": task.to_dict()}

    def cancel_task(self, *, task_id: str) -> dict[str, Any]:
        with self._lock:
            if self._active_job and self._active_job.task_id == task_id and self._active_job.status == "running":
                raise RuntimeError("Cannot cancel a task while it is actively executing in the GUI session.")
        task = self.task_manager.cancel_task(task_id)
        return {"task": task.to_dict()}

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
                run_dir=self.gui_run_dir,
                current_state=current_state,
                app=app,
                skill=bundle,
            )
            capture_error = None
            try:
                state = result.captured_state or (
                    self.adapter.capture_state(self.gui_run_dir) if result.refresh_state else None
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
            self._active_job = GuiJob(
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
        context = RunContext(
            app=get_app_config(task.app_name),
            goal=task.goal,
            run_dir=Path("."),
            exploration_enabled=True,
            max_steps=task.step_budget,
            yolo_mode=task.yolo_mode,
        )
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
            result = orchestrator.run(context)
            task = self.task_manager.record_run_result(task, result)
            payload = build_run_payload(
                result,
                context,
                extra={
                    "task_id": task.task_id,
                    "task_status": task.status,
                    "run_status": result.status,
                    "total_steps": task.total_steps,
                    "device_serial": task.device_serial,
                    "app_name": task.app_name,
                    "goal": task.goal,
                    "completion_criteria": task.completion_criteria,
                },
            )
            with self._lock:
                if self._active_job and self._active_job.task_id == task.task_id:
                    self._active_job.status = task.status
                    self._active_job.last_reason = result.reason
                    self._active_job.run_dir = str(result.run_dir)
                    self._active_job.payload = payload
                    self._last_job = self._active_job
                    self._active_job = None
        except Exception as exc:
            task.status = "error"
            task.last_reason = str(exc)
            task.checkpoints.append(
                {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "task_status": "error",
                    "reason": str(exc),
                }
            )
            self.task_manager.save_task(task)
            with self._lock:
                if self._active_job and self._active_job.task_id == task.task_id:
                    self._active_job.status = "error"
                    self._active_job.last_reason = str(exc)
                    self._last_job = self._active_job
                    self._active_job = None
        finally:
            self.adapter.close()

    def _handle_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            if self._active_job is None:
                return
            self._active_job.events.append({"timestamp": time.time(), **event})
            if event.get("type") == "run_started":
                self._active_job.run_dir = str(event.get("run_dir") or "")
            state = event.get("state")
            if isinstance(state, dict):
                self._active_job.latest_state = state

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
            state = self.adapter.capture_state(self.gui_run_dir)
        with self._lock:
            self._idle_state = state
            self._idle_state_at = time.time()
        return state

    def _active_model_name(self) -> str:
        return self.lmstudio_model if self.model_provider == "lmstudio" else self.gemini_model


GuiJob = SessionJob
DashboardRuntime = SessionController


def serve_gui(runtime, *, host: str, port: int, open_browser: bool) -> None:
    dashboard = DashboardRuntime(runtime)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/":
                self._serve_asset("index.html")
                return
            if path.startswith("/assets/"):
                self._serve_asset(path.removeprefix("/assets/"))
                return
            if path == "/api/runtime":
                self._send_json(dashboard.runtime_payload())
                return
            if path == "/api/apps":
                self._send_json(dashboard.apps_payload())
                return
            if path == "/api/tools":
                self._send_json(dashboard.tools_payload())
                return
            if path == "/api/tasks":
                self._send_json(dashboard.tasks_payload())
                return
            if path.startswith("/api/tasks/"):
                task_id = path.removeprefix("/api/tasks/")
                self._send_json(dashboard.task_payload(task_id))
                return
            if path == "/api/device/state":
                self._send_json(dashboard.device_state_payload())
                return
            if path == "/api/device/screenshot":
                try:
                    data, content_type = dashboard.screenshot_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", content_type)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, status=HTTPStatus.SERVICE_UNAVAILABLE)
                return
            if path == "/api/job":
                self._send_json(dashboard.active_job_payload())
                return
            self._send_json({"error": f"Unknown path '{path}'."}, status=HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            try:
                payload = self._read_json()
                if path == "/api/tasks/start":
                    response = dashboard.start_task(
                        app_name=str(payload["app_name"]),
                        goal=str(payload["goal"]),
                        max_steps=int(payload.get("max_steps", 12)),
                        yolo_mode=bool(payload.get("yolo_mode", False)),
                    )
                    self._send_json(response, status=HTTPStatus.ACCEPTED)
                    return
                if path.startswith("/api/tasks/") and path.endswith("/resume"):
                    task_id = path.removeprefix("/api/tasks/").removesuffix("/resume").rstrip("/")
                    raw_yolo = payload.get("yolo_mode", None)
                    response = dashboard.resume_task(
                        task_id=task_id,
                        max_steps=int(payload["max_steps"]) if payload.get("max_steps") else None,
                        yolo_mode=(bool(raw_yolo) if raw_yolo is not None else None),
                    )
                    self._send_json(response, status=HTTPStatus.ACCEPTED)
                    return
                if path.startswith("/api/tasks/") and path.endswith("/cancel"):
                    task_id = path.removeprefix("/api/tasks/").removesuffix("/cancel").rstrip("/")
                    self._send_json(dashboard.cancel_task(task_id=task_id))
                    return
                if path == "/api/tools/run":
                    response = dashboard.run_tool(
                        tool_name=str(payload["tool_name"]),
                        app_name=(str(payload["app_name"]) if payload.get("app_name") else None),
                        arguments=dict(payload.get("arguments") or {}),
                    )
                    self._send_json(response)
                    return
                if path == "/api/settings/model":
                    response = dashboard.update_model_settings(
                        model_provider=str(payload["model_provider"]),
                        gemini_model=(str(payload["gemini_model"]) if payload.get("gemini_model") else None),
                        lmstudio_model=(str(payload["lmstudio_model"]) if payload.get("lmstudio_model") else None),
                    )
                    self._send_json(response)
                    return
            except Exception as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
                return
            self._send_json({"error": f"Unknown path '{path}'."}, status=HTTPStatus.NOT_FOUND)

        def log_message(self, format: str, *args: object) -> None:
            return

        def _send_json(self, payload: Any, *, status: HTTPStatus = HTTPStatus.OK) -> None:
            data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except BrokenPipeError:
                return

        def _read_json(self) -> dict[str, Any]:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
            return json.loads(raw.decode("utf-8") or "{}")

        def _serve_asset(self, asset_name: str) -> None:
            if not asset_name:
                asset_name = "index.html"
            path = (ASSETS_DIR / asset_name).resolve()
            if not str(path).startswith(str(ASSETS_DIR.resolve())) or not path.exists():
                self._send_json({"error": f"Asset '{asset_name}' not found."}, status=HTTPStatus.NOT_FOUND)
                return
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            data = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer((host, port), Handler)
    url = f"http://{host}:{port}"
    print(f"Agent Runner GUI listening at {url}")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
