"""SharePoint release-notes upload via Microsoft Graph.

Credentials stay in env
(``MS_GRAPH_*``); folder / site targets live in ``workspace.yaml`` under
``sharepoint_upload``.

Typical flow once credentials exist:

1. ``load_upload_config`` → workspace + Graph status
2. ``plan_upload`` → dry-run preview (safe without credentials)
3. ``upload_release_notes`` → PUT file to drive folder, return web URL

The returned SharePoint link is what Service Ticket + Slack announce already
consume today (``shared_sharepoint_url`` / ``stk_sharepoint``).
"""

from __future__ import annotations

import base64
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import quote

from ms_graph import GraphClient
from sharepoint_url import validate_sharepoint_url

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^\w.\- ()]+", re.UNICODE)


@dataclass
class SharePointUploadConfig:
    """Workspace + env configuration for SharePoint upload."""

    enabled: bool = False
    site_id: str = ""
    drive_id: str = ""
    # Hostname + site path alternative when site_id is unknown, e.g.
    # hostname=contoso.sharepoint.com, site_path=/sites/ReleaseNotes
    hostname: str = ""
    site_path: str = ""
    folder_path: str = "Release Notes"
    remote_name_template: str = "Release Notes {{version}}.docx"
    auto_year_subfolder: bool = False
    auto_quarter_subfolder: bool = False
    auto_month_subfolder: bool = False
    conflict_behavior: str = "replace"  # replace | fail | rename
    graph: GraphClient = field(default_factory=GraphClient)

    def target_ready(self) -> bool:
        if self.drive_id:
            return True
        if self.site_id:
            return True
        return bool(self.hostname and self.site_path)

    def can_upload(self) -> bool:
        return self.enabled and self.graph.configured() and self.target_ready()


@dataclass
class UploadPlan:
    """Dry-run / preview of an upload."""

    local_path: str
    remote_name: str
    folder_path: str
    drive_id: str
    site_id: str
    upload_url: str
    conflict_behavior: str
    bytes_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "local_path": self.local_path,
            "remote_name": self.remote_name,
            "folder_path": self.folder_path,
            "drive_id": self.drive_id,
            "site_id": self.site_id,
            "upload_url": self.upload_url,
            "conflict_behavior": self.conflict_behavior,
            "bytes_size": self.bytes_size,
        }


@dataclass
class UploadResult:
    ok: bool
    web_url: str = ""
    item_id: str = ""
    remote_path: str = ""
    error: str = ""
    dry_run: bool = False
    plan: UploadPlan | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "web_url": self.web_url,
            "item_id": self.item_id,
            "remote_path": self.remote_path,
            "error": self.error,
            "dry_run": self.dry_run,
            "plan": self.plan.to_dict() if self.plan else None,
        }


def load_upload_config(
    workspace_section: dict[str, Any] | None = None,
    *,
    graph: GraphClient | None = None,
) -> SharePointUploadConfig:
    """Build config from a ``sharepoint_upload`` workspace section (+ env Graph)."""
    section = dict(workspace_section or {})
    return SharePointUploadConfig(
        enabled=bool(section.get("enabled", False)),
        site_id=str(section.get("site_id") or "").strip(),
        drive_id=str(section.get("drive_id") or "").strip(),
        hostname=str(section.get("hostname") or "").strip(),
        site_path=str(section.get("site_path") or "").strip(),
        folder_path=(str(section.get("folder_path") or "Release Notes").strip() or "Release Notes"),
        remote_name_template=str(
            section.get("remote_name_template") or "Release Notes {{version}}.docx"
        ).strip(),
        auto_year_subfolder=bool(section.get("auto_year_subfolder", False)),
        auto_quarter_subfolder=bool(section.get("auto_quarter_subfolder", False)),
        auto_month_subfolder=bool(section.get("auto_month_subfolder", False)),
        conflict_behavior=(
            str(section.get("conflict_behavior") or "replace").strip().lower() or "replace"
        ),
        graph=graph or GraphClient(),
    )


def year_label(reference: date | None = None) -> str:
    ref = reference or date.today()
    return str(ref.year)


def quarter_label(reference: date | None = None) -> str:
    """``2026 - Q3`` style folder suffix."""
    ref = reference or date.today()
    quarter = (ref.month - 1) // 3 + 1
    return f"{ref.year} - Q{quarter}"


