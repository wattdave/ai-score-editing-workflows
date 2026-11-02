#!/usr/bin/env python3
"""Generate the ScoreBridge.plg QueryPropTable from src/ai_score_editing/query_props.json.

query.py reads the same JSON, so the JSON is the single source of truth.
--check exits 1 if the plug-in is out of date.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
PROPS = ROOT / "src" / "ai_score_editing" / "query_props.json"
PLUGIN = ROOT / "src" / "ai_score_editing" / "sibelius" / "manuscript" / "ScoreBridge.plg"
BEGIN = "\t\t// BEGIN GENERATED from query_props.json (scripts/dev/gen_query_props.py)\n"
END = "\t\t// END GENERATED\n"


def render(data: dict) -> str:
    lines = ["\t\tcommon = CreateDictionary();\n"]
    lines += [f"\t\tcommon['{name}'] = True;\n" for name in data["common"]]
    lines.append("\t\ttypes = CreateDictionary();\n")
    for kind, names in data["types"].items():
        lines.append("\t\tprops = CreateDictionary();\n")
        lines += [f"\t\tprops['{name}'] = True;\n" for name in names]
        lines.append(f"\t\ttypes['{kind}'] = props;\n")
    return BEGIN + "".join(lines) + END


def generate(source: str, data: dict) -> str:
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(source):
        raise SystemExit("generated markers not found in ScoreBridge.plg")
    return pattern.sub(lambda _: render(data), source, count=1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the plug-in is out of date")
    args = parser.parse_args()
    data = json.loads(PROPS.read_text())
    source = PLUGIN.read_text()
    updated = generate(source, data)
    if args.check:
        if updated != source:
            print("ScoreBridge.plg QueryPropTable is out of date; run scripts/dev/gen_query_props.py", file=sys.stderr)
            return 1
        print("QueryPropTable is in sync with query_props.json.")
        return 0
    if updated != source:
        PLUGIN.write_text(updated)
        print("Updated ScoreBridge.plg QueryPropTable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
