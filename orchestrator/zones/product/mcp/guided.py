"""Conversational Release Orchestrator — one tool, no step memorization."""

from __future__ import annotations

import re
from typing import Any

import team_crew

from release_mcp import onboarding, onboarding_store, onboarding_team_flow, step_ux, welcome, wizard, wizard_store

# Plain-English labels matching platform UI order
STEP_GUIDE: dict[str, dict[str, str]] = {
    "welcome": {
        "number": "0",
        "title": "Welcome",
        "goal": "Confirm team (Glofox default) and choose a release path.",
    },
    "start_menu": {
        "number": "0",
        "title": "Start menu",
        "goal": "Pick path: fetch review tickets, fetch release list, review call, release notes, or SHIPIT.",
    },
    "onboarding": {
        "number": "setup",
        "title": "Onboarding",
        "goal": "One-time .env and MCP setup before first release.",
    },
    "ticket_review": {
        "number": "1",
        "title": "Ticket Review — fetch & lock",
        "goal": "Fetch review-ready tickets (PIC Review + AN Passed QA), lock the release set.",
    },
    "ticket_list": {
        "number": "—",
        "title": "Release ticket list",
        "goal": "Read-only list of release-ready tickets (fetch release tickets — no lock).",
    },
    "exclusions": {
        "number": "2",
        "title": "Exclusions",
        "goal": "Drop any tickets that should not ship in this release.",
    },
    "release_date_confirm": {
        "number": "2b",
        "title": "Release date confirm",
        "goal": "Confirm deploy date from Jira fixVersions or pick/override before Release Notes & SHIPIT.",
    },
    "release_notes": {
        "number": "3",
        "title": "Release Notes",
        "goal": "Generate Word release notes (.docx), then upload to SharePoint (Playwright).",
    },
    "sharepoint": {
        "number": "4",
        "title": "SharePoint",
        "goal": "Upload Release Notes .docx to SharePoint and save the document link.",
    },
    "service_ticket": {
        "number": "5",
        "title": "Service Ticket (SHIPIT)",
        "goal": "Create SHIPIT change ticket, then post Slack deployment announce.",
    },
    "slack": {
        "number": "6",
        "title": "Slack announce",
        "goal": "Post deployment notice to #insights-customize-squad (SharePoint download + folder links, SHIPIT key).",
    },
    "deploy": {
        "number": "7",
        "title": "Deploy",
        "goal": "Post deployment comments and move tickets to Done.",
    },
    "mark_released": {
        "number": "8",
        "title": "Mark released",
        "goal": "Mark the fix version released in Jira (optional).",
    },
    "complete": {
        "number": "done",
        "title": "Complete",
        "goal": "Release workflow finished.",
    },
}

YES_PHRASES = frozenset(
    {
        "yes",
        "y",
        "ok",
        "okay",
        "sure",
        "go",
        "go ahead",
        "proceed",
        "continue",
        "confirm",
        "lock",
        "lock it",
        "looks good",
        "lgtm",
        "approve",
        "yes lock tickets",
        "yes — start step 1",
        "yes - start step 1",
        "start step 1",
    }
)
NO_PHRASES = frozenset({"no", "n", "cancel", "stop", "abort", "different team", "other team"})
NEXT_PHRASES = frozenset({"next", "next step", "resume", "status"})
WELCOME_PHRASES = frozenset({
    "welcome", "hello", "hi", "hey", "begin",
    "new release", "start release", "release", "deploy",
})
WELCOME_ONBOARD_PHRASES = frozenset({
    "welcome onboard", "welcome onboarding", "onboard me", "first time setup",
})
START_MENU_PHRASES = frozenset({"start", "lets start", "let's start", "go"})
ONBOARDING_PROGRESS_PHRASES = frozenset({
    "done", "next", "next setup step", "setup done", "step done", "continue setup",
    "continue", "next step",
})
TRACK_PICKER_PHRASES = frozenset({
    "both", "release only", "daily review only", "release and daily review",
    "setup both", "everything", "weekly release only", "daily release only", "daily review setup",
})
TEAM_ONBOARD_PHRASES = frozenset({
    "use glofox", "team glofox", "glofox team", "use ignite", "team ignite",
    "team etl", "use etl", "projects pic an", "projects pic", "projects an",
    "crew done", "lock crew", "team setup done", "crew looks good", "team crew done",
})
CREW_STATUS_PHRASES = frozenset({
    "crew status", "team crew status", "show crew", "my crew", "team setup status",
})
FULL_RELEASE_PHRASES = frozenset({
    "week release", "weekly release", "full release", "run release", "run full release",
    "lets go", "let's go", "go release",
})
SLACK_SEND_PHRASES = frozenset({
    "send slack", "post slack", "send deployment", "post to slack",
    "send slack playwright", "slack playwright",
})
RELEASE_NOTES_CONFIRM_PHRASES = frozenset({
    "create release notes",
    "generate release notes",
    "generate docx",
    "yes generate docx",
})
SHIPIT_CONFIRM_PHRASES = frozenset({
    "create shipit",
    "create shipit ticket",
    "yes create shipit",
    "create service ticket",
    "create tckt",
})
SHAREPOINT_UPLOAD_PHRASES = frozenset({
    "upload sharepoint", "sharepoint upload", "upload to sharepoint",
})
SHAREPOINT_DONE_PHRASES = frozenset({
    "sharepoint done", "uploaded sharepoint", "sharepoint uploaded",
})
SLACK_SKIP_PHRASES = frozenset({"skip slack", "skip announcement", "no slack"})
SLACK_DONE_PHRASES = frozenset({"slack done", "posted slack", "slack sent", "slack posted"})
REVIEW_CALL_SCHEDULE_PHRASES = frozenset({
    "schedule review call",
    "review call schedule",
    "schedule review meeting",
    "schedule review",
    "review call",
})
FETCH_RELEASE_LIST_PHRASES = frozenset({
    "fetch release tickets",
    "fetch release tkts",
    "fetch release tkt",
    "list release tickets",
    "list release tkts",
    "list release tkt",
})
ENV_CHECKLIST_PHRASES = frozenset({
    "env checklist", "env params", "show env", "env status", ".env checklist",
})
SETUP_PHRASES = frozenset({
    "onboarding", "onboard", "setup", "setup status", "check setup",
    "am i ready", "ready to start", "first time", "new user", "get started",
    "mcp configured", "mcp is configured", "env is ready", ".env is ready",
})
HELP_PHRASES = frozenset({
    "help", "help me", "what can i say", "phrases", "phrase sheet",
    "cheat sheet", "mcp help", "how does this work",
})
QUICKSTART_PHRASES = frozenset({
    "guide", "quickstart", "quick start", "get started", "start here", "mcp quickstart",
    "read me", "readme", "docs", "documentation",
})
READINESS_PHRASES = frozenset({
    "production ready", "production readiness", "mcp ready", "mcp status",
    "readiness", "100%", "launch ready", "are we ready",
})
DAILY_REVIEW_PHRASES = frozenset({
    "daily review",
    "daily review welcome",
    "daily review setup",
    "daily review onboard",
    "daily review preflight",
    "daily review live",
    "daily review calendar playwright",
    "schedule calendar playwright",
    "calendar done",
    "meeting scheduled",
    "start daily review",
    "setup daily review",
    "outlook login",
    "teams done",
    "outlook done",
})
EMERGENCY_PHRASES = frozenset({"emergency", "emergency deployment", "emergency deploy"})
TEST_SHIPIT_PHRASES = frozenset({
    "test shipit", "demo shipit", "test service ticket", "demo validation",
    "do not deploy", "migration validation",
})
DISPOSE_TEST_PHRASES = frozenset({
    "dispose test shipit", "delete test shipit", "cancel test ticket",
    "close test shipit", "remove demo shipit",
})
SIGNOFF_PHRASES: dict[str, str] = {
    "shipit confirmed": "shipit_dry_run",
    "shipit dry-run done": "shipit_dry_run",
    "slack confirmed": "slack_live_confirm",
    "slack live confirmed": "slack_live_confirm",
}

