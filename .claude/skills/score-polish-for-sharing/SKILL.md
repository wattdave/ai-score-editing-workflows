---
name: score-polish-for-sharing
description: >
  Take a scanned or OMR-imported score from "plays back correctly" to "fit to
  print and hand to people": audit it, fix the MusicXML (title, credits,
  copyright line, part names, chord symbols, beams), choose system breaks by
  musical phrase, import it, tidy staff spacing and lyrics in the editor,
  export a PDF and check it against the source scan. Orchestrates the audit,
  repair and layout skills in order. Use when asked to clean up, polish,
  prepare, typeset or get a scanned score ready to share, print or send to a
  choir, after halbestunde-omr or musescore-pdf-convert, or when a score
  imported from MusicXML looks unfinished.
---

# Score polish for sharing

A scan that plays back correctly is usually not fit to print: beams, title
block, part names, chord symbols and line breaks are wrong or missing. This
skill is the order of work. It does not repeat the other skills; it says which
to run when, what to look at between steps, and what is still manual.

Trial run: Deck the Halls (scan, 16 bars, three verses), 2026-11-05.

## Requires

These skills carry the scripts; load each when its step comes up. Each is
standalone (standard library Python), so they work from a marketplace install
without the rest of the repository.

| Step | Skill |
|---|---|
| Find defects, check the result | `score-engraving-audit` |
| Structure repair after OMR (stacked staves, padding, redundant clefs) | `omr-score-repair` |
| Lyric hyphens | `lyric-hyphenation` |
| Title, credits, copyright, part names | `score-metadata-repair` |
| Chord symbols | `chord-symbol-repair` |
| Beams | `beaming-repair` |
| Transposition (when the piece must be sung in another key) | `transpose-score` |
| System and page breaks | `phrase-breaks` |
| Editor operations after import | `sibelius`, `dorico` or `musescore` |

If one is not installed, say so and do that step by hand or skip it; do not
invent a substitute silently.

## Before you start

1. Keep the **source scan or PDF** open: it is the ground truth for words,
   notes, title block, dynamics and what the original printed.
2. Ask the user for facts the file cannot give: title as printed, composer,
   arranger, lyricist, the source's rights status (public domain, in
   copyright with a notice, or the user's own arrangement), and the staff
   names they want. Never invent a composer or a copyright line.
3. Work on **copies** (a scratch directory). Never overwrite the raw scan,
   the user's `.sib` or an existing PDF.
4. Sibelius is the main target. Dorico and MuseScore lack the `beam` and
   `flip-stem` operations (MuseScore has `beam`); say which later steps
   cannot be done there.

## The order of work

### 1. Audit the raw file

```bash
python3 "${CLAUDE_SKILL_DIR}/../score-engraving-audit/scripts/audit_musicxml.py" raw.xml
```

Read the findings against the source. Note what is only informational:
`beams-none` is only fine if the source print is also unbeamed (check it: on the
Brumel file Sibelius left every eighth flagged);
`layout-no-breaks` is expected; `stems-wrong-direction` and `lyrics-crowded`
are estimates to compare with the PDF.

### 2. Repair the XML, in this order

Each step writes a new file (`01-...`, `02-...`) so any step can be undone.

1. **Structure** (`omr-score-repair`): stacked systems, padding bars,
   redundant clefs. Do this first; later steps assume correct bars.
2. **Lyric hyphens** (`lyric-hyphenation`) when `lyrics-unjoined` is reported.
3. **Metadata** (`score-metadata-repair`): title, composer/lyricist, the
   copyright line from the three templates, part names. Two-staff choral
   reductions: `--parts "S A,T B"`.
4. **Chords** (`chord-symbol-repair`): keep chord symbols, rehearsal marks and
   dynamics; repair misreads, never delete.
5. **Beams** (`beaming-repair`): see below.
6. **Stray text**: scans misread printed credits as directions ("Words
   traditions!" beside the real "Words traditional"). Remove duplicates of
   what the credits now say; there is no script for this yet.

Beams: a beamless import may or may not be beamed by Sibelius (Silent Night
yes, Brumel no), and it **keeps explicit partial beams**, which print wrong. If the audit reports `beams-mixed`, run
`fix_beams.py` (default scope completes partly beamed groups). Choose the
style from the source print: the audit's `beam-style` hints (syllabic vs
modern); when undetermined, look at the PDF. If the source print is beamed and the
file has no beams, run `fix_beams.py --scope all`; in 2/2 a beat is a half
note, so four eighths join. Only a source print that is itself unbeamed needs
no step.

Transposing, when asked, belongs here: run `transpose-score` on the
repaired XML (before the phrase breaks, because the ranges and the key
signature decide the layout) and check each part's range in its `--report`.

### 3. Proofread against the source

Scans misread words and notes, and no script can see that. Compare the
lyrics, chord roots and any markings with the source PDF line by line (render
the source page, read the XML text). In the Deck the Halls scan: "Hail thee
new, ye lads" became "Hail the new, yes lads", "Heed-less of" became "al",
verse 2's refrain was lost, and the crescendo hairpin was dropped. Fix lyric
text with the editor's lyric operations after import, or in the XML before.
Record what could not be fixed so the user can decide.

