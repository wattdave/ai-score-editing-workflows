# Layout taste: rules for system and page breaks

These are the working rules behind `scripts/propose_breaks.py`, drafted from
standard engraving practice (Elaine Gould, *Behind Bars*, on system and page
layout; the general norms of Read, Ross and Stone on music typesetting). They
are a starting point. The user's own judgement, recorded under "Lessons from
review" below, wins over everything in this file.

## Rules

1. **Break at phrase ends.** A system should end where the music and the text
   come to rest, so a singer or player never has to turn a phrase around a
   line end. Signals, strongest first: a fermata, a double or repeat barline,
   sentence-final lyric punctuation (. ! ?), a rest, a new key, time
   signature, tempo or rehearsal mark in the next bar, a semicolon or colon, a
   long final note, a comma. Gould: phrase-aligned lines make a score read
   better than evenly filled ones.
2. **Similar bar counts per system.** Lines of 4-4-4-4 read calmer than
   5-3-6-2. The eye learns the line length; uneven neighbours cost.
3. **Match the density.** Dense bars (many notes, long syllables, long bars
   such as 12/8) take fewer per system; sparse bars take more. Enough room for
   the lyric syllables under the notes matters more than bar count.
4. **No orphan bars.** A last system of one or two bars looks like a mistake
   and wastes a page turn. Do not leave only the last note, or only a closing
   chord, on a line of its own.
5. **Never separate a pickup from its first bar.** The upbeat belongs to the
   downbeat it leads to.
6. **Avoid splitting a tied note** across a system break when another break
   is nearly as good.
7. **Page turns at rests.** For players, put the page turn where there is a
   rest or a strong phrase end, so they have a hand free. A choir that sings
   from a page benefits too: turn between sections.
8. **The last system is not too short.** At least half a normal line.
9. **Four-bar periodicity** is a weak signal: when nothing else marks the
   phrase, a break after bar 4, 8, 12 counted from the first full bar is the
   best guess for dance-like and hymn-like music.
10. **A compromise is allowed but visible.** If the next phrase end is too far
    away, the script breaks mid-phrase and says so; prefer the break that
    falls after a long note or a rest.

## Candidates

| Name | Bars per system | Use when |
|---|---|---|
| wide | about 5-6 | sparse music, simple rhythm, large page, few parts |
| medium | about 4 | the default for hymns and carols |
| narrow | about 3 | dense music, long lyrics, many parts, large staff size |

Sizes are scaled by density and clamped, so a sparse 6/8 piece can get 6-7
under `wide`. Pass a number to `--candidates` to force bars per system.

## Cost weights (see `W` in the script)

| Weight | Default | Meaning |
|---|---|---|
| size | 1.0 per bar squared | distance from the target system size |
| uneven | 1.0 per bar squared | difference to the previous system |
| off_phrase | 6.0 | break with phrase score 0 (scales down to 0 at score 4) |
| tie | 2.0 | break splits a tied note |
| orphan1 / orphan2 | 30 / 8 | last system of one / two bars |
| short_final | 2.0 per bar squared | last system under half the target |
| last_note | 10 | break right before a final bar holding only its last note |

## Lessons from review

After the user critiques a proposal, add an entry below and change the rule,
weight or signal it names. Keep entries short and dated.

### 2026-11-05  Deck the Halls (16 bars, 4/4, three verses on the treble staff)
- Candidate chosen: medium (4 systems, 4-4-4-4). Wide (8-8) was rejected: three stacked
  verses collided and crushed together.
- What was wrong: the wide candidate ignored how many verses sit under the staff.
- Rule to change: rule 3 (match the density). 4+4+4+4 is the natural default for a 16-bar
  carol, provided the page layout supports it. With 3 or more stacked verses a system
  never holds more than 4 bars; with 2 verses, 6 (`VERSE_CAPS`).
- Changed in script: yes, `VERSE_CAPS` and `--candidates` report a capped target.

### 2026-11-05  Deck the Halls: identical lyrics on every voice
- Tactic: when every voice sings the same words, show the lyrics once and hide the
  copies below the lower staves to give the systems more room (in a 2-staff reduction,
  keep the lyrics under the top staff only). Also give the staves enough space for
  stacked verses instead of squeezing the bars.
- Changed in script: no, noted only (an editor step after import).

### 2026-11-05  Deck the Halls: staff names
- For a two-staff choral reduction name the staves "S A" and "T B" (abbreviations the
  same), not Treble and Bass. `score-metadata-repair --parts "S A,T B"`.
- Changed in script: no, noted only.

Template:

```
### YYYY-MM-DD  <piece>
- Candidate chosen: <wide | medium | narrow | custom> (N systems, sizes ...)
- What was wrong: <what the user saw in the rendered PDF>
- Rule to change: <rule number, weight or signal, and the new value>
- Changed in script: <yes, commit/PR | no, noted only>
```
