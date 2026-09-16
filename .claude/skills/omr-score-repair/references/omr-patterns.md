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
