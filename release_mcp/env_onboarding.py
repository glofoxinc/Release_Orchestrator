"""Natural-language `.env` onboarding — parse random chat inputs into required params."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import team_crew as tc

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"
_ENV_EXAMPLE = _PROJECT_ROOT / ".env.example"

# Keys the guided onboard flow may auto-write (never commit `.env`).
_ONBOARD_ENV_KEYS = frozenset({
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "DEFAULT_JIRA_TEAM",
    "DEFAULT_JIRA_TEAM_ID",
    "DEFAULT_PROJECTS",
    "DEFAULT_SELECTION_MODE",
})

_PLACEHOLDER_TOKENS = frozenset({
    "",
    "your-api-token-here",
    "changeme",
    "your-org",
    "you@company.com",
})

_ATLASSIAN_URL_RE = re.compile(
    r"https?://[\w.-]+\.atlassian\.net/?",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_JIRA_TOKEN_RE = re.compile(r"\bATATT[\w-]+\b")
_KV_RE = re.compile(
    r"(?P<key>[A-Z][A-Z0-9_]{2,})\s*=\s*(?P<value>.+?)(?:\s|$)",
    re.IGNORECASE,
)
_PROJECT_CODE_RE = re.compile(r"\b(PIC|AN)\b", re.IGNORECASE)
_ORG_SLUG_RE = re.compile(r"\b(?:org(?:anization)?|site|jira)\s+(?:is\s+)?([a-z0-9-]+)\b", re.I)


def _env_path() -> Path:
    return _ENV_FILE


def _read_env_file() -> dict[str, str]:
    path = _env_path()
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _env(name: str) -> str:
    return (os.environ.get(name) or _read_env_file().get(name) or "").strip()


def required_env_specs() -> tuple[dict[str, Any], ...]:
    """Required + recommended `.env` params for onboarding checklist."""
    return (
        {
            "key": "JIRA_BASE_URL",
            "label": "Jira site URL",
            "required": True,
            "phase": "credentials",
            "example": "https://abcfinancial.atlassian.net",
            "say_examples": [
                "jira url https://abcfinancial.atlassian.net",
                "org is abcfinancial",
                "JIRA_BASE_URL=https://abcfinancial.atlassian.net",
            ],
            "check": lambda: bool(_env("JIRA_BASE_URL") and "atlassian.net" in _env("JIRA_BASE_URL")),
        },
        {
            "key": "JIRA_EMAIL",
            "label": "Jira account email",
            "required": True,
            "phase": "credentials",
            "example": "you@abcfitness.com",
            "say_examples": ["email you@abcfitness.com", "my jira email is you@abcfitness.com"],
            "check": lambda: bool(_env("JIRA_EMAIL") and "@" in _env("JIRA_EMAIL")),
        },
        {
            "key": "JIRA_API_TOKEN",
            "label": "Jira API token",
            "required": True,
            "phase": "credentials",
            "example": "ATATT3x… (from id.atlassian.com)",
            "say_examples": ["paste token in .env only — or say JIRA_API_TOKEN=ATATT… in chat if you accept"],
            "check": lambda: bool(
                _env("JIRA_API_TOKEN") and _env("JIRA_API_TOKEN") not in _PLACEHOLDER_TOKENS
            ),
        },
        {
            "key": "DEFAULT_JIRA_TEAM",
            "label": "Jira team name",
            "required": True,
            "phase": "team",
            "example": "Glofox Insights Customize",
            "say_examples": ["use glofox", "use ignite", "use etl", "team glofox"],
            "check": lambda: bool(_env("DEFAULT_JIRA_TEAM")),
        },
        {
            "key": "DEFAULT_PROJECTS",
            "label": "Jira projects",
            "required": True,
            "phase": "team",
            "example": "PIC,AN",
            "say_examples": ["projects pic an", "project pic", "we use PIC and AN"],
            "check": lambda: bool(_env("DEFAULT_PROJECTS")),
        },
        {
            "key": "DEFAULT_SELECTION_MODE",
            "label": "Ticket selection mode",
            "required": False,
            "phase": "optional",
            "example": "status",
            "say_examples": ["selection mode status"],
            "check": lambda: bool(_env("DEFAULT_SELECTION_MODE")),
        },
    )


def assess_env_params() -> dict[str, Any]:
    """Status of each onboard-relevant `.env` param."""
    rows: list[dict[str, Any]] = []
    missing_required: list[str] = []
    for spec in required_env_specs():
        ok = bool(spec["check"]())
        row = {
            "key": spec["key"],
            "label": spec["label"],
            "required": spec["required"],
            "done": ok,
            "example": spec["example"],
            "current": _env(spec["key"]) if ok else "",
        }
        rows.append(row)
        if spec["required"] and not ok:
            missing_required.append(spec["key"])
    return {
        "env_file_exists": _env_path().is_file(),
        "env_path": str(_env_path()),
        "items": rows,
        "required_missing": missing_required,
        "credentials_ready": all(
            r["done"] for r in rows if r["key"] in {"JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN"}
        ),
        "team_ready": all(r["done"] for r in rows if r["key"] in {"DEFAULT_JIRA_TEAM", "DEFAULT_PROJECTS"}),
        "all_required_ready": not missing_required,
    }


def format_env_checklist(*, compact: bool = False) -> str:
    """Human-readable checklist of required `.env` params."""
    status = assess_env_params()
    lines = ["**`.env` checklist** (say values in chat — agent writes `.env` for you)", ""]
    for row in status["items"]:
        mark = "✅" if row["done"] else "⬜"
        req = " *required*" if row["required"] else ""
        lines.append(f"{mark} **`{row['key']}`** — {row['label']}{req}")
        if not row["done"]:
            lines.append(f"   Example: `{row['example']}`")
    if compact:
        missing = status["required_missing"]
        if missing:
            lines.append("")
            lines.append(f"Still need: **{', '.join(missing)}**")
        return "\n".join(lines)

    lines.extend([
        "",
        "**Say naturally (any order):**",
        "- `org is abcfinancial` or paste full Jira URL",
        "- `email you@abcfitness.com`",
        "- `use glofox` / `use ignite` / `projects pic an`",
        "- Token: paste in `.env` only (recommended) — or `JIRA_API_TOKEN=ATATT…`",
        "",
        "Or say **`env checklist`** anytime.",
    ])
    return "\n".join(lines)


def _next_missing_spec() -> dict[str, Any] | None:
    for spec in required_env_specs():
        if spec["required"] and not spec["check"]():
            return spec
    return None


def format_next_env_question() -> str:
    """One friendly question for the next missing required param."""
    spec = _next_missing_spec()
    if not spec:
        return "All required `.env` params are set. Say **mcp configured** or **production ready**."
    examples = spec.get("say_examples") or []
    ex = examples[0] if examples else spec["example"]
    return (
        f"**Next for `.env`:** {spec['label']} (`{spec['key']}`)\n\n"
        f"Example: `{ex}`\n\n"
        f"Or say **`env checklist`** to see everything."
    )


def parse_env_from_message(message: str) -> dict[str, str]:
    """Extract `.env` key/value pairs from free-form chat (no file write)."""
    raw = (message or "").strip()
    lowered = raw.lower()
    found: dict[str, str] = {}

    for match in _KV_RE.finditer(raw):
        key = match.group("key").upper()
        if key in _ONBOARD_ENV_KEYS:
            found[key] = match.group("value").strip().strip('"').strip("'")

    for url in _ATLASSIAN_URL_RE.findall(raw):
        found["JIRA_BASE_URL"] = url.rstrip("/")
        break

    org_match = _ORG_SLUG_RE.search(raw)
    if org_match and "JIRA_BASE_URL" not in found:
        slug = org_match.group(1).strip().lower()
        if slug and slug not in {"jira", "atlassian", "cloud"}:
            found["JIRA_BASE_URL"] = f"https://{slug}.atlassian.net"

    if "abcfinancial" in lowered or "abc fitness" in lowered:
        found.setdefault("JIRA_BASE_URL", "https://abcfinancial.atlassian.net")

    if any(p in lowered for p in ("jira email", "my email", "email is", "email:")) or lowered.startswith(
        "email "
    ):
        emails = _EMAIL_RE.findall(raw)
        if emails:
            found["JIRA_EMAIL"] = emails[0]

    if "token" in lowered or "api token" in lowered or "JIRA_API_TOKEN" in raw.upper():
        token_match = _JIRA_TOKEN_RE.search(raw)
        if token_match:
            found["JIRA_API_TOKEN"] = token_match.group(0)

    team_key = tc.resolve_team_key_from_phrase(lowered)
    if team_key:
        profile = tc.load_team_profile(team_key)
        if profile:
            found["DEFAULT_JIRA_TEAM"] = profile.display_name
            if profile.jira_team_id:
                found["DEFAULT_JIRA_TEAM_ID"] = profile.jira_team_id
            if profile.default_projects:
                found["DEFAULT_PROJECTS"] = ",".join(profile.default_projects)

    projects = tc.parse_projects_phrase(lowered)
    if projects and (
        "project" in lowered or "projects" in lowered or "proj " in lowered or "use pic" in lowered
    ):
        found["DEFAULT_PROJECTS"] = ",".join(projects)
    elif any(p in lowered for p in ("project", "projects", "proj ")) and _PROJECT_CODE_RE.search(raw):
        codes = {m.upper() for m in _PROJECT_CODE_RE.findall(raw)}
        if codes:
            found["DEFAULT_PROJECTS"] = ",".join(sorted(codes))

    if "selection mode" in lowered or "select by status" in lowered:
        found["DEFAULT_SELECTION_MODE"] = "status"
    if "selection mode fix" in lowered or "fix version" in lowered:
        found["DEFAULT_SELECTION_MODE"] = "fix_version"

    return found


def ensure_env_file_from_example() -> bool:
    """Create `.env` from `.env.example` if missing."""
    target = _env_path()
    if target.is_file():
        return True
    if not _ENV_EXAMPLE.is_file():
        target.write_text(
            "\n".join(
                [
                    "JIRA_BASE_URL=",
                    "JIRA_EMAIL=",
                    "JIRA_API_TOKEN=",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return True
    target.write_text(_ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    return True


def merge_env_updates(updates: dict[str, str], *, env_path: Path | None = None) -> dict[str, Any]:
    """Merge parsed keys into `.env` without touching unrelated lines."""
    if not updates:
        return {"ok": True, "written": [], "path": str(_env_path())}

    ensure_env_file_from_example()
    target = env_path or _env_path()
    allowed = {k: v for k, v in updates.items() if k in _ONBOARD_ENV_KEYS and str(v).strip()}
    if not allowed:
        return {"ok": True, "written": [], "path": str(target)}

    lines = target.read_text(encoding="utf-8").splitlines() if target.is_file() else []
    seen: set[str] = set()
    merged: list[str] = []
    for line in lines:
        key = line.split("=", 1)[0].strip() if "=" in line else ""
        if key in allowed:
            merged.append(f"{key}={allowed[key]}")
            seen.add(key)
        else:
            merged.append(line.rstrip())

    for key, value in allowed.items():
        if key not in seen:
            if merged and merged[-1].strip():
                merged.append("")
            merged.append(f"{key}={value}")

    target.write_text("\n".join(merged).rstrip() + "\n", encoding="utf-8")

    # Refresh process env for same-session checks
    for key, value in allowed.items():
        os.environ[key] = value

    return {"ok": True, "written": sorted(allowed.keys()), "path": str(target)}


def process_env_message(message: str) -> dict[str, Any]:
    """Parse chat, write `.env`, return status + next prompt."""
    lowered = (message or "").lower().strip()
    if lowered in {"env checklist", "env params", "show env", "env status", ".env checklist"}:
        return {
            "action": "checklist",
            "prompt": format_env_checklist(),
            "status": assess_env_params(),
        }

    parsed = parse_env_from_message(message)
    merge_result = merge_env_updates(parsed) if parsed else {"ok": True, "written": []}
    after = assess_env_params()

    lines: list[str] = []
    if merge_result.get("written"):
        keys = ", ".join(f"`{k}`" for k in merge_result["written"])
        lines.append(f"Updated `.env`: {keys}")
    elif parsed:
        lines.append("Nothing new to write — values may already be set or unrecognized.")
    else:
        lines.append(format_next_env_question())
        return {
            "action": "question",
            "parsed": parsed,
            "merge": merge_result,
            "status": after,
            "prompt": "\n".join(lines),
        }

    if after["all_required_ready"]:
        lines.append("")
        lines.append("**All required `.env` params set.** Continue setup — say **done** or **mcp configured**.")
    else:
        lines.append("")
        lines.append(format_next_env_question())

    return {
        "action": "updated",
        "parsed": parsed,
        "merge": merge_result,
        "status": after,
        "prompt": "\n".join(lines),
    }


def is_env_onboarding_message(message: str) -> bool:
    """True when message likely carries `.env` inputs or asks for checklist."""
    raw = (message or "").strip()
    lowered = raw.lower()
    if lowered in {"env checklist", "env params", "show env", "env status", ".env checklist"}:
        return True
    if parse_env_from_message(raw):
        return True
    if _KV_RE.search(raw) and any(k in raw.upper() for k in _ONBOARD_ENV_KEYS):
        return True
    return False
