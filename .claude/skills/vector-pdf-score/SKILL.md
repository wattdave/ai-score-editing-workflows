---
name: vector-pdf-score
description: >
  Turn a vector sheet-music PDF (exported from Sibelius, so the music is text in the Opus font and
  not a scanned image) into MusicXML without OMR: exact pitches, rhythms, ties and lyrics read
  from the glyph positions. Use first for any clean PDF whose Creator is Sibelius; fall back to
  halbestunde-omr for scans and for PDFs from other programs. Shenandoah (SATB, 21 bars) and
  three short pieces came out right with it.
---

# Vector PDF to MusicXML

A PDF exported by Sibelius keeps every note as a glyph at an exact position, so nothing has to be
recognised. Halbestunde (OMR) was wrong on these files (staves swapped, clefs read wrongly,
bars moved between parts); reading the glyphs was exact for pitches.

## 1. Check the PDF is a vector PDF from Sibelius

```bash
pdfinfo score.pdf | grep Creator            # "Sibelius version ..." is what this skill has been tested on
uv run --with pymupdf python -I -c "import pymupdf,sys; p=pymupdf.open(sys.argv[1])[0]; print({s['font'] for b in p.get_text('rawdict')['blocks'] for l in b.get('lines',[]) for s in l['spans']})" score.pdf
```

The font set must contain `OpusStd`. Scans, photos and PDFs from Dorico or MuseScore are **not
covered** (their music fonts have other glyph codes; verifying them is still to do): use
`halbestunde-omr`.

Then look at the pages (render at 100 dpi and read the picture) and note: staves per system and
which voice each is, clefs (a treble clef with a small 8 below is a tenor: `G8`), key, time, tempo,
pickup bar, repeats, bars where one staff carries two voices, and lyrics that belong to no staff.
Ask the user for staff roles when the print does not label them.

## 2. Dump the bars and read the sums

```bash
uv run --with pymupdf python -I "${CLAUDE_SKILL_DIR}/scripts/vecscore.py" score.pdf --staves 4 --clefs G,G,G8,F
```

Every bar must add up (16 sixteenths in 4/4). Bars that do not are two voices on one staff, a
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

## Not handled yet

Tuplets, grace notes, whole notes, 16th rests and
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
