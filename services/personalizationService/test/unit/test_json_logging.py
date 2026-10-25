"""Verify the log field allowlist and one-line JSON output."""

import json
import logging

from personalization.infrastructure.observability.logging_config import (
    JsonLogFormatter,
)


def test_formatter_whitelists_fields_and_keeps_one_line() -> None:
    record = logging.LogRecord(
        "personalization.test",
        logging.WARNING,
        __file__,
        1,
        "Controlled message\nwith a second line",
        (),
        None,
    )
    record.__dict__.update(
        {
            "event": "test.completed",
            "status_code": 400,
            "Authorization": "Bearer private-authorization",
            "body": "private-body",
            "email": "private-contact",
        }
    )
    output = JsonLogFormatter("test").format(record)
    event = json.loads(output)
    assert len(output.splitlines()) == 1
    assert event["level"] == "WARN"
    assert event["trace_id"] is None
    assert event["span_id"] is None
    assert event["timestamp"].endswith("Z")
    assert event["status_code"] == 400
    assert "private" not in output
