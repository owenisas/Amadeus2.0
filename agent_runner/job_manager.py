from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

from croniter import croniter

from agent_runner.models import AppConfig, JobRecord, RunResult
from agent_runner.utils import dump_json, ensure_directory, load_json, slugify, timestamp_slug


class JobManager:
    def __init__(self, jobs_root: Path) -> None:
        self.jobs_root = ensure_directory(jobs_root)

    def create_job(
        self,
        *,
        name: str,
        app: AppConfig,
        device_serial: str,
        goal: str,
        cron: str,
        yolo_mode: bool,
        step_budget: int,
    ) -> JobRecord:
        now = self._now()
        job_id = f"{app.name}-{slugify(name)[:32]}-{timestamp_slug()}"
        job = JobRecord(
            job_id=job_id,
            name=name,
            device_serial=device_serial,
            app_name=app.name,
            goal=goal,
            cron=cron,
            yolo_mode=yolo_mode,
            step_budget=step_budget,
            enabled=True,
            created_at=now,
            updated_at=now,
            next_run_at=self.compute_next_run_at(cron, now),
        )
        self.save_job(job)
        return job

    def load_job(self, job_id: str) -> JobRecord:
        payload = load_json(self._job_path(job_id), default=None)
        if payload is None:
            raise FileNotFoundError(f"Job '{job_id}' was not found.")
        return JobRecord.from_dict(payload)

    def save_job(self, job: JobRecord) -> Path:
        job.updated_at = self._now()
        path = self._job_path(job.job_id)
        dump_json(path, job.to_dict())
        return path

    def list_jobs(self, *, device_serial: str | None = None) -> list[JobRecord]:
        jobs: list[JobRecord] = []
        for path in sorted(self.jobs_root.glob("*.json")):
            payload = load_json(path, default=None)
            if payload is None:
                continue
            job = JobRecord.from_dict(payload)
            if device_serial and job.device_serial != device_serial:
                continue
            jobs.append(job)
        jobs.sort(key=lambda item: item.updated_at, reverse=True)
        return jobs

    def update_job(
        self,
        job_id: str,
        *,
        name: str | None = None,
        goal: str | None = None,
        cron: str | None = None,
        step_budget: int | None = None,
        yolo_mode: bool | None = None,
        enabled: bool | None = None,
    ) -> JobRecord:
        job = self.load_job(job_id)
        if name is not None:
            job.name = name
        if goal is not None:
            job.goal = goal
        if cron is not None:
            job.cron = cron
            job.next_run_at = self.compute_next_run_at(cron, self._now())
        if step_budget is not None:
            job.step_budget = step_budget
        if yolo_mode is not None:
            job.yolo_mode = yolo_mode
        if enabled is not None:
            job.enabled = enabled
        self.save_job(job)
        return job

    def due_jobs(self, *, device_serial: str | None = None, now: str | None = None) -> list[JobRecord]:
        due_at = self._parse_timestamp(now or self._now())
        jobs = []
        for job in self.list_jobs(device_serial=device_serial):
            if not job.enabled or not job.next_run_at:
                continue
            if self._parse_timestamp(job.next_run_at) <= due_at:
                jobs.append(job)
        jobs.sort(key=lambda item: item.next_run_at or "")
        return jobs

    def record_run_result(self, job: JobRecord, result: RunResult, *, now: str | None = None) -> JobRecord:
        current = now or self._now()
        job.last_run_at = current
        job.last_result_status = result.status
        job.last_result_reason = result.reason
        job.next_run_at = self.compute_next_run_at(job.cron, current)
        self.save_job(job)
        return job

    def compute_next_run_at(self, cron: str, reference_timestamp: str) -> str:
        base = self._parse_timestamp(reference_timestamp)
        next_run = croniter(cron, base).get_next(datetime)
        return next_run.strftime("%Y-%m-%dT%H:%M:%S")

    def _job_path(self, job_id: str) -> Path:
        return self.jobs_root / f"{job_id}.json"

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%S")

    def _parse_timestamp(self, value: str) -> datetime:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
