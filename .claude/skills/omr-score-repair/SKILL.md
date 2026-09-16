---
name: omr-score-repair
description: >
  Diagnose and repair optical music recognition (OMR) artifacts in scanned
  sheet music and MusicXML files. Inspect source PDF scans for visual ground truth,
  unstack mistakenly concurrent staves into sequential lines, prune dummy measure
  padding, restore system breaks, normalize lyric prosody and melismas, and
  verify cleanly in Sibelius.
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

---

## Dependencies

- **`sibelius` skill** (`.claude/skills/sibelius/SKILL.md`): Used for score inspection, lyric checking, and engraving verification after importing the repaired MusicXML into Sibelius.
- **`omr_tool.py`** (`scripts/omr_tool.py`): Standalone CLI helper for auditing, unstacking, and validating MusicXML measure structures.

---

## Quick Start

### 1. Audit a scanned MusicXML file
```bash
uv run python .claude/skills/omr-score-repair/scripts/omr_tool.py audit "path/to/scan.xml"
```

### 2. Unstack parts into a single voice with line breaks
```bash
uv run python .claude/skills/omr-score-repair/scripts/omr_tool.py unstack "path/to/scan.xml" \
  --output "path/to/repaired.xml" \
  --prune P1:6 \
  --part-name "Voice"
```

### 3. Validate measure durations
```bash
uv run python .claude/skills/omr-score-repair/scripts/omr_tool.py validate "path/to/repaired.xml"
```

---

## Core Workflow

### Step 1: Establish Visual Ground Truth
Always inspect the source PDF or image before making musical decisions:
- Render high-resolution page previews using macOS QuickLook:
  ```bash
  qlmanage -t -s 2000 -o /tmp/score_preview "path/to/score.pdf"
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
  uv run python .claude/skills/omr-score-repair/scripts/omr_tool.py validate "path/to/repaired.xml"
  ```
- Open the score in Sibelius:
  - Run `uv run sibelius-websocket-cli inspect` to verify staff count and title.
  - Run `uv run sibelius-websocket-cli read-lyrics` or `check-lyrics` to ensure all words and hyphens render cleanly.

---

## Common Mistakes

- **Trusting OMR bar counts without visual inspection**: Scanners frequently miss thin barlines or pad systems with empty bars. Always count visual barlines on the printed page.
- **Adding manual hyphens to lyric text**: Do not write `<text>pe-</text>`. Let `<syllabic>begin</syllabic>` or `middle` drive hyphenation automatically to prevent double-hyphen engraving defects.
- **Leaving spurious rests across system breaks**: When Line 1 has 5 bars and Line 2 has 6 bars, retaining a 6th dummy rest bar breaks the musical phrase and sentence in half.
