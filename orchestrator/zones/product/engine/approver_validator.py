"""Pre-flight validation for TCKT approvers and approver groups.

Runs before ticket creation so a stale ``accountId`` or renamed group doesn't
cause the whole POST to fail. Validation results are cached in-memory per
process for 30 minutes — the Streamlit session receives them via
:func:`validate_defaults`.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import jira_client

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 30 * 60


@dataclass
class ApproverCheck:
    """Result of validating a single approver."""

    account_id: str
    name: str = ""
    ok: bool = False
    error: str = ""
    display_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "name": self.name,
            "ok": self.ok,
            "error": self.error,
            "display_name": self.display_name,
        }


@dataclass
class GroupCheck:
    """Result of validating a single approver group."""

    name: str
    ok: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "error": self.error}


@dataclass
class ValidationResult:
    approvers: list[ApproverCheck] = field(default_factory=list)
    groups: list[GroupCheck] = field(default_factory=list)
    cached_at: float = 0.0

    @property
    def all_ok(self) -> bool:
        return all(a.ok for a in self.approvers) and all(g.ok for g in self.groups)

    @property
    def failures(self) -> list[str]:
        messages: list[str] = []
        for a in self.approvers:
            if not a.ok:
                messages.append(
                    f"Approver {a.name or a.account_id} "
                    f"(accountId: {a.account_id or '?'}) {a.error or 'failed validation'}."
                )
        for g in self.groups:
            if not g.ok:
                messages.append(f"Approver group '{g.name}' {g.error or 'failed validation'}.")
        return messages

    def to_dict(self) -> dict[str, Any]:
        return {
            "approvers": [a.to_dict() for a in self.approvers],
            "groups": [g.to_dict() for g in self.groups],
            "cached_at": self.cached_at,
            "all_ok": self.all_ok,
        }


# ── core validators ──────────────────────────────────────────────


def _lookup_user(
    account_id: str,
    *,
    lookup: Callable[[str], dict | None] = jira_client.get_user,
) -> ApproverCheck:
    check = ApproverCheck(account_id=account_id)
    if not account_id:
        check.error = "is missing an accountId — cannot validate"
        return check
    try:
        user = lookup(account_id)
    except Exception as exc:
        logger.debug("Approver lookup failed for %s", account_id, exc_info=True)
        check.error = f"could not be validated: {exc}"
        return check
    if not user:
        check.error = "no longer exists. Remove or replace."
        return check
    check.ok = True
    check.display_name = user.get("displayName", "") or ""
    return check


def _lookup_group(
    group_name: str,
    *,
    lookup: Callable[[str], dict | None] = jira_client.get_group,
) -> GroupCheck:
    check = GroupCheck(name=group_name)
    if not group_name:
        check.error = "is empty — cannot validate"
        return check
    try:
        group = lookup(group_name)
    except Exception as exc:
        logger.debug("Group lookup failed for %s", group_name, exc_info=True)
        check.error = f"could not be validated: {exc}"
        return check
    if not group:
        check.error = "does not exist in Jira."
        return check
    check.ok = True
    return check


def validate_approvers(
    approvers: list[dict[str, Any]],
    *,
    user_lookup: Callable[[str], dict | None] | None = None,
) -> list[ApproverCheck]:
    """Validate each approver's ``accountId`` via Jira."""
    lookup = user_lookup or jira_client.get_user
    out: list[ApproverCheck] = []
    for a in approvers or []:
        account_id = ""
        name = ""
        if isinstance(a, dict):
            account_id = str(a.get("accountId") or a.get("account_id") or "")
            name = str(a.get("name") or a.get("displayName") or "")
        elif isinstance(a, str):
            account_id = a
        check = _lookup_user(account_id, lookup=lookup)
        check.name = name or check.display_name
        out.append(check)
    return out


def validate_groups(
    groups: list[Any],
    *,
    group_lookup: Callable[[str], dict | None] | None = None,
) -> list[GroupCheck]:
    """Validate each approver group exists in Jira."""
    lookup = group_lookup or jira_client.get_group
    out: list[GroupCheck] = []
    for g in groups or []:
        name = ""
        if isinstance(g, dict):
            name = str(g.get("name") or "")
        elif isinstance(g, str):
            name = g
        out.append(_lookup_group(name, lookup=lookup))
    return out


# ── session cache ────────────────────────────────────────────────


def _cache_key(approvers: list[dict[str, Any]], groups: list[Any]) -> str:
    ids = sorted(
        str(a.get("accountId") or a.get("account_id") or a) for a in approvers or []
    )
    names = sorted(
        str(g.get("name") if isinstance(g, dict) else g) for g in groups or []
    )
    return "|".join(ids) + "::" + "|".join(names)


def validate_defaults(
    approvers: list[dict[str, Any]],
    groups: list[Any],
    *,
    cache: dict[str, ValidationResult] | None = None,
    user_lookup: Callable[[str], dict | None] | None = None,
    group_lookup: Callable[[str], dict | None] | None = None,
    now: Callable[[], float] = time.time,
) -> ValidationResult:
    """Validate both approvers and groups, caching the result for 30 minutes.

    Pass ``cache`` (typically ``st.session_state`` for Streamlit) to persist
    the result. Subsequent calls within the TTL return the cached payload.
    """
    key = _cache_key(approvers, groups)
    current = now()
    if cache is not None and key in cache:
        hit = cache[key]
        if isinstance(hit, ValidationResult) and (current - hit.cached_at) < _CACHE_TTL_SECONDS:
            return hit

    result = ValidationResult(
        approvers=validate_approvers(approvers, user_lookup=user_lookup),
        groups=validate_groups(groups, group_lookup=group_lookup),
        cached_at=current,
    )
    if cache is not None:
        cache[key] = result
    return result


def clear_cache(cache: dict[str, Any]) -> None:
    """Remove validation entries from a session-state style cache."""
    for k in list(cache.keys()):
        if isinstance(cache.get(k), ValidationResult):
            del cache[k]
