---
name: omr-score-repair
description: >
  Diagnose and repair optical music recognition (OMR) artifacts in scanned
  sheet music and MusicXML files. Inspect source PDF scans for visual ground truth,
  unstack mistakenly concurrent staves into sequential lines, prune dummy measure
  padding, restore system breaks, purge redundant clef objects injected at
  system breaks, normalize lyric prosody and melismas, and verify cleanly in
  Sibelius.
---

# OMR Score Repair

This skill diagnoses and repairs common Optical Music Recognition (OMR) artifacts
in MusicXML files exported from sheet music scanners (e.g. Halbestunde, PhotoScore,
SmartScore, PlayScore), establishing visual ground truth against the original
score and preparing clean, publication-ready MusicXML for Sibelius.

---

## Overview

When sheet music is scanned to MusicXML, scanning engines frequently make
systematic architectural and engraving mistakes:
1. **Stacked Systems**: Sequential lines of a solo melody or single voice are
   exported as concurrent ensemble staves (`Voice0`, `Voice1`, `Voice2`).
2. **Dummy Measure Padding**: Scanners insert spurious measures with whole
   rests to pad shorter systems (e.g. Line 1) to match longer systems.
3. **Dropped System Breaks**: Notes run continuously without preserving the
   original printed line flow.
4. **Mangled Lyrics & OCR Text**: Hymn numbers misread as lyric syllables,
   syllables dropped or unhyphenated, and melisma extenders lost.
5. **Redundant Clef Objects**: Every recognized system break restates the clef,
   leaving duplicate `Clef` objects mid-bar across all staves after import.

6. **Fragmented parts**: one printed staff comes back as several parts, and
   the notes for stretches where the main part shows a whole-bar rest sit in
   the fragments.

---

## Fragmented parts (read before merging)

Halbestunde and MuseScore's converter can return more parts than the page has
staves (11 for 5 staves on All I Want For Christmas). To merge:

1. List, per part and bar, whether it holds notes or only rests, and find the
   stretches where a main part rests but a fragment has notes.
2. Decide which fragment belongs to which staff **from the print**, not from
   part order: at bars 29-36 the A2 line ("din a") sat in the part numbered
   for A1, so merging in order swapped A1 and A2. Render the page and compare
   pitches and lyrics.
3. Keep a tied note's accidental: a note tied from a D# is a D#, whatever the
   scan wrote (bars 52 and 69-70 had it wrong).
4. When a stretch has a chord (stacked voices) do not collapse it to one note:
   a dropped voice is a lost line. Keep every note and split later
   (`playback-divisi-split`, extra-staves mode).
5. A tenor line may already be marked treble 8vb with sounding pitches. Import
   first and compare the tenor's octave with the print; do not add a
   `<transpose>` or raise the pitches until you have seen it wrong (a
   Sibelius-exported tenor is different, see `tenor-playback-repair`).
6. Check the structure after every script edit:

   ```bash
   python3 ${CLAUDE_SKILL_DIR}/scripts/check_musicxml.py "Score.xml"
   ```

   It flags `<transpose>` before `<clef>`, a note with two `<rest/>` (a second
   `to_rest()` on an existing rest), note children out of schema order,
   bars of the wrong length and parts with different bar counts. Sibelius
   shows each of these as a MusicXML warning on import (the first import of
   this score had two).
7. Count notes before and after; do not trust that nothing was lost.

---

## Dependencies

- **`sibelius` skill** (`.claude/skills/sibelius/SKILL.md`): Used for score inspection, lyric checking, and engraving verification after importing the repaired MusicXML into Sibelius.
- **`omr_tool.py`** (`${CLAUDE_SKILL_DIR}/scripts/omr_tool.py`): Standalone CLI helper for auditing, unstacking, and validating MusicXML measure structures.
- **`clean_clefs.py`** (`${CLAUDE_SKILL_DIR}/scripts/clean_clefs.py`): Audits and purges redundant `Clef` objects from the score open in Sibelius. Must run under `uv run` so it can import `ai_score_editing`.

---

## Token-efficient operation

- Run `omr_tool.py audit` once per file and work from its summary; do not
  dump the MusicXML.
- Render only the PDF pages you need, at the size you need.
- After import, use one `score-snapshot` for staff count, keys, and barlines,
  and one `proofread --lyrics` instead of `inspect` + `read-lyrics` +
  `check-lyrics`.
- Fold clef cleanup and restored system breaks into one `patch-layout` file
  (`remove-redundant-clefs` plus `set-break` ops) so the score is backed up,
  changed, and verified once.
- Put lyric corrections found in Sibelius into one `patch-lyrics` file.

## Quick Start

### 1. Audit a scanned MusicXML file
```bash
uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/omr_tool.py audit "path/to/scan.xml"
```

### 2. Unstack parts into a single voice with line breaks
```bash
uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/omr_tool.py unstack "path/to/scan.xml" \
  --output "path/to/repaired.xml" \
  --prune P1:6 \
  --part-name "Voice"
```

### 3. Validate measure durations
```bash
uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/omr_tool.py validate "path/to/repaired.xml"
```

### 4. Purge redundant clefs from the imported score (runs against live Sibelius)
```bash
uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/clean_clefs.py audit          # report only
uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/clean_clefs.py strip          # backs up, deletes, saves
```

---

## Core Workflow

### Step 1: Establish Visual Ground Truth
Always inspect the source PDF or image before making musical decisions:
- Render every page with the bundled PDFKit script (QuickLook's `qlmanage`
  renders only page 1):
  ```bash
  swift ${CLAUDE_SKILL_DIR}/scripts/render_pdf_pages.swift "path/to/score.pdf" /tmp/score_preview
  ```
