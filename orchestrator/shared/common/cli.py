"""Shared CLI helpers — argument parsing patterns and exit codes.

Consolidates the CLI ergonomics used by the two tools so that ``--dry-run``,
``--config``, ``--json`` etc. behave identically across entry points.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

# Standard exit codes used by both tools.
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_CONFIG = 3
EXIT_NETWORK = 4
EXIT_VALIDATION = 5
EXIT_UNEXPECTED = 10


def add_common_args(parser: argparse.ArgumentParser) -> None:
    """Attach common CLI flags (``--verbose``, ``--quiet``, ``--json``)."""
    verbosity = parser.add_mutually_exclusive_group()
    verbosity.add_argument("-v", "--verbose", action="count", default=0, help="Increase log verbosity (-vv for debug).")
    verbosity.add_argument("-q", "--quiet", action="store_true", help="Log only warnings and errors.")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Emit machine-readable JSON on stdout.")
    parser.add_argument("--config", type=Path, default=None, help="Path to a YAML/JSON config file.")
    parser.add_argument("--dry-run", action="store_true", help="Simulate; do not perform remote side-effects.")


def setup_cli_logging(args: argparse.Namespace) -> None:
    """Configure root logger based on CLI flags."""
    if getattr(args, "quiet", False):
        level = logging.WARNING
    else:
        verbosity = getattr(args, "verbose", 0)
        level = [logging.INFO, logging.DEBUG][min(1, verbosity)] if verbosity else logging.INFO
    logging.basicConfig(
        level=level,
        format=os.environ.get("CLI_LOG_FORMAT", "%(levelname)s %(name)s: %(message)s"),
        stream=sys.stderr,
        force=True,
    )


def load_config_file(path: Path) -> dict[str, Any]:
    """Load YAML or JSON config. Raises :class:`FileNotFoundError` if missing."""
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yml", ".yaml"}:
        import yaml  # lazy

        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise ValueError(f"Config must be a mapping, got {type(data).__name__}")
    return data


def print_json(obj: Any, *, stream: Any | None = None) -> None:
    """Pretty-print ``obj`` as JSON to ``stream`` (stdout by default)."""
    out = stream or sys.stdout
    out.write(json.dumps(obj, indent=2, default=str, sort_keys=True))
    out.write("\n")


def build_subparsers(
    prog: str,
    description: str,
    commands: Iterable[tuple[str, str, Callable[[argparse.ArgumentParser], None], Callable[[argparse.Namespace], int]]],
) -> tuple[argparse.ArgumentParser, dict[str, Callable[[argparse.Namespace], int]]]:
    """Build a parser with subcommands from a list of ``(name, help, configure, run)`` tuples."""
    parser = argparse.ArgumentParser(prog=prog, description=description)
    add_common_args(parser)
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    handlers: dict[str, Callable[[argparse.Namespace], int]] = {}
    for name, help_text, configure, run in commands:
        sp = sub.add_parser(name, help=help_text, description=help_text)
        add_common_args(sp)
        configure(sp)
        handlers[name] = run
    return parser, handlers


def dispatch(
    parser: argparse.ArgumentParser,
    handlers: dict[str, Callable[[argparse.Namespace], int]],
    argv: list[str] | None = None,
) -> int:
    """Parse ``argv``, dispatch to the right handler, normalise exit codes."""
    args = parser.parse_args(argv)
    setup_cli_logging(args)
    handler = handlers.get(getattr(args, "command", None) or "")
    if handler is None:
        parser.error(f"Unknown command: {args.command}")
        return EXIT_USAGE
    try:
        return int(handler(args) or EXIT_OK)
    except FileNotFoundError as exc:
        logger.error("%s", exc)
        return EXIT_CONFIG
    except (ValueError, KeyError) as exc:
        logger.error("%s", exc)
        return EXIT_VALIDATION
    except Exception:
        logger.exception("unexpected error")
        return EXIT_UNEXPECTED


__all__ = [
    "EXIT_OK",
    "EXIT_USAGE",
    "EXIT_CONFIG",
    "EXIT_NETWORK",
    "EXIT_VALIDATION",
    "EXIT_UNEXPECTED",
    "add_common_args",
    "setup_cli_logging",
    "load_config_file",
    "print_json",
    "build_subparsers",
    "dispatch",
]
