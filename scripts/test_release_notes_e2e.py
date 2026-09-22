"""End-to-end Release Notes pipeline test (sample data → readiness → DOCX).

Usage
-----
    python scripts/test_release_notes_e2e.py
    python scripts/test_release_notes_e2e.py --status
    python scripts/test_release_notes_e2e.py --write ./Release Notes sample.docx
    python scripts/test_release_notes_e2e.py --live --version 2026.3.08.21

Exit codes: 0 OK, 1 failure, 2 bad args.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Release Notes E2E — readiness + publish + parity smoke.")
    parser.add_argument("--status", action="store_true", help="Pipeline status only (fixture path).")
    parser.add_argument("--write", default="", help="Write generated DOCX to this path.")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Fetch real Jira tickets for --version and generate DOCX via MCP release_ops.",
    )
    parser.add_argument("--version", default="", help="Fix version for --live (e.g. 2026.3.08.21).")
    parser.add_argument(
        "--skip-readiness",
        action="store_true",
        help="Generate even when readiness blockers exist (not recommended).",
    )
    args = parser.parse_args()

    if args.live:
        version = (args.version or "").strip()
        if not version:
            print("ERROR: --live requires --version", file=sys.stderr)
            return 2
        import config
        from release_mcp import release_ops

        config.reload_workspace()
        print("=== Release Notes LIVE E2E ===")
        out = release_ops.generate_release_notes_docx_file(
            version,
            enforce_readiness=not args.skip_readiness,
        )
        print(json.dumps({k: v for k, v in out.items() if k != "readiness"}, indent=2))
        if out.get("readiness"):
            print("\nReadiness:")
            print(json.dumps(out["readiness"], indent=2))
        return 0 if out.get("status") == "ok" else 1

    from generators.release_notes_e2e import e2e_status, run_fixture_e2e

    if args.status:
        print(json.dumps(e2e_status(), indent=2))
        return 0 if e2e_status().get("ok") else 1

    print("=== Release Notes E2E (fixture) ===")
    result = run_fixture_e2e(
        enforce_readiness=not args.skip_readiness,
        write_path=args.write.strip(),
    )
    print(json.dumps({k: v for k, v in result.items() if k != "platform_features"}, indent=2))
    if result.get("ok"):
        print("\nOK — Release Notes E2E passed on sample data.")
        if result.get("written_path"):
            print(f"Wrote: {result['written_path']}")
        return 0
    print("\nFAILED — see readiness/publish above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
