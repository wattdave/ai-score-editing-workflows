# Lyric Workflow

Read this file for lyric proofreading and lyric changes. Read
[engraving.md](engraving.md) as well only when the request involves visual
layout, collisions, or typography.

## Proofread

1. Run one `proofread --lyrics [--staff N] [--bars A-B]` for structural
   findings (collisions, missing vowels, cross-voice divergence, untexted
   passages) and compact lyric data together. Do not also run `check-lyrics`.
2. Only if the report is not enough to judge wording, run
   `read-lyrics --words [--verse N] [--bars A-B]` on the flagged bars.
3. Before editing, run one `read-lyrics --compact [--staff N] --bars A-B`
   covering every bar you will patch and retain each item's `staff`, `bar`,
   and `index`.
4. Put every correction into a single `patch-lyrics` file.

## Preserve the score's lyric typography

`ReadLyrics` returns `obj.Text` without its character-formatting tags.
`GetScoreInfo.mainTextFontName` describes the score default, not necessarily the
font of typed lyrics. Before a lyric write, export a representative page to PNG
and inspect the body lyrics to establish their font family and point size.

Establish the style from one rendered page, once per score, not per edit.
Pass the observed style explicitly. For two or more corrections, always use
one batch so the score is read, backed up, changed, and verified once:

```json
[
  {"staff": 1, "bar": 12, "index": 2, "text": "jah!"},
  {"staff": 2, "bar": 12, "index": 4, "text": "Amen"}
]
```

```bash
uv run sibelius-websocket-cli --expect-file /path/to/score.sib \
  patch-lyrics --file /path/to/patches.json \
  --font "Font Family" --font-size TENTHS_OF_POINT
```

Use optional per-item `font` and `fontSize` fields when patches need different
styles. Add `--save` when textual readback is sufficient; when visual review is
required, export and inspect first, then run `--expect-file PATH save`.

**Never infer a lyric font size when the bridge does not return one.** An
inferred fallback can silently introduce a visible size mismatch. Export and
inspect a neighboring body lyric to establish its actual point size, then pass
both `font` and `fontSize` explicitly. If that size cannot be established,
stop and ask rather than writing a bare or fallback-styled lyric.

For a single correction:

```bash
uv run sibelius-websocket-cli --expect-file /path/to/score.sib set-lyric \
  --staff S --bar B --index I --text "correction" \
  --font "Font Family" --font-size TENTHS_OF_POINT [--save]
```

For example, `--font "Times New Roman" --font-size 95` writes 9.5-point text.
Do not use `--raw` for ordinary corrections. The CLI requires the additional
`--allow-style-reset` acknowledgement because a bare string removes character
formatting and lets the lyric text style supply its defaults. Do not rely on
bare `set-lyric` style inference when the page uses overrides that differ from
the score default.

`reset-design` clears formatting overrides and returns objects to their House
Style definitions. Use it for lyric work only when the user explicitly asks to
adopt those definitions.

## ManuScript styled strings

- Font tokens are `\f<FontFamily>\`; size tokens are
  `\s<TenthsOfPoint>\`.
- Adjacent commands require two backslashes between tokens:
  `\fTimes New Roman\\s95\text`.
- In Python string literals, escape backslashes because `\f` otherwise denotes
  ASCII form feed. Examples are `"\\fTimes New Roman\\\\s95\\"` and
  `"\x5cfTimes New Roman\x5c\x5cs95\x5c"`.
- Styled-string sizes are tenths of a point. They are not Sibelius
  `InitialFontSize` space-unit values.

## Multi-verse and batch lyric workflows

### ManuScript `Bar.AddLyric` argument semantics

- In ManuScript, `Bar.AddLyric(position, duration, text, syllableType, numNotes, voiceNumber)`
  takes `numNotes` (the melisma note span count) as its 5th argument, **not**
  the lyric verse line number.
- Lyric line/verse assignment is controlled exclusively by `LyricItem.StyleId`
  (e.g. `text.staff.space.hypen.lyrics.verse1` through `verse5`), not by an
  argument to `AddLyric`.

### Batch lyric deletion

- When clearing, replacing, or re-flowing lyrics in a bar, find them with
  `query --staff S --bars B --type LyricItem` and delete them in one `apply`
  batch of `{"op":"delete","staff":S,"bar":B,"index":I,"type":"LyricItem"}`
  operations. The batch resolves every address before the first delete, so
  order does not matter, and the `type` guard refuses the whole batch if an
  index no longer points at a lyric.
- Separate `delete-object` commands are not protected this way: each deletion
  shifts the indices of later objects in the bar. If you must use them, go in
  **strict descending index order**.

### Lower-voice lyric duplication for playback

- When duplicating vocal lyrics into accompaniment or lower vocal lines (e.g.
  Alto, Bass) solely so virtual instruments articulate playback without
  altering visual engraving:
  - Mark every duplicated lyric item hidden: `lyric.Hidden = True`.
  - Apply compact vertical offsets: `Dy = -192` for verses 1–5, and `-592` for
    verse 6. Do not leave default or unconstrained vertical offsets on
    duplicated items, as Sibelius's magnetic layout engine can expand stave
    spacing even for hidden objects.

### Verse 6 style and line disambiguation

- Sibelius provides built-in text styles only for `verse1` through `verse5`
  (`text.staff.space.hypen.lyrics.verse1` ... `verse5`). Scores with 6 or more
  verses typically reuse `text.staff.space.hypen.lyrics.verse5` for line 6.
- In inspection tooling and verse-line inference, disambiguate Verse 6 from
  Verse 5 by inspecting `dy` (`dy == -592`) or tracking sequential occurrence
  after Verse 5 at the same rhythmic position.

## Verify

`patch-lyrics` performs one readback verification for the complete batch;
trust its summary rather than re-reading. After a standalone write, re-read
before reusing addresses. Re-export the
representative page only when visual style or layout is part of the change, and
compare edited syllables with adjacent lyrics. Save after verification when
requested.
