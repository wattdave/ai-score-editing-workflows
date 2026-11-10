---
name: vector-pdf-score
description: >
  Turn a vector sheet-music PDF (exported from Sibelius, so the music is text in the Opus or
  Helsinki font and not a scanned image) into MusicXML without OMR: exact pitches, rhythms, ties
  and lyrics read from the glyph positions. Use first for any clean PDF whose Creator is Sibelius;
  fall back to omr-halbestunde for scans and for PDFs from other programs. Shenandoah (Opus, SATB,
  21 bars), three short Opus pieces and a Helsinki one-page choir piece were read correctly.
---

# Vector PDF to MusicXML

PDF made by LilyPond (Emmentaler font) with no `.ly` source? Use `lilypond-pdf-score`.

A PDF exported by Sibelius keeps every note as a glyph at an exact position, so nothing has to be
recognised. Halbestunde (OMR) was wrong on these files (staves swapped, clefs read wrongly,
bars moved between parts); reading the glyphs was exact for pitches.

## 1. Check the PDF is a vector PDF from Sibelius

Quick triage of any PDF (scan or vector, and which program made it): `uv run --with pymupdf python -I "${CLAUDE_SKILL_DIR}/scripts/pdf_source_check.py" file.pdf [more.pdf] [-v]`. It reports page images, vector drawings, staff lines and the music font, and names the skill that can read it.

```bash
pdfinfo score.pdf | grep Creator            # "Sibelius version ..." is what this skill has been tested on
uv run --with pymupdf python -I -c "import pymupdf,sys; p=pymupdf.open(sys.argv[1])[0]; print({s['font'] for b in p.get_text('rawdict')['blocks'] for l in b.get('lines',[]) for s in l['spans']})" score.pdf
```

The font set must contain `OpusStd` or `HelsinkiStd` (Sibelius's two music fonts; the reader takes any
font whose name starts with `Opus` or `Helsinki`). Both use the same legacy glyph codes (noteheads
`œ ˙`, rests `Ó Œ ‰`, clefs `& ?`, flags `j J`, dot `™`), and neither is SMuFL (no private-use
codepoints), so one table serves both. Scans, photos and PDFs from Dorico or MuseScore (Bravura,
Leland, Petaluma use SMuFL codepoints) are **not covered**: use `omr-halbestunde`.

A PDF printed through a Windows driver (Creator `PScript5.dll`, `PDFCreator`, `PrimoPDF`) names the fonts
`Opus` and `OpusSpecial` and stores each glyph as its code plus 0xF000 (U+F0CF for the notehead `œ`).
`vecglyph.py` maps those back, so `vecscore.py` reads them like Sibelius's own export. They carry no
"Sibelius" Creator, so judge them by the font name. Checked 2026-11-06 on Stille Nacht, Gaudete and Tourdion
(glyphs and bar sums read; the limits below still apply). Runs of music glyphs that text extraction returns as
"words" are skipped as lyrics (`vecglyph.has_music_code`): left in, they became boxes in the lyric row and took
notes away from real syllables (Alle Psallite Cum Luya).

Ghostscript-converted copies of those PDFs rename the fonts (`TT1F7t00`, `TT204t00`, `TT206t00`: Ghostscript 8.15, Creator `PScript5.dll`); the reader accepts any span made only of U+F0xx codes as music (`vecglyph.is_music_font`), so the names do not matter (Non Nobis Domine, Nou Is Yole, Ther Is No Rose).

Then look at the pages (render at 100 dpi and read the picture) and note: staves per system and
which voice each is, clefs (a treble clef with a small 8 below is a tenor: `G8`), key, time, tempo,
pickup bar, repeats, bars where one staff carries two voices, and lyrics that belong to no staff.
Ask the user for staff roles when the print does not label them.

## 2. Dump the bars and read the sums

```bash
uv run --with pymupdf python -I "${CLAUDE_SKILL_DIR}/scripts/vecscore.py" score.pdf --staves 4 --clefs G,G,G8,F
```

