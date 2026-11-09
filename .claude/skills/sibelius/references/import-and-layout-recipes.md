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

- A window that is not frontmost ignores its AXCloseButton: `AXRaise` it, then send **Cmd+W**
  with System Events (Sibelius frontmost).
- The save-changes sheet (Yes / No / Cancel) has nested buttons: `click button "No" of window 1`
  fails; walk `entire contents of window` and click the button named "No"
  (`lyric-sheet/scripts/sib_windows.sh no-save`). Or save first so no sheet appears.
- If you must click it for real, read the display scale first (`CGDisplayBounds`): screenshot
  pixels equal points on a 1920x1080 display; the "divide by 1.371" value was for another one.
- Missing Fonts on an old-format file: Return, after every open, or the bridge answers "plug-in
  not reachable" for later scores. Several agents on one GUI: `sibelius-shared-gui`.
- `sibelius-cli save --path COPY` is refused; the never-saved import is saved with
  `ExportScore ... SIBL` (step 2 above), then reopen the `.sib`.

## One command: auto-layout

`auto-layout` runs the order below and picks the `set-layout` row from the table
for the score's staves (read from Sibelius, or `--staves`) and `--verses`:

```bash
sibelius-cli --expect-file /abs/x.sib auto-layout --ready _work/x/ready.json --verses 4 --dry-run
sibelius-cli --expect-file /abs/x.sib auto-layout --systems "1,5,9/13,17" --verses 4 \
  --hide-empty 11-18 --verify --pdf /abs/x.pdf --save
```

- `--systems`: printed bars where systems start, pages split by `/`; `--ready` reads
  `breaks`/`page_breaks` in any of the ready.json shapes (starts, ends-after, bare
  list; a bare list is read as starts unless `post_import` says "after").
- Bars are as printed. `--pickup` (auto when ready.json mentions a pickup) adds 1:
  the pickup is score bar 1. Check the `notes` in the output.
- `--unlock-format` is on by default and **clears manual formatting** (all breaks,
  locked layout) before the batch, as its own undo step; `--no-unlock-format` keeps it.
- `--hide-empty` caps `staffSize` at 5.5; `--layout staffSize=5` overrides any value.
- `--out FILE` writes the plain `apply` batch (needs `--staves`) to merge with other
  ops; run `invoke select_all unlock_format select_none` first yourself.
- `--verify` reads each bar's `OnNthPage`/`OnNthSystem` and fails on a page or system
  that differs from the plan; `--pdf` exports and counts pages. On overlap shrink
  `staffSize` (rows marked `presetMeasured: false` were not measured).

## Pickup bars: printed versus score numbers

With a pickup, score bar = printed bar + 1 (pickup is printed 0). `auto-layout --pickup`
expects **printed** numbers as the print shows them and no "1": `--systems "5,11,16" --pickup`
(passing the old render's pickup-counted 4,10,15 gave a pickup-only first system and every break
one bar early; `--verify` reports `systemStarts [1,6,12,17]` in score bars). `hide-empty-staves
fromBar/toBar` and other direct ops take **score** bars: for printed bars 0-16 use 1-17, or give
`auto-layout --hide-empty` the printed range and let it apply the offset. Afterwards check no
system keeps a staff of only rests. The preset may overflow or leave systems touching; follow with
`set-layout` (4.8 / 9 / 9 for Myrie it is; 6 / 17 / 8 with `extraSpacesBelowVocalStaves` 5 for
Emmanuel).

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
| 5 staves (voices + piano) | `staffSize` 5, with `--layout bottomMargin=12 --layout belowBottomStaveGap=35` to keep the footer on the page |
| 6 staves, 2 systems per page | 5 / 6.5 / 3 |
| 128 bars on one page | 5 / 6 / 7 |
| long piece, tight system 1 | 5 with `leftMargin` and `rightMargin` 12 (6 broke system 1 after bar 3) |

Sibelius stretches the last system to the bottom margin, so check the copyright footer in the PDF.
Raising `bottomMargin` does not help; make the page less full.

## Things the import gets wrong, and the fix

- **Credits.** Multi-line credits arrive as several items: the composer item holds only the last
  line, `$Lyricist$` repeats the verse credit. `set` `Text` of the composer item to the whole block
  with `\n`, and `set Hidden true` on the extra items. Better: emit one credit-words with newlines in
  the MusicXML.