TEAM_ALIASES: list[tuple[str, str]] = [
    ("glofox", "Glofox Insights Customize"),
    ("ignite", "Ignite Insights Customize"),
    ("etl", "Insights Customize (ETL)"),
]


def _normalize_message(message: str) -> str:
    raw = (message or "").strip().lower()
    return raw.replace("'", "").replace("'", "").replace("`", "")


def _is_fetch_release_list_intent(lowered: str) -> bool:
    if "release notes" in lowered:
        return False
    return any(phrase in lowered for phrase in FETCH_RELEASE_LIST_PHRASES)


def _is_review_call_schedule_intent(lowered: str) -> bool:
    if "daily review" in lowered:
        return False
    return any(phrase in lowered for phrase in REVIEW_CALL_SCHEDULE_PHRASES)


def _resolve_start_path(lowered: str) -> str | None:
    """Map user phrase to start_menu option id."""
    if _is_fetch_release_list_intent(lowered):
        return None
    if any(
        phrase in lowered
        for phrase in (
            "fetch review tickets",
            "fetch review tkts",
            "fetch review tkt",
            "fetch review",
            "review tickets",
            "ticket review",
            "week release",
            "weekly release",
            "full release",
            "run release",
            "run full release",
            "lets go",
            "go release",
            "start step 1",
        )
    ):
        return "fetch_review_tickets"
    if any(
        phrase in lowered
        for phrase in (
            "start with release notes",
            "create release notes",
            "release notes only",
            "notes only",
            "generate docx",
            "generate release notes",
        )
    ):
        return "release_notes"
    if lowered in {"release notes", "release notes."}:
        return "release_notes"
    if any(
        phrase in lowered
        for phrase in (
            "create shipit",
            "shipit ticket",
            "service ticket",
            "create tckt",
            "shipit only",
        )
    ):
        return "shipit"
    if lowered in {"shipit", "tckt"}:
        return "shipit"
    return None


def _extract_team(message: str) -> str | None:
    lowered = _normalize_message(message)
    for alias, full_name in TEAM_ALIASES:
        if alias in lowered:
            return full_name
    match = re.search(r"team\s+(.+)", lowered)
    if match:
        return match.group(1).strip().title()
    return None


def _resolve_confirm_token(workflow_id: str) -> str | None:
    try:
        session = wizard_store.load_session(workflow_id)
    except wizard_store.WizardStoreError:
        return None
    step = str(session.get("step") or "")
    stored = (session.get("confirmations") or {}).get(step) or {}
    token = str(stored.get("token") or "").strip()
    return token or None


def _session_step(workflow_id: str | None) -> str | None:
    if not workflow_id:
        return None
    try:
        session = wizard_store.load_session(workflow_id)
    except wizard_store.WizardStoreError:
        return None
    step = str(session.get("step") or "").strip()
    return step or None


def _is_release_notes_include_intent(lowered: str, step: str | None) -> bool:
    if "include" not in lowered:
        return False
    if step == wizard.STEP_RELEASE_NOTES:
        return True
    if "release note" in lowered:
        return True
    return False


