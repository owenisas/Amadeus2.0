from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
BACKUP_JSON = ROOT / "skills" / "apps" / "facebook" / "data" / "backup.json"


def _classify_state(screen: dict[str, Any]) -> str:
    visible = [str(item) for item in screen.get("visible_text") or []]
    clickable = [str(item) for item in screen.get("clickable_text") or []]
    text = " ".join(visible + clickable).casefold()
    if "marketplace seller inbox" in text and "marketplace buyer inbox" in text:
        return "marketplace_inbox"
    if "marketplace listing" in text and ("send" in text or "type a message" in text or "message seller" in text):
        return "message_thread"
    if "search messenger" in text or text.startswith("messages "):
        return "message_inbox"
    if "mute notifications" in text and "search in conversation" in text:
        return "thread_settings"
    if "get help on marketplace" in text:
        return "marketplace_help"
    if "for you" in text and "local" in text and "what do you want to buy?" in text:
        return "marketplace_feed"
    if "product image" in text and "navigate to search" in text:
        return "listing_detail"
    if "messenger backup" in text or "recovery" in text or "are you sure?" in text:
        return "recovery_prompt"
    return "other"


def _read_workflow() -> tuple[str | None, int | None, str | None]:
    try:
        payload = json.loads(BACKUP_JSON.read_text(encoding="utf-8"))
    except Exception:
        return (None, None, None)
    workflow = dict(payload.get("facebook_marketplace", {}).get("workflow") or {})
    mode = workflow.get("mode")
    queue = workflow.get("reply_queue")
    queue_length = len(queue) if isinstance(queue, list) else None
    active_thread = workflow.get("active_thread_key")
    return (mode, queue_length, active_thread)


def _capture_state(device_serial: str) -> dict[str, Any] | None:
    env = os.environ.copy()
    env["ANDROID_DEVICE_SERIAL"] = device_serial
    command = [
        str(PYTHON),
        "-m",
        "agent_runner",
        "tools",
        "run",
        "--tool",
        "capture_state",
        "--app",
        "facebook",
        "--args",
        "{}",
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"capture_state failed ({result.returncode})")
    payload = json.loads(result.stdout)
    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("error") or "capture_state returned not ok"))
    return dict(payload.get("captured_state") or {})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-serial", required=True)
    parser.add_argument("--interval-seconds", type=int, default=30)
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument("--log-path", default="/tmp/facebook_monitor.log")
    args = parser.parse_args()

    log_path = Path(args.log_path)
    last_signature: tuple[str | None, str | None, int | None, str | None] | None = None
    iteration = 0

    while args.max_iterations == 0 or iteration < args.max_iterations:
        iteration += 1
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        try:
            screen = _capture_state(args.device_serial)
            mode, queue_length, active_thread = _read_workflow()
            classification = _classify_state(screen)
            visible = list(screen.get("visible_text") or [])[:6]
            signature = (
                classification,
                str(mode) if mode is not None else None,
                queue_length,
                str(active_thread) if active_thread is not None else None,
            )
            if signature != last_signature:
                line = {
                    "timestamp": now,
                    "classification": classification,
                    "workflow_mode": mode,
                    "reply_queue_count": queue_length,
                    "active_thread_key": active_thread,
                    "package_name": screen.get("package_name"),
                    "activity_name": screen.get("activity_name"),
                    "visible_text": visible,
                    "screenshot_path": screen.get("screenshot_path"),
                }
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with log_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(line, ensure_ascii=True) + "\n")
                print(json.dumps(line, ensure_ascii=True))
                sys.stdout.flush()
                last_signature = signature
        except Exception as exc:
            line = {"timestamp": now, "error": str(exc)}
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, ensure_ascii=True) + "\n")
            print(json.dumps(line, ensure_ascii=True))
            sys.stdout.flush()
        time.sleep(max(5, args.interval_seconds))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