For pages whose systems differ in size (a solo staff beside three-staff systems), use
`--staves auto --clefs auto`: systems are found from the thin line joining the staves at the left,
and each clef from its `&` or `?` glyph (it never finds `G8`, so a tenor needs `--clefs`). The dump
marks repeat starts (`|:`), repeat ends, double and final barlines, and multi-bar rests (`x7bars`).

Every bar must add up (16 sixteenths in 2/2 or 4/4). A bar with two voices on one staff prints as
`sum 12+12  v1: ... | v2: ...` (see Two voices below). Bars that do not add up are a missing rest or
dot, or a glyph the reader does not know: look at the print at 260 dpi, then give the bar by hand (below).

**Two voices on one staff** (`--split-voices auto`, the default in both scripts; `off` gives the old
merged reading). A bar is split when a stem-up and a stem-down note sound together, or a rest sits off
its usual height on the other voice's side. Stems up are voice 1, stems down voice 2; a shared
notehead (unison, two stems) is in both; noteheads on one stem stay a chord; each stem's beams and
flags give its duration, so a 16th beside a dotted 8th reads right. Bars whose two voices have the
same rhythm stay one voice of chords. The writer emits `<voice>1/2` with `<backup>`, fills a voice
with no printed rest by `print-object="no"` rests (reported as "hidden rests added in N bars": check
those against the print), and puts lyrics on voice 1 (voice 2 only where voice 1 has no note).

## 3. Write MusicXML

```bash
uv run --with pymupdf python -I "${CLAUDE_SKILL_DIR}/scripts/vecscore_musicxml.py" score.pdf out.musicxml \
  --parts Soprano,Alto,Tenor,Bass --clefs G,G,G8,F --key 2 --time 4/4 --tempo 60 \
  --title "Title" --composer "arr. Name" [--override bars.json] [--copy-lyrics 1:2]
```

- `--key` is the number of sharps (negative for flats); notes in the key signature get their
  accidental from it.
- `--override` is a JSON list for bars the reader cannot sum, for example two voices:
  `[{"page":1,"sys":1,"part":3,"bar":2,"voices":[[{"p":["F3"],"dur":4,"x":418.8}, ...],[...]]}]`
  (`dur` in sixteenths, `x` is only used to place lyrics, `p` is a list of note names; an empty list is a rest).
  `page`, `sys` and `bar` count from 0, `part` from the top staff of a system.
- `--copy-lyrics FROM:TO` copies one staff's syllables onto another staff that has none in a system.
- Lyric rows: by default every row that follows the one before it under a staff is kept (the first
  within 48 pt), up to the next staff, so verses 3 and 4 are read; skipped rows are printed. A footer or
  copyright line and tokens with `=` are never lyrics. `--lyric-reach 90` sets a fixed reach instead.
  `--skip-word "Revels,"` (repeatable) or `--skip-words skip.json` (a JSON list) for words with commas.
- What the print has but the reader cannot see: `--metronome dotted-quarter=60` (or `half=86`; the
  sound tempo is written in quarters), `--tempo-text Langsam`, `--cut-time`, `--breaks 5,9,p13`
  (system starts, `p` = page), `--final-barline`, `--abbrevs S/A,T/B`, `--rights auto` (the copyright
  line printed on the page, verbatim; nothing when none is printed), and `--patch patch.json`:
  `[{"type":"fermata","measure":14,"part":1,"beat":3}, {"type":"slur","measure":2,"from":1,"to":2.5},
  {"type":"barline","measure":8,"style":"repeat-end"}, {"type":"volta","number":1,"from":7,"to":8},
  {"type":"rehearsal","measure":5,"text":"A"}, {"type":"words","measure":1,"text":"Solo"},
  {"type":"dynamics","measure":1,"part":2,"text":"mf"}]` (measures as numbered in the output, parts
  from 1, beats in quarters from 1; `voice` defaults to 1, `note` (0-based) may replace `beat`).
