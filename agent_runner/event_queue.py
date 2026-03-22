from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from agent_runner.utils import append_jsonl, ensure_directory


class EventQueue:
    def __init__(self, runs_dir: Path) -> None:
        self.root = ensure_directory(runs_dir / "hooks")
        self.path = self.root / "events.jsonl"

    def append(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        event = {
            "event_type": event_type,
            "timestamp": time.time(),
            **payload,
        }
        append_jsonl(self.path, event)
        return event

    def tail(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        output: list[dict[str, Any]] = []
        for raw in lines[-limit:]:
            try:
                output.append(json.loads(raw))
            except Exception:
                continue
        return output
