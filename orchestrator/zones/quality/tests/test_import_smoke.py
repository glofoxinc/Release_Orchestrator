"""Verify editable install exposes top-level packages without conftest alias hacks."""

from __future__ import annotations


def test_release_mcp_importable():
    import release_mcp
    import release_mcp.server

    assert hasattr(release_mcp.server, "mcp")


def test_mcp_server_shim_importable():
    import mcp_server

    assert hasattr(mcp_server, "wizard")


def test_orchestrator_entry_cli_importable():
    from orchestrator.entry.cli import main

    assert callable(main)


def test_daily_review_agent_importable():
    import importlib

    mod = importlib.import_module("daily_review_agent.__main__")
    assert callable(mod.main)
