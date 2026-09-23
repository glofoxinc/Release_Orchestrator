"""Tests for the TCKT schedule-window clarification comment."""

from __future__ import annotations

from datetime import date, time
from unittest.mock import patch

import jira_client
import schedule_time as stz


def test_build_schedule_window_comment_adf_states_ist_and_central():
    window = stz.window_statement(
        date(2026, 8, 5), time(10, 0),
        date(2026, 8, 5), time(13, 0),
        tz_name="Asia/Kolkata",
        display_tz="America/Chicago",
    )
    adf = jira_client.build_schedule_window_comment_adf(window)
    assert adf["type"] == "doc"
    texts = []
    for block in adf["content"]:
        for item in block.get("content", []):
            if item.get("type") == "text":
                texts.append(item["text"])
    joined = " ".join(texts)
    assert "Deployment window (timezone clarification)" in joined
    assert "10:00 AM" in joined and "IST" in joined
    assert "11:30 PM" in joined and "CDT" in joined
    assert "Do not close" in joined


def test_add_schedule_window_comment_posts_adf():
    window = stz.window_statement(
        date(2026, 8, 5), time(10, 30),
        date(2026, 8, 5), time(11, 30),
        tz_name="America/Chicago",
        display_tz="America/Chicago",
    )
    with patch.object(jira_client, "_post", return_value={"id": "1"}) as post:
        result = jira_client.add_schedule_window_comment("TCKT-1", window)
    assert result == {"id": "1"}
    args, kwargs = post.call_args
    assert args[0] == "/issue/TCKT-1/comment"
    body = args[1]["body"]
    assert body["type"] == "doc"
    assert any(
        "CDT" in (item.get("text") or "") or "10:30 AM" in (item.get("text") or "")
        for block in body["content"]
        for item in block.get("content", [])
    )


def test_add_schedule_window_comment_skips_empty():
    with patch.object(jira_client, "_post") as post:
        assert jira_client.add_schedule_window_comment("TCKT-1", {}) is None
        post.assert_not_called()
