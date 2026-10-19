"""Headless SharePoint upload helpers for Release Orchestrator MCP (parity with platform backend)."""

from __future__ import annotations

import os
from typing import Any

import browser_automation
import config
import sharepoint_upload as sp
from generators.release_notes_deployment import extract_deployment_rows_from_docx
from integration_archive import archived_response, is_archived
from ms_graph import GraphClient


def _cfg(graph: GraphClient | None = None) -> sp.SharePointUploadConfig:
    return sp.load_upload_config(config.SHAREPOINT_UPLOAD, graph=graph)


def sharepoint_upload_status() -> dict[str, Any]:
    """Feature/config status — safe without credentials."""
    if is_archived("sharepoint_upload"):
        base = archived_response("sharepoint_upload")
        pw = browser_automation.playwright_mcp_readiness()
        base["playwright_alternative"] = {
            "tool": "sharepoint_playwright_handoff",
            "phrase": "upload sharepoint",
            "mcp": browser_automation.playwright_mcp(),
            "ready": bool(browser_automation.enabled() and pw.get("in_mcp_config")),
            "blockers": pw.get("blockers") or [],
        }
        return base
    return sp.status(_cfg())


def sharepoint_upload_release_notes(
    local_path: str,
    *,
    remote_name: str | None = None,
    dry_run: bool = True,
    version_name: str = "",
) -> dict[str, Any]:
    """Upload (or dry-run preview) a release-notes ``.docx`` to SharePoint."""
    if is_archived("sharepoint_upload"):
        handoff = browser_automation.build_sharepoint_upload_handoff(
            local_path,
            remote_name=remote_name or "",
        )
        return {
            **archived_response("sharepoint_upload"),
            "dry_run": dry_run,
            "delivery": "playwright_mcp",
            "playwright_handoff": handoff,
            "hint": "Graph archived — run playwright_handoff.steps via Playwright MCP, then sharepoint done + URL.",
        }
    result = sp.upload_release_notes(
        _cfg(),
        local_path,
        remote_name=remote_name,
        version=version_name,
        dry_run=dry_run,
    )
    return result.to_dict()


def sharepoint_upload_client_notes(
    local_path: str,
    *,
    version_name: str = "",
    remote_name: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Upload PIC/custom client notes to the same SharePoint folder as release notes."""
    name = remote_name or sp.default_client_remote_name(version_name)
    return sharepoint_upload_release_notes(
        local_path,
        remote_name=name,
        dry_run=dry_run,
        version_name=version_name,
    )


def sharepoint_upload_notes_pair(
    release_notes_path: str,
    *,
    client_notes_path: str = "",
    version_name: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """Upload internal release notes and client notes to the same SharePoint folder."""
    extra: list[tuple[str, str]] = []
    client_path = (client_notes_path or "").strip()
    if client_path and os.path.isfile(client_path):
        extra.append((client_path, sp.default_client_remote_name(version_name)))
    if is_archived("sharepoint_upload"):
        handoff = browser_automation.build_sharepoint_upload_handoff(
            release_notes_path,
            version_name=version_name,
            extra_files=extra,
        )
        return {
            **archived_response("sharepoint_upload"),
            "dry_run": dry_run,
            "delivery": "playwright_mcp",
            "playwright_handoff": handoff,
            "release_notes": {"remote_name": sp.default_remote_name(version_name)},
            "client_notes": (
                {"remote_name": extra[0][1], "local_path": extra[0][0]} if extra else None
            ),
            "hint": (
                "Graph archived — upload both .docx files to the same quarter folder, "
                "then paste both SharePoint URLs (release notes + client notes)."
            ),
        }
    release = sharepoint_upload_release_notes(
        release_notes_path,
        remote_name=sp.default_remote_name(version_name),
        dry_run=dry_run,
        version_name=version_name,
    )
    client = None
    if extra:
        client = sharepoint_upload_client_notes(
            extra[0][0],
            version_name=version_name,
            remote_name=extra[0][1],
            dry_run=dry_run,
        )
    ok = bool(release.get("ok")) and (client is None or client.get("ok"))
    return {
        "ok": ok,
        "dry_run": dry_run,
        "release_notes": release,
        "client_notes": client,
        "web_url": release.get("web_url") or "",
        "client_web_url": (client or {}).get("web_url") or "",
    }


def sharepoint_download_release_notes(
    web_url: str,
    *,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Download notes by SharePoint URL and return parsed deployment rows."""
    if is_archived("sharepoint_upload"):
        return {**archived_response("sharepoint_upload"), "bytes_size": 0, "deployment_rows": []}
    try:
        data = sp.download_by_web_url(_cfg(), web_url)
    except (RuntimeError, ValueError) as exc:
        return {"ok": False, "error": str(exc), "bytes_size": 0, "deployment_rows": []}

    saved_path = ""
    if output_path:
        saved_path = os.path.abspath(output_path)
        parent = os.path.dirname(saved_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(saved_path, "wb") as handle:
            handle.write(data)

    return {
        "ok": True,
        "error": "",
        "bytes_size": len(data),
        "output_path": saved_path,
        "deployment_rows": extract_deployment_rows_from_docx(data),
    }
