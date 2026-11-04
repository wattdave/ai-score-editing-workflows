---
name: lilypond-pdf-score
description: >
  Turn a PDF engraved by LilyPond (Emmentaler music font, as on Mutopia, CPDL and IMSLP) into
  MusicXML by reading glyph names and positions, when the .ly source is not available and a scan
  would be poor. One voice per staff (SATB on four staves). Reads notes, rests, dots, flags, beams,
  ties, accidentals, ficta, clefs, key, time-signature changes, pickups and lyrics, and checks the
  result against the piece's own MIDI. Use for a LilyPond-made PDF with no source; use
  lilypond-to-score when the .ly exists and vector-pdf-score for Sibelius PDFs.
---

# LilyPond PDF to MusicXML

A LilyPond PDF keeps every notehead, rest, flag and accidental as a font glyph at an exact
position, so nothing has to be recognised. On a Renaissance piece (Brumel, 62 bars) Halbestunde's
scan was unusable; the glyph read matched the print. Validation on three more LilyPond PDFs is at
the end.

## 1. Check the PDF

```bash
pdfinfo score.pdf | grep Creator      # "LilyPond 2.x" (a re-saved file says Preview or similar)
```

Fonts: `Emmentaler-NN` (music), `feta-alphabet` (digits), `CenturySchL` (text). If the source `.ly`
exists, use `lilypond-to-score`. If the site also ships a **MIDI** (Mutopia and many CPDL pages do),
download it: `check_midi.py` below uses it as ground truth.

**Limits.** One voice per staff, no chords, only the simple triplet (below). A system may show
fewer staves than voices when LilyPond hides resting staves: each staff is then matched to its voice
by the name or abbreviation printed in the left margin (first three letters). Two voices on one staff (tenor and bass sharing a bass staff) or a grand staff stops with
"notes overlap ... one voice per staff". Pages that are not voice systems (a piano practice
reduction, a translation) are skipped with `--pages 1`.

Sources: Cloudflare blocks `curl` on cpdl.org and imslp.org (a "Just a moment" 403), so fetching
from there needs a real browser. With Claude in Chrome the check clears by itself after about five
seconds (wait, then read the page); list a page's files with `javascript_tool`
(`[...document.querySelectorAll('a')].filter(a=>/\.(pdf|mid|zip)/i.test(a.href))`) and download by
clicking a generated `<a download>`; the file lands in ~/Downloads. CPDL search for
`lilypond SATB Renaissance` lists hundreds of editions, and a `-source.zip` usually holds the `.ly`
and the score's MIDI. mutopiaproject.org downloads with plain `curl` and is always LilyPond.

## 2. How it reads

`reader.py` takes glyph ids from `page.get_texttrace()` and turns them into **names** (`noteheads.s2`,
`rests.1`, `flags.u3`, `accidentals.flat`, `clefs.G`, `dots.dot`, `timesig.C22`) through the glyph order
of the embedded CFF font. Names make the reader independent of LilyPond version (tested on 2.8.7
and 2.12.2) and font size (every metric scales with the notation size).

- **Offset.** For a file written by LilyPond, glyph id = index in the name list. A file re-saved by
  macOS Preview drops `.notdef` from the numbering (id = index - 1) and loses the name of the last
  glyph of each font subset. `calibrate_offset` picks the offset that turns most glyphs into
  noteheads. In a Preview file the unnamed small glyph is the ficta flat (handled in `build.py`).
- **Pitch.** Half-space index `hs = (bottom_line_y - y) / (space / 2)`. The clef glyph's own position
  gives the reference line (G = G4, F = F3, C = C4), so G, F and C clefs on any line work. The "8"
  under a treble-8 clef is a small italic text character, not a glyph; it moves the pitch down an
  octave (MusicXML pitch is sounding pitch). Override with `--clefs G,G,G8,F`.
- **Incipits** (the original-clef start of an edition) use mensural noteheads and are skipped:
  only the exact modern notehead names count, and the clef in force is the one nearest the first
  sung note.
- **Durations.** Notehead kind, dots, flags (`flags.u3` one flag, `u4` two), and beams. Level beams
  are plain filled rects (1.2 to 3 pt thick), slanted beams filled polygons; both are listed twice
  (fill and stroke), so deduplicate before counting.
- **Ties.** A filled curve from one head to the next head of the same pitch is a tie; a stub ending
  at the first note of a system is a tie over the system break. Ties merge into one longer note.
  Slurs are not read.
