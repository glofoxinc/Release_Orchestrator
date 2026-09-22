"""Tests for jira_client.set_request_type_detailed() + RequestTypeStatus."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")

import config
from jira_client import RequestTypeStatus, set_request_type, set_request_type_detailed
from request_type_setter import SetRequestTypeResult


class TestRequestTypeStatus:
    def test_ok_shape(self):
        s = RequestTypeStatus(RequestTypeStatus.OK, "", http_status=201)
        assert s.ok
        assert s.status == "ok"
        assert s.http_status == 201

    def test_disabled_is_not_ok(self):
        s = RequestTypeStatus(RequestTypeStatus.DISABLED, "missing")
        assert not s.ok
        assert s.status == "disabled"

    def test_to_dict(self):
        s = RequestTypeStatus(RequestTypeStatus.FAILED, "e", http_status=500)
        d = s.to_dict()
        assert d == {"status": "failed", "message": "e", "http_status": 500}


class TestSetRequestTypeDetailed:
    def test_disabled_when_missing_env(self):
        with patch.object(config, "TCKT_SERVICE_DESK_ID", ""), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", ""):
            result = set_request_type_detailed("TCKT-1")
        assert result.status == RequestTypeStatus.DISABLED
        assert "TCKT_SERVICE_DESK_ID" in result.message

    def test_disabled_when_only_request_type_id_set(self):
        with patch.object(config, "TCKT_SERVICE_DESK_ID", ""), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "42"):
            result = set_request_type_detailed("TCKT-1")
        assert result.status == RequestTypeStatus.DISABLED

    def test_ok_when_already_set(self):
        with patch.object(config, "TCKT_SERVICE_DESK_ID", "15"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "1223"), \
             patch.object(config, "TCKT_REQUEST_TYPE_NAME", "Submit A Normal or Emergency Change"), \
             patch("jira_client.get_issue_request_type_id", return_value="1223"):
            result = set_request_type_detailed("TCKT-111620")
        assert result.status == RequestTypeStatus.OK
        assert result.ok
        assert "already set" in result.message

    def test_ok_uses_request_type_endpoint(self):
        with patch.object(config, "TCKT_SERVICE_DESK_ID", "15"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "1223"), \
             patch.object(config, "TCKT_REQUEST_TYPE_NAME", "Submit A Normal or Emergency Change"), \
             patch("jira_client.get_issue_request_type_id", return_value=None), \
             patch("request_type_setter.set_request_type") as mock_rt:
            mock_rt.return_value = SetRequestTypeResult(
                ok=True, last_status=200, message="request type applied"
            )
            result = set_request_type_detailed("TCKT-111620")
        assert result.status == RequestTypeStatus.OK
        assert result.ok
        assert "Submit A Normal or Emergency Change" in result.message
        mock_rt.assert_called_once()
        call_kw = mock_rt.call_args.kwargs
        assert call_kw["service_desk_id"] == "15"
        assert call_kw["request_type_id"] == "1223"

    def test_failed_on_404_endpoint_missing(self):
        with patch.object(config, "TCKT_SERVICE_DESK_ID", "15"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "1223"), \
             patch.object(config, "TCKT_REQUEST_TYPE_NAME", "Submit A Normal or Emergency Change"), \
             patch("jira_client.get_issue_request_type_id", return_value=None), \
             patch("request_type_setter.set_request_type") as mock_rt:
            mock_rt.return_value = SetRequestTypeResult(
                ok=False,
                last_status=404,
                message="permanent failure HTTP 404 — check service_desk_id and request_type_id",
            )
            result = set_request_type_detailed("TCKT-1")
        assert result.status == RequestTypeStatus.FAILED
        assert result.http_status == 404
        assert "does not support setting Request Type after create" in result.message

    def test_failed_on_permanent_error(self):
        with patch.object(config, "TCKT_SERVICE_DESK_ID", "15"), \
             patch.object(config, "TCKT_REQUEST_TYPE_ID", "1223"), \
             patch.object(config, "TCKT_REQUEST_TYPE_NAME", ""), \
             patch("jira_client.get_issue_request_type_id", return_value=None), \
             patch("request_type_setter.set_request_type") as mock_rt:
            mock_rt.return_value = SetRequestTypeResult(
                ok=False,
                last_status=400,
                message="permanent failure HTTP 400 — check service_desk_id and request_type_id",
            )
            result = set_request_type_detailed("TCKT-1")
        assert result.status == RequestTypeStatus.FAILED
        assert result.http_status == 400


class TestSetRequestTypeBackwardCompat:
    def test_returns_true_on_ok(self):
        with patch("jira_client.set_request_type_detailed",
                   return_value=RequestTypeStatus(RequestTypeStatus.OK)):
            assert set_request_type("TCKT-1") is True

    def test_returns_false_on_disabled(self):
        with patch("jira_client.set_request_type_detailed",
                   return_value=RequestTypeStatus(RequestTypeStatus.DISABLED, "m")):
            assert set_request_type("TCKT-1") is False