Notes need the same care. In the Silent Night scan, OMR invented junk lower
notes in a treble bar and extra bass notes, and read `pp` as `ppp`. If a
corrected version of the piece exists (an SATB file, another edition), diff
note pitches bar by bar against it; a script that collapses the junk notes
and then re-checks for zero differing bars is safer than hand edits. Rewrite
lyrics slot by slot (per verse, per bar, one entry per note, a melisma is an
empty slot) rather than patching words, then re-run the lyric join.

Do not call a lower note "junk" from the XML alone: in Silent Night bar 11
the stacked lower noteheads were the real alto line (sharing the soprano's
stems), and deleting them left an alto rest that sat on the lyrics. Before
deleting any note, find it in the scan at 600 dpi and compare the *whole*
voice with the corrected SATB staff for that bar, not pitch classes. Restore
missing notes in the editor with `add-note` (as a chord on the voice-1 note
when the scan shares stems) and hide leftover empty voice-2 rests with `set`
`Hidden`.

Translation or alternate-language lines (the German verse under Silent Night)
are set in italic in the scan and were lost in the MusicXML. Give the verse
a label ("4.") in its first syllable's text and put `font-style="italic"` on
every `<text>` of that lyric number; Sibelius imports it as Times Italic.
When the source line is unnumbered, label it anyway so a first reader can tell
what it is. Editor-side restyling of one lyric line is not available through
the bridge, so make this change in the XML and re-import.

A subtitle (e.g. a German title) goes in with `fix_metadata.py --subtitle`.
Credits read one line per item (audit `credits-split`) are joined with
`fix_metadata.py --merge-credits` before import.

### 4. Choose breaks by phrase

```bash
python3 "${CLAUDE_SKILL_DIR}/../phrase-breaks/scripts/propose_breaks.py" file.xml
```

Do not copy the source's breaks. Show the user two or three candidates
(rendered as PDFs where possible), ask which reads best and why, apply the
choice with `--apply`, and append the lesson to the skill's
`references/layout-taste.md`. Read that file first: it holds the user's taste
(for example 4+4+4+4 for a 16-bar carol, and at most 4 bars per system under
three stacked verses).

### 5. Import into the editor

Sibelius: use the bridge, not menus (see the `sibelius` skill):

```bash
uv run sibelius-cli plugin ScoreBridge OpenScore --args '["/abs/path/file.xml"]'
```

An **Open MusicXML File** window appears. Keep "Use layout and formatting from
MusicXML file" ticked, or the breaks are ignored, then click OK. The bridge
reports "busy" until it is dismissed. Confirm with `score-info` that the new
file is the active score, and never touch the user's other open scores.

### 6. Tidy in the editor

Use `render`/`score-snapshot` and a PDF after each group of changes.

- **Staff spacing and page** (`set-layout`): writes need a saved score, so
  first save the import (`ExportScore` with `SIBL` to a new path, close the
  untitled import with **No**, `OpenScore` the saved file). Then one batch:
  `add-line` and other content ops first, `set-layout` last (structural ops
  must come last). Each `apply --save` leaves a `.backup-...sib` next to the
  file, so batch the edits and move the backups away when done.
  Recipe that worked for a two-staff choral reduction with three stacked
  verses on a Letter page (Deck the Halls): `staffSize` 6.5,
  `spacesBetweenStaves` 9.5, `spacesBetweenSystems` 8, `aboveTopStaveGap` 32.
  With four stacked verses (Silent Night, 3 systems, German verse 4) use
  `spacesBetweenStaves` 17, `spacesBetweenSystems` 9, `aboveTopStaveGap` 28 at
  `staffSize` 6.5: 14 let the fourth verse touch the bass stems, 19 filled the
  page so the footer collided, and systems gap 4 cramped the bar numbers.
  At staff size 7 and 4 systems the page fills, Sibelius stretches the last
  system down to the bottom margin, and the copyright footer (which sits at
  the margin) lands on the last bass staff; raising `bottomMargin` moves the
  footer up with it and does not help. Make the page less full instead.
  Check the PDF for the footer, not just the lyrics. The copyright line itself prints only
  through a page-aligned text item in bar 1 (a score with none, or one pushed off the page by
  leading newlines after a tight layout, has no footer); the fix and the `pdftotext -bbox` check
  are in the recipes. 5 and 6 staves need `staffSize` 5 (6 staves also 6.5 / 3) and, for 5,
  `bottomMargin` 12 and `belowBottomStaveGap` 35. Save a never-saved import with
  `ExportScore ... SIBL`, not `save --path`. Verse numbers, extender lines and the brace are
  not imported: list them as open items. When several agents share Sibelius, load
  `sibelius-shared-gui` before any GUI step.
