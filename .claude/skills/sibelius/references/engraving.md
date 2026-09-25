# Engraving and Visual Review

Read this file for collisions, lyric typography, stems, spacing, or other
changes whose result is visible rather than fully represented by bridge reads.

## Render and iterate

Render and verify pages in one call:

```bash
uv run sibelius-websocket-cli verify-render --format png --out /tmp/check.png
```

Numbered pages are written as `check_0001.png`, `check_0002.png`, and so on.
Open only the page that contains the passage in question; images are
expensive in context.

Batch adjustments rather than iterating one object per render: note every
collision on the page, write all fixes into one `patch-layout` file, validate
it with `--dry-run`, apply it, and render once. Re-render only the pages the
batch touched.

```json
[
  {"op": "nudge", "staff": 1, "bar": 12, "index": 3, "dy": -32},
  {"op": "nudge", "staff": 2, "bar": 12, "index": 1, "dx": 16},
  {"op": "set-break", "bar": 17, "type": "system"}
]
```

```bash
uv run sibelius-websocket-cli patch-layout --file /tmp/ops.json --dry-run
uv run sibelius-websocket-cli --expect-file /path/to/score.sib \
  patch-layout --file /tmp/ops.json
```

## System layout and footer space

When an imported score has cramped or manually displaced systems, distinguish
system/staff offsets from the actual page margin. Resetting **Space Above** on a
passage can clear unintended vertical staff offsets; then re-render before
changing any document-wide spacing. If the remaining issue is unused space
below the final system, reduce **Below Bottom Stave Gap** in Document Setup
rather than the page bottom margin. Keep page margins intact unless the user
explicitly wants a smaller printable margin, and use the separate first-page
value when Document Setup provides one.

Read the current Document Setup and staff spacing from `score_structure`
(`layout`: page size, orientation, staff size, margins and stave gaps in mm;
`engraving`: spaces between staves and systems). Change them with one
`set-layout` batch operation (bridge v50), which changes only the settings
it names, e.g. `{"op":"set-layout","belowBottomStaveGap":5}` or
`{"op":"set-layout","spacesBetweenSystems":10,"extraSpacesBelowVocalStaves":2}`.
Setting `orientation` swaps the margins, so set margins in the same op
(they are applied after it) or re-read afterwards. The first-page stave
margin is not settable yet.

To reset a freshly imported score whose systems overlap, reset positions and
spacing across the whole score, then hide empty staves:

```bash
uv run sibelius-websocket-cli invoke select_all reset_position \
  reset_space_above_staff reset_space_below_staff reset_note_spacing \
  reset_stems_and_beam_positions
uv run sibelius-websocket-cli command escape
```

then run `apply` with `[{"op":"hide-empty-staves","fromBar":1,"toBar":LAST_BAR}]`
(bridge v52). It also optimizes staff spacing. If systems still collide,
check for system and page breaks carried over from MusicXML `<print>`
elements: breaks copied from a printed page can force more systems onto a page
than fit once staves are added. Clear them with `set-break` `"type": "none"`
ops (a break imported at the start of bar N may sit on bar N-1, so clear
both), or with `invoke select_all unlock_format`. `invoke` always reports
success, so render to confirm.

Available layout operations include:

- `nudge` (a `patch-layout` op, or the single-object command) for an
  addressed object's horizontal or vertical offset in 1/32 spaces. Moving one
  colliding syllable can transfer the collision, so include both sides in the
  same batch and inspect both afterward.
- `set-break`, `set-barline`, and `reset-design` are also `patch-layout` ops;
  combine them with nudges in one file. `set-break` `"type": "none"` clears a
  break (bridge v37+); on older bridges it forbade one and collapsed the score
  onto a single system.
- `flip-stem --staff S --bar B --index I` for stem direction.
- `invoke select_all reset_note_spacing select_none` (one call, several IDs)
  or `increase_spacing` for global note spacing.
- `set-lyric-style --staff S --bar B --index I --style verse1` when a unison
  refrain should use lyric line 1 consistently.

## Review checklist

1. **Baseline continuity:** compare lyric baselines within each system and
   across phrase boundaries; look for unintended verse-line changes.
2. **Typography:** compare font family, size, and weight with surrounding body
   lyrics. Follow [lyrics.md](lyrics.md) before changing lyric text.
3. **Phrase-aware breaks:** place system or page breaks at phrase endings or
   rests, rather than across tied notes or pickups.
4. **Extender clearance:** inspect ties across barlines for extender lines that
   collide with or displace following pickup lyrics.

Report what was visually verified. For properties the bridge does not expose,
ask the user to confirm the rendered or on-screen result.
