"""Slack deployment announce templates — auto-fill from release context."""

from __future__ import annotations


import config
from slack_announce import (
    SlackAnnounceDraft,
    SlackChannelTarget,
    format_cc_line,
    format_client_notes_display,
    format_deploy_day,
    format_service_desk_display,
    format_sharepoint_download_display,
    format_sharepoint_folder_display,
    format_ticket_mix_display,
)
from template_engine import render_template


def _template_path() -> str:
    section = getattr(config, "SLACK_ANNOUNCE", {}) or {}
    templates = section.get("templates") if isinstance(section, dict) else {}
    if isinstance(templates, dict):
        path = str(templates.get("body") or templates.get("deploy_announce") or "").strip()
        if path:
            return path
    return "slack/deploy_announce.txt.j2"


def build_announce_body_from_template(
    draft: SlackAnnounceDraft,
    channel: SlackChannelTarget,
    *,
    for_preview: bool = False,
) -> str:
    """Render announce body from Jinja template (workspace override or default)."""
    day = format_deploy_day(draft.deploy_date)
    version = draft.version if draft.version.lower().startswith("v") else f"v{draft.version}"
    sharepoint_download_display = format_sharepoint_download_display(
        draft, for_preview=for_preview
    )
    sharepoint_folder_display = format_sharepoint_folder_display(
        draft, for_preview=for_preview
    )
    client_notes_display = format_client_notes_display(draft, for_preview=for_preview)
    service_desk_display = format_service_desk_display(draft, for_preview=for_preview)
    ticket_mix_display = format_ticket_mix_display(draft, for_preview=for_preview)
    cc_line = format_cc_line(channel, for_preview=for_preview)
    try:
        return render_template(
            _template_path(),
            deploy_day=day,
            version=version,
            environments=draft.environments,
            sharepoint_download_display=sharepoint_download_display,
            sharepoint_folder_display=sharepoint_folder_display,
            client_notes_display=client_notes_display,
            sharepoint_display=sharepoint_download_display,
            sharepoint_line=sharepoint_download_display,
            service_desk_display=service_desk_display,
            ticket_key=draft.ticket_key,
            ticket_line=service_desk_display,
            ticket_mix_display=ticket_mix_display,
            cc_line=cc_line,
            ticket_summary=draft.ticket_summary,
            ticket_url=draft.ticket_url,
            sharepoint_url=draft.sharepoint_url,
            ticket_count=getattr(draft, "ticket_count", 0),
        ).strip()
    except Exception:  # noqa: BLE001
        return ""


def template_enabled() -> bool:
    section = getattr(config, "SLACK_ANNOUNCE", {}) or {}
    templates = section.get("templates") if isinstance(section, dict) else {}
    if not isinstance(templates, dict):
        return True
    if templates.get("enabled") is False:
        return False
    return True


__all__ = [
    "build_announce_body_from_template",
    "template_enabled",
]
