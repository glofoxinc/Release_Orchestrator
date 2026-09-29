"""Tests for Jira component resolution."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


class TestResolveComponent:
    def test_exact_match(self):
        import jira_client

        jira_client._component_cache.clear()
        with patch(
            "jira_client._get",
            return_value=[{"id": "1", "name": "Dashboard"}, {"id": "2", "name": "API"}],
        ):
            assert jira_client.resolve_component("PIC", "Dashboard") == {"name": "Dashboard"}

    def test_general_returns_none(self):
        import jira_client

        assert jira_client.resolve_component("PIC", "General") is None
        assert jira_client.resolve_component("PIC", "") is None

    def test_partial_match(self):
        import jira_client

        jira_client._component_cache.clear()
        with patch(
            "jira_client._get",
            return_value=[{"id": "1", "name": "Data Pipeline"}],
        ):
            assert jira_client.resolve_component("PIC", "pipeline") == {"name": "Data Pipeline"}
