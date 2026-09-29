"""Post-QA snapshot filtering and MCP/UI draft parity."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


SAMPLE_EXTRACTED = [
    {
        "type": "Analyze",
        "client": "Standard",
        "report": "Visit Analysis",
        "description": "Fix drill-through",
        "ticket": "PIC-1",
    },
    {
        "type": "Custom",
        "client": "Acme",
        "report": "Sales Dashboard",
        "description": "New KPI",
        "ticket": "PIC-2",
    },
]


class TestSnapshotQaFiltering:
    def test_effective_snapshot_ticket_keys_subtracts_qa_excluded(self):
        from release_platform.ui.helpers import effective_snapshot_ticket_keys, filter_snapshot_issues

        snap = {
            "ticket_keys": ["PIC-1", "PIC-2", "PIC-3"],
            "qa_excluded_keys": ["PIC-2"],
            "issues": [
                {"key": "PIC-1"},
                {"key": "PIC-2"},
                {"key": "PIC-3"},
            ],
        }

        assert effective_snapshot_ticket_keys(snap) == {"PIC-1", "PIC-3"}
        assert len(filter_snapshot_issues(snap)) == 2

    def test_apply_deploy_issue_filter_excludes_qa_keys(self):
        from release_platform.ui.helpers import apply_deploy_issue_filter

        release = {"id": "1", "name": "R1"}
        snapshot = {
            "release_PIC": {"id": "1", "name": "R1"},
            "ticket_keys": ["PIC-1", "PIC-2"],
            "qa_excluded_keys": ["PIC-2"],
        }
        issues = [{"key": "PIC-1"}, {"key": "PIC-2"}]

        with patch("ui.helpers.get_snapshot", return_value=snapshot), patch(
            "ui.workflow.is_deployer_standalone",
            return_value=False,
        ):
            filtered, meta = apply_deploy_issue_filter(issues, "PIC", release)

        assert meta["using_snapshot"] is True
        assert [iss["key"] for iss in filtered] == ["PIC-1"]
        assert meta["removed"] == ["PIC-2"]


class TestMcpDraftParity:
    def test_build_docx_data_uses_shared_draft_builder(self):
        from release_mcp import release_ops

        draft = release_ops._build_docx_data(SAMPLE_EXTRACTED, "2026.3.08.12")
        assert draft["version"] == "v2026.3.08.12"
        assert draft["release_date"] == "12-August-2026"
        assert draft["summary_p2"] == ""
        assert "PIC-1" in draft["change_rows"]
        assert draft["sanity_checklist"] == ""

    def test_build_description_adf_has_no_legacy_sections(self):
        from adf_builder import adf_to_plain_text
        from release_mcp import release_ops

        adf_doc = release_ops._build_description_adf(
            SAMPLE_EXTRACTED,
            "https://sharepoint.example/doc.docx",
            "v2026.3.08.12",
            {"sentence": "Wed 10:00–13:00 IST"},
        )
        plain = adf_to_plain_text(adf_doc)
        assert "Standard & Custom Summary" not in plain
        assert "Dashboards / Reports" not in plain
        assert "What is changing, in business terms" in plain
        assert "Who is affected" in plain
        assert "Not included in this change" in plain
        assert "How it is deployed" in plain
        assert "Supporting records" in plain