def _assignee_exclude_inputs(raw: str, lowered: str) -> dict[str, Any] | None:
    """Map 'exclude assignee Erasmo' (no ticket key) to exclude_assignee_names."""
    if "exclude" not in lowered:
        return None
    if re.search(r"\b(?:PIC|AN|TCKT|PIIN)-\d+\b", raw, re.IGNORECASE):
        return None
    match = re.search(
        r"exclude\s+(?:assignee\s+|assignees\s+)?(.+?)(?:\s+tickets?)?\.?$",
        raw.strip(),
        re.IGNORECASE,
    )
    if not match:
        return None
    name = match.group(1).strip().strip('"').strip("'")
    if not name:
        return None
    return {"exclude_assignee_names": [name]}


def _format_assignee_check(preview: dict[str, Any]) -> str:
    check = preview.get("assignee_check") or {}
    groups = check.get("by_assignee") or []
    if not groups:
        return ""
    lines = ["**By assignee (check before locking):**"]
    for group in groups:
        assignee = str(group.get("assignee") or "Unassigned")
        keys = ", ".join(group.get("ticket_keys") or [])
        flag = "" if group.get("in_squad") else " — **outside Customize BI squad**"
        lines.append(f"- **{assignee}**{flag}: {keys}")
    skipped = preview.get("skipped_outside_squad") or {}
    if skipped.get("ticket_keys"):
        lines.append("")
        lines.append(
            "**Auto-skipped (outside squad / TEAM_CREW_EXCLUDE — Gabriel, Erasmo, etc.):** "
            + ", ".join(skipped.get("ticket_keys") or [])
        )
    supplement = preview.get("supplement_squad_assignee") or {}
    if supplement.get("ticket_keys"):
        lines.append("")
        lines.append(
            "**Included (in-squad, Team field edge case):** "
            + ", ".join(supplement.get("ticket_keys") or [])
        )
    outside = check.get("outside_squad") or []
    if outside and not skipped.get("ticket_keys"):
        names = ", ".join(str(row.get("assignee") or "") for row in outside)
        lines.append("")
        lines.append(
            f"To drop non-squad assignees, say **exclude assignee <name>** "
            f"(e.g. exclude assignee {outside[0].get('assignee', 'Name').split()[0]})."
        )
        lines.append(f"Currently flagged: {names}.")
    excluded = preview.get("assignee_excluded") or {}
    if excluded.get("ticket_keys"):
        lines.append("")
        lines.append(
            "**Excluded by assignee:** "
            + ", ".join(excluded.get("ticket_keys") or [])
            + f" (patterns: {', '.join(excluded.get('patterns') or [])})"
        )
    return "\n".join(lines)


def _ticket_key_update_inputs(
    raw: str,
    lowered: str,
    *,
    workflow_id: str | None,
) -> dict[str, Any] | None:
    """Map ticket-key phrases to workflow update inputs when a session is active."""
    if not workflow_id:
        return None
    ticket_keys = re.findall(r"\b(?:PIC|AN|TCKT|PIIN)-\d+\b", raw, re.IGNORECASE)
    if not ticket_keys:
        return None
    keys = [k.upper() for k in ticket_keys]
    if "exclude" in lowered or "without" in lowered or "drop" in lowered:
        return {"exclusion_ticket_keys": keys}
    step = _session_step(workflow_id)
    if _is_release_notes_include_intent(lowered, step):
        return {"release_notes_include_ticket_keys": keys}
    return {"selected_ticket_keys": keys}


