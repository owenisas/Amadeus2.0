import time
import threading
from pathlib import Path
from types import MethodType, SimpleNamespace

from agent_runner.config import APP_REGISTRY
from agent_runner.models import RunResult
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


def test_ensure_appium_running_skips_start_when_ready(tmp_path: Path, monkeypatch) -> None:
    controller = SessionController(_runtime(tmp_path))
    monkeypatch.setattr(controller, "_appium_status", lambda: "ready")

    payload = controller.ensure_appium_running()

    assert payload["status"] == "ready"
    assert payload["started"] is False


def test_ensure_appium_running_starts_process_when_unavailable(tmp_path: Path, monkeypatch) -> None:
    controller = SessionController(_runtime(tmp_path))
    statuses = iter(["unavailable", "unavailable", "ready"])
    monkeypatch.setattr(controller, "_appium_status", lambda: next(statuses))
    monkeypatch.setattr("agent_runner.session_controller.shutil.which", lambda name: "/opt/homebrew/bin/appium")

    class FakeProcess:
        def poll(self):
            return None

    spawned: list[list[str]] = []

    def fake_popen(command, **kwargs):
        spawned.append(command)
        return FakeProcess()

    monkeypatch.setattr("agent_runner.session_controller.subprocess.Popen", fake_popen)

    payload = controller.ensure_appium_running(force=True)

    assert payload["started"] is True
    assert spawned == [["/opt/homebrew/bin/appium"]]


def test_interrupt_active_session_requests_stop(tmp_path: Path) -> None:
    controller = SessionController(_runtime(tmp_path))
    started = threading.Event()
    finished = threading.Event()

    def fake_execute_run(self, context):
        started.set()
        deadline = time.time() + 1.0
        while context.should_stop is None or not context.should_stop():
            if time.time() > deadline:
                raise AssertionError("session was not interrupted")
            time.sleep(0.01)
        finished.set()
        return RunResult(
            status="canceled",
            reason="Run interrupted by user.",
            steps=0,
            run_dir=tmp_path / "runs" / "session-1",
        )

    controller._execute_run = MethodType(fake_execute_run, controller)

    controller.start_session(app_name="settings", goal="Open Wi-Fi", max_steps=12, yolo_mode=False)
    assert started.wait(1.0) is True

    payload = controller.interrupt_active_job()

    assert payload["interrupt_requested"] is True
    assert finished.wait(1.0) is True

    deadline = time.time() + 1.0
    while time.time() < deadline:
        active = controller.active_job_payload()
        if active and active["status"] == "canceled":
            break
        time.sleep(0.01)
    assert controller.active_job_payload()["status"] == "canceled"
