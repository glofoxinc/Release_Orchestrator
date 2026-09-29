"""In-process smoke tests for app bootstrap and workflow routing."""

from __future__ import annotations

import os

import pytest

from orchestrator.paths import ENTRY_DIR

os.environ.setdefault("JIRA_EMAIL", "smoke@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake-token")


@pytest.fixture(scope="module")
def app_test():
    from unittest.mock import patch

    from streamlit.testing.v1 import AppTest

    prev_mock = os.environ.get("MOCK_MODE")
    os.environ["MOCK_MODE"] = "1"
    try:
        app_path = ENTRY_DIR / "app.py"
        at = AppTest.from_file(str(app_path), default_timeout=90)
        with patch(
            "deploy_draft.load_deploy_draft_with_reason",
            return_value=(None, ""),
        ):
            at.run()
        yield at
    finally:
        if prev_mock is None:
            os.environ.pop("MOCK_MODE", None)
        else:
            os.environ["MOCK_MODE"] = prev_mock


class TestAppSmoke:
    def test_home_renders_without_exception(self, app_test):
        assert not app_test.exception
        page_text = "\n".join(m.value for m in app_test.main.markdown)
        page_text += "\n".join(getattr(m, "value", "") for m in app_test.main.title)
        assert "Release Orchestrator" in page_text or "Workflow apps" in page_text

    def test_workflow_apps_visible_on_home(self, app_test):
        labels = [m.value for m in app_test.main.markdown]
        joined = "\n".join(labels)
        assert "Workflow apps" in joined or "Ticket Review" in joined


class TestWorkflowPrerequisitesSmoke:
    def test_service_ticket_blocked_without_sharepoint(self, monkeypatch):
        import streamlit as st

        from release_platform.ui.workflow import check_app_prerequisites

        state = {
            "shared_snapshot": {"ticket_keys": ["PIC-1"]},
            "shared_docx_generated": True,
            "shared_sharepoint_url": "",
        }
        monkeypatch.setattr(st, "session_state", state, raising=False)
        result = check_app_prerequisites("service_ticket")
        assert result.ok is False

    def test_full_chain_prerequisites(self, monkeypatch):
        import streamlit as st

        from release_platform.ui.workflow import check_app_prerequisites

        ready = {
            "shared_snapshot": {"ticket_keys": ["PIC-1"]},
            "shared_docx_generated": True,
            "shared_sharepoint_url": "https://sharepoint.example/doc.docx",
            "stk_created_key": "TCKT-99",
        }
        monkeypatch.setattr(st, "session_state", ready, raising=False)
        assert check_app_prerequisites("ticket_review").ok is True
        assert check_app_prerequisites("release_notes").ok is True
        assert check_app_prerequisites("service_ticket").ok is True
        assert check_app_prerequisites("release_deployer").ok is True


@pytest.mark.playwright
class TestPlaywrightSmokeOptional:
    """Optional browser smoke — run with: RUN_PLAYWRIGHT=1 pytest -m playwright"""

    @pytest.fixture(autouse=True)
    def _require_flag(self):
        if os.environ.get("RUN_PLAYWRIGHT", "").lower() not in {"1", "true", "yes"}:
            pytest.skip("Set RUN_PLAYWRIGHT=1 to run browser smoke tests")

    def test_home_page_loads(self):
        pytest.importorskip("playwright.sync_api")
        from playwright.sync_api import sync_playwright

        port = os.environ.get("STREAMLIT_E2E_PORT", "8501")
        url = f"http://localhost:{port}"
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle", timeout=60_000)
            assert "Release Orchestrator" in page.content()
            browser.close()