def interpret_message(
    message: str,
    *,
    workflow_id: str | None = None,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    """Map natural language to release_wizard action + payload."""
    raw = (message or "welcome").strip()
    lowered = _normalize_message(raw)
    team = _extract_team(raw)

    if lowered in NO_PHRASES or "different team" in lowered:
        return {
            "action": "welcome",
            "inputs": {"team_name": team or ""},
            "intent": "change_team",
        }

    if lowered in QUICKSTART_PHRASES:
        return {"action": "quickstart", "inputs": {}, "intent": "quickstart"}

    if lowered in {"help", "?", "what next", "what's next", "whats next"}:
        return {"action": "help", "inputs": {}, "intent": "help"}

    if any(p in lowered for p in CREW_STATUS_PHRASES):
        return {"action": "team_crew_status", "inputs": {}, "intent": "team_crew_status"}

    if (
        "calendar playwright" in lowered
        or _is_review_call_schedule_intent(lowered)
        or lowered in {"calendar done", "meeting scheduled"}
    ):
        return {
            "action": "daily_review_calendar_handoff",
            "inputs": {"dry_run": "calendar done" not in lowered and "meeting scheduled" not in lowered},
            "intent": "daily_review_calendar_playwright",
        }

    if _is_fetch_release_list_intent(lowered):
        inputs: dict[str, Any] = {}
        if team:
            inputs["team_name"] = team
        return {"action": "list_release_tickets", "inputs": inputs, "intent": "list_release_tickets"}

    if any(p in lowered for p in DAILY_REVIEW_PHRASES) or lowered.startswith("daily review"):
        return {
            "action": "daily_review",
            "message": raw,
            "workflow_id": workflow_id,
            "intent": "daily_review",
        }

    if any(p in lowered for p in READINESS_PHRASES):
        return {"action": "readiness", "inputs": {}, "intent": "readiness"}

    for phrase, signoff_id in SIGNOFF_PHRASES.items():
        if phrase in lowered:
            return {
                "action": "signoff",
                "inputs": {"signoff_id": signoff_id, "detail": raw.strip()},
                "intent": "operator_signoff",
            }

    if workflow_id and any(p in lowered for p in EMERGENCY_PHRASES):
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": {"deployment_profile": "emergency"},
            "intent": "emergency_profile",
        }

    shipit_key_match = re.search(r"\bSHIPIT-\d+\b", raw, re.IGNORECASE)
    if any(p in lowered for p in DISPOSE_TEST_PHRASES) and shipit_key_match:
        return {
            "action": "dispose_test_shipit",
            "inputs": {"issue_key": shipit_key_match.group(0).upper()},
            "intent": "dispose_test_shipit",
        }

    if workflow_id and any(p in lowered for p in TEST_SHIPIT_PHRASES):
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": {"test_mode": True},
            "intent": "test_shipit_mode",
        }

    from release_mcp import unified_onboarding as uo

    if any(p in lowered for p in WELCOME_ONBOARD_PHRASES):
        return {
            "action": "beginner_wizard",
            "inputs": {"message": raw, "team_name": team},
            "intent": "welcome_onboard",
        }

    track = uo.resolve_track_phrase(lowered)
    if track and not workflow_id:
        uo.set_track(track)
        if onboarding_store.load_state().get("wizard_mode") == "beginner" or not uo.setup_complete(track=track):
            return {
                "action": "beginner_wizard",
                "inputs": {"message": raw},
                "intent": "onboarding_track",
            }
        return {
            "action": "welcome",
            "inputs": {"onboarding_track": track, "team_inputs": onboarding_store.load_state()},
            "intent": "onboarding_track",
        }

    start_path = _resolve_start_path(lowered)
    if not workflow_id and start_path:
        inputs: dict[str, Any] = {"start_path": start_path}
        if start_path == "fetch_review_tickets" and (
            any(p in lowered for p in FULL_RELEASE_PHRASES) or lowered in YES_PHRASES
        ):
            inputs["confirm_defaults"] = "yes"
        if team:
            inputs["team_name"] = team
        intent = (
            "full_release"
            if start_path == "fetch_review_tickets"
            and (any(p in lowered for p in FULL_RELEASE_PHRASES) or lowered in YES_PHRASES)
            else "start_path"
        )
        return {"action": "welcome", "inputs": inputs, "intent": intent}

    if not workflow_id and lowered in START_MENU_PHRASES:
        inputs = {"show_start_menu": True}
        if team:
            inputs["team_name"] = team
        return {"action": "welcome", "inputs": inputs, "intent": "start_menu"}

    team_hint = (
        not workflow_id
        and (
            any(p in lowered for p in TEAM_ONBOARD_PHRASES)
            or "crew exclude" in lowered
            or "crew add" in lowered
            or team_crew.resolve_team_key_from_phrase(lowered) is not None
        )
    )
    if team_hint:
        state = onboarding_store.load_state()
        team_updates = onboarding_team_flow.interpret_team_onboard_message(raw, state)
        if team_updates:
            onboarding_store.merge_state(team_updates)
        team_inputs: dict[str, Any] = {
            "onboarding": True,
            "interactive_onboarding": True,
            "team_inputs": onboarding_store.load_state(),
        }
        if "onboard" in lowered or "welcome onboard" in lowered:
            team_inputs["_trigger"] = "onboard"
        return {"action": "welcome", "inputs": team_inputs, "intent": "team_onboard"}

    from release_mcp import env_onboarding as env_ob

    if lowered in ENV_CHECKLIST_PHRASES or (
        not workflow_id and env_ob.is_env_onboarding_message(raw)
    ):
        return {
            "action": "env_onboard",
            "inputs": {"message": raw},
            "intent": "env_checklist" if lowered in ENV_CHECKLIST_PHRASES else "env_onboard",
        }

    if any(p in lowered for p in SETUP_PHRASES) or lowered.startswith("setup"):
        uo.apply_progress_from_message(raw)
        return {
            "action": "beginner_wizard",
            "inputs": {"message": raw},
            "intent": "onboarding",
        }

    if not workflow_id and (
        lowered in ONBOARDING_PROGRESS_PHRASES
        or any(p in lowered for p in ("mcp configured", "outlook done", "teams done"))
        or onboarding_store.load_state().get("wizard_mode") == "beginner"
    ):
        if onboarding_store.load_state().get("wizard_mode") == "beginner" or lowered in ONBOARDING_PROGRESS_PHRASES:
            return {
                "action": "beginner_wizard",
                "inputs": {"message": raw},
                "intent": "onboarding_progress",
            }
        assessment = onboarding.assess_setup(from_mcp=True)
        uo.apply_progress_from_message(raw, assessment=assessment)
        inputs: dict[str, Any] = {
            "onboarding": True,
            "interactive_onboarding": True,
            "team_inputs": onboarding_store.load_state(),
        }
        if any(p in lowered for p in ("mcp configured", "mcp is configured", "env is ready")):
            inputs["mcp_confirmed"] = True
        stored = onboarding_store.get_track()
        if stored:
            inputs["onboarding_track"] = stored
        return {"action": "welcome", "inputs": inputs, "intent": "onboarding_progress"}

    if lowered in NEXT_PHRASES and workflow_id:
        return {"action": "resume", "workflow_id": workflow_id, "intent": "resume"}

    if workflow_id and (
        lowered in YES_PHRASES
        or (
            _session_step(workflow_id) == wizard.STEP_RELEASE_NOTES
            and any(p in lowered for p in RELEASE_NOTES_CONFIRM_PHRASES)
        )
        or (
            _session_step(workflow_id) == wizard.STEP_SERVICE_TICKET
            and any(p in lowered for p in SHIPIT_CONFIRM_PHRASES)
        )
    ):
        token = (confirmation_token or "").strip() or _resolve_confirm_token(workflow_id)
        if token:
            return {
                "action": "confirm",
                "workflow_id": workflow_id,
                "confirmation_token": token,
                "intent": "confirm_step",
            }
        return {"action": "resume", "workflow_id": workflow_id, "intent": "resume"}

    if not workflow_id and (lowered in YES_PHRASES or "start step 1" in lowered):
        inputs = {"start_path": "fetch_review_tickets"}
        if team:
            inputs["team_name"] = team
        return {"action": "welcome", "inputs": inputs, "intent": "start_path_default"}

    ticket_update = _ticket_key_update_inputs(raw, lowered, workflow_id=workflow_id)
    if ticket_update:
        inputs = dict(ticket_update)
        if team:
            inputs["team_name"] = team
        intent = "release_notes_include"
        if "exclusion_ticket_keys" in inputs:
            intent = "exclude_tickets"
        elif "selected_ticket_keys" in inputs:
            intent = "select_tickets"
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": inputs,
            "intent": intent,
        }

    assignee_update = _assignee_exclude_inputs(raw, lowered)
    if workflow_id and assignee_update:
        inputs = dict(assignee_update)
        if team:
            inputs["team_name"] = team
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": inputs,
            "intent": "exclude_assignee",
        }

    if workflow_id and (
        "skip github pr" in lowered
        or "skip pr comment" in lowered
        or "no github pr comment" in lowered
    ):
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": {"skip_github_pr_comments": True},
            "intent": "skip_github_pr_comments",
        }

    if workflow_id and (
        "skip shipit link" in lowered
        or "skip link tickets" in lowered
        or "no link release tickets" in lowered
    ):
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": {"skip_shipit_link_tickets": True},
            "intent": "skip_shipit_link_tickets",
        }

    if workflow_id and (
        "skip review ready" in lowered
        or "skip shipit transition" in lowered
    ):
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": {"skip_shipit_review_ready": True},
            "intent": "skip_shipit_review_ready",
        }

    if any(p in lowered for p in WELCOME_PHRASES) or not workflow_id:
        inputs = {}
        if team:
            inputs["team_name"] = team
        return {"action": "welcome", "inputs": inputs, "intent": "welcome"}

    if workflow_id and confirmation_token and lowered in YES_PHRASES:
        return {
            "action": "confirm",
            "workflow_id": workflow_id,
            "confirmation_token": confirmation_token,
            "intent": "confirm_step",
        }

    if workflow_id and any(p in lowered for p in SLACK_SEND_PHRASES):
        import browser_automation

        inputs: dict[str, Any] = {"slack_decision": "send"}
        use_playwright = "playwright" in lowered or (
            browser_automation.prefer_playwright_slack() and "mcp" not in lowered
        )
        if use_playwright:
            inputs["slack_via_playwright"] = True
            inputs["slack_decision"] = "playwright"
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": inputs,
            "intent": "send_slack_playwright" if inputs.get("slack_via_playwright") else "send_slack",
        }

    if workflow_id and any(p in lowered for p in SHAREPOINT_UPLOAD_PHRASES):
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": {"sharepoint_upload": "playwright"},
            "intent": "sharepoint_playwright_upload",
        }

    if workflow_id and any(p in lowered for p in SHAREPOINT_DONE_PHRASES):
        inputs = {"sharepoint_decision": "sharepoint done"}
        if "sharepoint.com" in lowered or "http" in lowered:
            # URL may be on same line as "sharepoint done https://..."
            url_match = re.search(r"https://\S+", raw)
            if url_match:
                inputs["sharepoint_url"] = url_match.group(0).rstrip(").,;")
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": inputs,
            "intent": "sharepoint_done",
        }

    if any(p in lowered for p in HELP_PHRASES):
        return {"action": "help", "intent": "help"}

    if workflow_id and any(p in lowered for p in SLACK_SKIP_PHRASES):
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": {"slack_decision": "skip"},
            "intent": "skip_slack",
        }

    if workflow_id and any(p in lowered for p in SLACK_DONE_PHRASES):
        return {
            "action": "update",
            "workflow_id": workflow_id,
            "inputs": {"slack_decision": "slack done"},
            "intent": "slack_mcp_done",
        }

    # Pass-through: treat as structured update (sharepoint URL, version, exclusions)
    inputs: dict[str, Any] = {}
    if team:
        inputs["team_name"] = team
    if re.search(r"https?://", raw):
        inputs["sharepoint_url"] = raw.strip()
    version_match = re.search(r"\b20\d{2}\.\d+\.\d+\.\d+\b", raw)
    if version_match:
        inputs["version_name"] = version_match.group(0)
    ticket_update = _ticket_key_update_inputs(raw, lowered, workflow_id=workflow_id)
    if ticket_update:
        inputs.update(ticket_update)

    if workflow_id and inputs:
        return {"action": "update", "workflow_id": workflow_id, "inputs": inputs, "intent": "update"}

    if workflow_id:
        return {"action": "resume", "workflow_id": workflow_id, "intent": "resume"}

    return {"action": "welcome", "inputs": inputs, "intent": "welcome"}


