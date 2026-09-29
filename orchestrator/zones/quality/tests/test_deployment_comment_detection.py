"""Tests for strict deployment comment detection."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

import jira_client


def _adf(*lines: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": line}]}
            for line in lines
        ],
    }


class TestIsVerifiedDeploymentComment:
    def test_accepts_standard_template(self):
        body = _adf(
            "The change has been deployed to Production on July 1 2026 at 10:00 AM.",
            "and changes are reflecting the Production and verified",
            "Deployment ID: uuid-123",
        )
        assert jira_client.is_verified_deployment_comment(body)

    def test_rejects_on_hold_note(self):
        body = _adf(
            "Deployment on hold — will be deployed to Production once approved.",
            "Deployment ID: uuid-123",
        )
        assert not jira_client.is_verified_deployment_comment(body)

    def test_rejects_loose_deployed_to_only(self):
        body = _adf("Changes deployed to Production pending verification.")
        assert not jira_client.is_verified_deployment_comment(body)

    def test_rejects_missing_deployment_id(self):
        body = _adf(
            "The change has been deployed to Production on July 1 2026 at 10:00 AM.",
            "and changes are reflecting the Production and verified",
        )
        assert not jira_client.is_verified_deployment_comment(body)
