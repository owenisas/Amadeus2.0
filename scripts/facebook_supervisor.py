from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
ADB = Path.home() / "Library/Android/sdk/platform-tools/adb"
DEFAULT_GOAL = (
    "Resume the Facebook Marketplace hunting workflow. Recover from stale inbox, chat, "
    "thread-settings, or deep-linked surfaces back into the main Marketplace hunt. Inspect "
    "valuable local resale listings, send short human buyer messages using the Facebook skill "
    "rules when profitable, periodically check Marketplace replies from sellers, and then "
    "continue hunting for more listings unless blocked by account restrictions or device "
    "connectivity issues."
)


def _log(message: str) -> None:
    now = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"[{now}] {message}", flush=True)


def _latest_run_dir() -> Path | None:
    runs = sorted((ROOT / "runs").glob("facebook-*"), key=lambda path: path.stat().st_mtime, reverse=True)
    return runs[0] if runs else None


def _latest_context_log() -> Path | None:
    run_dir = _latest_run_dir()
    if run_dir is None:
        return None
    path = run_dir / "agent_context.jsonl"
    return path if path.exists() else None


def _context_log_age_seconds() -> float | None:
    path = _latest_context_log()
    if path is None:
        return None
    return max(0.0, time.time() - path.stat().st_mtime)


def _ensure_adb_connected(device_serial: str) -> None:
    result = subprocess.run(
        [str(ADB), "devices", "-l"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    devices_output = result.stdout
    if device_serial in devices_output:
        return
    reconnect = subprocess.run(
        [str(ADB), "connect", device_serial],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=20,
    )
    _log(f"adb reconnect -> {reconnect.stdout.strip() or reconnect.stderr.strip() or 'no output'}")


def _start_run(device_serial: str, goal: str, extra_env: dict[str, str]) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.update(extra_env)
    env["ANDROID_DEVICE_SERIAL"] = device_serial
    env.setdefault("AGENT_RUNNER_MODEL_PROVIDER", "gemini")
    env.setdefault("GEMINI_TIMEOUT_SECONDS", "120")
    command = [
        str(PYTHON),
        "-m",
        "agent_runner",
        "run",
        "--app",
        "facebook",
        "--goal",
        goal,
        "--max-steps",
        "0",
        "--yolo",
    ]
    _log(f"starting facebook run for {device_serial}")
    return subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
        start_new_session=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device-serial", required=True)
    parser.add_argument("--goal", default=DEFAULT_GOAL)
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--stall-seconds", type=int, default=300)
    args = parser.parse_args()

    stop = False
    child: subprocess.Popen[str] | None = None

    def _handle_signal(signum, _frame) -> None:  # type: ignore[no-untyped-def]
        nonlocal stop
        stop = True
        _log(f"received signal {signum}, stopping supervisor")

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    extra_env = {
        "AGENT_RUNNER_MODEL_PROVIDER": os.environ.get("AGENT_RUNNER_MODEL_PROVIDER", "gemini"),
        "GEMINI_TIMEOUT_SECONDS": os.environ.get("GEMINI_TIMEOUT_SECONDS", "120"),
    }

    while not stop:
        try:
            _ensure_adb_connected(args.device_serial)
            if child is None or child.poll() is not None:
                if child is not None:
                    _log(f"facebook run exited with code {child.returncode}; restarting")
                child = _start_run(args.device_serial, args.goal, extra_env)
            else:
                age = _context_log_age_seconds()
                if age is not None and age > float(args.stall_seconds):
                    _log(f"facebook run stalled for {age:.0f}s; restarting")
                    child.terminate()
                    try:
                        child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=10)
                    child = _start_run(args.device_serial, args.goal, extra_env)
            time.sleep(max(5, args.poll_seconds))
        except Exception as exc:  # pragma: no cover - runtime guard
            _log(f"supervisor error: {exc}")
            time.sleep(max(5, args.poll_seconds))

    if child is not None and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=15)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=10)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
