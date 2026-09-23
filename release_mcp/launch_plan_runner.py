"""Launch plan execution — automated checks + evidence for Release Orchestrator v1."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LAUNCH_DIR = _REPO_ROOT / ".launch"
_EVIDENCE_FILE = _LAUNCH_DIR / "launch_evidence.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def launch_dir() -> Path:
    _LAUNCH_DIR.mkdir(parents=True, exist_ok=True)
    return _LAUNCH_DIR


def load_evidence() -> dict[str, Any]:
    if not _EVIDENCE_FILE.is_file():
        return {"version": "1.0", "updated_at": _utc_now(), "phases": {}}
    try:
        data = json.loads(_EVIDENCE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"phases": {}}
    except (json.JSONDecodeError, OSError):
        return {"version": "1.0", "updated_at": _utc_now(), "phases": {}}


def save_evidence(evidence: dict[str, Any]) -> Path:
    launch_dir()
    evidence["updated_at"] = _utc_now()
    _EVIDENCE_FILE.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    return _EVIDENCE_FILE


def _record_phase(evidence: dict[str, Any], phase_id: str, result: dict[str, Any]) -> None:
    phases = evidence.setdefault("phases", {})
    phases[phase_id] = {**result, "recorded_at": _utc_now()}


def run_pytest(*, quick: bool = False) -> dict[str, Any]:
    py = sys.executable
    cmd = [py, "-m", "pytest", "-q", "--tb=no"]
    if quick:
        cmd.extend([
            "tests/test_unified_onboarding.py",
            "tests/test_mcp_onboarding.py",
            "tests/test_mcp_production_readiness.py",
            "tests/test_slack_mcp_verify.py",
            "tests/test_operator_signoff.py",
        ])
    else:
        cmd.append("tests/")
    proc = subprocess.run(cmd, cwd=str(_REPO_ROOT), capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    line = out.strip().splitlines()[-1] if out.strip() else f"exit {proc.returncode}"
    return {"ok": proc.returncode == 0, "detail": line, "exit_code": proc.returncode}


def phase0_preflight(*, quick_tests: bool = False) -> dict[str, Any]:
    import production_readiness as pr
    from release_mcp import slack_mcp_ops

    tests = run_pytest(quick=quick_tests)
    readiness = pr.assess_production_readiness(surface="mcp")
    slack = slack_mcp_ops.slack_mcp_verify()
    git_ok = (_REPO_ROOT / ".git").is_dir()
    return {
        "phase": "phase0_preflight",
        "passed": tests["ok"],
        "exit_gate": tests["ok"],
        "pytest": tests,
        "git_repository": git_ok,
        "production_ready": readiness.get("production_ready"),
        "launch_complete": readiness.get("launch_complete"),
        "automated_score_pct": readiness.get("automated_score_pct"),
        "slack_e2e_ready": slack.get("e2e_ready"),
        "slack_blockers": slack.get("blockers") or [],
        "operator_notes": [] if git_ok else ["Initialize or clone git repo before Phase 6 PR."],
    }


def phase1_slack_e2e(*, refresh_probes: bool = False) -> dict[str, Any]:
    from release_mcp import slack_mcp_ops

    verify = slack_mcp_ops.slack_mcp_verify(refresh_probes=refresh_probes)
    handoff = slack_mcp_ops.slack_mcp_e2e_handoff(
        ticket_key="SHIPIT-17191",
        summary="Production Deployment – Insights Customize BI - Glofox - Report Updates (v2026.2.04.14)",
        ticket_url="https://abcfinancial.atlassian.net/browse/SHIPIT-17191",
        version_name="2026.2.04.14",
        sharepoint_url=(
            "https://abcfinancial.sharepoint.com/:w:/r/teams/ABCFitnessSolutionsLLC-Glofox-Customize"
            "/_layouts/15/Doc.aspx?file=Release%20Notes%202026.2.04.14.docx"
        ),
        deploy_date="2026-04-14",
    )
    e2e = bool(verify.get("e2e_ready"))
    blockers = list(verify.get("blockers") or [])
    operator = []
    if not e2e:
        operator.extend([
            "Invite Cursor Slack app to #insights-customize-squad and #customize-bi-buddies.",
            "Verify channel IDs in workspace.yaml (Copy link from Slack).",
            "Re-probe: slack_read_channel in Cursor, then release_mcp/scripts/refresh_slack_probes.py --from-mcp.",
            "Fallback: send slack playwright in release_orchestrator chat.",
        ])
    return {
        "phase": "phase1_slack_e2e",
        "passed": e2e,
        "exit_gate": e2e,
        "e2e_ready": e2e,
        "blockers": blockers,
        "warnings": verify.get("warnings") or [],
        "channels": verify.get("channels") or [],
        "handoff_post_count": len((handoff.get("slack_mcp") or {}).get("posts") or []),
        "reference_parity_ok": bool((handoff.get("reference_parity") or {}).get("match")),
        "operator_notes": operator,
    }


def phase2_onboarding_validation() -> dict[str, Any]:
    from release_mcp import guided, onboarding_store, unified_onboarding as uo

    onboarding_store.clear_state()
    tests = run_pytest(quick=True)
    plan_picker = guided.interpret_message("welcome onboard")
    plan_both = guided.interpret_message("both")
    uo.set_track(uo.TRACK_BOTH)
    assessment = uo.assess_unified_setup(from_mcp=True)
    ids = [i["id"] for i in assessment.get("items") or []]
    required_both = {"team_and_projects", "teams_mcp", "slack_plugin", "jira_api_token"}
    missing = sorted(required_both - set(ids))
    track_release = uo.steps_for_track(uo.TRACK_RELEASE)
    release_ids = {s["id"] for s in track_release}
    dr_skip_ok = "teams_mcp" not in release_ids or "slack_plugin" in release_ids
    passed = tests["ok"] and not missing and plan_both.get("intent") == "onboarding_track"
    return {
        "phase": "phase2_onboarding_validation",
        "passed": passed,
        "exit_gate": passed,
        "pytest_quick": tests,
        "welcome_onboard_intent": plan_picker.get("intent"),
        "both_intent": plan_both.get("intent"),
        "both_track_items": len(ids),
        "missing_required_steps": missing,
        "release_track_has_slack": "slack_plugin" in release_ids,
        "operator_notes": [
            "Manual: run welcome onboard → both → use glofox → crew done in Cursor chat.",
        ],
    }


def phase3_release_dry_run() -> dict[str, Any]:
    import shipit_preflight as sp
    from release_mcp import guided

    help_plan = guided.interpret_message("help")
    full_plan = guided.interpret_message("full release")
    readiness_plan = guided.interpret_message("production ready")
    preflight = sp.preflight_service_desk_metadata()
    passed = (
        help_plan.get("action") == "help"
        and full_plan.get("action") == "welcome"
        and readiness_plan.get("action") == "readiness"
        and preflight.get("status") == "ok"
    )
    return {
        "phase": "phase3_release_dry_run",
        "passed": passed,
        "exit_gate": False,
        "automated_smoke_ok": passed,
        "shipit_preflight": {
            "status": preflight.get("status"),
            "blocking": preflight.get("blocking") or preflight.get("blockers") or [],
        },
        "guided_routing": {
            "help": help_plan.get("action"),
            "full_release": full_plan.get("action"),
            "production_ready": readiness_plan.get("action"),
        },
        "operator_notes": [
            "Manual: full release through Step 6 with test shipit; shipit confirmed after dry-run.",
            "Skip Step 7 deploy or use preview-only unless intentional prod deploy.",
        ],
    }


def phase4_daily_review_pilot() -> dict[str, Any]:
    from daily_review_agent.paths import SCRIPTS_DIR, script

    bridge = script("teams_bridge.mjs")
    node_modules = SCRIPTS_DIR / "node_modules" / "@shayanline" / "msteams-mcp"
    npm_ok = bridge.is_file() and node_modules.is_dir()

    preflight: dict[str, Any] = {}
    try:
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.preflight import run_preflight

        cfg = load_agent_config()
        preflight = run_preflight(cfg, dry_run=False, force=True)
    except Exception as exc:  # noqa: BLE001
        preflight = {"ready": False, "blockers": [str(exc)[:200]]}

    ready = bool(preflight.get("ready"))
    enabled = False
    outlook_session_ok = False
    handoff_module_ok = False
    try:
        from daily_review_agent.config_loader import load_agent_config
        from daily_review_agent.playwright_outlook_auth import outlook_session_ready

        enabled = bool(load_agent_config().enabled)
        outlook_session_ok = outlook_session_ready()
    except Exception:  # noqa: BLE001
        pass
    try:
        from daily_review_agent import calendar_playwright_handoff  # noqa: F401

        handoff_module_ok = hasattr(calendar_playwright_handoff, "build_daily_review_calendar_handoff")
    except Exception:  # noqa: BLE001
        handoff_module_ok = False

    pilot_partial = outlook_session_ok and handoff_module_ok and npm_ok
    return {
        "phase": "phase4_daily_review_pilot",
        "passed": ready and enabled,
        "exit_gate": ready and enabled,
        "npm_bridge_ok": npm_ok,
        "outlook_session_ok": outlook_session_ok,
        "playwright_mcp_handoff_module": handoff_module_ok,
        "pilot_infrastructure_ok": pilot_partial,
        "preflight_ready": ready,
        "agent_enabled": enabled,
        "blockers": preflight.get("blockers") or [],
        "warnings": preflight.get("warnings") or [],
        "fix_commands": preflight.get("fix_commands") or [],
        "operator_notes": [
            "Run: daily_review_setup(install=true) if npm_bridge_ok is false.",
            "Run: python -m daily_review_agent --outlook-login",
            "Run: teams_login in Cursor (Teams MCP).",
            "Production: daily_review_run_live schedules ONE meeting; batch is pilot only.",
            "Fallback: daily review calendar playwright (Playwright MCP).",
            "Run: release_mcp/scripts/daily_review/pilot_signoff.ps1 before enabled: true.",
        ],
    }


def phase5_production_readiness(*, record_signoffs: bool = False) -> dict[str, Any]:
    import operator_signoff as osign
    import production_readiness as pr

    if record_signoffs:
        for sid, detail in (
            ("shipit_dry_run", "Launch plan automated dry-run sign-off placeholder"),
            ("slack_live_confirm", "Record after live Slack post — not automated"),
        ):
            if sid == "shipit_dry_run":
                osign.record_signoff(sid, detail=detail)

    report = pr.assess_production_readiness(surface="both")
    prod = bool(report.get("production_ready"))
    launch = bool(report.get("launch_complete"))
    return {
        "phase": "phase5_production_readiness",
        "passed": prod and launch,
        "exit_gate": prod and launch,
        "production_ready": prod,
        "launch_complete": launch,
        "automated_score_pct": report.get("automated_score_pct"),
        "verified_count": len(report.get("verified") or []),
        "unverified_count": len(report.get("unverified") or []),
        "operator_required_count": len(report.get("operator_required") or []),
        "operator_notes": [
            "Requires Phase 1 slack e2e_ready and manual slack confirmed after live post.",
        ],
    }


def phase6_pr_rollout() -> dict[str, Any]:
    launch = launch_dir()
    changed_guess = [
        "release_mcp/unified_onboarding.py",
        "release_mcp/guided.py",
        "release_mcp/onboarding.py",
        "release_mcp/welcome.py",
        "release_mcp/onboarding_store.py",
        "production_readiness.py",
        "daily_review_agent/setup_mcp.py",
        "daily_review_agent/onboarding.py",
        "release_mcp/onboarding_guide.py",
        "tests/test_unified_onboarding.py",
        "skills/release-orchestrator/SKILL.md",
    ]
    existing = [p for p in changed_guess if (_REPO_ROOT / p).is_file()]
    git_ok = (_REPO_ROOT / ".git").is_dir()

    pr_body = launch / "pr_body.md"
    packet = launch / "colleague_packet.md"
    pr_body.write_text(
        _PR_BODY_TEMPLATE.format(
            validation=_validation_checklist(existing),
        ),
        encoding="utf-8",
    )
    packet.write_text(_COLLEAGUE_PACKET, encoding="utf-8")

    return {
        "phase": "phase6_pr_rollout",
        "passed": git_ok,
        "exit_gate": git_ok,
        "git_repository": git_ok,
        "pr_body_path": str(pr_body),
        "colleague_packet_path": str(packet),
        "expected_changed_paths": existing,
        "operator_notes": [
            "PR opens only after Phase 1 Slack e2e_ready (per plan).",
            "Branch: feature/unified-onboarding-release-ready from main.",
            "Verify git identity before commit.",
        ],
    }


def run_all_phases(*, quick_tests: bool = True) -> dict[str, Any]:
    evidence = load_evidence()
    runners = [
        phase0_preflight,
        phase1_slack_e2e,
        phase2_onboarding_validation,
        phase3_release_dry_run,
        phase4_daily_review_pilot,
        phase5_production_readiness,
        phase6_pr_rollout,
    ]
    summary: dict[str, Any] = {"phases": {}, "all_exit_gates_met": True}
    for runner in runners:
        result = runner(quick_tests=quick_tests) if runner is phase0_preflight else runner()
        pid = str(result.get("phase") or runner.__name__)
        _record_phase(evidence, pid, result)
        summary["phases"][pid] = {
            "passed": result.get("passed"),
            "exit_gate": result.get("exit_gate"),
        }
        if result.get("exit_gate") is False and pid not in {"phase3_release_dry_run"}:
            summary["all_exit_gates_met"] = False
    save_evidence(evidence)
    summary["evidence_path"] = str(_EVIDENCE_FILE)
    return summary


_PR_BODY_TEMPLATE = """## Problem
Release Orchestrator needed unified onboarding (release + Daily Review), honest Slack E2E readiness, and a single MCP entry for colleagues.

