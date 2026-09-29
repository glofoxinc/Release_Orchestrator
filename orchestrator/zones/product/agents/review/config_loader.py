"""Load Daily Review Agent config (agent.yaml + workspace + env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_AGENT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _AGENT_DIR.parent


def _orchestrator_root() -> Path:
    from daily_review_agent.bootstrap import orchestrator_root

    return orchestrator_root()


from daily_review_agent.paths import ARCHIVE_DIR

_ARCHIVE_TEAMS = ARCHIVE_DIR / "teams_schedule.yaml"


@dataclass
class AttendeeSpec:
    email: str
    name: str = ""
    type: str = "required"


@dataclass
class AlertingConfig:
    on_schedule_failure: bool = True
    channel: str = "organizer_dm"
    organizer_upn: str = ""


@dataclass
class AgentConfig:
    enabled: bool = False
    timezone: str = "Asia/Kolkata"
    run_at: str = "18:00"
    meeting_start: str = "11:30"
    meeting_end: str = "12:00"
    meeting_day_offset: int = 1
    meeting_subject: str = "Glofox Customize BI — Daily Ticket Review"
    meeting_location: str = "Cross Fit"
    meeting_room_email: str = ""
    skip_weekends: bool = True
    jira_team_id: str = ""
    jira_team_name: str = ""
    projects: list[str] = field(default_factory=lambda: ["PIC", "AN"])
    required_attendees: list[AttendeeSpec] = field(default_factory=list)
    optional_attendees: list[AttendeeSpec] = field(default_factory=list)
    assignee_invite_type: str = "optional"
    organizer_upn: str = ""
    demo_subject: str = "Daily Review Agent DEMO"
    demo_duration_minutes: int = 15
    demo_attendees: list[AttendeeSpec] = field(default_factory=list)
    teams_schedule_section: dict[str, Any] = field(default_factory=dict)
    teams_mcp_enabled: bool = True
    teams_summary_conversation_id: str = ""
    teams_post_summary: bool = True
    # Calendar: outlook_com (local Outlook, fully automated) | teams_mcp | graph
    calendar_backend: str = "auto"
    calendar_backends: list[str] = field(default_factory=list)
    calendar_accept_outlook_without_join_url: bool = True
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    slack: Any = None  # SlackDeliveryConfig — set in load_agent_config
    review_filter: Any = None  # ReviewFilterConfig — set in load_agent_config
    ticket_scope: Any = None  # TicketScopeConfig — set in load_agent_config
    playwright_mcp_primary_enabled: bool = True
    playwright_mcp_fallback_enabled: bool = True
    embedded_playwright_fallback_enabled: bool = False

    def can_schedule_live(self) -> bool:
        backend = (self.calendar_backend or "auto").strip().lower()
        if backend == "playwright_mcp" or (
            backend == "auto" and self.playwright_mcp_primary_enabled
        ):
            import browser_automation

            return bool(browser_automation.playwright_mcp_readiness().get("can_schedule"))
        if backend in {"auto", "playwright_outlook", "playwright", "browser", "outlook_web"}:
            from daily_review_agent.playwright_outlook_auth import outlook_readiness

            return bool(outlook_readiness().get("can_schedule"))
        if backend == "graph_delegated":
            from daily_review_agent.graph_calendar import graph_calendar_ready

            return bool(graph_calendar_ready().get("can_schedule"))
        if backend == "outlook_com":
            from daily_review_agent.outlook_calendar import outlook_calendar_ready

            return bool(outlook_calendar_ready().get("can_schedule"))
        if backend == "teams_mcp" and self.teams_mcp_enabled:
            from daily_review_agent.teams_mcp import teams_session_ready

            return teams_session_ready()
        return False


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    return raw if isinstance(raw, dict) else {}


def _parse_attendees(raw: Any, *, default_type: str = "required") -> list[AttendeeSpec]:
    out: list[AttendeeSpec] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            email = item.strip()
            if email:
                out.append(AttendeeSpec(email=email, type=default_type))
            continue
        if not isinstance(item, dict):
            continue
        email = str(item.get("email") or "").strip()
        if not email:
            continue
        out.append(
            AttendeeSpec(
                email=email,
                name=str(item.get("name") or "").strip(),
                type=str(item.get("type") or default_type).strip() or default_type,
            )
        )
    return out


def load_agent_config(path: Path | None = None) -> AgentConfig:
    """Merge agent.yaml with optional workspace overrides and env."""
    agent_path = path or (_AGENT_DIR / "agent.yaml")
    root = _load_yaml(agent_path)

    meeting = root.get("meeting") if isinstance(root.get("meeting"), dict) else {}
    jira_team = root.get("jira_team") if isinstance(root.get("jira_team"), dict) else {}
    demo = root.get("demo") if isinstance(root.get("demo"), dict) else {}
    teams_raw = root.get("teams") if isinstance(root.get("teams"), dict) else {}
    slack_raw = root.get("slack") if isinstance(root.get("slack"), dict) else {}
    huddle_raw = slack_raw.get("huddle") if isinstance(slack_raw.get("huddle"), dict) else {}
    filter_raw = root.get("review_filter") if isinstance(root.get("review_filter"), dict) else {}
    scope_raw = root.get("ticket_scope") if isinstance(root.get("ticket_scope"), dict) else {}
    calendar_raw = root.get("calendar") if isinstance(root.get("calendar"), dict) else {}
    alert_raw = root.get("alerting") if isinstance(root.get("alerting"), dict) else {}

    organizer = str(root.get("organizer_upn") or "").strip()
    teams_section: dict[str, Any] = {}
    if _ARCHIVE_TEAMS.is_file():
        archived = _load_yaml(_ARCHIVE_TEAMS)
        teams_section = archived.get("teams_schedule") if isinstance(archived.get("teams_schedule"), dict) else {}
    if not organizer:
        organizer = str(teams_section.get("organizer_upn") or "").strip()

    demo_attendees = _parse_attendees(demo.get("attendees") or [], default_type="required")
    for person in demo_attendees:
        if not person.email and person.name.lower().find("mohan") >= 0:
            person.email = (os.environ.get("MOHAN_DEMO_EMAIL") or "").strip()

    cfg = AgentConfig(
        enabled=bool(root.get("enabled", False)),
        timezone=str(root.get("timezone") or "Asia/Kolkata").strip() or "Asia/Kolkata",
        run_at=str(root.get("run_at") or "18:00").strip() or "18:00",
        meeting_start=str(meeting.get("start") or "11:30").strip() or "11:30",
        meeting_end=str(meeting.get("end") or "12:00").strip() or "12:00",
        meeting_day_offset=int(meeting.get("day_offset_business_days") or 1),
        meeting_subject=str(meeting.get("subject") or root.get("meeting_subject") or "").strip()
        or "Glofox Customize BI — Daily Ticket Review",
        meeting_location=str(meeting.get("location") or "Cross Fit").strip() or "Cross Fit",
        meeting_room_email=str(meeting.get("room_email") or os.environ.get("MEETING_ROOM_EMAIL") or "").strip(),
        skip_weekends=bool(meeting.get("skip_weekends", True)),
        jira_team_id=str(jira_team.get("id") or "").strip(),
        jira_team_name=str(jira_team.get("name") or "").strip(),
        projects=[str(p).strip().upper() for p in (root.get("projects") or ["PIC", "AN"]) if str(p).strip()],
        required_attendees=_parse_attendees(root.get("required_attendees") or [], default_type="required"),
        optional_attendees=_parse_attendees(root.get("optional_attendees") or [], default_type="optional"),
        assignee_invite_type=str(root.get("assignee_invite_type") or "optional").strip() or "optional",
        organizer_upn=organizer,
        demo_subject=str(demo.get("subject") or "Daily Review Agent DEMO").strip(),
        demo_duration_minutes=int(demo.get("duration_minutes") or 15),
        demo_attendees=[a for a in demo_attendees if a.email],
        teams_schedule_section=teams_section,
        teams_mcp_enabled=bool(teams_raw.get("mcp_enabled", True)),
        teams_summary_conversation_id=str(teams_raw.get("summary_conversation_id") or "").strip(),
        teams_post_summary=bool(teams_raw.get("post_summary", True)),
        calendar_backend=str(root.get("calendar_backend") or "auto").strip().lower() or "auto",
        calendar_backends=[
            str(b).strip().lower()
            for b in (root.get("calendar_backends") or [])
            if str(b).strip()
        ],
        calendar_accept_outlook_without_join_url=bool(
            root.get("calendar_accept_outlook_without_join_url", True)
        ),
    )

    cfg.alerting = AlertingConfig(
        on_schedule_failure=bool(alert_raw.get("on_schedule_failure", True)),
        channel=str(alert_raw.get("channel") or "organizer_dm").strip() or "organizer_dm",
        organizer_upn=str(alert_raw.get("organizer_upn") or organizer).strip(),
    )

    from daily_review_agent.slack_notify import SlackDeliveryConfig

    archive_slack: dict[str, Any] = {}
    archive_path = ARCHIVE_DIR / "slack_announce.yaml"
    if archive_path.is_file():
        archived_slack = _load_yaml(archive_path)
        archive_slack = archived_slack.get("slack_announce") if isinstance(archived_slack.get("slack_announce"), dict) else {}
    channel_ids = archive_slack.get("channel_ids") if isinstance(archive_slack.get("channel_ids"), dict) else {}
    default_channel = str(slack_raw.get("channel_name") or "insights-customize-squad").strip()
    default_channel_id = str(slack_raw.get("channel_id") or channel_ids.get(default_channel) or "").strip()
    cc_ids = slack_raw.get("cc_user_ids") or []
    if not isinstance(cc_ids, list):
        cc_ids = []

    from daily_review_agent.review_filter import ReviewFilterConfig

    phrases = filter_raw.get("skip_comment_phrases") or []
    if not isinstance(phrases, list):
        phrases = []
    cfg.review_filter = ReviewFilterConfig(
        enabled=bool(filter_raw.get("enabled", True)),
        check_comments=bool(filter_raw.get("check_comments", True)),
        skip_phrases=[str(p).strip() for p in phrases if str(p).strip()],
        case_insensitive=bool(filter_raw.get("case_insensitive", True)),
    )

    from daily_review_agent.assignee_scope import TicketScopeConfig

    cfg.ticket_scope = TicketScopeConfig(
        include_outside_squad_assignees=bool(scope_raw.get("include_outside_squad_assignees", False)),
    )
    cfg.playwright_mcp_primary_enabled = bool(calendar_raw.get("playwright_mcp_primary_enabled", True))
    cfg.playwright_mcp_fallback_enabled = bool(calendar_raw.get("playwright_mcp_fallback_enabled", True))
    cfg.embedded_playwright_fallback_enabled = bool(
        calendar_raw.get("embedded_playwright_fallback_enabled", False)
    )

    cfg.slack = SlackDeliveryConfig(
        enabled=bool(slack_raw.get("enabled", False)),  # Teams-first: Slack off by default
        channel_name=default_channel,
        channel_id=default_channel_id,
        team_id=str(slack_raw.get("team_id") or os.environ.get("SLACK_TEAM_ID") or "").strip(),
        post_summary=bool(slack_raw.get("post_summary", True)),
        schedule_reminder=bool(slack_raw.get("schedule_reminder", False)),
        reminder_minutes_before=int(slack_raw.get("reminder_minutes_before") or 15),
        huddle_enabled=bool(huddle_raw.get("enabled", False)),
        huddle_post_link=bool(huddle_raw.get("post_link", True)),
        cc_user_ids=[str(x).strip() for x in cc_ids if str(x).strip()],
    )

    jira_email = (os.environ.get("JIRA_EMAIL") or "").strip()
    if jira_email and not any(a.email.lower() == jira_email.lower() for a in cfg.demo_attendees):
        cfg.demo_attendees.insert(
            0,
            AttendeeSpec(email=jira_email, name="Organizer", type="required"),
        )

    return cfg


def readiness_report(cfg: AgentConfig) -> dict[str, Any]:
    """Human-readable readiness for CLI / logs."""
    import config as app_config

    from daily_review_agent.schedule_registry import schedule_status
    from daily_review_agent.slack_notify import slack_readiness
    from daily_review_agent.teams_mcp import teams_readiness

    jira_blockers: list[str] = []
    if not (os.environ.get("JIRA_EMAIL") and os.environ.get("JIRA_API_TOKEN")):
        jira_blockers.append("JIRA_EMAIL and JIRA_API_TOKEN required in .env")
    if not cfg.jira_team_id:
        jira_blockers.append("jira_team.id missing in orchestrator/zones/product/agents/review/agent.yaml")

    from daily_review_agent.outlook_calendar import outlook_calendar_ready

    from daily_review_agent.graph_calendar import graph_calendar_ready

    calendar_backend = (cfg.calendar_backend or "auto").strip().lower()
    graph_status = graph_calendar_ready() if calendar_backend == "graph_delegated" else {"enabled": False}
    outlook_status = outlook_calendar_ready()
    teams_status = teams_readiness() if cfg.teams_mcp_enabled else {"enabled": False}
    teams_blockers = list(teams_status.get("blockers") or [])
    calendar_blockers: list[str] = []
    orchestrator_status: dict[str, Any] = {}
    if calendar_backend == "auto":
        from daily_review_agent.calendar_orchestrator import orchestrator_readiness

        orchestrator_status = orchestrator_readiness(cfg)
        if not orchestrator_status.get("can_schedule_any"):
            calendar_blockers = list(orchestrator_status.get("blockers") or [])
    elif calendar_backend == "graph_delegated":
        calendar_blockers = list(graph_status.get("blockers") or [])
    elif calendar_backend == "outlook_com":
        calendar_blockers = list(outlook_status.get("blockers") or [])
    elif calendar_backend == "teams_mcp":
        calendar_blockers = list(teams_status.get("blockers") or [])
    if cfg.teams_post_summary and not cfg.teams_summary_conversation_id:
        teams_blockers.append("teams.summary_conversation_id missing in agent.yaml")

    slack_status = slack_readiness(cfg.slack) if cfg.slack else {"enabled": False}

    import browser_automation

    playwright_mcp_status = browser_automation.playwright_mcp_readiness()
    playwright_fallback_warnings: list[str] = []
    if cfg.playwright_mcp_primary_enabled or cfg.playwright_mcp_fallback_enabled:
        for msg in playwright_mcp_status.get("blockers") or []:
            if msg:
                playwright_fallback_warnings.append(str(msg))

    return {
        "agent_enabled": cfg.enabled,
        "calendar_backend": calendar_backend,
        "delivery_backend": calendar_backend,
        "jira_configured": bool(app_config.JIRA_EMAIL and app_config.JIRA_API_TOKEN),
        "organizer_upn": cfg.organizer_upn,
        "jira_team": cfg.jira_team_name or cfg.jira_team_id,
        "projects": cfg.projects,
        "hard_blockers_for_jira_fetch": jira_blockers,
        "hard_blockers_for_live_teams": teams_blockers,
        "hard_blockers_for_live_calendar": calendar_blockers,
        "graph_delegated": graph_status,
        "outlook_com": outlook_status,
        "calendar_orchestrator": orchestrator_status,
        "teams_mcp": teams_status,
        "schedule": schedule_status(),
        "demo_attendee_count": len(cfg.demo_attendees),
        "slack": slack_status,
        "playwright_mcp": playwright_mcp_status,
        "playwright_mcp_primary_enabled": cfg.playwright_mcp_primary_enabled,
        "playwright_mcp_fallback_enabled": cfg.playwright_mcp_fallback_enabled,
        "embedded_playwright_fallback_enabled": cfg.embedded_playwright_fallback_enabled,
        "playwright_mcp_fallback_warnings": playwright_fallback_warnings,
    }
