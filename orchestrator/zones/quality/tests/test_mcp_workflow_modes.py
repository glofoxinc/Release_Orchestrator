"""MCP standalone workflow modes and operator guide."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch


sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

from release_mcp import wizard, workflow_modes
from release_mcp.operator_guide import operator_cheat_sheet


class TestWorkflowModesRegistry:
    def test_normalize_aliases(self):
        assert workflow_modes.normalize_mode("notes") == workflow_modes.WORKFLOW_MODE_RELEASE_NOTES
        assert workflow_modes.normalize_mode("deployer") == workflow_modes.WORKFLOW_MODE_DEPLOYER

    def test_release_notes_only_steps(self):
        steps = workflow_modes.steps_for(workflow_modes.WORKFLOW_MODE_RELEASE_NOTES)
        assert steps[0] == wizard.STEP_RELEASE_NOTES
        assert wizard.STEP_COMPLETE in steps
        assert wizard.STEP_TICKET_REVIEW not in steps

    def test_service_ticket_only_includes_slack(self):
        steps = workflow_modes.steps_for(workflow_modes.WORKFLOW_MODE_SERVICE_TICKET)
        assert steps == [wizard.STEP_SERVICE_TICKET, wizard.STEP_SLACK, wizard.STEP_COMPLETE]


class TestOperatorGuide:
    def test_wizard_response_includes_operator_guide(self):
        session = {"id": "test", "step": wizard.STEP_RELEASE_NOTES, "inputs": {}, "updated_at": "now"}
        body = wizard._response(session, status="needs_input", prompt="test")
        assert "operator_guide" in body
        assert body["operator_guide"]["workflow_mode"] == "full"

    def test_release_notes_mode_cheat_sheet(self):
        guide = operator_cheat_sheet(
            step=wizard.STEP_RELEASE_NOTES,
            workflow_mode="release_notes_only",
            status="needs_input",
        )
        assert guide["workflow_mode"] == "release_notes_only"
        assert "generate_release_notes_docx" in guide["related_tools"]


class TestStandaloneWizardStart:
    def test_start_release_notes_only_mode(self):
        with patch("release_mcp.wizard._process") as proc:
            proc.return_value = {"status": "ok"}
            wizard.run_wizard(
                "start",
                inputs={"workflow_mode": "release_notes_only", "version_name": "2026.3.08.12"},
            )
        assert proc.called
        session_arg = proc.call_args[0][0]
        assert session_arg["step"] == wizard.STEP_RELEASE_NOTES
        assert session_arg["inputs"]["workflow_mode"] == "release_notes_only"