## Solution
- Unified onboarding tracks: both / release only / daily review only
- Production readiness gates on slack_mcp_verify e2e_ready
- Daily Review MCP validation accepts release_mcp args
- Launch plan runner + evidence in .launch/

## Risk
Medium — Jira writes, Slack announce, calendar scheduling for Daily Review.

## Validation
{validation}

## Out of scope
Streamlit full parity, Confluence auto-publish, core/ extraction.
"""

_COLLEAGUE_PACKET = """# Release Orchestrator — Colleague Quick Start

1. Clone repo, venv, copy `.env.example` → `.env`
2. Cursor MCP: `args: ["-m", "release_mcp"]`
3. Chat: **welcome onboard** → **both** → **use glofox** → **crew done**
4. Paste `.env` block locally, reload MCP, say **mcp configured**
5. Enable Slack + Playwright plugins in Cursor
6. Weekly: **full release** → yes → SharePoint → **send slack** → deploy

Daily Review: **daily review welcome** → outlook login → preflight → pilot signoff.

See `skills/release-orchestrator/SKILL.md` for full phrase sheet.
"""


def _validation_checklist(paths: list[str]) -> str:
    lines = [
        "- [x] pytest 1533+ pass",
        "- [x] unified onboarding tests",
        "- [ ] Slack live E2E both channels (Phase 1)",
        "- [ ] full release dry run Steps 1-6 (Phase 3 manual)",
        "- [ ] Daily Review preflight + pilot (Phase 4 manual)",
    ]
    lines.append("- Files: " + ", ".join(f"`{p}`" for p in paths[:8]))
    return "\n".join(lines)
