"""Tests for deployment client resolution and filled-entry guards."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


class TestDeployFilledHelpersExtended:
    def test_first_filled_entry_empty(self):
        from release_platform.ui.helpers import first_filled_entry

        assert first_filled_entry({}) is None

    def test_first_filled_entry_returns_info(self):
        from release_platform.ui.helpers import first_filled_entry

        info = {"deployment_id": "uuid", "deployment_time": "10:00 AM"}
        assert first_filled_entry({"BDGyms": info}) == info


class TestResolveGroupedClient:
    def test_exact_match(self):
        from release_platform.ui.helpers import issues_for_filled_client, resolve_grouped_client

        grouped = {"BDGyms": [{"key": "PIC-1"}]}
        assert resolve_grouped_client("BDGyms", grouped) == "BDGyms"
        assert issues_for_filled_client("BDGyms", grouped) == [{"key": "PIC-1"}]

    def test_space_insensitive_match(self):
        from release_platform.ui.helpers import issues_for_filled_client, resolve_grouped_client

        grouped = {"BDGyms": [{"key": "PIC-5634"}]}
        assert resolve_grouped_client("BD Gyms", grouped) == "BDGyms"
        assert issues_for_filled_client("BD Gyms", grouped)[0]["key"] == "PIC-5634"

    def test_no_match_returns_empty(self):
        from release_platform.ui.helpers import issues_for_filled_client, resolve_grouped_client

        grouped = {"Jetts": [{"key": "PIC-1"}]}
        assert resolve_grouped_client("Unknown", grouped) is None
        assert issues_for_filled_client("Unknown", grouped) == []


class TestServiceDeskSupplementalFields:
    def test_supplemental_includes_assignment_group(self):
        import config
        import jira_client

        fields = {
            "customfield_13073": {"id": "12712"},
            "customfield_11752": [{"accountId": "abc"}],
        }
        with patch.object(
            config,
            "TCKT_FIELDS",
            {
                "assignment_group": "customfield_13073",
                "approvers": "customfield_11752",
            },
        ), patch.object(config, "SERVICE_DESK_CREATE_MODE", "full_form"):
            out = jira_client._build_supplemental_tckt_fields(fields)
        assert out["customfield_13073"] == {"id": "12712"}
        assert out["customfield_11752"] == [{"accountId": "abc"}]
