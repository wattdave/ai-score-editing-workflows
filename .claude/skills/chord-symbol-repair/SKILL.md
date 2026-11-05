---
name: chord-symbol-repair
description: >
  Repair guitar/piano chord symbols in a MusicXML file that an OMR scan stored
  as plain text and misread (lowercase roots such as c and c7 for C and C7,
  0 for o, l for 1): upper-case the roots, or convert each chord into a real
  chord symbol (harmony element) at the same place. Keeps chord symbols in
  shared scores instead of deleting them. Use when score-engraving-audit
  reports chords-as-text or chords-lowercase, or before importing a scanned
  lead sheet or carol with chord letters.
---

# Chord symbol repair

OMR (Halbestunde and others) reads chord symbols as ordinary text, so a
score carries `<direction><direction-type><words>c7</words>` instead of a
chord symbol, often with a lowercase root. This skill fixes that in the
MusicXML before it is imported into Sibelius, Dorico or MuseScore. It needs
only `python3` (standard library), not this repository or any editor.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_chords.py" IN.xml OUT.xml            # to <harmony>
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_chords.py" IN.xml OUT.xml --report   # list every change and skip
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_chords.py" IN.xml OUT.xml --mode capitalize
```

`IN` may be `.xml`, `.musicxml` or `.mxl`; `OUT` is plain MusicXML. The
input file is never modified. The XML declaration and DOCTYPE are copied from
the input, comments are kept, and only the chord directions change.

## Modes

- `harmony` (default): each recognised chord word becomes a `<harmony>`
  element (root-step, root-alter, `kind` with a `text` attribute holding the
  displayed suffix, `bass` for slash chords, `degree` for `add9`) in the same
  place in the measure. The direction's `placement`, `offset` and `staff`
  and the words' `default-x/y`, `relative-x/y` carry over. The words
  direction is removed.
- `capitalize`: keeps the text and only upper-cases roots and slash basses:
  `dm` to `Dm`, `c7` to `C7`, `bbmaj7` to `Bbmaj7`, `f#m` to `F#m`, `c/e` to
  `C/E`. A lowercase `b` after the root stays a flat, and `m`, `maj`, `dim`,
  `sus`, `add` stay lowercase. Choose this if the editor should keep chords as
  text (for example to place them by hand).

Recognised suffixes: major, `m`/`min`/`-`, `7`, `maj7`/`M7`, `m7`, `dim`/`o`,
`dim7`, `ø`/`m7b5`, `aug`/`+`, `sus`/`sus4`, `sus2`, `6`, `m6`, `9`, `maj9`,
`m9`, `11`, `13`, `5`, `add9`, `madd9`. OCR repairs applied while parsing:
`0` or `O` for the diminished `o` (`C07` is Co7) and `l`, `I`, `|` for `1`
(`Gl3` is G13).

## What counts as a chord

A words element is converted only if the whole trimmed text parses as a
chord and it is the only content of its direction (one direction-type, no
`<sound>`). So `Dm.`, `dim.`, `rit.`, `a tempo`, `With spirit`, `mf`,
`Coda`, a words element beside a dynamic, and anything with extra text are
left alone.

A bare letter (`a`, `F`, `e`) or the English word `am` is ambiguous: it may
be a part label or rehearsal letter. It is converted only when the score
has at least 3 unambiguous chords (`Gm`, `c7`, `F#`, `C/E`, ...) or
existing `<harmony>` elements; otherwise it is left and listed as
`ambiguous` by `--report`. Check those against the print.

Words that look like chords but do not parse (`C13b9`, `Dm.`) are left
untouched and listed as `unrecognised` by `--report`. Fix them by hand or
extend the suffix table in `fix_chords.py`.

## Workflow

1. Run `score-engraving-audit` and note `chords-as-text` / `chords-lowercase`.
2. Run `fix_chords.py IN OUT --report`; read the ambiguous and unrecognised
   lines and compare with the source print (OMR can also misread the root
   letter itself, for example `G` for `C`, which no script can see).
3. Run the audit on `OUT`: both chord findings should be gone.
4. Import `OUT`.

The script is idempotent: running it again on its own output changes
nothing.

## Editors

How Sibelius, Dorico and MuseScore treat `<harmony>` on MusicXML import has
not been tested in this repository. MusicXML chord symbols are standard and
all three are expected to import them as chord symbols, but check one file
after import before relying on it, and fall back to `--mode capitalize` if
an editor drops them.
