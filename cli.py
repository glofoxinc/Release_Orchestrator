"""Headless CLI for ``jira-release-tool``.

Provides three commands:

* ``create`` — build a TCKT from a YAML config (supports ``--dry-run``).
* ``validate-config`` — syntactic + semantic validation of a config file.
* ``list-recent`` — show recently-created TCKTs from local history.

Run ``python -m cli --help`` for full usage.
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from common import cli as shared_cli

logger = logging.getLogger(__name__)


# ── Config schema & validation ──────────────────────────────────────────────

REQUIRED_CONFIG_KEYS = (
    "releases",           # list of release-version strings
    "workspace",          # workspace.yaml identifier
)
OPTIONAL_CONFIG_KEYS = (
    "summary",
    "priority",
    "approvers",
    "approver_groups",
    "team",
    "affected_services",
    "change_type",
    "change_risk",
    "impact",
    "urgency",
    "planned_start",
    "planned_end",
    "template",
    "notify",
)


@dataclass
class ConfigValidation:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "errors": list(self.errors), "warnings": list(self.warnings)}


def _normalize_release_values(releases: list[Any]) -> tuple[list[str], list[str]]:
    """Return ``(normalized_releases, duplicate_values)`` preserving order."""
    normalized: list[str] = []
    duplicates: list[str] = []
    seen: set[str] = set()
    for item in releases:
        value = str(item or "").strip()
        if not value:
            continue
        if value in seen:
            if value not in duplicates:
                duplicates.append(value)
            continue
        seen.add(value)
        normalized.append(value)
    return normalized, duplicates


def _parse_isoish_datetime(value: str) -> datetime | None:
    """Parse Jira-style datetime values, returning ``None`` if invalid."""
    text = (value or "").strip()
    if not text:
        return None
    candidates = [text]
    # Accept offsets written as ``-0500`` by normalizing to ``-05:00``.
    if len(text) >= 5 and text[-5] in {"+", "-"} and text[-3] != ":":
        candidates.append(f"{text[:-2]}:{text[-2:]}")
    if text.endswith("Z"):
        candidates.append(text[:-1] + "+00:00")
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    return None


def validate_config(data: dict[str, Any]) -> ConfigValidation:
    """Check the shape of a CLI release-config dict."""
    v = ConfigValidation()
    if not isinstance(data, dict):
        v.fail("config must be a mapping")
        return v

    for key in REQUIRED_CONFIG_KEYS:
        if key not in data or data[key] in (None, "", []):
            v.fail(f"missing required key: {key}")

    workspace = data.get("workspace")
    if "workspace" in data and (not isinstance(workspace, str) or not workspace.strip()):
        v.fail("'workspace' must be a non-empty string")

    if "releases" in data and not isinstance(data["releases"], list):
        v.fail("'releases' must be a list of version strings")
    elif "releases" in data and data["releases"]:
        if not all(isinstance(r, str) for r in data["releases"]):
            v.fail("'releases' entries must be strings")
        normalized_releases, duplicates = _normalize_release_values(data["releases"])
        if not normalized_releases:
            v.fail("'releases' must contain at least one non-empty value")
        for duplicate in duplicates:
            v.warn(f"duplicate release ignored: {duplicate}")

    if "approvers" in data and not isinstance(data["approvers"], list):
        v.fail("'approvers' must be a list")
    if "approver_groups" in data and not isinstance(data["approver_groups"], list):
        v.fail("'approver_groups' must be a list")

    unknown = set(data.keys()) - set(REQUIRED_CONFIG_KEYS) - set(OPTIONAL_CONFIG_KEYS)
    for key in sorted(unknown):
        v.warn(f"unknown config key: {key}")

    if data.get("priority") and data["priority"] not in {"Low", "Medium", "High", "Highest"}:
        v.warn(f"unusual priority value: {data['priority']}")

    planned_start_raw = str(data.get("planned_start") or "").strip()
    planned_end_raw = str(data.get("planned_end") or "").strip()
    planned_start = None
    planned_end = None
    if planned_start_raw:
        planned_start = _parse_isoish_datetime(planned_start_raw)
        if planned_start is None:
            v.fail("'planned_start' must be an ISO 8601 datetime")
    if planned_end_raw:
        planned_end = _parse_isoish_datetime(planned_end_raw)
        if planned_end is None:
            v.fail("'planned_end' must be an ISO 8601 datetime")
    if planned_start and planned_end and planned_end <= planned_start:
        v.fail("'planned_end' must be after 'planned_start'")
    return v


# ── Hook points (injected for tests) ────────────────────────────────────────

@dataclass
class CliDeps:
    """Callables the CLI needs to perform side-effects.

    Injected from ``__main__`` to the real Jira client in production, and
    replaced with fakes during unit tests.
    """

    create_ticket: Callable[[dict[str, Any]], dict[str, Any]] = field(
        default=lambda payload: {"key": "DRY-RUN", "dry_run": True}
    )
    list_recent: Callable[[int], list[dict[str, Any]]] = field(
        default=lambda limit: []
    )


# ── Subcommand: validate-config ─────────────────────────────────────────────

def _configure_validate(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("config_path", type=Path, help="Path to the config file to validate.")


def _run_validate(args: argparse.Namespace, deps: CliDeps) -> int:
    data = shared_cli.load_config_file(args.config_path)
    v = validate_config(data)
    if args.json_output:
        shared_cli.print_json(v.to_dict())
    else:
        for err in v.errors:
            print(f"ERROR: {err}", file=sys.stderr)
        for w in v.warnings:
            print(f"WARN: {w}", file=sys.stderr)
        print("OK" if v.ok else "FAILED")
    return shared_cli.EXIT_OK if v.ok else shared_cli.EXIT_VALIDATION


# ── Subcommand: create ──────────────────────────────────────────────────────

def _configure_create(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--force", action="store_true", help="Skip validation warnings.")


def build_ticket_payload(config: dict[str, Any]) -> dict[str, Any]:
    """Translate a CLI config into a Jira create-issue payload shell."""
    releases, _ = _normalize_release_values(list(config.get("releases") or []))
    summary = config.get("summary") or (
        f"Production Deployment – {', '.join(releases)}" if releases else "Production Deployment"
    )
    return {
        "summary": summary,
        "releases": list(releases),
        "priority": config.get("priority", "Medium"),
        "approvers": list(config.get("approvers") or []),
        "approver_groups": list(config.get("approver_groups") or []),
        "team": config.get("team", ""),
        "affected_services": list(config.get("affected_services") or []),
        "change_type": config.get("change_type", "Normal"),
        "change_risk": config.get("change_risk", "Medium"),
        "impact": config.get("impact", "Moderate / Limited"),
        "urgency": config.get("urgency", "Medium"),
        "planned_start": config.get("planned_start", ""),
        "planned_end": config.get("planned_end", ""),
        "workspace": config.get("workspace", ""),
    }


def _run_create(args: argparse.Namespace, deps: CliDeps) -> int:
    if not args.config:
        print("ERROR: --config is required for 'create'", file=sys.stderr)
        return shared_cli.EXIT_USAGE
    data = shared_cli.load_config_file(args.config)
    v = validate_config(data)
    if not v.ok:
        for err in v.errors:
            print(f"ERROR: {err}", file=sys.stderr)
        return shared_cli.EXIT_VALIDATION
    if v.warnings and not args.force:
        for w in v.warnings:
            print(f"WARN: {w}", file=sys.stderr)
    payload = build_ticket_payload(data)
    if args.dry_run:
        result = {"dry_run": True, "payload": payload}
    else:
        try:
            result = deps.create_ticket(payload)
        except Exception as exc:
            print(f"ERROR: failed to create ticket: {exc}", file=sys.stderr)
            return shared_cli.EXIT_NETWORK
    if args.json_output:
        shared_cli.print_json(result)
    else:
        if args.dry_run:
            print(f"[dry-run] Would create TCKT with summary: {payload['summary']}")
        else:
            print(f"Created: {result.get('key', '(no key)')}")
    return shared_cli.EXIT_OK


# ── Subcommand: list-recent ─────────────────────────────────────────────────

def _configure_list_recent(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--limit", type=int, default=10, help="Max records to return.")


def _run_list_recent(args: argparse.Namespace, deps: CliDeps) -> int:
    if args.limit < 1:
        print("ERROR: --limit must be >= 1", file=sys.stderr)
        return shared_cli.EXIT_VALIDATION
    try:
        records = deps.list_recent(args.limit)
    except Exception as exc:
        print(f"ERROR: failed to list recent tickets: {exc}", file=sys.stderr)
        return shared_cli.EXIT_NETWORK
    if args.json_output:
        shared_cli.print_json(records)
    else:
        for rec in records:
            print(f"{rec.get('key', '?'):12} {rec.get('created', ''):20} {rec.get('summary', '')[:80]}")
    return shared_cli.EXIT_OK


# ── Entry point ─────────────────────────────────────────────────────────────

def build_parser(deps: CliDeps | None = None) -> argparse.ArgumentParser:
    d = deps or CliDeps()

    def wrap(run):
        return lambda args: run(args, d)

    parser, handlers = shared_cli.build_subparsers(
        "jira-release-tool",
        "Headless CLI for creating TCKT deployment tickets.",
        [
            ("create", "Create a TCKT from a config file", _configure_create, wrap(_run_create)),
            ("validate-config", "Validate a CLI config file", _configure_validate, wrap(_run_validate)),
            ("list-recent", "List recently-created TCKTs", _configure_list_recent, wrap(_run_list_recent)),
        ],
    )
    parser._jrt_handlers = handlers  # type: ignore[attr-defined]
    return parser


def main(argv: list[str] | None = None, deps: CliDeps | None = None) -> int:
    parser = build_parser(deps)
    handlers = getattr(parser, "_jrt_handlers", {})
    return shared_cli.dispatch(parser, handlers, argv)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "CliDeps",
    "ConfigValidation",
    "REQUIRED_CONFIG_KEYS",
    "OPTIONAL_CONFIG_KEYS",
    "build_parser",
    "build_ticket_payload",
    "main",
    "validate_config",
]
