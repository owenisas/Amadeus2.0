from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_runner.config import APP_REGISTRY
from agent_runner.gui import DashboardRuntime, GuiJob


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


def test_dashboard_runtime_rejects_cancel_for_active_task(tmp_path: Path) -> None:
    dashboard = DashboardRuntime(_runtime(tmp_path))
    task = dashboard.task_manager.create_task(
        app=APP_REGISTRY["settings"],
        device_serial="device-1",
        goal="Inspect Settings.",
        yolo_mode=False,
        step_budget=4,
    )
    dashboard._active_job = GuiJob(
        job_type="task",
        app_name="settings",
        goal=task.goal,
        device_serial="device-1",
        started_at=0.0,
        status="running",
        task_id=task.task_id,
    )

    with pytest.raises(RuntimeError, match="actively executing"):
        dashboard.cancel_task(task_id=task.task_id)


def test_dashboard_runtime_updates_model_settings(tmp_path: Path) -> None:
    dashboard = DashboardRuntime(_runtime(tmp_path))

    payload = dashboard.update_model_settings(
        model_provider="lmstudio",
        lmstudio_model="qwen-test",
    )

    assert payload["model_provider"] == "lmstudio"
    assert payload["vision_model"] == "qwen-test"
    assert payload["lmstudio_model"] == "qwen-test"
