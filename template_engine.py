"""Jinja2 template engine with workspace-level overrides."""

from __future__ import annotations

import os
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DIR = os.path.join(_APP_DIR, "templates", "default")
_OVERRIDE_DIR = os.path.join(_APP_DIR, "templates")


def _get_env() -> Environment:
    """Build a Jinja2 environment that checks workspace templates first, then defaults."""
    search_paths = [_OVERRIDE_DIR, _DEFAULT_DIR]
    return Environment(
        loader=FileSystemLoader(search_paths),
        autoescape=select_autoescape([]),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_template(name: str, **ctx: Any) -> str:
    """Render a named template with the given context variables."""
    env = _get_env()
    tmpl = env.get_template(name)
    return tmpl.render(**ctx)
