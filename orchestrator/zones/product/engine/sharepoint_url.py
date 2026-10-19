"""SharePoint URL host and link-shape validation (UI + MCP shared)."""

from __future__ import annotations

import os
import re
from datetime import date
from urllib.parse import parse_qs, quote, unquote, urlparse

# Path / deep-link markers (host alone is not enough for link-shape soft gate).
_LINK_SHAPE_HINTS = (
    "/sites/",
    "/teams/",
    "/personal/",
    "_layouts/",
    ":w:",
    ":b:",
    ":f:",
    ":p:",
    ":x:",
    ":u:",
    ":v:",
    "Doc.aspx",
    "guestaccess.aspx",
)

_DOCX_HINT = re.compile(r"\.docx(?:$|[?#&])", re.IGNORECASE)
_QUARTER_SUFFIX_RE = re.compile(r"/(\d{4}\s*-\s*Q[1-4])\s*$", re.IGNORECASE)


def allowed_sharepoint_hosts() -> list[str]:
    """Host allow-list from env (comma-separated) plus defaults."""
    raw = os.environ.get("SHAREPOINT_ALLOWED_HOSTS", "").strip()
    hosts: list[str] = []
    if raw:
        hosts.extend(h.strip().lower() for h in raw.split(",") if h.strip())
    # Always accept Microsoft SharePoint Online / OneDrive hosts.
    for default in ("sharepoint.com", "sharepoint.cn", "sharepoint.de", "sharepoint.us"):
        if default not in hosts:
            hosts.append(default)
    return hosts


def _host_allowed(hostname: str, allowed: list[str] | None = None) -> bool:
    host = (hostname or "").strip().lower().rstrip(".")
    if not host:
        return False
    # Accept any host that embeds "sharepoint" (Online + lab hosts like sharepoint.example).
    if "sharepoint" in host:
        return True
    allow = allowed if allowed is not None else allowed_sharepoint_hosts()
    for pattern in allow:
        p = pattern.lower().lstrip(".")
        if not p:
            continue
        if host == p or host.endswith("." + p):
            return True
    return False


def has_sharepoint_link_shape(url: str) -> bool:
    """True when the URL looks like a SharePoint / OneDrive document link."""
    raw = (url or "").strip()
    if not raw:
        return False
    lowered = raw.lower()
    if any(hint in lowered for hint in _LINK_SHAPE_HINTS):
        return True
    if _DOCX_HINT.search(raw):
        return True
    parsed = urlparse(raw)
    qs = parse_qs(parsed.query)
    for key in ("file", "File", "id", "sourcedoc"):
        vals = qs.get(key) or []
        for val in vals:
            if ".docx" in unquote(str(val)).lower() or "sharepoint" in unquote(str(val)).lower():
                return True
    return False


def release_notes_docx_name(version: str) -> str:
    ver = (version or "").strip().lstrip("vV")
    return f"Release Notes {ver}.docx" if ver else "Release Notes.docx"


def client_notes_docx_name(version: str) -> str:
    ver = (version or "").strip().lstrip("vV")
    return f"Client Release Notes {ver}.docx" if ver else "Client Release Notes.docx"


def sibling_sharepoint_url(url: str, *, from_name: str, to_name: str) -> str:
    """Swap a known .docx file name inside a SharePoint URL (same folder)."""
    raw = (url or "").strip()
    src = (from_name or "").strip()
    dest = (to_name or "").strip()
    if not raw or not src or not dest or src == dest:
        return ""
    variants = (
        (src, dest),
        (src.replace(" ", "%20"), dest.replace(" ", "%20")),
        (quote(src, safe=""), quote(dest, safe="")),
    )
    for old, new in variants:
        if old and old in raw:
            return raw.replace(old, new, 1)
    return ""


def sibling_client_notes_url(release_notes_url: str, version: str) -> str:
    return sibling_sharepoint_url(
        release_notes_url,
        from_name=release_notes_docx_name(version),
        to_name=client_notes_docx_name(version),
    )


def validate_sharepoint_url(
    url: str,
    *,
    require_link_shape: bool = False,
    allowed_hosts: list[str] | None = None,
) -> bool:
    """Return True for http(s) SharePoint-looking URLs.

    Parameters
    ----------
    require_link_shape:
        When True, also require a SharePoint path / ``.docx`` / Doc.aspx-style marker.
        Default False keeps host+scheme as the hard gate (link shape is a soft warning).
    """
    u = (url or "").strip()
    if not (u.startswith("http://") or u.startswith("https://")):
        return False
    try:
        parsed = urlparse(u)
    except ValueError:
        return False
    if not _host_allowed(parsed.hostname or "", allowed_hosts):
        return False
    if require_link_shape and not has_sharepoint_link_shape(u):
        return False
    return True


def parse_sharepoint_folder_browse_url(url: str) -> dict[str, str]:
    """Extract browser_automation.sharepoint fields from an AllItems.aspx folder URL.

    Accepts folder browse links (with ``id=`` query) pasted during team onboarding.
    Strips a trailing ``YYYY - QN`` segment so quarter folders stay dynamic per release.
    """
    raw = (url or "").strip()
    if not raw:
        return {}
    try:
        parsed = urlparse(raw)
    except ValueError:
        return {}
    if not _host_allowed(parsed.hostname or ""):
        return {}

    qs = parse_qs(parsed.query)
    id_vals = qs.get("id") or []
    if not id_vals:
        return {}

    id_path = unquote(str(id_vals[0])).strip()
    if not id_path.startswith("/"):
        id_path = f"/{id_path}"

    site_match = re.match(r"^/(teams|sites)/([^/]+)", id_path, re.IGNORECASE)
    if not site_match:
        return {}

    site_type, site_name = site_match.group(1).lower(), site_match.group(2)
    site_path = f"/{site_type}/{site_name}"
    remainder = id_path[len(site_path) :].lstrip("/")
    if not remainder:
        return {}

    auto_quarter = True
    quarter_match = _QUARTER_SUFFIX_RE.search(f"/{remainder}")
    if quarter_match:
        remainder = remainder[: quarter_match.start()].rstrip("/")
        auto_quarter = True

    out: dict[str, str] = {
        "hostname": str(parsed.hostname or "").strip(),
        "site_path": site_path,
        "folder_path": remainder,
    }
    view_vals = qs.get("viewid") or []
    if view_vals:
        out["viewid"] = str(view_vals[0]).strip()
    return out


