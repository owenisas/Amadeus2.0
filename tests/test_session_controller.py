import time
from pathlib import Path
from types import MethodType, SimpleNamespace

from agent_runner.config import APP_REGISTRY
from agent_runner.session_controller import SessionController


def _runtime(tmp_path: Path):
    return SimpleNamespace(
        appium_url="http://127.0.0.1:4723",
        device_serial="device-1",
        adb_path="/tmp/adb",
        android_sdk_root="/tmp/sdk",
        skills_dir=tmp_path / "skills",
        system_skill_file=tmp_path / "skills" / "system" / "SKILL.md",
        runs_dir=tmp_path / "runs",
        model_provider="gemini",
        model_name="gemini-test",
        gemini_model="gemini-test",
        gemini_api_key=None,
        lmstudio_api_key=None,
        lmstudio_model="local-model",
        lmstudio_base_url="http://127.0.0.1:1234/v1",
    )


def test_scheduler_defers_due_jobs_while_device_reserved(tmp_path: Path) -> None:
    controller = SessionController(_runtime(tmp_path))
    controller.SCHEDULER_POLL_SECONDS = 0.05
    invoked: list[str] = []

    def fake_run(self, job_id: str) -> None:
        invoked.append(job_id)

    controller._run_scheduled_job = MethodType(fake_run, controller)
    job = controller.job_manager.create_job(
        name="Nightly",
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Inspect Wi-Fi.",
        cron="*/15 * * * *",
        yolo_mode=False,
        step_budget=3,
    )
    persisted = controller.job_manager.load_job(job.job_id)
    persisted.next_run_at = "2026-03-22T00:00:00"
    controller.job_manager.save_job(persisted)
    controller.task_manager.create_task(
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Hold device lock",
        yolo_mode=False,
        step_budget=2,
    )

    controller.start_background_services(scheduler=True, notifications=False)
    time.sleep(0.2)
    controller.stop_background_services()

    assert invoked == []