- Fermatas (`U` above, `u` below) are read and put on the note under them. A whole note beside a
  stemmed note (unison or not) is a second voice. Pages that print the dot as `.` (no `™`) are read.
- Beams are not written: run `beaming-repair` (`fix_beams.py --scope all`).
- **Name parts Soprano, Alto, Tenor, Bass (with numbers), never "Women" or "Men".** Sibelius picks the
  instrument from the part name on import; generic names give staves without a vocal range
  (everything below F3 flagged out of range, no choir sound).
- Tenor staves are written an octave lower than printed (`G8`), because MusicXML pitch is sounding
  pitch. Check the first tenor note after import (a written A4 must read MIDI 57, not 69).

Then import the file (see the `sibelius` skill; Sibelius raises an "Open MusicXML File" dialog that
needs OK), save, and **compare the render with the PDF**: `verify-render --format pdf`, then page
by page, and `read-lyrics --compact` per staff. A lyric a word too far left, a missing syllable or a
dangling hyphen are the usual faults; patch them with `delete-object` plus `add-lyric`.

## What it reads

Noteheads (quarter, half), stems, beams (filled quadrilaterals), flags, dots, rests (whole bar,
half, quarter, eighth), chords (noteheads sharing an x), ties (curve drawings that start on a note
and end on the next note of the same pitch), barlines, a pickup bar and lyrics (words under a
staff, hyphens as separate words, matched to the nearest note, greedy and one word per note),
accidentals (sharp, flat and natural glyphs left of a notehead, held for the rest of the bar) and
notes up to 4.2 staff spaces off the staff (ledger-line notes, for example E3 under a treble staff).

Opus line widths scale with the staff size (barline 0.66 at 4.25 pt staff spacing, 0.60 at 3.8), so the stem/barline cut is 0.125 x staff space (`vecglyph.stem_barline_cut`); a fixed 0.6 found no barlines in Here's a Health or In Dulci Jubilo.

Helsinki details: stems are 0.60 wide and barlines 0.75 (the reader switches thresholds per page),
and the repeat dots and augmentation dots are the same glyph (repeat dots are told apart by sitting
in a pair on the middle line beside a barline).

## Limits

**Read correctly now**
- Several staves per system, and a bracket or brace line (a barline only one staff has is merged away).
- A repeat-start barline after the clef (no empty bar); a pickup bar.
- Seconds: two noteheads a second apart with the same duration become one chord.
- Whole notes; flat beams drawn as thin rectangles (Apple Tree Wassail).
- One verse per row of words under a staff (`<lyric number="1">`, `"2"`, ...).
- Meter changes, with `--time-changes "8:3/2,9:4/4"` (measure numbers as in the output). A change
  printed at the right end of a system applies to the next bar.

**Read, but finish by hand in the MusicXML**
- Repeats, endings and double barlines: the dump marks them, the writer does not emit them. Use
  `<barline><repeat/>` and `<ending number="1" type="start|stop|discontinue">`.
- Cut time (`<time symbol="cut">`), accents (`<articulations><accent/>`).
- Triplets: scale `<divisions>` by 3, give the three notes `<time-modification>` 3:2 and a
  `<tuplet>` start and stop (Sussex Mummers Carol).
- Lyrics: a verse printed inline after another (Sussex) needs its `number` changed; verse 2 with a
  different rhythm needs patching by onset (chord members take no lyric); ligatures (U+FB01), a
  stray `>` or `&quot;`, and words that fit no note (an elided "a long") need a search and replace.
- A bar whose unused voice prints a half rest beside quarter rests sums too long: use `--override`.
- Ties: any curve between two same-pitch notes counts as a tie. Ties inside a two-voice bar are
  not read; add them by hand.
- Two voices on a staff: read (Stille Nacht, both Midnight Clears, Parting Glass, Somerset Wassail,
  Gloucester RVW, Die Ehre Gottes), but a hidden rest is placed by matching x with the other voice:
  check bars where the reader reports hidden rests. Slanted beams on a few stems still read as
  quarters (Die Ehre Gottes, bar 21).

