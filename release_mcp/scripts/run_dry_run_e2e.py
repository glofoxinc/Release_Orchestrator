"""Drive guided test-shipit dry-run E2E against live Jira (operator review)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from release_mcp.guided import run_guided  # noqa: E402


def step(label: str, message: str, *, workflow_id: str | None = None) -> dict:
    print(f"\n{'=' * 60}\nSTEP: {label}\nSAY: {message!r}\n{'=' * 60}")
    body = run_guided(message, workflow_id=workflow_id)
    wid = body.get("workflow_id") or workflow_id
    print(f"status={body.get('status')} step={body.get('step')} workflow_id={wid}")
    prompt = str(body.get("prompt") or body.get("say_to_user") or "")[:1400]
    if prompt:
        print(f"prompt:\n{prompt}")
    if body.get("error"):
        print(f"ERROR: {body.get('error')}")
    return body


def main() -> int:
    wid: str | None = None
    sharepoint_url = (
        "https://abcfitness.sharepoint.com/sites/GlofoxCustomizeBI/"
        "Shared%20Documents/Release%20Notes/Release%20Notes%202026.3.09.23.docx"
    )

    chain = [
        ("1 fetch review tickets", "fetch review tickets"),
        ("2 confirm lock", "yes"),
        ("3 include release-ready overrides", "include PIC-6085 PIC-6016 PIC-6058 for release notes"),
        ("4 test shipit mode", "test shipit"),
        ("5 confirm release date", "yes"),
        ("6 confirm release notes list", "yes"),
        ("7 sharepoint done", f"sharepoint done {sharepoint_url}"),
        ("8 create shipit preflight", "create shipit"),
        ("9 confirm shipit create", "yes"),
        ("10 slack done", "slack done"),
    ]

    last_step = ""
    for label, message in chain:
        body = step(label, message, workflow_id=wid)
        wid = str(body.get("workflow_id") or wid or "")
        last_step = str(body.get("step") or last_step)
        status = str(body.get("status") or "")
        if status in {"error", "blocked"}:
            print("\nDRY-RUN STOPPED — fix blocker above.", file=sys.stderr)
            print(json.dumps({k: body.get(k) for k in ("status", "step", "error", "missing")}, indent=2))
            return 1
        if body.get("step") == "complete":
            break

    print(f"\nDRY-RUN FINISHED at step={last_step} workflow_id={wid}")
    preview = body.get("preview") or {}
    if preview.get("service_ticket") or preview.get("preflight"):
        print("shipit preview keys:", list(preview.keys())[:12])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
