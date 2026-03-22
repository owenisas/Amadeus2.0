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

    def infer_app_name(self):
        return "settings"

    def start_session(self, **kwargs):
        self.calls.append(("start_session", kwargs))
        return {"accepted": True}

    def start_task(self, **kwargs):
        self.calls.append(("start_task", kwargs))
        return {"accepted": True}

    def interrupt_active_job(self):
        self.calls.append(("interrupt_active_job", {}))
        return {"accepted": True, "interrupt_requested": True}

    def create_job(self, **kwargs):
        self.calls.append(("create_job", kwargs))
        return {"job": kwargs}

    def update_model_settings(self, **kwargs):
        self.calls.append(("update_model_settings", kwargs))
        provider = kwargs["model_provider"]
        model_name = kwargs.get("lmstudio_model") or kwargs.get("gemini_model") or "unchanged"
        return {
            "model_provider": provider,
            "vision_model": model_name,
            "gemini_model": kwargs.get("gemini_model") or "gemini-test",
            "lmstudio_model": kwargs.get("lmstudio_model") or "local-model",
        }


def test_tui_run_command_uses_ad_hoc_session() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    response = app._execute_command("/run settings | Open Wi-Fi")

    assert response["accepted"] is True
    assert controller.calls == [
        ("start_session", {"app_name": "settings", "goal": "Open Wi-Fi", "max_steps": 12, "yolo_mode": False})
    ]


def test_tui_job_add_command_creates_job() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    response = app._execute_command("/job add Nightly scan | */15 * * * * | settings | Inspect Wi-Fi")

    assert response["job"]["name"] == "Nightly scan"
    assert controller.calls[0][0] == "create_job"


def test_tui_plain_text_submits_direct_prompt() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    response = app._execute_command("Open Wi-Fi and inspect the current page")

    assert response["accepted"] is True
    assert controller.calls == [
        (
            "start_session",
            {
                "app_name": "settings",
                "goal": "Open Wi-Fi and inspect the current page",
                "max_steps": 12,
                "yolo_mode": False,
            },
        )
    ]


def test_tui_app_command_pins_direct_prompt_context() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    response = app._execute_command("/app facebook")

    assert response == {"preferred_app_name": "facebook"}
    assert app._preferred_app_name == "facebook"


def test_tui_toggles_apply_to_direct_prompt_and_task() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    assert app._execute_command("/yolo on") == {"yolo_mode": True}
    assert app._execute_command("/infinite toggle") == {"infinite_mode": True, "max_steps": 0}
    response = app._execute_command("/task settings | Open Wi-Fi")

    assert response["accepted"] is True
    assert controller.calls == [
        ("start_task", {"app_name": "settings", "goal": "Open Wi-Fi", "max_steps": 0, "yolo_mode": True})
    ]


def test_tui_interrupt_command_requests_active_job_stop() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    response = app._execute_command("/interrupt")

    assert response["interrupt_requested"] is True
    assert controller.calls == [("interrupt_active_job", {})]


def test_tui_model_command_switches_to_lmstudio() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    response = app._execute_command("/model lmstudio qwen-test")

    assert response["model_provider"] == "lmstudio"
    assert response["vision_model"] == "qwen-test"
    assert controller.calls == [
        ("update_model_settings", {"model_provider": "lmstudio", "lmstudio_model": "qwen-test"})
    ]


def test_tui_hint_mentions_model_command() -> None:
    controller = FakeController()
    app = AgentSessionTui(controller)

    hint = app._hint_for("")

    assert "/model" in hint
