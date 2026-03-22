from __future__ import annotations

import time
from pathlib import Path

from agent_runner.models import AppConfig, RunResult, TaskRecord
from agent_runner.utils import dump_json, ensure_directory, load_json, slugify, timestamp_slug


TERMINAL_TASK_STATUSES = {"completed", "blocked", "error", "canceled"}
OPEN_TASK_STATUSES = {
    "ready",
    "running",
    "ready_to_resume",
    "waiting_for_login",
    "waiting_for_verification",
    "waiting_for_manual",
}


class TaskManager:
    def __init__(self, tasks_root: Path) -> None:
        self.tasks_root = ensure_directory(tasks_root)

    def create_task(
        self,
        *,
        app: AppConfig,
        device_serial: str,
        goal: str,
        yolo_mode: bool,
        step_budget: int,
    ) -> TaskRecord:
        self.ensure_device_available(device_serial)
        now = self._now()
        task_id = f"{app.name}-{slugify(goal)[:40]}-{timestamp_slug()}"
        task = TaskRecord(
            task_id=task_id,
            app_name=app.name,
            device_serial=device_serial,
            goal=goal,
            status="ready",
            created_at=now,
            updated_at=now,
            yolo_mode=yolo_mode,
            step_budget=step_budget,
            completion_criteria=[
                f"Complete the requested goal: {goal}",
                "Continue across repeated runs until the agent reports completed or a terminal error occurs.",
                "Pause and resume when login, verification, manual takeover, or step-budget boundaries are reached.",
            ],
        )
        self.save_task(task)
        return task

    def load_task(self, task_id: str) -> TaskRecord:
        payload = load_json(self._task_path(task_id), default=None)
        if payload is None:
            raise FileNotFoundError(f"Task '{task_id}' was not found.")
        return TaskRecord.from_dict(payload)

    def save_task(self, task: TaskRecord) -> Path:
        task.updated_at = self._now()
        path = self._task_path(task.task_id)
        dump_json(path, task.to_dict())
        return path

    def list_tasks(self, *, device_serial: str | None = None) -> list[TaskRecord]:
        tasks: list[TaskRecord] = []
        for path in sorted(self.tasks_root.glob("*.json")):
            payload = load_json(path, default=None)
            if payload is None:
                continue
            task = TaskRecord.from_dict(payload)
            if device_serial and task.device_serial != device_serial:
                continue
            tasks.append(task)
        tasks.sort(key=lambda item: item.updated_at, reverse=True)
        return tasks

    def cancel_task(self, task_id: str) -> TaskRecord:
        task = self.load_task(task_id)
        task.status = "canceled"
        task.last_reason = "Task canceled by user."
        task.checkpoints.append(
            {
                "timestamp": self._now(),
                "task_status": task.status,
                "reason": task.last_reason,
            }
        )
        self.save_task(task)
        return task

    def mark_running(self, task: TaskRecord) -> TaskRecord:
        self.ensure_device_available(task.device_serial, allow_task_id=task.task_id)
        task.status = "running"
        self.save_task(task)
        return task

    def can_resume(self, task: TaskRecord) -> bool:
        return task.status in OPEN_TASK_STATUSES

    def ensure_device_available(self, device_serial: str, *, allow_task_id: str | None = None) -> None:
        for task in self.list_tasks(device_serial=device_serial):
            if task.task_id == allow_task_id:
                continue
            if task.status in OPEN_TASK_STATUSES:
                raise RuntimeError(
                    f"Device {device_serial} is already reserved by task '{task.task_id}' with status '{task.status}'."
                )

    def record_run_result(self, task: TaskRecord, result: RunResult) -> TaskRecord:
        task.status = self._map_run_status(result.status)
        task.total_steps += result.steps
        task.last_reason = result.reason
        task.last_run_dir = str(result.run_dir)
        task.checkpoints.append(
            {
                "timestamp": self._now(),
                "run_status": result.status,
                "task_status": task.status,
                "reason": result.reason,
                "steps": result.steps,
                "run_dir": str(result.run_dir),
                "package_name": result.last_state.package_name if result.last_state else None,
                "activity_name": result.last_state.activity_name if result.last_state else None,
            }
        )
        self.save_task(task)
        return task

    def _map_run_status(self, run_status: str) -> str:
        if run_status == "completed":
            return "completed"
        if run_status == "manual_login_required":
            return "waiting_for_login"
        if run_status == "manual_verification_required":
            return "waiting_for_verification"
        if run_status in {"approval_required", "paused_for_manual"}:
            return "waiting_for_manual"
        if run_status in {"max_steps_reached", "stalled"}:
            return "ready_to_resume"
        if run_status in {"blocked", "error"}:
            return run_status
        return "ready_to_resume"

    def _task_path(self, task_id: str) -> Path:
        return self.tasks_root / f"{task_id}.json"

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")
