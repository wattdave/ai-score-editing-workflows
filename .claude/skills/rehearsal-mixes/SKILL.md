---
name: rehearsal-mixes
description: >
  Produce practice parts (rehearsal tracks, learning tracks, part-predominant
  mixes) from the score open in Sibelius: one MP3 of all voices, plus for each
  sung part an "only" mix (that voice with accompaniment) and a "louder" mix
  (that voice at 3x over the others). Use when the user asks for practice
  parts, rehearsal audio, learning tracks or per-voice MP3s from a .sib file.
---

# Rehearsal Mixes

Practice audio is built by the CLI's `rehearsal-mixes` command. It exports
one audio stem per staff from Sibelius, then mixes them with ffmpeg. The
score is not changed.

## Before exporting

1. **ffmpeg** must be on `PATH`, and the bridge must be v55 or newer.
2. **Check the sounds.** Run `playback-sounds` to see each staff's sound
   set, patch and any Mixer override. If the user wants a specific library
   (for example Cantai), pass `--require-sound <name>` to the export so it
   refuses to run if any voice plays something else.
3. **One note per staff.** If a voice staff has chords or divisi, the
   rendered sound may drop notes. Offer the `playback-divisi-split` skill
   first to build a playback copy.
4. **Staff names.** Voices are the staves with lyrics; file names come from
   staff names. Name unnamed staves with `--name 1=Soprano` (repeatable).

## Export

```bash
uv run sibelius-websocket-cli playback-sounds
uv run sibelius-websocket-cli rehearsal-mixes --out DIR \
  [--file SCORE] [--name 1=Soprano] [--require-sound Cantai] \
  [--bitrate 192k] [--loudness -16] [--keep-stems]
```

Allow about 10 seconds per staff: each staff is exported twice, because an
export's opening otherwise carries the previous staff's voice. Read
`--help` before composing unusual invocations.

## Output

- `<score> - All voices.mp3`
- `<voice> only.mp3`: that voice plus accompaniment
- `<voice> louder.mp3`: that voice at 3x amplitude over the others

Voices are first equalized to one loudness; accompaniment keeps its
Sibelius level. Each file is then gained as a whole to `--loudness`
(default -16 LUFS), lowered if it would peak above -1 dBFS, so every file
plays at the same level. `--keep-stems` keeps the per-staff stems.

## Afterwards

Listen to the start of at least one "only" file to confirm no other voice
bleeds in, and report the files written to the user.
