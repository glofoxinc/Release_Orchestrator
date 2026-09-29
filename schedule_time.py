"""Timezone handling for SHIPIT planned start / end.

The Customize BI team agrees deployment in **IST** (10:30–11:30 AM). Jira
planned start/end fields store the same instant in **US Central (CST/CDT)** so
Command Center sees the correct local time. Ticket text always states **both**
clocks to prevent early closure.
"""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

# Zone the team agrees the window in (India morning deploy).
DEFAULT_SOURCE_TZ = "Asia/Kolkata"

# Zone Jira planned start/end ISO fields are stored in.
DEFAULT_STORE_TZ = "America/Chicago"

# Legacy aliases — store/display for Jira + approver preview.
DEFAULT_SCHEDULE_TZ = DEFAULT_STORE_TZ
DEFAULT_DISPLAY_TZ = DEFAULT_STORE_TZ

# Offered in the picker; ordered by how often this team uses them.
COMMON_TIMEZONES: tuple[str, ...] = (
    "Asia/Kolkata",
    "America/Chicago",
    "America/New_York",
    "Europe/Dublin",
    "Europe/London",
    "Australia/Sydney",
    "UTC",
)

TZ_LABELS: dict[str, str] = {
    "Asia/Kolkata": "India (IST)",
    "America/Chicago": "US Central (CST/CDT)",
    "America/New_York": "US Eastern (EST/EDT)",
    "Europe/Dublin": "Ireland (GMT/IST)",
    "Europe/London": "UK (GMT/BST)",
    "Australia/Sydney": "Australia East (AEST/AEDT)",
    "UTC": "UTC",
}


def zone_label(tz_name: str) -> str:
    """Human label for a timezone, e.g. ``India (IST) — Asia/Kolkata``."""
    label = TZ_LABELS.get(tz_name)
    return f"{label} — {tz_name}" if label else tz_name


def resolve_zone(tz_name: str | None) -> ZoneInfo:
    """Return a ZoneInfo, falling back to the schedule default then UTC."""
    for candidate in (tz_name, DEFAULT_SCHEDULE_TZ, "UTC"):
        if not candidate:
            continue
        try:
            return ZoneInfo(str(candidate))
        except (ZoneInfoNotFoundError, ValueError, KeyError):
            continue
    return ZoneInfo("UTC")


def to_aware(d: date, t: time, tz_name: str | None) -> datetime:
    """Combine a date and time and attach the given timezone."""
    return datetime.combine(d, t).replace(tzinfo=resolve_zone(tz_name))


def format_jira_iso(d: date, t: time, tz_name: str | None) -> str:
    """ISO 8601 with the offset of the chosen zone, e.g. ``...+0530``.

    The offset is derived from the zone on that date, so DST is handled instead
    of stamping whatever offset the machine running the app happens to be in.
    """
    return to_aware(d, t, tz_name).strftime("%Y-%m-%dT%H:%M:%S.000%z")


def convert(dt: datetime, tz_name: str | None) -> datetime:
    """Convert an aware datetime into another zone."""
    return dt.astimezone(resolve_zone(tz_name))


def zone_abbrev(dt: datetime) -> str:
    """Short zone name for an aware datetime (IST, CDT, ...)."""
    return dt.strftime("%Z") or ""


def format_stamp(dt: datetime, *, with_zone: bool = True) -> str:
    """``Aug 05, 2026, 10:00 AM IST`` — Jira pads the day but not the hour."""
    hour = dt.hour % 12 or 12
    meridiem = "AM" if dt.hour < 12 else "PM"
    base = f"{dt.strftime('%b %d, %Y')}, {hour}:{dt.minute:02d} {meridiem}"
    if not with_zone:
        return base
    abbrev = zone_abbrev(dt)
    return f"{base} {abbrev}".strip()


def crosses_day(start: datetime, end: datetime) -> bool:
    """True when the window spans midnight in the given rendering."""
    return start.date() != end.date()