def _step_meta(step: str | None) -> dict[str, str]:
    key = (step or "welcome").strip()
    return STEP_GUIDE.get(key, {"number": "?", "title": key, "goal": ""})


def _say_to_user(result: dict[str, Any]) -> str:
    """Build the message the agent should speak to the user."""
    step = str(result.get("step") or "welcome")
    meta = _step_meta(step)
    status = str(result.get("status") or "")
    prompt = str(result.get("prompt") or "").strip()

    if step == "onboarding" or (step in {"welcome", "onboarding"} and status in {"setup", "blocked"}):
        if result.get("interactive_onboarding") or result.get("prompt"):
            prompt = str(result.get("prompt") or "").strip()
            if prompt:
                return prompt
        guide = (result.get("env") or {}).get("setup_guide") or ""
        if guide:
            return guide
        return onboarding.format_interactive_onboarding_prompt(
            onboarding.assess_setup(),
            show_intro=True,
        )

    if step == "start_menu" and status == "ok":
        prompt = str(result.get("prompt") or "").strip()
        return step_ux.wrap_user_message("start_menu", prompt, status=status)

    if step == "welcome" and status == "ok":
        body = str(result.get("prompt") or step_ux.step_hint("welcome"))
        return step_ux.wrap_user_message("welcome", body, status=status, include_progress=False)

    if status == "blocked" and (result.get("env") or {}).get("missing"):
        return (result.get("env") or {}).get("setup_guide") or (
            "One-time setup needed — say **onboarding** for the full checklist."
        )

    if status == "awaiting_confirmation":
        preview = result.get("preview") or {}
        count = preview.get("selected_count") or preview.get("total_tickets")
        if step == "release_date_confirm":
            proposal = preview.get("release_date_proposal") or {}
            body = str(result.get("prompt") or "").strip()
            if not body and proposal:
                from release_date_confirm import format_confirmation_prompt

                body = format_confirmation_prompt(proposal)
            return step_ux.wrap_user_message(step, body, status=status)
        if step == "release_notes":
            gh = preview.get("github_pr_gate") or {}
            gh_block = ""
            if gh.get("blocking_count"):
                gh_block = f"\n\n{gh.get('summary') or ''}"
            comment_keys = preview.get("comment_included_keys") or []
            comment_block = ""
            if comment_keys:
                comment_block = (
                    f"\n\nIncluded via **ready for release** comment: **{', '.join(comment_keys)}**"
                )
            body = f"{result.get('prompt') or 'Review release notes draft.'}{comment_block}{gh_block}"
            return step_ux.wrap_user_message(step, body, status=status)
        if step == "ticket_review" and count is not None:
            missing = preview.get("in_progress_gate") or {}
            held = preview.get("review_comment_gate") or {}
            held_lines = ""
            if missing.get("held_back_keys"):
                keys = ", ".join(missing["held_back_keys"])
                held_lines = (
                    f"\n\nHeld back (no **ready for review** Jira comment): **{keys}**"
                )
            if held.get("held_back_keys"):
                keys = ", ".join(held["held_back_keys"])
                held_lines += f"\n\nHeld back (already review-complete in Jira): **{keys}**"
            assignee_lines = _format_assignee_check(preview)
            assignee_block = f"\n\n{assignee_lines}" if assignee_lines else ""
            body = f"Found **{count}** ticket(s) ready for review.{held_lines}{assignee_block}"
            return step_ux.wrap_user_message(step, body, status=status)
        return step_ux.wrap_user_message(step, prompt or "Review the preview.", status=status)

    if status == "needs_input":
        return step_ux.wrap_user_message(step, prompt or meta["goal"], status=status)

    if status in {"completed", "complete"} or step == "complete":
        return step_ux.wrap_user_message("complete", "Release workflow complete.", status=status)

    if prompt:
        return step_ux.wrap_user_message(step, prompt, status=status)

    return step_ux.wrap_user_message(step, meta["goal"], status=status)


