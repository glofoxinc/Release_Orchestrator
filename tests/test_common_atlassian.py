"""Tests for the shared Atlassian REST client."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json

import pytest

from common.atlassian import (
    AtlassianClient,
    AtlassianCredentials,
    AtlassianError,
    AtlassianTransient,
    HttpResponse,
)

CREDS = AtlassianCredentials(
    email="alice@example.com",
    api_token="token-xyz",
    base_url="https://ex.atlassian.net",
)


def _fake_transport(script):
    """Build a transport that returns each response from ``script`` in turn."""
    calls = []

    def _call(method, url, payload, headers):
        calls.append({"method": method, "url": url, "payload": payload, "headers": dict(headers)})
        if not script:
            raise AssertionError("transport called more times than scripted")
        next_resp = script.pop(0)
        if isinstance(next_resp, Exception):
            raise next_resp
        return next_resp

    _call.calls = calls
    return _call


class TestCredentials:
    def test_basic_header_is_base64(self):
        h = CREDS.basic_header()
        assert h.startswith("Basic ")
        import base64
        decoded = base64.b64decode(h.split(" ", 1)[1]).decode()
        assert decoded == "alice@example.com:token-xyz"

    def test_from_env_happy_path(self, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "e@e")
        monkeypatch.setenv("JIRA_API_TOKEN", "tok")
        monkeypatch.setenv("JIRA_BASE_URL", "https://u")
        c = AtlassianCredentials.from_env()
        assert c.email == "e@e" and c.base_url == "https://u"

    def test_from_env_missing_var_raises(self, monkeypatch):
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        monkeypatch.delenv("JIRA_BASE_URL", raising=False)
        with pytest.raises(AtlassianError):
            AtlassianCredentials.from_env()


class TestRequestStatuses:
    def test_2xx_returns_response(self):
        t = _fake_transport([HttpResponse(200, '{"ok": true}', {})])
        c = AtlassianClient(CREDS, transport=t)
        resp = c.request("GET", "/rest/api/3/myself")
        assert resp.status == 200
        assert resp.json() == {"ok": True}

    def test_400_raises_non_transient(self):
        t = _fake_transport([HttpResponse(400, "bad", {})])
        c = AtlassianClient(CREDS, transport=t)
        with pytest.raises(AtlassianError) as exc:
            c.request("GET", "/rest/api/3/foo")
        assert exc.value.status == 400
        assert not isinstance(exc.value, AtlassianTransient)

    def test_429_raises_transient(self):
        t = _fake_transport([HttpResponse(429, "slow down", {})])
        c = AtlassianClient(CREDS, transport=t)
        with pytest.raises(AtlassianTransient):
            c.request("GET", "/x")

    def test_500_raises_transient(self):
        t = _fake_transport([HttpResponse(503, "down", {})])
        c = AtlassianClient(CREDS, transport=t)
        with pytest.raises(AtlassianTransient):
            c.request("GET", "/x")


class TestHeaderAuth:
    def test_auth_header_is_sent(self):
        t = _fake_transport([HttpResponse(200, "{}", {})])
        c = AtlassianClient(CREDS, transport=t)
        c.request("GET", "/x")
        sent = t.calls[0]["headers"]
        assert sent["Authorization"].startswith("Basic ")
        assert sent["Accept"] == "application/json"
        assert sent["User-Agent"]

    def test_payload_is_json_encoded_url_absolute(self):
        t = _fake_transport([HttpResponse(200, "{}", {})])
        c = AtlassianClient(CREDS, transport=t)
        c.request("POST", "https://other.example/x", {"k": 1})
        assert t.calls[0]["url"] == "https://other.example/x"
        assert t.calls[0]["payload"] == {"k": 1}


class TestJiraConvenience:
    def test_get_issue_path(self):
        t = _fake_transport([HttpResponse(200, '{"key": "X-1"}', {})])
        c = AtlassianClient(CREDS, transport=t)
        c.get_issue("X-1")
        assert t.calls[0]["url"].endswith("/rest/api/3/issue/X-1")

    def test_get_issue_fields_param(self):
        t = _fake_transport([HttpResponse(200, '{"key": "X-1"}', {})])
        c = AtlassianClient(CREDS, transport=t)
        c.get_issue("X-1", fields="summary,status")
        assert "fields=summary,status" in t.calls[0]["url"]

    def test_search_jql_payload(self):
        t = _fake_transport([HttpResponse(200, '{"issues": []}', {})])
        c = AtlassianClient(CREDS, transport=t)
        c.search_jql("project = X", fields=["summary"], max_results=10)
        p = t.calls[0]["payload"]
        assert p["jql"] == "project = X"
        assert p["fields"] == ["summary"]
        assert p["maxResults"] == 10

    def test_transition_issue_with_comment(self):
        t = _fake_transport([HttpResponse(204, "", {})])
        c = AtlassianClient(CREDS, transport=t)
        c.transition_issue("X-1", "31", comment="done")
        payload = t.calls[0]["payload"]
        assert payload["transition"]["id"] == "31"
        assert payload["update"]["comment"]

    def test_add_label(self):
        t = _fake_transport([HttpResponse(204, "", {})])
        c = AtlassianClient(CREDS, transport=t)
        c.add_label("X-1", "release-vX")
        payload = t.calls[0]["payload"]
        assert payload["update"]["labels"][0]["add"] == "release-vX"


class TestConfluenceConvenience:
    def test_create_page_payload(self):
        t = _fake_transport([HttpResponse(200, '{"id": "1"}', {})])
        c = AtlassianClient(CREDS, transport=t)
        c.confluence_create_page("SPACE", "Title", "<p>body</p>", parent_id="42")
        payload = t.calls[0]["payload"]
        assert payload["spaceId"] == "SPACE"
        assert payload["title"] == "Title"
        assert payload["parentId"] == "42"
        assert payload["body"]["representation"] == "storage"

    def test_update_page_payload(self):
        t = _fake_transport([HttpResponse(200, '{"id": "1"}', {})])
        c = AtlassianClient(CREDS, transport=t)
        c.confluence_update_page("1", title="T", storage_body="b", version_number=3)
        payload = t.calls[0]["payload"]
        assert payload["version"]["number"] == 3
        assert payload["title"] == "T"

    def test_find_page_by_title_returns_first(self):
        body = json.dumps({"results": [{"id": "99", "title": "T"}, {"id": "100"}]})
        t = _fake_transport([HttpResponse(200, body, {})])
        c = AtlassianClient(CREDS, transport=t)
        page = c.confluence_find_page_by_title("S", "T")
        assert page["id"] == "99"

    def test_find_page_by_title_returns_none_when_empty(self):
        t = _fake_transport([HttpResponse(200, '{"results": []}', {})])
        c = AtlassianClient(CREDS, transport=t)
        assert c.confluence_find_page_by_title("S", "Nothing") is None

    def test_find_page_url_encodes_title(self):
        t = _fake_transport([HttpResponse(200, '{"results": []}', {})])
        c = AtlassianClient(CREDS, transport=t)
        c.confluence_find_page_by_title("S", "Hello World")
        assert "Hello%20World" in t.calls[0]["url"]


class TestErrorShape:
    def test_error_has_status_and_url(self):
        t = _fake_transport([HttpResponse(404, "not found", {})])
        c = AtlassianClient(CREDS, transport=t)
        with pytest.raises(AtlassianError) as exc:
            c.request("GET", "/x")
        assert exc.value.status == 404
        assert exc.value.url.endswith("/x")
