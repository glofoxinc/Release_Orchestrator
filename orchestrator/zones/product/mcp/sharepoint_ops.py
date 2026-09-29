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
        dry_run=dry_run,
    )
    return result.to_dict()


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