**Not read**
- Tuplets in the reader, grace notes, 16th rests and shorter, key changes, voltas as objects,
  dynamics, hairpins, tempo and expression text, slurs (use `--patch`), cross-staff notes, the bar count of a
  multi-bar rest beyond the number printed above it.
- Systems with different numbers of staves: `vecscore_musicxml.py` assumes every system has the
  same staves. Read a mixed page with `vecscore.py --staves auto` and assemble the MusicXML from
  per-section runs.
- PDFs from Dorico or MuseScore (different fonts): use `omr-halbestunde`.

**Seen in the Nelson Carol Book run (check your piece; use `--override` with explicit voices)**
- A bar with a chord, a shared rest and one unison note (two stems on the single head) can be
  split into two voices wrongly: give it one voice.
- A whole note over half notes of the other voice (no stem on the whole) can merge with them
  into one chord.
- A bar split by a double barline inside the measure is listed as "BAR SUM" though the pair adds
  up; the notes are right.
- A word printed with an extender and no hyphen reads as two words (see `lyric-hyphenation`).
- Verse numbers, extender lines and the brace are not emitted (they are drawn by hand in the
  editor; see the recipes in `sibelius`). Composer + arranger credits: use `--merge-credits`.

**After import (Sibelius)**
- With a pickup bar and endings, Sibelius can draw the first and second ending brackets in the
  wrong place (Apple Tree Wassail: under bars 12-13 instead of 17-18, although
  `query --staff system --type Line` shows the right bars). Save the score, delete both
  `RepeatTimeLine` objects with `apply`, and `add-line` them again on staff 0 (`line.system.repeat.1st`
  and `.2nd`, same bar, position 0, same duration).

## After the MusicXML

Use `lyric-hyphenation` only if syllables came without hyphens. For playback copies see
`playback-divisi-split` (it refuses a staff with two voices in a bar and does not split bass divisi
into extra staves; for those, split by hand: top note to the first staff, bottom note to the last).

## What was verified

- Opus: `vecscore.py` output on Shenandoah and Sail Away Ladies, and the MusicXML for Shenandoah,
  are identical before and after the Helsinki change.
- Opus, 6/8 (Fortune plango vulnera, Sibelius 7.1.3 export, three treble staves, 85 bars, Latin lyrics): after
  the left-edge and whole-bar-rest fixes every bar sums to the bar length and the first note of each system
  is read. Not run on the older test PDFs after the change.
- Helsinki: Sibelius 26.8 export, one page, 2/2, G major, SAB with a solo-staff section, repeat and
  voltas, three lyric verses (Mi Burrito Sabanero). With `--staves auto --clefs auto` every bar's
  pitches, durations (half-bar pickup, dotted quarters, beamed eighths, half and quarter rests) and
  repeat barlines matched a by-eye transcription, for all 3 SAB staves and the 16 bars of the
  single-staff section. Not verified: ties, lyrics and MusicXML output on Helsinki (the page mixes
  system sizes), HelsinkiTextStd/HelsinkiSpecialStd glyphs beyond the dot, whole notes, 16ths.

## Ficta (editorial accidentals above the notes)

Renaissance and early-music editions print **ficta** as a small accidental *above* the staff, over
the note it changes and for that note only. It is not a printed-in-the-staff accidental, and it must
not be rendered as one. Sibelius and Dorico both ignore `<accidental-mark placement="above">` on
import and draw the accidental in the staff (checked on Brumel, *Du tout plongiet*, 2026-11-04;
MuseScore imported the pitches correctly but its engraving was not looked at). So after import:

- Keep the sounding pitch right (the `<alter>` carries it); do not add `<accidental>` for a ficta.
- Write `<notations><accidental-mark placement="above">flat|sharp|natural</accidental-mark></notations>`
  on the note so the information survives in the MusicXML (`lilypond-pdf-score` does).
