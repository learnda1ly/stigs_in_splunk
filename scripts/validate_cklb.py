#!/usr/bin/env python3
"""Check downloaded CKLB files against the STIG Viewer shape.

Usage:
  ./scripts/validate_cklb.py ~/Downloads/*.cklb
  ./scripts/validate_cklb.py --strict New\\ Checklist.cklb
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "package" / "bin"))

from cklb_validate import format_result, validate_paths  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate CKLB files for STIG Viewer shape")
    parser.add_argument("files", nargs="+", help="One or more .cklb files")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Also require srg_id and reference_identifier on every rule",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable results")
    parser.add_argument("--verbose", action="store_true", help="Print every error and warning")
    args = parser.parse_args(argv)

    results = validate_paths(args.files, strict=args.strict)
    if args.json:
        payload = [
            {
                "path": r.path,
                "ok": r.ok,
                "rule_count": r.rule_count,
                "errors": r.errors,
                "warnings": r.warnings,
            }
            for r in results
        ]
        print(json.dumps(payload, indent=2))
    else:
        print("\n".join(format_result(r, verbose=args.verbose) for r in results))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
