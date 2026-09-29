"""Reusable TCKT ticket templates.

Templates capture a partial ``ticket_data`` dict plus the deployment window
defaults for a recurring scenario. They're stored as YAML files under a
user-controlled directory (defaulting to ``~/.jira-release-tool/templates``)
so personal templates survive tool upgrades.

Public API
----------
- :func:`list_templates` — enumerate template names.
- :func:`load_template` — read a template by name.
- :func:`save_template` — persist/overwrite a template.
- :func:`delete_template` — remove a template.
- :func:`apply_template` — merge a template into an existing draft dict.
- :data:`BUILTIN_TEMPLATES` — shipped-with-the-tool presets.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

logger = logging.getLogger(__name__)


def default_templates_dir() -> Path:
    """Return the directory where user templates are stored."""
    override = os.environ.get("JRT_TEMPLATES_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".jira-release-tool" / "templates"


@dataclass
class Template:
    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)

    def to_yaml(self) -> str:
        return yaml.safe_dump(
            {
                "name": self.name,
                "description": self.description,
                "tags": list(self.tags),
                "data": dict(self.data),
            },
            sort_keys=False,
            default_flow_style=False,
            allow_unicode=True,
        )

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Template":
        if not isinstance(raw, dict):
            raise ValueError("Template source must be a mapping")
        name = str(raw.get("name") or "").strip()
        if not name:
            raise ValueError("Template is missing required 'name'")
        tags_raw = raw.get("tags") or []
        if isinstance(tags_raw, str):
            tags = [part.strip() for part in tags_raw.split(",") if part.strip()]
        elif isinstance(tags_raw, (list, tuple, set)):
            tags = [str(tag).strip() for tag in tags_raw if str(tag).strip()]
        else:
            raise ValueError("Template 'tags' must be a list or comma-separated string")
        data_raw = raw.get("data") or {}
        if not isinstance(data_raw, dict):
            raise ValueError("Template 'data' must be a mapping")
        return cls(
            name=name,
            description=str(raw.get("description") or ""),
            tags=tags,
            data=dict(data_raw),
        )


# ── Built-in presets ────────────────────────────────────────────────────────

BUILTIN_TEMPLATES: list[Template] = [
    Template(
        name="standard-monthly-glofox",
        description="Standard monthly Glofox release covering Analyze + Custom clients.",
        tags=["glofox", "monthly", "standard"],
        data={
            "priority": "Medium",
            "change_type": "Normal",
            "change_risk": "Medium",
            "impact": "Moderate / Limited",
            "urgency": "Medium",
            "deploy_window_start_hour": 10,
            "deploy_window_end_hour": 13,
            "approver_groups": ["Command Center", "Insights Analyze / Customize"],
        },
    ),
    Template(
        name="emergency-hotfix",
        description="Fast-track deployment for a severe production bug.",
        tags=["emergency", "hotfix"],
        data={
            "priority": "High",
            "change_type": "Emergency",
            "change_risk": "High",
            "impact": "High",
            "urgency": "High",
            "deploy_window_start_hour": 0,
            "deploy_window_end_hour": 23,
            "approver_groups": ["Command Center"],
        },
    ),
    Template(
        name="major-feature-release",
        description="Large scope release with new dashboards / significant semantic model work.",
        tags=["major", "feature"],
        data={
            "priority": "High",
            "change_type": "Normal",
            "change_risk": "High",
            "impact": "High",
            "urgency": "Medium",
            "deploy_window_start_hour": 9,
            "deploy_window_end_hour": 15,
            "approver_groups": ["Command Center", "Insights Analyze / Customize", "Product"],
        },
    ),
    Template(
        name="custom-client-deployment",
        description="Single-tenant custom client deployment (Jetts / Lift / etc).",
        tags=["custom", "single-tenant"],
        data={
            "priority": "Medium",
            "change_type": "Normal",
            "change_risk": "Medium",
            "impact": "Moderate / Limited",
            "urgency": "Medium",
            "deploy_window_start_hour": 10,
            "deploy_window_end_hour": 12,
            "approver_groups": ["Insights Analyze / Customize"],
        },
    ),
    Template(
        name="semantic-model-refactor",
        description="Semantic model restructuring — elevated risk, long validation window.",
        tags=["semantic-model", "refactor"],
        data={
            "priority": "Medium",
            "change_type": "Normal",
            "change_risk": "High",
            "impact": "High",
            "urgency": "Low",
            "deploy_window_start_hour": 10,
            "deploy_window_end_hour": 16,
            "approver_groups": ["Command Center", "Insights Analyze / Customize"],
        },
    ),
]

_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")


def _validate_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError("Template name is required")
    if not _NAME_RE.match(name):
        raise ValueError(
            "Template name must contain only letters, digits, hyphens, and underscores."
        )
    return name


def _file_path(name: str, directory: Path | None = None) -> Path:
    d = directory or default_templates_dir()
    return d / f"{_validate_name(name)}.yaml"


def ensure_directory(directory: Path | None = None) -> Path:
    """Create and return the templates directory."""
    d = directory or default_templates_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_templates(directory: Path | None = None) -> list[Template]:
    """Return built-in templates plus any user-defined templates on disk.

    User templates override built-ins that share the same name.
    """
    directory = directory or default_templates_dir()
    templates: dict[str, Template] = {t.name: t for t in BUILTIN_TEMPLATES}
    if directory.exists():
        for f in sorted(directory.glob("*.yaml")):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
                tpl = Template.from_dict(data)
                templates[tpl.name] = tpl
            except Exception:
                logger.warning("Skipping malformed template: %s", f, exc_info=True)
    return sorted(templates.values(), key=lambda t: t.name)


def load_template(name: str, directory: Path | None = None) -> Template:
    """Load a single template by name, falling back to built-ins."""
    directory = directory or default_templates_dir()
    path = _file_path(name, directory)
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return Template.from_dict(data)
    for bt in BUILTIN_TEMPLATES:
        if bt.name == name:
            return bt
    raise KeyError(f"Template '{name}' not found")


def save_template(template: Template, directory: Path | None = None, *, overwrite: bool = True) -> Path:
    """Persist ``template`` to YAML. Returns the written path."""
    name = _validate_name(template.name)
    d = ensure_directory(directory)
    path = d / f"{name}.yaml"
    if path.exists() and not overwrite:
        raise FileExistsError(f"Template '{name}' already exists")
    path.write_text(template.to_yaml(), encoding="utf-8")
    return path


def delete_template(name: str, directory: Path | None = None) -> bool:
    """Delete a user template. Returns True if a file was removed."""
    directory = directory or default_templates_dir()
    path = _file_path(name, directory)
    if path.exists():
        path.unlink()
        return True
    return False


def capture_from_draft(
    name: str,
    draft: dict[str, Any],
    *,
    description: str = "",
    tags: Iterable[str] | None = None,
    include_keys: Iterable[str] | None = None,
) -> Template:
    """Build a :class:`Template` from a live ticket-draft dict.

    ``include_keys`` restricts which fields are captured; when not provided
    a sensible default ("shape" fields, no secrets) is used.
    """
    default_keys = {
        "priority",
        "change_type",
        "change_risk",
        "impact",
        "urgency",
        "deploy_window_start_hour",
        "deploy_window_end_hour",
        "approver_groups",
        "approvers",
        "affected_services",
        "team",
        "implementation_plan",
        "test_plan",
        "backout_plan",
        "business_impact",
    }
    keys = set(include_keys) if include_keys is not None else default_keys
    data = {k: draft[k] for k in keys if k in draft}
    return Template(name=_validate_name(name), description=description, tags=list(tags or []), data=data)


def apply_template(
    draft: dict[str, Any],
    template: Template,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Merge ``template.data`` into a copy of ``draft``.

    When ``overwrite`` is False (the default) only missing/empty fields are
    populated, preserving anything the user already filled in.
    """
    merged = dict(draft)
    for k, v in template.data.items():
        current = merged.get(k)
        is_empty = current in (None, "", [], {})
        if overwrite or is_empty:
            merged[k] = v
    return merged


__all__ = [
    "Template",
    "BUILTIN_TEMPLATES",
    "default_templates_dir",
    "ensure_directory",
    "list_templates",
    "load_template",
    "save_template",
    "delete_template",
    "capture_from_draft",
    "apply_template",
]
