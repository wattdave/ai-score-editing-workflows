# Common OMR Failure Modes and MusicXML Repair Recipes

Optical Music Recognition (OMR) software (e.g. Halbestunde, PhotoScore, SmartScore, PlayScore) systematically produces specific rendering and structural artifacts. This guide catalogs these failure patterns and provides concrete repair procedures.

---

## Pattern 1: Erroneously Stacked Systems (Ensemble vs. Sequential Flow)

### Symptom
A single melody or solo vocal line printed over several lines/systems on the page is exported as an ensemble score with multiple concurrent parts (e.g., `Voice0`, `Voice1`, `Voice2` / `P1`, `P2`, `P3`), sounding simultaneously in 1 bracketed system.

### Cause
OMR engines assume that any page layout with multiple staves must be a multi-staff ensemble score unless explicit system breaks are configured.

### Repair
1. Consolidate into a single `<score-part id="P1">` in `<part-list>`.
2. Sequence the `<measure>` elements from all parts end-to-end into one `<part id="P1">`.
3. Renumber all measures sequentially from `1` to `N`.
4. Inject `<print new-system="yes"/>` at the start of each unstacked system boundary (e.g., measure 6 and 12).
5. Remove redundant clef, key signature, and time signature attributes from non-initial measures unless there is a genuine musical change.

---

## Pattern 2: Dummy Measure Padding (Spurious Whole Rests)

### Symptom
An extra measure containing only a whole rest appears at the end of a line (often Line 1), breaking musical phrasing and creating artificial silence.

### Cause
In standard MusicXML `score-partwise`, all parts within a concurrent system are expected to align in measure count. When Line 1 has fewer measures (e.g. 5 measures due to score title and key/time signatures) while subsequent lines have 6 measures, the OMR engine inserts a dummy measure with `<rest/>` into Part 1 so that `len(P1) == len(P2) == len(P3)`.

### Repair
1. Verify against visual ground truth (the printed PDF). If there is no printed barline or rest at the end of that system, identify the dummy measure.
2. Prune the dummy measure completely during unstacking (`--prune P1:6`).
3. Verify that musical phrases connect seamlessly across the system break without artificial pauses.

---

## Pattern 3: Accidental & Key Discrepancies

### Symptom
Notes receive incorrect pitches or missing accidentals (e.g. C natural encoded as C sharp, or explicit accidentals omitted).

### Cause
OCR engine fails to detect natural signs ($\natural$) or accidental marks next to noteheads, or confuses accidentals with nearby note stems or ledger lines.

### Repair
1. In MusicXML, `<pitch>` specifies `<step>`, `<octave>`, and optional `<alter>` (e.g. `1` for sharp, `-1` for flat, `0` or omitted for natural).
2. For explicit accidentals, always include the `<accidental>` tag (e.g. `<accidental>natural</accidental>` or `<accidental>sharp</accidental>`) alongside the `<alter>` tag.
3. Validate that measure durations sum up to the declared `<time>` beats.

---

## Pattern 4: Beaming and Slur Fragmentation

### Symptom
Eighth notes that are visually beamed together appear with separated flags, or slurs across melismas are missing.

### Cause
Image resolution or staff line interference causes the OMR detector to drop beam bands or misread slur curves.

### Repair
- Beams: Use `<beam number="1">begin</beam>` and `<beam number="1">end</beam>` on eighth note groups.
- Slurs: Enclose melismatic note groups in `<notations><slur type="start" number="1"/></notations>` on the first note, and `<notations><slur type="stop" number="1"/></notations>` on the last note.

---

## Pattern 5: Missing Pages in OMR Scanner Exports

### Symptom
Multi-page OMR scans (e.g. Halbestunde) occasionally skip an entire page completely (e.g. Page 12 omitted out of a 13-page score), resulting in an abrupt jump in measure numbers or missing choral sections.

### Cause
Scanner page-split failures or OCR timeouts during heavy multi-voice engraving.

### Repair
1. Compare page count and printed rehearsal/measure numbers between the source PDF and the raw XML export.
2. If a page was omitted, crop each system of the missing page from the high-resolution PDF preview (`PIL.Image` or `qlmanage`).
3. Transcribe the missing measures directly into programmatic note/rest lists matching standard MusicXML structures, validating clefs, key signatures, and accidentals.

---

## Pattern 6: Rhythmic Misclassification & Meter Misalignment

### Symptom
Beamed eighth notes are misrecognized as quarter notes (or vice versa), causing an OMR engine to invent spurious time signatures or insert spurious rests (e.g. converting a $3/4$ measure into $4/4$ with a rest).

### Cause
Close stem spacing or thick beam lines causing the OCR classifier to misidentify notehead durations.

### Repair
1. Calculate the exact tick sum for each measure (`divisions * beats * (4 / beat_type)`).
2. Trace barlines visually on the source scan across all staves in the system to verify true measure boundaries.
3. Check anacruses/pickups: if an eighth-note pickup into the next measure was mistakenly placed after the barline with an eighth rest, reposition the pickup to the end of the preceding measure and restore true meter.

---

## Pattern 7: MusicXML Schema Child Sequence for Sibelius Compatibility

### Symptom
Sibelius rejects the imported MusicXML with schema errors such as:
`Line X: Element 'tie': This element is not expected. Expected is one of ( lyrics, play, listen )`

