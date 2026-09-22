"""Tests for Phase 4–5: session persistence, cancel meeting, SharePoint paths, TCKT profiles."""

from __future__ import annotations

import os
import sys
from datetime import date, time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token-not-placeholder")


class TestReleaseSession:
    def test_save_and_restore_release_session(self, monkeypatch, tmp_path):
        import release_session as rs

        draft_file = tmp_path / ".deploy_draft.json"
        monkeypatch.setattr(rs.deploy_draft, "draft_path", lambda app_dir=None: str(draft_file))

        state = {
            "wiz_release": "2026.3.09.30",
            "shared_teams_review_event_id": "evt-1",
            "stk_planned_start_date": date(2026, 3, 30),
            "stk_planned_start_time": time(10, 0),
        }
        rs.save_release_session(state)
        loaded = rs.load_release_session()
        assert loaded is not None
        assert loaded.get("release_session", {}).get("shared_teams_review_event_id") == "evt-1"

        restored: dict = {}
        rs.apply_release_session(restored, loaded)
        assert restored.get("shared_teams_review_event_id") == "evt-1"


class TestCancelMeeting:
    def test_cancel_dry_run(self):
        import teams_schedule as ts

        cfg = ts.TeamsScheduleConfig(enabled=True, organizer_upn="org@example.com")
        result = ts.cancel_meeting(cfg, "evt-99", dry_run=True)
        assert result.ok is True
        assert result.dry_run is True


class TestSharePointPaths:
    def test_quarter_folder_and_remote_name(self):
        import sharepoint_upload as sp

        cfg = sp.SharePointUploadConfig(
            folder_path="Release Notes/{{quarter}}",
            remote_name_template="Release Notes {{version}}.docx",
        )
        folder = sp.resolve_folder_path(cfg, reference_date=date(2026, 8, 15))
        assert folder == "Release Notes/2026 - Q3"
        name = sp.default_remote_name("v2026.3.09.30", cfg.remote_name_template)
        assert name == "Release Notes 2026.3.09.30.docx"


class TestReleaseDefaults:
    def test_last_schedule_window_roundtrip(self, monkeypatch, tmp_path):
        import release_defaults as rd

        target = tmp_path / ".release_defaults.json"
        monkeypatch.setattr(rd, "defaults_path", lambda app_dir=None: str(target))
        rd.save_last_schedule_window(
            start_date=date(2026, 3, 30),
            start_time=time(10, 0),
            end_date=date(2026, 3, 30),
            end_time=time(13, 0),
            timezone_name="Asia/Kolkata",
        )
        loaded = rd.load_last_schedule_window()
        assert loaded is not None
        assert loaded["start_time"] == time(10, 0)
        assert loaded["end_time"] == time(13, 0)


class TestAttendeeGroups:
    def test_load_attendee_groups(self, monkeypatch):
        import config
        import teams_meeting_content as tmc

        monkeypatch.setattr(
            config,
            "TEAMS_SCHEDULE",
            {
                "attendee_groups": {
                    "review_core": [{"email": "a@x.com", "name": "Alice"}],
                },
                "templates": {"review": {"attendee_groups": ["review_core"]}},
            },
        )
        groups = tmc.load_attendee_groups()
        assert "review_core" in groups
        merged = tmc.attendees_for_groups(tmc.template_attendee_groups("review"))
        assert merged[0].email == "a@x.com"
