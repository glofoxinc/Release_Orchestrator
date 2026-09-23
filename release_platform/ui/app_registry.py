"""App registry — auto-discovers installed apps from ui/ subpackages."""

from __future__ import annotations

from typing import Any

import config

_BUILTIN_APPS: list[dict[str, Any]] = [
    {
        "id": "ticket_review",
        "label": "Ticket Review",
        "icon": "\U0001f4cb",
        "subtitle": "Review & Group",
        "description": "Lock tickets by fix version or board status, then group for review.",
        "accent": "#8b5cf6",
        "requires_service_desk": False,
    },
    {
        "id": "release_notes",
        "label": "Release Notes",
        "icon": "\U0001f4dd",
        "subtitle": "Release Notes v4",
        "description": "Generate the Word (.docx), then paste your manual SharePoint document link.",
        "accent": "#10b981",
        "requires_service_desk": False,
    },
    {
        "id": "service_ticket",
        "label": "Service Ticket",
        "icon": "\U0001f3ab",
        "subtitle": "Create SHIPIT",
        "description": "Create the Manual Change ticket with ADF plans, approvers, and release notes link.",
        "accent": "#f59e0b",
        "requires_service_desk": True,
    },
    {
        "id": "release_deployer",
        "label": "Release Deployer",
        "icon": "\U0001f680",
        "subtitle": "Post-Deploy",
        "description": "Add deployment comments and transition tickets to Done.",
        "accent": "#3b82f6",
        "requires_service_desk": False,
    },
    {
        "id": "ai_ticket_creator",
        "label": "AI Ticket Creator",
        "icon": "\U0001f916",
        "subtitle": "NL \u2192 Jira",
        "description": "Create Jira tickets from natural-language descriptions with auto-triage.",
        "accent": "#8b5cf6",
        "requires_service_desk": False,
        "optional": True,
    },
]


def _build_app_list(*, optional: bool | None = None) -> list[dict[str, Any]]:
    """Return enabled apps, optionally filtered to primary or optional only."""
    apps: list[dict[str, Any]] = []
    proj_label = config.project_label()
    sd_key = config.TCKT_PROJECT_KEY

    meta_map = {
        "ticket_review": proj_label,
        "release_notes": proj_label,
        "service_ticket": f"{proj_label} \u2192 {sd_key}" if config.SERVICE_DESK_ENABLED else proj_label,
        "release_deployer": " or ".join(config.project_keys()),
        "ai_ticket_creator": proj_label,
    }

    for app_def in _BUILTIN_APPS:
        aid = app_def["id"]
        if not config.app_enabled(aid):
            continue
        if app_def.get("requires_service_desk") and not config.SERVICE_DESK_ENABLED:
            continue
        is_optional = bool(app_def.get("optional"))
        if optional is True and not is_optional:
            continue
        if optional is False and is_optional:
            continue
        app = dict(app_def)
        label = config.app_label(aid)
        if label:
            app["label"] = label
        app["meta"] = meta_map.get(aid, "")
        apps.append(app)
    return apps


def get_enabled_apps() -> list[dict[str, Any]]:
    """Return ordered list of apps that are enabled in the workspace config."""
    apps = _build_app_list()
    for idx, app in enumerate(apps):
        if not app.get("optional"):
            app["title"] = f"{idx + 1}. {app['label']}"
        else:
            app["title"] = app["label"]
    return apps


def get_primary_apps() -> list[dict[str, Any]]:
    """Return enabled core workflow apps shown on the home page."""
    apps = _build_app_list(optional=False)
    for idx, app in enumerate(apps):
        app["title"] = f"{idx + 1}. {app['label']}"
    return apps


def get_optional_apps() -> list[dict[str, Any]]:
    """Return enabled optional apps hidden under a collapsed section on home."""
    apps = _build_app_list(optional=True)
    for app in apps:
        app["title"] = app["label"]
    return apps
