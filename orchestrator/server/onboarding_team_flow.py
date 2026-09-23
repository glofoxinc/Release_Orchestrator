"""Interactive team + crew selection — kept short for Glofox and other teams."""

from __future__ import annotations

import re
from typing import Any

import team_crew as tc
from sharepoint_url import parse_sharepoint_folder_browse_url
from team_crew import TeamCrewDraft

_PREFILLED_TEAMS = frozenset({"glofox"})
_SHAREPOINT_OK_PHRASES = frozenset({
    "sharepoint ok",
    "sharepoint confirmed",
    "sharepoint setup done",
    "sharepoint path ok",
})


def _draft_from_inputs(inputs: dict[str, Any]) -> TeamCrewDraft | None:
    raw = inputs.get("team_crew_draft")
    if not isinstance(raw, dict):
        env_draft = tc.load_crew_from_env()
        if env_draft and env_draft.is_complete():
            return env_draft
        return None
    draft = TeamCrewDraft(
        team_key=str(raw.get("team_key") or ""),
        team_name=str(raw.get("team_name") or ""),
        jira_team_id=str(raw.get("jira_team_id") or ""),
        projects=[str(p).upper() for p in (raw.get("projects") or []) if str(p).strip()],
    )
    draft.squad = [_person_dict(p) for p in (raw.get("squad") or [])]
    draft.review = [_person_dict(p) for p in (raw.get("review") or [])]
    draft.release = [_person_dict(p) for p in (raw.get("release") or [])]
    draft.qa = [_person_dict(p) for p in (raw.get("qa") or [])]
    draft.leadership = [_person_dict(p) for p in (raw.get("leadership") or [])]
    draft.optional = [_person_dict(p) for p in (raw.get("optional") or [])]
    ex = raw.get("exclude_emails") or []
    draft.exclude_emails = {str(e).lower() for e in ex if str(e).strip()}
    return draft


def _person_dict(item: Any) -> tc.CrewPerson:
    if isinstance(item, dict):
        return tc.CrewPerson(name=str(item.get("name") or ""), email=str(item.get("email") or ""))
    return tc.CrewPerson(name=str(item))


def _draft_to_dict(draft: TeamCrewDraft) -> dict[str, Any]:
    return {
        "team_key": draft.team_key,
        "team_name": draft.team_name,
        "jira_team_id": draft.jira_team_id,
        "projects": list(draft.projects),
        "squad": [{"name": p.name, "email": p.email} for p in draft.squad],
        "review": [{"name": p.name, "email": p.email} for p in draft.review],
        "release": [{"name": p.name, "email": p.email} for p in draft.release],
        "qa": [{"name": p.name, "email": p.email} for p in draft.qa],
        "leadership": [{"name": p.name, "email": p.email} for p in draft.leadership],
        "optional": [{"name": p.name, "email": p.email} for p in draft.optional],
        "exclude_emails": sorted(draft.exclude_emails),
    }


def team_crew_env_configured() -> bool:
    draft = tc.load_crew_from_env()
    return draft is not None and draft.is_complete() and draft.crew_configured()


def _try_lock_crew(draft: TeamCrewDraft) -> dict[str, Any] | None:
    if not draft.crew_configured():
        return None
    try:
        return tc.apply_crew_to_env(draft)
    except OSError as exc:
        return {"ok": False, "error": str(exc)}


def _extract_url(text: str) -> str:
    match = re.search(r"https?://[^\s<>\"']+", text or "")
    return match.group(0).rstrip(").,;") if match else ""


def _sharepoint_override_from_profile(profile: tc.TeamCrewProfile | None) -> dict[str, Any]:
    if not profile or not profile.sharepoint:
        return {}
    out = dict(profile.sharepoint)
    out.pop("confirm_note", None)
    return out


def _persist_sharepoint_override(override: dict[str, Any]) -> None:
    if not override:
        return
    from release_mcp import onboarding_store

    onboarding_store.merge_state({"sharepoint_override": override})


