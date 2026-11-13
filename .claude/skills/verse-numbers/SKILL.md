---
name: verse-numbers
description: >
  Sibelius (via sibelius-cli). Draw the verse numbers ("1." "2." "3.") a print
  shows beside each lyric verse, as separate staff text and never as part of the
  lyric, so vocal playback (Cantai) does not sing them and lyric tools do not
  read them. Also repairs scores where an earlier pass put "1. " inside the first
  syllable. Use when a score imported from MusicXML or a scan lacks the print's
  verse numbers, when score-engraving-audit or a proofread reports "verse
  numbers not drawn", or when check-lyrics / a lyric sheet shows "1. The".
---

# Verse numbers as text, not lyrics

Verse numbers are lost on every MusicXML import. Do **not** put them in the lyric
text (`patch-lyrics` with "1. The"): Sibelius's lyric items are what Cantai and any
other vocal playback sings, and what `read-lyrics`, `check-lyrics`, the
`lyric-sheet` skill and the MusicXML export read, so "1." would be sung and would
leak into every lyric extraction. Draw each numeral as a plain staff text object
beside the verse's first syllable. Staff text is ignored by playback and by the
lyric tools.

## Run it

Sibelius must be open on the score, one score at a time (take the GUI lock first
when other agents share the screen: `sibelius-shared-gui`). `--expect-file` is
required and must be the open score. Needs poppler (`pdftotext`) for the calibration.

```bash
V=.claude/skills/verse-numbers/scripts/verse_numbers.py
python3 $V --expect-file "/abs/score.sib" --dry-run                 # what it found
python3 $V --expect-file "/abs/score.sib" --save                    # draw, calibrate, save
python3 $V --expect-file "/abs/score.sib" --from-bar 7 --save       # numerals start in a later system
```

What it does:
1. Finds the earliest lyric item of every verse on `--staff` (default 1) and adds a
   `text.staff.plain` text "N." at that bar and position (skipped if already there,
   so the script is safe to rerun).
2. **Calibrates from the render.** It exports a PDF, uses `pdftotext -bbox` to find each
   numeral and its verse's first word, and solves the offsets: every numeral gets the
   baseline of its verse's first word (Dy per verse), and all numerals get **one Dx**, so
   they form a left-aligned column as in the print. The widest first word sets the column;
   its gap to the numeral is `--gap-pt` (default 2.5 pt). It prints the residuals
   (baseline off, gap per verse) and refuses to continue if a baseline is still more than
   0.5 pt off.
3. Saves with `--save`.

Dx/Dy are in 1/32 space and differ from score to score (the plain-text baseline and the
first words' widths vary), which is why the script measures them instead of using a
fixed offset. Each `apply` is one undo step and every write is checked against
`--expect-file`.

Options:
- `--from-bar N`: only look from score bar N. Use it when the numbered verse rows start
  in a later system than the first words. Ther is no rose sings verse 1 unnumbered in
  bars 1-6 and the print numbers "1." to "4." from the second system: `--from-bar 7`
  (with a pickup, score bar = printed bar + 1).
- `--strip-lyric-prefix`: first remove a leading "N. " that an earlier pass put inside the
  lyric (font reset to Times New Roman 7.4 pt; `patch-lyrics` takes tenths of a point).
- `--staff S`: the staff that carries the verse rows (the top staff of a choral reduction;
  numerals are drawn once, beside the first lyric line).
- `--dx`, `--dy-adjust`: only the starting guess. If it stops with "probably locked onto a
  neighbouring row", pass a `--dy-adjust` that puts the numerals within half a row
  (about 40 units) of their verse, e.g. `-56` for We Three Kings.
- `--no-auto`: skip the calibration and use `--dx` / `--dy-adjust` as given.
- `--gap-pt`: numeral-to-word gap of the tightest row.

Verses that start with the same word (Boar's Head: "The", "The", "Our") are told apart by
row order: verse N is the Nth row from the top.

Worked on: Boar's Head (3 verses, one staff), We Three Kings (5 verses, two staves),
Ther is no rose (4 verse rows from bar 7).

## Check

- `uv run sibelius-cli check-lyrics`: no new issue (a "Notes without lyrics"
  passage on lower staves is the print's own layout, not this change).
- Read the first syllables of the verse bar (`query --staff S --bars N-N --type
  LyricItem`): they must be "The", not "1. The".
- Look at a crop of the render against the print for every verse row
  (`pdftoppm -r 160 -png -f 1 -l 1 -x X -y Y -W W -H H file.pdf out`; a whole-page PNG from
  `verify-render --format png` can come back cropped).
- Save (`--save`, or `sibelius-cli --expect-file F save`), move the `.backup-...sib` files
  away, and close the window. If the close does nothing, Sibelius is showing a floating
  "Do you want to save the changes" dialog (not a sheet, and invisible to `sheets of window`):
  find its Yes button in `entire contents of` the unnamed window and click it. Answer Yes for an
  edited score, No for one you only read.

## Finding scores that need repair

Search every score's first lyric syllables for a leading number:

```bash
uv run sibelius-cli query --staff 1 --bars 1-8 --type LyricItem | python3 -c "
import json,sys
print([o['text'] for o in json.load(sys.stdin)['objects'] if o['text'][:1].isdigit()])"
```

Then run the script with `--strip-lyric-prefix` on any hit. Good King Wenceslas and
other scores from the first Nelson Carol Book pass may carry numerals in the lyrics.

## Limits

- The numerals are separate objects with fixed offsets, so they do not follow the lyric if
  its spacing changes later (a layout change, a different page size): rerun the script.
- Sibelius only. Dorico and MuseScore have their own verse-number mechanisms and no
  script here.
- Not drawn by this skill: brace, extender lines and slurs from the print.
