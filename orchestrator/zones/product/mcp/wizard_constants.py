"""Workflow step identifiers and artifact invalidation map."""

from __future__ import annotations

WORKFLOW_NAME = "releaseops-full"

STEP_TICKET_REVIEW = "ticket_review"
STEP_EXCLUSIONS = "exclusions"
STEP_RELEASE_DATE = "release_date_confirm"
STEP_RELEASE_NOTES = "release_notes"
STEP_SHAREPOINT = "sharepoint"
STEP_SERVICE_TICKET = "service_ticket"
STEP_SLACK = "slack"
STEP_DEPLOY = "deploy"
STEP_MARK_RELEASED = "mark_released"
STEP_COMPLETE = "complete"
STEP_UNDO = "undo_deployment"

STEP_ORDER = [
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

_DOWNSTREAM_ARTIFACT_KEYS: dict[str, tuple[str, ...]] = {
    STEP_TICKET_REVIEW: (
        "ticket_snapshot",
        "ticket_snapshot_draft",
        "exclusion_results",
        "release_notes_docx",
        "sharepoint_url",
        "service_ticket_preflight",
        "service_ticket",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
        "applied_writes",
    ),
    STEP_EXCLUSIONS: (
        "exclusion_results",
        "release_notes_docx",
        "sharepoint_url",
        "service_ticket_preflight",
        "service_ticket",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_RELEASE_NOTES: (
        "release_notes_docx",
        "sharepoint_url",
        "service_ticket_preflight",
        "service_ticket",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_SHAREPOINT: (
        "sharepoint_url",
        "service_ticket_preflight",
        "service_ticket",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_SERVICE_TICKET: (
        "service_ticket_preflight",
        "duplicate_tckt",
        "slack",
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_SLACK: (
        "deployment_context",
        "deployment_result",
        "deployment_results",
        "pending_preview",
    ),
    STEP_DEPLOY: (
        "deployment_context",
        "pending_preview",
    ),
    STEP_MARK_RELEASED: ("pending_preview",),
}
