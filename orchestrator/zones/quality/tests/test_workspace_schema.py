"""CI contract — orchestrator/zones/config/profiles/workspace.yaml must load and pass schema checks."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
WORKSPACE = ROOT / "orchestrator" / "zones" / "config" / "profiles" / "workspace.yaml"


def test_workspace_yaml_loads_and_slack_channels_present():
    import yaml

    assert WORKSPACE.is_file(), "orchestrator/zones/config/profiles/workspace.yaml is required"
    raw = yaml.safe_load(WORKSPACE.read_text(encoding="utf-8"))
    cfg = raw.get("workspace") or raw
    slack = cfg.get("slack_announce") or {}
    channel_ids = slack.get("channel_ids") or {}
    assert channel_ids.get("insights-customize-squad")
    assert channel_ids.get("customize-bi-buddies")


def test_workspace_slack_schema_via_verify_integrations():
    from orchestrator.ops import verify_integrations as vi

    result = vi.check_workspace_slack_schema()
    assert result.status == vi.Result.PASS, result.message
