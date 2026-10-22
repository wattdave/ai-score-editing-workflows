---
name: vector-pdf-score
description: >
  Turn a vector sheet-music PDF (music is text in a music font, not a scanned image) into MusicXML
  without OMR: exact pitches, rhythms, ties and lyrics read from the glyph positions. Covers PDFs
  exported by Sibelius (Opus or Helsinki font) and by Dorico (Bravura font, 2-staff choral layout,
  with repeats, key and time changes, jumps); fall back to halbestunde-omr for scans, for PDFs from
  MuseScore and for Dorico PDFs printed through "Microsoft Print To PDF" (the glyphs are outlines
  there). Shenandoah (Opus, SATB, 21 bars), three short Opus pieces and a Helsinki one-page choir
  piece were read correctly.
---

# Vector PDF to MusicXML

A PDF exported by Sibelius keeps every note as a glyph at an exact position, so nothing has to be
recognised. Halbestunde (OMR) was wrong on these files (staves swapped, clefs read wrongly,
bars moved between parts); reading the glyphs was exact for pitches.

## 1. Check which kind of PDF it is

```bash
pdfinfo score.pdf | grep -E "Creator|Producer"
uv run --with pymupdf python -I -c "import pymupdf,sys; p=pymupdf.open(sys.argv[1])[0]; print({s['font'] for b in p.get_text('rawdict')['blocks'] for l in b.get('lines',[]) for s in l['spans']})" score.pdf
```

- Font set contains `OpusStd` or `HelsinkiStd` (Sibelius's two music fonts; the reader takes any font
  whose name starts with `Opus` or `Helsinki`): a Sibelius PDF. Both use the same legacy glyph codes
  (noteheads `œ ˙`, rests `Ó Œ ‰`, clefs `& ?`, flags `j J`, dot `™`) and neither is SMuFL (no
  private-use codepoints), so one table serves both. Follow sections 2 and 3 below.
- Font set contains `Bravura` (plus a text font for lyrics): a Dorico PDF. Follow "Dorico PDFs" below.
- Producer is "Microsoft: Print To PDF": the music glyphs were turned into filled outlines (Carol of the Bells
  had 4 music characters on a page of 282 noteheads), so the glyph readers find nothing. Ask for a PDF
  exported from the program itself (File > Export, not Print), or use `halbestunde-omr`.
- Scans, photos and MuseScore PDFs (Leland, Petaluma use SMuFL codepoints) are not covered (MuseScore has not been tried): use `halbestunde-omr`.

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

Tuplets, grace notes, whole notes, 16th rests and
shorter, repeats and voltas, dynamics, hairpins, tempo and expression text, slurs (ignored),
cross-staff notes, key or time changes, more than one verse (read each lyric row yourself),
systems with different numbers of staves (parse with `--staves 1` and assemble the staves by
hand), and stem-sharing chords in two-voice passages, which can come out as a single note: check
every chord bar against the print. Dorico and MuseScore PDFs (different
fonts). The tie rule treats any curve between two same-pitch notes as a tie.

## Dorico PDFs

Tested on one score, Carol of the Bells (145 bars: multi-bar rests, repeats at bars 35-36 and 37-44, a segno,
To Coda, D.S. al Coda, key changes at bars 79 and 113, 3/4 and 2/4 meter changes), in two layouts:

- **Choral score** (`02 - Choral score`): systems of separate S. / A. / T. / B. staves (the tenor staff is a treble
  staff with a small 8 below), systems with a condensed pair of staves (Ch.: treble = soprano and alto, bass = tenor
  and bass, with cue labels such as "(alto only)" and "(S+A)"), and systems with both. **Use this layout.**
- **Choir SATB** (`01 - Choir SATB`): only the condensed pair. It hides the separate S/A/T/B players, so bars 81-116
  (where the choir sings in C major) print as multi-bar rests and the reader gets nothing there. Whenever a
  Dorico score has several layouts, export the one that shows every part, and check the bar numbers against
  another layout's.

```bash
S="${CLAUDE_SKILL_DIR}/scripts"
uv run --with pymupdf python -I $S/dorico_pdf.py score.pdf                    # bars, key, time, repeats found
uv run --with pymupdf python -I $S/dorico_pdf_musicxml.py score.pdf out.musicxml \
  --tempo 144 --tempo-map 35:126          # title, composer and arranger come from the first page
python3 $S/compare_musicxml.py reference.musicxml out.musicxml --map P1=P1,P2=P2,P3=P3,P4=P4   # when a reference exists
```

How well it did, with Dorico's own MusicXML (the For Playback file) as the answer key and nothing copied from it:

| PDF | Notes in both | Only in reference | Pitch, onset, duration, ties differ | Lyrics differ |
|---|---|---|---|---|
| Choral score | 1,285 | 0 | 0 | 8 (extra "oo" vowels the print has, and a misspelled word in the print) |
| Choir SATB | 1,004 | 281 (bars 81-116, not printed) | 0 | 14 |

- **Parts:** soprano, alto, tenor and bass come from the staff labels (S. A. T. B.), or for the condensed pair from
  chords (top and bottom note), stem direction for two rhythms on one staff, and the cue labels for single lines.
- **Key, time and repeats:** key changes, meter changes, repeat barlines, multi-bar rests (the number above the rest
  becomes that many bars), segno, To Coda, D.S. al Coda, the coda, rehearsal marks, text directions (swing and
  straight phrasing, rallentando) and fermatas are written as MusicXML. Sibelius's `play-order` read
  "1-36, 35-44, 37-133, 17-34, 134-145", the right route through the jumps.
- **Scale:** every measurement is relative to the staff space, so the 20 pt Choir SATB and the 13.5 pt Choral score
  exports both read. Text sizes (lyrics, cue labels) are measured from the PDF.
- **Tempo and swing:** the PDF has no metronome mark. Give `--tempo` and `--tempo-map bar:bpm`; the swing feel is
  only a text direction, so use the `swing-playback-copy` skill for a swung recording.

Not covered: layouts other than these (other staff counts, a single staff, cue-size notes), tuplets, grace notes,
whole notes, dynamics, slurs, voltas (1st and 2nd endings), more than one verse. The notehead glyphs (U+F4BE black,
U+F4BD half), staff and stem line widths relative to the staff space (0.125, 0.12), and barlines (0.2, thick 0.5)
are the ones this Dorico version uses; check them first on a different Dorico version.
Dorico PDFs printed through "Microsoft Print To PDF" have outlined glyphs and cannot be read.

## After the MusicXML

Use `lyric-hyphenation` only if syllables came without hyphens. For playback copies see
`playback-divisi-split` (it refuses a staff with two voices in a bar and does not split bass divisi
into extra staves; for those, split by hand: top note to the first staff, bottom note to the last).

## What was verified

- Opus: `vecscore.py` output on Shenandoah and Sail Away Ladies, and the MusicXML for Shenandoah,
  are identical before and after the Helsinki change.
- Helsinki: Sibelius 26.8 export, one page, 2/2, G major, SAB with a solo-staff section, repeat and
  voltas, three lyric verses (Mi Burrito Sabanero). With `--staves auto --clefs auto` every bar's
  pitches, durations (half-bar pickup, dotted quarters, beamed eighths, half and quarter rests) and
  repeat barlines matched a by-eye transcription, for all 3 SAB staves and the 16 bars of the
  single-staff section. Not verified: ties, lyrics and MusicXML output on Helsinki (the page mixes
  system sizes), HelsinkiTextStd/HelsinkiSpecialStd glyphs beyond the dot, whole notes, 16ths.
