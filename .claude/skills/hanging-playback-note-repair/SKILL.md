---
name: hanging-playback-note-repair
description: >
  Diagnose and repair hanging or endlessly sustaining notes during Sibelius
  playback caused by dangling ties, ties crossing tuplet boundaries, or ties
  connecting to mismatched pitches. Establish ground truth against original
  sheet music or PDF scans, verify MIDI Note-Off events, and restore clean playback.
---

# Hanging Playback Note Repair

This skill diagnoses and repairs notes that continue sounding or "drone"
indefinitely during Sibelius playback. In Sibelius, this symptom almost always
stems from a missing MIDI `Note-Off` event caused by an unresolved or
dangling tie in the score engine.

---

## Symptoms

- A note continues sounding for several measures beyond where it is notated to end,
  frequently bleeding over subsequent rests or quiet solo entrances.
- Pressing **`Shift + O`** (**Play → Transport → All Notes Off**) immediately silences
  the hanging pitch, confirming an omitted MIDI Note-Off event in the playback engine.
- The note appears visually complete on the page, but playback behaves as if the note
  has infinite sustain.

---

## Dependencies & Tools

- **`sibwscli` / `sibelius-websocket-cli`**: Used to read note objects, adjust ties, delete unwanted artifacts, and export MIDI files.
- **`hanging_notes.py`** (`scripts/hanging_notes.py`): Bundled standalone CLI helper for:
  - `audit-score`: Scans score bars via CLI to detect dangling ties, pitch mismatches, and inform on tuplet boundary ties.
  - `audit-midi`: Scans exported MIDI track events for `Note-On` events without matching `Note-Off` or notes exceeding a duration threshold.
  - `render-pdf`: Renders high-resolution PNG page images from source PDF sheet music using macOS native `PDFKit` via Swift for visual ground truth comparison.

---

## The Two Distinct Problem Tiers & Operating Policies

Never treat all tie anomalies the same. Score issues fall into two fundamentally different categories:

### Tier 1: True Defective / Dangling Ties (Unambiguous Errors)
- **What they are:** A note marked `tied: true` that connects to a *different pitch* across a chord change (e.g. Bar 35–36 $D\sharp_4 \rightarrow D\natural_4$), or connects to a *rest* or *empty space*.
- **Root Cause:** Optical Music Recognition (OMR) artifacts or voice-splitting scripts inadvertently mirroring common-tone ties onto voices that move.
- **Musical Validity:** Violates music notation grammar. The composer never wrote a tie between two different pitches.
- **Policy:** **Safe to Auto-Remove.** Remove the tie using `tie --remove` under `--expect-file` backup protection and report the fix.

### Tier 2: Tuplet Boundary Ties (Engraving vs. Playback Engine Bug)
- **What they are:** A note marked `tied: true` that connects to the *exact same pitch* inside a tuplet (e.g. Bar 3 and Bar 7: half note $E_3$ tied to triplet quarter $E_3$).
- **Root Cause:** The tie is 100% intentional and matches the composer's printed score. However, Sibelius's real-time audio engine (SoundWorld / Espressivo) fails to match the tie's release point across the scaled timebase boundary. If that pitch is not immediately re-attacked in subsequent bars (e.g. Bar 7 followed by rests/solo), the dropped Note-Off causes an endless drone. (If re-attacked quickly, as in Bar 3 $\rightarrow$ Bar 4 beat 1, the hang is masked).
- **Musical Validity:** 100% intentional notation reflecting phrasing and sustained duration.
- **Policy:** **DO NOT automatically remove the tie.** Never vandalize valid sheet music notation blindly.
- **The Verified Workaround (The Slur Solution):**
  1. Remove the engine tie: `tie --staff <STAFF> --bar <BAR> --index <INDEX> --remove`.
  2. Replace it with a **Slur** (`S` in Sibelius) spanning the two notes.
  3. **Why this works:** The slur draws the exact visual curve of a tie on the page (matching the original engraving), but instructs Sibelius's playback engine to play legato with proper Note-Off release timing, completely eliminating the hanging drone.

---

## Quick Start with Helper Script

### 1. Audit Live Score Structure
```bash
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py audit-score \
  --staff 3 --from-bar 1 --to-bar 20
```

### 2. Audit Exported MIDI for Hanging Note-Ons or Long Sustain
```bash
uv run sibelius-websocket-cli export --format midi --out /private/tmp/playback_check.mid
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py audit-midi \
  /private/tmp/playback_check.mid --max-beats 8.0
```

### 3. Render Source PDF Page for Visual Ground Truth
```bash
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py render-pdf \
  "~/Downloads/Tell Me a Bedtime Story.pdf" 1 --out /private/tmp/ground_truth_p1.png
```

---

## Diagnostic & Repair Workflow

### Step 1: Establish Visual Ground Truth Against Original Score
Render the corresponding page of the source PDF sheet music using `render-pdf`.
- Inspect the printed score: Did the composer write a tie or separate notes?
- Did the chord change? Are other choir parts holding common tones while this part moves?
- If the tie is NOT in the PDF (or connects different pitches), it is a Tier 1 defect.
- If the tie IS in the PDF, it is a Tier 2 intentional element.

### Step 2: Read the Passage & Audit the Score
Run `audit-score` on the suspected staff and bar range:
```bash
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py audit-score \
  --staff <STAFF> --from-bar <FROM> --to-bar <TO>
```
Review the flags:
- **`[!] DEFECTIVE DANGLING TIE`**: Proceed to Step 3A.
- **`[i] TUPLET BOUNDARY TIE`**: Proceed to Step 3B.

### Step 3A: Repairing Tier 1 Defects (Dangling / Mismatched Ties)
Remove the invalid tie under `--expect-file` backup protection:
```bash
uv run sibelius-websocket-cli --expect-file "<PATH_TO_SIB>" tie \
  --staff <STAFF> --bar <BAR> --index <INDEX> --remove
```
*Clean up any accompanying OMR artifacts:*
- Delete stray notes left on rest beats with `delete-object`.
- Set dangling lyric hyphens from `middle` to `end` via `set-lyric`.

### Step 3B: Repairing Tier 2 Defects (Tuplet Boundary Playback Drone)
1. Remove the engine tie that triggers the playback hang:
   ```bash
   uv run sibelius-websocket-cli --expect-file "<PATH_TO_SIB>" tie \
     --staff <STAFF> --bar <BAR> --index <INDEX> --remove
   ```
2. Save the score:
   ```bash
   uv run sibelius-websocket-cli save
   ```
3. Apply a **Slur** across the two noteheads in Sibelius:
   - Select the first notehead in the active score.
   - Press **`S`** to insert a slur extending to the next note.
   - The score retains its visual tie appearance, while Sibelius plays legato cleanly without droning.

### Step 4: Save, Export MIDI, and Audit Playback
1. Save the active score:
   ```bash
   uv run sibelius-websocket-cli save
   ```
2. Export test MIDI and audit:
   ```bash
   uv run sibelius-websocket-cli export --format midi --out /private/tmp/playback_check.mid
   python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py audit-midi \
     /private/tmp/playback_check.mid --max-beats 8.0
   ```
3. Test live playback in Sibelius to confirm the drone is completely silenced.
