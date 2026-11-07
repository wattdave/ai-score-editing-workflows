# Importing MusicXML and laying it out: recipes from the Nelson Carol Book run

Measured on about 40 one-page to five-page carols (overnight run, 2026-11-06/07). Numbers are
`set-layout` values; judge by a rendered PDF, not by the numbers alone.

## Import and save

1. `ScoreBridge OpenScore` with the MusicXML path opens the "Open MusicXML File" window; **Return**
   (default OK) answers it. A schema warning (for example "notations after lyric") may follow: it is
   harmless, continue.
2. Writes need a saved score, so right after the import run `ScoreBridge ExportScore <path>.sib SIBL`,
   then reopen the saved file.
3. If an "Update Score" dialog is up, opens stall until it is answered.

## Closing windows and the save sheet

- Clicking the window close button through Accessibility is unreliable. Activate Sibelius and send
  **Cmd+W** with System Events.
- The save-changes sheet (Yes / No / Cancel) is not exposed to Accessibility. Save first so no sheet
  appears, or take a screenshot and post a real Quartz click on **No** (screen point = screenshot
  pixel x, y divided by 1.371 on this display).

## Layout order that worked

When `set-layout` seems to do nothing, or the last staff of a system overlaps the next system, the
imported system and page breaks are forcing the layout. Order:

1. `invoke select_all unlock_format` (removes imported breaks).
2. `set-break` system / page on bar **N-1** for each system or page start in the print
   (bar must be >= 1; the first bar needs no break).
3. `hide-empty-staves` for each range where a voice rests or is silent (for example bars 4-15).
4. `set-layout` **last** in the batch.

Overlap on a hidden-staff page means the page is overfull: shrink `staffSize` (5.5 instead of 6.5)
before raising gaps. Raising `spacesBetweenSystems` above about 9 made gaps smaller or overlapped
on 4-staff pages and overflowed pages; 4 to 8 worked.

## Lyric rows and layout (staffSize / spacesBetweenStaves / spacesBetweenSystems / aboveTopStaveGap)

| Page | Values |
|---|---|
| 2 staves, 2 verses | 6.5 / 10 / 8 / 24 (rise-up-shepherd: 6 / 11 / 7 / 24, 6.5 spilled to page 2) |
| 2 staves, 4 verses | 6.5 / 17 / 9 / 24 |
| 2 staves, 5 verses | 6 / 22 / 8 / 24 |
| 3 staves, 4 verses | 5 / 12 / 10 / 20, `bottomMargin` 24, `belowBottomStaveGap` 22 |
| 4 staves, 3 verses, 4-5 pages | 5.5 / 8 / 4, or 5.5 / 7 / 3 |
| 128 bars on one page | 5 / 6 / 7 |
| long piece, tight system 1 | 5 with `leftMargin` and `rightMargin` 12 (6 broke system 1 after bar 3) |

Sibelius stretches the last system to the bottom margin, so check the copyright footer in the PDF.
Raising `bottomMargin` does not help; make the page less full.

## Things the import gets wrong, and the fix

- **Credits.** Multi-line credits arrive as several items: the composer item holds only the last
  line, `$Lyricist$` repeats the verse credit. `set` `Text` of the composer item to the whole block
  with `\n`, and `set Hidden true` on the extra items. Better: emit one credit-words with newlines in
  the MusicXML.
- **Page-aligned credit text** (verse 3-4 blocks, footers, bottom-left notes):
  `set Dy` is accepted and does nothing. Put leading newlines in `Text` instead (about 16 px per
  newline at 100 dpi; 7 to 26 newlines were used). For many stacked items, put the whole text in item
  0 and hide the rest.
- **Sixth and later verses** share the verse-5 style, so rows 5 and 6 overprint. For each position
  holding two items at the same `Dy`, set the second lower (-512 to -592).
- **Descant staff lyrics** written as verse 3: `set-lyric-verse` them to verse 1 (this also sets Dy).
- **Hidden time signatures** (print-object=no is not kept): `set Hidden true` on staff 0, index 0 of
  each such bar (type TimeSignature).
- **Final barline** where the print has an end repeat, and a missing start repeat: set both by hand.
- **Melisma extender lines** are not drawn: `set` `NumNotes` (3, 2 ...) on the LyricItem. `Duration`
  alone changes nothing. A middle-type syllable before a long rest draws a hyphen line to the
  rest; delete it and `add-lyric` with `syllableType` end.
- **Tempo.** A dotted `<metronome>` unit (dotted half, dotted quarter) imports correctly as tempo
  text; no rewrite needed. A tempo can also be drawn a second time above the lowest staff
  ("tempo above this staff" property). A tempo the print does not have: `set Hidden true`.
- **Staff names.** `set-staff-name --full X --short X` makes Sibelius draw the name twice per
  system. Do not rename parts in the MusicXML to fix it: re-importing with new part names lost the
  group bracket and repeated the tempo above the last staff. Keep the imported names, or set only
  one property.
- **Not imported at all:** verse numbers ("1." "2."), brace, boxed text, slurs and extender lines
  from some readers, and fermatas on lower staves (no fermata op exists). Draw them by hand or list
  them as open items for the user.
