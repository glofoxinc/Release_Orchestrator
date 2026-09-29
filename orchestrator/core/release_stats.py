"""Quick stats about the current user's TCKT history.

Used by the sidebar "Quick Stats" panel. Everything is in-memory and
cache-friendly; a callable is injected so tests can avoid live Jira calls.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 60 * 60


@dataclass
class QuickStats:
    total: int = 0
    this_quarter: int = 0
    this_month: int = 0
    last_release_date: str = ""
    most_used_approver: str = ""
    avg_draft_to_create_minutes: float | None = None
    cached_at: float = 0.0
    # The approver histogram is useful for the UI hover-tip
    approver_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "this_quarter": self.this_quarter,
            "this_month": self.this_month,
            "last_release_date": self.last_release_date,
            "most_used_approver": self.most_used_approver,
            "avg_draft_to_create_minutes": self.avg_draft_to_create_minutes,
            "approver_counts": dict(self.approver_counts),
            "cached_at": self.cached_at,
        }


def _parse_created(value: str) -> datetime | None:
    if not value:
        return None
    # Strip trailing "Z" and rely on isoformat for Jira's 2026-04-14T10:00:00.000+0000
    cleaned = value.replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return None


def _quarter_start(today: date) -> date:
    q_first_month = 3 * ((today.month - 1) // 3) + 1
    return date(today.year, q_first_month, 1)


def _month_start(today: date) -> date:
    return date(today.year, today.month, 1)


def compute_quick_stats(
    issues: Iterable[dict[str, Any]],
    *,
    draft_timings: list[float] | None = None,
    today: date | None = None,
) -> QuickStats:
    """Compute :class:`QuickStats` from an iterable of Jira issue dicts.

    ``draft_timings`` is an optional list of draft-to-create durations in
    seconds (captured by the Streamlit session); its average is reported in
    minutes so the sidebar can show a single "avg lead time" figure.
    """
    if today is None:
        today = datetime.now(timezone.utc).date()

    total = 0
    this_quarter = 0
    this_month = 0
    last_dt: datetime | None = None
    approver_counts: Counter[str] = Counter()

    q_start = _quarter_start(today)
    m_start = _month_start(today)

    for iss in issues or []:
        total += 1
        fields = iss.get("fields", {}) or {}
        created = _parse_created(fields.get("created", ""))
        if created:
            if last_dt is None or created > last_dt:
                last_dt = created
            if created.date() >= q_start:
                this_quarter += 1
            if created.date() >= m_start:
                this_month += 1
        for approver in _extract_approvers(fields):
            approver_counts[approver] += 1

    most_used_approver = approver_counts.most_common(1)[0][0] if approver_counts else ""

    avg_minutes: float | None = None
    if draft_timings:
        valid = [t for t in draft_timings if t and t > 0]
        if valid:
            avg_minutes = round(sum(valid) / len(valid) / 60.0, 2)

    return QuickStats(
        total=total,
        this_quarter=this_quarter,
        this_month=this_month,
        last_release_date=last_dt.strftime("%Y-%m-%d") if last_dt else "",
        most_used_approver=most_used_approver,
        avg_draft_to_create_minutes=avg_minutes,
        approver_counts=dict(approver_counts),
        cached_at=time.time(),
    )


def _extract_approvers(fields: dict[str, Any]) -> list[str]:
    """Pull approver display-names out of a custom field on a Jira issue."""
    try:
        import config
        cf = (config.TCKT_FIELDS or {}).get("approvers", "")
    except Exception:
        cf = ""
    if not cf or cf not in fields:
        return []
    raw = fields[cf]
    if not raw:
        return []
    if isinstance(raw, dict):
        raw = [raw]
    names: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            name = item.get("displayName") or item.get("name") or item.get("accountId")
            if name:
                names.append(str(name))
        elif isinstance(item, str):
            names.append(item)
    return names


def get_cached_stats(
    fetch: Callable[[], Iterable[dict[str, Any]]],
    *,
    cache: dict[str, Any] | None = None,
    draft_timings: list[float] | None = None,
    now: Callable[[], float] = time.time,
    today: date | None = None,
) -> QuickStats:
    """Get :class:`QuickStats`, hitting a session cache first (1h TTL)."""
    key = "_release_stats_cache"
    if cache is not None and key in cache:
        hit = cache[key]
        if isinstance(hit, QuickStats) and (now() - hit.cached_at) < _CACHE_TTL_SECONDS:
            return hit
    try:
        issues = list(fetch())
    except Exception as exc:
        logger.debug("Failed to fetch TCKT issues for stats: %s", exc)
        issues = []
    stats = compute_quick_stats(issues, draft_timings=draft_timings, today=today)
    if cache is not None:
        cache[key] = stats
    return stats


def record_draft_timing(cache: dict[str, Any], seconds: float) -> None:
    """Append a draft-to-create duration to the session's timing buffer."""
    buf = cache.setdefault("_release_stats_timings", [])
    if isinstance(buf, list):
        buf.append(float(seconds))