- **Copyright line.** Score Info > Copyright alone prints nothing; the footer is a system text
  `\$Copyright\` in style `text.system.page_aligned.copyright` in bar 1 (MusicXML credits import
  it). If the file has none (read-exact pieces, a score without the credit), add it:
  `{"op":"add-text","staff":0,"bar":1,"position":0,"text":"\\$Copyright\\","styleId":"text.system.page_aligned.copyright"}`
  and type the line in Score Info (File > Info). The bridge cannot set the copyright
  (`SetScoreInfo` has title/composer/lyricist only), so that step is a GUI click.
  Position is by leading newlines in `Text` (`set Dy` and `nudge` do nothing): after a tight
  layout (`bottomMargin` 12) two newlines dropped it off the page (779 of 792 pt), none at all
  was too low; `add-text` with two newlines gave 760 pt. The count depends on page fill, so
  export the PDF and check the text position with `pdftotext -bbox`, never assume.
- **Composer and arranger credits** on the right: Sibelius keeps only one of two right-aligned
  credits. Merge them into one two-line credit in the MusicXML (`fix_metadata --merge-credits`)
  or set the composer text to both lines with `\n`; a left credit near y 1450 can collide with a
  subtitle.
- **Page-aligned credit text** (verse 3-4 blocks, footers, bottom-left notes):
  `set Dy` is accepted and does nothing. Put leading newlines in `Text` instead (about 16 px per
  newline at 100 dpi; 7 to 26 newlines were used). For many stacked items, put the whole text in item
  0 and hide the rest.
- **Lyric item one row too high after a melisma `_` placeholder.** When Dy is assigned by running
  order, a placeholder row hands the next row's Dy to later items (Riu Riu Chiu: four syllables
  sat on the row above). Assign Dy by verse row (`set-lyric-verse`, `add-lyric` with `dy`), then
  query `LyricItem` Dy per bar/position and look for a position where the values skip a row;
  fix with `nudge` (-80 per row) and re-export the PDF.
- **Sixth and later verses** share the verse-5 style, so rows 5 and 6 overprint. For each position
  holding two items at the same `Dy`, set the second lower (-512 to -592).
- **Descant staff lyrics** written as verse 3: `set-lyric-verse` them to verse 1 (this also sets Dy).
- **Hidden time signatures** (print-object=no is not kept): `hide-time-signatures --musicxml
  FILE.musicxml` (or `--bars 2-54`) sets `Hidden` on the system staff's TimeSignature in each such
  bar as one checked batch; `--dry-run` first. Bars where Sibelius has no time signature are listed.
- **Final barline** where the print has an end repeat, and a missing start repeat: set both by hand.
- **Melisma extender lines** are not drawn: `set` `NumNotes` (3, 2 ...) on the LyricItem. `Duration`
  alone changes nothing. A middle-type syllable before a long rest draws a hyphen line to the
  rest; delete it and `add-lyric` with `syllableType` end.
- **Tempo.** A dotted `<metronome>` unit (dotted half, dotted quarter) imports correctly as tempo
  text; no rewrite needed. A tempo can also be drawn a second time above the lowest staff
  ("tempo above this staff" property). A tempo the print does not have: fix the file first with
  `score-metadata-repair --tempo once` (or `none`), which keeps `<sound tempo>` for playback but out
  of the printed direction; if a tempo text still appears, `set Hidden true` on it.
- **Staff names.** `set-staff-name --full X --short X` sets the instrument names only (bridge
  v64). Bridge v63 and older also wrote the staff name, so Sibelius drew the name twice per
  system ("I I"), bold beside the staff; running it again on v64 clears that duplicate. Do not
  rename parts in the MusicXML instead: re-importing with new part names lost the group bracket
  and repeated the tempo above the last staff.
- **Verse numbers** ("1." "2.") are lost on every import. Add them as text at the start of the
  first syllable of each verse line with `patch-lyrics` (`--font-size` is tenths of a point, 74,
  not points). With a pickup the first syllable of each line is not always in bar 1 (Bleak
  Midwinter: only verse 2 starts in the pickup): `read-lyrics` per bar and take the earliest item
  per verse; a piece may print its first line as verse 2. No helper exists yet.
- **Not imported at all:** verse numbers ("1." "2."), brace, boxed text, slurs and extender lines
  from some readers, and fermatas on lower staves (no fermata op exists). Draw them by hand or list
  them as open items for the user.