def _user_can_say(result: dict[str, Any]) -> list[str]:
    status = str(result.get("status") or "")
    step = str(result.get("step") or "")

    if step == "onboarding" or (step in {"welcome", "onboarding"} and status in {"setup", "blocked"}):
        onboarding_assessment = (result.get("env") or {}).get("onboarding") or {}
        if onboarding_assessment.get("needs_track_picker"):
            return ["both", "release only", "daily review only", "help"]
        primary = ["done", "use glofox", "crew done", "help"]
        extra = ["next", "mcp configured", "use ignite", "projects pic an", "crew status", "outlook done", "teams done"]
        return primary + [p for p in extra if p not in primary]
    if step in step_ux.STEP_UX or step in {"start_menu", "welcome"}:
        phrases = step_ux.primary_phrases(step, limit=4)
        if phrases:
            if "help" not in phrases:
                phrases.append("help")
            return phrases
    if status == "awaiting_confirmation":
        return step_ux.primary_phrases(step, limit=3) or ["yes", "exclude PIC-1234", "help"]
    if step == "complete":
        return ["welcome", "full release"]
    return ["yes", "help", "cancel"]


def _next_mcp_call(result: dict[str, Any]) -> dict[str, Any]:
    """Tell the agent exactly what to call next (internal); user only sees say_to_user."""
    status = str(result.get("status") or "")
    step = str(result.get("step") or "")
    workflow_id = result.get("workflow_id")
    call: dict[str, Any] = {"tool": "release_orchestrator"}

    if status == "awaiting_confirmation" and workflow_id:
        destructive = {
            "service_ticket",
            "deploy",
            "mark_released",
            "undo",
        }
        if step in destructive:
            call["message"] = "review preview first — confirm with yes only after operator review"
        else:
            call["message"] = "yes"
        call["workflow_id"] = workflow_id
        return call
    if status == "needs_input" and workflow_id:
        call["message"] = "next"
        call["workflow_id"] = workflow_id
        return call
    if step == "complete":
        call["message"] = "welcome"
        return call
    if step == "start_menu" and not workflow_id:
        call["message"] = "fetch review tickets"
        return call
    if step == "onboarding" and not workflow_id:
        call["message"] = "done"
        return call
    if not workflow_id:
        call["message"] = "start"
        return call
    call["message"] = "next"
    call["workflow_id"] = workflow_id
    return call


