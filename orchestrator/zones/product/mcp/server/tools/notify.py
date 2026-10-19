"""MCP tools: Slack + Outlook role notices (owners, testers, review, fix versions)."""

from __future__ import annotations

import os
from typing import Any

import config
import jira_client
import release_role_notify as rn
from release_mcp import release_ops
from release_mcp.operator_guide import enrich_tool_response
from release_mcp.server.bootstrap import mcp


def _rows(
    version_name: str,
    projects: list[str] | None,
    ticket_keys: list[str] | None,
    extracted_override: list[dict] | None,
) -> list[dict[str, Any]]:
    if extracted_override is not None:
        return list(extracted_override)
    if ticket_keys:
        fetched = release_ops.fetch_tickets_by_keys(ticket_keys)
        return list(fetched.get("extracted") or [])
    result = release_ops.fetch_release_tickets(version_name, projects=projects)
    return list(result.get("extracted") or [])


def _shipit_scope_rows(
    version_name: str,
    projects: list[str] | None,
    ticket_keys: list[str] | None,
    extracted_override: list[dict] | None,
    shipit_key: str = "",
) -> list[dict[str, Any]]:
    """Tickets included on this SHIPIT only (not the open PIC/AN backlog)."""
    if extracted_override is not None:
        return list(extracted_override)
    keys = [str(k).strip().upper() for k in (ticket_keys or []) if str(k).strip()]
    if shipit_key and not keys:
        keys = rn.shipit_linked_ticket_keys(shipit_key)
    if keys:
        fetched = release_ops.fetch_tickets_by_keys(keys)
        return list(fetched.get("extracted") or [])
    return _rows(version_name, projects, None, None)


@mcp.tool()
def notify_owners_and_testers(
    version_name: str,
    shipit_key: str = "",
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    owner_name: str = "",
    owner_email: str = "",
    extracted_override: list[dict] | None = None,
    deploy_when: str = "",
    dry_run: bool = True,
) -> dict:
    """Slack + Outlook ahead of ship: deployment owner and Test-by testers.

    Testers come from release-notes Test by. Sushma is not a tester — she is
    pinged when SHIPIT is created (create_service_ticket / notify_sushma_on_shipit).
    Owner defaults to workspace release_notes.release_owner.
    dry_run=true (default) preview only.

    Args:
        version_name: Fix version (e.g. 2026.4.10.15)
        shipit_key: Optional SHIPIT ticket key
        projects: Optional PIC/AN subset
        ticket_keys: Optional include-only keys
        owner_name: Optional deployment owner display name
        owner_email: Optional owner Outlook address
        extracted_override: Optional ticket rows (tests / already-fetched notes)
        deploy_when: Optional date label (else next safe deploy day IST)
        dry_run: Preview without sending (default true)
    """
    rows = _rows(version_name, projects, ticket_keys, extracted_override)
    payload = rn.notify_owners_and_testers(
        rows,
        version_name=version_name,
        shipit_key=shipit_key,
        owner_name=owner_name,
        owner_email=owner_email,
        deploy_when=deploy_when,
        dry_run=dry_run,
    )
    return enrich_tool_response(payload, tool="notify_owners_and_testers")


@mcp.tool()
def propose_release_dates(extra_day_off: str = "") -> dict:
    """Propose review + safe deploy dates from the cached company holiday calendar.

    Review may be Friday. Deploy never Friday and never the day before a day off.
    Outlook/Playwright refresh is a background handoff — this tool does not wait on it.

    Args:
        extra_day_off: Optional YYYY-MM-DD to remember (unlisted company holiday)
    """
    import release_calendar as cal
    from datetime import date as _date

    if extra_day_off.strip():
        try:
            cal.remember_extra_day_off(_date.fromisoformat(extra_day_off.strip()[:10]))
        except ValueError:
            return enrich_tool_response(
                {"ok": False, "error": "extra_day_off must be YYYY-MM-DD"},
                tool="propose_release_dates",
            )
    payload = cal.propose_release_dates()
    return enrich_tool_response(payload, tool="propose_release_dates")


@mcp.tool()
def notify_review_call(
    version_name: str,
    when: str = "",
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    extracted_override: list[dict] | None = None,
    dry_run: bool = True,
) -> dict:
    """After a review call is scheduled: Slack + Outlook testers and main assignees.

    Does not notify optional attendees. Call this when the review meeting is booked.

    Args:
        version_name: Fix version on the review agenda
        when: Meeting time text (e.g. tomorrow 10:30 IST)
        projects: Optional PIC/AN subset
        ticket_keys: Optional include-only keys
        extracted_override: Optional ticket rows
        dry_run: Preview without sending (default true)
    """
    rows = _rows(version_name, projects, ticket_keys, extracted_override)
    payload = rn.notify_review_assignees(
        rows,
        version_name=version_name,
        when=when,
        dry_run=dry_run,
    )
    return enrich_tool_response(payload, tool="notify_review_call")


