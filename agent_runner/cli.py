from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from agent_runner.android_adapter import AndroidAdapter
from agent_runner.agent_tools import AgentToolExecutor
from agent_runner.config import get_app_config, list_app_configs, load_runtime_config
from agent_runner.models import RunContext
from agent_runner.orchestrator import Orchestrator
from agent_runner.run_payload import (
    agent_response,
    build_run_payload,
    decision_log,
    model_errors,
    simplify_action_history,
    simplify_events,
    state_snapshots,
    tools_used,
)
from agent_runner.skill_manager import SkillManager
from agent_runner.task_manager import TaskManager
from agent_runner.utils import dump_json, ensure_directory
from agent_runner.vision_agent import VisionAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent_runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run an app automation workflow.")
    run_parser.add_argument("--app", required=True, help="App registry key, for example amazon.")
    run_parser.add_argument("--goal", required=True, help="Natural-language goal for the agent.")
    run_parser.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Maximum number of agent steps. Use 0 for unbounded runs.",
    )
    run_parser.add_argument(
        "--yolo",
        action="store_true",
        help="Run without interactive approval prompts. Existing hard safety blocks still apply.",
    )

    doctor_parser = subparsers.add_parser("doctor", help="Print local runtime configuration.")
    doctor_parser.add_argument("--json", action="store_true", help="Return machine-readable output.")

    app_parser = subparsers.add_parser("app", help="Inspect the registered app catalog.")
    app_subparsers = app_parser.add_subparsers(dest="app_command", required=True)
    app_list = app_subparsers.add_parser("list", help="List registered apps.")
    app_list.add_argument("--json", action="store_true", help="Return machine-readable output.")

    gui_parser = subparsers.add_parser("gui", help="Start a local web UI for device control and task monitoring.")
    gui_parser.add_argument("--host", default="127.0.0.1", help="Bind host. Default: 127.0.0.1")
    gui_parser.add_argument("--port", type=int, default=8765, help="Bind port. Default: 8765")
    gui_parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the dashboard in the default browser after the server starts.",
    )

    subparsers.add_parser("tui", help="Start the terminal UI for continuous sessions, jobs, and notifications.")

    task_parser = subparsers.add_parser("task", help="Manage persistent multi-run tasks.")
    task_subparsers = task_parser.add_subparsers(dest="task_command", required=True)

    task_start = task_subparsers.add_parser("start", help="Create and run a new persistent task.")
    task_start.add_argument("--app", required=True, help="App registry key, for example amazon.")
    task_start.add_argument("--goal", required=True, help="Natural-language goal for the task.")
    task_start.add_argument(
        "--max-steps",
        type=int,
        default=12,
        help="Maximum number of agent steps per run segment. Use 0 for unbounded segments.",
    )
    task_start.add_argument(
        "--yolo",
        action="store_true",
        help="Run without interactive approval prompts. Existing hard safety blocks still apply.",
    )

    task_resume = task_subparsers.add_parser("resume", help="Resume an existing persistent task.")
    task_resume.add_argument("--task-id", required=True, help="Task identifier returned by task start/list/show.")
    task_resume.add_argument(
        "--max-steps",
        type=int,
        help="Override the saved step budget for this resume. Use 0 for unbounded segments.",
    )
    task_resume.add_argument(
        "--yolo",
        action="store_true",
        help="Override the saved YOLO setting for this resume.",
    )

    task_show = task_subparsers.add_parser("show", help="Show one task.")
    task_show.add_argument("--task-id", required=True, help="Task identifier.")

    task_list = task_subparsers.add_parser("list", help="List tasks.")
    task_list.add_argument("--json", action="store_true", help="Return machine-readable output.")

    task_cancel = task_subparsers.add_parser("cancel", help="Cancel a task and release the device.")
    task_cancel.add_argument("--task-id", required=True, help="Task identifier.")

    tools_parser = subparsers.add_parser("tools", help="Inspect or invoke agent tools directly.")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command", required=True)

    tools_list = tools_subparsers.add_parser("list", help="List available agent tools.")
    tools_list.add_argument("--json", action="store_true", help="Return machine-readable output.")

    tools_run = tools_subparsers.add_parser("run", help="Run one tool directly.")
    tools_run.add_argument("--tool", required=True, help="Tool name.")
    tools_run.add_argument("--app", help="Optional app registry key for app-scoped tools.")
    tools_run.add_argument("--args", default="{}", help="JSON object with tool arguments.")
    return parser


