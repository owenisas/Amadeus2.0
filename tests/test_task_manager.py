from pathlib import Path

import pytest

from agent_runner.config import APP_REGISTRY
from agent_runner.models import RunResult
from agent_runner.task_manager import TaskManager


def test_task_manager_creates_and_persists_task(tmp_path: Path) -> None:
    manager = TaskManager(tmp_path / "tasks")

    task = manager.create_task(
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Open settings and inspect Wi-Fi.",
        yolo_mode=False,
        step_budget=5,
    )

    loaded = manager.load_task(task.task_id)

    assert loaded.task_id == task.task_id
    assert loaded.status == "ready"
    assert loaded.device_serial == "device-1"


def test_task_manager_enforces_one_open_task_per_device(tmp_path: Path) -> None:
    manager = TaskManager(tmp_path / "tasks")
    manager.create_task(
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Task A",
        yolo_mode=False,
        step_budget=5,
    )

    with pytest.raises(RuntimeError, match="already reserved"):
        manager.create_task(
            app=APP_REGISTRY["chrome"],
            device_serial="device-1",
            goal="Task B",
            yolo_mode=False,
            step_budget=5,
        )


def test_task_manager_maps_resume_states_from_run_result(tmp_path: Path) -> None:
    manager = TaskManager(tmp_path / "tasks")
    task = manager.create_task(
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Task A",
        yolo_mode=True,
        step_budget=4,
    )

    updated = manager.record_run_result(
        task,
        RunResult(
            status="manual_login_required",
            reason="Manual login required before automation can continue.",
            steps=1,
            run_dir=tmp_path / "runs" / "r1",
        ),
    )

    assert updated.status == "waiting_for_login"
    assert updated.total_steps == 1
    assert updated.checkpoints[-1]["run_status"] == "manual_login_required"


def test_task_manager_cancel_releases_device(tmp_path: Path) -> None:
    manager = TaskManager(tmp_path / "tasks")
    task = manager.create_task(
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Task A",
        yolo_mode=False,
        step_budget=5,
    )

    canceled = manager.cancel_task(task.task_id)

    assert canceled.status == "canceled"
    follow_up = manager.create_task(
        app=APP_REGISTRY["chrome"],
        device_serial="device-1",
        goal="Task B",
        yolo_mode=False,
        step_budget=5,
    )
    assert follow_up.task_id != task.task_id
