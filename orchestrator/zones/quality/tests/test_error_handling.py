"""Tests for error handling — simulated Jira API failures, malformed data, timeouts."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")

import jira_client


def _mock_response(status_code: int, json_body=None, headers=None) -> MagicMock:
    """Build a fake requests.Response with the given status code."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.ok = 200 <= status_code < 300
    resp.content = b'{"error":"mocked"}' if json_body is not None else b""
    resp.json.return_value = json_body if json_body is not None else {}
    resp.request = MagicMock(method="GET", path_url="/mock")
    resp.raise_for_status.side_effect = (
        None if 200 <= status_code < 300
        else requests.HTTPError(response=resp)
    )
    return resp


# ── 401 Unauthorized ──────────────────────────────────────────────────

class TestUnauthorized:
    @patch("jira_client.requests.get")
    def test_get_versions_401(self, mock_get):
        mock_get.return_value = _mock_response(401)
        with pytest.raises(jira_client.JiraApiError, match="authentication failed"):
            jira_client.get_project_versions("PROJ")

    @patch("jira_client.build_scoped_version_jql", return_value="project = PROJ AND fixVersion = 12345 ORDER BY key ASC")
    @patch("jira_client.requests.post")
    def test_post_search_401(self, mock_post, _build):
        mock_post.return_value = _mock_response(401)
        with pytest.raises(jira_client.JiraApiError, match="authentication failed"):
            jira_client.get_issues_for_version("PROJ", "12345")


# ── 404 Not Found ────────────────────────────────────────────────────

class TestNotFound:
    @patch("jira_client.requests.get")
    def test_get_transitions_404(self, mock_get):
        mock_get.return_value = _mock_response(404)
        with pytest.raises(jira_client.JiraApiError, match="Not found"):
            jira_client.get_transitions("PROJ-999")

    @patch("jira_client.requests.post")
    def test_add_comment_404(self, mock_post):
        mock_post.return_value = _mock_response(404)
        with pytest.raises(jira_client.JiraApiError, match="Not found"):
            jira_client.add_deployment_comment("BAD-1", "Apr 1", "10:00 AM", "uuid-x")


# ── 500 Internal Server Error ────────────────────────────────────────

class TestServerError:
    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.get")
    def test_get_versions_500_retries_then_fails(self, mock_get, mock_sleep):
        mock_get.return_value = _mock_response(500)
        with pytest.raises(jira_client.JiraApiError, match="server error"):
            jira_client.get_project_versions("PROJ")
        assert mock_get.call_count == jira_client._MAX_RETRIES + 1

    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.post")
    def test_create_issue_500_retries_then_fails(self, mock_post, mock_sleep):
        mock_post.return_value = _mock_response(500)
        with pytest.raises(jira_client.JiraApiError, match="server error"):
            jira_client.create_issue("PROJ", "10001", "Summary", {})
        assert mock_post.call_count == jira_client._MAX_RETRIES + 1

    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.get")
    def test_502_retries_then_succeeds(self, mock_get, mock_sleep):
        bad_resp = _mock_response(502)
        ok_resp = _mock_response(200, json_body=[])
        mock_get.side_effect = [bad_resp, ok_resp]
        result = jira_client.get_project_versions("PROJ")
        assert result == []
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1

    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.get")
    def test_503_retries_then_succeeds(self, mock_get, mock_sleep):
        bad_resp = _mock_response(503)
        ok_resp = _mock_response(200, json_body=[])
        mock_get.side_effect = [bad_resp, ok_resp]
        result = jira_client.get_project_versions("PROJ")
        assert result == []
        assert mock_get.call_count == 2
        assert mock_sleep.call_count == 1


# ── 429 Rate Limiting & Retry ────────────────────────────────────────

class TestRateLimiting:
    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.get")
    def test_retries_on_429_then_succeeds(self, mock_get, mock_sleep):
        rate_resp = _mock_response(429, headers={"Retry-After": "1"})
        rate_resp.raise_for_status.side_effect = None
        ok_resp = _mock_response(200, json_body={"transitions": []})
        mock_get.side_effect = [rate_resp, ok_resp]

        result = jira_client.get_transitions("PROJ-1")
        assert result == []
        mock_sleep.assert_called_once_with(1)


# ── Timeout Handling ─────────────────────────────────────────────────

class TestTimeoutHandling:
    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.get")
    def test_connection_error_retries_then_raises_friendly(self, mock_get, mock_sleep):
        mock_get.side_effect = requests.ConnectionError("Connection refused")
        with pytest.raises(jira_client.JiraApiError, match="Cannot reach Jira"):
            jira_client.get_project_versions("PROJ")
        assert mock_get.call_count == jira_client._MAX_RETRIES + 1

    @patch("jira_client.build_scoped_version_jql", return_value="project = PROJ AND fixVersion = 123 ORDER BY key ASC")
    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.post")
    def test_timeout_retries_then_raises_friendly(self, mock_post, mock_sleep, _build):
        mock_post.side_effect = requests.Timeout("Read timed out")
        with pytest.raises(jira_client.JiraApiError, match="timed out"):
            jira_client.get_issues_for_version("PROJ", "123")
        assert mock_post.call_count == jira_client._MAX_RETRIES + 1

    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.get")
    def test_connection_error_recovers_on_retry(self, mock_get, mock_sleep):
        ok_resp = _mock_response(200, json_body=[])
        mock_get.side_effect = [requests.ConnectionError("blip"), ok_resp]
        result = jira_client.get_project_versions("PROJ")
        assert isinstance(result, list)
        assert mock_sleep.call_count == 1


