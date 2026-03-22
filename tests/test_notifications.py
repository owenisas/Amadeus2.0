from agent_runner.notifications import parse_notification_logcat_line


def test_parse_notification_logcat_line_extracts_json_payload() -> None:
    line = '03-22 10:00:00.000  1000  1001 I AGENT_NOTIFICATION: {"event_type":"notification_posted","package_name":"com.facebook.katana","title":"Hello","key":"abc"}'

    payload = parse_notification_logcat_line(line)

    assert payload == {
        "event_type": "notification_posted",
        "package_name": "com.facebook.katana",
        "title": "Hello",
        "key": "abc",
    }


def test_parse_notification_logcat_line_ignores_invalid_lines() -> None:
    assert parse_notification_logcat_line("random noise") is None
