"""Load and learn from real SHIPIT Manual Change deployment tickets in Jira.

Reference tickets such as SHIPIT-8346 define the canonical structure for
summaries, descriptions, plans, and approver groups on the SHIPIT project.

Legacy TCKT references remain in ``tckt_reference.py`` (rollback docs only).
"""

from __future__ import annotations

from typing import Any

import config
import jira_client

from tckt_reference import (
    TcktReference,
    apply_learned_defaults,
    apply_reference_to_session,
    build_summary_from_reference_pattern,
    fetch_reference,
    learn_from_tickets,
)

DEFAULT_REFERENCE_KEY = "SHIPIT-17036"
# Dual gold standards: single-ticket Analyze (17036) + multi-custom PIC (17191)
GOLD_STANDARD_KEYS = ("SHIPIT-17036", "SHIPIT-17191")
LEARN_REFERENCE_KEYS = (
    "SHIPIT-17191",
    "SHIPIT-17036",
    "SHIPIT-16769",
    "SHIPIT-8346",
    "SHIPIT-16106",
)

_DEPLOYMENT_JQL = (
    'project = SHIPIT AND summary ~ "Production Deployment" '
    'AND summary ~ "Insights Customize BI" ORDER BY created DESC'
)


def search_deployment_tickets(
    *,
    max_results: int = 30,
    jql_extra: str = "",
) -> list[dict[str, Any]]:
    """Return recent Insights Customize BI production-deployment SHIPIT tickets."""
    jql = _DEPLOYMENT_JQL
    if jql_extra:
        jql = f"{jql[:-len(' ORDER BY created DESC')]} AND {jql_extra} ORDER BY created DESC"
    fields = [
        "summary",
        "status",
        "created",
        "updated",
        "priority",
        config.TCKT_FIELDS.get("approver_groups", ""),
        config.TCKT_FIELDS.get("implementation_steps", ""),
        config.TCKT_FIELDS.get("verification_steps", ""),
        config.TCKT_FIELDS.get("rollback_steps", ""),
    ]
    fields = [f for f in fields if f]
    return jira_client.search_issues_jql(jql, fields=fields, max_results=max_results)


def fetch_shipit_reference(issue_key: str | None = None) -> TcktReference:
    """Load one SHIPIT ticket using the shared reference extractor."""
    key = (issue_key or DEFAULT_REFERENCE_KEY).strip().upper()
    return fetch_reference(key)


def build_shipit_summary(*, version_name: str) -> str:
    """Match SHIPIT-17036: Glofox Insights Customize BI - Prod Deployment - Release Version …."""
    clean = str(version_name or "").strip().lstrip("vV")
    team_line = config.TCKT_SUMMARY_TEAM or "Insights Customize BI"
    if not clean:
        return f"Glofox {team_line} - Prod Deployment"
    return f"Glofox {team_line} - Prod Deployment - Release Version {clean}"


def collect_approver_group_options(
    recent_tickets: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Merge workspace defaults with groups seen on recent SHIPIT deployment tickets."""
    names: set[str] = set()
    for item in config.TCKT_DEFAULTS.get("approver_groups") or []:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if name:
                names.add(name)
    if recent_tickets:
        learned = learn_from_tickets(recent_tickets)
        for name in learned.get("approver_groups") or []:
            if name:
                names.add(str(name))
    return sorted(names)


def apply_shipit_template(
    ss: dict,
    *,
    issue_key: str | None = None,
    include_summary: bool = False,
    include_plans: bool = False,
) -> TcktReference:
    """One-click apply from the canonical SHIPIT reference ticket (default SHIPIT-17036)."""
    ref = fetch_shipit_reference(issue_key)
    apply_reference_to_session(ref, ss, include_summary=include_summary)
    if not include_plans:
        # Keep generated plans from tickets unless explicitly loading full reference.
        for key in (
            "stk_impl_plan",
            "stk_test_plan",
            "stk_backout_plan",
            "stk_business_impact",
            "stk_description_adf",
            "stk_description_text",
        ):
            ss.pop(key, None)
    if ref.approver_groups and not ss.get("stk_approver_groups"):
        ss["stk_approver_groups"] = list(ref.approver_groups)
    if ref.schedule_timezone:
        ss["stk_schedule_tz"] = ref.schedule_timezone
    return ref


__all__ = [
    "DEFAULT_REFERENCE_KEY",
    "GOLD_STANDARD_KEYS",
    "LEARN_REFERENCE_KEYS",
    "TcktReference",
    "apply_learned_defaults",
    "apply_reference_to_session",
    "apply_shipit_template",
    "build_shipit_summary",
    "build_summary_from_reference_pattern",
    "collect_approver_group_options",
    "fetch_reference",
    "fetch_shipit_reference",
    "learn_from_tickets",
    "search_deployment_tickets",
]
