---
name: satb-part-splitting
description: >
  Demix and transform 2-staff choral/piano scores (S+A in treble, T+B in bass)
  into 4 discrete SATB staves with separate MIDI playback channels, proper
  clefs (including Tenor treble-8vb), preserved lyrics, and clean measure rests.
---

# SATB Part Splitting

This skill audits, demixes, and transforms 2-staff choral reductions (Soprano + Alto
in treble, Tenor + Bass in bass) into 4 discrete, publication-ready SATB vocal staves.
It establishes individual playback channels for rehearsal, sets correct choral clefs,
prevents chord-tie corruption, and preserves lyric prosody across all four voices.

---

## Overview & Purpose

Choral music, vocal jazz charts, and hymnbooks are almost universally printed in a
compact 2-staff reduction:
- **Upper Staff (Treble Clef):** Soprano (upper voice) + Alto (lower voice).
- **Lower Staff (Bass Clef):** Tenor (upper voice) + Bass (lower voice).

While convenient for print and keyboard accompaniment, 2-staff notation prevents:
1. Rehearsal playback with independent part isolation (e.g. soloing Tenor or muting Soprano).
2. Assigning distinct vocal samples or stereo pan positions per voice.
3. Printing clean, un-cluttered individual octavo rehearsal parts.

Splitting 2 staves into 4 discrete parts (`P1` through `P4`) in MusicXML/Sibelius involves
several non-obvious traps that this skill handles systematically.

---

## Dependencies & Tools

- **`split_satb.py`** (`scripts/split_satb.py`): Standalone Python CLI helper for:
  - `audit`: Analyzes voice streams, chord clusters, and lyrics on each staff.
  - `split`: Demixes notes/chords, clones lyrics, reconnects shattered syllables, assigns clefs, and writes 4-part `.mxl` or `.xml`.
  - `reconnect-lyrics`: Standalone command to scan and reconnect shattered OMR syllables into hyphenated multi-syllable words in any MusicXML file.
  - `validate`: Verifies measure duration consistency across all 4 parts.
- **`ScoreBridge` / `sibelius-cli`**: Used to inspect, verify, and engrave the resulting score in Sibelius.
- **`hanging_notes.py`** (`.claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py`): Used to audit the split score for any residual dangling ties.

---

## Quick Start

The SATB wrapper routes notes through the repository's shared onset-based
MusicXML engine. Its lyric reconnection remains SATB-only post-processing;
the generic engine never attempts OMR lyric repair.

### 1. Audit the Input Score
Inspect the 2-staff MusicXML (`.xml` or `.mxl`) to determine voice usage and chords:
```bash
python3 .claude/skills/satb-part-splitting/scripts/split_satb.py audit "path/to/2staff_score.mxl"
```

### 2. Split into 4 SATB Parts (with Automatic Lyric Reconnection)
Run `split`, specifying any solo bars, lyric propagation, and automatic syllable reconnection (enabled by default):
```bash
python3 .claude/skills/satb-part-splitting/scripts/split_satb.py split "path/to/2staff_score.mxl" \
  --output "path/to/4staff_satb.mxl" \
  --tenor-solo "8-15,20-27,41" \
  --copy-lyrics-to-tb \
  --reconnect-lyrics
```

### 3. (Optional) Reconnect Lyrics on an Existing Score
To reconnect shattered OMR syllables on an already split or existing MusicXML file without re-splitting:
```bash
python3 .claude/skills/satb-part-splitting/scripts/split_satb.py reconnect-lyrics \
  "path/to/score.mxl" -o "path/to/reconnected.mxl"
```

### 4. Validate Measure Durations
Ensure every bar in all 4 parts has valid, consistent durations:
```bash
python3 .claude/skills/satb-part-splitting/scripts/split_satb.py validate "path/to/4staff_satb.mxl"
```

