from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_runner.android_adapter import AndroidAdapter
from agent_runner.agent_tools import AgentToolExecutor
from agent_runner.config import get_app_config, load_runtime_config
from agent_runner.models import RunContext
from agent_runner.orchestrator import Orchestrator
from agent_runner.skill_manager import SkillManager
from agent_runner.utils import ensure_directory
from agent_runner.vision_agent import VisionAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agent_runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run an app automation workflow.")
    run_parser.add_argument("--app", required=True, help="App registry key, for example amazon.")
    run_parser.add_argument("--goal", required=True, help="Natural-language goal for the agent.")
    run_parser.add_argument("--max-steps", type=int, default=12, help="Maximum number of agent steps.")

    doctor_parser = subparsers.add_parser("doctor", help="Print local runtime configuration.")
    doctor_parser.add_argument("--json", action="store_true", help="Return machine-readable output.")

    tools_parser = subparsers.add_parser("tools", help="Inspect or invoke agent tools directly.")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command", required=True)

    tools_list = tools_subparsers.add_parser("list", help="List available agent tools.")
    tools_list.add_argument("--json", action="store_true", help="Return machine-readable output.")

    tools_run = tools_subparsers.add_parser("run", help="Run one tool directly.")
    tools_run.add_argument("--tool", required=True, help="Tool name.")
    tools_run.add_argument("--app", help="Optional app registry key for app-scoped tools.")
    tools_run.add_argument("--args", default="{}", help="JSON object with tool arguments.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    runtime = load_runtime_config()

    if args.command == "doctor":
        payload = {
            "appium_url": runtime.appium_url,
            "device_serial": runtime.device_serial,
            "gemini_model": runtime.gemini_model,
            "skills_dir": str(runtime.skills_dir),
            "system_skill_file": str(runtime.system_skill_file),
            "runs_dir": str(runtime.runs_dir),
            "gemini_api_key_present": bool(runtime.gemini_api_key),
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

    adapter = AndroidAdapter(
        appium_url=runtime.appium_url,
        device_serial=runtime.device_serial,
        adb_path=runtime.adb_path,
        android_sdk_root=runtime.android_sdk_root,
    )
    skill_manager = SkillManager(runtime.skills_dir, runtime.system_skill_file)
    tool_executor = AgentToolExecutor(android_adapter=adapter, skill_manager=skill_manager)

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

    ensure_directory(runtime.runs_dir)
    app = get_app_config(args.app)
    orchestrator = Orchestrator(
        android_adapter=adapter,
        tool_executor=tool_executor,
        vision_agent=VisionAgent(runtime.gemini_api_key, runtime.gemini_model),
        skill_manager=skill_manager,
        runs_dir=runtime.runs_dir,
    )
    context = RunContext(
        app=app,
        goal=args.goal,
        run_dir=Path("."),
        exploration_enabled=True,
        max_steps=args.max_steps,
    )
    try:
        result = orchestrator.run(context)
    finally:
        adapter.close()
    print(json.dumps(
        {
            "status": result.status,
            "reason": result.reason,
            "steps": result.steps,
            "run_dir": str(result.run_dir),
            "package_name": result.last_state.package_name if result.last_state else None,
            "activity_name": result.last_state.activity_name if result.last_state else None,
        },
        indent=2,
        sort_keys=True,
    ))
    return 0 if result.status in {"completed", "manual_login_required", "approval_required"} else 1
