"""Reference-quality sample payload for release notes E2E tests (UI, MCP, CLI)."""

from __future__ import annotations

from typing import Any


def sample_release_notes_data() -> dict[str, Any]:
    """Payload aligned with orchestrator/zones/quality/tests/fixtures reference DOCX parity."""
    return {
        "version": "v2026.3.09.09",
        "release_date": "15-July-2026",
        "dev_team": "Insights Customize BI Team",
        "release_owner": "Nikhath Begum",
        "senior_mgr": "Sushma Bhamidipati",
        "director": "Trent Vanest",
        "svp": "Rahul Das",
        "environment": "Production",
        "summary_p1": (
            "This release includes reporting enhancements, a new report migration "
            "from Looker, and documentation updates."
        ),
        "summary_p2": (
            "Standard (Analyze): Enhanced member reporting\n"
            "Lift: Migrated AIA Partnership Data NZ paginated report\n"
            "Jazzercise: Enhanced Royalties report"
        ),
        "extracted": [
            {
                "type": "Analyze",
                "client": "Standard",
                "report": "Attrition analysis - Expiring Members Details",
                "description": "Expiring Members Details",
                "ticket": "AN-5328",
                "assignee": "Narasimha",
            },
            {
                "type": "Custom",
                "client": "Jazzercise",
                "report": "Royalties",
                "description": "Royalty rates",
                "ticket": "PIC-5730",
                "assignee": "Nikhila",
            },
            {
                "type": "Custom",
                "client": "Lift",
                "report": "AIA Partnership Data NZ - New Paginated Report",
                "description": "New paginated report migrated from Looker",
                "ticket": "PIC-5731",
                "assignee": "Chanti",
            },
        ],
        "analyze_report_rows": (
            "Analyze|Attrition analysis - Expiring Members Details|AN-5328|Narasimha|Dashboard|Existing"
        ),
        "custom_report_tables": (
            "[Jazzercise]\nJazzercise|Royalties|PIC-5730|Nikhila|Dashboard|Existing\n"
            "[Lift]\nLift|AIA Partnership Data NZ - New Paginated Report|PIC-5731|Chanti|Paginated report|Looker-exit"
        ),
        "custom_clients": "Jazzercise, Lift",
        "include_analyze_section": True,
        "deployment_rows": "Analyze| Navya||\nLift|Chanti||\nJazzercise|Nikhath||",
        "change_rows": (
            "PIC-5730|https://abcfinancial.atlassian.net/browse/PIC-5730|Nikhila|Done\n"
            "AN-5328|https://abcfinancial.atlassian.net/browse/AN-5328|Narasimha|Done"
        ),
        "sanity_checklist": "",
        "screenshot_names": "PIC-5730\nAN-5328",
        "excluded_tickets": "",
        "notes": "",
    }
