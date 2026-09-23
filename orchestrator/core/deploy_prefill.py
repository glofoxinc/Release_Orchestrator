"""Shared deployer prefill — Release Notes, SharePoint, history (UI + MCP parity)."""

from __future__ import annotations

import logging

import config
import deployment_history
import jira_client
import sharepoint_upload
from generators.release_notes_deployment import (
    extract_deployment_rows_from_docx,
    parse_deployment_id_time,
    parse_deployment_rows,
)

logger = logging.getLogger(__name__)


def merge_deployment_row_sources(
    sources: dict[str, dict],
    rows: list[list[str]],
) -> None:
    """Merge deployment table rows into a client-keyed source map."""
    for row in rows:
        client = (row[0] or "").strip()
        if not client:
            continue
        parts = parse_deployment_id_time(row[3] if len(row) > 3 else "")
        if not parts.get("deployment_id"):
            continue
        if client not in sources:
            sources[client] = parts
            continue
        existing = sources[client]
        for field in ("deployment_id", "deployment_date", "deployment_time"):
            if not existing.get(field) and parts.get(field):
                existing[field] = parts[field]


def collect_history_deploy_info(release_version: str | None = None) -> dict[str, dict]:
    """Deployment IDs from persisted deployment history."""
    merged: dict[str, dict] = {}
    for entry in deployment_history.load_history():
        if release_version and entry.get("version") != release_version:
            continue
        clients = entry.get("clients", {})
        if not isinstance(clients, dict):
            continue
        for client, info in clients.items():
            if not isinstance(info, dict) or not info.get("deployment_id"):
                continue
            if str(client) not in merged:
                merged[str(client)] = {
                    "deployment_id": info.get("deployment_id", ""),
                    "deployment_date": info.get("deployment_date", ""),
                    "deployment_time": info.get("deployment_time", ""),
                }
        if release_version:
            break
    return merged


def build_deploy_prefill(
    grouped_keys: list[str],
    *,
    deployment_row_text: str = "",
    docx_bytes: bytes | None = None,
    sharepoint_url: str = "",
    release_version: str | None = None,
    try_sharepoint_download: bool = True,
) -> tuple[dict[str, dict], list[str]]:
    """Map deployment IDs onto Deployer client keys from notes, docx, SharePoint, history."""
    sources: dict[str, dict] = {}
    source_labels: list[str] = []

    session_rows = parse_deployment_rows(deployment_row_text)
    merge_deployment_row_sources(sources, session_rows)
    if any(info.get("deployment_id") for info in sources.values()):
        source_labels.append("Release Notes deployment rows")

    if isinstance(docx_bytes, bytes) and docx_bytes:
        before = len(sources)
        merge_deployment_row_sources(
            sources,
            extract_deployment_rows_from_docx(docx_bytes),
        )
        if len(sources) > before:
            source_labels.append("generated Release Notes document")

    url = (sharepoint_url or "").strip()
    if url and try_sharepoint_download and not docx_bytes:
        upload_cfg = sharepoint_upload.load_upload_config(config.SHAREPOINT_UPLOAD)
        if upload_cfg.graph.configured():
            try:
                downloaded = sharepoint_upload.download_by_web_url(upload_cfg, url)
                before = len(sources)
                merge_deployment_row_sources(
                    sources,
                    extract_deployment_rows_from_docx(downloaded),
                )
                if len(sources) > before:
                    source_labels.append("SharePoint Release Notes")
            except Exception as exc:  # noqa: BLE001 — prefill is best-effort
                logger.warning("Could not prefill deployment IDs from SharePoint: %s", exc)

    before_history = len(sources)
    for client, info in collect_history_deploy_info(release_version).items():
        if info.get("deployment_id") and client not in sources:
            sources[client] = dict(info)
    if len(sources) > before_history:
        source_labels.append("deployment history")

    prefill: dict[str, dict] = {}
    for src_client, info in sources.items():
        target = (
            src_client
            if src_client in grouped_keys
            else jira_client.fuzzy_match_client(src_client, grouped_keys)
        )
        if target and target not in prefill:
            prefill[target] = dict(info)

    return prefill, source_labels


def deployment_info_from_paste(
    raw_text: str,
    grouped_keys: list[str],
) -> dict[str, dict]:
    """Parse pasted deployment output into a client-keyed deployment_info map."""
    filled: dict[str, dict] = {}
    for item in jira_client.parse_deployment_input(raw_text):
        client = (item.client or "").strip()
        if not client:
            continue
        target = (
            client
            if client in grouped_keys
            else jira_client.fuzzy_match_client(client, grouped_keys)
        )
        if not target:
            continue
        filled[target] = {
            "deployment_id": item.deployment_id,
            "deployment_date": item.deployment_date,
            "deployment_time": item.deployment_time,
        }
    return filled