def enrich_response(result: dict[str, Any], *, user_message: str = "") -> dict[str, Any]:
    """Add conversational layer on top of wizard/welcome JSON."""
    enriched = dict(result)
    step = str(result.get("step") or "welcome")
    meta = _step_meta(step)
    enriched["guided"] = True
    enriched["step_number"] = meta["number"]
    enriched["step_title"] = meta["title"]
    enriched["step_goal"] = meta["goal"]
    enriched["roadmap"] = welcome.STEP_ROADMAP
    enriched["say_to_user"] = _say_to_user(result)
    default_can_say = _user_can_say(result)
    enriched["user_can_say"] = result.get("user_can_say") or default_can_say
    enriched["primary_phrase"] = (enriched["user_can_say"] or default_can_say or [None])[0]
    enriched["progress"] = step_ux.progress_header(step)
    enriched["next_mcp_call"] = _next_mcp_call(result)
    enriched["whats_next"] = onboarding.format_release_next_step(
        str(result.get("step") or "welcome"),
        status=str(result.get("status") or ""),
    )
    if result.get("setup_checklist"):
        enriched["setup_checklist"] = result["setup_checklist"]
    if user_message:
        enriched["understood_message"] = user_message.strip()
    return enriched


def run_guided(
    message: str = "welcome",
    *,
    workflow_id: str | None = None,
    confirmation_token: str | None = None,
) -> dict[str, Any]:
    """Single entry point: natural language → wizard → friendly response."""
    plan = interpret_message(message, workflow_id=workflow_id, confirmation_token=confirmation_token)

    if plan.get("action") == "beginner_wizard":
        from release_mcp import beginner_wizard

        body = beginner_wizard.process_message(message)
        assessment = onboarding.assess_setup(from_mcp=True)
        body = {
            **body,
            "status": "complete" if body.get("wizard_step") == "complete" else (
                "ok" if body.get("step_done") else "setup"
            ),
            "step": "onboarding",
            "interactive_onboarding": True,
            "setup_checklist": assessment.get("items") or [],
            "user_can_say": ["continue", "env checklist", "help", "production ready"],
        }
        return enrich_response(body, user_message=message)

    if plan.get("action") == "env_onboard":
        from release_mcp import env_onboarding as env_ob

        body = env_ob.process_env_message(message)
        assessment = onboarding.assess_setup(from_mcp=True)
        body = {
            **body,
            "status": "ok" if body.get("status", {}).get("all_required_ready") else "setup",
            "step": "onboarding",
            "prompt": body.get("prompt") or env_ob.format_env_checklist(),
            "env_checklist": body.get("status"),
            "setup_checklist": assessment.get("items") or [],
            "user_can_say": [
                "env checklist",
                "use glofox",
                "email you@abcfitness.com",
                "org is abcfinancial",
                "done",
                "mcp configured",
            ],
        }
        return enrich_response(body, user_message=message)

    if plan.get("action") == "list_release_tickets":
        from release_mcp import release_ops

        inputs = plan.get("inputs") or {}
        team_res = welcome.resolve_team(str(inputs.get("team_name") or ""))
        team_map: dict[str, list[str]] | None = None
        if team_res.get("status") == "ok":
            tid = str((team_res.get("team") or {}).get("id") or "")
            projects = welcome.default_projects()
            if tid:
                team_map = {pk: [tid] for pk in projects}
        body = release_ops.list_release_ready_tickets(jira_team_ids_by_project=team_map)
        count = int(body.get("ticket_count") or 0)
        formatted = str(body.get("formatted_list") or "").strip()
        status = str(body.get("status") or "error")
        held_back = body.get("held_back_keys") or []
        held_note = ""
        if held_back:
            held_note = (
                f"\n\nHeld back (no **ready for release** comment): **{', '.join(held_back)}**"
            )
        pr_summary = str(body.get("github_pr_summary") or "").strip()
        pr_note = f"\n\n{pr_summary}" if pr_summary else ""
        if status == "ok" and formatted:
            prompt = (
                f"**{count} release-ready ticket(s)** — list only (not locked):\n\n"
                f"{formatted}{held_note}{pr_note}\n\n"
                "Next: **fetch review tickets** to lock for release · "
                "**create release notes** · **schedule review call**."
            )
        elif status == "ok":
            prompt = (
                "No release-ready tickets with a ready-for-release Jira comment."
                + held_note
                + pr_note
            )
        else:
            prompt = str(body.get("message") or "Could not fetch release tickets.")
        body = {
            **body,
            "status": status,
            "step": "ticket_list",
            "prompt": prompt,
            "user_can_say": [
                "fetch review tickets",
                "create release notes",
                "schedule review call",
                "help",
            ],
        }
        return enrich_response(body, user_message=message)

    if plan.get("action") == "daily_review_calendar_handoff":
        from daily_review_agent.calendar_playwright_handoff import handoff_from_run_context
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.schedule import collect_meeting_attendees, meeting_window
        from daily_review_agent.ticket_pipeline import resolve_review_issues

        cfg = load_agent_config()
        start, end = meeting_window(cfg)
        meeting_date = start.strftime("%Y-%m-%d")
        subject = f"{cfg.meeting_subject} — {meeting_date}"
        fetch = resolve_review_issues(cfg)
        issues = fetch.get("issues") or []
        attendees = collect_meeting_attendees(cfg, issues)
        handoff = handoff_from_run_context(
            subject=subject,
            start=start,
            end=end,
            attendees=attendees,
            body_text=f"{len(issues)} ticket(s) in daily review scope.",
            timezone=cfg.timezone,
            primary=True,
        )
        body = {
            "status": "ok",
            "step": "daily_review_calendar_playwright",
            "handoff": handoff,
            "ticket_count": len(issues),
            "prompt": handoff.get("instruction") or "Execute Playwright MCP steps to schedule the review call.",
            "user_can_say": handoff.get("completion", {}).get("user_phrases") or ["calendar done"],
        }
        return enrich_response(body, user_message=message)

    if plan.get("action") == "daily_review":
        from release_mcp import daily_review_guided

        dr_wid = plan.get("workflow_id")
        body = daily_review_guided.run_daily_review_guided(message, workflow_id=dr_wid)
        body["status"] = "ok"
        body["step"] = str(body.get("step") or "daily_review")
        body["prompt"] = str(body.get("say_to_user") or "")
        body["user_can_say"] = body.get("user_can_say") or ["yes", "help"]
        return enrich_response(body, user_message=message)

    if plan.get("action") == "readiness":
        from release_mcp import mcp_readiness

        body = mcp_readiness.assess_mcp_production()
        body["step"] = "onboarding"
        body["status"] = "ok" if body.get("launch_complete") else (
            "ok" if body.get("production_ready") else "setup"
        )
        return enrich_response(body, user_message=message)

    if plan.get("action") == "signoff":
        import operator_signoff as osign
        import production_readiness as pr

        inputs = plan.get("inputs") or {}
        rec = osign.record_signoff(
            str(inputs.get("signoff_id") or ""),
            detail=str(inputs.get("detail") or message),
        )
        body = pr.assess_production_readiness(surface="mcp")
        body["signoff"] = rec
        body["step"] = "onboarding"
        body["status"] = "complete" if body.get("launch_complete") else "ok"
        body["prompt"] = (
            "Launch complete — all sign-offs recorded."
            if body.get("launch_complete")
            else f"Sign-off recorded: {inputs.get('signoff_id')}. Say **production ready** to refresh."
        )
        return enrich_response(body, user_message=message)

    if plan.get("action") == "dispose_test_shipit":
        from release_mcp import release_ops

        inputs = plan.get("inputs") or {}
        body = release_ops.dispose_test_shipit_ticket(str(inputs.get("issue_key") or ""))
        body["step"] = "service_ticket"
        body["status"] = (
            "complete"
            if body.get("deleted") or body.get("canceled")
            else str(body.get("status") or "error")
        )
        body["prompt"] = str(body.get("message") or "")
        return enrich_response(body, user_message=message)

    if plan.get("action") == "team_crew_status":
        import team_crew as tc

        status = tc.team_crew_status()
        draft = status.get("draft") or {}
        team_name = draft.get("team_name") or "*(not configured)*"
        projects = ", ".join(draft.get("projects") or []) or "*(not set)*"
        review_n = len((status.get("teams_meeting_attendees") or {}).get("review") or [])
        deploy_n = len((status.get("teams_meeting_attendees") or {}).get("deployment") or [])
        if status.get("crew_in_env"):
            prompt = (
                f"**Team crew configured** for **{team_name}** ({projects}).\n\n"
                f"- Review call invites: **{review_n}** attendee(s)\n"
                f"- Release call invites: **{deploy_n}** attendee(s)\n\n"
                "To change crew, re-run onboard: **welcome onboard** → pick team → adjust → **crew done**."
            )
        else:
            prompt = (
                "**Team crew not in `.env` yet.**\n\n"
                "Say **use glofox** → **crew done** (writes `.env` automatically).\n"
                "Other teams: **use ignite** / **use etl** → add crew → **crew done**."
            )
        body = {
            "status": "ok" if status.get("crew_in_env") else "setup",
            "step": "onboarding" if not status.get("crew_in_env") else "welcome",
            "prompt": prompt,
            "team_crew": status,
        }
        return enrich_response(body, user_message=message)

    if plan.get("action") == "quickstart":
        from release_mcp import quickstart as qs

        payload = qs.quickstart_payload()
        md = qs.quickstart_markdown()
        body = {
            "status": "ok",
            "step": "welcome",
            "prompt": md,
            "quickstart": payload,
            "user_can_say": ["welcome onboard", "week release", "help", "production ready"],
        }
        return enrich_response(body, user_message=message)

    if plan.get("action") == "help":
        from release_mcp import onboarding_guide, phrase_catalog

        assessment = onboarding.assess_setup(from_mcp=True)
        guide = onboarding.full_onboarding_guide(assessment=assessment)
        e2e_map = phrase_catalog.format_e2e_cheat_sheet()
        body = {
            "status": "ok" if assessment.get("fully_ready") else "setup",
            "step": "onboarding" if not assessment.get("fully_ready") else "welcome",
            "prompt": (guide.get("help") or onboarding_guide.format_help_guide(assessment))
            + "\n\n"
            + e2e_map,
            "onboarding_guide": guide,
            "phrase_e2e_map": phrase_catalog.PHRASE_E2E_FLOWS,
            "help": {
                "usage": (
                    "One doc: **`orchestrator/zones/knowledge/guides/GUIDE.md`** — say **guide** or **quickstart**. "
                    "New machine? **welcome onboard** once. Daily: **week release**. "
                    "Tickets: **fetch review tickets** (lock) · **fetch release tickets** (list only) · "
                    "**schedule review call**. Daily review? **daily review welcome**."
                ),
                "phrase_cheat_sheet": guide.get("phrase_cheat_sheet"),
                "mcp_catalog": guide.get("mcp_catalog"),
                "workflow_phrases": guide.get("workflow_phrases"),
                "setup_checklist": assessment.get("items"),
                "release_roadmap": onboarding.RELEASE_ROADMAP,
                "teams": ["Glofox Insights Customize (default)", "Ignite Insights Customize", "Insights Customize (ETL)"],
                "projects": welcome.default_projects(),
            },
        }
        return enrich_response(body, user_message=message)

    action = str(plan.get("action") or "welcome")
    inputs = dict(plan.get("inputs") or {})
    wf_id = plan.get("workflow_id") or workflow_id
    token = plan.get("confirmation_token") or confirmation_token

    if action == "welcome":
        result = wizard.run_wizard("welcome", inputs=inputs)
    else:
        result = wizard.run_wizard(
            action,
            workflow_id=wf_id,
            inputs=inputs if inputs else None,
            confirmation_token=token,
        )

    return enrich_response(result, user_message=message)