- **Accidentals.** `accidentals.flat/sharp/natural` left of a note on the same line. The first
  |fifths| accidentals after the clef are the key signature and are not note accidentals (an
  explicit flat right after the key signature is: it was missed once, see below). Small (about 12.5
  pt) accidentals above the staff are editorial **ficta**, valid for that note only. The small
  "L" is an editorial bracket, not a sharp.
- **Key, time, pickup.** Read from the first system: the run of accidentals before the first note,
  `timesig.*` or two stacked digits. A half-bar start gives an implicit first measure. Every
  time-signature change in the piece is found and written (4/2 to 2/2 to 6/2 worked).
- **Triplets.** A small "3" just outside the staff (1 to 3 staff spaces; one inside the staff is a
  proportion sign) makes the three events nearest its centre 2/3 length. The MusicXML uses 12
  divisions per quarter and a 3:2 time-modification. Only the 3:2 case is read (no 6 or 5, no
  bracket check).
- **Whole-bar rests.** A whole rest centred between two barlines is a rest for the whole bar, which can
  be longer than a whole note (a bar of 6 or 8 beats); its length is the usual bar sum of the other
  staves.
- **Unbarred or thinly barred editions.** If a system has no barlines to read, its start is the
  previous start plus the staff totals (no grid snapping), and time-signature changes still come
  from the printed signs.
- **System timing.** Onsets are summed per staff; each system's start is snapped to the barline
  grid on the shortest usual bar length (bars may change length); lead-in rests invisible at the start
  of a system are anchored on columns shared with the other voices. `onset2.py` prints per-system
  totals and misaligned columns; it must say **0 misaligned** before you go on (a few misaligned
  columns pointed at a missed beam, a missed tie, or a missed 16th rest).
- **Mensurstriche** (barlines between staves only, notes crossing them): the MusicXML uses regular
  bars with ties across barlines; barline x positions are not used to assign bars.

## 3. Lyrics

For a file written by LilyPond the text layer is usable: characters are read as they are, words are
split by text span (LilyPond writes each word as its own span; a gap rule alone glued "brief temps"),
hyphens are drawn rects (about 2.3 wide, 0.22 high), and each syllable goes to the nearest unused
note. Words may sit up to 14 pt plus 0.3 of their width from the note (long words such as "fraine,"
were dropped at 14). Bar numbers share the text font and are skipped. An **elision** (`re~e` in the
source, two syllables on one note) is marked by a `ties.lyric.default` glyph between the two
words; they are joined as `re‿e` on that note. Words that find no note are collected in
`build.DROPPED` (page, staff, text, x, y, distance): print it after a run, it should be empty.
Checked against the `.ly` lyrics for Secretz regretz (Superius and Contra exact; Tenor and Bassus
differ only by the `ij.` repeat text the print omits).

A **re-saved** PDF can have a scrambled text layer (the Brumel PDF): copying text gives nonsense.
Pass `--scrambled`; letters then come from a glyph-id to letter table in `lyr.py` (`SH`), which is
for the Brumel PDF only. For another scrambled PDF, pull the lyric font (`doc.extract_font`),
render its glyphs to a contact sheet with their ids, and write a new table.

Known gaps: a syllable more than about 14 pt from its note is dropped (seen: "fraine" and a few words
of a repeated phrase in a lute song), some hyphens are missing, and extender lines are not read.
Check every word against the print.

## 4. Run it

```bash
S=/Users/wattd/dev/ai-score-editing-workflows/.claude/skills/lilypond-pdf-score/scripts
run() { uv run --with pymupdf --with fonttools --with mido python -I "$@"; }
run $S/extract.py score.pdf 4 [pages]        # bar sums per staff per system: each should add up
run $S/onset2.py  score.pdf 4 [pages]        # 0 misaligned columns
run $S/mxl.py score.pdf out.musicxml --title "Title" --composer "Name" --names S,A,T,B \
    [--pages 1] [--clefs G,G,G8,F] [--fifths -2] [--time 4/4] [--no-pickup] [--scrambled]
run $S/check_midi.py out.musicxml score.mid     # exact pitches, accidentals, ties vs the MIDI
#   a MIDI that plays a repeat or volta the print writes once is longer: the checker accepts it when the
#   notes after the first difference are exactly the MIDI's last notes (repeats are not written to the XML)
run $S/check_midi.py score.pdf score.mid        # reader level, before writing XML
```