def month_label(reference: date | None = None) -> str:
    """``2026-10`` style folder (ISO year-month)."""
    ref = reference or date.today()
    return f"{ref.year}-{ref.month:02d}"


def apply_folder_tokens(
    folder_path: str,
    reference: date | None = None,
    *,
    auto_year_subfolder: bool = False,
    auto_quarter_subfolder: bool = False,
    auto_month_subfolder: bool = False,
) -> str:
    """Expand ``{{year}}`` / ``{{quarter}}`` / ``{{month}}`` and optional auto folders.

    Auto folders append only when that token is not already in the path, so
    ``Release Notes/{{quarter}}`` plus ``auto_month_subfolder`` becomes
    ``Release Notes/2026 - Q4/2026-10``.
    """
    folder = (folder_path or "Release Notes").replace("\\", "/").strip().strip("/")
    ref = reference or date.today()
    had_year = "{{year}}" in folder
    had_quarter = "{{quarter}}" in folder
    had_month = "{{month}}" in folder
    folder = (
        folder.replace("{{year}}", year_label(ref))
        .replace("{{quarter}}", quarter_label(ref))
        .replace("{{month}}", month_label(ref))
    )
    extras: list[str] = []
    if auto_year_subfolder and not had_year:
        extras.append(year_label(ref))
    if auto_quarter_subfolder and not had_quarter:
        extras.append(quarter_label(ref))
    if auto_month_subfolder and not had_month:
        extras.append(month_label(ref))
    if extras:
        folder = "/".join([folder, *extras])
    return folder


def resolve_folder_path(
    cfg: SharePointUploadConfig,
    *,
    reference_date: date | None = None,
) -> str:
    """Apply year/quarter/month tokens and auto subfolders from the release date."""
    return apply_folder_tokens(
        cfg.folder_path or "Release Notes",
        reference_date or date.today(),
        auto_year_subfolder=cfg.auto_year_subfolder,
        auto_quarter_subfolder=cfg.auto_quarter_subfolder,
        auto_month_subfolder=cfg.auto_month_subfolder,
    )


def default_remote_name(version: str, template: str | None = None) -> str:
    tmpl = (template or "Release Notes {{version}}.docx").strip()
    ver = (version or "").strip().lstrip("vV")
    if not ver:
        ver = date.today().strftime("%Y.%m.%d")
    return sanitize_remote_name(tmpl.replace("{{version}}", ver))


def default_client_remote_name(version: str) -> str:
    return default_remote_name(version, "Client Release Notes {{version}}.docx")


def sanitize_remote_name(name: str) -> str:
    """Make a SharePoint-safe file name, keeping ``.docx`` when present."""
    base = (name or "Release Notes.docx").strip() or "Release Notes.docx"
    cleaned = _SAFE_NAME_RE.sub("_", base).strip(" ._")
    if not cleaned.lower().endswith(".docx"):
        cleaned = f"{cleaned}.docx" if cleaned else "Release Notes.docx"
    return cleaned


def _folder_segments(folder_path: str) -> str:
    parts = [p.strip().strip("/") for p in (folder_path or "").split("/") if p.strip()]
    return "/".join(parts)


def ensure_folder_path(cfg: SharePointUploadConfig, folder_path: str) -> list[str]:
    """Create each SharePoint folder segment if missing (year / quarter / month).

    Graph ``nameAlreadyExists`` (409) is treated as success so monthly folders
    can be created once and reused for later uploads.
    """
    drive_id = resolve_drive_id(cfg)
    created: list[str] = []
    parent = ""
    for seg in _folder_segments(folder_path).split("/"):
        if not seg:
            continue
        if parent:
            encoded = "/".join(quote(p, safe="") for p in parent.split("/"))
            children_url = f"/drives/{drive_id}/root:/{encoded}:/children"
        else:
            children_url = f"/drives/{drive_id}/root/children"
        status, body = cfg.graph.request(
            "POST",
            children_url,
            json_body={
                "name": seg,
                "folder": {},
                "@microsoft.graph.conflictBehavior": "fail",
            },
        )
        if status in (200, 201):
            created.append(seg)
        elif status not in (409, 405):
            err = body if isinstance(body, str) else (body or {})
            code = ""
            if isinstance(err, dict):
                code = str((err.get("error") or {}).get("code") or "")
            if code.lower() not in {"namealreadyexists", "itemnotfound"} and status >= 400:
                raise RuntimeError(
                    f"Could not create SharePoint folder '{parent + '/' + seg if parent else seg}' "
                    f"(HTTP {status}): {body}"
                )
        parent = f"{parent}/{seg}" if parent else seg
    return created


