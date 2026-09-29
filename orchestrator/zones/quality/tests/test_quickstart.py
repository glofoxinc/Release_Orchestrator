"""MCP quickstart — one-page operator entry."""

from __future__ import annotations


def test_quickstart_payload_structure():
    from release_mcp import quickstart as qs

    payload = qs.quickstart_payload()
    assert payload["docs"]["guide"] == "orchestrator/zones/knowledge/guides/GUIDE.md"
    assert payload["golden_path"]
    assert len(payload["daily_release"]) >= 5
    assert "release-orchestrator" in payload["mcp_json"]["mcpServers"]


def test_quickstart_markdown_mentions_key_phrases():
    from release_mcp import quickstart as qs

    md = qs.quickstart_markdown()
    assert "week release" in md
    assert "welcome onboard" in md
    assert "GUIDE" in md or "Guide" in md


def test_guided_interprets_quickstart():
    from release_mcp import guided

    assert guided.interpret_message("quickstart").get("action") == "quickstart"
    assert guided.interpret_message("guide").get("action") == "quickstart"
