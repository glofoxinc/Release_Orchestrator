"""Efficiency workstream: shared deploy executor parity, call counts, rate limits."""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock, patch

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")

import deploy_ops
import jira_client


def _issue(key: str, done: bool = False) -> dict:
    return {
        "key": key,
        "fields": {
            "status": {
                "name": "Done" if done else "In Progress",
                "statusCategory": {"key": "done" if done else "indeterminate"},
            }
        },
    }


def _verified_body() -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "The change has been deployed to Production on 2026-08-10 "
                            "at 10:00. and changes are reflecting the Production and "
                            "verified Deployment ID: abc"
                        ),
                    }
                ],
            }
        ],
    }


def _mock_response(status_code: int, json_body=None, headers=None) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.ok = 200 <= status_code < 300
    resp.content = b"{}" if json_body is not None else b""
    resp.json.return_value = json_body if json_body is not None else {}
    resp.request = MagicMock(method="GET", path_url="/mock")
    resp.raise_for_status.side_effect = None if 200 <= status_code < 300 else requests.HTTPError(response=resp)
    return resp


class TestDeployExecutorParity:
    def test_progress_callback_and_identical_outcomes(self, tmp_path, monkeypatch):
        import deployment_history as dh

        hist = tmp_path / ".deployment_history.json"
        monkeypatch.setattr(dh, "history_path", lambda app_dir=None: str(hist))

        filled = {
            "PIC": {
                "deployment_date": "2026-08-10",
                "deployment_time": "10:00",
                "deployment_id": "D-1",
            }
        }
        issues = [_issue("PIC-1"), _issue("PIC-2", done=True)]
        tickets = deploy_ops.build_tickets_to_process(
            filled=filled,
            selected_keys={"PIC-1", "PIC-2"},
            project_key="PIC",
            issues=issues,
            multi_client=False,
        )

        progress_events: list[tuple[int, int, str]] = []

        with (
            patch(
                "deploy_ops.jira_client.check_deployment_comments",
                return_value=({"PIC-1": False, "PIC-2": False}, {}),
            ),
            patch("deploy_ops.jira_client.add_deployment_comment", return_value={"id": "c1"}),
            patch("deploy_ops.jira_client.transition_to_done", return_value=True),
        ):
            with_progress = deploy_ops.execute_deploy(
                tickets,
                filled=filled,
                release={"name": "R", "id": "1"},
                project_key="PIC",
                selected_keys={"PIC-1", "PIC-2"},
                issues=issues,
                on_progress=lambda c, t, m: progress_events.append((c, t, m)),
            )

        with (
            patch(
                "deploy_ops.jira_client.check_deployment_comments",
                return_value=({"PIC-1": False, "PIC-2": False}, {}),
            ),
            patch("deploy_ops.jira_client.add_deployment_comment", return_value={"id": "c1"}),
            patch("deploy_ops.jira_client.transition_to_done", return_value=True),
        ):
            without = deploy_ops.execute_deploy(
                tickets,
                filled=filled,
                release={"name": "R", "id": "1"},
                project_key="PIC",
                selected_keys={"PIC-1", "PIC-2"},
                issues=issues,
            )

        assert with_progress["success"] == without["success"] == 2
        assert with_progress["skipped"] == without["skipped"]
        assert with_progress["errors"] == without["errors"]
        assert with_progress["log"] == without["log"]
        assert [u["key"] for u in with_progress["undo_data"]] == [u["key"] for u in without["undo_data"]]
        assert progress_events[0] == (1, 2, "PIC-1")
        assert progress_events[-1] == (2, 2, "Complete!")

    def test_undo_progress_callback(self):
        events: list[str] = []
        undo_data = [
            {"key": "PIC-1", "comment_id": "c1", "prev_status": "In Progress", "transitioned": True},
        ]
        with (
            patch("deploy_ops.jira_client.delete_comment"),
            patch("deploy_ops.jira_client.find_transition_by_name", return_value="21"),
            patch("deploy_ops.jira_client.transition_issue"),
        ):
            result = deploy_ops.undo_deploy(
                undo_data,
                on_progress=lambda c, t, m: events.append(m),
            )
        assert result["ok"] == 1
        assert "PIC-1" in events
        assert events[-1] == "Complete!"


class TestRecentCommentsFirst:
    def test_marker_in_recent_window_avoids_full_scan(self):
        """Probe + recent page only when marker is among newest comments."""
        pages: list[tuple[int, int]] = []

        def fake_page(issue_key, *, start_at, max_results):
            pages.append((start_at, max_results))
            if start_at == 0 and max_results == 1:
                return {"total": 80, "comments": [{"id": "old", "body": {"type": "doc", "content": []}}]}
            # Recent tail includes verified marker
            return {
                "total": 80,
                "comments": [
                    {"id": "mid", "body": {"type": "doc", "content": []}},
                    {"id": "new", "body": _verified_body()},
                ],
            }

        with (
            patch.object(jira_client, "_fetch_comments_page", side_effect=fake_page),
            patch.object(jira_client, "_iter_all_comments") as full,
        ):
            found = jira_client.get_verified_deployment_comment_id("PIC-9")
        assert found == "new"
        assert pages == [(0, 1), (55, 25)]  # total 80 → start 55, window 25
        full.assert_not_called()

    def test_fallback_full_scan_when_marker_older(self):
        def fake_page(issue_key, *, start_at, max_results):
            if start_at == 0 and max_results == 1:
                return {"total": 40, "comments": [{"id": "1", "body": {}}]}
            return {
                "total": 40,
                "comments": [{"id": "r", "body": {"type": "doc", "content": []}}],
            }

        with (
            patch.object(jira_client, "_fetch_comments_page", side_effect=fake_page),
            patch.object(
                jira_client,
                "_iter_all_comments",
                return_value=[
                    {"id": "old-marker", "body": _verified_body()},
                    {"id": "later", "body": {}},
                ],
            ) as full,
        ):
            found = jira_client.get_verified_deployment_comment_id("PIC-9")
        assert found == "old-marker"
        full.assert_called_once()


