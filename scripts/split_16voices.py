#!/usr/bin/env python3
"""CLI utility to demix 12-staff polychoral scores into 16 discrete vocal staves."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sibelius_websocket_cli.polychoral import demix_16voices, validate_16voices


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Demix a polychoral score into 16 discrete vocal staves."
    )
    parser.add_argument("input", help="Path to input MusicXML (.xml or .mxl)")
    parser.add_argument(
        "-o",
        "--output",
        required=True,
        help="Path to output 16-voice MusicXML (.xml or .mxl)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate measure durations without modifying",
    )

    args = parser.parse_args(argv)

    if args.validate_only:
        issues = validate_16voices(args.input)
        if issues:
            print(f"Validation failed with {len(issues)} issues:", file=sys.stderr)
            for issue in issues[:20]:
                print(f"  - {issue}", file=sys.stderr)
            return 1
        print("Validation succeeded: 0 issues found.")
        return 0

    print(f"Demixing {args.input} into 16 discrete voices...")
    res = demix_16voices(args.input, args.output)
    print(f"Demixed {res['totalMeasures']} measures across {res['partsCount']} parts.")
    print(f"Saved to: {res['outputFile']}")

    print("Validating generated score...")
    issues = validate_16voices(args.output)
    if issues:
        print(f"Warning: {len(issues)} validation issues detected:", file=sys.stderr)
        for issue in issues[:10]:
            print(f"  - {issue}", file=sys.stderr)
        return 1

    print("Validation passed: 0 duration discrepancies found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
