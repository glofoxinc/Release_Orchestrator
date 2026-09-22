"""Assign Change Details \"Test by\" names and Testing Status.

ETL tickets are handled specially:
- Detected when the Jira assignee/owner is an ETL owner (default: Mona) **or**
  the ticket content matches an ETL signal (e.g. "... BI Reporting").
- Test by → ``Mona/Nikhila`` (the ETL testers).
- Testing Status → ``ETL Done``.

All other tickets:
- Test by → balanced pick from the QA pool, never the ticket owner.
- Testing Status → ``Done``.
"""

from __future__ import annotations

import re

# Canonical QA pool for Change Details \"Test by\" (title case for release notes).
# Prefer ``config.RELEASE_NOTES_TEST_BY_POOL`` / workspace.yaml when configured.
CHANGE_TABLE_TEST_BY_POOL: tuple[str, ...] = (
    "Rekha",
    "Mona",
    "Navya",
    "Chanti",
    "Narasimha",
    "Nikhath",
    "Bharathi",
    "Soumya",
    "Sushma",
)

# Jira assignees treated as ETL owners → Testing Status = "ETL Done".
ETL_OWNER_NAMES: tuple[str, ...] = ("Mona",)

# Test by name applied to ETL tickets. Override via
# ``config.RELEASE_NOTES_ETL_TEST_BY`` / workspace.yaml.
ETL_TEST_BY_NAME = "Mona/Nikhila"

# Ticket content signals that mark a ticket as ETL even when the assignee is not
# an ETL owner. Matched case-insensitively against summary / report / description.
# Override via ``config.RELEASE_NOTES_ETL_CONTENT_PATTERNS`` / workspace.yaml.
ETL_CONTENT_PATTERNS: tuple[str, ...] = (
    r"\betl\b",
    r"\bbi\s+reporting\b",
    r"\b(?:remove|removing|add|adding|onboard\w*|offboard\w*|migrat\w*)\b"
    r".{0,60}\breporting\b",
    r"\bdata\s+(?:fix|load|refresh|backfill|reprocess\w*|correction)\b",
)

# Entry fields scanned for ETL content signals.
_ETL_CONTENT_FIELDS: tuple[str, ...] = ("summary", "report", "description")

TESTING_STATUS_ETL_DONE = "ETL Done"
TESTING_STATUS_DONE = "Done"

_NON_ALPHA = re.compile(r"[^a-z]+")


def _normalize_person_name(name: str) -> str:
    return _NON_ALPHA.sub("", (name or "").strip().lower())


def _first_token(name: str) -> str:
    token = (name or "").strip().split()[0:1]
    return token[0] if token else ""


def person_name_matches(candidate: str, other: str) -> bool:
    """True when ``candidate`` and ``other`` refer to the same person (first-name aware)."""
    if not candidate.strip() or not other.strip():
        return False

    c_norm = _normalize_person_name(candidate)
    o_norm = _normalize_person_name(other)
    if c_norm and o_norm and c_norm == o_norm:
        return True

    c_first = _normalize_person_name(_first_token(candidate))
    o_first = _normalize_person_name(_first_token(other))
    if c_first and o_first and c_first == o_first:
        return True

    if c_norm and o_norm and (c_norm in o_norm or o_norm in c_norm):
        return True

    return False


def get_test_by_pool(
    pool: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, ...]:
    """Return the active QA pool (explicit override → workspace config → default)."""
    if pool:
        return tuple(str(name).strip() for name in pool if str(name).strip())
    try:
        import config

        configured = getattr(config, "RELEASE_NOTES_TEST_BY_POOL", ()) or ()
        names = tuple(str(name).strip() for name in configured if str(name).strip())
        if names:
            return names
    except (ImportError, TypeError):
        # No workspace config on the path — fall back to the built-in pool.
        pass
    return CHANGE_TABLE_TEST_BY_POOL