def interpret_team_onboard_message(message: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse team/project/crew phrases during welcome onboard."""
    inputs = dict(inputs or {})
    lowered = (message or "").lower().strip()
    updates: dict[str, Any] = {}
    draft = _draft_from_inputs(inputs) or TeamCrewDraft()

    team_key = tc.resolve_team_key_from_phrase(lowered)
    if team_key:
        profile = tc.load_team_profile(team_key)
        if profile:
            draft = tc.draft_from_profile(team_key) or draft
            updates["team_selected"] = team_key
            if team_key in _PREFILLED_TEAMS and draft.crew_configured():
                lock = _try_lock_crew(draft)
                if lock and lock.get("ok"):
                    updates["team_crew_locked"] = True
                    updates["team_crew_confirmed"] = True

    projects = tc.parse_projects_phrase(lowered)
    if projects:
        draft.projects = projects
        updates["projects_selected"] = projects

    if "crew exclude" in lowered or lowered.startswith("exclude "):
        email_part = lowered.split("exclude", 1)[-1].strip()
        for token in email_part.replace(",", " ").split():
            if "@" in token:
                draft.exclude_emails.add(token.strip("<>").lower())
        updates["crew_excluded"] = True

    if "crew add" in lowered or "add to" in lowered:
        person = tc.parse_crew_person(message.split("crew add", 1)[-1] if "crew add" in lowered else message)
        if person:
            if "squad" in lowered:
                draft.squad.append(person)
            elif "leadership" in lowered or "leader" in lowered:
                draft.leadership.append(person)
            elif "qa" in lowered:
                draft.qa.append(person)
            elif "optional" in lowered:
                draft.optional.append(person)
            elif "release" in lowered:
                draft.release.append(person)
            else:
                draft.review.append(person)
            updates["crew_added"] = person.display()

    lock_phrase = any(
        p in lowered
        for p in (
            "crew done",
            "lock crew",
            "team setup done",
            "crew looks good",
            "team crew done",
        )
    )
    if lock_phrase:
        updates["team_crew_confirmed"] = True
        lock = _try_lock_crew(draft)
        if lock:
            updates["team_crew_locked"] = bool(lock.get("ok"))
            if not lock.get("ok"):
                updates["team_crew_lock_error"] = lock.get("error")

    profile = tc.load_team_profile(draft.team_key) if draft.team_key else None

    if lowered in _SHAREPOINT_OK_PHRASES or lowered == "sharepoint ok":
        override = _sharepoint_override_from_profile(profile)
        if override:
            updates["sharepoint_override"] = override
            updates["sharepoint_confirmed"] = True
            _persist_sharepoint_override(override)
            from release_mcp import onboarding_store

            onboarding_store.merge_state({"sharepoint_confirmed": True})

    if "sharepoint folder" in lowered or (
        "sharepoint.com" in lowered and "sharepoint done" not in lowered
    ):
        url = _extract_url(message)
        parsed = parse_sharepoint_folder_browse_url(url)
        if parsed:
            parsed["auto_quarter_subfolder"] = True
            updates["sharepoint_override"] = parsed
            updates["sharepoint_confirmed"] = True
            _persist_sharepoint_override(parsed)
            from release_mcp import onboarding_store

            onboarding_store.merge_state({"sharepoint_confirmed": True})

    if draft.team_key or draft.team_name:
        updates["team_crew_draft"] = _draft_to_dict(draft)
    return updates


def format_team_pick_prompt() -> str:
    return (
        "**Pick your team** (one phrase):\n\n"
        "- **`use glofox`** — PIC + AN, crew pre-filled → then **`crew done`**\n"
        "- **`use ignite`** — PIC only, you add crew\n"
        "- **`use etl`** — PIC only, you add crew\n\n"
        "Glofox is 3 steps: `use glofox` → `crew done` → `sharepoint ok`."
    )


def format_crew_review_prompt(draft: TeamCrewDraft) -> str:
    prefilled = draft.team_key in _PREFILLED_TEAMS
    lines = [
        "**Confirm crew** (one-time)",
        "",
        tc.crew_summary_text(draft),
        "",
    ]
    if prefilled:
        lines.append("Say **`crew done`** to lock this into `.env` automatically.")
    else:
        lines.extend(
            [
                "Send crew in one message, or use **`crew add Name <email> to leadership|qa|squad|optional`**. ",
                "Then **`crew done`** to lock `.env`.",
                "",
                "**Need:** squad names · leadership emails · QA emails · exclude emails (if any)",
            ]
        )
    return "\n".join(lines)


def format_crew_locked_message(draft: TeamCrewDraft, lock: dict[str, Any] | None = None) -> str:
    if lock and lock.get("ok"):
        return (
            f"**Crew locked** for **{draft.team_name}** → `.env` updated.\n\n"
            "Reload MCP in Cursor, then say **`done`** or **`start`**."
        )
    err = (lock or {}).get("error") or "Could not write `.env`"
    snippet = tc.build_env_snippet(draft)
    return (
        f"**Paste into `.env` manually** (auto-lock failed: {err}):\n\n"
        f"```env\n{snippet}\n```\n\n"
        "Reload MCP, then say **`done`**."
    )


def format_sharepoint_onboard_step(draft: TeamCrewDraft | None) -> str:
    profile = tc.load_team_profile(draft.team_key) if draft and draft.team_key else None
    sp = _sharepoint_override_from_profile(profile)
    lines = [
        "**SharePoint Release Notes folder (one-time)**",
        "",
        "Each release uploads to a **quarter subfolder** under your team's Release Notes library,",
        "for example **`2026 - Q3`**. The MCP creates that folder if missing, then uploads the DOCX.",
        "",
    ]
    if sp:
        folder = sp.get("folder_path") or "Shared Documents/.../Release Notes"
        site = sp.get("site_path") or "/teams/..."
        lines.extend([
            f"**{profile.display_name if profile else draft.team_name}** (pre-filled):",
            f"- Site: `{site}`",
            f"- Parent folder: `{folder}`",
            f"- Upload target: `{folder}/{{Year}} - Q{{N}}` (from release version date)",
            "",
        ])
        note = (profile.sharepoint.get("confirm_note") if profile else "") or ""
        if note:
            lines.append(note)
            lines.append("")
        lines.append("Say **`sharepoint ok`** to confirm, or paste a different folder URL:")
        lines.append("`sharepoint folder https://abcfinancial.sharepoint.com/teams/.../AllItems.aspx?id=...`")
    else:
        lines.extend([
            "**New team — paste your SharePoint folder URL:**",
            "1. Open SharePoint → your team's **Release Notes** parent folder (not inside a quarter folder).",
            "2. Copy the browser URL (`AllItems.aspx` with `id=` in the address bar).",
            "3. Paste in chat:",
            "",
            "`sharepoint folder https://abcfinancial.sharepoint.com/teams/.../AllItems.aspx?id=...`",
            "",
            "We strip any existing quarter suffix and recreate **`YYYY - QN`** dynamically each release.",
        ])
    return "\n".join(lines)


def _sharepoint_confirmed(inputs: dict[str, Any] | None = None) -> bool:
    inputs = dict(inputs or {})
    if inputs.get("sharepoint_confirmed"):
        return True
    try:
        from release_mcp import onboarding_store

        state = onboarding_store.load_state()
        if state.get("sharepoint_confirmed") or state.get("sharepoint_override"):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


def onboarding_team_phase(inputs: dict[str, Any] | None = None) -> str:
    """Return phase: needs_team | needs_crew | needs_sharepoint | needs_env_paste | complete."""
    inputs = dict(inputs or {})
    draft = _draft_from_inputs(inputs)

    if team_crew_env_configured() and _sharepoint_confirmed(inputs):
        return "complete"
    if inputs.get("team_crew_locked") and _sharepoint_confirmed(inputs):
        return "complete"

    if draft is None or not draft.team_key or not draft.projects:
        return "needs_team"
    if not draft.crew_configured():
        return "needs_crew"
    if not inputs.get("team_crew_confirmed"):
        return "needs_crew"
    if not _sharepoint_confirmed(inputs):
        return "needs_sharepoint"
    if inputs.get("team_crew_confirmed") and not team_crew_env_configured():
        return "needs_env_paste"
    return "complete"


def format_team_onboard_step(inputs: dict[str, Any] | None = None) -> str:
    """Next team/crew prompt for interactive onboarding."""
    inputs = dict(inputs or {})
    phase = onboarding_team_phase(inputs)
    draft = _draft_from_inputs(inputs)

    if phase == "needs_team":
        return format_team_pick_prompt()
    if phase == "needs_crew" and draft:
        return format_crew_review_prompt(draft)
    if phase == "needs_sharepoint" and draft:
        return format_sharepoint_onboard_step(draft)
    if phase == "needs_env_paste" and draft:
        return format_crew_locked_message(draft, {"ok": False, "error": inputs.get("team_crew_lock_error")})
    if phase == "complete":
        env_draft = tc.load_crew_from_env()
        name = env_draft.team_name if env_draft else (draft.team_name if draft else "your team")
        return f"**Team ready — {name}**. Say **`done`** or **`full release`**."
    return format_team_pick_prompt()


def team_onboard_payload(inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    inputs = dict(inputs or {})
    draft = _draft_from_inputs(inputs)
    phase = onboarding_team_phase(inputs)
    return {
        "phase": phase,
        "team_crew_draft": _draft_to_dict(draft) if draft else None,
        "env_snippet": tc.build_env_snippet(draft) if draft and phase == "needs_env_paste" else "",
        "crew_locked": bool(inputs.get("team_crew_locked")),
        "prompt": format_team_onboard_step(inputs),
        "status": tc.team_crew_status(),
    }
