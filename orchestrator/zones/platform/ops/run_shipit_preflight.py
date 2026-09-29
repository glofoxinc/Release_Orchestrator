#!/usr/bin/env python3
"""SHIPIT preflight CLI — metadata, assignment group, optional dry-run create.

Usage:
    python orchestrator/zones/platform/ops/run_shipit_preflight.py
    python orchestrator/zones/platform/ops/run_shipit_preflight.py --dry-run --version 2026.3.09.09 \\
        --sharepoint-url "https://tenant.sharepoint.com/.../Release.docx"

Exit: 0 pass/skip, 1 fail, 2 bad args.
"""

from __future__ import annotations

import argparse
import json
import sys

try:
    from . import _bootstrap  # noqa: F401
except ImportError:
    import _bootstrap  # noqa: F401


def main() -> int:
    parser = argparse.ArgumentParser(description="SHIPIT service desk preflight checks.")
    parser.add_argument("--assignment-only", action="store_true")
    parser.add_argument("--metadata-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Preview SHIPIT create (no write).")
    parser.add_argument("--version", default="", help="Fix version for --dry-run.")
    parser.add_argument("--sharepoint-url", default="", help="SharePoint doc URL for --dry-run.")
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    args = parser.parse_args()

    import shipit_preflight as sp

    meta = sp.preflight_service_desk_metadata()
    assign = sp.preflight_assignment_group()
    dry: dict | None = None
    if args.dry_run:
        version = (args.version or "").strip()
        url = (args.sharepoint_url or "").strip()
        if not version or not url:
            print("ERROR: --dry-run requires --version and --sharepoint-url", file=sys.stderr)
            return 2
        dry = sp.preflight_shipit_create_dry_run(version_name=version, sharepoint_url=url)

    if args.metadata_only:
        out = meta
    elif args.assignment_only:
        out = assign
    else:
        out = sp.summarize_preflight(metadata=meta, assignment=assign, dry_run=dry)

    if args.json:
        print(json.dumps(out, indent=2, default=str))
    else:
        print("=== SHIPIT Preflight ===")
        if isinstance(out, dict) and "metadata" in out:
            for label, block in (
                ("Metadata", out["metadata"]),
                ("Assignment group", out["assignment_group"]),
            ):
                print(f"  [{block.get('status', '?').upper()}] {label}: {block.get('detail', '')}")
            if out.get("dry_run"):
                dr = out["dry_run"]
                print(f"  [{dr.get('status', '?').upper()}] Dry-run create: {dr.get('summary') or dr.get('status')}")
            print(f"\nReady: {out.get('ready')}")
        else:
            print(f"  [{out.get('status', '?').upper()}] {out.get('detail', out)}")

    fail_statuses = {"fail", "error"}
    if isinstance(out, dict) and "metadata" in out:
        if out["metadata"].get("status") in fail_statuses:
            return 1
        if out["assignment_group"].get("status") in fail_statuses:
            return 1
        if out.get("dry_run") and out["dry_run"].get("status") == "error":
            return 1
        return 0
    return 1 if out.get("status") in fail_statuses else 0


if __name__ == "__main__":
    raise SystemExit(main())
