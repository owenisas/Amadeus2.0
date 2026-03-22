from pathlib import Path

from agent_runner.event_queue import EventQueue


def test_event_queue_appends_and_tails_events(tmp_path: Path) -> None:
    queue = EventQueue(tmp_path / "runs")

    queue.append("task_started", {"task_id": "task-1", "app_name": "settings"})
    queue.append("task_finished", {"task_id": "task-1", "status": "completed"})

    events = queue.tail(limit=10)

    assert [event["event_type"] for event in events] == ["task_started", "task_finished"]
    assert events[0]["task_id"] == "task-1"
