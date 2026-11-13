"""Isolated MCP program packs (Glofox vs Ignite vs ETL).

Active program is ``RELEASE_PROGRAM`` (default ``glofox``). Crew, QA, leaders,
review-call rules, SharePoint, and Slack from one pack never fill another.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from orchestrator.paths import KNOWLEDGE_DIR, REPO_ROOT

PROGRAMS_DIR = KNOWLEDGE_DIR / "programs"
DEFAULT_PROGRAM = "glofox"
KNOWN_PROGRAMS = ("glofox", "ignite", "etl")
ENV_KEY = "RELEASE_PROGRAM"


def _pack_path(key: str) -> Path:
    return PROGRAMS_DIR / f"{key.strip().lower()}.yaml"


def normalize_program_key(raw: str | None) -> str:
    key = (raw or "").strip().lower()
    if key in KNOWN_PROGRAMS:
        return key
    return DEFAULT_PROGRAM


def active_program_key() -> str:
    return normalize_program_key(os.getenv(ENV_KEY) or DEFAULT_PROGRAM)


def load_program(key: str | None = None) -> dict[str, Any]:
    pack_key = normalize_program_key(key or active_program_key())
    path = _pack_path(pack_key)
    if not path.is_file():
        return {
            "program": pack_key,
            "trained": False,
            "error": f"Missing program pack {path}",
            "crew": {},
        }
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        return {"program": pack_key, "trained": False, "crew": {}}
    data["program"] = pack_key
    data["pack_path"] = str(path)
    return data


def _crew_rows(pack: dict[str, Any], group: str) -> list[dict[str, Any]]:
    rows = ((pack.get("crew") or {}).get(group)) or []
    out: list[dict[str, Any]] = []
    for item in rows:
        if isinstance(item, dict):
            out.append(item)
    return out


def _exclude_emails(pack: dict[str, Any]) -> set[str]:
    emails: set[str] = set()
    for row in _crew_rows(pack, "exclude"):
        em = str(row.get("email") or "").strip().lower()
        if em:
            emails.add(em)
    return emails


def _issue_assignee(issue: dict[str, Any]) -> tuple[str, str]:
    assignee = issue.get("assignee")
    if isinstance(assignee, dict):
        name = str(assignee.get("displayName") or assignee.get("name") or "").strip()
        email = str(
            assignee.get("emailAddress") or assignee.get("email") or ""
        ).strip()
        return name, email
    name = str(issue.get("assignee") or issue.get("assignee_name") or "").strip()
    email = str(issue.get("assignee_email") or issue.get("email") or "").strip()
    return name, email


def build_program_review_attendees(
    issues: list[dict[str, Any]] | None = None,
    program_key: str | None = None,
) -> list[dict[str, str]]:
    """Glofox-style review invite: leadership + QA + ticket owners required; squad optional."""
    pack = load_program(program_key)
    exclude = _exclude_emails(pack)
    attendees: list[dict[str, str]] = []
    seen: set[str] = set()

    def add(email: str, name: str = "", invite_type: str = "required") -> None:
        norm = email.strip().lower()
        if not norm or norm in exclude or norm in seen:
            return
        seen.add(norm)
        row: dict[str, str] = {"email": email.strip(), "type": invite_type}
        if name.strip():
            row["name"] = name.strip()
        attendees.append(row)

    for row in _crew_rows(pack, "leadership") + _crew_rows(pack, "qa"):
        add(str(row.get("email") or ""), str(row.get("name") or ""), "required")

    for issue in issues or []:
        name, email = _issue_assignee(issue)
        add(email, name, "required")

    for row in _crew_rows(pack, "squad"):
        name = str(row.get("name") or "").strip()
        email = str(row.get("email") or "").strip()
        if not email:
            continue
        if "rekha" in name.lower():
            add(email, name, "required")
        else:
            add(email, name, "optional")

    for row in _crew_rows(pack, "optional"):
        add(str(row.get("email") or ""), str(row.get("name") or ""), "optional")

    return attendees


def issue_rows_from_jira_issues(jira_issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize Jira REST issues for build_program_review_attendees."""
    rows: list[dict[str, Any]] = []
    for raw in jira_issues:
        fields = raw.get("fields") or {}
        assignee = fields.get("assignee") or {}
        key = str(raw.get("key") or "").strip()
        summary = str(fields.get("summary") or "").strip()
        rows.append(
            {
                "key": key,
                "summary": summary,
                "assignee": str(assignee.get("displayName") or ""),
                "assignee_email": str(assignee.get("emailAddress") or ""),
            }
        )
    return rows


def build_review_call_subject(start: datetime, *, timezone_name: str = "Asia/Kolkata") -> str:
    """US-style subject date to match Glofox review call convention (Review call MM/DD/YYYY)."""
    from zoneinfo import ZoneInfo

    dt = start
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(timezone_name))
    local = dt.astimezone(ZoneInfo(timezone_name))
    return f"Review call {local.strftime('%m/%d/%Y')}"


def build_review_call_body(
    issues: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    *,
    timezone_name: str = "Asia/Kolkata",
    jira_site: str = "https://abcfinancial.atlassian.net/browse",
) -> str:
    """Ticket-only agenda body for Glofox ad-hoc review calls."""
    from zoneinfo import ZoneInfo

    start_l = start if start.tzinfo else start.replace(tzinfo=ZoneInfo(timezone_name))
    end_l = end if end.tzinfo else end.replace(tzinfo=ZoneInfo(timezone_name))
    start_l = start_l.astimezone(ZoneInfo(timezone_name))
    end_l = end_l.astimezone(ZoneInfo(timezone_name))
    tz_label = "IST" if timezone_name == "Asia/Kolkata" else timezone_name
    st = start_l.strftime("%I:%M %p").lstrip("0")
    et = end_l.strftime("%I:%M %p").lstrip("0")
    header = (
        f"Glofox release review — {start_l.day} {start_l.strftime('%b %Y')}, "
        f"{st}–{et} {tz_label}"
    )
    lines = [header, ""]
    for issue in issues:
        key = str(issue.get("key") or "").strip()
        name = str(issue.get("assignee") or issue.get("assignee_name") or "").strip()
        if key:
            lines.append(f"{key} — {jira_site}/{key} — {name}")
    return "\n".join(lines).strip()


