"""Pre-flight onboarding checks — run before welcome onboard to catch blockers early."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from orchestrator.paths import (
    DAILY_REVIEW_OPS_DIR,
    DAILY_REVIEW_SETUP_PS1,
    ENV_FILE,
    PROJECT_MCP_CONFIG,
    REQUIREMENTS_MCP_FILE,
    REPO_ROOT,
    json_path,
    venv_python,
)
from release_mcp.mcp_installer import load_mcp_config, user_mcp_config_path
from release_mcp.mcp_templates import detect_node, detect_npx, starter_mcp_servers

_DEPRECATED_MCP_SERVERS = frozenset({"daily-review-agent", "daily_review_agent"})
_MAX_TOOL_NAME_LEN = 60
_PLAYWRIGHT_MCP_PKG = "@playwright/mcp@0.0.39"


def _check(name: str, ok: bool, detail: str, *, fix: str = "", severity: str = "required") -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "detail": detail,
        "fix": fix,
        "severity": severity,
    }


def _node_checks() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    node = detect_node()
    npx = detect_npx()
    node_ok = bool(node) and "{{" not in node and (node in {"node"} or Path(node.replace("/", os.sep)).is_file())
    npx_ok = bool(npx) and "{{" not in npx and (npx in {"npx"} or Path(npx.replace("/", os.sep)).is_file())
    rows.append(
        _check(
            "node",
            node_ok,
            node if node_ok else "Node.js not found",
            fix="Install Node LTS or set NODE_EXE to node.exe path",
        )
    )
    rows.append(
        _check(
            "npx",
            npx_ok,
            npx if npx_ok else "npx not on PATH",
            fix="Install Node npm bundle or use onboarding MCP merge (injects PATH into playwright server)",
        )
    )
    if node_ok and not npx_ok:
        sibling = Path(node.replace("/", os.sep)).parent / ("npx.cmd" if sys.platform.startswith("win") else "npx")
        if sibling.is_file():
            rows[-1] = _check("npx", True, json_path(sibling), fix="")
    return rows


def _python_checks() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    venv_py = venv_python()
    rows.append(
        _check(
            "venv",
            venv_py.is_file(),
            str(venv_py) if venv_py.is_file() else "No .venv — wizard can create it",
            fix=f"python -m venv {REPO_ROOT / '.venv'}",
        )
    )
    req_ok = REQUIREMENTS_MCP_FILE.is_file()
    rows.append(
        _check(
            "requirements-mcp",
            req_ok,
            str(REQUIREMENTS_MCP_FILE),
            fix="Restore orchestrator/zones/config/deps/requirements-mcp.txt from repo",
        )
    )
    import_ok = False
    if venv_py.is_file():
        try:
            subprocess.run(
                [str(venv_py), "-c", "import release_mcp"],
                cwd=str(REPO_ROOT),
                check=True,
                capture_output=True,
                timeout=60,
            )
            import_ok = True
        except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
            import_ok = False
    rows.append(
        _check(
            "release_mcp import",
            import_ok,
            "release_mcp importable" if import_ok else "pip install not complete",
            fix=f"{venv_py} -m pip install -r {REQUIREMENTS_MCP_FILE} && {venv_py} -m pip install -e .",
        )
    )
    return rows


def _mcp_config_checks(*, track: str = "release") -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    loaded = load_mcp_config(prefer_project=True)
    parse_err = loaded.get("parse_error")
    rows.append(
        _check(
            "mcp.json parse",
            not parse_err,
            loaded.get("path") or str(PROJECT_MCP_CONFIG),
            fix=f"Fix JSON syntax in {loaded.get('path')}",
        )
    )
    servers = loaded.get("servers") or {}
    deprecated = [k for k in servers if k in _DEPRECATED_MCP_SERVERS]
    rows.append(
        _check(
            "deprecated MCP servers",
            not deprecated,
            "none" if not deprecated else ", ".join(deprecated),
            fix="Remove daily-review-agent from mcp.json — tools live on release-orchestrator",
        )
    )
    starter = starter_mcp_servers(track=track)
    missing = [k for k in starter if k not in servers]
    rows.append(
        _check(
            "required MCP blocks",
            not missing and not parse_err,
            "all present" if not missing else f"missing: {', '.join(missing)}",
            fix="Say welcome onboard (auto-merge) or install_mcp_config MCP tool",
        )
    )
    user_path = user_mcp_config_path()
    if user_path.is_file() and PROJECT_MCP_CONFIG.is_file():
        if user_path.resolve() != PROJECT_MCP_CONFIG.resolve():
            rows.append(
                _check(
                    "dual mcp.json",
                    True,
                    f"project {PROJECT_MCP_CONFIG} and user {user_path}",
                    fix="Open repo root in Cursor so project .cursor/mcp.json wins",
                    severity="warn",
                )
            )
    pw = servers.get("playwright") if isinstance(servers.get("playwright"), dict) else {}
    pw_cmd = str(pw.get("command") or "")
    pw_env = pw.get("env") if isinstance(pw.get("env"), dict) else {}
    bare_npx = pw_cmd.lower() in {"npx", "npx.cmd"} or pw_cmd == "npx"
    rows.append(
        _check(
            "playwright MCP command",
            not bare_npx or bool(pw_env.get("PATH")),
            pw_cmd or "playwright server not configured",
            fix="Re-run install_mcp_config to rewrite playwright with absolute npx/node + PATH",
            severity="warn" if bare_npx else "required",
        )
    )
    return rows


def _long_mcp_tool_names() -> list[dict[str, Any]]:
    """Best-effort scan of registered tool names (when release_mcp is importable)."""
    rows: list[dict[str, Any]] = []
    try:
        import importlib

        import release_mcp.server as srv

        importlib.reload(srv)
        tm = getattr(srv.mcp, "_tool_manager", None) or getattr(srv.mcp, "tool_manager", None)
        if tm is None:
            rows.append(
                _check(
                    "MCP tool name length",
                    False,
                    "FastMCP tool manager not found on release_mcp.server",
                    fix="Upgrade FastMCP or adjust tool-manager introspection",
                    severity="warn",
                )
            )
            return rows
        tools = getattr(tm, "_tools", None)
        if not isinstance(tools, dict) or not tools:
            rows.append(
                _check(
                    "MCP tool name length",
                    False,
                    "No MCP tools registered (cannot verify 60-char limit)",
                    fix="Fix release_mcp.server registration before onboarding",
                    severity="warn",
                )
            )
            return rows
        names = sorted(tools.keys())
        long_names = [n for n in names if len(n) > _MAX_TOOL_NAME_LEN]
        rows.append(
            _check(
                "MCP tool name length",
                not long_names,
                f"{len(names)} tools, {len(long_names)} over {_MAX_TOOL_NAME_LEN} chars",
                fix="Shorten tool aliases (daily_review_calendar_playwright_handoff → dr_cal_handoff)",
                severity="warn",
            )
        )
    except Exception as exc:  # noqa: BLE001
        rows.append(
            _check(
                "MCP tool name length",
                True,
                f"skipped ({exc})",
                severity="warn",
            )
        )
    return rows


def run_preflight(*, track: str = "release", include_tool_scan: bool = True) -> dict[str, Any]:
    """Full preflight report. status: ready | needs_fix | blocked."""
    checks: list[dict[str, Any]] = []
    checks.extend(_python_checks())
    checks.extend(_node_checks())
    checks.extend(_mcp_config_checks(track=track))
    try:
        from release_mcp import onboarding_mcp_ping as ping

        live = ping.live_mcp_ready(require_config=False)
        checks.append(
            _check(
                "release_mcp module smoke",
                bool((live.get("ping") or {}).get("ok")),
                str((live.get("ping") or {}).get("tool_count") or live.get("ping")),
                fix="pip install -e . in repo venv",
            )
        )
    except Exception as exc:  # noqa: BLE001
        checks.append(
            _check(
                "release_mcp module smoke",
                False,
                str(exc),
                fix="Fix venv / pip install",
            )
        )
    if include_tool_scan:
        checks.extend(_long_mcp_tool_names())
    checks.append(
        _check(
            "env file",
            ENV_FILE.is_file(),
            str(ENV_FILE) if ENV_FILE.is_file() else "missing .env",
            fix=f"copy {ENV_FILE.parent / '.env.example'} to {ENV_FILE}",
            severity="warn",
        )
    )
    bridge_nm = DAILY_REVIEW_OPS_DIR / "node_modules" / "@shayanline" / "msteams-mcp"
    if track in {"daily_review", "both"}:
        checks.append(
            _check(
                "daily review npm bridge",
                bridge_nm.is_dir(),
                str(DAILY_REVIEW_OPS_DIR),
                fix=f"Run {DAILY_REVIEW_SETUP_PS1} or daily_review_setup(install=true)",
            )
        )

    required_fail = [c for c in checks if c["severity"] == "required" and not c["ok"]]
    warn_fail = [c for c in checks if c["severity"] == "warn" and not c["ok"]]
    if required_fail:
        status = "blocked"
    elif warn_fail:
        status = "needs_fix"
    else:
        status = "ready"

    return {
        "status": status,
        "track": track,
        "checks": checks,
        "required_failures": [c["name"] for c in required_fail],
        "warnings": [c["name"] for c in warn_fail],
        "playwright_mcp_package": _PLAYWRIGHT_MCP_PKG,
        "next_action": (
            "welcome onboard"
            if status == "ready"
            else required_fail[0].get("fix")
            if required_fail
            else warn_fail[0].get("fix")
        ),
    }


def apply_safe_fixes(*, track: str = "release") -> dict[str, Any]:
    """Non-destructive fixes: merge MCP blocks, strip deprecated servers from project config."""
    from release_mcp import mcp_installer

    merge = mcp_installer.merge_starter_servers(track=track, backup=True)
    report = run_preflight(track=track, include_tool_scan=False)
    return {"merge": merge, "preflight": report}


def format_preflight_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"**Onboarding preflight:** `{report.get('status')}`",
        "",
    ]
    for row in report.get("checks") or []:
        mark = "✅" if row.get("ok") else ("⚠️" if row.get("severity") == "warn" else "❌")
        lines.append(f"{mark} **{row.get('name')}** — {row.get('detail')}")
        if not row.get("ok") and row.get("fix"):
            lines.append(f"   → {row['fix']}")
    lines.extend(["", f"**Next:** {report.get('next_action')}"])
    return "\n".join(lines)
