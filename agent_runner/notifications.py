from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable


LOGCAT_TAG = "AGENT_NOTIFICATION"
_LOGCAT_PATTERN = re.compile(rf".*?\b{LOGCAT_TAG}\b\s*:?\s*(\{{.*)$")


def parse_notification_logcat_line(line: str) -> dict[str, Any] | None:
    match = _LOGCAT_PATTERN.match(line.strip())
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
    if "event_type" not in payload:
        return None
    return payload


def notification_listener_enabled(*, adb_path: str, device_serial: str, component_name: str) -> bool:
    command = [
        adb_path,
        "-s",
        device_serial,
        "shell",
        "settings",
        "get",
        "secure",
        "enabled_notification_listeners",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
    except Exception:
        return False
    enabled = completed.stdout.strip()
    return component_name in enabled


class NotificationMonitor:
    def __init__(
        self,
        *,
        adb_path: str,
        device_serial: str,
        on_event: Callable[[dict[str, Any]], None],
    ) -> None:
        self.adb_path = adb_path
        self.device_serial = device_serial
        self.on_event = on_event
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._process: subprocess.Popen[str] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        process = self._process
        if process and process.poll() is None:
            process.terminate()
        thread = self._thread
        if thread:
            thread.join(timeout=1)

    def _run(self) -> None:
        while not self._stop.is_set():
            command = [
                self.adb_path,
                "-s",
                self.device_serial,
                "logcat",
                "-T",
                "1",
                "-s",
                f"{LOGCAT_TAG}:I",
                "*:S",
            ]
            try:
                self._process = subprocess.Popen(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except Exception as exc:
                self.on_event({"event_type": "notification_monitor_error", "detail": str(exc), "timestamp": time.time()})
                time.sleep(3)
                continue
            assert self._process.stdout is not None
            for raw_line in self._process.stdout:
                if self._stop.is_set():
                    break
                payload = parse_notification_logcat_line(raw_line)
                if payload:
                    self.on_event(payload)
            if self._stop.is_set():
                break
            time.sleep(1)
