---
name: hanging-playback-note-repair
description: >
  Diagnose and repair hanging or endlessly sustaining notes during Sibelius
  playback caused by dangling ties, ties crossing tuplet boundaries, or same-pitch
  re-attacks. Establish ground truth against original sheet music or PDF scans, verify
  MIDI Note-Off events, and restore clean playback.
---

# Hanging Playback Note Repair

This skill diagnoses and repairs notes that continue sounding or "drone"
indefinitely during Sibelius playback. In Sibelius, this symptom almost always
stems from a missing MIDI `Note-Off` event caused by an unresolved tie, a tuplet
boundary timebase mismatch, or a same-pitch re-attack conflict in the playback engine.

> [!NOTE]
> **Engraving vs. Playback:** Redundant `Clef` objects (frequently injected at
> system breaks by OMR scanners) do *not* generate MIDI events or cause playback
> drones; they are purely engraving clutter. Detecting and proposing redundant clef
> cleanup belongs to score proofreading and the `omr-score-repair` workflow.

---

## Symptoms

- A note continues sounding for several measures beyond where it is notated to end,
  frequently bleeding over subsequent rests or quiet solo entrances.
- Pressing **`Shift + O`** (**Play → Transport → All Notes Off**) immediately silences
  the hanging pitch, confirming an omitted MIDI Note-Off event in the playback engine.
- The note appears visually complete on the page, but playback behaves as if the note
  has infinite sustain.
- **Important Engine Distinction (Offline MIDI Export vs. Live SoundWorld Playback):**
  Sibelius's offline MIDI file export calculates note durations mathematically and
  will often include Note-Off events that its real-time audio engine (**SoundWorld /
  Espressivo**) drops! Therefore, while `audit-midi` is useful for spotting runaway
  durations, live playback testing in Sibelius remains the authoritative test.

---

## Dependencies & Tools

- **`sibwscli` / `sibelius-websocket-cli`**: Used to read note objects, adjust ties, delete unwanted artifacts, and export MIDI files.
- **`hanging_notes.py`** (`scripts/hanging_notes.py`): Standalone CLI helper for:
  - `audit-score`: Scans score bars across one or all staves to detect dangling ties, pitch mismatches, tuplet boundary ties, and same-pitch re-attack conflicts.
  - `audit-midi`: Scans exported MIDI track events for unclosed `Note-On` events or abnormally long sustains.
  - `render-pdf`: Renders high-resolution PNG page images from source PDF sheet music using macOS native `PDFKit` via Swift for visual ground truth comparison.

---

## The Three Problem Tiers & Operating Policies

Never treat all tie anomalies the same. Score issues fall into three fundamentally different categories:

### Tier 1: True Defective / Dangling Ties (Unambiguous Notation Errors)
- **What they are:** A note marked `tied: true` that connects to a *different pitch* across a chord change (e.g. Bar 35–36 $D\sharp_4 \rightarrow D\natural_4$), or connects to a *rest* or *empty space*.
- **Root Cause:** Optical Music Recognition (OMR) artifacts or voice-splitting scripts inadvertently mirroring common-tone ties onto voices that move.
- **Musical Validity:** Violates music notation grammar. The composer never wrote a tie between two different pitches.
- **Policy:** **Safe to Auto-Remove.** Remove the tie using `tie --remove` under `--expect-file` backup protection.

### Tier 2: Tuplet Boundary Ties (Engraving vs. Playback Engine Bug)
- **What they are:** A note marked `tied: true` that connects to the *exact same pitch* inside a tuplet (e.g. Bar 3 and Bar 7: half note $E_3$ tied to triplet quarter $E_3$).
- **Root Cause:** The tie is 100% intentional and matches the composer's printed score. However, Sibelius's real-time audio engine (SoundWorld / Espressivo) fails to match the tie's release point across the scaled timebase boundary. If that pitch is not immediately re-attacked in subsequent bars, the dropped Note-Off causes an endless drone.
- **Musical Validity:** 100% intentional notation reflecting phrasing and sustained duration.
- **Policy:** **DO NOT automatically remove the tie.** Never vandalize valid sheet music notation blindly.
- **The Verified Workaround (The Slur Solution):**
  1. Remove the engine tie: `tie --staff <STAFF> --bar <BAR> --index <INDEX> --remove`.
  2. Replace it with a **Slur** (`S` in Sibelius) spanning the two notes.
  3. **Why this works:** The slur draws the exact visual curve of a tie on the page (matching the original engraving), but instructs Sibelius's playback engine to play legato with proper Note-Off release timing, completely eliminating the hanging drone.

