"""Guard against ImportError for snapshot helpers used by Ticket Review."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("JIRA_EMAIL", "test@example.com")
os.environ.setdefault("JIRA_API_TOKEN", "fake")


def test_snapshot_helpers_importable():
    from release_platform.ui.helpers import get_snapshot_ticket_keys, snapshot_selection_pending

    assert callable(get_snapshot_ticket_keys)
    assert callable(snapshot_selection_pending)


def test_ticket_review_step2_importable():
    from release_platform.ui.ticket_review import step2_group

    assert callable(step2_group.get_snapshot_ticket_keys)
