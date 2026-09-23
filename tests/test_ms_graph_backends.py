"""Tests for Microsoft Graph / SharePoint upload / Teams schedule backends."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import sharepoint_upload as sp
import teams_schedule as ts
from ms_graph import GraphClient, GraphCredentials


def test_graph_credentials_from_env(monkeypatch):
    monkeypatch.setenv("MS_GRAPH_TENANT_ID", "tenant-1")
    monkeypatch.setenv("MS_GRAPH_CLIENT_ID", "client-1")
    monkeypatch.setenv("MS_GRAPH_CLIENT_SECRET", "secret-1")
    creds = GraphCredentials.from_env()
    assert creds.configured()
    assert "tenant-1" in creds.token_url()


def test_graph_credentials_aliases(monkeypatch):
    monkeypatch.delenv("MS_GRAPH_TENANT_ID", raising=False)
    monkeypatch.delenv("MS_GRAPH_CLIENT_ID", raising=False)
    monkeypatch.delenv("MS_GRAPH_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("MICROSOFT_TENANT_ID", "t2")
    monkeypatch.setenv("MICROSOFT_CLIENT_ID", "c2")
    monkeypatch.setenv("MICROSOFT_CLIENT_SECRET", "s2")
    assert GraphCredentials.from_env().configured()


def test_graph_request_retries_on_429():
    attempts: list[int] = []

    def http_transport(method, url, headers, body):
        attempts.append(1)
        if len(attempts) == 1:
            return 429, {"error": {"code": "TooManyRequests"}}
        return 200, {"value": []}

    client = GraphClient(
        credentials=GraphCredentials("t", "c", "s"),
        token_transport=lambda url, form: (200, {"access_token": "tok", "expires_in": 3600}),
        http_transport=http_transport,
    )
    status, body = client.request("GET", "/users")
    assert status == 200
    assert body == {"value": []}
    assert len(attempts) == 2


def test_graph_token_cached(monkeypatch):
    calls: list[str] = []

    def token_transport(url: str, form: dict) -> tuple[int, dict]:
        calls.append(url)
        return 200, {"access_token": "tok", "expires_in": 3600, "token_type": "Bearer"}

    client = GraphClient(
        credentials=GraphCredentials("t", "c", "s"),
        token_transport=token_transport,
    )
    assert client.get_access_token() == "tok"
    assert client.get_access_token() == "tok"
    assert len(calls) == 1


def test_graph_status_missing():
    client = GraphClient(credentials=GraphCredentials())
    status = client.status()
    assert status["configured"] is False
    assert "MS_GRAPH_TENANT_ID" in status["missing"]


def test_sanitize_remote_name():
    assert sp.sanitize_remote_name("Release Notes 2026.3.08.14.docx").endswith(".docx")
    assert sp.sanitize_remote_name("bad/name?.txt").endswith(".docx")
    assert "name" in sp.sanitize_remote_name("bad/name?.txt")


def test_build_upload_url_encodes_segments():
    url = sp.build_upload_url("drive1", "Release Notes/2026", "Notes A.docx")
    assert url.startswith("/drives/drive1/root:/")
    assert "Release%20Notes" in url
    assert url.endswith(":/content")


def test_plan_and_dry_run_upload(tmp_path: Path):
    doc = tmp_path / "Release Notes.docx"
    doc.write_bytes(b"PK fake docx")
    cfg = sp.load_upload_config(
        {
            "enabled": False,
            "drive_id": "drv",
            "folder_path": "Release Notes",
        },
        graph=GraphClient(credentials=GraphCredentials()),
    )
    plan = sp.plan_upload(cfg, str(doc))
    assert plan.remote_name.endswith(".docx")
    assert plan.bytes_size > 0

    result = sp.upload_release_notes(cfg, str(doc), dry_run=True)
    assert result.ok
    assert result.dry_run
    assert result.plan is not None


def test_live_upload_with_mock_graph(tmp_path: Path):
    doc = tmp_path / "notes.docx"
    doc.write_bytes(b"docx-bytes")

    def token_transport(url: str, form: dict) -> tuple[int, dict]:
        return 200, {"access_token": "tok", "expires_in": 3600}

    def http_transport(method, url, headers, body):
        assert method == "PUT"
        assert "drives/drv" in url
        assert body == b"docx-bytes"
        return 201, {
            "id": "item-1",
            "webUrl": "https://contoso.sharepoint.com/sites/x/Release%20Notes/notes.docx",
        }

    client = GraphClient(
        credentials=GraphCredentials("t", "c", "s"),
        token_transport=token_transport,
        http_transport=http_transport,
    )
    cfg = sp.load_upload_config(
        {"enabled": True, "drive_id": "drv", "folder_path": "Release Notes"},
        graph=client,
    )
    result = sp.upload_release_notes(cfg, str(doc), dry_run=False)
    assert result.ok
    assert not result.dry_run
    assert result.item_id == "item-1"
    assert "sharepoint.com" in result.web_url


def test_sharepoint_status_disabled():
    cfg = sp.load_upload_config({"enabled": False}, graph=GraphClient(credentials=GraphCredentials()))
    status = sp.status(cfg)
    assert status["feature"] == "sharepoint_upload"
    assert status["enabled"] is False
    assert status["can_upload"] is False


def test_download_sharepoint_by_web_url_with_mock_graph():
    def token_transport(url: str, form: dict) -> tuple[int, dict]:
        return 200, {"access_token": "tok", "expires_in": 3600}

    def http_transport(method, url, headers, body):
        assert method == "GET"
        assert "/shares/u!" in url
        assert url.endswith("/driveItem/content")
        return 200, b"PK-docx"

    client = GraphClient(
        credentials=GraphCredentials("t", "c", "s"),
        token_transport=token_transport,
        http_transport=http_transport,
    )
    cfg = sp.load_upload_config({"enabled": True}, graph=client)
    data = sp.download_by_web_url(
        cfg,
        "https://contoso.sharepoint.com/sites/x/Release%20Notes/notes.docx",
    )
    assert data == b"PK-docx"


def test_teams_draft_and_payload():
    cfg = ts.load_schedule_config(
        {
            "enabled": False,
            "organizer_upn": "owner@example.com",
            "default_timezone": "Asia/Kolkata",
            "review_duration_minutes": 30,
            "default_attendees": [{"email": "a@example.com", "name": "A"}],
        },
        graph=GraphClient(credentials=GraphCredentials()),
    )
    draft = ts.build_meeting_draft(
        cfg,
        kind="review",
        subject="",
        start=datetime(2026, 8, 14, 11, 0, 0),
        version="2026.3.08.14",
    )
    assert "Review" in draft.subject
    assert draft.end > draft.start
    assert len(draft.attendees) == 1
    payload = ts.build_graph_event_payload(draft)
    assert payload["isOnlineMeeting"] is True
    assert payload["onlineMeetingProvider"] == "teamsForBusiness"
    assert payload["attendees"][0]["emailAddress"]["address"] == "a@example.com"


def test_teams_schedule_dry_run():
    cfg = ts.load_schedule_config(
        {"enabled": False, "organizer_upn": "owner@example.com"},
        graph=GraphClient(credentials=GraphCredentials()),
    )
    draft = ts.build_meeting_draft(
        cfg,
        kind="deployment",
        subject="Deploy window",
        start=datetime(2026, 8, 14, 15, 0, 0),
    )
    result = ts.schedule_meeting(cfg, draft, dry_run=True)
    assert result.ok and result.dry_run
    assert result.graph_payload is not None


def test_teams_schedule_live_mock():
    def token_transport(url: str, form: dict) -> tuple[int, dict]:
        return 200, {"access_token": "tok", "expires_in": 3600}

    def http_transport(method, url, headers, body):
        assert method == "POST"
        assert "/users/" in url and "/events" in url
        return 201, {
            "id": "evt-1",
            "webLink": "https://outlook.office.com/item/1",
            "onlineMeeting": {"joinUrl": "https://teams.microsoft.com/l/meetup-join/xxx"},
        }

    client = GraphClient(
        credentials=GraphCredentials("t", "c", "s"),
        token_transport=token_transport,
        http_transport=http_transport,
    )
    cfg = ts.load_schedule_config(
        {"enabled": True, "organizer_upn": "owner@example.com"},
        graph=client,
    )
    draft = ts.build_meeting_draft(
        cfg,
        kind="review",
        subject="Review",
        start=datetime(2026, 8, 14, 11, 0, 0),
    )
    result = ts.schedule_meeting(cfg, draft, dry_run=False)
    assert result.ok
    assert result.event_id == "evt-1"
    assert "teams.microsoft.com" in result.join_url


def test_mcp_ops_status_imports(monkeypatch):
    from release_mcp import sharepoint_ops, teams_ops

    monkeypatch.setattr("integration_archive.is_archived", lambda _id: False)
    sp_status = sharepoint_ops.sharepoint_upload_status()
    assert "feature" in sp_status or sp_status.get("enabled") is not None
    ts_status = teams_ops.teams_schedule_status()
    assert "feature" in ts_status or ts_status.get("enabled") is not None


def test_mcp_teams_ops_invalid_kind(monkeypatch):
    from release_mcp import teams_ops

    monkeypatch.setattr("release_mcp.teams_ops.is_archived", lambda _id: False)
    out = teams_ops.teams_schedule_meeting(kind="standup", start="2026-08-14T11:00:00")
    assert out["ok"] is False
    assert "kind" in out["error"]