def eligible_test_by_candidates(
    assignee: str,
    pool: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """Pool members who are not the ticket owner (Jira assignee)."""
    names = list(get_test_by_pool(pool))
    eligible = [name for name in names if not person_name_matches(name, assignee)]
    return eligible or names


def is_etl_ticket_owner(
    assignee: str,
    *,
    etl_owners: tuple[str, ...] | list[str] | None = None,
) -> bool:
    """True when the Jira assignee is an ETL owner (default: Mona)."""
    owners = tuple(etl_owners) if etl_owners is not None else ETL_OWNER_NAMES
    return any(person_name_matches(owner, assignee) for owner in owners)


def get_etl_test_by_name(name: str | None = None) -> str:
    """Return the Test-by name for ETL tickets (override → config → default)."""
    if name and name.strip():
        return name.strip()
    try:
        import config

        configured = getattr(config, "RELEASE_NOTES_ETL_TEST_BY", "") or ""
        if str(configured).strip():
            return str(configured).strip()
    except ImportError:
        pass
    return ETL_TEST_BY_NAME


def get_etl_content_patterns(
    patterns: tuple[str, ...] | list[str] | None = None,
) -> tuple[str, ...]:
    """Return ETL content patterns (explicit override → config → default)."""
    if patterns:
        return tuple(str(p) for p in patterns if str(p).strip())
    try:
        import config

        configured = getattr(config, "RELEASE_NOTES_ETL_CONTENT_PATTERNS", ()) or ()
        pats = tuple(str(p) for p in configured if str(p).strip())
        if pats:
            return pats
    except (ImportError, TypeError):
        # No workspace config on the path — fall back to the built-in patterns.
        pass
    return ETL_CONTENT_PATTERNS


def is_etl_content(
    entry: dict,
    *,
    content_patterns: tuple[str, ...] | list[str] | None = None,
) -> bool:
    """True when a ticket's content matches an ETL signal (e.g. 'BI Reporting')."""
    text = " ".join(str(entry.get(field) or "") for field in _ETL_CONTENT_FIELDS)
    if not text.strip():
        return False
    for pattern in get_etl_content_patterns(content_patterns):
        try:
            if re.search(pattern, text, flags=re.IGNORECASE):
                return True
        except re.error:
            # A malformed custom pattern must not break release notes.
            continue
    return False


def is_etl_ticket(
    entry: dict,
    *,
    etl_owners: tuple[str, ...] | list[str] | None = None,
    content_patterns: tuple[str, ...] | list[str] | None = None,
) -> bool:
    """True when a ticket is ETL by owner (Mona) or by content (BI Reporting …)."""
    assignee = str(entry.get("assignee") or "")
    if is_etl_ticket_owner(assignee, etl_owners=etl_owners):
        return True
    return is_etl_content(entry, content_patterns=content_patterns)


def resolve_testing_status(
    assignee: str,
    *,
    etl_owners: tuple[str, ...] | list[str] | None = None,
) -> str:
    """ETL owner tickets → ``ETL Done``; everyone else → ``Done``.

    This owner-only helper is kept for callers that have just the assignee.
    Prefer :func:`is_etl_ticket` when the full ticket entry is available so
    content-based ETL tickets are also caught.
    """
    if is_etl_ticket_owner(assignee, etl_owners=etl_owners):
        return TESTING_STATUS_ETL_DONE
    return TESTING_STATUS_DONE


def resolve_change_table_test_by(
    assignee: str,
    *,
    ticket_key: str = "",
    row_index: int = 0,
    release_seed: str = "",
    pool: tuple[str, ...] | list[str] | None = None,
    usage_counts: dict[str, int] | None = None,
) -> str:
    """Pick a tester from the pool; never the ticket owner (Jira assignee).

    When ``usage_counts`` is provided, prefers the least-used eligible name so
    assignments stay balanced across the full pool.
    """
    del ticket_key, release_seed  # kept for API compatibility with callers/tests
    candidates = eligible_test_by_candidates(assignee, pool)
    if usage_counts is None:
        # Single-ticket fallback: stable pick by pool order + row index.
        return candidates[row_index % len(candidates)]

    min_count = min(usage_counts.get(name, 0) for name in candidates)
    tied = [name for name in candidates if usage_counts.get(name, 0) == min_count]
    # Preserve pool order among ties for predictable, even fill.
    pool_order = {name: idx for idx, name in enumerate(get_test_by_pool(pool))}
    tied.sort(key=lambda name: pool_order.get(name, 999))
    return tied[0]


def assign_change_table_testers(
    entries: list[dict],
    *,
    release_seed: str = "",
    pool: tuple[str, ...] | list[str] | None = None,
    etl_owners: tuple[str, ...] | list[str] | None = None,
    content_patterns: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """Return one Test-by name per entry.

    ETL tickets (Mona-owned or ETL by content) → ``Mona/Nikhila``. All other
    tickets get a balanced pick from the QA pool (least-assigned-first, never
    the Jira assignee) so the non-ETL rows still spread evenly.
    """
    del release_seed  # kept for API compatibility
    active_pool = get_test_by_pool(pool)
    etl_name = get_etl_test_by_name()
    usage_counts = {name: 0 for name in active_pool}
    assigned: list[str] = []
    for index, entry in enumerate(entries):
        if is_etl_ticket(
            entry, etl_owners=etl_owners, content_patterns=content_patterns
        ):
            assigned.append(etl_name)
            continue
        assignee = str(entry.get("assignee") or "")
        ticket_key = str(entry.get("ticket") or index)
        test_by = resolve_change_table_test_by(
            assignee,
            ticket_key=ticket_key,
            row_index=index,
            pool=active_pool,
            usage_counts=usage_counts,
        )
        usage_counts[test_by] = usage_counts.get(test_by, 0) + 1
        assigned.append(test_by)
    return assigned


def assign_change_table_testing_statuses(
    entries: list[dict],
    *,
    etl_owners: tuple[str, ...] | list[str] | None = None,
    content_patterns: tuple[str, ...] | list[str] | None = None,
) -> list[str]:
    """Return Testing Status per entry.

    ETL tickets (Mona-owned or ETL by content) → ``ETL Done``; else ``Done``.
    """
    return [
        TESTING_STATUS_ETL_DONE
        if is_etl_ticket(
            entry, etl_owners=etl_owners, content_patterns=content_patterns
        )
        else TESTING_STATUS_DONE
        for entry in entries
    ]