def describe_window(
    start_date: date,
    start_time: time,
    end_date: date,
    end_time: time,
    tz_name: str | None = None,
    display_tz: str | None = None,
) -> dict[str, object]:
    """Entered window plus how Jira reviewers will see it.

    Returns the entered strings, the converted strings, whether the converted
    view spans midnight (the thing that makes a normal morning deployment look
    like an overnight change), and the ISO values sent to Jira.
    """
    tz_name = tz_name or DEFAULT_SCHEDULE_TZ
    display_tz = display_tz or DEFAULT_DISPLAY_TZ

    start = to_aware(start_date, start_time, tz_name)
    end = to_aware(end_date, end_time, tz_name)
    disp_start = convert(start, display_tz)
    disp_end = convert(end, display_tz)

    duration_minutes = int((end - start).total_seconds() // 60)

    return {
        "timezone": tz_name,
        "display_timezone": display_tz,
        "entered_start": format_stamp(start),
        "entered_end": format_stamp(end),
        "display_start": format_stamp(disp_start),
        "display_end": format_stamp(disp_end),
        "start_iso": start.strftime("%Y-%m-%dT%H:%M:%S.000%z"),
        "end_iso": end.strftime("%Y-%m-%dT%H:%M:%S.000%z"),
        "display_crosses_day": crosses_day(disp_start, disp_end),
        "duration_minutes": duration_minutes,
        "valid": duration_minutes > 0,
        "same_zone": tz_name == display_tz,
    }


def _range_text(start: datetime, end: datetime) -> str:
    """``Aug 05, 2026, 10:00 AM – 1:00 PM IST``, expanding when it spans days."""
    abbrev = zone_abbrev(start)
    if start.date() == end.date():
        return (
            f"{format_stamp(start, with_zone=False)} \u2013 "
            f"{format_stamp(end, with_zone=False).split(', ', 2)[-1]} {abbrev}".strip()
        )
    return (
        f"{format_stamp(start, with_zone=False)} \u2013 "
        f"{format_stamp(end, with_zone=False)} {zone_abbrev(end)}".strip()
    )


def resolve_jira_schedule(
    start_date: date,
    start_time: time,
    end_date: date,
    end_time: time,
    *,
    source_tz: str | None = None,
    store_tz: str | None = None,
) -> dict[str, object]:
    """Convert agreed IST window → Jira storage times in CST/CDT (same instant).

    ``start_time`` / ``end_time`` are in ``source_tz`` (default IST).
    Returned ``start_iso`` / ``end_iso`` use ``store_tz`` (default America/Chicago).
    """
    source_tz = source_tz or DEFAULT_SOURCE_TZ
    store_tz = store_tz or DEFAULT_STORE_TZ

    start_src = to_aware(start_date, start_time, source_tz)
    end_src = to_aware(end_date, end_time, source_tz)
    start_store = convert(start_src, store_tz)
    end_store = convert(end_src, store_tz)

    store_start_time = start_store.time().replace(second=0, microsecond=0)
    store_end_time = end_store.time().replace(second=0, microsecond=0)

    return {
        "source_timezone": source_tz,
        "store_timezone": store_tz,
        "start_date": start_store.date(),
        "start_time": store_start_time,
        "end_date": end_store.date(),
        "end_time": store_end_time,
        "start_iso": format_jira_iso(start_store.date(), store_start_time, store_tz),
        "end_iso": format_jira_iso(end_store.date(), store_end_time, store_tz),
        "agreed_range": _range_text(start_src, end_src),
        "reviewer_range": _range_text(start_store, end_store),
        "crosses_day_in_store": crosses_day(start_store, end_store),
    }


def window_statement(
    start_date: date,
    start_time: time,
    end_date: date,
    end_time: time,
    tz_name: str | None = None,
    display_tz: str | None = None,
) -> dict[str, str]:
    """Wording that states the window in both zones inside the ticket text.

    Jira renders planned start/end in each viewer's own timezone, so a ticket
    that only carries the raw fields can be read hours early by another team.
    Spelling both clocks out in the description and plans removes the ambiguity.
    """
    tz_name = tz_name or DEFAULT_SCHEDULE_TZ
    display_tz = display_tz or DEFAULT_DISPLAY_TZ

    start = to_aware(start_date, start_time, tz_name)
    end = to_aware(end_date, end_time, tz_name)
    primary = _range_text(start, end)

    if tz_name == display_tz:
        return {
            "primary": primary,
            "secondary": "",
            "sentence": f"Deployment window: {primary}.",
            "note": "",
            "comment_title": "Deployment window",
            "comment_body": (
                f"Agreed deployment window: {primary}.\n\n"
                "Planned start and Planned end on this ticket match that window."
            ),
        }

    secondary = _range_text(convert(start, display_tz), convert(end, display_tz))
    sentence = f"Deployment window: {primary} ({secondary})."
    note = (
        f"Agreed window is {primary}. Planned start / Planned end on this ticket "
        f"appear as {secondary} for viewers in {display_tz} — same instant. "
        "Do not close or action this change before the agreed window has ended."
    )
    comment_body = (
        f"Agreed deployment window: {primary}.\n\n"
        f"How Planned start / Planned end appear for {display_tz} viewers: "
        f"{secondary}.\n\n"
        "These are the same instant. Do not close or action this change before "
        "the agreed window has ended."
    )
    return {
        "primary": primary,
        "secondary": secondary,
        "sentence": sentence,
        "note": note,
        "comment_title": "Deployment window (timezone clarification)",
        "comment_body": comment_body,
    }


def duration_label(minutes: int) -> str:
    """``3 hours`` / ``2 hours 30 minutes`` for the window length."""
    if minutes <= 0:
        return "invalid window"
    hours, mins = divmod(minutes, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if mins:
        parts.append(f"{mins} minute" + ("s" if mins != 1 else ""))
    return " ".join(parts)


__all__ = [
    "COMMON_TIMEZONES",
    "DEFAULT_DISPLAY_TZ",
    "DEFAULT_SCHEDULE_TZ",
    "DEFAULT_SOURCE_TZ",
    "DEFAULT_STORE_TZ",
    "resolve_jira_schedule",
    "TZ_LABELS",
    "convert",
    "crosses_day",
    "describe_window",
    "duration_label",
    "format_jira_iso",
    "format_stamp",
    "resolve_zone",
    "to_aware",
    "window_statement",
    "zone_abbrev",
    "zone_label",
]
