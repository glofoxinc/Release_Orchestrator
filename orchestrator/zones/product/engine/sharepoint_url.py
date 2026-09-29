"""SharePoint URL host and link-shape validation (UI + MCP shared)."""

from __future__ import annotations

import os
import re
from datetime import date
from urllib.parse import parse_qs, unquote, urlparse

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
