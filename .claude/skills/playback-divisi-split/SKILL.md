---
name: playback-divisi-split
description: >
  Build a playback copy of a choral or ensemble score in which every staff
  sounds exactly one note at a time: split chords and divisi onto separate
  staves, fill unison openings, and let resting voices double the melody.
  Use when playback (one vocal sample or MIDI channel per singer) drops
  stacked notes, or when the user asks for a separate playback version.
---

# Playback Divisi Split

Some playback setups sound only one note per staff, so chords and divisi go
silent. This skill makes a **separate playback copy** in which every chord note
sits on its own staff. The engraved score is left untouched.

The script works on MusicXML and runs locally. Sibelius is needed only to
import and save the result.

## Ask the user first

These choices change the notes. Do not assume them:

1. **Unison passages.** Does the whole choir sing the opening (or any passage)
   printed on one staff? Get the last unison bar, and state whether it is a
   bar index (pickup = 1) or a displayed bar number (pickup = 0).
2. **Resting and hidden voices.** When a voice rests, or its staff is hidden,
   should it rest or double the melody?
3. **Chords with more notes than voices.** Where one part's own line has a
   chord, where do the extra notes go? The script's rule is described below;
   offer it, or take the user's rule and edit the script.

## Run

```bash
uv run python .claude/skills/playback-divisi-split/scripts/playback_split.py \
  "Score.xml" -o "Score (playback).xml" --melody P1 --unison-until 8
```

- `--melody`: the part carrying the tune (default `P1`).
- `--unison-until N`: every part copies the melody for bar indexes 1..N.
- `--no-double-rests`: leave other parts' rests as written.

The rules:

1. **Unison:** bars 1..N of every other part copy the melody.
2. **Resting voices double the melody:** a rest is replaced by the melody's
   notes when the melody's note boundaries line up with it exactly
   (consecutive rests are merged first).
3. **Melody chords** are shared among the voices singing melody material at
   that moment: top note to the melody part, bottom note to the lowest part,
   middle notes in between. With fewer notes than voices, the leftover voices
   sing the melody note.
4. **Chords on another part's own line:** the part keeps the note nearest its
   previous note (voice-leading). An extra note already sounding elsewhere is
   dropped. Otherwise it replaces the note of the adjacent part nearest in
   pitch that starts at the same moment with the same duration. Non-melody
   parts come first; the melody part is a last resort, and only when the note
   it would lose sounds in another octave elsewhere.

The script prints a **decision log** for every chord. Report each rule-4 line to
the user: those are the places where a voice sings something other than its
written line.

It refuses multiple voices on one staff (`<backup>`) and parts with different
`<divisions>`. Unpack `.mxl` files first.

## Import and save

Import silently and save through the bridge (see the `sibelius` skill), rather
than asking the user to click through the import dialog:

```bash
uv run sibelius-websocket-cli plugin sibwscli OpenScore --args '["/abs/Score (playback).xml"]'
uv run sibelius-websocket-cli plugin sibwscli ExportScore --args '["/abs/Score (playback).sib", "SIBL"]'
uv run sibelius-websocket-cli plugin sibwscli OpenScore --args '["/abs/Score (playback).sib"]'
```

Then:

- **Clear imported breaks.** Breaks copied from a printed layout rarely fit
  once staves are added. Clear them with `patch-layout` `set-break` ops of
  type `none`, clearing both bar N-1 and bar N for each imported break.
- **Reset the layout.** Follow the layout-reset recipe in the `sibelius`
  skill's engraving reference.
- **Restore repeats.** Check `score-snapshot` barlines: an end repeat can
  import as `Final`, so set it again with `set-barline ... end_repeat`.
- **Verify.** Run `verify-render`, then check every staff for chords, and the
  rule-4 bars against the log.

## Common mistakes

- **Editing the engraved score.** Always write a separate file; the engraved
  score keeps its chords.
- **Confusing bar numbers.** Sibelius displays the pickup as bar 0, but the
  bridge and this script count it as bar 1.
- **Rebuilding from a stale XML.** Apply MusicXML fixes (for example a missing
  key signature) to the source XML first, then regenerate the playback copy
  from it.
