"""Shared release-notes row parsing — used by generator, MCP preview, and UI."""

from __future__ import annotations

from generators.release_notes_template_defaults import CHANGE_COLUMN_COUNT


def normalize_change_row(cols: list[str]) -> list[str]:
    """Normalize legacy 10/12-column rows and current Ticket Details rows."""
    cols = [c.strip() for c in cols]

    if len(cols) == CHANGE_COLUMN_COUNT:
        return cols

    # Legacy 4-column rows (Ticket|Link|Test|Status) before Assignee was added.
    if len(cols) == 4 and CHANGE_COLUMN_COUNT == 5:
        return [cols[0], cols[1], "", cols[2], cols[3]]

    if len(cols) >= 13 and cols[1] == cols[2] == cols[3]:
        cols = [cols[0], cols[1], cols[2], cols[4], *cols[5:]]

    if len(cols) >= 12:
        legacy = cols[:12]
        cols = [
            legacy[0],
            legacy[1],
            legacy[2],
            legacy[3],
            legacy[4],
            legacy[7],
            legacy[8],
            legacy[9],
            legacy[10],
            legacy[11],
        ]
    elif len(cols) == 11:
        cols.append("")

    if len(cols) >= 10:
        link = cols[4]
        if not link.startswith(("http://", "https://")):
            ticket = cols[1]
            if ticket and "-" in ticket:
                try:
                    import config

                    base = (config.JIRA_BASE_URL or "").rstrip("/")
                    if base:
                        link = f"{base}/browse/{ticket}"
                except (ImportError, AttributeError):
                    pass
        cols = [cols[1], link, "", cols[7], cols[9]]

    while len(cols) < CHANGE_COLUMN_COUNT:
        cols.append("")
    return cols[:CHANGE_COLUMN_COUNT]


def parse_change_rows(raw: str) -> list[list[str]]:
    """Parse pipe-delimited change-row text into normalized column lists."""
    rows: list[list[str]] = []
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        rows.append(normalize_change_row([part.strip() for part in stripped.split("|")]))
    return rows


__all__ = ["normalize_change_row", "parse_change_rows"]
