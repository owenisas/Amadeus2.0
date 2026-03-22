from types import SimpleNamespace

from agent_runner.tui import AgentSessionTui


class FakeController:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def start_background_services(self, **kwargs):
        return None

    def close(self):
        return None

    def runtime_payload(self):
        return {
            "device_serial": "device-1",
            "model_provider": "gemini",
            "vision_model": "gemini-test",
            "adb_status": "connected",
            "appium_status": "ready",
            "notification_listener_enabled": False,
            "active_job": None,
        }

    def tasks_payload(self):
        return []

    def jobs_payload(self):
        return []

    def notifications_payload(self, **kwargs):
        return []

    def device_state_payload(self):
        return {"screen": None}

    def active_job_payload(self):
        return None

    def start_session(self, **kwargs):
        self.calls.append(("start_session", kwargs))
        return {"accepted": True}

    def create_job(self, **kwargs):
        self.calls.append(("create_job", kwargs))
        return {"job": kwargs}


def test_tui_run_command_uses_ad_hoc_session() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    response = app._execute_command("run settings | Open Wi-Fi")

    assert response["accepted"] is True
    assert controller.calls == [
        ("start_session", {"app_name": "settings", "goal": "Open Wi-Fi", "max_steps": 12, "yolo_mode": False})
    ]


def test_tui_job_add_command_creates_job() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    response = app._execute_command("job add Nightly scan | */15 * * * * | settings | Inspect Wi-Fi")

    assert response["job"]["name"] == "Nightly scan"
    assert controller.calls[0][0] == "create_job"