@mcp.tool()
def notify_missing_fix_versions(
    version_name: str = "",
    shipit_key: str = "",
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    extracted_override: list[dict] | None = None,
    dry_run: bool = True,
) -> dict:
    """Fix Versions for tickets on this SHIPIT only (not the open backlog).

    Prefer notify_sushma_on_shipit for the combined SHIPIT + Fix Version mail.

    Args:
        version_name: This ship's Fix Version (e.g. 2026.4.10.15)
        shipit_key: SHIPIT whose linked tickets are checked
        projects: Defaults to workspace release_notify.glofox_projects
        ticket_keys: Optional keys to inspect
        extracted_override: Optional rows
        dry_run: Preview without sending (default true)
    """
    cfg = getattr(config, "RELEASE_NOTIFY", {}) or {}
    pks = projects or list(cfg.get("glofox_projects") or ["PIC", "AN"])
    rows = _shipit_scope_rows(
        version_name, pks, ticket_keys, extracted_override, shipit_key=shipit_key
    )
    payload = rn.notify_missing_fix_versions(
        rows,
        version_name=version_name,
        shipit_key=shipit_key,
        dry_run=dry_run,
    )
    return enrich_tool_response(payload, tool="notify_missing_fix_versions")


@mcp.tool()
def create_fix_version(
    version_name: str,
    projects: list[str] | None = None,
    description: str = "",
    dry_run: bool = True,
) -> dict:
    """Create the Jira Fix Version on Glofox projects (PIC/AN by default).

    dry_run=true previews only. Pair with create_service_ticket for SHIPIT,
    then notify_owners_and_testers / notify_missing_fix_versions.

    Args:
        version_name: Version string (e.g. 2026.4.10.15)
        projects: Defaults to PIC, AN
        description: Optional Jira version description
        dry_run: Preview without creating (default true)
    """
    cfg = getattr(config, "RELEASE_NOTIFY", {}) or {}
    pks = [p.strip().upper() for p in (projects or cfg.get("glofox_projects") or ["PIC", "AN"]) if str(p).strip()]
    if dry_run:
        return enrich_tool_response(
            {
                "ok": True,
                "dry_run": True,
                "version_name": version_name,
                "projects": pks,
                "description": description,
                "hint": "Pass dry_run=false after the operator confirms.",
            },
            tool="create_fix_version",
        )
    results = []
    for pk in pks:
        try:
            results.append({"project": pk, **jira_client.create_project_version(pk, version_name, description=description)})
        except Exception as exc:  # noqa: BLE001
            results.append({"project": pk, "ok": False, "error": str(exc)})
    ok = all(r.get("created") or r.get("existing") for r in results)
    return enrich_tool_response(
        {"ok": ok, "dry_run": False, "version_name": version_name, "results": results},
        tool="create_fix_version",
    )


@mcp.tool()
def notify_sushma_on_shipit(
    version_name: str,
    shipit_key: str,
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    extracted_override: list[dict] | None = None,
    deploy_when: str = "",
    dry_run: bool = True,
    sharepoint_url: str = "",
    client_sharepoint_url: str = "",
) -> dict:
    """One Slack + Outlook: this SHIPIT and Fix Versions of tickets linked on it.

    MCP is the main path. Slack and Outlook both; Playwright MCP if either API fails.
    Not tester, not assignee. Tickets = SHIPIT links only (not the daily backlog).
    Message body starts with ``Release orchestrator:``.

    Args:
        version_name: Fix version (e.g. 2026.4.10.15)
        shipit_key: Required SHIPIT key
        projects: Optional PIC/AN subset
        ticket_keys: Optional include-only keys
        extracted_override: Optional ticket rows
        deploy_when: Optional deploy date label
        dry_run: Preview without sending (default true)
        sharepoint_url: Optional Release Notes SharePoint URL
        client_sharepoint_url: Optional Client Release Notes SharePoint URL
    """
    rows = _shipit_scope_rows(
        version_name, projects, ticket_keys, extracted_override, shipit_key=shipit_key
    )
    payload = rn.notify_sushma_on_shipit_created(
        rows,
        version_name=version_name,
        shipit_key=shipit_key,
        deploy_when=deploy_when,
        dry_run=dry_run,
        sharepoint_url=sharepoint_url,
        client_sharepoint_url=client_sharepoint_url,
    )
    return enrich_tool_response(payload, tool="notify_sushma_on_shipit")


@mcp.tool()
def notify_shipit_developers(
    version_name: str,
    shipit_key: str = "",
    projects: list[str] | None = None,
    ticket_keys: list[str] | None = None,
    extracted_override: list[dict] | None = None,
    dry_run: bool = True,
) -> dict:
    """Comment on every ticket in the SHIPIT reminding the assignee.

    Developers only need to reply with **ready for review** or **ready for release**.
    No links, group chats, Fix Version, or TCKT/SHIPIT status. dry_run=true preview.

    Args:
        version_name: Fix version on the ship
        shipit_key: SHIPIT ticket; linked PIC/AN keys are included when ticket_keys empty
        projects: Optional PIC/AN subset when fetching by version
        ticket_keys: Optional include-only keys
        extracted_override: Optional already-fetched rows
        dry_run: Preview without posting (default true)
    """
    keys = [str(k).strip().upper() for k in (ticket_keys or []) if str(k).strip()]
    if shipit_key and not keys and extracted_override is None:
        keys = rn.shipit_linked_ticket_keys(shipit_key)
    if extracted_override is not None:
        rows = list(extracted_override)
    elif keys:
        fetched = release_ops.fetch_tickets_by_keys(keys)
        rows = list(fetched.get("extracted") or [])
    else:
        rows = _rows(version_name, projects, None, None)
    payload = rn.remind_shipit_developers(
        rows,
        version_name=version_name,
        shipit_key=shipit_key,
        dry_run=dry_run,
    )
    return enrich_tool_response(payload, tool="notify_shipit_developers")
