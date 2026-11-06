---
name: vector-pdf-score
description: >
  Turn a vector sheet-music PDF (exported from Sibelius, so the music is text in the Opus or
  Helsinki font and not a scanned image) into MusicXML without OMR: exact pitches, rhythms, ties
  and lyrics read from the glyph positions. Use first for any clean PDF whose Creator is Sibelius;
  fall back to halbestunde-omr for scans and for PDFs from other programs. Shenandoah (Opus, SATB,
  21 bars), three short Opus pieces and a Helsinki one-page choir piece were read correctly.
---

# Vector PDF to MusicXML

PDF made by LilyPond (Emmentaler font) with no `.ly` source? Use `lilypond-pdf-score`.

A PDF exported by Sibelius keeps every note as a glyph at an exact position, so nothing has to be
recognised. Halbestunde (OMR) was wrong on these files (staves swapped, clefs read wrongly,
bars moved between parts); reading the glyphs was exact for pitches.

## 1. Check the PDF is a vector PDF from Sibelius

```bash
pdfinfo score.pdf | grep Creator            # "Sibelius version ..." is what this skill has been tested on
uv run --with pymupdf python -I -c "import pymupdf,sys; p=pymupdf.open(sys.argv[1])[0]; print({s['font'] for b in p.get_text('rawdict')['blocks'] for l in b.get('lines',[]) for s in l['spans']})" score.pdf
```

The font set must contain `OpusStd` or `HelsinkiStd` (Sibelius's two music fonts; the reader takes any
font whose name starts with `Opus` or `Helsinki`). Both use the same legacy glyph codes (noteheads
`œ ˙`, rests `Ó Œ ‰`, clefs `& ?`, flags `j J`, dot `™`), and neither is SMuFL (no private-use
codepoints), so one table serves both. Scans, photos and PDFs from Dorico or MuseScore (Bravura,
Leland, Petaluma use SMuFL codepoints) are **not covered**: use `halbestunde-omr`.

A PDF printed through a Windows driver (Creator `PScript5.dll`, `PDFCreator`, `PrimoPDF`) names the fonts
`Opus` and `OpusSpecial` and stores each glyph as its code plus 0xF000 (U+F0CF for the notehead `œ`).
`vecglyph.py` maps those back, so `vecscore.py` reads them like Sibelius's own export. They carry no
"Sibelius" Creator, so judge them by the font name. Checked 2026-11-06 on Stille Nacht, Gaudete and Tourdion
(glyphs and bar sums read; the limits below still apply). Runs of music glyphs that text extraction returns as
"words" are skipped as lyrics (`vecglyph.has_music_code`): left in, they became boxes in the lyric row and took
notes away from real syllables (Alle Psallite Cum Luya).

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

Every bar must add up (16 sixteenths in 2/2 or 4/4). Bars that do not are two voices on one staff, a
missing rest or dot, or a glyph the reader does not know: look at the print at 260 dpi, then give
the bar by hand (below).

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

Helsinki details: stems are 0.60 wide and barlines 0.75 (the reader switches thresholds per page),
and the repeat dots and augmentation dots are the same glyph (repeat dots are told apart by sitting
in a pair on the middle line beside a barline).

## Not handled yet

`vecscore_musicxml.py` still assumes every system has the same staves, so for a mixed page like the
Helsinki test piece it cannot write the whole file: read it with `vecscore.py --staves auto`, and
write the MusicXML by hand or from per-section runs. Voltas (1.2. / 3.) are not read, neither is the
bar count of a multi-bar rest beyond the number printed above it.

Layout quirks the reader now absorbs (Jingle Bells, 2/2, SB, two verses): a bracket or
braces line is not a barline (a barline only one staff of a system has is merged away); a
repeat-start barline right after the clef makes no empty bar; two noteheads a second apart
with the same duration become one chord; and each row of words under a staff is its own
verse (`<lyric number="1">`, `"2"`, ...). Check verse 2 per note: when the rows differ in
rhythm from the first verse, patch the XML by onset (chord members take no lyric).
Repeat signs and endings are still written by hand into the MusicXML
(`<barline><repeat/>`, `<ending number="1" type="start|stop|discontinue">`), as are cut time
(`<time symbol="cut">`) and accents (`<articulations><accent/>`). A bar whose unused voice
prints a half rest beside quarter rests sums too long: give that bar with `--override`.
Whole notes are read (they were counted as quarters), and `--time-changes "8:3/2,9:4/4"` writes a
new time signature at the given measure numbers and checks each bar against its own length (A la
claire fontaine: 4/4 with 3/2 bars). Look at the right end of each system for a printed change:
it applies to the next bar. Triplets still need hand edits (see Sussex Mummers Carol: scale
`<divisions>` by 3, give the three notes `<time-modification>` 3:2 and a `<tuplet>` start and stop).

Flat beams that some PDFs draw as thin filled rectangles (Apple Tree Wassail) count as beams too;
before that, their eighths read as quarters and the bars summed too long.
After importing a piece with a pickup bar and endings, Sibelius can draw the first and second
ending brackets in the wrong place (Apple Tree Wassail: under bars 12-13 instead of 17-18, though
`query --staff system --type Line` shows them on the right bars). Delete both `RepeatTimeLine`
objects with `apply` and add them again (`add-line` on staff 0, `line.system.repeat.1st` and
`.2nd`, same bar, position 0, same duration); the score must be saved first.
Ligatures (U+FB01) and a stray `>` or `&quot;` in a lyric need a search and replace.

Tuplets, grace notes, 16th rests and
shorter, repeats and voltas, dynamics, hairpins, tempo and expression text, slurs (ignored),
cross-staff notes, key or time changes, more than one verse (read each lyric row yourself),
systems with different numbers of staves (parse with `--staves 1` and assemble the staves by
hand), and stem-sharing chords in two-voice passages, which can come out as a single note: check
every chord bar against the print. Dorico and MuseScore PDFs (different
fonts). The tie rule treats any curve between two same-pitch notes as a tie.

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