def crew_names(pack: dict[str, Any], group: str) -> list[str]:
    rows = ((pack.get("crew") or {}).get(group)) or []
    names: list[str] = []
    for item in rows:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.append(name)
        elif str(item).strip():
            names.append(str(item).strip())
    return names


def is_trained(key: str | None = None) -> bool:
    return bool(load_program(key).get("trained"))


def clash_if_untrained(target: str) -> dict[str, Any] | None:
    """Block using another program's people when that pack is not trained."""
    key = normalize_program_key(target)
    pack = load_program(key)
    if pack.get("trained"):
        return None
    active = active_program_key()
    return {
        "ok": False,
        "clash_prevented": True,
        "requested_program": key,
        "active_program": active,
        "trained": False,
        "error": (
            f"{pack.get('display_name') or key} is not trained. "
            f"Do not use {active} squad, QA, leaders, Slack, or SharePoint for {key}. "
            f"Train {key} later with its own roster."
        ),
    }


def program_context() -> dict[str, Any]:
    """Attached to every MCP tool response so agents never mix programs."""
    key = active_program_key()
    pack = load_program(key)
    return {
        "program": key,
        "trained": bool(pack.get("trained")),
        "display_name": pack.get("display_name") or key,
        "projects": list(pack.get("projects") or []),
        "isolation": pack.get("isolation") or {},
        "review_call": pack.get("review_call") or {},
        "developer_comments": pack.get("developer_comments") or {},
        "squad": crew_names(pack, "squad"),
        "leadership": crew_names(pack, "leadership"),
        "qa": crew_names(pack, "qa"),
        "optional": crew_names(pack, "optional"),
        "exclude": crew_names(pack, "exclude"),
        "org_leaders": pack.get("org_leaders") or {},
        "test_by_pool": list(pack.get("test_by_pool") or []),
        "hint": (
            "This MCP session is bound to this program pack only. "
            "Ignite/ETL training is a separate pack — never copy Glofox people."
            if key == "glofox"
            else "This program pack is isolated. Do not reuse another team's crew."
        ),
    }


def train_program(key: str = DEFAULT_PROGRAM, *, lock_env: bool = False) -> dict[str, Any]:
    """Mark the pack as the MCP source of truth. Glofox is already trained in git."""
    pack_key = normalize_program_key(key)
    pack = load_program(pack_key)
    if pack_key != "glofox" and not pack.get("trained"):
        return {
            "ok": False,
            "program": pack_key,
            "trained": False,
            "clash_prevented": True,
            "error": (
                f"{pack_key} has no roster yet. Collect that team's squad, QA, "
                "leadership, optional, and exclude lists — do not copy glofox.yaml."
            ),
            "setup_note": pack.get("setup_note") or "",
        }
    if not pack.get("trained"):
        return {"ok": False, "program": pack_key, "trained": False, "error": "Pack is not trained."}
    result: dict[str, Any] = {
        "ok": True,
        "program": pack_key,
        "trained": True,
        "display_name": pack.get("display_name"),
        "projects": pack.get("projects"),
        "review_call": pack.get("review_call"),
        "developer_comments": pack.get("developer_comments"),
        "squad": crew_names(pack, "squad"),
        "leadership": crew_names(pack, "leadership"),
        "qa": crew_names(pack, "qa"),
        "optional": crew_names(pack, "optional"),
        "exclude": crew_names(pack, "exclude"),
        "org_leaders": pack.get("org_leaders"),
        "test_by_pool": pack.get("test_by_pool"),
        "sharepoint": pack.get("sharepoint"),
        "message": (
            f"{pack.get('display_name')} is the trained MCP program. "
            "Review call = leadership + QA + in-squad ticket owners. "
            "Developers comment only ready for review / ready for release."
        ),
    }
    if lock_env:
        import team_crew as tc

        locked = tc.lock_crew_from_profile(pack_key)
        result["env_lock"] = locked
        os.environ[ENV_KEY] = pack_key
        _upsert_env_program(pack_key)
        result["active"] = pack_key
    else:
        result["active"] = active_program_key()
    return result


def switch_program(key: str) -> dict[str, Any]:
    blocked = clash_if_untrained(key)
    if blocked:
        return blocked
    pack_key = normalize_program_key(key)
    os.environ[ENV_KEY] = pack_key
    _upsert_env_program(pack_key)
    return {"ok": True, "active": pack_key, **program_context()}


def _upsert_env_program(key: str, env_path: Path | None = None) -> None:
    target = env_path or (REPO_ROOT / ".env")
    line = f"{ENV_KEY}={key}"
    if not target.is_file():
        return
    rows = target.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    found = False
    for row in rows:
        if row.startswith(f"{ENV_KEY}="):
            out.append(line)
            found = True
        else:
            out.append(row)
    if not found:
        out.append(line)
    target.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def list_programs() -> list[dict[str, Any]]:
    rows = []
    for key in KNOWN_PROGRAMS:
        pack = load_program(key)
        rows.append(
            {
                "program": key,
                "trained": bool(pack.get("trained")),
                "display_name": pack.get("display_name") or key,
                "projects": pack.get("projects") or [],
                "active": key == active_program_key(),
            }
        )
    return rows