`check_midi.py` matches each part to a MIDI track and reports the first differing note. Read it
with care: (1) MIDI often unfolds repeats, so a read that stops where the print has a repeat sign
is expected; (2) the MIDI can be an octave off the print for treble-8 voices (an alto an octave
high and a tenor an octave low in one test file): the clef printed in the PDF decides the octave,
not the MIDI.

## 5. Import and proofread (Sibelius)

Import with `OpenScore` (the "Open MusicXML File" dialog needs a click on OK, see the `sibelius`
skill), then `ExportScore ... SIBL`. Compare **every bar of every voice against the print**,
page by page, at 200 dpi, looking for explicit accidentals especially: the first run on the
Brumel piece dropped a flat that sat right after the key signature at the start of a system
(Cantus bar 44, A flat) and a proofread by eye did not catch it; the glyph list did.

Fix in place with `apply`: `set-pitch` for a note, `delete` (type LyricItem) plus `add-lyric` for
words (syllableType only `middle` or `end`).

## Validation (Mutopia, LilyPond 2.12.2 unless noted)

All compared with the MIDI each piece ships; Brumel (LilyPond PDF re-saved by Preview) was
compared with the earlier hand-proofread score.

| Piece | Layout | Result |
|---|---|---|
| Il Est de Bonne Heure Ne (anon., c.1470) | SATB, 2/2, pickup, repeats, treble-8 tenor, beamed eighths and sixteenths, ties over system breaks; page 2 is a piano practice staff (skipped) | All 4 parts match the MIDI note for note (72, 67, 62, 68 notes), onsets and accidentals |
| Unquiet Thoughts (Dowland) | SATB lute-song layout, two flats, 2/1 | All notes match; the MIDI (89, 104, 108, 83 notes) plays the repeat and the first-time ending, and the checker confirms the print's last notes equal the MIDI's ending. Repeat signs and voltas are not written to the MusicXML |
| Come Again (Dowland) | SATB, 4/2 to 2/2 to 6/2 | All 4 parts match the MIDI (43, 45, 49, 44 notes); time changes written |
| Nuz my dzis krzescijani (2.8.7) | S, A, and T+B sharing one bass staff | Refused with a clear message (two voices on a staff) |
| Obrecht, Missa Malheur me bat, Kyrie (CPDL, LilyPond 2.18.2) | SATB, 3/2, 4/4 and cut-C, treble-8 voices, hidden resting staves, 3:2 triplets, longas, an unbarred Kyrie II | All 63, 236, 233 and 196 notes match the MIDI pitch for pitch (the MIDI splits Kyrie I and the rest into tracks i and i+4; join them), 0 misaligned columns. The 2021 Finale MusicXML on CPDL matches too except it drops one longa-plus-note in the bass and times some bars differently, so it is not a ground truth |
| de la Rue, Secretz regretz (CPDL, 2.18.2) | SATB, 4/2, no pickup, mensural incipits at the left, neomensural breves and longas in the music, unusual thin barlines through all four staves | All 4 parts match the MIDI from the source zip (147, 132, 101, 109 notes) exactly, including accidentals and ties |
| Bianciardi, Ego dormivi (CPDL, 2.22.1) | Same editor and layout, one flat, ficta, breves | All 4 parts match the MIDI (147, 168, 174, 99 notes) exactly |
| Brumel, Du tout plongiet (Preview-saved) | 4 staves, mensural incipit, cut-C | Identical to the proofread score except one explicit A flat (bar 44, Cantus) that the first reader dropped |

Found on the CPDL files (and now handled): some editions draw breves with the **neomensural** shape
(`noteheads.sM1neomensural`, `srM1neomensural`; longas are `uM2/dM2/urM2/drM2neomensural`); the
incipit left of the first modern clef holds mensural time signs, clefs (`clefs.petrucci.*`) and
a couple of heads, all dropped; barlines can be very thin rects running through every staff of the
system (recognised by height, not width); `brackettips.*` are the system bracket, not ligatures
(I first misread them as ligature brackets, which sent me looking in the wrong place). A clef change
inside the piece is applied to the notes after it, but the MusicXML only carries the opening clefs
(pitches right, clef sign not repeated).

What the validation changed in the code: glyph names instead of ids; sizes scaled; ties and beams
(rect beams) read; pickup grid; bar-length changes; time-signature changes; incipit skipped;
clef and key found from the print; key signature kept apart from note accidentals.
