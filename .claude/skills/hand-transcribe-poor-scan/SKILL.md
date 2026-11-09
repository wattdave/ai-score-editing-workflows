---
name: hand-transcribe-poor-scan
description: >
  Decide whether a bad scan (photocopy, warped or skewed page, OMR that scrambles staves) can
  be transcribed by hand, and how: triage first, then read crops at full resolution, build
  MusicXML from a token text file instead of editing OMR output, and compare renders page by page.
  Use when omr-halbestunde and omr-musescore-convert both give scrambled parts, shifted bars or
  empty results, or before spending hours on a speckled photocopy with piano reductions.
---

# Hand transcription of a poor scan

From Pat-a-pan (done), Riu Riu Chiu (done), Fum Fum Fum (OMR plus hand rebuild), and two pieces
that were **not** done: The Christmas Song and O Holy Night. The expensive failure was
starting without checking readability: about 2 h of cropping produced no score.

## 1. Triage before you start (10 minutes)

1. Render at 300 dpi (`pdftoppm -r 300`), look at one system at full size.
2. Readable: vocal staves with clear noteheads, stems and lyrics. Not readable even at 300 dpi:
   stacked ledger-line chords, 3-note clusters, cross-staff beams, hollow heads lost in speckle,
   whole piano reductions of a photocopy.
3. If the voices are readable but the piano is not, or the page is a speckled photocopy,
   **ask for a clean source** (director, publisher, a vector PDF) before scheduling the piece, and
   say which parts are the problem. Never invent music: mark unreadable bars in a `todo.md` in the
   piece folder (bar, part, what is unclear) and stop.
4. Keep the OMR output only as a cross-check and bar map (below).

## 2. Read the print

- Crop each system at 300 dpi with PIL. A grid overlay with pixel rulers makes crops reliable;
  the preview PNG coordinates are not the 300 dpi pixel coordinates.
- Scans are skewed or warped: track each staff's top and bottom per system instead of assuming
  straight lines. A notehead-versus-staff-line overlay settles clear cases; read hollow heads by
  eye. Filled heads can be found by script, hollow ones cannot.
- Map OMR part and measure numbers to print bars **by system** (write it in `todo.md`): the
  offset changes mid-piece, piano voices overflow bars and one staff can be split across parts.
- Read the whole bar, key, time signature, accidentals, ties, lyrics and verses from the print.
  A lyric typo in OMR (Fam, res, Sin) is cheaper to fix in the builder than afterwards.

## 3. Build MusicXML from text

Write one builder script per piece (in the piece's own folder, not a shared scratch folder:
another agent overwrote a shared script once): a token list per bar and part (pitch, duration,
tie, lyric syllable), auto beams, per-bar overrides, one place for metadata. Rebuild from it after
each correction; do not patch the XML by hand. For a Halbestunde result that is mostly right but
has the voices spread over unnamed parts, remap by lyric row into named parts in the same
builder, drop junk bars, then run `fix_metadata.py` and `fix_beams.py` (`beaming-repair`,
syllabic style for choral lyrics). Then `check_musicxml.py` and the audit.

## 4. Compare renders

`musicxml2ly` then `lilypond` renders PNG pages you can lay beside the print page by page
(MuseScore needs the GUI; there is no offscreen plug-in). Compare bar by bar in the busiest
systems, not only at page level. Then import into Sibelius and follow `score-polish-for-sharing`.
Layout numbers for 5 and 6 staves are in
`sibelius/references/import-and-layout-recipes.md`.

## Stop conditions

If a part cannot be read after one pass at 300 dpi, write what is unreadable and stop that part;
do not loop on the same crop. Report the result as "voices only" rather than a full score.
