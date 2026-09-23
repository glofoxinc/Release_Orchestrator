#!/usr/bin/env python3
"""Compare Release Notes DOCX against reference fixture or a second file.

Usage:
    python scripts/compare_release_notes_docx.py
    python scripts/compare_release_notes_docx.py --reference tests/fixtures/Release\\ Notes\\ 2026.3.09.09.docx \\
        --generated output/Release\\ Notes\\ 2026.3.09.09.docx
    python scripts/compare_release_notes_docx.py --generate-sample

Exit: 0 structural OK, 1 gaps, 2 bad args.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Release Notes DOCX structure.")
    parser.add_argument("--reference", default="", help="Reference .docx path.")
    parser.add_argument("--generated", default="", help="Generated .docx path.")
    parser.add_argument(
        "--generate-sample",
        action="store_true",
        help="Generate from sample data and compare to bundled reference.",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    from release_notes_compare import compare_docx_paths, compare_generated_bytes
    from tests.reference_fixture import REFERENCE_PATH

    if args.generate_sample:
        from generators.release_notes_generator import generate_release_notes_docx
        from generators.release_notes_sample import sample_release_notes_data

        data = sample_release_notes_data()
        result = compare_generated_bytes(REFERENCE_PATH, generate_release_notes_docx(data))
    else:
        ref = args.reference or REFERENCE_PATH
        gen = args.generated
        if not gen:
            print("ERROR: pass --generated or use --generate-sample", file=sys.stderr)
            return 2
        result = compare_docx_paths(ref, gen)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print("=== Release Notes DOCX Compare ===")
        print(f"Status: {result.get('status')}")
        if result.get("missing_v4_sections"):
            print("Missing v4 sections:", ", ".join(result["missing_v4_sections"]))
        print(f"Fingerprint gaps: {result.get('fingerprint_gap_count', len(result.get('fingerprint_gaps') or []))}")
        gaps = result.get("fingerprint_gaps") or []
        if gaps:
            print("Gap keys:", ", ".join(gaps[:20]))
            if len(gaps) > 20:
                print(f"  ... and {len(gaps) - 20} more")

    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