### 5. Open in Sibelius and Verify
Import the repaired `.mxl` into Sibelius:
```bash
open -a Sibelius "path/to/4staff_satb.mxl"
```
Verify in as few calls as possible: one `score-snapshot` for staves, keys,
and barlines, one `proofread --lyrics` for lyric integrity across all four
parts, and one tie audit across every staff:
```bash
uv run sibelius-cli score-snapshot
uv run sibelius-cli proofread --lyrics
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py audit-score \
  --staff all --from-bar 1 --to-bar 30
```
Fix any lyric findings with a single `patch-lyrics` file rather than
per-syllable `set-lyric` calls.


---

## The 5 Critical Technical Pitfalls & Rules

### 1. The Lyric Attachment Trap in MusicXML
In MusicXML, `<lyric>` elements on chords are attached **only to the first (lowest) note** of the `<chord>` cluster.
- **The Pitfall:** If a script naively demixes a chord by putting the top note into Soprano and base note into Alto, the Soprano voice loses all lyrics.
- **The Rule:** During chord demixing, always inspect the chord cluster for `<lyric>`. If the base note holds lyrics, clone them onto the upper note (`clean_note_element`).

### 2. The Tie-Propagation Trap (Prevents Hanging Drones)
In 2-staff chord writing, common tones are often tied while other voices move (e.g. Alto holds $C\sharp_4$ while Soprano moves $F\sharp_4 \rightarrow G\sharp_4$).
- **The Pitfall:** Naive part-splitters copy `tied: true` to both voices. This causes the moving voice to carry a forward tie to a different pitch (e.g. $F\sharp \rightarrow G\sharp$), becoming a **dangling tie** that drops Note-Off events in Sibelius.
- **The Rule:** Ties must follow specific pitches, never whole chords. Verify that `notes[].tied` is only retained on the voice whose pitch actually persists into the next measure.

### 3. Polyphonic vs. Homophonic Demixing
Scores alternate between two notation styles:
- **Polyphonic (Opposing Stems):** Voice 1 (stems up) and Voice 2 (stems down).
  - *Action:* Route Voice 1 $\rightarrow$ Soprano / Tenor, Voice 2 $\rightarrow$ Alto / Bass.
- **Homophonic (Shared Stems / Chords):** A single voice stream containing chords.
  - *Action:* Sort cluster notes by MIDI pitch (`get_midi`). Assign highest pitch to upper part (S/T) and lowest pitch to lower part (A/B).

### 4. Solo vs. Tutti Infilling
When a single voice has a solo passage (e.g. Tenor solo):
- **The Pitfall:** The 2-staff reduction often leaves the lower staff as a single melodic line without explicit rests for the other voice. Merging without infill leaves missing measure time or duplicates the melody.
- **The Rule:** Inject whole-measure rests (`<rest measure="yes"/>` via `make_rest_measure`) on the silent staves during solo sections.

### 5. Clef & Playback Architecture
- **Tenor Clef:** Must be set to **octave-treble** (`clef.sign: G`, `clef.line: 2`, `clef-octave-change: -1`).
- **Instrument Sounds:** Assign `Choir Aahs` (GM program 53) with standard sound IDs (`voice.soprano`, `voice.alto`, `voice.tenor`, `voice.bass`).
- **MIDI Channels:** Allocate discrete channels (1, 2, 3, 4) in `<midi-instrument>` so Sibelius automatically creates 4 separate mixer faders for independent solo/mute control.
- **Strip Hardcoded System Breaks:** Omit `<print>` elements from the 2-staff scan. 4-staff systems need more vertical space; stripping `<print>` lets Sibelius calculate clean page layouts without overlapping staves.

---

## Post-Split Verification Checklist

1. **Duration Check:** Run `split_satb.py validate <file.mxl>`. (Must report 0 issues).
2. **Clef Verification:** In Sibelius, confirm that Soprano and Alto are in Treble, Tenor is in Treble-8vb (little "8" under the clef), and Bass is in Bass clef.
3. **Mixer Verification:** Open Sibelius Mixer (`M`). Confirm 4 discrete strips (S, A, T, B) with Choir Aahs on channels 1–4.
4. **Tie Verification:** Run one `hanging_notes.py audit-score --staff all` to guarantee no dangling ties were introduced during demixing.
