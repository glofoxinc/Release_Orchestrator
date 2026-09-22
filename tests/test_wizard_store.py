"""Tests for mcp.wizard_store durable session persistence."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from release_mcp import wizard_store as ws


@pytest.fixture
def store_dir(tmp_path: Path):
    directory = tmp_path / "sessions"
    directory.mkdir()
    ws.set_sessions_dir_override(directory)
    ws.set_token_secret_override(b"test-secret")
    yield directory
    ws.set_sessions_dir_override(None)
    ws.set_token_secret_override(None)


class TestCreateResumeListUpdate:
    def test_create_resume_list_update(self, store_dir: Path):
        created = ws.create_session(
            "release_notes",
            step="select_version",
            inputs={"version": "2026.1.01.01"},
            deterministic="rn-1",
            directory=store_dir,
        )
        assert created["schema_version"] == ws.SCHEMA_VERSION
        assert created["status"] == ws.STATUS_ACTIVE
        assert created["inputs"]["version"] == "2026.1.01.01"
        assert (store_dir / f"{created['id']}.json").is_file()

        loaded = ws.load_session(created["id"], directory=store_dir)
        assert loaded["id"] == created["id"]
        assert loaded["workflow"] == "release_notes"
        assert loaded["step"] == "select_version"

        listed = ws.list_sessions(directory=store_dir)
        assert len(listed) == 1
        assert listed[0]["id"] == created["id"]

        updated = ws.update_session(
            created["id"],
            step="review",
            drafts={"notes": "draft body"},
            artifacts={"docx": "out.docx"},
            directory=store_dir,
        )
        assert updated["step"] == "review"
        assert updated["drafts"]["notes"] == "draft body"
        assert updated["artifacts"]["docx"] == "out.docx"
        assert updated["inputs"]["version"] == "2026.1.01.01"
        assert any(e["event"] == "updated" for e in updated["audit"])

        again = ws.load_session(created["id"], directory=store_dir)
        assert again["step"] == "review"
        assert again["updated_at"] >= created["created_at"]


class TestPersistenceAndWorkspaceScope:
    def test_persists_across_load(self, store_dir: Path):
        session = ws.create_session(
            "service_ticket",
            inputs={"summary": "Ship it"},
            deterministic="stk-1",
            directory=store_dir,
        )
        path = store_dir / f"{session['id']}.json"
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert on_disk["inputs"]["summary"] == "Ship it"
        assert on_disk["schema_version"] == ws.SCHEMA_VERSION

    def test_workspace_scoped_directory(self, tmp_path: Path):
        ws.set_sessions_dir_override(None)
        app_dir = tmp_path / "app"
        (app_dir / "workspaces" / "team_a").mkdir(parents=True)

        with patch.object(ws.config, "active_workspace_name", return_value=""):
            root_dir = ws.sessions_dir(app_dir=app_dir)
        assert root_dir == app_dir / ".mcp_wizard_sessions"
        assert root_dir.is_dir()

        with patch.object(ws.config, "active_workspace_name", return_value="team_a"):
            scoped = ws.sessions_dir(app_dir=app_dir)
        assert scoped == app_dir / "workspaces" / "team_a" / ".mcp_wizard_sessions"
        assert scoped.is_dir()

    def test_deterministic_session_ids(self, store_dir: Path):
        a = ws.create_session("wf", deterministic="same", directory=store_dir)
        with pytest.raises(ws.WizardStoreError):
            ws.create_session("wf", deterministic="same", directory=store_dir)
        assert a["id"] == ws.new_session_id(prefix="wf", deterministic="same")


class TestConfirmationTokens:
    def test_mint_validate_bound_to_workflow_step_preview(self):
        ws.set_token_secret_override(b"test-secret")
        preview = {"tickets": ["PIC-1"], "count": 1}
        token = ws.mint_confirmation_token(
            "release_notes",
            "confirm_create",
            preview,
            deterministic=True,
        )
        assert ws.validate_confirmation_token(token, "release_notes", "confirm_create", preview)
        assert not ws.validate_confirmation_token(token, "other_wf", "confirm_create", preview)
        assert not ws.validate_confirmation_token(token, "release_notes", "other_step", preview)
        assert not ws.validate_confirmation_token(token, "release_notes", "confirm_create", {"tickets": ["PIC-2"]})
        ws.set_token_secret_override(None)

    def test_update_invalidates_step_token(self, store_dir: Path):
        session = ws.create_session(
            "release_notes",
            step="confirm_create",
            deterministic="tok-1",
            directory=store_dir,
        )
        preview = {"ok": True}
        token = ws.mint_confirmation_token(
            session["workflow"],
            "confirm_create",
            preview,
            deterministic=True,
        )
        ws.update_session(
            session["id"],
            confirmations={"confirm_create": {"token": token, "preview_hash": ws.content_hash(preview)}},
            directory=store_dir,
        )
        # Second update (non-confirmation) must invalidate the step token.
        updated = ws.update_session(
            session["id"],
            inputs={"note": "changed"},
            directory=store_dir,
        )
        assert "confirm_create" not in updated["confirmations"]
        assert not ws.check_confirmation(
            session["id"],
            "confirm_create",
            token,
            preview,
            directory=store_dir,
        )

    def test_consume_confirmation_one_time(self, store_dir: Path):
        session = ws.create_session(
            "release_notes",
            step="confirm_create",
            deterministic="tok-consume",
            directory=store_dir,
        )
        preview = {"ok": True}
        session = ws.store_confirmation(
            session["id"],
            "confirm_create",
            preview,
            directory=store_dir,
        )
        token = session["confirmations"]["confirm_create"]["token"]
        ws.consume_confirmation(
            session["id"],
            "confirm_create",
            token,
            preview,
            directory=store_dir,
        )
        assert not ws.check_confirmation(
            session["id"],
            "confirm_create",
            token,
            preview,
            directory=store_dir,
        )
        with pytest.raises(ws.ConfirmationConsumedError):
            ws.consume_confirmation(
                session["id"],
                "confirm_create",
                token,
                preview,
                directory=store_dir,
            )

    def test_terminal_session_guard(self, store_dir: Path):
        session = ws.create_session("wf", deterministic="term-1", directory=store_dir)
        session = ws.update_session(
            session["id"],
            status=ws.STATUS_COMPLETED,
            directory=store_dir,
        )
        with pytest.raises(ws.TerminalSessionError):
            ws.assert_session_mutable(session)


class TestCancelAndDelete:
    def test_cancel_and_delete(self, store_dir: Path):
        session = ws.create_session("deployer", deterministic="cxl-1", directory=store_dir)
        cancelled = ws.cancel_session(session["id"], reason="user_abort", directory=store_dir)
        assert cancelled["status"] == ws.STATUS_CANCELLED
        assert any(e["event"] == "cancelled" for e in cancelled["audit"])

        active = ws.list_sessions(status=ws.STATUS_ACTIVE, directory=store_dir)
        assert active == []
        listed = ws.list_sessions(status=ws.STATUS_CANCELLED, directory=store_dir)
        assert len(listed) == 1

        assert ws.delete_session(session["id"], directory=store_dir) is True
        assert ws.delete_session(session["id"], directory=store_dir) is False
        with pytest.raises(ws.SessionNotFoundError):
            ws.load_session(session["id"], directory=store_dir)


class TestPathTraversal:
    def test_rejects_traversal_session_ids(self, store_dir: Path):
        for bad in ("../escape", "..\\escape", "a/b", "a\\b", "../../etc/passwd"):
            with pytest.raises(ws.InvalidSessionIdError):
                ws._session_path(bad, directory=store_dir)
            with pytest.raises(ws.InvalidSessionIdError):
                ws.load_session(bad, directory=store_dir)

    def test_rejects_unsafe_workspace_name(self, tmp_path: Path):
        ws.set_sessions_dir_override(None)
        with patch.object(ws.config, "active_workspace_name", return_value="../outside"):
            with pytest.raises(ws.InvalidSessionIdError):
                ws.sessions_dir(app_dir=tmp_path)


class TestCorruptedJson:
    def test_load_raises_on_corrupt_json(self, store_dir: Path):
        session = ws.create_session("wf", deterministic="bad-1", directory=store_dir)
        path = store_dir / f"{session['id']}.json"
        path.write_text("{not-json", encoding="utf-8")
        with pytest.raises(ws.SessionCorruptError):
            ws.load_session(session["id"], directory=store_dir)

    def test_list_skips_corrupt_files(self, store_dir: Path):
        good = ws.create_session("wf", deterministic="good-1", directory=store_dir)
        (store_dir / "broken.json").write_text("{nope", encoding="utf-8")
        (store_dir / "also-broken.json").write_text('{"id": "x"}', encoding="utf-8")
        listed = ws.list_sessions(directory=store_dir)
        assert [item["id"] for item in listed] == [good["id"]]


class TestContentHashAndSafeSlug:
    def test_content_hash_stable(self):
        assert ws.content_hash({"b": 1, "a": 2}) == ws.content_hash({"a": 2, "b": 1})
        assert ws.content_hash({"a": 1}) != ws.content_hash({"a": 2})

    def test_safe_slug(self):
        assert ws.safe_slug("Hello World!") == "hello-world"
        assert ws.safe_slug("") == "session"
        assert ws.safe_slug("../Evil") == "evil"