def resolve_drive_id(cfg: SharePointUploadConfig) -> str:
    """Return drive id, resolving from site when needed."""
    if cfg.drive_id:
        return cfg.drive_id
    site_id = cfg.site_id
    if not site_id and cfg.hostname and cfg.site_path:
        path = cfg.site_path if cfg.site_path.startswith("/") else f"/{cfg.site_path}"
        status, body = cfg.graph.request("GET", f"/sites/{cfg.hostname}:{path}")
        if status >= 400 or not isinstance(body, dict) or not body.get("id"):
            raise RuntimeError(f"Could not resolve SharePoint site (HTTP {status}): {body}")
        site_id = str(body["id"])
        cfg.site_id = site_id
    if not site_id:
        raise RuntimeError(
            "SharePoint target incomplete — set sharepoint_upload.drive_id or "
            "site_id / hostname+site_path in workspace.yaml."
        )
    status, body = cfg.graph.request("GET", f"/sites/{site_id}/drive")
    if status >= 400 or not isinstance(body, dict) or not body.get("id"):
        raise RuntimeError(f"Could not resolve SharePoint drive (HTTP {status}): {body}")
    cfg.drive_id = str(body["id"])
    return cfg.drive_id


def build_upload_url(drive_id: str, folder_path: str, remote_name: str) -> str:
    folder = _folder_segments(folder_path)
    remote = sanitize_remote_name(remote_name)
    # Graph path encoding: encode each segment but keep `/` separators.
    encoded_folder = "/".join(quote(seg, safe="") for seg in folder.split("/")) if folder else ""
    encoded_name = quote(remote, safe="")
    if encoded_folder:
        item_path = f"{encoded_folder}/{encoded_name}"
    else:
        item_path = encoded_name
    return f"/drives/{drive_id}/root:/{item_path}:/content"


def build_share_id(web_url: str) -> str:
    """Encode a SharePoint sharing URL for the Graph ``/shares`` endpoint."""
    raw = (web_url or "").strip()
    if not validate_sharepoint_url(raw):
        raise ValueError("A valid SharePoint document URL is required.")
    encoded = base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")
    return f"u!{encoded}"


def download_by_web_url(cfg: SharePointUploadConfig, web_url: str) -> bytes:
    """Download a SharePoint document through its sharing URL."""
    if not cfg.graph.configured():
        raise RuntimeError(
            "Microsoft Graph credentials are not configured. Set MS_GRAPH_* first."
        )
    share_id = build_share_id(web_url)
    status_code, body = cfg.graph.request(
        "GET",
        f"/shares/{share_id}/driveItem/content",
    )
    if status_code >= 400:
        raise RuntimeError(f"SharePoint download failed (HTTP {status_code}): {body}")
    if isinstance(body, bytes):
        return body
    raise RuntimeError(
        "SharePoint download returned a non-binary response; verify the link and Graph permissions."
    )


def plan_upload(
    cfg: SharePointUploadConfig,
    local_path: str,
    *,
    remote_name: str | None = None,
    version: str = "",
    reference_date: date | None = None,
) -> UploadPlan:
    """Build an upload plan without calling Graph (except optional drive resolve)."""
    path = os.path.abspath(local_path)
    folder = resolve_folder_path(cfg, reference_date=reference_date)
    name = sanitize_remote_name(
        remote_name
        or default_remote_name(version, cfg.remote_name_template)
        or os.path.basename(path)
        or "Release Notes.docx"
    )
    size = os.path.getsize(path) if os.path.isfile(path) else 0
    drive_id = cfg.drive_id or "(resolve-at-upload)"
    upload_url = (
        build_upload_url(drive_id, folder, name)
        if cfg.drive_id
        else f"/drives/{{drive_id}}/root:/{_folder_segments(folder)}/{name}:/content"
    )
    return UploadPlan(
        local_path=path,
        remote_name=name,
        folder_path=folder,
        drive_id=drive_id if cfg.drive_id else "",
        site_id=cfg.site_id,
        upload_url=upload_url,
        conflict_behavior=cfg.conflict_behavior,
        bytes_size=size,
    )


