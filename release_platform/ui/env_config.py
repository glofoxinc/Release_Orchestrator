"""Environment and workspace persistence helpers."""

from __future__ import annotations

import os

import config
import jira_client

_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(_APP_DIR, ".env")

__all__ = ["ENV_FILE", "persist_workspace_to_env", "save_and_reload_env"]


def save_and_reload_env(
    email: str,
    token: str,
    base_url: str | None = None,
    workspace: str | None = None,
) -> None:
    url = base_url or config.JIRA_BASE_URL
    with open(ENV_FILE, "w") as f:
        f.write(f"JIRA_BASE_URL={url}\n")
        f.write(f"JIRA_EMAIL={email}\n")
        f.write(f"JIRA_API_TOKEN={token}\n")
        if workspace is not None:
            f.write(f"JIRA_TOOLKIT_WORKSPACE={workspace}\n")
    os.environ["JIRA_EMAIL"] = email
    os.environ["JIRA_API_TOKEN"] = token
    if base_url:
        os.environ["JIRA_BASE_URL"] = base_url
    if workspace is not None:
        if workspace:
            os.environ["JIRA_TOOLKIT_WORKSPACE"] = workspace
        else:
            os.environ.pop("JIRA_TOOLKIT_WORKSPACE", None)
    config.load_env_once()
    config.ensure_workspace_loaded(force=True)
    jira_client.reset_client()


def persist_workspace_to_env(workspace: str) -> None:
    """Write the active workspace to .env, preserving existing credentials."""
    lines: list[str] = []
    found = False
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("JIRA_TOOLKIT_WORKSPACE="):
                    found = True
                    lines.append(f"JIRA_TOOLKIT_WORKSPACE={workspace}\n")
                else:
                    lines.append(line)
    if not found:
        lines.append(f"JIRA_TOOLKIT_WORKSPACE={workspace}\n")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.writelines(lines)
    os.environ["JIRA_TOOLKIT_WORKSPACE"] = workspace
    config.ensure_workspace_loaded(force=True)
