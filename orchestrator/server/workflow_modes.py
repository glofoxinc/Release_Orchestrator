"""MCP wizard workflow modes — parity with Streamlit quick-start entry points."""

from __future__ import annotations

WORKFLOW_MODE_FULL = "full"
WORKFLOW_MODE_RELEASE_NOTES = "release_notes_only"
WORKFLOW_MODE_SERVICE_TICKET = "service_ticket_only"
WORKFLOW_MODE_DEPLOYER = "deployer_only"

STEP_TICKET_REVIEW = "ticket_review"
STEP_EXCLUSIONS = "exclusions"
STEP_RELEASE_NOTES = "release_notes"
STEP_SHAREPOINT = "sharepoint"
STEP_SERVICE_TICKET = "service_ticket"
STEP_SLACK = "slack"
STEP_DEPLOY = "deploy"
STEP_MARK_RELEASED = "mark_released"
STEP_COMPLETE = "complete"

FULL_STEP_ORDER = [
    STEP_TICKET_REVIEW,
    STEP_EXCLUSIONS,
    STEP_RELEASE_NOTES,
    STEP_SHAREPOINT,
    STEP_SERVICE_TICKET,
    STEP_SLACK,
    STEP_DEPLOY,
    STEP_MARK_RELEASED,
    STEP_COMPLETE,
]

MODE_REGISTRY: dict[str, dict[str, object]] = {
    WORKFLOW_MODE_FULL: {
        "workflow_name": "releaseops-full",
        "start_step": STEP_TICKET_REVIEW,
        "steps": FULL_STEP_ORDER,
    },
    WORKFLOW_MODE_RELEASE_NOTES: {
        "workflow_name": "releaseops-notes",
        "start_step": STEP_RELEASE_NOTES,
        "steps": [STEP_RELEASE_NOTES, STEP_SHAREPOINT, STEP_COMPLETE],
    },
    WORKFLOW_MODE_SERVICE_TICKET: {
        "workflow_name": "releaseops-tckt",
        "start_step": STEP_SERVICE_TICKET,
        "steps": [STEP_SERVICE_TICKET, STEP_SLACK, STEP_COMPLETE],
    },
    WORKFLOW_MODE_DEPLOYER: {
        "workflow_name": "releaseops-deploy",
        "start_step": STEP_DEPLOY,
        "steps": [STEP_DEPLOY, STEP_MARK_RELEASED, STEP_COMPLETE],
    },
}

_ALIASES = {
    "notes": WORKFLOW_MODE_RELEASE_NOTES,
    "release_notes": WORKFLOW_MODE_RELEASE_NOTES,
    "tckt": WORKFLOW_MODE_SERVICE_TICKET,
    "service_ticket": WORKFLOW_MODE_SERVICE_TICKET,
    "deploy": WORKFLOW_MODE_DEPLOYER,
    "deployer": WORKFLOW_MODE_DEPLOYER,
}


def normalize_mode(raw: str | None) -> str:
    value = (raw or WORKFLOW_MODE_FULL).strip().lower()
    return _ALIASES.get(value, value if value in MODE_REGISTRY else WORKFLOW_MODE_FULL)


def workflow_name_for(mode: str) -> str:
    entry = MODE_REGISTRY[normalize_mode(mode)]
    return str(entry["workflow_name"])


def start_step_for(mode: str) -> str:
    entry = MODE_REGISTRY[normalize_mode(mode)]
    return str(entry["start_step"])


def steps_for(mode: str) -> list[str]:
    entry = MODE_REGISTRY[normalize_mode(mode)]
    return list(entry["steps"])  # type: ignore[arg-type]


def is_standalone(mode: str) -> bool:
    return normalize_mode(mode) != WORKFLOW_MODE_FULL


def skip_snapshot_prerequisites(mode: str) -> bool:
    return normalize_mode(mode) in {
        WORKFLOW_MODE_RELEASE_NOTES,
        WORKFLOW_MODE_SERVICE_TICKET,
        WORKFLOW_MODE_DEPLOYER,
    }


def skip_drift_gate(mode: str) -> bool:
    return normalize_mode(mode) in {
        WORKFLOW_MODE_SERVICE_TICKET,
        WORKFLOW_MODE_DEPLOYER,
    }