def status(cfg: SharePointUploadConfig) -> dict[str, Any]:
    graph_status = cfg.graph.status()
    return {
        "feature": "sharepoint_upload",
        "enabled": cfg.enabled,
        "target_ready": cfg.target_ready(),
        "can_upload": cfg.can_upload(),
        "folder_path": cfg.folder_path,
        "site_id_set": bool(cfg.site_id),
        "drive_id_set": bool(cfg.drive_id),
        "hostname": cfg.hostname,
        "site_path": cfg.site_path,
        "conflict_behavior": cfg.conflict_behavior,
        "graph": graph_status,
        "note": (
            "Backend ready — set MS_GRAPH_* credentials and enable "
            "sharepoint_upload in workspace.yaml. UI and MCP wizard upload are wired."
        ),
    }


def upload_release_notes(
    cfg: SharePointUploadConfig,
    local_path: str,
    *,
    remote_name: str | None = None,
    version: str = "",
    reference_date: date | None = None,
    dry_run: bool = True,
) -> UploadResult:
    """Upload a local ``.docx`` to the configured SharePoint folder.

    Default ``dry_run=True`` so callers (MCP / future UI) preview safely before
    credentials are configured.
    """
    path = os.path.abspath(local_path)
    if not os.path.isfile(path):
        return UploadResult(ok=False, error=f"Local file not found: {path}")

    plan = plan_upload(
        cfg,
        path,
        remote_name=remote_name,
        version=version,
        reference_date=reference_date,
    )
    if dry_run or not cfg.enabled:
        reason = ""
        if not cfg.enabled:
            reason = "sharepoint_upload.enabled is false"
        return UploadResult(
            ok=True,
            dry_run=True,
            plan=plan,
            remote_path=f"{plan.folder_path}/{plan.remote_name}".strip("/"),
            error=reason,
            web_url="",
        )

    if not cfg.graph.configured():
        return UploadResult(
            ok=False,
            dry_run=False,
            plan=plan,
            error="Microsoft Graph credentials are not configured (MS_GRAPH_*).",
        )
    if not cfg.target_ready():
        return UploadResult(
            ok=False,
            dry_run=False,
            plan=plan,
            error="SharePoint target incomplete in workspace.yaml (drive_id or site).",
        )

    try:
        drive_id = resolve_drive_id(cfg)
        ensure_folder_path(cfg, plan.folder_path)
        plan.drive_id = drive_id
        plan.site_id = cfg.site_id
        plan.upload_url = build_upload_url(drive_id, plan.folder_path, plan.remote_name)
        with open(path, "rb") as fh:
            content = fh.read()
        headers = {"@microsoft.graph.conflictBehavior": cfg.conflict_behavior}
        # conflictBehavior is a query param on the upload URL for simple uploads
        upload_path = plan.upload_url
        sep = "&" if "?" in upload_path else "?"
        upload_path = f"{upload_path}{sep}@microsoft.graph.conflictBehavior={cfg.conflict_behavior}"
        status_code, body = cfg.graph.request(
            "PUT",
            upload_path,
            content=content,
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            extra_headers=headers,
        )
    except Exception as exc:
        logger.exception("SharePoint upload failed")
        return UploadResult(ok=False, dry_run=False, plan=plan, error=str(exc))

    if status_code >= 400 or not isinstance(body, dict):
        return UploadResult(
            ok=False,
            dry_run=False,
            plan=plan,
            error=f"SharePoint upload failed (HTTP {status_code}): {body}",
        )

    web_url = str(body.get("webUrl") or body.get("web_url") or "").strip()
    item_id = str(body.get("id") or "").strip()
    if web_url and not validate_sharepoint_url(web_url):
        logger.warning("Upload succeeded but webUrl failed SharePoint validation: %s", web_url)

    return UploadResult(
        ok=True,
        dry_run=False,
        plan=plan,
        web_url=web_url,
        item_id=item_id,
        remote_path=f"{plan.folder_path}/{plan.remote_name}".strip("/"),
    )


__all__ = [
    "SharePointUploadConfig",
    "UploadPlan",
    "UploadResult",
    "build_share_id",
    "build_upload_url",
    "default_remote_name",
    "download_by_web_url",
    "load_upload_config",
    "plan_upload",
    "quarter_label",
    "resolve_drive_id",
    "resolve_folder_path",
    "sanitize_remote_name",
    "status",
    "upload_release_notes",
]
