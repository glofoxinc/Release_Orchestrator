"""Tests for Jira Service Desk discovery helpers."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

import config
import jira_client


class TestListServiceDesks:
    def test_returns_values_list(self):
        payload = {
            "values": [
                {"id": "3", "projectKey": "TCKT", "projectName": "Change Tickets"},
                {"id": "7", "projectKey": "HELP", "projectName": "Help Desk"},
            ]
        }
        with patch.object(config, "JIRA_SD_API_URL", "https://x.example/rest/servicedeskapi"), \
             patch("jira_client._sd_get", return_value=payload):
            desks = jira_client.list_service_desks()
        assert len(desks) == 2
        assert desks[0]["projectKey"] == "TCKT"

    def test_empty_when_no_values(self):
        with patch("jira_client._sd_get", return_value={}):
            assert jira_client.list_service_desks() == []


class TestListRequestTypes:
    def test_returns_request_types(self):
        payload = {"values": [{"id": "101", "name": "Submit a normal or emergency change"}]}
        with patch("jira_client._sd_get", return_value=payload) as mock_get:
            rts = jira_client.list_request_types("3")
        mock_get.assert_called_once_with("/servicedesk/3/requesttype")
        assert rts[0]["id"] == "101"

    def test_empty_when_no_service_desk_id(self):
        assert jira_client.list_request_types("") == []


class TestFindServiceDeskForProject:
    def test_finds_matching_project_key(self):
        desks = [
            {"id": "3", "projectKey": "TCKT", "projectName": "Changes"},
            {"id": "7", "projectKey": "HELP", "projectName": "Help"},
        ]
        with patch("jira_client.list_service_desks", return_value=desks):
            found = jira_client.find_service_desk_for_project("tckt")
        assert found is not None
        assert found["id"] == "3"

    def test_returns_none_when_not_found(self):
        with patch("jira_client.list_service_desks", return_value=[]):
            assert jira_client.find_service_desk_for_project("TCKT") is None