def month_folder_from_version(fix_version: str) -> str:
    """YYYY.Q.MM.DD → YYYY-MM (e.g. 2026.3.09.16 → 2026-09)."""
    parts = (fix_version or "").strip().split(".")
    if len(parts) < 3:
        raise ValueError(f"Unexpected fix version format: {fix_version}")
    year, month = parts[0], int(parts[2])
    if not (1 <= month <= 12):
        raise ValueError(f"Unexpected month in fix version: {fix_version}")
    return f"{year}-{month:02d}"


def sharepoint_release_file_url(
    *,
    version_name: str,
    filename: str = "",
    download: bool = False,
) -> str:
    """Direct SharePoint file URL for Slack (parity with fitness-bi-release-notes)."""
    import config

    sp = (config.BROWSER_AUTOMATION or {}).get("sharepoint") or {}
    site_url = str(sp.get("site_url") or "").rstrip("/")
    hostname = str(sp.get("hostname") or "").strip()
    if not site_url and hostname:
        site_path = str(sp.get("site_path") or "").strip()
        site_url = f"https://{hostname}{site_path}" if site_path else f"https://{hostname}"
    base_folder = str(sp.get("folder_path") or "Shared Documents/Glofox - Customize/Release Notes").strip()
    if not filename:
        template = str(sp.get("remote_name_template") or "Release Notes {{version}}.docx")
        filename = template.replace("{{version}}", version_name).strip()
    from urllib.parse import quote

    path = f"/{base_folder.lstrip('/')}/{filename}"
    origin = site_url.split("/teams/")[0] if "/teams/" in site_url else site_url.rsplit("/", 1)[0]
    if hostname and "sharepoint" in hostname:
        origin = f"https://{hostname}"
        site_path = str(sp.get("site_path") or "")
        if site_path:
            path = f"{site_path.rstrip('/')}/{base_folder.lstrip('/')}/{filename}".replace("//", "/")
    url = f"{origin}{quote(path, safe='/')}"
    return sharepoint_direct_download_url(url) if download else url


def sharepoint_release_folder_url(*, version_name: str = "") -> str:
    """SharePoint AllItems.aspx folder URL for the release month/quarter."""
    folder_url, _label = resolve_sharepoint_folder_link(version_name=version_name)
    return folder_url


def sharepoint_document_open_url(doc_url: str) -> str:
    """Normalize a SharePoint doc link so Slack/browser opens the file (not download)."""
    raw = (doc_url or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if "action=download" in lowered:
        return re.sub(r"action=download", "action=default", raw, flags=re.IGNORECASE)
    if "download=1" in lowered:
        return re.sub(r"[?&]download=1", "", raw, flags=re.IGNORECASE)
    return raw


def sharepoint_direct_download_url(doc_url: str) -> str:
    """Turn a SharePoint document URL into a direct-download link for Slack."""
    raw = (doc_url or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if "download=1" in lowered or "action=download" in lowered:
        return raw
    if "action=default" in lowered:
        return re.sub(r"action=default", "action=download", raw, flags=re.IGNORECASE)
    parsed = urlparse(raw)
    sep = "&" if parsed.query else "?"
    return f"{raw}{sep}download=1"


def resolve_sharepoint_folder_link(
    *,
    version_name: str = "",
    reference_date: date | None = None,
) -> tuple[str, str]:
    """Return (folder browse URL, human label) for the release quarter folder."""
    from datetime import date as date_cls

    try:
        from browser_automation import (
            resolve_sharepoint_folder_url,
            resolve_sharepoint_quarter_label,
        )

        ref = reference_date or date_cls.today()
        folder_url = resolve_sharepoint_folder_url(
            version_name=version_name,
            reference_date=ref,
        )
        quarter = resolve_sharepoint_quarter_label(
            version_name=version_name,
            reference_date=ref,
        )
        label = f"Release Notes/{quarter}" if quarter else "Release Notes folder"
        return folder_url.strip(), label
    except Exception:  # noqa: BLE001
        return "", "Release Notes folder"


def sharepoint_validation_message(url: str) -> str:
    """Human-readable reason when validation fails, or empty string when OK."""
    u = (url or "").strip()
    if not u:
        return "SharePoint URL is empty."
    if not (u.startswith("http://") or u.startswith("https://")):
        return "SharePoint URL must start with http:// or https://."
    try:
        parsed = urlparse(u)
    except ValueError:
        return "SharePoint URL could not be parsed."
    if not _host_allowed(parsed.hostname or ""):
        return (
            f"Host `{parsed.hostname or '?'}` does not look like SharePoint. "
            "Use a `*.sharepoint.com` link (or set SHAREPOINT_ALLOWED_HOSTS)."
        )
    if not has_sharepoint_link_shape(u):
        return (
            "URL host looks like SharePoint, but the path does not look like a "
            "document link (expected /sites/, Doc.aspx, :w:, or .docx)."
        )
    return ""