- Check the printed layout:
  - How many visual lines/systems appear on the page?
  - Is it a single vocal line or an ensemble score?
  - Count actual barlines on each line. Do not trust measure numbers in the XML.
  - Read [the visual inspection guide](references/visual-inspection.md) for bounding and barline detection techniques.

### Step 2: Audit the MusicXML Structure
Run `omr_tool.py audit` to inspect the score topology:
- Check `part_count`: If part count matches the printed system count and each part has identical or near-identical measure counts, the systems were stacked into an ensemble.
- Check `dummy_rest_measures`: Identify padding measures containing whole rests at the end of systems.
- Read [the OMR failure modes catalog](references/omr-patterns.md) to identify matching symptoms and repair patterns.

### Step 3: Unstack and Restructure
Use `omr_tool.py unstack` to restructure the score:
- Recombine stacked parts (`P1`, `P2`, `P3`) into a single sequential part (`P1`).
- Prune spurious rest measures with `--prune <Part:Measure>` (e.g. `--prune P1:6`).
- Ensure `<print new-system="yes"/>` is placed at the start of each original line to preserve visual line flow.
- The tool automatically creates a `.orig` backup before writing in-place.

### Step 4: Align Lyrics and Melismas
- Check lyrics against the source sheet music text:
  - Separate song numbers (e.g. `10.`) from the initial lyric syllable.
  - Set syllabic types (`begin`, `middle`, `end`, `single`).
  - Add `<extend/>` and slurs on notes carrying held syllables/melismas.
  - Read [the lyrics and prosody guide](references/lyrics-and-prosody.md) for formatting rules.

### Step 5: Validate and Handoff to Sibelius
- Validate measure math:
  ```bash
  uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/omr_tool.py validate "path/to/repaired.xml"
  ```
- Open the score in Sibelius:
  - Run `uv run --project "${CLAUDE_SKILL_DIR}" sibelius-cli score-snapshot` to verify staff count, title, keys, and barlines in one call.
  - Run `uv run --project "${CLAUDE_SKILL_DIR}" sibelius-cli proofread --lyrics` to check words and hyphens in one report.

### Step 6: Purge Redundant Clefs in the Live Score
Unstacking strips clef restatements at the XML level, but surviving duplicates
materialize as `Clef` objects once Sibelius opens the score. Clean them with the
score open, after the import itself has been verified. See
[Pattern 9](references/omr-patterns.md) for the underlying failure mode.

1. **Audit first — never strip an unreviewed score:**
   ```bash
   uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/clean_clefs.py audit
   ```
   Findings are grouped per staff, each annotated with the default clef used and
   where it came from (read from bar 1, inferred from the instrument name, or
   unknown), followed by a preview of the first 20.
2. **Check the flagged list against the printed page.** A clef the engraving
   genuinely needs — a real mid-piece clef change — must not be deleted.
3. **Strip, optionally narrowed to a single staff:**
   ```bash
   uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/clean_clefs.py strip --dry-run   # preview only
   uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/clean_clefs.py strip --staff 16
   ```
   `strip` backs up the score first, deletes in reverse index order within each
   bar so earlier indices stay valid, then **saves the score automatically**.

   When system breaks also need restoring, prefer one `patch-layout` file that
   combines `{"op":"remove-redundant-clefs"}` (optionally with `"staff"`) and
   the `set-break` operations; validate with `--dry-run`, then apply with
   `--save`. The audit step above still comes first.

Redundant clefs are engraving clutter only — they emit no MIDI events. If the
score also drones during playback, that is a separate tie defect; use the
`hanging-playback-note-repair` skill.

---

## Common Mistakes

- **Trusting OMR bar counts without visual inspection**: Scanners frequently miss thin barlines or pad systems with empty bars. Always count visual barlines on the printed page.
- **Adding manual hyphens to lyric text**: Do not write `<text>pe-</text>`. Let `<syllabic>begin</syllabic>` or `middle` drive hyphenation automatically to prevent double-hyphen engraving defects.
- **Leaving spurious rests across system breaks**: When Line 1 has 5 bars and Line 2 has 6 bars, retaining a 6th dummy rest bar breaks the musical phrase and sentence in half.
- **Unstacking genuine ensemble parts**: a `Stacked system suspected` audit result can simply mean voices enter late. Check the PDF first; see [Pattern 10](references/omr-patterns.md).
- **Reading only lyric line 1**: verses 2+ are separate `<lyric number="N">` elements on the same notes. Dump every lyric number before reporting a verse as missing.
- **Trusting single notes where the print shows chords**: OMR often keeps only the lowest chord member; see [Pattern 11](references/omr-patterns.md). Also check that every part has a key signature in bar 1 ([Pattern 12](references/omr-patterns.md)).
- **Stripping clefs without reading the audit first**: a *genuine* clef change that falls at a system break is engraved as a courtesy clef at the end of the previous bar, which looks identical to the artifact. Deleting the wrong one of the pair removes the clef change itself. Always review the `audit` output, or use `strip --dry-run`, against the printed page before deleting.
- **Expecting full coverage on staves with no inferable clef**: when the staff default cannot be read from bar 1 and the instrument name implies nothing definite (`Piano`, `Organ`), the default-clef comparison is skipped by design and only end-of-bar artifacts are reported. That under-reports rather than risking a wrong deletion; clean those staves by eye.
