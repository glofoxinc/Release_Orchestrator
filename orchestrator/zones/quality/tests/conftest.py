"""Test bootstrap — wire Release Orchestrator before package imports."""

from __future__ import annotations

import importlib
import importlib.abc
import importlib.util
import sys
from pathlib import Path

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

from orchestrator.paths import ALIASES_DIR, ENV_FILE as _ENV_FILE, REPO_ROOT as _REPO_ROOT

for _path in (_REPO_ROOT, ALIASES_DIR):
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
