"""Tests for TCKT reference learning module."""

from __future__ import annotations

import adf_builder as adf
import tckt_reference


def test_derive_client_label_single():
    extracted = [{"type": "Custom", "client": "Glofox", "report": "R", "description": "d"}]
    assert tckt_reference.derive_client_label(extracted) == "Glofox"


def test_derive_client_label_multi():
    extracted = [
        {"type": "Custom", "client": "Jazzercise", "report": "R", "description": "d"},
        {"type": "Custom", "client": "BFT", "report": "R", "description": "d"},
        {"type": "Custom", "client": "Jetts", "report": "R", "description": "d"},
        {"type": "Custom", "client": "Lift", "report": "R", "description": "d"},
    ]
    assert tckt_reference.derive_client_label(extracted) == "Multi-Client"


def test_build_summary_matches_reference_pattern():
    extracted = [{"type": "Custom", "client": "Glofox", "report": "R", "description": "d"}]
    summary = tckt_reference.build_summary_from_reference_pattern(
        version_name="v2026.3.07.23",
        extracted=extracted,
        team="Insights Customize BI Team",
        environment="Production",
    )
    assert "Production Deployment" in summary
    assert "Insights Customize BI Team" in summary
    assert "Glofox" in summary
    assert "v2026.3.07.23" in summary


def test_build_summary_uses_config_team_when_omitted(monkeypatch):
    import config

    monkeypatch.setattr(config, "TCKT_SUMMARY_TEAM", "Insights Customize BI Team")
    summary = tckt_reference.build_summary_from_reference_pattern(
        version_name="v2026.3.07.23",
        extracted=[],
    )
    assert "Insights Customize BI Team" in summary


    ref = tckt_reference.TcktReference(
        key="TCKT-111137",
        description_plain="Release Summary\nLine",
        description_adf=adf.doc(adf.paragraph(adf.text("Release Summary"))),
        approvers=[{"accountId": "abc123"}],
        approver_groups=[{"name": "Command Center"}],
    )
    ss: dict = {}
    tckt_reference.apply_reference_to_session(ref, ss)
    assert ss["stk_reference_key"] == "TCKT-111137"
    assert ss["stk_description_custom"] is True
    assert ss["stk_approvers"] == [{"accountId": "abc123"}]
    assert ss["stk_approver_groups"] == [{"name": "Command Center"}]