_simplify_action_history = simplify_action_history
_tools_used = tools_used
_agent_response = agent_response
_build_run_payload = build_run_payload
_simplify_events = simplify_events
_decision_log = decision_log
_state_snapshots = state_snapshots
_model_errors = model_errors


def _write_run_trace(run_dir: Path, payload: dict[str, Any]) -> None:
    dump_json(run_dir / "agent_trace.json", payload)


def _runtime_error_payload(*, reason: str, run_dir: Path | None = None, appium_start_hint: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "error",
        "reason": reason,
    }
    if run_dir and run_dir != Path("."):
        payload["run_dir"] = str(run_dir)
    if appium_start_hint:
        payload["appium_start_hint"] = appium_start_hint
    return payload


def _clip(value: object, limit: int = 120) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _format_live_event(event: dict[str, Any]) -> str | None:
    event_type = str(event.get("type") or "")
    step = event.get("step")
    prefix = f"[step {step}]" if step is not None else "[run]"
    if event_type == "run_started":
        return f"{prefix} started app={event.get('app_name')} yolo={event.get('yolo_mode')} run_dir={event.get('run_dir')}"
    if event_type == "interrupt_requested":
        return f"{prefix} interrupt_requested reason={_clip(event.get('reason'), 180)}"
    if event_type == "state_captured":
        state = dict(event.get("state") or {})
        visible = ", ".join(list(state.get("visible_text") or [])[:4])
        return (
            f"{prefix} state {state.get('package_name')}/{state.get('activity_name')} "
            f"visible=[{_clip(visible, 160)}]"
        )
    if event_type == "skill_loaded":
        return (
            f"{prefix} skill_loaded app={event.get('app_name')} "
            f"path={event.get('path')} screens={event.get('screen_count')} selectors={event.get('selector_count')}"
        )
    if event_type == "system_skill_loaded":
        return f"{prefix} system_skill_loaded path={event.get('path')}"
    if event_type == "skill_auto_updated":
        return (
            f"{prefix} skill_auto_updated app={event.get('app_name')} screen_id={event.get('screen_id')} "
            f"new_screen={event.get('new_screen')} selectors_added={event.get('selectors_added')}"
        )
    if event_type == "skill_state_updated":
        return (
            f"{prefix} skill_state_updated app={event.get('app_name')} "
            f"status={event.get('status')} reason={_clip(event.get('reason'), 140)}"
        )
    if event_type == "memory_updated":
        return (
            f"{prefix} memory_updated app={event.get('app_name')} "
            f"status={event.get('status')} path={event.get('path')}"
        )
    if event_type == "backup_updated":
        sections = ",".join(list(event.get("sections") or []))
        return (
            f"{prefix} backup_updated app={event.get('app_name')} "
            f"sections={sections} path={event.get('path')}"
        )
    if event_type == "decision_made":
        decision = dict(event.get("decision") or {})
        meta = dict(event.get("decision_meta") or {})
        line = (
            f"{prefix} decision source={meta.get('source')} provider={meta.get('provider')} "
            f"action={decision.get('next_action')} target={decision.get('target_label')} "
            f"reason={_clip(decision.get('reason'), 180)}"
        )
        source = str(meta.get("source") or "")
        if ("fallback" in source or "error" in source) and meta.get("detail"):
            line += f" detail={_clip(meta.get('detail'), 180)}"
        if ("fallback" in source or "error" in source) and meta.get("status_code") is not None:
            line += f" status={meta.get('status_code')}"
        return line
    if event_type == "action_performed":
        return f"{prefix} performed action={event.get('action')} target={event.get('target_label')} reason={_clip(event.get('reason'), 180)}"
    if event_type == "tap_retry_attempted":
        line = (
            f"{prefix} tap_retry method={event.get('method')} changed={event.get('changed')} "
            f"target={event.get('target_label')}"
        )
        if event.get("error"):
            line += f" error={_clip(event.get('error'), 140)}"
        return line
    if event_type == "tool_executed":
        tool_name = str(event.get("tool_name") or "")
        output = dict(event.get("output") or {})
        if tool_name == "write_skill_file":
            return (
                f"{prefix} tool=write_skill_file ok={event.get('ok')} "
                f"app={output.get('app_name')} file={output.get('file_name')} path={output.get('path')}"
            )
        if tool_name == "bootstrap_skill":
            return (
                f"{prefix} tool=bootstrap_skill ok={event.get('ok')} "
                f"app={output.get('app_name')} path={output.get('path')}"
            )
        if tool_name == "read_skill":
            return (
                f"{prefix} tool=read_skill ok={event.get('ok')} "
                f"app={output.get('app_name')} file={output.get('file_name')}"
            )
        if tool_name == "save_script":
            return (
                f"{prefix} tool=save_script ok={event.get('ok')} "
                f"app={output.get('app_name')} script={output.get('script_name')} path={output.get('path')}"
            )
        if tool_name == "run_script":
            return (
                f"{prefix} tool=run_script ok={event.get('ok')} "
                f"app={output.get('app_name')} script={output.get('script_name')} "
                f"executed={output.get('steps_executed')} skipped={output.get('steps_skipped')}"
            )
        return f"{prefix} tool={tool_name} ok={event.get('ok')} args={_clip(event.get('tool_arguments'), 120)}"
    if event_type in {"run_completed", "run_stalled", "max_steps_reached", "manual_intervention_required", "action_blocked", "run_interrupted"}:
        return f"{prefix} {event_type} reason={_clip(event.get('reason'), 180)}"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runtime = load_runtime_config()
    yolo_mode = bool(getattr(args, "yolo", False)) or os.environ.get("AGENT_RUNNER_YOLO", "").strip().casefold() in {
        "1",
        "true",
        "yes",
        "on",
    }

    if args.command == "doctor":
        payload = {
            "appium_url": runtime.appium_url,
            "device_serial": runtime.device_serial,
            "model_provider": runtime.model_provider,
            "vision_model": runtime.model_name,
            "gemini_model": runtime.gemini_model,
            "lmstudio_model": runtime.lmstudio_model,
            "lmstudio_base_url": runtime.lmstudio_base_url,
            "skills_dir": str(runtime.skills_dir),
            "system_skill_file": str(runtime.system_skill_file),
            "runs_dir": str(runtime.runs_dir),
            "gemini_api_key_present": bool(runtime.gemini_api_key),
            "lmstudio_api_key_present": bool(runtime.lmstudio_api_key),
            "adb_path": runtime.adb_path,
            "android_sdk_root": runtime.android_sdk_root,
            "appium_start_hint": (
                f'export ANDROID_SDK_ROOT="{runtime.android_sdk_root}" '
                f'ANDROID_HOME="{runtime.android_sdk_root}" && appium'
            ),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for key, value in payload.items():
                print(f"{key}: {value}")
        return 0

    if args.command == "app":
        payload = [
            {
                "name": app.name,
                "package_name": app.package_name,
                "launch_activity": app.launch_activity,
                "default_goal_hint": app.default_goal_hint,
            }
            for app in list_app_configs()
        ]
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            for app in payload:
                print(f"{app['name']}: {app['package_name']}")
        return 0

    if args.command == "gui":
        from agent_runner.gui import serve_gui

        serve_gui(runtime, host=args.host, port=args.port, open_browser=args.open_browser)
        return 0

    if args.command == "tui":
        from agent_runner.tui import serve_tui

        serve_tui(runtime)
        return 0

    adapter = AndroidAdapter(
        appium_url=runtime.appium_url,
        device_serial=runtime.device_serial,
        adb_path=runtime.adb_path,
        android_sdk_root=runtime.android_sdk_root,
    )
    skill_manager = SkillManager(runtime.skills_dir, runtime.system_skill_file)
    tool_executor = AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager)
    task_manager = TaskManager(runtime.runs_dir / "tasks")

    def build_orchestrator() -> tuple[Orchestrator, list[dict[str, Any]]]:
        events: list[dict[str, Any]] = []

        def handle_event(event: dict[str, Any]) -> None:
            enriched = {"timestamp": time.time(), **event}
            events.append(enriched)
            line = _format_live_event(enriched)
            if line:
                print(line, file=sys.stderr, flush=True)

        orchestrator = Orchestrator(
            android_adapter=adapter,
            tool_executor=tool_executor,
            vision_agent=VisionAgent(
                runtime.gemini_api_key,
                runtime.model_name,
                provider=runtime.model_provider,
                lmstudio_base_url=runtime.lmstudio_base_url,
                lmstudio_api_key=runtime.lmstudio_api_key,
            ),
            skill_manager=skill_manager,
            runs_dir=runtime.runs_dir,
            event_callback=handle_event,
        )
        return orchestrator, events

    def run_context_for(
        app_name: str,
        goal: str,
        *,
        max_steps: int,
        yolo: bool,
    ) -> tuple[RunContext, Orchestrator, list[dict[str, Any]]]:
        app = get_app_config(app_name)
        orchestrator, events = build_orchestrator()
        context = RunContext(
            app=app,
            goal=goal,
            run_dir=Path("."),
            exploration_enabled=True,
            max_steps=max_steps,
            yolo_mode=yolo,
        )
        return context, orchestrator, events

    if args.command == "tools":
        if args.tools_command == "list":
            payload = [tool.to_dict() for tool in tool_executor.list_tools()]
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                for item in payload:
                    print(f"{item['name']}: {item['description']}")
            return 0
        ensure_directory(runtime.runs_dir)
        run_dir = ensure_directory(runtime.runs_dir / "tool-debug")
        app = get_app_config(args.app) if args.app else None
        arguments = json.loads(args.args)
        bundle = skill_manager.load_skill(app) if app else None
        current_state = None
        if args.tool in {"tap", "swipe"}:
            current_state = adapter.capture_state(run_dir)
        try:
            result = tool_executor.execute(
                tool_name=args.tool,
                arguments=arguments,
                run_dir=run_dir,
                current_state=current_state,
                app=app,
                skill=bundle,
            )
        finally:
            adapter.close()
        print(json.dumps(
            {
                "tool_name": result.tool_name,
                "ok": result.ok,
                "output": result.output,
                "error": result.error,
                "captured_state": result.captured_state.summary() if result.captured_state else None,
            },
            indent=2,
            sort_keys=True,
        ))
        return 0 if result.ok else 1

    if args.command == "task":
        if args.task_command == "list":
            payload = [task.to_dict() for task in task_manager.list_tasks(device_serial=runtime.device_serial)]
            if args.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                for task in payload:
                    print(f"{task['task_id']}: {task['status']} ({task['app_name']}) - {task['goal']}")
            return 0

        if args.task_command == "show":
            task = task_manager.load_task(args.task_id)
            print(json.dumps(task.to_dict(), indent=2, sort_keys=True))
            return 0

        if args.task_command == "cancel":
            task = task_manager.cancel_task(args.task_id)
            print(json.dumps(task.to_dict(), indent=2, sort_keys=True))
            return 0

        try:
            if args.task_command == "start":
                task = task_manager.create_task(
                    app=get_app_config(args.app),
                    device_serial=runtime.device_serial,
                    goal=args.goal,
                    yolo_mode=yolo_mode,
                    step_budget=args.max_steps,
                )
            else:
                task = task_manager.load_task(args.task_id)
                if task.device_serial != runtime.device_serial:
                    raise RuntimeError(
                        f"Task '{task.task_id}' is bound to device {task.device_serial}, "
                        f"but the current runtime device is {runtime.device_serial}."
                    )
                if not task_manager.can_resume(task):
                    raise RuntimeError(f"Task '{task.task_id}' is not resumable from status '{task.status}'.")
                if args.max_steps:
                    task.step_budget = args.max_steps
                if bool(getattr(args, "yolo", False)):
                    task.yolo_mode = True
                task_manager.save_task(task)
        except (FileNotFoundError, RuntimeError) as exc:
            print(json.dumps({"error": str(exc)}, indent=2, sort_keys=True))
            return 1

        task_manager.mark_running(task)
        context, orchestrator, events = run_context_for(
            task.app_name,
            task.goal,
            max_steps=task.step_budget,
            yolo=task.yolo_mode,
        )
        try:
            result = orchestrator.run(context)
        except Exception as exc:
            task.status = "error"
            task.last_reason = str(exc)
            task.checkpoints.append(
                {
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "task_status": "error",
                    "reason": str(exc),
                }
            )
            task_manager.save_task(task)
            error_payload = _runtime_error_payload(
                reason=str(exc),
                run_dir=context.run_dir if context.run_dir != Path(".") else None,
                appium_start_hint=(
                    f'export ANDROID_SDK_ROOT="{runtime.android_sdk_root}" '
                    f'ANDROID_HOME="{runtime.android_sdk_root}" && appium'
                ),
            )
            if context.run_dir != Path("."):
                _write_run_trace(context.run_dir, error_payload)
            print(json.dumps(error_payload, indent=2, sort_keys=True))
            return 1
        finally:
            adapter.close()
        task = task_manager.record_run_result(task, result)
        payload = _build_run_payload(
            result,
            context,
            extra={
                "task_id": task.task_id,
                "task_status": task.status,
                "run_status": result.status,
                "total_steps": task.total_steps,
                "device_serial": task.device_serial,
                "app_name": task.app_name,
                "goal": task.goal,
                "completion_criteria": task.completion_criteria,
                "decisions": _decision_log(events),
                "state_snapshots": _state_snapshots(events),
                "events": _simplify_events(events),
                "context_log_path": str(result.run_dir / "agent_context.jsonl"),
                **({"model_errors": _model_errors(events)} if _model_errors(events) else {}),
            },
        )
        _write_run_trace(result.run_dir, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if task.status in {"completed", "ready_to_resume", "waiting_for_login", "waiting_for_verification", "waiting_for_manual"} else 1

    ensure_directory(runtime.runs_dir)
    context, orchestrator, events = run_context_for(args.app, args.goal, max_steps=args.max_steps, yolo=yolo_mode)
    try:
        result = orchestrator.run(context)
    except Exception as exc:
        error_payload = _runtime_error_payload(
            reason=str(exc),
            run_dir=context.run_dir if context.run_dir != Path(".") else None,
            appium_start_hint=(
                f'export ANDROID_SDK_ROOT="{runtime.android_sdk_root}" '
                f'ANDROID_HOME="{runtime.android_sdk_root}" && appium'
            ),
        )
        if context.run_dir != Path("."):
            _write_run_trace(context.run_dir, error_payload)
        print(json.dumps(error_payload, indent=2, sort_keys=True))
        return 1
    finally:
        adapter.close()
    payload = _build_run_payload(
        result,
        context,
        extra={
            "decisions": _decision_log(events),
            "state_snapshots": _state_snapshots(events),
            "events": _simplify_events(events),
            "context_log_path": str(result.run_dir / "agent_context.jsonl"),
            **({"model_errors": _model_errors(events)} if _model_errors(events) else {}),
        },
    )
    _write_run_trace(result.run_dir, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if result.status in {"completed", "manual_login_required", "manual_verification_required", "approval_required"} else 1
