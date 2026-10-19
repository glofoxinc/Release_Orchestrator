"""Reference Slack deployment announce messages — parity with shipit_reference.py.

Operator-approved examples (SHIPIT-17036, SHIPIT-17191) define the canonical
body structure, per-channel CC rules, and preview wording for Step 6.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

import config
from slack_announce import (
    CANONICAL_CHANNEL_REQUIREMENTS,
    SlackAnnounceDraft,
    build_channel_messages,
    default_channels,
    format_deploy_day,
)

from orchestrator.paths import TEMPLATES_DIR

_REFERENCE_PATH = TEMPLATES_DIR / "default" / "slack" / "reference.yaml"

DEFAULT_REFERENCE_KEY = "SHIPIT-17191"
GOLD_STANDARD_KEYS = ("SHIPIT-17191", "SHIPIT-17036")


@dataclass(frozen=True)
class SlackReferenceExample:
    """One gold-standard deployment announce reference."""

    key: str
    ticket_key: str
    version: str
    deploy_day: str
    sharepoint_label: str
    jira_url: str
    note: str
    squad_preview: str
    buddies_preview: str = ""


def _load_reference_yaml() -> dict[str, Any]:
    if not _REFERENCE_PATH.is_file():
        return {}
    with _REFERENCE_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    return data if isinstance(data, dict) else {}


def reference_examples() -> dict[str, SlackReferenceExample]:
    """All configured reference examples keyed by SHIPIT id."""
    raw = _load_reference_yaml().get("examples") or {}
    out: dict[str, SlackReferenceExample] = {}
    if not isinstance(raw, dict):
        return out
    for key, item in raw.items():
        if not isinstance(item, dict):
            continue
        out[str(key).upper()] = SlackReferenceExample(
            key=str(key).upper(),
            ticket_key=str(item.get("ticket_key") or key),
            version=str(item.get("version") or ""),
            deploy_day=str(item.get("deploy_day") or ""),
            sharepoint_label=str(item.get("sharepoint_label") or ""),
            jira_url=str(item.get("jira_url") or ""),
            note=str(item.get("note") or ""),
            squad_preview=str(item.get("squad_preview") or "").strip(),
            buddies_preview=str(item.get("buddies_preview") or "").strip(),
        )
    return out


def fetch_slack_reference(issue_key: str | None = None) -> SlackReferenceExample | None:
    """Load one reference example (default SHIPIT-17191)."""
    key = (issue_key or DEFAULT_REFERENCE_KEY).strip().upper()
    return reference_examples().get(key)


def body_rules() -> list[str]:
    """Human-readable rules agents should follow when composing/editing messages."""
    rules = _load_reference_yaml().get("body_rules") or []
    return [str(r) for r in rules if str(r).strip()]


def channel_reference_spec() -> list[dict[str, Any]]:
    """Per-channel CC requirements from reference.yaml + CANONICAL_CHANNEL_REQUIREMENTS."""
    yaml_channels = _load_reference_yaml().get("channels") or {}
    rows: list[dict[str, Any]] = []
    for spec in CANONICAL_CHANNEL_REQUIREMENTS:
        ych = yaml_channels.get(spec["key"]) if isinstance(yaml_channels, dict) else {}
        ych = ych if isinstance(ych, dict) else {}
        rows.append(
            {
                "key": spec["key"],
                "name": spec["name"],
                "cc_keys": list(spec["cc_keys"]),
                "cc_display": str(ych.get("cc_display") or ""),
            }
        )
    return rows


def build_reference_payload(issue_key: str | None = None) -> dict[str, Any]:
    """Full reference block for MCP tools and operator docs."""
    ref = fetch_slack_reference(issue_key)
    examples = reference_examples()
    return {
        "default_reference_key": DEFAULT_REFERENCE_KEY,
        "gold_standard_keys": list(GOLD_STANDARD_KEYS),
        "body_rules": body_rules(),
        "channels": channel_reference_spec(),
        "template_path": "templates/default/slack/deploy_announce.txt.j2",
        "reference": (
            {
                "key": ref.key,
                "ticket_key": ref.ticket_key,
                "version": ref.version,
                "deploy_day": ref.deploy_day,
                "sharepoint_label": ref.sharepoint_label,
                "jira_url": ref.jira_url,
                "note": ref.note,
                "messages": {
                    "insights-customize-squad": ref.squad_preview,
                    "customize-bi-buddies": ref.buddies_preview or "(same body, Sushma CC only)",
                },
            }
            if ref
            else None
        ),
        "all_examples": {
            key: {
                "ticket_key": ex.ticket_key,
                "version": ex.version,
                "deploy_day": ex.deploy_day,
                "squad_preview": ex.squad_preview,
                "buddies_preview": ex.buddies_preview,
                "note": ex.note,
            }
            for key, ex in examples.items()
        },
    }


def _parse_deploy_day(deploy_day: str) -> date | None:
    """Best-effort parse from reference deploy_day string."""
    text = (deploy_day or "").strip()
    if not text:
        return None
    # "Wednesday, September 16, 2026" -> date(2026, 9, 16)
    parts = text.split(",")
    if len(parts) < 2:
        return None
    tail = parts[-1].strip()
    month_day = parts[-2].strip()
    try:
        year = int(tail)
        month_name, day_str = month_day.split()
        from datetime import datetime

        parsed = datetime.strptime(f"{month_name} {day_str} {year}", "%B %d %Y")
        return parsed.date()
    except (ValueError, TypeError):
        return None


def render_reference_messages(issue_key: str | None = None) -> dict[str, str]:
    """Regenerate reference channel previews via slack_announce engine."""
    ref = fetch_slack_reference(issue_key)
    if ref is None:
        return {}
    deploy_date = _parse_deploy_day(ref.deploy_day)
    if deploy_date is None:
        return {
            "insights-customize-squad": ref.squad_preview,
            "customize-bi-buddies": ref.buddies_preview,
        }
    draft = SlackAnnounceDraft(
        ticket_key=ref.ticket_key,
        ticket_summary=f"Glofox Insights Customize BI - Prod Deployment - Release Version {ref.version}",
        ticket_url=ref.jira_url,
        version=f"v{ref.version.lstrip('vV')}",
        deploy_date=deploy_date,
        sharepoint_url=f"https://example.sharepoint.com/file={ref.sharepoint_label.replace(' ', '%20')}",
        sharepoint_label=ref.sharepoint_label,
    )
    messages = build_channel_messages(draft, default_channels())
    return {m.channel.name: m.preview for m in messages}


def compare_preview_to_reference(
    preview: dict[str, Any],
    *,
    issue_key: str | None = None,
) -> dict[str, Any]:
    """Check generated preview against gold-standard reference structure."""
    ref = fetch_slack_reference(issue_key)
    if ref is None:
        return {"ok": False, "error": "reference not found"}

    expected = {
        "insights-customize-squad": ref.squad_preview,
        "customize-bi-buddies": ref.buddies_preview,
    }
    checks: list[dict[str, Any]] = []
    for item in preview.get("channels") or []:
        name = str(item.get("name") or "")
        text = str(item.get("preview") or "")
        exp = expected.get(name, "")
        if not exp and name == "customize-bi-buddies":
            continue
        ok = True
        details: list[str] = []
        for needle in (
            "Hello Team,",
            "Our upcoming deployment is scheduled for",
            "Deployment notes and the deployment ticket are below for reference:",
            "SharePoint — Release Notes:",
            "SharePoint — Folder:",
            "SHIPIT ticket:",
            "CC:",
        ):
            if needle not in text:
                ok = False
                details.append(f"missing: {needle}")
        if name == "insights-customize-squad":
            for person in (
                "Sushma Bhamidipati",
                "Sai Anirudh Karre",
                "Zeke Brustkern",
                "Eoin George",
            ):
                if person not in text:
                    ok = False
                    details.append(f"squad must CC {person}")
        if name == "customize-bi-buddies":
            if "Sushma Bhamidipati" not in text:
                ok = False
                details.append("buddies must CC Sushma Bhamidipati")
            for person in ("Sai Anirudh Karre", "Zeke Brustkern", "Eoin George"):
                if person in text:
                    ok = False
                    details.append(f"buddies must not CC {person}")
        checks.append({"channel": name, "ok": ok, "details": details})

    return {
        "reference_key": ref.key,
        "ok": all(c["ok"] for c in checks),
        "checks": checks,
        "reference_squad_preview": ref.squad_preview,
        "reference_buddies_preview": ref.buddies_preview,
    }


def slack_reference_status() -> dict[str, Any]:
    """Safe status for MCP — no credentials required."""
    config.ensure_workspace_loaded()
    payload = build_reference_payload()
    rendered = render_reference_messages()
    payload["engine_renders_match"] = compare_preview_to_reference(
        {
            "channels": [
                {"name": name, "preview": text}
                for name, text in rendered.items()
            ]
        }
    )
    return payload


__all__ = [
    "DEFAULT_REFERENCE_KEY",
    "GOLD_STANDARD_KEYS",
    "SlackReferenceExample",
    "body_rules",
    "build_reference_payload",
    "channel_reference_spec",
    "compare_preview_to_reference",
    "fetch_slack_reference",
    "reference_examples",
    "render_reference_messages",
    "slack_reference_status",
]
