"""Pre-review and post-QA release gates with optional Slack assignee notify."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import config
import jira_client

DEFAULT_PRE_REVIEW_STATUSES: tuple[str, ...] = (
    "in review",
    "ready for review",
    "peer review",
    "code review",
)

DEFAULT_QA_PASSED_STATUSES: tuple[str, ...] = (
    "done",
    "closed",
    "resolved",
    "ready for release",
    "ready for deployment",
    "qa passed",
    "passed qa",
)

# Pre-review / post-QA default OFF until explicitly enabled in workspace.yaml.
_GATE_ENABLED_DEFAULTS: dict[str, bool] = {
    "pre_review": False,
    "post_qa": False,
}


@dataclass
class GateTicket:
    key: str
    summary: str
    status: str
    assignee_name: str
    assignee_email: str
    project: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "summary": self.summary,
            "status": self.status,
            "assignee_name": self.assignee_name,
            "assignee_email": self.assignee_email,
            "project": self.project,
            "reason": self.reason,
        }


@dataclass
class GateResult:
    gate: str
    ready: list[dict] = field(default_factory=list)
    blocked: list[GateTicket] = field(default_factory=list)
    slack: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "ready_count": len(self.ready),
            "blocked_count": len(self.blocked),
            "ready_keys": [iss.get("key") for iss in self.ready if iss.get("key")],
            "blocked": [t.to_dict() for t in self.blocked],
            "slack": self.slack,
        }


def _section(name: str) -> dict[str, Any]:
    root = getattr(config, "RELEASE_GATES", {}) or {}
    if not isinstance(root, dict):
        return {}
    section = root.get(name) or {}
    return section if isinstance(section, dict) else {}


def gates_root_enabled() -> bool:
    root = getattr(config, "RELEASE_GATES", {}) or {}
    return bool(root.get("enabled", True)) if isinstance(root, dict) else True


def gate_enabled(name: str) -> bool:
    if not gates_root_enabled():
        return False
    section = _section(name)
    default = _GATE_ENABLED_DEFAULTS.get(name, False)
    return bool(section.get("enabled", default))


DEFAULT_REVIEW_COMPLETED_PHRASES: tuple[str, ...] = (
    "review completed",
    "review complete",
    "review done",
    "peer review complete",
    "peer review completed",
    "code review complete",
    "code review completed",
    "review approved",
    "review passed",
    "lgtm",
)

DEFAULT_READY_FOR_REVIEW_PHRASES: tuple[str, ...] = (
    "ready for review",
    "ready to review",
    "please review",
    "ready for peer review",
)

DEFAULT_READY_FOR_RELEASE_PHRASES: tuple[str, ...] = (
    "ready for release",
    "ready to release",
    "rfr",
)


def skip_review_completed_comments_enabled() -> bool:
    """Exclude tickets whose Jira comments already mark review as done."""
    section = _section("pre_review")
    return bool(section.get("skip_review_completed_comments", True))


def review_completed_comment_phrases() -> tuple[str, ...]:
    raw = _section("pre_review").get("review_completed_phrases") or list(
        DEFAULT_REVIEW_COMPLETED_PHRASES
    )
    if not isinstance(raw, list):
        raw = list(DEFAULT_REVIEW_COMPLETED_PHRASES)
    values = tuple(str(s).strip().lower() for s in raw if str(s).strip())
    return values or DEFAULT_REVIEW_COMPLETED_PHRASES


def _latest_review_completed_snippet(comments: list[dict]) -> str | None:
    phrases = review_completed_comment_phrases()
    for comment in reversed(comments):
        body = comment.get("body")
        text = jira_client._comment_plain_text(body)  # noqa: SLF001 — shared ADF helper
        if not text.strip():
            continue
        if any(phrase in text for phrase in phrases):
            return text.strip()[:160]
    return None


def ticket_has_review_completed_comment(issue_key: str) -> tuple[bool, str]:
    """True when a recent comment indicates peer/code review is already finished."""
    if not issue_key:
        return False, ""
    try:
        comments = jira_client.get_issue_comments(issue_key)
    except Exception:  # noqa: BLE001
        return False, ""
    snippet = _latest_review_completed_snippet(comments)
    if snippet:
        return True, snippet
    return False, ""


def squad_assignee_roster() -> tuple[str, ...]:
    """Customize BI squad names used to flag non-squad assignees at ticket review."""
    try:
        import team_crew

        crew_tokens = team_crew.squad_roster_tokens()
        if crew_tokens:
            return crew_tokens
    except ImportError:
        pass
    names: list[str] = list(getattr(config, "RELEASE_NOTES_TEST_BY_POOL", ()) or [])
    owner = str((getattr(config, "RELEASE_META", {}) or {}).get("release_owner") or "").strip()
    if owner:
        names.append(owner)
    ticket_review = getattr(config, "TICKET_REVIEW", {}) or {}
    if isinstance(ticket_review, dict):
        extra = ticket_review.get("assignee_roster_extra") or []
        if isinstance(extra, list):
            names.extend(str(n).strip() for n in extra if str(n).strip())
    return tuple(dict.fromkeys(str(n).strip() for n in names if str(n).strip()))


def assignee_in_squad(display_name: str, roster: tuple[str, ...] | None = None) -> bool:
    """True when Jira assignee display name matches a squad roster token."""
    name = str(display_name or "").strip().lower()
    if not name or name == "unassigned":
        return False
    tokens = roster if roster is not None else squad_assignee_roster()
    return any(token.lower() in name for token in tokens if token)


def assignee_matches_pattern(display_name: str, pattern: str) -> bool:
    """Case-insensitive substring match for exclude-by-assignee chat commands."""
    name = str(display_name or "").strip().lower()
    pat = str(pattern or "").strip().lower()
    return bool(name and pat and pat in name)


def build_assignee_check(extracted: Iterable[dict]) -> dict[str, Any]:
    """Group fetched tickets by assignee; flag names outside the Customize BI squad roster."""
    roster = squad_assignee_roster()
    by_name: dict[str, list[dict]] = {}
    for item in extracted:
        key = str(item.get("ticket") or "").strip().upper()
        if not key:
            continue
        assignee = str(item.get("assignee") or "Unassigned").strip() or "Unassigned"
        by_name.setdefault(assignee, []).append(
            {
                "key": key,
                "summary": str(item.get("summary") or item.get("report") or ""),
                "status": str(item.get("status") or ""),
                "project": str(item.get("project") or key.split("-", 1)[0]),
            }
        )

    by_assignee: list[dict[str, Any]] = []
    outside_squad: list[dict[str, Any]] = []
    for assignee in sorted(by_name.keys(), key=str.lower):
        tickets = by_name[assignee]
        in_squad = assignee_in_squad(assignee, roster)
        entry = {
            "assignee": assignee,
            "in_squad": in_squad,
            "ticket_keys": [t["key"] for t in tickets],
            "tickets": tickets,
        }
        by_assignee.append(entry)
        if not in_squad:
            outside_squad.append(entry)

    return {
        "roster": list(roster),
        "by_assignee": by_assignee,
        "outside_squad_count": len(outside_squad),
        "outside_squad": outside_squad,
        "outside_squad_keys": [
            key for entry in outside_squad for key in entry.get("ticket_keys") or []
        ],
    }


def ticket_review_skip_outside_squad_enabled() -> bool:
    """Ticket Review Step 1 — drop outside-squad / TEAM_CREW_EXCLUDE assignees by default."""
    tr = getattr(config, "TICKET_REVIEW", None) or {}
    if not isinstance(tr, dict):
        return True
    return bool(tr.get("skip_outside_squad_assignees", True))


def ticket_review_include_squad_without_team() -> bool:
    """Include in-squad tickets missed by Jira Team filter (empty Team field edge case)."""
    tr = getattr(config, "TICKET_REVIEW", None) or {}
    if not isinstance(tr, dict):
        return True
    return bool(tr.get("include_squad_assignee_without_team", True))


def filter_extracted_outside_squad_assignees(
    extracted: Iterable[dict],
    *,
    include_outside_squad: bool | None = None,
) -> dict[str, Any]:
    """Remove Gabriel/Erasmo-style tickets before Ticket Review lock (matches Daily Review)."""
    from daily_review_agent.assignee_scope import assignee_scope_reason

    include = (
        bool(include_outside_squad)
        if include_outside_squad is not None
        else not ticket_review_skip_outside_squad_enabled()
    )
    if include:
        return {
            "status": "skipped",
            "kept": list(extracted),
            "skipped": [],
            "skipped_keys": [],
        }

    kept: list[dict] = []
    skipped: list[dict[str, str]] = []
    for item in extracted:
        key = str(item.get("ticket") or item.get("key") or "").strip().upper()
        name = str(item.get("assignee") or "Unassigned").strip() or "Unassigned"
        email = str(item.get("assignee_email") or "").strip()
        reason = assignee_scope_reason(name, email, include_outside_squad=False)
        if reason:
            skipped.append(
                {
                    "key": key,
                    "assignee": name,
                    "email": email,
                    "reason": reason,
                }
            )
            continue
        kept.append(item)
    return {
        "status": "ok",
        "kept": kept,
        "skipped": skipped,
        "skipped_keys": [row["key"] for row in skipped if row.get("key")],
    }


def keys_matching_assignee_patterns(
    extracted: Iterable[dict],
    patterns: Iterable[str],
) -> list[str]:
    """Return ticket keys whose assignee matches any exclude pattern."""
    pats = [str(p).strip() for p in patterns if str(p).strip()]
    if not pats:
        return []
    keys: list[str] = []
    for item in extracted:
        key = str(item.get("ticket") or "").strip().upper()
        assignee = str(item.get("assignee") or "")
        if key and any(assignee_matches_pattern(assignee, pat) for pat in pats):
            keys.append(key)
    return keys


def ready_for_review_comment_phrases() -> tuple[str, ...]:
    raw = _section("pre_review").get("ready_for_review_phrases") or list(
        DEFAULT_READY_FOR_REVIEW_PHRASES
    )
    if not isinstance(raw, list):
        raw = list(DEFAULT_READY_FOR_REVIEW_PHRASES)
    values = tuple(str(s).strip().lower() for s in raw if str(s).strip())
    return values or DEFAULT_READY_FOR_REVIEW_PHRASES


def _latest_ready_for_review_snippet(comments: list[dict]) -> str | None:
    phrases = ready_for_review_comment_phrases()
    for comment in reversed(comments):
        body = comment.get("body")
        text = jira_client._comment_plain_text(body)  # noqa: SLF001
        if not text.strip():
            continue
        lowered = text.lower()
        if any(phrase in lowered for phrase in phrases):
            return text.strip()[:160]
    return None


def ticket_has_ready_for_review_comment(issue_key: str) -> tuple[bool, str]:
    if not issue_key:
        return False, ""
    try:
        comments = jira_client.get_issue_comments(issue_key)
    except Exception:  # noqa: BLE001
        return False, ""
    snippet = _latest_ready_for_review_snippet(comments)
    if snippet:
        return True, snippet
    return False, ""


def filter_extracted_in_progress_review_candidates(
    extracted: Iterable[dict],
) -> dict[str, Any]:
    """Keep In Progress tickets only when a comment says ready for review."""
    kept: list[dict] = []
    held_back: list[dict] = []
    for item in extracted:
        key = str(item.get("ticket") or item.get("key") or "").strip().upper()
        status = str(item.get("status") or "").strip().lower()
        if status != "in progress":
            kept.append(item)
            continue
        ready, snippet = ticket_has_ready_for_review_comment(key)
        if ready:
            kept.append(item)
            continue
        held_back.append(
            {
                "key": key,
                "summary": str(item.get("summary") or ""),
                "status": str(item.get("status") or ""),
                "reason": "In Progress without ready-for-review comment",
                "comment_snippet": snippet,
            }
        )
    return {
        "status": "ok",
        "kept": kept,
        "held_back": held_back,
        "held_back_keys": [row["key"] for row in held_back if row.get("key")],
        "phrases": list(ready_for_review_comment_phrases()),
    }


def _release_notes_section() -> dict[str, Any]:
    rn = getattr(config, "RELEASE_NOTES", None) or {}
    return dict(rn) if isinstance(rn, dict) else {}


def include_ready_for_release_comments_enabled() -> bool:
    """Include tickets whose Jira comments say ready for release (Release Notes fetch)."""
    return bool(_release_notes_section().get("include_ready_for_release_comments", True))


def ready_for_release_comment_phrases() -> tuple[str, ...]:
    raw = _release_notes_section().get("ready_for_release_comment_phrases") or list(
        DEFAULT_READY_FOR_RELEASE_PHRASES
    )
    if not isinstance(raw, list):
        raw = list(DEFAULT_READY_FOR_RELEASE_PHRASES)
    values = tuple(str(s).strip().lower() for s in raw if str(s).strip())
    return values or DEFAULT_READY_FOR_RELEASE_PHRASES


def ready_for_release_comment_candidate_statuses(
    project_keys: Iterable[str] | None = None,
) -> dict[str, list[str]]:
    """Ticket Review-style statuses scanned for ready-for-release comments."""
    explicit = _release_notes_section().get("comment_candidate_statuses")
    if isinstance(explicit, dict) and explicit:
        out: dict[str, list[str]] = {}
        for pk, values in explicit.items():
            key = str(pk).strip().upper()
            if not key:
                continue
            out[key] = [str(s).strip() for s in (values or []) if str(s).strip()]
        return out
    keys = [str(p).strip().upper() for p in (project_keys or []) if str(p).strip()]
    if not keys:
        keys = [p["key"] for p in config.PROJECTS]
    return {pk: list(config.ticket_review_default_checked_statuses(pk)) for pk in keys}


def _latest_ready_for_release_snippet(comments: list[dict]) -> str | None:
    phrases = ready_for_release_comment_phrases()
    for comment in reversed(comments):
        body = comment.get("body")
        text = jira_client._comment_plain_text(body)  # noqa: SLF001
        if not text.strip():
            continue
        lowered = text.lower()
        if any(phrase in lowered for phrase in phrases):
            return text.strip()[:160]
    return None


def ticket_has_ready_for_release_comment(issue_key: str) -> tuple[bool, str]:
    if not issue_key:
        return False, ""
    try:
        comments = jira_client.get_issue_comments(issue_key)
    except Exception:  # noqa: BLE001
        return False, ""
    snippet = _latest_ready_for_release_snippet(comments)
    if snippet:
        return True, snippet
    return False, ""


def filter_extracted_review_completed_comments(
    extracted: Iterable[dict],
) -> dict[str, Any]:
    """Split extracted tickets — hold back those with review-complete comments."""
    if not skip_review_completed_comments_enabled():
        seq = list(extracted)
        return {
            "status": "disabled",
            "kept": seq,
            "held_back": [],
            "held_back_keys": [],
        }

    kept: list[dict] = []
    held_back: list[dict] = []
    for item in extracted:
        key = str(item.get("ticket") or "").strip().upper()
        done, snippet = ticket_has_review_completed_comment(key)
        if done:
            held_back.append(
                {
                    "key": key,
                    "summary": str(item.get("summary") or ""),
                    "status": str(item.get("status") or ""),
                    "reason": "Jira comment indicates review is already complete",
                    "comment_snippet": snippet,
                }
            )
            continue
        kept.append(item)

    return {
        "status": "ok",
        "kept": kept,
        "held_back": held_back,
        "held_back_keys": [row["key"] for row in held_back if row.get("key")],
        "phrases": list(review_completed_comment_phrases()),
    }


def ticket_review_pre_review_enabled() -> bool:
    """Ticket Review Step 2 status filter + Slack panel (feature-flagged).

    When false (default), all fetched tickets are shown. MCP/API pre_review_gate
    still respects gate_enabled('pre_review'). Set filter_ticket_review: true
    in workspace.yaml release_gates.pre_review when ready to enable the UI.
    """
    if not gate_enabled("pre_review"):
        return False
    section = _section("pre_review")
    return bool(section.get("filter_ticket_review", False))


def post_qa_release_notes_enabled() -> bool:
    """Release Notes Step 2 post-QA panel (feature-flagged, default off)."""
    if not gate_enabled("post_qa"):
        return False
    section = _section("post_qa")
    return bool(section.get("filter_release_notes", False))


def pre_review_statuses() -> tuple[str, ...]:
    raw = _section("pre_review").get("ready_statuses") or list(DEFAULT_PRE_REVIEW_STATUSES)
    if not isinstance(raw, list):
        raw = list(DEFAULT_PRE_REVIEW_STATUSES)
    values = tuple(str(s).strip().lower() for s in raw if str(s).strip())
    return values or DEFAULT_PRE_REVIEW_STATUSES


def qa_passed_statuses() -> tuple[str, ...]:
    raw = _section("post_qa").get("passed_statuses") or list(DEFAULT_QA_PASSED_STATUSES)
    if not isinstance(raw, list):
        raw = list(DEFAULT_QA_PASSED_STATUSES)
    values = tuple(str(s).strip().lower() for s in raw if str(s).strip())
    return values or DEFAULT_QA_PASSED_STATUSES


def slack_notify_enabled(gate: str) -> bool:
    return bool(_section(gate).get("slack_notify", True))


def issue_status_name(issue: dict) -> str:
    fields = issue.get("fields") or {}
    status = fields.get("status") or {}
    if isinstance(status, dict):
        return str(status.get("name") or "").strip()
    return str(status or "").strip()


def issue_assignee(issue: dict) -> tuple[str, str]:
    fields = issue.get("fields") or {}
    assignee = fields.get("assignee") or {}
    if not isinstance(assignee, dict):
        return "Unassigned", ""
    name = str(assignee.get("displayName") or "Unassigned").strip() or "Unassigned"
    email = str(assignee.get("emailAddress") or "").strip()
    return name, email


def issue_project_key(issue: dict) -> str:
    key = str(issue.get("key") or "")
    if "-" in key:
        return key.split("-", 1)[0].upper()
    fields = issue.get("fields") or {}
    proj = fields.get("project") or {}
    if isinstance(proj, dict) and proj.get("key"):
        return str(proj["key"]).upper()
    return ""


def _gate_ticket(issue: dict, *, reason: str) -> GateTicket:
    fields = issue.get("fields") or {}
    name, email = issue_assignee(issue)
    return GateTicket(
        key=str(issue.get("key") or ""),
        summary=str(fields.get("summary") or "").strip(),
        status=issue_status_name(issue),
        assignee_name=name,
        assignee_email=email,
        project=issue_project_key(issue),
        reason=reason,
    )


def classify_pre_review(issues: Iterable[dict]) -> GateResult:
    allowed = set(pre_review_statuses())
    ready: list[dict] = []
    blocked: list[GateTicket] = []
    for issue in issues:
        status = issue_status_name(issue).lower()
        if status in allowed:
            ready.append(issue)
            continue
        blocked.append(
            _gate_ticket(
                issue,
                reason=(
                    f"Status '{issue_status_name(issue)}' is not in review-ready list: "
                    + ", ".join(sorted(pre_review_statuses()))
                ),
            )
        )
    return GateResult(gate="pre_review", ready=ready, blocked=blocked)


def classify_post_qa(issues: Iterable[dict]) -> GateResult:
    passed = set(qa_passed_statuses())
    ready: list[dict] = []
    blocked: list[GateTicket] = []
    for issue in issues:
        status = issue_status_name(issue).lower()
        if status in passed:
            ready.append(issue)
            continue
        blocked.append(
            _gate_ticket(
                issue,
                reason=(
                    f"Status '{issue_status_name(issue)}' did not pass QA; expected one of: "
                    + ", ".join(sorted(qa_passed_statuses()))
                ),
            )
        )
    return GateResult(gate="post_qa", ready=ready, blocked=blocked)


def build_pre_review_message(ticket: GateTicket, *, version_name: str = "") -> str:
    statuses = ", ".join(s.replace("_", " ").title() for s in pre_review_statuses())
    from gate_message_content import build_gate_message

    return build_gate_message(
        "pre_review",
        ticket,
        version_name=version_name,
        ready_statuses=statuses,
    )


def build_post_qa_message(ticket: GateTicket, *, version_name: str = "") -> str:
    statuses = ", ".join(s.replace("_", " ").title() for s in qa_passed_statuses())
    from gate_message_content import build_gate_message

    return build_gate_message(
        "post_qa",
        ticket,
        version_name=version_name,
        passed_statuses=statuses,
    )


def format_excluded_table_text(tickets: Iterable[GateTicket]) -> str:
    """Pipe-delimited rows for the Release Notes excluded-tickets section."""
    lines: list[str] = []
    for idx, ticket in enumerate(tickets, start=1):
        lines.append(
            "|".join([
                str(idx),
                ticket.key,
                ticket.summary.replace("|", "/"),
                ticket.status,
                ticket.assignee_name,
                ticket.reason.replace("|", "/"),
                "",
                "",
            ])
        )
    return "\n".join(lines)


def merge_excluded_text(existing: str, tickets: Iterable[GateTicket]) -> str:
    existing_keys = {
        part.strip().upper()
        for line in (existing or "").splitlines()
        for part in line.split("|")
        if part.strip().upper().startswith(("PIC-", "AN-", "TCKT-"))
    }
    new_lines: list[str] = []
    start = len([ln for ln in (existing or "").splitlines() if ln.strip()]) + 1
    for offset, ticket in enumerate(tickets):
        if ticket.key.upper() in existing_keys:
            continue
        new_lines.append(
            "|".join([
                str(start + offset),
                ticket.key,
                ticket.summary.replace("|", "/"),
                ticket.status,
                ticket.assignee_name,
                ticket.reason.replace("|", "/"),
                "",
                "",
            ])
        )
    if not new_lines:
        return existing or ""
    prefix = (existing or "").rstrip()
    if prefix:
        return prefix + "\n" + "\n".join(new_lines)
    return "\n".join(new_lines)


def run_pre_review_gate(
    issues: Iterable[dict],
    *,
    version_name: str = "",
    notify: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    if not gate_enabled("pre_review"):
        seq = list(issues)
        return {
            "status": "disabled",
            "gate": "pre_review",
            "ready_count": len(seq),
            "blocked_count": 0,
            "ready_keys": [i.get("key") for i in seq if i.get("key")],
            "blocked": [],
        }
    result = classify_pre_review(issues)
    payload = result.to_dict()
    payload["status"] = "ok"
    payload["version_name"] = version_name
    if notify and slack_notify_enabled("pre_review") and result.blocked:
        from slack_assignee_notify import notify_gate_tickets

        payload["slack"] = notify_gate_tickets(
            result.blocked,
            lambda t: build_pre_review_message(t, version_name=version_name),
            dry_run=dry_run,
        )
    else:
        payload["slack"] = {"status": "skipped", "reason": "notify=false or no blocked tickets"}
    return payload


def run_post_qa_gate(
    issues: Iterable[dict],
    *,
    version_name: str = "",
    notify: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    if not gate_enabled("post_qa"):
        seq = list(issues)
        return {
            "status": "disabled",
            "gate": "post_qa",
            "ready_count": len(seq),
            "blocked_count": 0,
            "ready_keys": [i.get("key") for i in seq if i.get("key")],
            "blocked": [],
        }
    result = classify_post_qa(issues)
    payload = result.to_dict()
    payload["status"] = "ok"
    payload["version_name"] = version_name
    payload["excluded_tickets_text"] = format_excluded_table_text(result.blocked)
    if notify and slack_notify_enabled("post_qa") and result.blocked:
        from slack_assignee_notify import notify_gate_tickets

        payload["slack"] = notify_gate_tickets(
            result.blocked,
            lambda t: build_post_qa_message(t, version_name=version_name),
            dry_run=dry_run,
        )
    else:
        payload["slack"] = {"status": "skipped", "reason": "notify=false or no blocked tickets"}
    return payload
