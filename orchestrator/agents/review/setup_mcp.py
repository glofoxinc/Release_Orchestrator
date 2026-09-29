"""First-user setup — validate deps, MCP config, and generate copy-paste Cursor blocks."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from daily_review_agent.paths import DAILY_REVIEW_DIR, REPO_ROOT, SCRIPTS_DIR, script

_PROJECT_ROOT = REPO_ROOT
_AGENT_DIR = DAILY_REVIEW_DIR


def project_root() -> Path:
    return _PROJECT_ROOT


def _json_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/")


def _detect_python() -> Path | None:
    from daily_review_agent.bootstrap import orchestrator_root

    orch = orchestrator_root()
    venv_py = orch / ".venv" / "Scripts" / "python.exe"
    if venv_py.is_file():
        return venv_py
    if sys.executable and Path(sys.executable).is_file():
        return Path(sys.executable)
    return None


def _detect_node() -> Path | None:
    raw = (os.environ.get("NODE_EXE") or "").strip()
    if raw:
        p = Path(raw)
        if p.is_file():
            return p
    found = shutil.which("node")
    if found:
        return Path(found)
    for candidate in (
        Path.home() / "nodejs" / "node.exe",
        Path("C:/Program Files/nodejs/node.exe"),
    ):
        if candidate.is_file():
            return candidate
    return None


def _mcp_config_path() -> Path:
    raw = (os.environ.get("CURSOR_MCP_CONFIG") or "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".cursor" / "mcp.json"


def _teams_mcp_project() -> Path:
    raw = (os.environ.get("TEAMS_MCP_PROJECT") or "").strip()
    if raw:
        return Path(raw).resolve()
    sibling = _PROJECT_ROOT.parent / "teams-mcp"
    if sibling.is_dir():
        return sibling.resolve()
    return sibling.resolve()


def generate_mcp_snippets(*, python: Path | None = None, node: Path | None = None) -> dict[str, Any]:
    """Copy-paste blocks for ~/.cursor/mcp.json — unified Release Orchestrator + Daily Review."""
    py = python or _detect_python()
    nd = node or _detect_node()
    teams_proj = _teams_mcp_project()
    py_cmd = _json_path(py) if py else "C:/path/to/jira-release-tool/.venv/Scripts/python.exe"
    node_cmd = _json_path(nd) if nd else "C:/path/to/nodejs/node.exe"
    proj = _json_path(_PROJECT_ROOT)
    scripts_dir = _json_path(SCRIPTS_DIR)

    release_orchestrator = {
        "_description": (
            "Release Orchestrator + Daily Review — PIC/AN releases AND 6 PM daily review. "
            "Say welcome for releases; daily_review_setup for calendar path."
        ),
        "type": "stdio",
        "command": py_cmd,
        "args": ["-m", "release_mcp"],
        "cwd": proj,
        "env": {
            "TEAMS_MCP_ROOT": scripts_dir,
            "RELEASE_ORCHESTRATOR_ROOT": proj,
        },
    }

    teams = {
        "_description": (
            "Microsoft Teams MCP — group chat summary + organizer alerts. "
            "First use: teams_login in Cursor (abcfitness.com)."
        ),
        "_setup": f"Project: {teams_proj}. Run npm install once in that folder.",
        "type": "stdio",
        "command": node_cmd,
        "args": [_json_path(teams_proj / "run.mjs")],
        "cwd": _json_path(teams_proj),
        "env": {
            "LOG_LEVEL": "error",
            "PATH": os.environ.get("PATH", ""),
        },
    }

    cursor_plugins = {
        "playwright": {
            "role": (
                "Required (Glofox): SharePoint upload, Step 6 Slack (private channels), "
                "Daily Review review-call calendar (Outlook web). One-time M365 + Slack login."
            ),
            "setup": "Cursor → Settings → MCP → enable Playwright (mcp.json key: playwright)",
            "verify": "User signs in once → say playwright confirmed",
        },
        "slack": {
            "role": "Optional — public channels only; Glofox Step 6 uses Playwright, not Slack MCP",
            "setup": "Cursor → Settings → MCP → enable Slack plugin (ABC Fitness workspace)",
            "required_for_glofox": False,
        },
    }

    return {
        "mcp_config_path": _json_path(_mcp_config_path()),
        "instructions": [
            "Open mcp_config_path in a text editor (or Cursor Settings → MCP).",
            "Under mcpServers, add release-orchestrator (+ teams for Daily Review).",
            "Enable Playwright MCP (required for Glofox SharePoint + Slack Step 6). Slack plugin optional.",
            "Save, reload Cursor, then: setup status or daily_review_setup(install=true).",
            "Human guide: docs/COMPLETE_ONBOARDING.md",
        ],
        "required_servers": ["release-orchestrator", "teams"],
        "legacy_server_aliases": ["jira-release-tool"],
        "deprecated_servers": {
            "daily-review-agent": "Removed — daily review tools merged into release-orchestrator",
        },
        "cursor_plugins": cursor_plugins,
        "mcpServers": {
            "release-orchestrator": release_orchestrator,
            "teams": teams,
        },
    }


def _load_mcp_json() -> tuple[Path, dict[str, Any] | None, str | None]:
    path = _mcp_config_path()
    if not path.is_file():
        return path, None, "mcp.json not found"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return path, None, f"Invalid JSON: {exc}"
    if not isinstance(raw, dict):
        return path, None, "mcp.json root must be an object"
    servers = raw.get("mcpServers") or raw.get("servers")
    if not isinstance(servers, dict):
        return path, raw, "Missing mcpServers (or servers) object"
    return path, raw, None


def _validate_server_entry(name: str, entry: Any, *, expected: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not isinstance(entry, dict):
        return [f"{name}: entry is not an object"]
    if entry.get("disabled"):
        issues.append(f"{name}: server is disabled — enable it in mcp.json")
    if entry.get("url"):
        issues.append(f"{name}: HTTP MCP not supported for this agent — use stdio block from daily_review_mcp_config")
        return issues

    cmd = str(entry.get("command") or "").strip()
    if not cmd:
        issues.append(f"{name}: missing command")
    elif expected.get("command") and Path(cmd.replace("/", "\\")).name.lower() != Path(
        str(expected["command"]).replace("/", "\\")
    ).name.lower():
        if "python" not in cmd.lower() and "mcp" not in str(entry.get("args") or ""):
            issues.append(f"{name}: command should be jira-release-tool venv python.exe")

    args = entry.get("args") or []
    if name in {"release-orchestrator", "jira-release-tool"}:
        args_s = " ".join(str(a) for a in args)
        if "-m" not in args or not any(
            tok in args_s for tok in ("release_mcp", "mcp_server", " mcp")
        ):
            issues.append(f"{name}: args must include '-m', 'release_mcp' (or legacy 'mcp')")
        cwd = str(entry.get("cwd") or "").strip()
        if cwd and _json_path(_PROJECT_ROOT).lower() not in cwd.replace("\\", "/").lower():
            issues.append(f"{name}: cwd should point to jira-release-tool repo root")

    if name == "teams":
        args_s = " ".join(str(a) for a in args)
        if "run.mjs" not in args_s and "msteams-mcp" not in args_s:
            issues.append(f"{name}: args should point to teams-mcp/run.mjs")

    return issues


def validate_cursor_mcp_config() -> dict[str, Any]:
    path, raw, parse_error = _load_mcp_json()
    snippets = generate_mcp_snippets()
    expected = snippets["mcpServers"]
    result: dict[str, Any] = {
        "config_path": _json_path(path),
        "config_exists": path.is_file(),
        "parse_error": parse_error,
        "servers_present": {},
        "issues": [],
        "missing_servers": [],
    }

    if parse_error or raw is None:
        result["missing_servers"] = list(expected.keys())
        result["issues"].append(parse_error or "Cannot read mcp.json")
        return result

    servers = raw.get("mcpServers") or raw.get("servers") or {}
    aliases = list(snippets.get("legacy_server_aliases") or [])
    for key in expected:
        present = key in servers
        if not present and key == "release-orchestrator":
            for alias in aliases:
                if alias in servers:
                    present = True
                    key = alias
                    break
        result["servers_present"][key] = present
        if not present:
            result["missing_servers"].append(key if key != "release-orchestrator" else "release-orchestrator")
            result["issues"].append(f"Missing MCP server '{key}' in mcp.json")
        else:
            entry_key = key if key in servers else next(a for a in aliases if a in servers)
            result["issues"].extend(
                _validate_server_entry(
                    entry_key,
                    servers[entry_key],
                    expected={"command": expected.get("release-orchestrator", {}).get("command")},
                )
            )

    deprecated = snippets.get("deprecated_servers") or {}
    for name, reason in deprecated.items():
        entry = servers.get(name)
        if not isinstance(entry, dict):
            continue
        if not entry.get("disabled"):
            result["issues"].append(
                f"Deprecated MCP server '{name}' is still enabled — {reason}. Disable or remove it."
            )

    ro = servers.get("release-orchestrator")
    if isinstance(ro, dict):
        env = ro.get("env") if isinstance(ro.get("env"), dict) else {}
        if not env.get("TEAMS_MCP_ROOT"):
            result["issues"].append(
                "release-orchestrator: missing env.TEAMS_MCP_ROOT — add orchestrator/ops/daily_review path"
            )
        if not env.get("RELEASE_ORCHESTRATOR_ROOT"):
            result["issues"].append(
                "release-orchestrator: missing env.RELEASE_ORCHESTRATOR_ROOT — add repo root path"
            )

    return result


def _step(name: str, ok: bool, detail: str, fix: str = "", *, order: int) -> dict[str, Any]:
    return {"order": order, "name": name, "ok": ok, "detail": detail, "fix": fix}


def _package_ok(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def run_install_steps() -> dict[str, Any]:
    """npm install + pip install -e (same as setup.ps1 core steps)."""
    results: dict[str, Any] = {"npm": None, "pip": None, "errors": []}
    py = _detect_python()
    if not py:
        results["errors"].append("Python not found — install jira-release-tool venv first")
        return results

    npm = shutil.which("npm") or str(Path.home() / "nodejs" / "npm.cmd")
    if Path(npm).is_file() or shutil.which("npm"):
        proc = subprocess.run(
            [npm, "install"],
            cwd=SCRIPTS_DIR,
            capture_output=True,
            text=True,
            shell=(str(npm).endswith(".cmd")),
        )
        results["npm"] = {"ok": proc.returncode == 0, "returncode": proc.returncode}
        if proc.returncode != 0:
            results["errors"].append(f"npm install failed: {(proc.stderr or proc.stdout)[:300]}")
    else:
        results["errors"].append("npm not found — install Node.js or set PATH")

    proc = subprocess.run(
        [str(py), "-m", "pip", "install", "-e", ".[calendar,daily_review,dev]"],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    results["pip"] = {"ok": proc.returncode == 0, "returncode": proc.returncode}
    if proc.returncode != 0:
        results["errors"].append(f"pip install failed: {(proc.stderr or proc.stdout)[:300]}")

    teams_proj = _teams_mcp_project()
    if teams_proj.is_dir() and (shutil.which("npm") or Path(npm).is_file()):
        proc2 = subprocess.run(
            [npm, "install"],
            cwd=teams_proj,
            capture_output=True,
            text=True,
            shell=(str(npm).endswith(".cmd")),
        )
        results["teams_mcp_npm"] = {"ok": proc2.returncode == 0, "path": _json_path(teams_proj)}
        if proc2.returncode != 0:
            results["errors"].append("teams-mcp npm install failed")

    return results


def run_setup(*, install: bool = False) -> dict[str, Any]:
    """Full first-user setup report — run this before anything else in Cursor."""
    from daily_review_agent.bootstrap import bootstrap, orchestrator_root
    from daily_review_agent.config_loader import load_agent_config, readiness_report
    from daily_review_agent.onboarding import run_onboarding
    from daily_review_agent.preflight import run_preflight

    install_results = run_install_steps() if install else None

    steps: list[dict[str, Any]] = []
    order = 1

    # Orchestrator
    try:
        bootstrap(load_env=False)
        orch = orchestrator_root()
        orch_ok = orch.is_dir()
    except FileNotFoundError as exc:
        orch_ok = False
        orch = Path(str(exc))
    steps.append(
        _step(
            "Release Orchestrator (jira-release-tool)",
            orch_ok,
            f"Path: {_json_path(orch) if orch_ok else 'missing'}",
            "Clone/set RELEASE_ORCHESTRATOR_ROOT to jira-release-tool",
            order=order,
        )
    )
    order += 1

    py = _detect_python()
    steps.append(
        _step(
            "Python venv",
            bool(py and py.is_file()),
            str(py) if py else "No venv python found",
            "Create venv in jira-release-tool or run .\\scripts\\setup_e2e.ps1",
            order=order,
        )
    )
    order += 1

    steps.append(
        _step(
            "Python packages (mcp, msal, daily_review_agent)",
            _package_ok("daily_review_agent") and _package_ok("mcp") and _package_ok("msal"),
            "Editable install + MCP + calendar extras",
            "daily_review_setup(install=true) or .\\scripts\\setup_e2e.ps1",
            order=order,
        )
    )
    order += 1

    bridge = script("teams_bridge.mjs")
    node_modules = SCRIPTS_DIR / "node_modules" / "@shayanline" / "msteams-mcp"
    steps.append(
        _step(
            "Teams bridge (npm in this repo)",
            bridge.is_file() and node_modules.is_dir(),
            "teams_bridge.mjs for summary + alerts",
            "daily_review_setup(install=true)",
            order=order,
        )
    )
    order += 1

    teams_proj = _teams_mcp_project()
    teams_run = teams_proj / "run.mjs"
    teams_nm = teams_proj / "node_modules" / "@shayanline" / "msteams-mcp"
    steps.append(
        _step(
            "Teams MCP project (sibling teams-mcp/)",
            teams_run.is_file(),
            f"{_json_path(teams_proj)} — required for teams_login",
            f"Ensure teams-mcp exists; npm install in {_json_path(teams_proj)}",
            order=order,
        )
    )
    order += 1

    mcp_validation = validate_cursor_mcp_config()
    mcp_ok = (
        not mcp_validation.get("parse_error")
        and not mcp_validation.get("missing_servers")
        and not mcp_validation.get("issues")
    )
    steps.append(
        _step(
            "Cursor MCP config (release-orchestrator + teams)",
            mcp_ok,
            f"{mcp_validation.get('config_path')} — "
            + (
                "both servers registered"
                if mcp_ok
                else "; ".join(mcp_validation.get("issues") or mcp_validation.get("missing_servers") or [])[:200]
            ),
            "Call daily_review_mcp_config — copy blocks into mcp.json, reload Cursor",
            order=order,
        )
    )
    order += 1

    onboarding = run_onboarding(verbose=False)
    skip_names = {
        "Cursor MCP registered",
        "Python package",
        "Teams bridge (npm)",
    }
    for ob_step in onboarding.get("steps") or []:
        if ob_step.get("name") in skip_names:
            continue
        steps.append(
            _step(
                ob_step.get("name", "?"),
                bool(ob_step.get("ok")),
                str(ob_step.get("detail") or ""),
                str(ob_step.get("fix") or ""),
                order=order,
            )
        )
        order += 1

    cfg = load_agent_config()
    live_pf = run_preflight(cfg, dry_run=False, force=True)
    ready_live = bool(live_pf.get("ready"))

    first_run = [
        "1. daily_review_setup(install=true)  — install deps",
        "2. daily_review_mcp_config             — copy MCP blocks if step 6 failed",
        "3. Reload Cursor MCP servers",
        "4. teams_login                         — in Cursor (Teams MCP, one-time)",
        "5. daily_review_outlook_login() OR python -m daily_review_agent --outlook-login  — calendar (abcfitness.com)",
        "6. daily_review_preflight(live=true, force=true)  — must show ready: true",
        "7. daily_review_run_dry(force=true)    — preview tickets + meeting",
        "8. daily_review_run_live(force=true)   — live; verify invite on Outlook calendar",
    ]

    return {
        "phase": (
            "production_ready"
            if ready_live and mcp_ok
            else "almost_ready"
            if mcp_ok
            else "first_time_setup"
        ),
        "ready_for_dry_run": bool(onboarding.get("ready_for_dry_run")) and mcp_ok,
        "ready_for_live": ready_live and mcp_ok,
        "steps": steps,
        "mcp_validation": mcp_validation,
        "mcp_snippets": generate_mcp_snippets(),
        "install_results": install_results,
        "first_run_order": first_run,
        "next_action": (
            "daily_review_run_live(force=true)"
            if ready_live and mcp_ok
            else "daily_review_mcp_config"
            if mcp_validation.get("missing_servers")
            else "daily_review_setup(install=true)"
            if not steps[3].get("ok")
            else "teams_login then daily_review_outlook_login()"
        ),
        "preflight_live": live_pf,
        "readiness": readiness_report(cfg),
    }


def format_setup_text(report: dict[str, Any]) -> str:
    lines = [
        "Daily Review Agent — First-User Setup",
        "=====================================",
        f"Phase: {report.get('phase')}",
        f"Ready for dry-run: {report.get('ready_for_dry_run')}",
        f"Ready for live: {report.get('ready_for_live')}",
        "",
        "Checklist:",
    ]
    for step in sorted(report.get("steps") or [], key=lambda s: s.get("order", 0)):
        mark = "OK" if step.get("ok") else "!!"
        lines.append(f"  [{mark}] {step.get('name')}: {step.get('detail')}")
        if not step.get("ok") and step.get("fix"):
            lines.append(f"       Fix: {step.get('fix')}")
    lines.extend(["", "First-run order (do in sequence):", ""])
    for item in report.get("first_run_order") or []:
        lines.append(f"  {item}")
    lines.extend(["", f"Next action: {report.get('next_action')}", ""])
    mv = report.get("mcp_validation") or {}
    if mv.get("missing_servers") or mv.get("issues"):
        lines.append("MCP config: call daily_review_mcp_config for copy-paste JSON blocks.")
    return "\n".join(lines)