- **Sibelius:** save the import as `.sib`, then for each ficta note run
  `sibelius-cli ficta --staff S --bar B --index I --accidental flat|natural|sharp` (and `--remove` to
  undo). It puts the sign above the note and hides the staff accidental, as Sibelius's own Add Ficta
  plug-in does. List the marks with `uv run python .claude/skills/lilypond-pdf-score/scripts/list_ficta.py file.musicxml` (staff, bar, position, pitch); give it `--query q.json --editor sibelius|musescore|dorico` (the editor's `query` output for the whole score) to get the ready-to-run `ficta` batch. It matches by staff, bar, position and pitch, so no hand-counted indices.
- **Dorico:** `dorico-cli apply` with `{"op":"ficta","id":N,"accidental":"flat"|"natural"|"sharp"}` (address the
  note by `id`). It hides the staff accidental and attaches a playing technique above the note; the project
  needs three custom techniques first (see the dorico skill, "Ficta").
- **MuseScore:** `musescore-cli apply` with `{"op":"ficta","staff":S,"bar":B,"index":I,"type":"NoteRest","position":P,"accidental":"flat"|"natural"|"sharp"}` (bridge v11). It hides the staff accidental and adds the sign as staff text above the note; `"remove":true` undoes it. The added text takes an index in the bar, so query again between batches.

## PDFs engraved by MusiXTeX (TeXMUSIX fonts)

Typeset-by-TeX scores (many IMSLP and hymnal PDFs) use `TeXMUSIX20-Regular` and the slur fonts `TeXXSLU/XSLD/XSLZ20`, not Opus. There is no Sibelius-style glyph reader for them, but the vectors are exact: read them with PyMuPDF and write MusicXML from a script (worked example: [references/musixtex-build-example.py](references/musixtex-build-example.py), Reinecke *Silent Night*, 12 bars, two parts, 4 lyric verses).

1. `uv run --with pymupdf python3 -I` : `page.get_texttrace()` gives each glyph's Unicode and origin (x, y); `page.get_drawings()` gives the staff lines (thin horizontals) and stems/flat beams (rectangles).
2. The PDF's Unicode is not the MusiXTeX code. Extract the font (`doc.extract_font(xref)`, a Type 1 program) and read its `dup N /glyphname put` lines: N is the code, then look it up in [references/musixtex-code-table.md](references/musixtex-code-table.md).
3. Pitch from y: `steps = round((bottom_line_y - head_y) / (line_spacing / 2))` above the bottom line (treble: E4, bass: G2). Rhythm from head type, dots, flags (codes 40/41/45) and beams; check every bar sums.
4. Lyrics are ordinary text in a text font; assign to notes by x.
5. Verify the result against the PDF page image before importing, and run the audit/beaming skills as for any other source.

## Finale PDFs (Petrucci music font)

Finale's legacy `Petrucci` font uses the same glyph codes as Opus (notehead `œ`, half `˙`, whole `w`, `&` and `?` clefs), so the reader accepts it, with these differences (checked on one 4-page SSA + piano score, Belliston *O Holy Night*, 12/8):

- Stems and barlines are drawn at the same width. A barline is a vertical that starts exactly on a staff's top line and ends exactly on a staff's bottom line (the other staff's, on a grand staff) and does not end on a notehead.
- Beams are filled three-line shapes, and the down-stem flag glyph `J` sits further from the staff than Sibelius's.
- Two noteheads on opposite sides of one stem (a second) are one chord; a dot beside only one of them dots the chord.
- A lone whole rest fills the bar whatever the meter (12/8: 24 sixteenths), so a first bar of rests is not a pickup.
- An 8vb line (one long dashed path below the bass staff) lowers the heads over it by an octave, so the MusicXML sounds right; the 8vb bracket is not redrawn.
- Piano staves may both be bass clef (`--clefs G,F,F`): read the clef off the print.
- Still read by hand: a bar with a second voice the reader splits wrongly (use `--override`, as for any unsummable bar), the volta brackets, and verse labels such as "SSA" or "Soloist I" (`--skip-word`).
