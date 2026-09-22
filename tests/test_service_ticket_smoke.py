"""Smoke tests for Service Ticket step helpers (catch missing imports at runtime)."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


@pytest.fixture
def stk_state():
    return {
        "stk_extracted": [
            {
                "type": "Analyze",
                "client": "Standard",
                "report": "Visit Analysis",
                "description": "Fix drill-through",
                "ticket": "PIC-1",
            }
        ],
        "stk_sharepoint": "https://sharepoint.example/doc.docx",
        "stk_release_PIC": {"id": "1", "name": "2026.3.07.29"},
        "stk_release_AN": {"id": "2", "name": "2026.3.07.29"},
        "shared_stk_standalone_mode": True,
    }


class TestServiceTicketSmoke:
    def test_step4_get_context(self, monkeypatch, stk_state):
        import streamlit as st

        from release_platform.ui import helpers
        from release_platform.ui.service_ticket import step4_plans

        monkeypatch.setattr(st, "session_state", stk_state, raising=False)
        monkeypatch.setattr(helpers.config, "PROJECTS", [
            {"key": "PIC", "name": "PIC"},
            {"key": "AN", "name": "AN"},
        ])

        ctx = step4_plans._get_context()
        assert ctx["sharepoint"] == "https://sharepoint.example/doc.docx"
        assert "2026.3.07.29" in ctx["version_name"]

    def test_step4_build_plans(self, monkeypatch, stk_state):
        import streamlit as st

        from release_platform.ui.service_ticket import step4_plans

        monkeypatch.setattr(st, "session_state", stk_state, raising=False)
        ctx = step4_plans._get_context()
        assert step4_plans._build_impl(ctx).strip()
        assert step4_plans._build_test(ctx).strip()
        assert step4_plans._build_backout(ctx).strip()
        assert step4_plans._build_impact(ctx).strip()

    def test_step3_build_description_adf(self, monkeypatch, stk_state):
        import streamlit as st

        from adf_builder import adf_links, adf_to_plain_text
        from release_platform.ui.service_ticket.step3_description import _build_description_adf

        monkeypatch.setattr(st, "session_state", stk_state, raising=False)
        adf_doc = _build_description_adf(
            stk_state["stk_extracted"],
            stk_state["stk_sharepoint"],
        )
        plain = adf_to_plain_text(adf_doc)
        assert "What is changing, in business terms" in plain
        assert "Who is affected" in plain
        assert "Supporting records" in plain
        assert "PIC-1" in plain
        links = adf_links(adf_doc)
        assert any(href == stk_state["stk_sharepoint"] for _label, href in links)

    def test_step2_esc_helper_importable(self):
        from release_platform.ui.helpers import esc

        assert esc("<TCKT-1>") == "&lt;TCKT-1&gt;"
