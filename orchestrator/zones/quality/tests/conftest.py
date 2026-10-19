"""Test bootstrap — wire Release Orchestrator before package imports."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class _UILegacyAliasLoader(importlib.abc.Loader):
    def __init__(self, fullname: str, mapped: str) -> None:
        self.fullname = fullname
        self.mapped = mapped

    def create_module(self, spec):  # noqa: ANN001
        return None

    def exec_module(self, module) -> None:  # noqa: ANN001
        target = importlib.import_module(self.mapped)
        sys.modules[self.fullname] = target
        module.__dict__.update(target.__dict__)


class _UILegacyAliasFinder(importlib.abc.MetaPathFinder):
    """Map legacy ``ui.*`` imports to ``release_platform.ui.*`` for tests."""

    def find_spec(self, fullname: str, path, target=None):  # noqa: ANN001
        if fullname == "ui":
            mapped = "release_platform.ui"
        elif fullname.startswith("ui."):
            mapped = "release_platform.ui" + fullname[2:]
        else:
            return None
        target_spec = importlib.util.find_spec(mapped)
        if target_spec is None:
            return None
        return importlib.util.spec_from_loader(
            fullname,
            _UILegacyAliasLoader(fullname, mapped),
            origin=target_spec.origin,
            is_package=target_spec.submodule_search_locations is not None,
        )


def _install_ui_legacy_shim() -> None:
    if not any(isinstance(finder, _UILegacyAliasFinder) for finder in sys.meta_path):
        sys.meta_path.insert(0, _UILegacyAliasFinder())


_install_ui_legacy_shim()

from orchestrator.paths import ALIASES_DIR, ENGINE_DIR, ENV_FILE as _ENV_FILE, REPO_ROOT as _REPO_ROOT

for _path in (_REPO_ROOT, ALIASES_DIR, ENGINE_DIR):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

try:
    from dotenv import load_dotenv

    if _ENV_FILE.is_file():
        load_dotenv(_ENV_FILE, override=True)
except ImportError:
    pass

import config

config.ensure_workspace_loaded()


@pytest.fixture(autouse=True)
def _clear_jira_version_cache():
    """Prevent cross-test pollution from jira_client version cache."""
    import jira_client

    jira_client.clear_version_cache()
    yield
    jira_client.clear_version_cache()


@pytest.fixture(autouse=True)
def _reload_workspace_after_test():
    """Tests that switch workspace via tmp paths must not leave PROJECTS empty."""
    yield
    config.ensure_workspace_loaded(force=True)


@pytest.fixture(autouse=True)
def _default_team_scope_open(request, monkeypatch):
    """Allow deploy/preview tests to use synthetic PIC keys unless marked real_scope."""
    if request.node.get_closest_marker("real_scope"):
        return
    import team_scope

    monkeypatch.setattr(team_scope, "assert_keys_in_scoped_version", lambda *args, **kwargs: None)
    monkeypatch.setattr(team_scope, "keys_outside_scoped_version", lambda *args, **kwargs: [])


_ONBOARDING_MISSING_ENV_TESTS = frozenset({
    "test_assess_setup_flags_missing_jira",
    "test_setup_guide_mentions_atlassian_token_url",
    "test_welcome_blocked_without_credentials",
    "test_run_guided_onboarding_without_env",
})


@pytest.fixture
def mock_jira_offline(monkeypatch):
    """Block live Jira for SHIPIT and service-desk preflight tests."""
    import jira_client

    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.setattr(jira_client, "validate_service_desk_create_payload", lambda _s, _f: [])
    monkeypatch.setattr(
        jira_client,
        "enrich_extracted_with_jira_evidence",
        lambda items: items,
        raising=False,
    )
    with patch(
        "generators.shipit_ticket_evidence.enrich_extracted_with_jira_evidence",
        lambda items: items,
    ):
        yield


@pytest.fixture(autouse=True)
def _shipit_offline_jira(request, monkeypatch):
    """Auto-mock Jira preflight for SHIPIT test modules."""
    if "test_shipit" not in Path(str(request.fspath)).name:
        yield
        return
    import jira_client

    monkeypatch.setenv("MOCK_MODE", "1")
    monkeypatch.setattr(jira_client, "validate_service_desk_create_payload", lambda _s, _f: [])
    monkeypatch.setattr(
        jira_client,
        "get_current_user",
        lambda: {"accountId": "test-user", "displayName": "Test User"},
    )
    monkeypatch.setattr(jira_client, "find_tckt_by_summary", lambda _summary: None)
    monkeypatch.setattr(jira_client, "find_service_ticket_by_summary", lambda *_a, **_k: None)
    with patch(
        "generators.shipit_ticket_evidence.enrich_extracted_with_jira_evidence",
        lambda items: items,
    ):
        yield


@pytest.fixture(autouse=True)
def _mcp_onboarding_ready(request, monkeypatch):
    """Mock full onboarding readiness for welcome/guided tests that expect status=ok."""
    name = Path(str(request.fspath)).name
    apply = name in {
        "test_mcp_welcome.py",
        "test_mcp_guided.py",
        "test_mcp_onboarding.py",
    } and request.node.name not in _ONBOARDING_MISSING_ENV_TESTS
    if not apply:
        yield
        return

    monkeypatch.setenv("JIRA_EMAIL", "test@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "fake-token-not-placeholder")
    monkeypatch.setenv("JIRA_BASE_URL", "https://abcfinancial.atlassian.net")

    ready = {
        "jira_ready": True,
        "fully_ready": True,
        "items": [],
        "next_setup_step": None,
        "needs_track_picker": False,
    }
    with patch("release_mcp.onboarding_verify.setup_complete", return_value=True):
        with patch("release_mcp.onboarding.assess_setup", return_value=ready):
            yield
