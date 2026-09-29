"""Tests for Ticket Review Step 3 export helpers."""

from __future__ import annotations

import csv
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestStep3Export:
    def test_build_ticket_csv(self):
        from release_platform.ui.ticket_review import step3_format as s3

        grouped = {
            "Alice": [
                {
                    "key": "PIC-1",
                    "fields": {
                        "summary": "Fix report",
                        "status": {"name": "Review"},
                    },
                }
            ]
        }
        raw = s3._build_ticket_csv(grouped, "https://jira.example")
        text = raw.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        assert rows[0] == ["Owner", "Key", "Summary", "Status", "Link"]
        assert rows[1][0] == "Alice"
        assert rows[1][1] == "PIC-1"
        assert "PIC-1" in rows[1][4]

    def test_resolve_grouped_from_snapshot(self, monkeypatch):
        import streamlit as st
        from release_platform.ui.ticket_review import step3_format as s3

        monkeypatch.setattr(
            st,
            "session_state",
            {},
            raising=False,
        )
        monkeypatch.setattr(
            s3,
            "get_snapshot",
            lambda: {
                "issues": [
                    {
                        "key": "AN-1",
                        "fields": {
                            "summary": "Test",
                            "assignee": {"displayName": "Bob"},
                            "status": {"name": "Passed QA"},
                        },
                    }
                ]
            },
        )
        grouped = s3._resolve_grouped()
        assert grouped is not None
        assert "Bob" in grouped
        assert grouped["Bob"][0]["key"] == "AN-1"
