---
name: beaming-repair
description: >
  Fix beams in a MusicXML file before it is imported into Sibelius, Dorico or
  MuseScore: complete partly beamed beat groups left by OMR scans (for example
  a dotted eighth and sixteenth joined while the next eighth is left flagged
  in 6/8), re-beam by meter or by syllable, or strip all beams so the editor
  beams by meter. Use when a scanned score has missing or wrong beams, when
  score-engraving-audit reports beams-mixed, or before sharing or printing.
---

# Beaming repair

`scripts/fix_beams.py` edits only `<beam>` elements. Pitches, durations,
stems, ties and lyrics are never touched. It needs only `python3` (standard
library) and reads `.xml`, `.musicxml` and `.mxl`.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_beams.py" in.xml out.xml                  # complete partly beamed groups
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_beams.py" in.xml out.xml --scope all      # re-beam every beat group
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_beams.py" in.xml out.xml --style syllabic # break at new syllables
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_beams.py" in.xml out.xml --strip          # remove all beams
```

## Choose the approach

Tested in Sibelius on 2026-11-05:

- A file with **no** beams is beamed by meter on import. If the scan has no
  beams at all, do nothing, or use `--strip` to be explicit.
- **Explicit beams are kept**, even partial ones. A scan that beams a dotted
  eighth with a sixteenth but leaves the third eighth of a 6/8 beat flagged
  prints wrong. That is the default case here: `--scope mixed`, which
  completes only partly beamed beat groups and leaves complete and unbeamed
  groups alone.
- **Copy the source print's style.** Many carol and hymn editions are
  syllabic (a beam breaks at each new syllable, notes sharing one syllable
  stay joined). Look at the source PDF first. For a syllabic source use
  `--style syllabic --scope all`; a modern edition beams by the beat, the
  default `--style meter`. Voices with no lyrics always fall back to meter.

## What it does

- Beat groups: a quarter note in simple time; three eighths in 6/8, 9/8 and
  12/8. A rest or an unbeamable note breaks a run.
- Secondary beams for sixteenths and shorter, with backward hooks after a
  dotted note and forward hooks otherwise.
- Chord notes receive the same beams as the note they sound with.
- The XML declaration and DOCTYPE are preserved.
- It prints counts of groups and notes changed.

## Not covered

- Beams across beat groups (for example beaming four eighths in 4/4) and
  cross-staff beaming.
- Beams over lyrics-heavy melismas in a non-syllabic edition are left to the
  meter rule.
- Stem direction: use the editor's `flip-stem` after import.

## Check the result

1. `python3 ../score-engraving-audit/scripts/audit_musicxml.py out.xml`:
   `beams-mixed` should be gone.
2. Import, export a PDF, and compare a few bars with the source scan.
3. The Sibelius `beam` operation can fix the odd group by hand afterwards
   (Sibelius and MuseScore only; Dorico has no beam operation yet).
