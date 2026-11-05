"""List the ficta marks in a MusicXML file, and optionally write the ficta batch for an editor.

    uv run python .claude/skills/lilypond-pdf-score/scripts/list_ficta.py score.musicxml
    uv run python .../list_ficta.py score.musicxml --query q.json --editor sibelius > ficta.json

Without --query it prints one line per mark: staff, bar, position, pitch, accidental. With
--query (the JSON from the editor's `query --type NoteRest` for the whole score; Dorico: a
query that includes ids) it prints the batch to pass to `apply`, and fails listing marks it
cannot place. Marks are matched by staff, bar, position in the bar and pitch.
"""

import argparse
import json
import sys

from ai_score_editing.core.errors import ScoreEditingError
from ai_score_editing.core.ficta import list_ficta, resolve


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("musicxml")
    parser.add_argument("--query", help="JSON file with the editor's query result")
    parser.add_argument("--editor", choices=["sibelius", "musescore", "dorico"])
    args = parser.parse_args()
    with open(args.musicxml, encoding="utf-8") as handle:
        rows = list_ficta(handle.read())
    if not args.query:
        for r in rows:
            print(f"staff {r['staff']} ({r['partName']}) bar {r['bar']} pos {r['position']} "
                  f"note #{r['noteIndex']} pitch {r['pitch']} {r['accidental']}")
        flats = sum(r["accidental"] == "flat" for r in rows)
        print(f"{len(rows)} ficta ({flats} flat)", file=sys.stderr)
        return 0
    if not args.editor:
        parser.error("--query needs --editor")
    with open(args.query, encoding="utf-8") as handle:
        data = json.load(handle)
    objects = data["objects"] if isinstance(data, dict) else data
    try:
        print(json.dumps(resolve(rows, objects, args.editor), indent=1))
    except ScoreEditingError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