class TestVersionCache:
    @patch("jira_client.requests.get")
    def test_versions_cached_within_ttl(self, mock_get, monkeypatch):
        monkeypatch.setenv("JIRA_VERSION_CACHE_TTL", "300")
        jira_client.clear_version_cache()
        mock_get.return_value = _mock_response(
            200,
            [{"id": "1", "name": "v1", "released": False, "startDate": "2026-01-01"}],
        )
        a = jira_client.get_project_versions("PIC", released=False)
        b = jira_client.get_project_versions("PIC", released=False)
        assert a == b
        assert mock_get.call_count == 1

    @patch("jira_client.requests.get")
    def test_clear_cache_forces_refetch(self, mock_get, monkeypatch):
        monkeypatch.setenv("JIRA_VERSION_CACHE_TTL", "300")
        jira_client.clear_version_cache()
        mock_get.return_value = _mock_response(
            200,
            [{"id": "1", "name": "v1", "released": False, "startDate": "2026-01-01"}],
        )
        jira_client.get_project_versions("PIC")
        jira_client.clear_version_cache()
        jira_client.get_project_versions("PIC")
        assert mock_get.call_count == 2


class TestRateLimitPause:
    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.get")
    def test_inter_call_pause_respected(self, mock_get, mock_sleep, monkeypatch):
        monkeypatch.setenv("JIRA_RATE_LIMIT_PAUSE", "0.25")
        monkeypatch.setenv("JIRA_VERSION_CACHE_TTL", "0")
        jira_client.clear_version_cache()
        # Reset pause clock
        jira_client._last_call_mono = 0.0
        mock_get.return_value = _mock_response(200, [])
        jira_client.get_project_versions("PIC")
        jira_client.get_project_versions("AN")
        # First call may sleep almost full pause from epoch; second must wait again.
        assert mock_sleep.call_count >= 1
        assert any(c.args[0] > 0 for c in mock_sleep.call_args_list)

    @patch("jira_client.time.sleep")
    @patch("jira_client.requests.get")
    def test_429_still_retries_with_backoff(self, mock_get, mock_sleep, monkeypatch):
        monkeypatch.setenv("JIRA_RATE_LIMIT_PAUSE", "0")
        monkeypatch.setenv("JIRA_VERSION_CACHE_TTL", "0")
        jira_client.clear_version_cache()
        mock_get.side_effect = [
            _mock_response(429, headers={"Retry-After": "1"}),
            _mock_response(200, []),
        ]
        assert jira_client.get_project_versions("PIC") == []
        assert mock_get.call_count == 2
        assert mock_sleep.call_count >= 1


class TestReadonlyConcurrency:
    def test_check_deployment_comments_preserves_order(self, monkeypatch):
        monkeypatch.setenv("JIRA_READONLY_CONCURRENCY", "3")
        keys = ["PIC-1", "PIC-2", "PIC-3"]

        def fake_has(key: str) -> bool:
            return key == "PIC-2"

        with patch.object(jira_client, "has_deployment_comment", side_effect=fake_has):
            already, errors = jira_client.check_deployment_comments(keys)
        assert errors == {}
        assert already == {"PIC-1": False, "PIC-2": True, "PIC-3": False}

    def test_preview_uses_batch_check(self):
        tickets = [
            ("PIC", {"deployment_date": "d", "deployment_time": "t", "deployment_id": "i"}, _issue("PIC-1")),
            ("PIC", {"deployment_date": "d", "deployment_time": "t", "deployment_id": "i"}, _issue("PIC-2")),
        ]
        with patch(
            "deploy_ops.jira_client.check_deployment_comments",
            return_value=({"PIC-1": True, "PIC-2": False}, {}),
        ) as batch:
            result = deploy_ops.preview_deploy(
                tickets,
                release={"name": "R", "id": "1"},
                project_key="PIC",
            )
        batch.assert_called_once()
        assert result["would_skip"] == ["PIC-1"]
        assert result["would_update"] == ["PIC-2"]


class TestSearchPaginationShared:
    @patch("jira_client._post")
    def test_get_issues_and_keys_share_helper(self, mock_post):
        mock_post.return_value = {
            "issues": [{"key": "PIC-1", "fields": {"summary": "x"}}],
            "nextPageToken": None,
        }
        issues = jira_client.get_issues_for_version("PIC", "9")
        keys = jira_client.get_issue_keys_for_version("PIC", "9")
        assert issues[0]["key"] == "PIC-1"
        assert keys == ["PIC-1"]
        assert mock_post.call_count == 2