### Cause
Sibelius strictly enforces the W3C MusicXML schema element sequence. Inside `<note>`, child tags MUST appear in exact canonical order:
`grace | cue | chord` $\to$ `pitch | unpitched | rest` $\to$ `duration` $\to$ `tie` $\to$ `instrument` $\to$ `voice` $\to$ `type` $\to$ `dot` $\to$ `accidental` $\to$ `time-modification` $\to$ `stem` $\to$ `notehead` $\to$ `staff` $\to$ `beam` $\to$ `notations` $\to$ `lyric` $\to$ `play` $\to$ `listen`.
Similarly, inside `<notations>`, children must follow:
`tied` $\to$ `slur` $\to$ `tuplet` $\to$ `glissando` $\to$ `slide` $\to$ `ornaments` $\to$ `technical` $\to$ `articulations` $\to$ `dynamics` $\to$ `fermata`...

### Repair
Always run a post-processing sort pass over all `<note>` and `<notations>` elements using a pre-defined tag order map prior to writing output XML, and validate with:
```bash
xmllint --noout --schema "/Applications/Sibelius.app/Contents/Components/MusicXML/musicxml.xsd" score.xml
```

---

## Pattern 8: Double-Chorus & Antiphonal Divisi Scoring

### Symptom
Scores for double choir (e.g. SSAATTBB $\times$ 2 = 16 voices) have sections written on 2 or 4 staves labeled *"Both choirs unis."*, alternating with Choir 1 solo or antiphonal Choir 1 / Choir 2 passages.

### Repair
1. Maintain 16 discrete `<part>` elements (`P1`–`P16`) throughout the entire score to ensure independent MIDI channels and clean part extraction in Sibelius.
2. Implement a `tutti_unison_measure()` builder that clones identical notes and lyrics across the corresponding vocal pairs (e.g. Soprano $\to$ P1, P2, P9, P10; Alto $\to$ P3, P4, P11, P12, etc.).
3. Audit dangling ties across antiphonal section transitions using automated scripts to guarantee zero infinite-sustain playback bugs in Sibelius.

---

## Pattern 9: Redundant Clef Objects at System Breaks (Post-Import Engraving Clutter)

### Symptom
After importing the repaired MusicXML, the Sibelius score shows duplicate clefs mid-bar — typically one at each original system break, repeated across every staff. The page looks cluttered, but playback is unaffected.

### Cause
Scanners emit a full `<attributes>` block, including `<clef>`, at the start of every recognized system. Unstacking (Pattern 1) concatenates those measures end-to-end, so each former line start carries its own clef restatement. Pattern 1 step 5 strips these at the XML level; any that survive — or that Sibelius materializes on import — persist as live `Clef` objects in the score.

### Repair
Operate on the score open in Sibelius, using `clean_clefs.py` (`${CLAUDE_SKILL_DIR}/scripts/`):
1. Audit without modifying anything:
   ```bash
   uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/clean_clefs.py audit
   ```
2. Review the flagged list against the printed page, then purge:
   ```bash
   uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/clean_clefs.py strip --dry-run   # preview
   uv run --project "${CLAUDE_SKILL_DIR}" python ${CLAUDE_SKILL_DIR}/scripts/clean_clefs.py strip             # backs up, deletes, saves
   ```

A clef is flagged when its `styleId` matches the staff's default clef (read from bar 1 of that staff, falling back to inference from the instrument name), or when it sits at or past the end of its bar, computed from that bar's meter. Where either input is unknown the corresponding check is skipped rather than guessed, so the audit under-reports instead of proposing a wrong deletion — see the caveats in the skill's Common Mistakes.

### Not a playback defect
These clefs generate no MIDI events and never cause hanging or droning notes. A score that drones has a tie defect; use the `hanging-playback-note-repair` skill instead.

---

## Pattern 10: Late-Entering Staves Flagged as Stacked Systems

### Symptom
`omr_tool.py audit` reports `Stacked system suspected: True`, and some parts consist mostly of "dummy rest measures" at the start of the piece (for example `P2` rests for bars 1-19 and `P3` for bars 1-26).

### Cause
The audit reads long runs of whole-bar rests as padding. In a genuine ensemble score where voices enter later, the printed page hides empty staves ("hide empty staves"), so the OMR fills those bars with rests. The rests are correct.

### Repair
Check the PDF before unstacking. If later systems show the extra staves singing at the same time, the parts are real: **do not unstack**. Delete only bars that are rests in *every* part and have no printed counterpart, and hide empty staves in Sibelius after import. Check each part's rests in 3/4 or other changed-meter bars: OMR sometimes leaves a hidden staff's rest at the previous meter's length.

---

## Pattern 11: Chords Collapsed to Their Lowest Note

### Symptom
Where the print shows a chord or divisi on one staff (for example D3/A3/D4), the MusicXML has a single note, usually the **lowest** chord member. The melody drops out of that bar, and repeated low notes appear where the tune moves.

### Cause
Some engines (Halbestunde in particular) keep only one notehead of a stacked chord, and the others are lost silently.

### Repair
Compare every printed chord with the XML and rebuild the bar with `<chord/>` notes. Search the PDF for stacked noteheads, especially at cadences and fermatas and in bars where the meter changes. A melody that suddenly repeats a low note is a strong hint.

---

## Pattern 12: Missing Key Signature on a Late-Entering Staff

### Symptom
After import, one staff (typically the last to enter) has no key signature until partway through, and spells its sharps or flats as accidentals. Sibelius reports extra "key changes" to the same key (`score-snapshot` → `keySignatures` lists G major at bars 18 and 32, say). Courtesy key signatures appear at the end of the preceding systems.

### Cause
The OMR omitted `<key>` from that part's first `<attributes>`, then restated it where the staff first became visible. Sibelius turns each restatement into a key-change object.

### Repair
Fix it in the MusicXML: put `<key>` in bar 1 of **every** part and remove `<key>` from later bars unless the key really changes. The bridge cannot delete key-signature objects (they live on the system staff), so re-import rather than patching the live score. After import, `score-snapshot` should list no `keySignatures` for a piece with no key changes (the initial key is not reported).
