from pathlib import Path

from agent_runner.config import APP_REGISTRY
from agent_runner.job_manager import JobManager
from agent_runner.models import RunResult


def test_job_manager_creates_job_with_next_run(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "jobs")

    job = manager.create_job(
        name="Nightly scan",
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Inspect Wi-Fi.",
        cron="*/15 * * * *",
        yolo_mode=True,
        step_budget=4,
    )

    assert job.job_id
    assert job.next_run_at is not None
    assert manager.load_job(job.job_id).goal == "Inspect Wi-Fi."


def test_job_manager_lists_due_jobs(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "jobs")
    job = manager.create_job(
        name="Frequent",
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Inspect Wi-Fi.",
        cron="*/15 * * * *",
        yolo_mode=False,
        step_budget=3,
    )
    manager.update_job(job.job_id, cron="*/15 * * * *")
    persisted = manager.load_job(job.job_id)
    persisted.next_run_at = "2026-03-22T00:00:00"
    manager.save_job(persisted)

    due = manager.due_jobs(device_serial="device-1", now="2026-03-22T00:16:00")

    assert [item.job_id for item in due] == [job.job_id]


def test_job_manager_records_run_result_and_rolls_next_run(tmp_path: Path) -> None:
    manager = JobManager(tmp_path / "jobs")
    job = manager.create_job(
        name="Frequent",
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Inspect Wi-Fi.",
        cron="*/15 * * * *",
        yolo_mode=False,
        step_budget=3,
    )

    updated = manager.record_run_result(
        job,
        RunResult(status="completed", reason="Done", steps=2, run_dir=tmp_path / "runs" / "x"),
        now="2026-03-22T00:16:00",
    )

    assert updated.last_result_status == "completed"
    assert updated.last_result_reason == "Done"
    assert updated.next_run_at == "2026-03-22T00:30:00"