- **Layout that ignores `set-layout` or overlaps systems:** run
  `invoke select_all unlock_format`, then `set-break` on bar N-1 for each
  system/page start of the print, `hide-empty-staves` for resting ranges, and
  `set-layout` last. Layout numbers by verse count (2, 4 and 5 verses; 3 and 4
  staves; one-page 128 bars), page-aligned credit text that `set Dy` cannot
  move (use leading newlines), multi-line credits, hidden time signatures,
  verse 6 overprinting verse 5, melisma extenders (`NumNotes`), and
  save-sheet / import-dialog handling are in
  [import-and-layout-recipes](../sibelius/references/import-and-layout-recipes.md).
  A dotted `<metronome>` unit (dotted half, dotted quarter) already imports as
  correct tempo text; check, do not rewrite. A tempo the print lacks, or drawn
  twice: `score-metadata-repair --tempo once|none` before import. Hidden time
  signatures: `sibelius-cli hide-time-signatures --musicxml FILE` after
  import. Verse numbers, brace, slurs and
  extender lines from the print are often not drawn: say so in the hand-off.
- **Duplicate lyrics:** when every voice sings the same words, keep one set
  and hide the others (`set` `Hidden` on the lyric items of the lower staves)
  to give the systems room.
- **Staff names:** full names on the first system, short after
  (`set-staff-name`).
- **Redundant clefs** (`remove-redundant-clefs`), **bar numbers** at the start
  of each system (`set-bar-number`), tempo text aligned over the time
  signature.
- **Tempo unit that fits the meter:** the beat unit in the tempo marking must
  divide the bar evenly and match how the bar is felt. 9/8 (3+3+3) takes a
  dotted quarter or an eighth, 6/8 a dotted quarter or an eighth, 12/8 a dotted
  quarter, 3/4 a quarter, cut time a half. Never a plain quarter in compound
  time, and never a unit longer than the bar. Take the unit and number from the
  source print (dotted quarter = 108 stays that way). Importers and the vector
  reader write `<sound tempo>` in quarters per minute, so a 6/8 or 9/8 piece
  comes in as quarter = 162 where the print says dotted quarter = 108: replace
  the text (`query --staff system --type SystemTextItem` finds `text.system.tempo`;
  `set` with `"prop":"Text"` and a value like `\\fOpus Text\\q.\\f_\\ = 108`
  in the JSON, which draws a dotted quarter; plain `q.` prints as letters) and
  check playback speed is unchanged.
- **Duplicate markings from the scan:** OMR often repeats a dynamic on both
  staves (`f` twice in Deck the Halls where the print has one). Delete the
  extra Text object (`query --type Text`, then `delete` with its `index`).
  Add a dropped hairpin with `add-line` (`line.staff.hairpin.crescendo`, in
  quarter/256 units: a bar of 4/4 is 1024).
- **Stems and beams by hand**: `flip-stem` and the `beam` operation for the odd
  group left.
- Reset the design if the import left odd text styles (`reset-design`).

### 7. Verify

1. Export a PDF and look at every page against the source. Check the title
   block, system bars, lyrics under notes, chord symbols, dynamics.
2. Export MusicXML and run the audit again. Nothing should get worse: beams,
   chords, lyrics and breaks must not drop.
3. If the pitches or rhythms could have changed, compare the notes with the
   original (`compare_musicxml.py` in the `musescore-pdf-convert` skill: `uv run python -I ${CLAUDE_SKILL_DIR}/../musescore-pdf-convert/scripts/compare_musicxml.py original.xml new.xml`).

### 8. Deliver and clean up

- Save as a new file next to the source (for example `Title - shareable.sib`)
  and export the PDF; back up anything already at that path first.
- Close windows you opened: close button, then **No** to "save changes" for
  test imports; leave the user's windows alone.
- Report the PDF path, what was fixed, and the list of things left for the
  user (misread words, missing markings, rights wording).

## Early music and other engraved sources (Brumel, Du tout plongiet)

When the source is an engraved PDF read by `lilypond-pdf-score`, three more
checks apply:

- **Clef octave.** Do not "fix" a treble-8 from the PDF image or text alone.
  On Brumel I judged the Cantus clef a plain treble (a 400 dpi crop and a text
  search for an "8" both missed it) and moved the line up an octave; the print
  does have a treble-8 and the older XML was right. If the XML and your reading
  of the clef disagree, ask the user or have them look at the print, and leave
  the old value in place until they say.
- **Ficta.** Re-read the PDF with the current `mxl.py` (it writes ficta as
  `accidental-mark`), copy only the marks onto the corrected XML by note
  position, import, then run `list_ficta.py --query ... --editor sibelius`
  and `sibelius-cli apply` the batch. 25 marks placed in the Brumel file.
- **Re-read differences.** A fresh read exposed two wrong Cantus accidentals
  in the older XML (a sharp that was a natural, a natural that was a flat):
  diff pitches per part against a fresh read before trusting an old XML.
  Four staves with lyrics need `staffSize` 5 for three systems per page.

## What is still manual

Lyric and note proofreading against the source, removing stray text,
re-adding dropped hairpins, hiding duplicate lyrics (one operation per
staff), and the first-page house style. Dorico and MuseScore cannot yet beam or
flip stems through this repository's back end.

## Lessons

When the user critiques a result, add it to `phrase-breaks/references/
layout-taste.md` (layout) or note it here (other steps), with the date and
the piece, so the next run starts from the user's taste.
