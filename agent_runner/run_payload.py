from __future__ import annotations

from typing import Any


def model_errors(events: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "decision_made":
            continue
        meta = dict(event.get("decision_meta") or {})
        source = str(meta.get("source") or "")
        if "fallback" not in source and "error" not in source:
            continue
        errors.append(
            {
                "step": event.get("step"),
                "source": source,
                "provider": meta.get("provider"),
                "model": meta.get("model"),
                "status_code": meta.get("status_code"),
                "detail": meta.get("detail"),
            }
        )
    return errors[-limit:]


def simplify_events(events: list[dict[str, Any]], *, limit: int = 20) -> list[dict[str, Any]]:
    simplified: list[dict[str, Any]] = []
    for event in events[-limit:]:
        entry: dict[str, Any] = {
            "type": event.get("type"),
            "step": event.get("step"),
        }
        if event.get("timestamp") is not None:
            entry["timestamp"] = event.get("timestamp")
        event_type = event.get("type")
        if event_type == "decision_made":
            decision = dict(event.get("decision") or {})
            decision_meta = dict(event.get("decision_meta") or {})
            entry.update(
                {
                    "next_action": decision.get("next_action"),
                    "reason": decision.get("reason"),
                    "confidence": decision.get("confidence"),
                    "target_label": decision.get("target_label"),
                    "tool_name": decision.get("tool_name"),
                    "decision_source": decision_meta.get("source"),
                    "model_provider": decision_meta.get("provider"),
                    "model_name": decision_meta.get("model"),
                }
            )
            if decision_meta.get("status_code") is not None:
                entry["status_code"] = decision_meta.get("status_code")
            if decision_meta.get("detail") is not None:
                entry["detail"] = decision_meta.get("detail")
        elif event_type == "state_captured":
            state = dict(event.get("state") or {})
            entry["package_name"] = state.get("package_name")
            entry["activity_name"] = state.get("activity_name")
            entry["visible_text"] = list(state.get("visible_text") or [])[:8]
            entry["clickable_text"] = list(state.get("clickable_text") or [])[:8]
            if state.get("screenshot_path"):
                entry["screenshot_path"] = state.get("screenshot_path")
            if state.get("hierarchy_path"):
                entry["hierarchy_path"] = state.get("hierarchy_path")
        elif event_type in {"skill_loaded", "system_skill_loaded", "skill_auto_updated", "skill_state_updated", "memory_updated", "backup_updated"}:
            for key in (
                "app_name",
                "path",
                "screen_id",
                "new_screen",
                "selectors_added",
                "screen_count",
                "selector_count",
                "status",
                "reason",
                "summary_path",
                "thread_count",
                "contacted_item_count",
                "inspected_item_count",
            ):
                if event.get(key) is not None:
                    entry[key] = event.get(key)
            if event.get("sections") is not None:
                entry["sections"] = list(event.get("sections") or [])
        elif event_type == "tap_retry_attempted":
            for key in ("method", "changed", "target_label", "error", "screenshot_path", "hierarchy_path"):
                if event.get(key) is not None:
                    entry[key] = event.get(key)
        else:
            for key in ("reason", "status", "run_dir", "app_name", "goal", "target_label", "tool_name"):
                if event.get(key) is not None:
                    entry[key] = event.get(key)
        simplified.append(entry)
    return simplified


def decision_log(events: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "decision_made":
            continue
        decision = dict(event.get("decision") or {})
        decisions.append(
            {
                "step": event.get("step"),
                "next_action": decision.get("next_action"),
                "reason": decision.get("reason"),
                "confidence": decision.get("confidence"),
                "target_label": decision.get("target_label"),
                "tool_name": decision.get("tool_name"),
                "decision_source": dict(event.get("decision_meta") or {}).get("source"),
                "model_provider": dict(event.get("decision_meta") or {}).get("provider"),
                "model_name": dict(event.get("decision_meta") or {}).get("model"),
                "status_code": dict(event.get("decision_meta") or {}).get("status_code"),
                "detail": dict(event.get("decision_meta") or {}).get("detail"),
            }
        )
    return decisions[-limit:]


def state_snapshots(events: list[dict[str, Any]], *, limit: int = 8) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") != "state_captured":
            continue
        state = dict(event.get("state") or {})
        snapshots.append(
            {
                "step": event.get("step"),
                "package_name": state.get("package_name"),
                "activity_name": state.get("activity_name"),
                "visible_text": list(state.get("visible_text") or [])[:10],
                "clickable_text": list(state.get("clickable_text") or [])[:10],
                "screenshot_path": state.get("screenshot_path"),
                "hierarchy_path": state.get("hierarchy_path"),
            }
        )
    return snapshots[-limit:]


def simplify_action_history(action_history: list[Any]) -> list[dict[str, Any]]:
    simplified: list[dict[str, Any]] = []
    for item in action_history:
        raw = item.to_dict() if hasattr(item, "to_dict") else dict(item)
        entry = {
            "step": raw.get("step"),
            "action": raw.get("action"),
            "allowed": raw.get("allowed"),
            "label": raw.get("tool_name") or raw.get("action"),
            "reason": raw.get("reason"),
        }
        if raw.get("tool_name"):
            entry["tool_name"] = raw.get("tool_name")
        if raw.get("tool_arguments"):
            entry["tool_arguments"] = raw.get("tool_arguments")
        if raw.get("tool_output"):
            entry["tool_output_keys"] = sorted(raw.get("tool_output", {}).keys())
        simplified.append(entry)
    return simplified


def tools_used(action_history: list[Any]) -> list[str]:
    names: list[str] = []
    for item in action_history:
        raw = item.to_dict() if hasattr(item, "to_dict") else dict(item)
        tool_name = raw.get("tool_name")
        if tool_name and tool_name not in names:
            names.append(tool_name)
    return names


def agent_response(result, action_history: list[Any]) -> str:
    if action_history:
        last = action_history[-1]
        raw = last.to_dict() if hasattr(last, "to_dict") else dict(last)
        detail = raw.get("tool_name") or raw.get("action") or "action"
        return f"{result.status}: {result.reason} Last step: {detail}."
    return f"{result.status}: {result.reason}"


def build_run_payload(result, context, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "status": result.status,
        "reason": result.reason,
        "steps": result.steps,
        "run_dir": str(result.run_dir),
        "package_name": result.last_state.package_name if result.last_state else None,
        "activity_name": result.last_state.activity_name if result.last_state else None,
        "yolo_mode": context.yolo_mode,
        "notice": result.notice,
        "agent_response": agent_response(result, context.action_history),
        "actions": simplify_action_history(context.action_history),
        "tools_used": tools_used(context.action_history),
    }
    if extra:
        payload.update(extra)
    return payload
