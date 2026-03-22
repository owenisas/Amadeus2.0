from agent_runner.cli import (
    _agent_response,
    _build_run_payload,
    _decision_log,
    _format_live_event,
    _model_errors,
    _runtime_error_payload,
    _simplify_action_history,
    _simplify_events,
    _state_snapshots,
    _tools_used,
    build_parser,
)
from agent_runner.models import ActionRecord, RunContext, RunResult
from agent_runner.config import APP_REGISTRY
from pathlib import Path


def test_cli_simplifies_actions_and_tools() -> None:
    history = [
        ActionRecord(
            step=1,
            action="tool",
            reason="Capture screen.",
            allowed=True,
            package_name="com.android.settings",
            activity_name=".MainSettings",
            tool_name="capture_state",
            tool_arguments={},
            tool_output={"screen": {}},
        ),
        ActionRecord(
            step=2,
            action="tap",
            reason="Open Wi-Fi.",
            allowed=True,
            package_name="com.android.settings",
            activity_name=".MainSettings",
        ),
    ]

    actions = _simplify_action_history(history)

    assert actions[0]["tool_name"] == "capture_state"
    assert actions[0]["tool_output_keys"] == ["screen"]
    assert _tools_used(history) == ["capture_state"]


def test_cli_builds_run_payload_with_agent_response() -> None:
    context = RunContext(
        app=APP_REGISTRY["settings"],
        goal="Open settings",
        run_dir=Path("."),
        exploration_enabled=True,
        max_steps=2,
    )
    context.action_history.append(
        ActionRecord(
            step=1,
            action="wait",
            reason="Wait for Settings to stabilize.",
            allowed=True,
            package_name="com.android.settings",
            activity_name=".MainSettings",
        )
    )
    result = RunResult(
        status="completed",
        reason="Settings is visible.",
        steps=1,
        run_dir=Path("runs/settings-1"),
    )

    payload = _build_run_payload(result, context)

    assert payload["agent_response"] == _agent_response(result, context.action_history)
    assert payload["actions"][0]["action"] == "wait"
    assert payload["tools_used"] == []


def test_cli_simplifies_decisions_and_state_events() -> None:
    events = [
        {
            "timestamp": 1.0,
            "type": "state_captured",
            "step": 0,
            "state": {
                "package_name": "com.android.settings",
                "activity_name": ".MainSettings",
                "visible_text": ["Settings", "Network & internet"],
                "clickable_text": ["Network & internet"],
                "screenshot_path": "runs/settings-1/step0.png",
                "hierarchy_path": "runs/settings-1/step0.xml",
            },
        },
        {
            "timestamp": 2.0,
            "type": "decision_made",
            "step": 1,
            "decision": {
                "next_action": "tap",
                "reason": "Open Wi-Fi settings.",
                "confidence": 0.9,
                "target_label": "Network & internet",
                "tool_name": None,
            },
            "decision_meta": {},
        },
    ]

    simplified = _simplify_events(events)
    decisions = _decision_log(events)
    snapshots = _state_snapshots(events)

    assert simplified[0]["type"] == "state_captured"
    assert simplified[1]["next_action"] == "tap"
    assert decisions == [
        {
            "step": 1,
            "next_action": "tap",
            "reason": "Open Wi-Fi settings.",
            "confidence": 0.9,
            "target_label": "Network & internet",
            "tool_name": None,
            "decision_source": None,
            "model_provider": None,
            "model_name": None,
            "status_code": None,
            "detail": None,
        }
    ]
    assert snapshots[0]["package_name"] == "com.android.settings"
    assert _model_errors(events) == []


def test_cli_formats_live_decision_event() -> None:
    line = _format_live_event(
        {
            "type": "decision_made",
            "step": 2,
            "decision": {
                "next_action": "tap",
                "target_label": "Take Survey",
                "reason": "Open the survey.",
            },
            "decision_meta": {
                "source": "heuristic_bypass",
                "provider": "lmstudio",
            },
        }
    )

    assert line is not None
    assert "source=heuristic_bypass" in line
    assert "provider=lmstudio" in line
    assert "action=tap" in line


def test_cli_includes_model_error_details_only_for_failures() -> None:
    events = [
        {
            "type": "decision_made",
            "step": 1,
            "decision": {
                "next_action": "wait",
                "reason": "LM Studio returned non-JSON content; heuristic fallback used.",
            },
            "decision_meta": {
                "source": "lmstudio_non_json_fallback",
                "provider": "lmstudio",
                "model": "qwen",
                "detail": "raw model prose",
            },
        }
    ]

    line = _format_live_event(events[0])

    assert line is not None
    assert "detail=raw model prose" in line
    assert _model_errors(events) == [
        {
            "step": 1,
            "source": "lmstudio_non_json_fallback",
            "provider": "lmstudio",
            "model": "qwen",
            "status_code": None,
            "detail": "raw model prose",
        }
    ]


def test_cli_formats_skill_write_tool_event() -> None:
    line = _format_live_event(
        {
            "type": "tool_executed",
            "step": 3,
            "tool_name": "write_skill_file",
            "ok": True,
            "output": {
                "app_name": "facebook",
                "file_name": "memory.md",
                "path": "/Users/user/Documents/Amadeus2.0/skills/apps/facebook/memory.md",
            },
        }
    )

    assert line is not None
    assert "tool=write_skill_file" in line
    assert "file=memory.md" in line
    assert "facebook/memory.md" in line


def test_cli_parser_supports_tui_command() -> None:
    parser = build_parser()

    args = parser.parse_args(["tui"])

    assert args.command == "tui"


def test_cli_runtime_error_payload_includes_run_dir_and_hint() -> None:
    payload = _runtime_error_payload(
        reason="Appium server is unavailable at http://127.0.0.1:4723. Start Appium and retry.",
        run_dir=Path("runs/settings-1"),
        appium_start_hint='export ANDROID_SDK_ROOT="/sdk" ANDROID_HOME="/sdk" && appium',
    )

    assert payload["status"] == "error"
    assert payload["run_dir"] == "runs/settings-1"
    assert "appium" in payload["appium_start_hint"]
