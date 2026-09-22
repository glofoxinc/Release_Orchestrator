"""Integration verification for Jira Release Tool.

Checks Jira REST API auth, issue search, create metadata (dry-run), Slack bot
auth + read-only channel membership, Service Desk metadata, workspace Slack
schema, placeholder credentials, and SharePoint URL host/link shape.
Never prints tokens. Never posts to Slack or creates Jira issues.

Usage
-----
    python scripts/verify_integrations.py --check=all
    python scripts/verify_integrations.py --check=auth
    python scripts/verify_integrations.py --check=search --project=AN
    python scripts/verify_integrations.py --check=create --dry-run
    python scripts/verify_integrations.py --check=slack
    python scripts/verify_integrations.py --check=service_desk
    python scripts/verify_integrations.py --check=team_scope
    python scripts/verify_integrations.py --check=teams
    python scripts/verify_integrations.py --check=release_gates
    python scripts/test_release_notes_e2e.py
    python scripts/verify_integrations.py --check=release_notes
    python scripts/verify_integrations.py --mock

Exit codes
----------
    0  all required checks passed
    1  one or more required checks failed
    2  bad arguments
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
RESET = "\033[0m"
CYAN = "\033[36m"


def _is_tty() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(color: str, text: str) -> str:
    return f"{color}{text}{RESET}" if _is_tty() else text


def mask(value: str | None, keep: int = 4) -> str:
    if not value:
        return "<unset>"
    if len(value) <= keep:
        return "*" * len(value)
    return value[:keep] + "*" * max(4, len(value) - keep)


def is_mock() -> bool:
    return os.environ.get("MOCK_MODE", "").lower() in {"1", "true", "yes", "on"}


class Result:
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    MOCK = "MOCK"

    def __init__(self, name: str, status: str, message: str, hint: str = "", required: bool = True):
        self.name = name
        self.status = status
        self.message = message
        self.hint = hint
        self.required = required

    def print(self) -> None:
        icons = {
            self.PASS: _c(GREEN, "[PASS]"),
            self.FAIL: _c(RED, "[FAIL]"),
            self.SKIP: _c(YELLOW, "[SKIP]"),
            self.MOCK: _c(CYAN, "[MOCK]"),
        }
        tag = "" if self.required else _c(YELLOW, " (optional)")
        print(f"  {icons[self.status]} {self.name}{tag}: {self.message}")
        if self.hint and self.status == self.FAIL:
            print(f"         -> Next step: {self.hint}")


def _jira_config() -> tuple[str | None, str | None, str | None]:
    base = os.getenv("JIRA_BASE_URL", "").rstrip("/") or None
    email = os.getenv("JIRA_EMAIL") or None
    token = os.getenv("JIRA_API_TOKEN") or None
    return base, email, token


def _auth_session():
    import requests  # noqa: PLC0415
    from requests.auth import HTTPBasicAuth  # noqa: PLC0415

    base, email, token = _jira_config()
    if not (base and email and token):
        return None, None
    s = requests.Session()
    s.auth = HTTPBasicAuth(email, token)
    s.headers.update({"Accept": "application/json"})
    return s, base


def check_auth() -> Result:
    name = "Jira auth (/myself)"
    if is_mock():
        return Result(name, Result.MOCK, "mock mode enabled; pretending auth worked")

    base, email, token = _jira_config()
    if not (base and email and token):
        return Result(
            name,
            Result.FAIL,
            f"missing env (JIRA_BASE_URL={base or '<unset>'}, "
            f"JIRA_EMAIL={email or '<unset>'}, JIRA_API_TOKEN={mask(token)})",
            "Set JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN in .env. Generate token at https://id.atlassian.com/manage-profile/security/api-tokens",
        )

    try:
        import requests  # noqa: PLC0415
    except ImportError:
        return Result(name, Result.FAIL, "requests package missing", "pip install -r requirements.txt")

    s, base = _auth_session()
    try:
        resp = s.get(f"{base}/rest/api/3/myself", timeout=15)
    except requests.RequestException as exc:  # noqa: F821
        return Result(name, Result.FAIL, f"network error: {exc}", f"Confirm {base} is reachable from this host.")

    if resp.status_code == 200:
        data = resp.json()
        return Result(
            name, Result.PASS, f"authenticated as {data.get('displayName', '?')} ({data.get('emailAddress', '?')})"
        )
    if resp.status_code == 401:
        return Result(
            name,
            Result.FAIL,
            "401 Unauthorized",
            "API token is invalid/expired. Regenerate at https://id.atlassian.com/manage-profile/security/api-tokens",
        )
    if resp.status_code == 403:
        return Result(
            name,
            Result.FAIL,
            "403 Forbidden",
            "Account exists but lacks permission. Ask admin to grant Jira Software/Service Desk access.",
        )
    return Result(
        name,
        Result.FAIL,
        f"HTTP {resp.status_code}: {resp.text[:150]}",
        "Unexpected — check JIRA_BASE_URL host.",
    )


def _default_project_key(explicit: str | None = None) -> str:
    """Prefer CLI project, else first workspace project, else PIC."""
    if explicit and str(explicit).strip():
        return str(explicit).strip().upper()
    try:
        import config  # noqa: PLC0415

        projects = list(getattr(config, "PROJECTS", []) or [])
        if projects:
            key = str(projects[0].get("key") or "").strip()
            if key:
                return key.upper()
    except Exception:  # noqa: BLE001 - verifier must stay resilient
        pass
    return "PIC"


def check_search(project: str | None = None) -> Result:
    name = "Jira search"
    if is_mock():
        return Result(name, Result.MOCK, "mock mode enabled; returning 3 fake issues")

    base, email, token = _jira_config()
    if not (base and email and token):
        return Result(
            name,
            Result.SKIP,
            "auth not configured (see auth check)",
            "Configure JIRA_* env vars first.",
            required=False,
        )

    import requests  # noqa: PLC0415

    s, base = _auth_session()

    # Cloud rejects unbounded JQL — always restrict to a project key.
    project_key = _default_project_key(project)
    jql = f"project = {project_key} ORDER BY created DESC"
    try:
        resp = s.post(
            f"{base}/rest/api/3/search/jql",
            json={"jql": jql, "maxResults": 1, "fields": ["summary"]},
            timeout=15,
        )
    except requests.RequestException as exc:
        return Result(name, Result.FAIL, f"network error: {exc}", "Check connectivity.")

    if resp.status_code == 200:
        payload = resp.json()
        count = len(payload.get("issues", []))
        return Result(name, Result.PASS, f"search/jql returned {count} issue(s) for jql={jql!r}")
    if resp.status_code == 400:
        return Result(
            name,
            Result.FAIL,
            f"400 Bad Request: {resp.text[:150]}",
            "JQL rejected — does project key exist and is the user permitted to browse it?",
        )
    if resp.status_code in (401, 403):
        return Result(
            name,
            Result.FAIL,
            f"HTTP {resp.status_code} on search",
            "Account lacks 'Browse projects' for the given project.",
        )
    return Result(name, Result.FAIL, f"HTTP {resp.status_code}: {resp.text[:150]}", "See Jira REST /search/jql docs.")


def check_create(dry_run: bool = True, project: str | None = None) -> Result:
    name = "Jira create-issue (dry-run)" if dry_run else "Jira create-issue"
    if is_mock():
        return Result(name, Result.MOCK, "mock mode enabled; would return fake issue MOCK-1")

    base, email, token = _jira_config()
    if not (base and email and token):
        return Result(name, Result.SKIP, "auth not configured", "Configure JIRA_* env vars first.", required=False)

    import requests  # noqa: PLC0415

    s, base = _auth_session()

    # Dry-run: exercise createmeta instead of actually creating.
    # Always scope to one project — unscoped createmeta is large and often times out.
    if dry_run:
        project_key = _default_project_key(project)
        params: dict[str, Any] = {
            "expand": "projects.issuetypes.fields",
            "projectKeys": project_key,
        }
        try:
            resp = s.get(f"{base}/rest/api/3/issue/createmeta", params=params, timeout=30)
        except requests.RequestException as exc:
            return Result(name, Result.FAIL, f"network error: {exc}", "Check connectivity.")
        if resp.status_code == 200:
            data = resp.json()
            nproj = len(data.get("projects", []))
            return Result(
                name,
                Result.PASS,
                f"createmeta reachable for {project_key}; {nproj} project(s) visible for creation",
            )
        if resp.status_code in (401, 403):
            return Result(
                name,
                Result.FAIL,
                f"HTTP {resp.status_code} on createmeta",
                "Account lacks 'Create issues' permission. Ask admin.",
            )
        return Result(name, Result.FAIL, f"HTTP {resp.status_code}: {resp.text[:150]}", "Unexpected.")

    return Result(
        name,
        Result.SKIP,
        "non-dry-run create not implemented in verifier (safety)",
        "Use the app itself to create real tickets.",
        required=False,
    )


def check_placeholders() -> Result:
    name = "Placeholder credentials"
    import config  # noqa: PLC0415

    issues = config.placeholder_credential_issues()
    if is_mock():
        return Result(name, Result.MOCK, "mock mode — placeholder check skipped", required=False)
    if issues:
        return Result(
            name,
            Result.FAIL,
            "; ".join(issues),
            "Replace example values in .env with real tokens.",
            required=False,
        )
    return Result(name, Result.PASS, "no placeholder credentials detected", required=False)


def check_workspace_slack_schema() -> Result:
    name = "Workspace Slack schema"
    import config  # noqa: PLC0415

    warnings = list(getattr(config, "CONFIG_WARNINGS", []) or [])
    warnings.extend(config.validate_slack_announce_schema(config.SLACK_ANNOUNCE))
    # Deduplicate while preserving order.
    seen: set[str] = set()
    uniq = []
    for w in warnings:
        if w not in seen:
            seen.add(w)
            uniq.append(w)
    if uniq:
        return Result(
            name,
            Result.FAIL,
            "; ".join(uniq),
            "Fix slack_announce channels/cc in workspace.yaml.",
            required=False,
        )
    return Result(name, Result.PASS, "slack_announce schema looks valid", required=False)


def check_service_desk(*, live: bool = False) -> list[Result]:
    """Validate Service Desk metadata from config; optional read-only live check."""
    import config  # noqa: PLC0415

    results: list[Result] = []
    name = "Service Desk metadata"
    if not config.SERVICE_DESK_ENABLED:
        results.append(Result(name, Result.SKIP, "service_desk.enabled is false", required=False))
        return results

    missing: list[str] = []
    if not config.TCKT_ISSUE_TYPE_ID:
        missing.append("issue_type_id")
    if not config.TCKT_SERVICE_DESK_ID:
        missing.append("service_desk_id")
    if not config.TCKT_REQUEST_TYPE_ID:
        missing.append("request_type_id")
    if missing:
        results.append(
            Result(
                name,
                Result.FAIL,
                "missing " + ", ".join(missing),
                "Configure Settings → Service Desk or TCKT_* env vars.",
                required=False,
            )
        )
    else:
        results.append(
            Result(
                name,
                Result.PASS,
                f"{config.TCKT_PROJECT_KEY} issue_type={config.TCKT_ISSUE_TYPE_ID} "
                f"desk={config.TCKT_SERVICE_DESK_ID} request_type={config.TCKT_REQUEST_TYPE_ID} "
                f"create_mode={config.SERVICE_DESK_CREATE_MODE}",
                required=False,
            )
        )

    if not live or is_mock() or missing:
        if is_mock():
            results.append(
                Result(
                    "Service Desk request-type (live)",
                    Result.MOCK,
                    "mock mode — skipped live request-type read",
                    required=False,
                )
            )
        return results

    base, email, token = _jira_config()
    if not (base and email and token):
        results.append(
            Result(
                "Service Desk request-type (live)",
                Result.SKIP,
                "Jira auth not configured",
                required=False,
            )
        )
        return results

    import requests  # noqa: PLC0415

    s, base = _auth_session()
    url = (
        f"{base}/rest/servicedeskapi/servicedesk/{config.TCKT_SERVICE_DESK_ID}"
        f"/requesttype/{config.TCKT_REQUEST_TYPE_ID}"
    )
    try:
        resp = s.get(url, timeout=15, headers={"X-ExperimentalApi": "opt-in"})
    except requests.RequestException as exc:
        results.append(
            Result(
                "Service Desk request-type (live)",
                Result.FAIL,
                f"network error: {exc}",
                required=False,
            )
        )
        return results

    if resp.status_code == 200:
        data = resp.json()
        results.append(
            Result(
                "Service Desk request-type (live)",
                Result.PASS,
                f"request type ok: {data.get('name') or data.get('id')}",
                required=False,
            )
        )
    else:
        results.append(
            Result(
                "Service Desk request-type (live)",
                Result.FAIL,
                f"HTTP {resp.status_code}: {resp.text[:120]}",
                "Confirm TCKT_SERVICE_DESK_ID / TCKT_REQUEST_TYPE_ID.",
                required=False,
            )
        )
    return results


def check_slack(*, live: bool = True) -> list[Result]:
    """Slack bot token + read-only channel resolution/membership."""
    import config  # noqa: PLC0415
    import slack_announce as sa  # noqa: PLC0415

    results: list[Result] = []
    if is_mock():
        results.append(Result("Slack auth", Result.MOCK, "mock mode — Slack skipped", required=False))
        return results

    if config.slack_archived():
        results.append(
            Result(
                "Slack auth",
                Result.SKIP,
                "Archived — restore from archive/slack_announce.yaml and set enabled=true",
                required=False,
            )
        )
        return results

    cfg = sa.load_announce_config({"slack_announce": config.SLACK_ANNOUNCE})
    if not cfg.enabled:
        results.append(
            Result(
                "Slack auth",
                Result.SKIP,
                "slack_announce.enabled is false",
                required=False,
            )
        )
        return results

    if not live:
        if cfg.bot_token:
            results.append(
                Result(
                    "Slack auth",
                    Result.PASS,
                    f"SLACK_BOT_TOKEN present ({mask(cfg.bot_token)})",
                    required=False,
                )
            )
        else:
            results.append(
                Result(
                    "Slack auth",
                    Result.FAIL,
                    "SLACK_BOT_TOKEN missing",
                    "Set SLACK_BOT_TOKEN in .env",
                    required=False,
                )
            )
        return results

    for item in sa.preflight_slack_readonly(cfg):
        status = Result.PASS if item.ok else Result.FAIL
        label = "Slack auth" if item.name == "slack_auth" else f"Slack channel #{item.channel_name or '?'}"
        results.append(
            Result(
                label,
                status,
                item.message,
                "Invite the bot and/or set slack_announce.channel_ids." if not item.ok else "",
                required=False,
            )
        )
    return results


def check_team_scope() -> list[Result]:
    """Verify tenant-safe ticket scope is configured for each workspace project."""
    import config
    import team_scope

    config.reload_workspace()
    results: list[Result] = []
    for proj in config.PROJECTS:
        pk = str(proj.get("key", "")).strip().upper()
        if not pk:
            continue
        name = f"Team scope ({pk})"
        st = team_scope.scope_status(pk)
        if st.get("blocking"):
            return_msg = Result(
                name,
                Result.FAIL,
                "; ".join(st.get("errors") or ["scope not configured"]),
                "Set board_id, filter_id, labels, JQL, or allow_project_wide in workspace.yaml.",
                required=True,
            )
            results.append(return_msg)
        elif st.get("configured"):
            results.append(Result(
                name,
                Result.PASS,
                f"{st.get('scope_type', 'configured')} — fingerprint {st.get('fingerprint', '')[:8]}",
                required=True,
            ))
        else:
            results.append(Result(
                name,
                Result.FAIL,
                "invalid scope: " + "; ".join(st.get("errors") or []),
                "Fix scope block in workspace.yaml.",
                required=True,
            ))
    if not results:
        results.append(Result("Team scope", Result.SKIP, "no projects in workspace.yaml", required=True))
    return results


def check_teams_schedule() -> Result:
    """Report Teams meeting scheduling readiness (no calendar write)."""
    name = "Teams meeting schedule"
    try:
        import config
        import teams_schedule as ts

        config.reload_workspace()
        if config.teams_archived():
            return Result(
                name,
                Result.SKIP,
                "Archived — restore from archive/teams_schedule.yaml and set enabled=true",
                required=False,
            )
        cfg = ts.load_schedule_config(config.TEAMS_SCHEDULE)
        st = ts.status(cfg)
    except Exception as exc:  # noqa: BLE001
        return Result(name, Result.FAIL, str(exc), "Fix workspace.yaml teams_schedule block.", required=False)

    if cfg.can_schedule():
        return Result(name, Result.PASS, f"ready — organizer {cfg.organizer_upn}", required=False)
    if not cfg.organizer_upn:
        return Result(
            name,
            Result.SKIP,
            "organizer_upn not set; UI/MCP dry-run preview still works",
            "Set teams_schedule.organizer_upn in workspace.yaml.",
            required=False,
        )
    missing = (st.get("graph") or {}).get("missing") or []
    if missing:
        return Result(
            name,
            Result.FAIL,
            "missing credentials: " + ", ".join(missing),
            "Set MS_GRAPH_* (Calendar.ReadWrite) and enable teams_schedule.",
            required=False,
        )
    return Result(
        name,
        Result.SKIP,
        "teams_schedule.enabled=false",
        "Enable after Graph credentials are provisioned.",
        required=False,
    )


def check_readiness_summary() -> list[Result]:
    """Print-style summary of all integration readiness rows."""
    import config
    from integration_readiness import summarize_readiness

    config.reload_workspace()
    summary = summarize_readiness()
    results: list[Result] = []
    blocking = summary.get("blocking_pending") or []
    if blocking:
        for row in blocking:
            results.append(Result(
                f"Readiness: {row.get('title', row.get('id', '?'))}",
                Result.FAIL,
                row.get("detail", ""),
                row.get("fix", ""),
                required=True,
            ))
    else:
        results.append(Result(
            "Readiness: blocking",
            Result.PASS,
            "no blocking integration gaps",
            required=True,
        ))
    ops = summary.get("ops_pending") or []
    for row in ops:
        results.append(Result(
            f"Readiness: {row.get('title', row.get('id', '?'))}",
            Result.SKIP,
            row.get("detail", ""),
            row.get("fix", ""),
            required=False,
        ))
    ext = summary.get("external_pending") or []
    for row in ext:
        results.append(Result(
            f"External: {row.get('title', row.get('id', '?'))}",
            Result.SKIP,
            row.get("detail", ""),
            row.get("fix", ""),
            required=False,
        ))
    ready = summary.get("ready_count", 0)
    results.append(Result(
        "Readiness: summary",
        Result.PASS,
        f"{ready} integration(s) ready; see ops/external rows above for credential work",
        required=False,
    ))
    return results


def check_release_notes() -> list[Result]:
    """Smoke-test Release Notes E2E on fixture data (readiness + publish)."""
    name = "Release Notes E2E"
    try:
        from generators.release_notes_e2e import e2e_status

        st = e2e_status()
    except Exception as exc:  # noqa: BLE001
        return [Result(name, Result.FAIL, str(exc), "Fix generator/release_notes_e2e module.", required=False)]

    results: list[Result] = []
    build = st.get("generator_build_id") or "unknown"
    if st.get("ok"):
        results.append(Result(
            name,
            Result.PASS,
            f"fixture E2E OK — build {build}, score {st.get('readiness_score')}/100",
            required=False,
        ))
    else:
        results.append(Result(
            name,
            Result.FAIL,
            f"fixture E2E failed — publish={st.get('publish_status')}, score={st.get('readiness_score')}",
            "Run: python scripts/test_release_notes_e2e.py",
            required=False,
        ))
    if st.get("reference_fixture_available"):
        results.append(Result(
            "Release Notes reference fixture",
            Result.PASS,
            "Reference DOCX present for parity tests",
            required=False,
        ))
    else:
        results.append(Result(
            "Release Notes reference fixture",
            Result.SKIP,
            "Reference DOCX not in tests/fixtures",
            required=False,
        ))
    return results


def check_release_gates() -> list[Result]:
    """Report pre-review / post-QA gate configuration and Slack DM readiness."""
    import config
    import release_gates
    from slack_assignee_notify import gate_slack_status

    config.reload_workspace()
    results: list[Result] = []
    name_root = "Release gates"
    if not release_gates.gates_root_enabled():
        results.append(Result(
            name_root,
            Result.SKIP,
            "release_gates.enabled is false",
            required=False,
        ))
        return results

    pre = release_gates.gate_enabled("pre_review")
    post = release_gates.gate_enabled("post_qa")
    results.append(Result(
        "Pre-review gate",
        Result.PASS if pre else Result.SKIP,
        f"ready statuses: {', '.join(release_gates.pre_review_statuses())}" if pre else "disabled",
        required=False,
    ))
    results.append(Result(
        "Post-QA gate",
        Result.PASS if post else Result.SKIP,
        f"passed statuses: {', '.join(release_gates.qa_passed_statuses())}" if post else "disabled",
        required=False,
    ))
    slack = gate_slack_status()
    if slack.get("can_dm_assignees"):
        results.append(Result(
            "Gate assignee Slack DMs",
            Result.PASS,
            "SLACK_BOT_TOKEN configured for assignee DMs",
            required=False,
        ))
    else:
        results.append(Result(
            "Gate assignee Slack DMs",
            Result.SKIP,
            "SLACK_BOT_TOKEN missing — preview works, live DM needs token",
            "Add SLACK_BOT_TOKEN (im:write, users:read.email).",
            required=False,
        ))
    return results


def check_graph_sharepoint() -> Result:
    """Report SharePoint Graph upload readiness (config + credentials, no upload)."""
    name = "SharePoint Graph upload"
    try:
        import config
        import sharepoint_upload as sp_up

        config.reload_workspace()
        if config.sharepoint_upload_archived():
            return Result(
                name,
                Result.SKIP,
                "Archived — manual SharePoint URL remains; restore from archive/sharepoint_upload.yaml",
                required=False,
            )
        cfg = sp_up.load_upload_config(config.SHAREPOINT_UPLOAD)
        st = sp_up.status(cfg)
    except Exception as exc:  # noqa: BLE001
        return Result(name, Result.FAIL, str(exc), "Fix workspace.yaml sharepoint_upload block.")

    if not cfg.enabled:
        if cfg.target_ready():
            return Result(
                name,
                Result.PASS,
                f"target ready ({cfg.folder_path}); enabled=false until MS_GRAPH_* set",
                required=False,
            )
        return Result(
            name,
            Result.SKIP,
            "sharepoint_upload not enabled and target incomplete",
            required=False,
        )

    if st.get("can_upload"):
        return Result(name, Result.PASS, f"ready — folder {cfg.folder_path}", required=False)

    missing = (st.get("graph") or {}).get("missing") or []
    if missing:
        return Result(
            name,
            Result.FAIL,
            "missing credentials: " + ", ".join(missing),
            "Set MS_GRAPH_* in .env and grant Sites.ReadWrite.All (application).",
            required=False,
        )
    return Result(
        name,
        Result.FAIL,
        "enabled but cannot upload — check hostname/site_path/drive_id",
        "Confirm site_path with IT for the Glofox Customize team site.",
        required=False,
    )


def check_sharepoint(url: str | None = None) -> list[Result]:
    results = [check_graph_sharepoint()]
    name = "SharePoint URL shape"
    from sharepoint_url import sharepoint_validation_message, validate_sharepoint_url  # noqa: PLC0415

    sample = (url or os.getenv("SHAREPOINT_SAMPLE_URL") or "").strip()
    if not sample:
        results.append(Result(
            name,
            Result.SKIP,
            "no URL provided (pass --sharepoint-url or SHAREPOINT_SAMPLE_URL)",
            required=False,
        ))
        return results
    if validate_sharepoint_url(sample, require_link_shape=True):
        results.append(Result(name, Result.PASS, "host and link shape look like SharePoint", required=False))
        return results
    if validate_sharepoint_url(sample):
        results.append(Result(
            name,
            Result.FAIL,
            sharepoint_validation_message(sample) or "link shape weak",
            "Use a document link (/sites/, Doc.aspx, :w:, or .docx).",
            required=False,
        ))
        return results
    results.append(Result(
        name,
        Result.FAIL,
        sharepoint_validation_message(sample) or "invalid SharePoint URL",
        "Paste a *.sharepoint.com URL.",
        required=False,
    ))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Jira Release Tool integrations.")
    parser.add_argument(
        "--check",
        default="all",
        help="One of: all, auth, search, create, slack, service_desk, sharepoint, team_scope, teams, readiness, release_gates, release_notes, placeholders, workspace",
    )
    parser.add_argument("--project", default=None, help="Optional project key (e.g. AN, PIC).")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Dry-run create (default, safe).")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="Disable dry-run (not recommended).")
    parser.add_argument("--mock", action="store_true", help="Enable mock mode.")
    parser.add_argument(
        "--sharepoint-url",
        default=None,
        help="Sample SharePoint URL to validate (read-only shape check).",
    )
    parser.add_argument(
        "--no-live",
        action="store_true",
        help="Skip live Slack/Service Desk HTTP calls (config-only).",
    )
    args = parser.parse_args()

    if args.mock:
        os.environ["MOCK_MODE"] = "true"

    live = not args.no_live

    def _flatten(items: Result | list[Result]) -> list[Result]:
        if isinstance(items, list):
            return items
        return [items]

    all_checks: dict[str, Any] = {
        "auth": lambda: check_auth(),
        "search": lambda: check_search(args.project),
        "create": lambda: check_create(args.dry_run, args.project),
        "placeholders": check_placeholders,
        "workspace": check_workspace_slack_schema,
        "team_scope": check_team_scope,
        "service_desk": lambda: check_service_desk(live=live),
        "slack": lambda: check_slack(live=live),
        "sharepoint": lambda: check_sharepoint(args.sharepoint_url),
        "teams": check_teams_schedule,
        "readiness": check_readiness_summary,
        "release_gates": check_release_gates,
        "release_notes": check_release_notes,
    }
    selected = list(all_checks) if args.check == "all" else [args.check]
    unknown = [s for s in selected if s not in all_checks]
    if unknown:
        print(f"Unknown check(s): {unknown}. Valid: all, {', '.join(all_checks)}", file=sys.stderr)
        return 2

    print(_c(CYAN, "=== Jira Release Tool — Integration Verification ==="))
    if is_mock():
        print(_c(YELLOW, "MOCK_MODE enabled — no real credentials will be used.\n"))
    if args.no_live:
        print(_c(YELLOW, "Live Slack/Service Desk HTTP checks disabled (--no-live).\n"))

    results: list[Result] = []
    for key in selected:
        try:
            results.extend(_flatten(all_checks[key]()))
        except Exception as exc:  # noqa: BLE001
            results.append(Result(key, Result.FAIL, f"unexpected error: {exc}", "Open an issue with this traceback."))

    print()
    for r in results:
        r.print()

    failed_required = [r for r in results if r.status == Result.FAIL and r.required]
    print()
    if failed_required:
        print(_c(RED, f"FAILED: {len(failed_required)} required check(s) failed."))
        return 1
    passed = [r for r in results if r.status in (Result.PASS, Result.MOCK)]
    skipped = [r for r in results if r.status == Result.SKIP]
    optional_failed = [r for r in results if r.status == Result.FAIL and not r.required]
    print(_c(GREEN, f"OK: {len(passed)} passed, {len(skipped)} skipped."))
    if optional_failed:
        print(_c(YELLOW, f"Note: {len(optional_failed)} optional check(s) failed (non-blocking)."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
