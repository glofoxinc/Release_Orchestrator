"""Centralized configuration — loads from workspace.yaml with .env credentials."""

from __future__ import annotations

import logging
import os
from typing import Any

import yaml
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_ENV_LOADED = False
_WORKSPACE_RELOAD_FINGERPRINT: str | None = None


def load_env_once(*, env_file: str | None = None) -> None:
    """Load .env at most once per process (avoids triple parse on Streamlit reruns)."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    if env_file and os.path.isfile(env_file):
        load_dotenv(env_file, override=True)
    else:
        load_dotenv(override=True)
    _ENV_LOADED = True


# ── Locate workspace config ──────────────────────────────────────────

_ENGINE_ROOT = os.path.dirname(os.path.abspath(__file__))
_ZONES_ROOT = os.path.dirname(os.path.dirname(_ENGINE_ROOT))
_ORCH_ROOT = os.path.dirname(_ZONES_ROOT)
_REPO_ROOT = os.path.dirname(_ORCH_ROOT)
_CONFIG_DIR = os.path.join(_ZONES_ROOT, "config", "profiles")
_WORKSPACES_DIR = os.path.join(_CONFIG_DIR, "workspaces")
_WS_PATH = os.path.join(_CONFIG_DIR, "workspace.yaml")
_TEMPLATES_DIR = os.path.join(_ZONES_ROOT, "config", "assets", "templates")
_ENV_FILE = os.path.join(_ZONES_ROOT, "runtime", "local", ".env")
_APP_DIR = _REPO_ROOT

if not os.environ.get("_JRT_ENV_BOOTSTRAPPED"):
    load_env_once(env_file=_ENV_FILE if os.path.isfile(_ENV_FILE) else None)

# Soft validation warnings collected during workspace load (not fatal).
CONFIG_WARNINGS: list[str] = []

_PLACEHOLDER_CREDENTIAL_VALUES = frozenset({
    "",
    "your-api-token-here",
    "xoxb-your-bot-token",
    "changeme",
    "replace-me",
    "todo",
    "xxx",
    "paste-token-here",
    "sk-...",
})


def list_workspaces() -> list[str]:
    """Return names of available workspace directories."""
    if not os.path.isdir(_WORKSPACES_DIR):
        return []
    return sorted(
        d for d in os.listdir(_WORKSPACES_DIR)
        if os.path.isfile(os.path.join(_WORKSPACES_DIR, d, "workspace.yaml"))
    )


_TEAMS_LIST_CACHE: tuple[list[dict[str, str]], float] | None = None


def _workspaces_dir_mtime() -> float:
    """Latest mtime across root + sub-workspace YAML files (cache invalidation key)."""
    mtimes: list[float] = []
    if os.path.isfile(_WS_PATH):
        mtimes.append(os.path.getmtime(_WS_PATH))
    if os.path.isdir(_WORKSPACES_DIR):
        for d in list_workspaces():
            ws_file = os.path.join(_WORKSPACES_DIR, d, "workspace.yaml")
            if os.path.isfile(ws_file):
                mtimes.append(os.path.getmtime(ws_file))
    return max(mtimes) if mtimes else 0.0


def invalidate_teams_list_cache() -> None:
    global _TEAMS_LIST_CACHE
    _TEAMS_LIST_CACHE = None


def _load_all_teams_uncached() -> list[dict[str, str]]:
    """Return all teams: root workspace + each workspace/ subfolder."""
    teams: list[dict[str, str]] = []

    if os.path.isfile(_WS_PATH):
        with open(_WS_PATH, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        ws = raw.get("workspace", raw)
        projs = " + ".join(p.get("key", "?") for p in ws.get("projects", []))
        teams.append({"id": "", "name": ws.get("name", "Default"), "projects": projs})

    for d in list_workspaces():
        ws_file = os.path.join(_WORKSPACES_DIR, d, "workspace.yaml")
        try:
            with open(ws_file, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            ws = raw.get("workspace", raw)
            projs = " + ".join(p.get("key", "?") for p in ws.get("projects", []))
            teams.append({"id": d, "name": ws.get("name", d), "projects": projs})
        except Exception:
            logger.debug("Failed to load workspace config for '%s'", d, exc_info=True)
            teams.append({"id": d, "name": d, "projects": ""})

    return teams


def list_all_teams() -> list[dict[str, str]]:
    """Return all teams: root workspace + each workspace/ subfolder.

    Each entry: {"id": folder_name_or_empty, "name": display_name, "projects": "KEY1 + KEY2"}
    """
    global _TEAMS_LIST_CACHE
    mtime = _workspaces_dir_mtime()
    if _TEAMS_LIST_CACHE is not None and _TEAMS_LIST_CACHE[1] == mtime:
        return _TEAMS_LIST_CACHE[0]
    teams = _load_all_teams_uncached()
    _TEAMS_LIST_CACHE = (teams, mtime)
    return teams


def create_workspace(folder_name: str, display_name: str) -> str:
    """Create a new workspace directory with a minimal workspace.yaml. Returns the path."""
    ws_dir = os.path.join(_WORKSPACES_DIR, folder_name)
    os.makedirs(ws_dir, exist_ok=True)
    ws_path = os.path.join(ws_dir, "workspace.yaml")
    if not os.path.exists(ws_path):
        minimal = {
            "workspace": {
                "name": display_name,
                "jira": {"base_url": "https://yourorg.atlassian.net"},
                "projects": [],
                "service_desk": {"enabled": False},
                "deployment": {"environment": "Production"},
                "release_notes": {"enabled": False},
                "apps": {
                    "ticket_review": {"enabled": True, "label": "Ticket Review"},
                    "release_notes": {"enabled": True, "label": "Release Notes"},
                    "service_ticket": {"enabled": False, "label": "Service Ticket"},
                    "release_deployer": {"enabled": True, "label": "Release Deployer"},
                },
            }
        }
        with open(ws_path, "w", encoding="utf-8") as f:
            yaml.dump(minimal, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    invalidate_teams_list_cache()
    return ws_path


def get_active_workspace_path() -> str:
    """Return the path to the currently active workspace.yaml."""
    active = os.environ.get("JIRA_TOOLKIT_WORKSPACE", "")
    if active:
        candidate = os.path.join(_WORKSPACES_DIR, active, "workspace.yaml")
        if os.path.isfile(candidate):
            return candidate
    return _WS_PATH


def switch_workspace(name: str) -> None:
    """Set the active workspace by name. Empty string = root workspace."""
    if name:
        os.environ["JIRA_TOOLKIT_WORKSPACE"] = name
    else:
        os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
    ensure_workspace_loaded(force=True)


def active_workspace_name() -> str:
    """Return the name of the active workspace directory, or '' for root."""
    return os.environ.get("JIRA_TOOLKIT_WORKSPACE", "")


def is_placeholder_credential(value: str | None) -> bool:
    """Return True when a credential looks unset or is an example placeholder."""
    if value is None:
        return True
    cleaned = str(value).strip()
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if lowered in _PLACEHOLDER_CREDENTIAL_VALUES:
        return True
    if lowered.startswith("your-") or lowered.endswith("-here"):
        return True
    if lowered in {"xoxb-...", "xoxb-xxx", "xoxb-test"}:
        return True
    return False


def validate_slack_announce_schema(section: Any) -> list[str]:
    """Return human-readable Slack announce schema problems (empty = OK)."""
    warnings: list[str] = []
    if section is None:
        return warnings
    if not isinstance(section, dict):
        return ["slack_announce must be a mapping"]

    cc_map = section.get("cc") or {}
    if cc_map and not isinstance(cc_map, dict):
        warnings.append("slack_announce.cc must be a mapping of person keys")
        cc_map = {}

    channels = section.get("channels")
    if channels is None:
        return warnings
    if not isinstance(channels, list):
        warnings.append("slack_announce.channels must be a list")
        return warnings

    for idx, raw in enumerate(channels):
        if not isinstance(raw, dict):
            warnings.append(f"slack_announce.channels[{idx}] must be a mapping")
            continue
        key = str(raw.get("key") or raw.get("name") or "").strip()
        if not key:
            warnings.append(f"slack_announce.channels[{idx}] needs key or name")
        if "cc" in raw:
            cc_list = raw.get("cc") or []
            if not isinstance(cc_list, list):
                warnings.append(f"slack_announce.channels[{idx}].cc must be a list")
                continue
            for ck in cc_list:
                if isinstance(ck, str) and ck not in cc_map and ck not in {
                    "sushma", "sai_anirudh", "zeke", "eoin", "soumyakant", "trent",
                }:
                    warnings.append(
                        f"slack_announce.channels[{idx}] references unknown cc key '{ck}'"
                    )

    channel_ids = section.get("channel_ids")
    if channel_ids is not None and not isinstance(channel_ids, dict):
        warnings.append("slack_announce.channel_ids must be a mapping")

    return warnings


def placeholder_credential_issues() -> list[str]:
    """Describe placeholder / missing credentials that block real integrations."""
    issues: list[str] = []
    if is_placeholder_credential(os.getenv("JIRA_API_TOKEN", "")):
        issues.append("JIRA_API_TOKEN is missing or still a placeholder value")
    slack_enabled = True
    try:
        slack_enabled = bool(SLACK_ANNOUNCE.get("enabled", True))
    except Exception:  # noqa: BLE001 — module may still be loading
        slack_enabled = True
    if slack_enabled:
        token = (
            os.getenv("SLACK_BOT_TOKEN", "").strip()
            or os.getenv("SLACK_TOKEN", "").strip()
        )
        if is_placeholder_credential(token):
            issues.append(
                "SLACK_BOT_TOKEN is missing or still a placeholder "
                "(required when slack_announce.enabled is true)"
            )
    return issues


def _validate_config(config: dict) -> dict:
    """Validate workspace config structure and provide safe defaults."""
    global CONFIG_WARNINGS
    if not isinstance(config, dict):
        raise ValueError("Workspace config must be a YAML mapping")
    config.setdefault("name", "My Team")
    config.setdefault("jira", {})
    config.setdefault("projects", [])
    config.setdefault("service_desk", {})
    config.setdefault("deployment", {})
    config.setdefault("release_notes", {})
    config.setdefault("apps", {})
    config.setdefault("slack_announce", {})
    if not isinstance(config["jira"], dict):
        raise ValueError("'jira' must be a mapping")
    if not isinstance(config["projects"], list):
        raise ValueError("'projects' must be a list")
    if not isinstance(config["apps"], dict):
        raise ValueError("'apps' must be a mapping")
    if not isinstance(config.get("service_desk", {}), dict):
        raise ValueError("'service_desk' must be a mapping")

    warnings = validate_slack_announce_schema(config.get("slack_announce"))
    CONFIG_WARNINGS = list(warnings)
    for msg in warnings:
        logger.warning("Workspace config: %s", msg)
    return config


def _load_workspace() -> dict[str, Any]:
    ws_path = get_active_workspace_path()
    if os.path.exists(ws_path):
        with open(ws_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        ws = raw.get("workspace", raw)
        return _validate_config(ws)
    return _validate_config({})


def save_workspace(ws: dict[str, Any]) -> None:
    """Persist workspace dict back to the active workspace.yaml."""
    ws_path = get_active_workspace_path()
    os.makedirs(os.path.dirname(ws_path), exist_ok=True)
    with open(ws_path, "w", encoding="utf-8") as f:
        yaml.dump({"workspace": ws}, f, default_flow_style=False, sort_keys=False, allow_unicode=True)


_ws: dict[str, Any] = _load_workspace()

WORKSPACE_NAME: str = _ws.get("name", "My Team")

# ── Jira connection (credentials from .env, URL from workspace) ──────

_jira = _ws.get("jira", {})
JIRA_BASE_URL: str = os.getenv("JIRA_BASE_URL", _jira.get("base_url", "https://example.atlassian.net"))
JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
JIRA_API_URL: str = f"{JIRA_BASE_URL}/rest/api/3"
JIRA_SD_API_URL: str = f"{JIRA_BASE_URL}/rest/servicedeskapi"
JIRA_ISSUE_TEAM_FIELD: str = str(_jira.get("issue_team_field") or "customfield_10700")
JIRA_ISSUE_TEAM_JQL: str = str(_jira.get("issue_team_jql") or "cf[10700]")
KNOWN_JIRA_TEAMS: list[dict[str, Any]] = list(_jira.get("known_teams") or [])

# ── Projects ─────────────────────────────────────────────────────────

PROJECTS: list[dict[str, Any]] = _ws.get("projects", [])

# ── Service desk ─────────────────────────────────────────────────────

_sd = _ws.get("service_desk", {})
SERVICE_DESK: dict[str, Any] = dict(_sd) if isinstance(_sd, dict) else {}
SERVICE_DESK_ENABLED: bool = _sd.get("enabled", False)
SERVICE_DESK_CREATE_MODE: str = str(_sd.get("create_mode", "full_form") or "full_form").strip()

# Generic aliases (active config); TCKT_* names kept for backward compatibility.
SERVICE_DESK_PROJECT_KEY: str = _sd.get("project_key", "TCKT")
SERVICE_DESK_ISSUE_TYPE_ID: str = str(_sd.get("issue_type_id", ""))
TCKT_PROJECT_KEY: str = SERVICE_DESK_PROJECT_KEY
TCKT_ISSUE_TYPE_ID: str = SERVICE_DESK_ISSUE_TYPE_ID

# Logical field aliases: legacy UI keys → canonical SHIPIT keys.
SERVICE_DESK_FIELD_ALIASES: dict[str, str] = {
    "implementation_plan": "implementation_steps",
    "test_plan": "verification_steps",
    "backout_plan": "rollback_steps",
}


def service_desk_field(logical: str) -> str:
    """Resolve a logical service-desk field name to its customfield_* id."""
    canonical = SERVICE_DESK_FIELD_ALIASES.get(logical, logical)
    return TCKT_FIELDS.get(canonical) or TCKT_FIELDS.get(logical, "")


def service_desk_fields() -> dict[str, str]:
    """Return non-empty logical → customfield id map from active config."""
    out: dict[str, str] = {}
    for key, field_id in TCKT_FIELDS.items():
        if field_id:
            out[key] = field_id
    return out


def _resolve_setting(yaml_value: str | int | None, env_key: str) -> str:
    """Prefer explicit env override; fall back to workspace.yaml value."""
    env_val = os.getenv(env_key, "").strip()
    if env_val:
        return env_val
    if yaml_value is None:
        return ""
    return str(yaml_value).strip()


TCKT_SERVICE_DESK_ID: str = _resolve_setting(
    _sd.get("service_desk_id", ""), "TCKT_SERVICE_DESK_ID"
)
TCKT_REQUEST_TYPE_ID: str = _resolve_setting(
    _sd.get("request_type_id", ""), "TCKT_REQUEST_TYPE_ID"
)
TCKT_REQUEST_TYPE_NAME: str = str(_sd.get("request_type_name", "") or "").strip()
SERVICE_DESK_SERVICE_DESK_ID: str = TCKT_SERVICE_DESK_ID
SERVICE_DESK_REQUEST_TYPE_ID: str = TCKT_REQUEST_TYPE_ID
SERVICE_DESK_REQUEST_TYPE_NAME: str = TCKT_REQUEST_TYPE_NAME

_sd_fields = _sd.get("fields", {})
TCKT_FIELDS: dict[str, str] = {
    "change_type": _sd_fields.get("change_type", ""),
    "change_risk": _sd_fields.get("change_risk", ""),
    "impact": _sd_fields.get("impact", ""),
    "urgency": _sd_fields.get("urgency", ""),
    "planned_start": _sd_fields.get("planned_start", ""),
    "planned_end": _sd_fields.get("planned_end", ""),
    "implementation_steps": _sd_fields.get("implementation_steps", ""),
    "verification_steps": _sd_fields.get("verification_steps", ""),
    "rollback_steps": _sd_fields.get("rollback_steps", ""),
    "communication_plan": _sd_fields.get("communication_plan", ""),
    "reason_for_change": _sd_fields.get("reason_for_change", ""),
    "business_impact": _sd_fields.get("business_impact", ""),
    "risks_management": _sd_fields.get("risks_management", ""),
    "qa_test_plan": _sd_fields.get("qa_test_plan", ""),
    "implementation_plan": _sd_fields.get("implementation_plan", ""),
    "test_plan": _sd_fields.get("test_plan", ""),
    "backout_plan": _sd_fields.get("backout_plan", ""),
    "approvers": _sd_fields.get("approvers", ""),
    "approver_groups": _sd_fields.get("approver_groups", ""),
    "affected_services": _sd_fields.get("affected_services", ""),
    "team": _sd_fields.get("team", ""),
    "assignment_group": _sd_fields.get("assignment_group", ""),
    "unplanned": _sd_fields.get("unplanned", ""),
    "affects_pf": _sd_fields.get("affects_pf", ""),
    "outage_required": _sd_fields.get("outage_required", ""),
}
SERVICE_DESK_FIELDS: dict[str, str] = TCKT_FIELDS

_sd_defaults = _sd.get("defaults", {})
TCKT_SUMMARY_TEAM: str = str(
    _sd_defaults.get("summary_team_name", "") or _ws.get("name", "My Team")
).strip()

TCKT_DEFAULTS: dict[str, Any] = {
    "change_type": _sd_defaults.get("change_type", {}),
    "change_risk": _sd_defaults.get("change_risk", {}),
    "impact": _sd_defaults.get("impact", {}),
    "urgency": _sd_defaults.get("urgency", {}),
    "priority": _sd_defaults.get("priority", {"name": "Medium"}),
    "unplanned": _sd_defaults.get("unplanned", {}),
    "approvers": _sd_defaults.get("approvers", []),
    "approver_groups": _sd_defaults.get("approver_groups", []),
    "team": _sd_defaults.get("team", ""),
    "team_name": str(_sd_defaults.get("team_name", "") or "").strip(),
    "assignment_group_name": str(_sd_defaults.get("assignment_group_name", "") or "").strip(),
    "affected_services": _sd_defaults.get("affected_services", []),
    "assignment_group": _sd_defaults.get("assignment_group", {}),
    "affects_pf": _sd_defaults.get("affects_pf", []),
    "outage_required": _sd_defaults.get("outage_required", []),
}
SERVICE_DESK_DEFAULTS: dict[str, Any] = TCKT_DEFAULTS

_sd_post = _sd.get("post_create", {})
SHIPIT_POST_CREATE: dict[str, Any] = {
    "enabled": _sd_post.get("enabled", True),
    "transition_to_status": _sd_post.get("transition_to_status", True),
    "transition_status": str(_sd_post.get("transition_status") or "Review Ready"),
    "assign_to_creator": _sd_post.get("assign_to_creator", True),
    "link_release_tickets": _sd_post.get("link_release_tickets", True),
    "link_type": str(_sd_post.get("link_type") or "Discovery - Connected"),
    "skip_if_test_mode": _sd_post.get("skip_if_test_mode", True),
}

# ── Schedule timezones ───────────────────────────────────────────────
# Jira stores an instant and renders it per viewer profile, so the zone the
# window was agreed in has to be explicit rather than inherited from whichever
# machine runs the app.

TCKT_SCHEDULE_TZ: str = str(
    _sd_defaults.get("schedule_timezone", "") or "America/Chicago"
).strip()
TCKT_DISPLAY_TZ: str = str(
    _sd_defaults.get("schedule_display_timezone", "") or "America/Chicago"
).strip()
TCKT_SCHEDULE_SOURCE_TZ: str = str(
    _sd_defaults.get("schedule_source_timezone", "") or "Asia/Kolkata"
).strip()

# ── Deployment ───────────────────────────────────────────────────────

_dep = _ws.get("deployment", {})
DEPLOY_ENVIRONMENT: str = _dep.get("environment", "Production")

# ── Slack announce (post-TCKT, pre-deployer) ─────────────────────────

_slack_announce = _ws.get("slack_announce", {})
SLACK_ANNOUNCE: dict[str, Any] = dict(_slack_announce) if isinstance(_slack_announce, dict) else {}

_ba = _ws.get("browser_automation", {})
BROWSER_AUTOMATION: dict[str, Any] = dict(_ba) if isinstance(_ba, dict) else {}

# ── SharePoint upload + Teams schedule (Graph backends; UI later) ────

_sharepoint_upload = _ws.get("sharepoint_upload", {})
SHAREPOINT_UPLOAD: dict[str, Any] = (
    dict(_sharepoint_upload) if isinstance(_sharepoint_upload, dict) else {}
)

_teams_schedule = _ws.get("teams_schedule", {})
TEAMS_SCHEDULE: dict[str, Any] = (
    dict(_teams_schedule) if isinstance(_teams_schedule, dict) else {}
)

_release_notify = _ws.get("release_notify", {})
RELEASE_NOTIFY: dict[str, Any] = (
    dict(_release_notify) if isinstance(_release_notify, dict) else {}
)

_release_gates = _ws.get("release_gates", {})
RELEASE_GATES: dict[str, Any] = (
    dict(_release_gates) if isinstance(_release_gates, dict) else {}
)

_github = _ws.get("github", {})
GITHUB: dict[str, Any] = dict(_github) if isinstance(_github, dict) else {}

# ── Ticket Review defaults ───────────────────────────────────────────

_tr = _ws.get("ticket_review", {}) if isinstance(_ws.get("ticket_review"), dict) else {}
TICKET_REVIEW: dict[str, Any] = dict(_tr)
TICKET_REVIEW_DEFAULT_CHECKED_STATUSES: dict[str, list[str]] = (
    dict(_tr.get("default_checked_statuses") or {})
    if isinstance(_tr.get("default_checked_statuses"), dict)
    else {}
)


def ticket_review_default_checked_statuses(project_key: str) -> list[str]:
    """Status names auto-selected on Step 2 when using status mode."""
    pk = (project_key or "").strip().upper()
    configured = TICKET_REVIEW_DEFAULT_CHECKED_STATUSES.get(pk) or []
    if configured:
        return [str(s).strip() for s in configured if str(s).strip()]
    if pk == "PIC":
        return ["Review", "In Review", "Ready for Review", "In Progress"]
    if pk == "AN":
        return ["Review", "In Review", "Ready for Review", "In Progress"]
    return []


RELEASE_NOTES_DEFAULT_STATUSES: dict[str, list[str]] = (
    dict(_rn.get("default_statuses") or {})
    if isinstance((_rn := _ws.get("release_notes", {})).get("default_statuses"), dict)
    else {}
)


def release_notes_default_statuses(project_key: str) -> list[str]:
    """Statuses for Release Notes / SHIPIT ticket inventory (release-ready only)."""
    pk = (project_key or "").strip().upper()
    configured = RELEASE_NOTES_DEFAULT_STATUSES.get(pk) or []
    if configured:
        return [str(s).strip() for s in configured if str(s).strip()]
    if pk == "PIC":
        return ["Ready for Release"]
    if pk == "AN":
        return ["QA(migrated)"]
    return []

# ── Release notes ────────────────────────────────────────────────────

_rn = _ws.get("release_notes", {})
RELEASE_NOTES_ENABLED: bool = _rn.get("enabled", False)
_rn_pool_raw = _rn.get("test_by_pool") or []
RELEASE_NOTES_TEST_BY_POOL: tuple[str, ...] = tuple(
    str(name).strip() for name in _rn_pool_raw if str(name).strip()
)
RELEASE_META: dict[str, str] = {
    "dev_team": _rn.get("team_name", WORKSPACE_NAME),
    "release_owner": _rn.get("release_owner", ""),
    "senior_mgr": _rn.get("senior_mgr", ""),
    "director": _rn.get("director", ""),
    "svp": _rn.get("svp", ""),
    "environment": DEPLOY_ENVIRONMENT,
}

_gen_script = _rn.get("generator_script", "")
if _gen_script and not os.path.isabs(_gen_script):
    _gen_script = os.path.join(_APP_DIR, _gen_script)
RELEASE_NOTES_GENERATOR: str = _gen_script or os.path.join(
    _REPO_ROOT, "orchestrator", "generators", "release_notes_generator.py"
)

# ── Apps ─────────────────────────────────────────────────────────────

_apps = _ws.get("apps", {})


def app_enabled(app_id: str) -> bool:
    """Check whether an app is enabled in the workspace config."""
    return _apps.get(app_id, {}).get("enabled", True)


def app_label(app_id: str, default: str = "") -> str:
    """Return the display label for an app."""
    return _apps.get(app_id, {}).get("label", default)


def _integration_archived(section: dict[str, Any] | None) -> bool:
    """True when a workspace integration block is explicitly archived."""
    if not isinstance(section, dict):
        return False
    return bool(section.get("archived"))


def slack_archived() -> bool:
    """True when Slack announce is archived (feature-flagged off)."""
    return _integration_archived(SLACK_ANNOUNCE)


def teams_archived() -> bool:
    """True when Teams meeting scheduling is archived."""
    return _integration_archived(TEAMS_SCHEDULE)


def sharepoint_upload_archived() -> bool:
    """True when SharePoint Graph auto-upload is archived."""
    return _integration_archived(SHAREPOINT_UPLOAD)


def archived_integration_restore_path(integration_id: str) -> str:
    """Relative path to the archive YAML for a named integration."""
    mapping = {
        "slack_announce": "archive/slack_announce.yaml",
        "teams_schedule": "archive/teams_schedule.yaml",
        "sharepoint_upload": "archive/sharepoint_upload.yaml",
    }
    return mapping.get(integration_id, "")


# ── Helpers for project labels ───────────────────────────────────────

def project_keys() -> list[str]:
    return [p["key"] for p in PROJECTS]


def service_desk_request_type_configured() -> bool:
    """True when Service Desk request-type auto-set has both required IDs."""
    return bool(TCKT_SERVICE_DESK_ID and TCKT_REQUEST_TYPE_ID)


def resolve_tckt_select(field: str, label: str) -> dict:
    """Map a UI label (Normal, Medium, etc.) to a Jira select-field value."""
    import jira_client

    sd_defaults = _ws.get("service_desk", {}).get("defaults", {})
    option_map = sd_defaults.get(f"{field}_options", {})
    if isinstance(option_map, dict) and label in option_map:
        val = option_map[label]
        return val if isinstance(val, dict) else {"id": str(val)}

    default = TCKT_DEFAULTS.get(field, {})
    if field == "change_type" and label == "Normal":
        return default
    if field == "change_risk" and label == "Medium":
        return default

    field_id = service_desk_field(field)
    if field_id and TCKT_ISSUE_TYPE_ID:
        try:
            resolved = jira_client.resolve_custom_field_option(
                TCKT_PROJECT_KEY,
                TCKT_ISSUE_TYPE_ID,
                field_id,
                label,
            )
        except Exception:
            resolved = None
        if resolved:
            return resolved
    return default


def project_label() -> str:
    """Human-readable label like 'PIC + AN'."""
    return " + ".join(p["key"] for p in PROJECTS)


def _workspace_reload_fingerprint() -> str:
    path = get_active_workspace_path()
    try:
        mtime = os.path.getmtime(path) if os.path.isfile(path) else 0
    except OSError:
        mtime = 0
    return f"{active_workspace_name()}:{mtime}:{path}"


def ensure_workspace_loaded(*, force: bool = False) -> None:
    """Reload workspace.yaml only when workspace, path, or file mtime changed."""
    global _WORKSPACE_RELOAD_FINGERPRINT
    fp = _workspace_reload_fingerprint()
    if force or fp != _WORKSPACE_RELOAD_FINGERPRINT:
        reload_workspace()
        _WORKSPACE_RELOAD_FINGERPRINT = fp


def reload_workspace() -> None:
    """Re-read workspace.yaml and refresh all module-level variables."""
    global _ws, WORKSPACE_NAME, JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN
    global JIRA_API_URL, JIRA_SD_API_URL, JIRA_ISSUE_TEAM_FIELD, JIRA_ISSUE_TEAM_JQL, KNOWN_JIRA_TEAMS
    global PROJECTS, SERVICE_DESK, SERVICE_DESK_ENABLED
    global SERVICE_DESK_SERVICE_DESK_ID, SERVICE_DESK_REQUEST_TYPE_ID, SERVICE_DESK_REQUEST_TYPE_NAME
    global SERVICE_DESK_FIELDS, SERVICE_DESK_DEFAULTS
    global TCKT_PROJECT_KEY, TCKT_ISSUE_TYPE_ID, TCKT_SERVICE_DESK_ID
    global TCKT_REQUEST_TYPE_ID, TCKT_REQUEST_TYPE_NAME, TCKT_FIELDS, TCKT_DEFAULTS
    global DEPLOY_ENVIRONMENT, RELEASE_NOTES_ENABLED, RELEASE_META
    global RELEASE_NOTES_TEST_BY_POOL, RELEASE_NOTES_GENERATOR, _apps
    global SLACK_ANNOUNCE, SHAREPOINT_UPLOAD, TEAMS_SCHEDULE, RELEASE_GATES, GITHUB, RELEASE_NOTIFY
    global TICKET_REVIEW_DEFAULT_CHECKED_STATUSES, RELEASE_NOTES_DEFAULT_STATUSES
    global TCKT_SCHEDULE_TZ, TCKT_DISPLAY_TZ, TCKT_SCHEDULE_SOURCE_TZ, TCKT_SUMMARY_TEAM
    global SHIPIT_POST_CREATE, BROWSER_AUTOMATION, CONFIG_WARNINGS

    CONFIG_WARNINGS = []
    _ws = _load_workspace()


    WORKSPACE_NAME = _ws.get("name", "My Team")

    _jira_r = _ws.get("jira", {})
    JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", _jira_r.get("base_url", "https://example.atlassian.net"))
    JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
    JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
    JIRA_API_URL = f"{JIRA_BASE_URL}/rest/api/3"
    JIRA_SD_API_URL = f"{JIRA_BASE_URL}/rest/servicedeskapi"
    JIRA_ISSUE_TEAM_FIELD = str(_jira_r.get("issue_team_field") or "customfield_10700")
    JIRA_ISSUE_TEAM_JQL = str(_jira_r.get("issue_team_jql") or "cf[10700]")
    KNOWN_JIRA_TEAMS = list(_jira_r.get("known_teams") or [])

    PROJECTS = _ws.get("projects", [])

    _sd_r = _ws.get("service_desk", {})
    SERVICE_DESK = dict(_sd_r) if isinstance(_sd_r, dict) else {}
    SERVICE_DESK_ENABLED = _sd_r.get("enabled", False)
    SERVICE_DESK_CREATE_MODE = str(_sd_r.get("create_mode", "full_form") or "full_form").strip()
    SERVICE_DESK_PROJECT_KEY = _sd_r.get("project_key", "TCKT")
    SERVICE_DESK_ISSUE_TYPE_ID = str(_sd_r.get("issue_type_id", ""))
    TCKT_PROJECT_KEY = SERVICE_DESK_PROJECT_KEY
    TCKT_ISSUE_TYPE_ID = SERVICE_DESK_ISSUE_TYPE_ID
    TCKT_SERVICE_DESK_ID = _resolve_setting(
        _sd_r.get("service_desk_id", ""), "TCKT_SERVICE_DESK_ID"
    )
    TCKT_REQUEST_TYPE_ID = _resolve_setting(
        _sd_r.get("request_type_id", ""), "TCKT_REQUEST_TYPE_ID"
    )
    TCKT_REQUEST_TYPE_NAME = str(_sd_r.get("request_type_name", "") or "").strip()
    SERVICE_DESK_SERVICE_DESK_ID = TCKT_SERVICE_DESK_ID
    SERVICE_DESK_REQUEST_TYPE_ID = TCKT_REQUEST_TYPE_ID
    SERVICE_DESK_REQUEST_TYPE_NAME = TCKT_REQUEST_TYPE_NAME

    _sd_f_r = _sd_r.get("fields", {})
    for k in TCKT_FIELDS:
        TCKT_FIELDS[k] = _sd_f_r.get(k, "")
    SERVICE_DESK_FIELDS = TCKT_FIELDS

    _sd_d_r = _sd_r.get("defaults", {})
    for k in TCKT_DEFAULTS:
        if k in _sd_d_r:
            TCKT_DEFAULTS[k] = _sd_d_r[k]
    SERVICE_DESK_DEFAULTS = TCKT_DEFAULTS

    TCKT_SCHEDULE_TZ = str(
        _sd_d_r.get("schedule_timezone", "") or "America/Chicago"
    ).strip()
    TCKT_DISPLAY_TZ = str(
        _sd_d_r.get("schedule_display_timezone", "") or "America/Chicago"
    ).strip()
    TCKT_SCHEDULE_SOURCE_TZ = str(
        _sd_d_r.get("schedule_source_timezone", "") or "Asia/Kolkata"
    ).strip()
    TCKT_SUMMARY_TEAM = str(
        _sd_d_r.get("summary_team_name", "") or _ws.get("name", "My Team")
    ).strip()

    _sd_post_r = _sd_r.get("post_create", {})
    SHIPIT_POST_CREATE = {
        "enabled": _sd_post_r.get("enabled", True),
        "transition_to_status": _sd_post_r.get("transition_to_status", True),
        "transition_status": str(_sd_post_r.get("transition_status") or "Review Ready"),
        "assign_to_creator": _sd_post_r.get("assign_to_creator", True),
        "link_release_tickets": _sd_post_r.get("link_release_tickets", True),
        "link_type": str(_sd_post_r.get("link_type") or "Discovery - Connected"),
        "skip_if_test_mode": _sd_post_r.get("skip_if_test_mode", True),
    }

    _dep_r = _ws.get("deployment", {})
    DEPLOY_ENVIRONMENT = _dep_r.get("environment", "Production")

    _slack_r = _ws.get("slack_announce", {})
    SLACK_ANNOUNCE = dict(_slack_r) if isinstance(_slack_r, dict) else {}

    _ba_r = _ws.get("browser_automation", {})
    BROWSER_AUTOMATION = dict(_ba_r) if isinstance(_ba_r, dict) else {}

    _sp_r = _ws.get("sharepoint_upload", {})
    SHAREPOINT_UPLOAD = dict(_sp_r) if isinstance(_sp_r, dict) else {}

    _teams_r = _ws.get("teams_schedule", {})
    TEAMS_SCHEDULE = dict(_teams_r) if isinstance(_teams_r, dict) else {}

    _notify_r = _ws.get("release_notify", {})
    RELEASE_NOTIFY = dict(_notify_r) if isinstance(_notify_r, dict) else {}

    _gates_r = _ws.get("release_gates", {})
    RELEASE_GATES = dict(_gates_r) if isinstance(_gates_r, dict) else {}

    _github_r = _ws.get("github", {})
    GITHUB = dict(_github_r) if isinstance(_github_r, dict) else {}

    _tr_r = _ws.get("ticket_review", {})
    TICKET_REVIEW_DEFAULT_CHECKED_STATUSES = (
        dict(_tr_r.get("default_checked_statuses") or {})
        if isinstance(_tr_r.get("default_checked_statuses"), dict)
        else {}
    )

    _rn_r = _ws.get("release_notes", {})
    RELEASE_NOTES_DEFAULT_STATUSES = (
        dict(_rn_r.get("default_statuses") or {})
        if isinstance(_rn_r.get("default_statuses"), dict)
        else {}
    )
    RELEASE_NOTES_ENABLED = _rn_r.get("enabled", False)
    _pool_r = _rn_r.get("test_by_pool") or []
    RELEASE_NOTES_TEST_BY_POOL = tuple(
        str(name).strip() for name in _pool_r if str(name).strip()
    )
    RELEASE_META.update({
        "dev_team": _rn_r.get("team_name", WORKSPACE_NAME),
        "release_owner": _rn_r.get("release_owner", ""),
        "senior_mgr": _rn_r.get("senior_mgr", ""),
        "director": _rn_r.get("director", ""),
        "svp": _rn_r.get("svp", ""),
        "environment": DEPLOY_ENVIRONMENT,
    })

    _gen_script = _rn_r.get("generator_script", "")
    if _gen_script and not os.path.isabs(_gen_script):
        _gen_script = os.path.join(_APP_DIR, _gen_script)
    RELEASE_NOTES_GENERATOR = _gen_script or os.path.join(
        _REPO_ROOT, "orchestrator", "generators", "release_notes_generator.py"
    )

    _apps = _ws.get("apps", {})