### Tier 3: Same-Pitch Re-Attack Conflicts (Double-Attack / Voice-Merging Artifact)
- **What they are:** A note $N_1$ marked `tied: true` connects to an intermediate duration $N_2$, and then within the same measure (or immediate phrase on the same voice), another note $N_3$ attacks the **exact same pitch** (e.g. Measure 59: half note $F\sharp_2$ tied to eighth note $F\sharp_2$, immediately followed by dotted quarter $F\sharp_2$ on syllable *"num:"*).
- **Root Cause:** OMR scanning or polyphonic demixing merging two distinct vocal lines into Voice 1 without proper polyphonic voice assignments.
- **Engine Failure Mode:** SoundWorld tracks the re-attack ($N_3$) and terminates it at the barline, but **drops the Note-Off for the initial tied note** ($N_1$). The voice remains active in the synthesizer and drones through subsequent rests for dozens of measures until that staff plays a new note.
- **Policy:** Remove the redundant forward tie connecting $N_1 \rightarrow N_2$ with `tie --remove`. The incoming tie from the previous measure remains intact, while each note receives timely Note-Off release timing.

---

## Token-efficient operation

- Audit once with `--staff all` across the whole suspect range instead of
  one staff at a time; the helper reads everything in one session.
- Render only the single source page you need for ground truth.
- Classify every flagged tie before writing anything, then remove them all
  with one `patch-notes` file of `{"op":"tie",...,"remove":true}` ops and
  `--save`.
- Export MIDI once, after all repairs, for `audit-midi`.

## Quick Start with Helper Script

### 1. Audit Live Score Structure (Single Staff or All Staves)
```bash
# Audit a single staff across a bar range
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py audit-score \
  --staff 7 --from-bar 50 --to-bar 75

# Audit ALL staves simultaneously across a passage
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py audit-score \
  --staff all --from-bar 55 --to-bar 65
```

### 2. Audit Exported MIDI for Runaway Sustain
```bash
uv run sibelius-websocket-cli export --format midi --out /private/tmp/playback_check.mid
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py audit-midi \
  /private/tmp/playback_check.mid --max-beats 8.0
```

### 3. Render Source PDF Page for Visual Ground Truth
```bash
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py render-pdf \
  "~/Downloads/Score.pdf" 7 --out /private/tmp/ground_truth_p7.png
```

---

## Diagnostic & Repair Workflow

### Step 1: Establish Visual Ground Truth Against Original Score
Render the corresponding page of the source PDF sheet music using `render-pdf`.
- Inspect the printed score: Did the composer write a tie or separate notes?
- Did the chord change? Are other choir parts holding common tones while this part moves?
- Is there a syllable change on the destination note (e.g. "num:")?

### Step 2: Audit the Score Structure
Run `audit-score --staff all` across the suspect bars:
```bash
python3 .claude/skills/hanging-playback-note-repair/scripts/hanging_notes.py audit-score \
  --staff all --from-bar <FROM> --to-bar <TO>
```
Review flagged items:
- **`[!] DEFECTIVE DANGLING TIE`**: Proceed to Step 3A.
- **`[i] TUPLET BOUNDARY TIE`**: Proceed to Step 3B.
- **`[!] SAME-PITCH RE-ATTACK CONFLICT`**: Proceed to Step 3C.

### Step 3A: Repairing Tier 1 Defects (Dangling / Mismatched Ties)
Remove the invalid tie under `--expect-file` backup protection:
```bash
uv run sibelius-websocket-cli --expect-file "<PATH_TO_SIB>" tie \
  --staff <STAFF> --bar <BAR> --index <INDEX> --remove
```

### Step 3B: Repairing Tier 2 Defects (Tuplet Boundary Playback Drone)
1. Remove the engine tie that triggers the playback hang:
   ```bash
   uv run sibelius-websocket-cli --expect-file "<PATH_TO_SIB>" tie \
     --staff <STAFF> --bar <BAR> --index <INDEX> --remove
   ```
2. Apply a **Slur** across the two noteheads in Sibelius (`S` key) to preserve visual engraving while playing legato cleanly.

### Step 3C: Repairing Tier 3 Defects (Same-Pitch Re-Attack Conflicts)
Remove the forward tie on the intermediate note:
```bash
uv run sibelius-websocket-cli --expect-file "<PATH_TO_SIB>" tie \
  --staff <STAFF> --bar <BAR> --index <INDEX> --remove
```

### Step 4: Save and Verify Playback
1. Apply all Tier 1–3 tie removals in one batch:
   ```bash
   uv run sibelius-websocket-cli --expect-file "<PATH_TO_SIB>" patch-notes \
     --file /private/tmp/ties.json --save
   ```
2. Re-run a single `audit-score --staff all` over the range to confirm no
   flags remain.
3. Test live playback in Sibelius starting 2 bars before the problem measure to confirm the drone is completely silenced.
