"""Tests for confluence_publisher.generate_page_body and publish_page."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")
os.environ.setdefault("JIRA_BASE_URL", "https://example.atlassian.net")

from confluence_publisher import (
    PublishResult,
    default_title,
    generate_page_body,
    publish_page,
)

TICKET = {
    "ticket_key": "TCKT-123",
    "summary": "Production Deployment",
    "sharepoint_url": "https://sp.example.com/notes.docx",
    "extracted": [
        {"ticket": "AN-1", "type": "Analyze", "client": "Standard",
         "report": "New Members", "description": "add filter"},
        {"ticket": "PIC-2", "type": "Custom", "client": "Jetts",
         "report": "Revenue", "description": "fix currency"},
    ],
    "affected_clients": ["Standard", "Jetts"],
    "implementation_plan": "Deploy everything.",
    "test_plan": "Validate everything.",
    "backout_plan": "Roll back.",
    "business_impact": "Positive.",
}


class TestGeneratePageBody:
    def test_includes_header_with_key(self):
        body = generate_page_body(TICKET)
        assert "TCKT-123" in body
        assert "<h1>" in body

    def test_includes_sharepoint_link(self):
        body = generate_page_body(TICKET)
        assert "sp.example.com/notes.docx" in body

    def test_includes_jira_link(self):
        body = generate_page_body(TICKET)
        assert "browse/TCKT-123" in body

    def test_includes_release_summary_and_delivered_table(self):
        body = generate_page_body(TICKET)
        assert "Release Summary" in body
        assert "Key Highlights" in body
        assert "Reports / Dashboards Delivered" in body
        assert "New Members" in body
        assert "Jetts" in body
        assert "Revenue" in body

    def test_legacy_affected_clients_when_no_extracted(self):
        minimal = {
            "ticket_key": "SHIPIT-123",
            "summary": "Production Deployment",
            "affected_clients": ["Standard", "Jetts"],
        }
        body = generate_page_body(minimal)
        assert "Affected Clients" in body
        assert "Jetts" in body

    def test_includes_plan_sections(self):
        body = generate_page_body(TICKET)
        assert "Implementation Plan" in body
        assert "Test Plan" in body
        assert "Backout Plan" in body
        assert "Business Impact" in body

    def test_escapes_html_in_summary(self):
        tkt = dict(TICKET, summary="<script>alert(1)</script>")
        body = generate_page_body(tkt)
        assert "<script>" not in body
        assert "&lt;script&gt;" in body

    def test_missing_extracted_still_renders(self):
        minimal = {"ticket_key": "TCKT-9", "summary": "X"}
        body = generate_page_body(minimal)
        assert "TCKT-9" in body

    def test_delivered_reports_consolidated(self):
        tkt = dict(TICKET)
        tkt["extracted"] = [
            {"ticket": "AN-1", "type": "Analyze", "client": "Standard",
             "report": "New Members", "description": "a"},
            {"ticket": "AN-2", "type": "Analyze", "client": "Standard",
             "report": "New Members", "description": "b"},
        ]
        body = generate_page_body(tkt)
        assert body.count("New Members") >= 1
        assert "Reports / Dashboards Delivered" in body


class TestPublishPage:
    def test_missing_space_returns_error(self):
        result = publish_page("", None, "body", title="T")
        assert not result.ok
        assert "space" in result.error.lower()

    def test_happy_path(self):
        def fake_publisher(space, title, body, parent):
            return {"id": "p-42", "_links": {"webui": "/spaces/X/pages/p-42"}}

        result = publish_page("X", None, "body", title="T", publisher=fake_publisher)
        assert result.ok
        assert result.page_id == "p-42"
        assert "p-42" in result.url

    def test_publisher_exception_is_captured(self):
        def raiser(*a, **k):
            raise RuntimeError("boom")

        result = publish_page("X", None, "b", title="T", publisher=raiser)
        assert not result.ok
        assert "boom" in result.error

    def test_parent_is_forwarded(self):
        seen = {}

        def fake_publisher(space, title, body, parent):
            seen["parent"] = parent
            return {"id": "p"}

        publish_page("X", "12345", "b", title="T", publisher=fake_publisher)
        assert seen["parent"] == "12345"

    def test_default_publisher_uses_jira_client(self):
        with patch("confluence_publisher.jira_client") as mock_jc:
            mock_jc.confluence_find_page_by_title.return_value = None
            mock_jc.confluence_create_page.return_value = {"id": "new"}
            result = publish_page("X", None, "b", title="T")
        assert result.ok
        mock_jc.confluence_find_page_by_title.assert_called_once()
        mock_jc.confluence_create_page.assert_called_once()


class TestDefaultTitle:
    def test_with_key(self):
        assert "TCKT-123" in default_title(TICKET)

    def test_fallback_summary(self):
        assert default_title({"summary": "Foo"}).startswith("Foo")

    def test_fallback_plain(self):
        assert default_title({}) == "Release Notes"


class TestPublishResult:
    def test_to_dict(self):
        r = PublishResult(ok=True, page_id="1", url="u")
        assert r.to_dict()["ok"] is True