# ── User-Friendly Error Messages ─────────────────────────────────────

class TestFriendlyErrors:
    @patch("jira_client.requests.get")
    def test_403_gives_permission_message(self, mock_get):
        mock_get.return_value = _mock_response(403)
        with pytest.raises(jira_client.JiraApiError, match="Permission denied"):
            jira_client.get_project_versions("PROJ")

    @patch("jira_client.requests.get")
    def test_unknown_status_gives_generic_message(self, mock_get):
        mock_get.return_value = _mock_response(418)
        with pytest.raises(jira_client.JiraApiError, match="HTTP 418"):
            jira_client.get_project_versions("PROJ")

    def test_jira_api_error_has_status_code(self):
        err = jira_client.JiraApiError("test", status_code=401)
        assert err.status_code == 401
        assert str(err) == "test"

    def test_jira_api_error_preserves_original(self):
        original = requests.HTTPError("original")
        err = jira_client.JiraApiError("wrapped", original=original)
        assert err.original is original


# ── HTTP 400 detail surfacing ────────────────────────────────────────

class TestBadRequestDetail:
    @patch("jira_client.requests.post")
    def test_400_includes_field_errors_from_jira(self, mock_post):
        mock_post.return_value = _mock_response(400, {
            "errorMessages": [],
            "errors": {"customfield_11763": "Invalid date format."},
        })
        with pytest.raises(jira_client.JiraApiError) as excinfo:
            jira_client.create_issue("TCKT", "10502", "Deploy", {})

        err = excinfo.value
        assert err.status_code == 400
        assert err.field_errors == {"customfield_11763": "Invalid date format."}
        assert "Invalid date format." in str(err)
        assert "customfield_11763" in str(err)
        assert "Check your connection" not in str(err)

    @patch("jira_client.requests.post")
    def test_400_includes_service_desk_error_message(self, mock_post):
        mock_post.return_value = _mock_response(400, {
            "errorMessage": "Field 'customfield_13073' cannot be set.",
        })
        with pytest.raises(jira_client.JiraApiError, match="cannot be set"):
            jira_client.create_issue("TCKT", "10502", "Deploy", {})

    @patch("jira_client.requests.post")
    def test_non_json_body_falls_back_to_text(self, mock_post):
        resp = _mock_response(400)
        resp.json.side_effect = ValueError("not json")
        resp.text = "<html>Bad Request</html>"
        mock_post.return_value = resp
        with pytest.raises(jira_client.JiraApiError, match="Bad Request"):
            jira_client.create_issue("TCKT", "10502", "Deploy", {})

    @patch("jira_client.requests.post")
    def test_400_recovers_field_id_from_service_desk_prose(self, mock_post):
        """JSM names the field in the message rather than in an errors map."""
        mock_post.return_value = _mock_response(400, {
            "errorMessage": (
                "Unable to create request because of these errors : Field with id "
                "'customfield_14549' named 'Business Impact' has these errors : []"
            ),
        })
        with pytest.raises(jira_client.JiraApiError) as excinfo:
            jira_client.create_issue("TCKT", "10502", "Deploy", {})

        assert "customfield_14549" in excinfo.value.field_errors

    def test_field_ids_in_message_handles_both_shapes(self):
        assert jira_client._field_ids_in_message(
            "Field with id 'customfield_14549' named 'Business Impact'"
        ) == ["customfield_14549"]
        assert jira_client._field_ids_in_message(
            "customfield_11760 and customfield_11762 are invalid"
        ) == ["customfield_11760", "customfield_11762"]
        assert jira_client._field_ids_in_message("no fields here") == []

    def test_field_label_names_known_tckt_fields(self):
        import config

        with patch.object(config, "TCKT_FIELDS", {"planned_start": "customfield_11763"}):
            assert jira_client.field_label("customfield_11763") == (
                "customfield_11763 (planned start)"
            )
            assert jira_client.field_label("customfield_99999") == "customfield_99999"


# ── Malformed Input Data ─────────────────────────────────────────────

class TestMalformedData:
    def test_group_issues_missing_fields(self):
        issues = [{"key": "T-1", "fields": {}}]
        groups = jira_client.group_issues_by_client(issues)
        assert "Unknown" in groups

    def test_group_by_assignee_missing_assignee_key(self):
        issues = [{"key": "T-1", "fields": {}}]
        groups = jira_client.group_issues_by_assignee(issues)
        assert "Unassigned" in groups

    def test_has_deployment_comment_raises_on_api_failure(self):
        with patch.object(
            jira_client, "_fetch_comments_page", side_effect=Exception("API boom"),
        ):
            with pytest.raises(jira_client.CommentCheckError):
                jira_client.has_deployment_comment("PROJ-1")
