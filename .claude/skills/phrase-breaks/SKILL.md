---
name: phrase-breaks
description: >
  Propose system and page breaks for a MusicXML file by musical phrase, not by
  copying the source print: detect phrase ends (sentence-final lyric
  punctuation, long final notes, rests, fermatas, double or repeat barlines,
  key/time/tempo changes, rehearsal marks, 4-bar periodicity), then compare
  wide, medium and narrow candidate layouts and write the chosen one into every
  part. Use after an OMR scan or import when a score has no breaks
  (score-engraving-audit reports layout-no-breaks), or when asked to lay out,
  space or break a score for readability. Records the user's taste in a rules
  file.
---

# Phrase breaks

`scripts/propose_breaks.py` reads MusicXML (`.xml`, `.musicxml`, `.mxl`),
finds the phrase ends, and chooses system breaks by dynamic programming. It
needs only `python3` (standard library). It writes plain MusicXML and changes
only `<print>` elements; notes are never touched.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/propose_breaks.py" score.xml                       # table per candidate
python3 "${CLAUDE_SKILL_DIR}/scripts/propose_breaks.py" score.xml --json                # for scripts
python3 "${CLAUDE_SKILL_DIR}/scripts/propose_breaks.py" score.xml --candidates wide,5   # a name, or bars per system
python3 "${CLAUDE_SKILL_DIR}/scripts/propose_breaks.py" score.xml --apply medium --out score-medium.xml
python3 "${CLAUDE_SKILL_DIR}/scripts/propose_breaks.py" score.xml --apply medium --page-bars 24 --out score-medium.xml
```

## The goal is the user's taste, not a fixed answer

The user does not want the source print's breaks copied. They want breaks
chosen by the phrases, and they want to build taste by reviewing proposals.
So this skill is a conversation, not a one-shot fix:

1. Read `references/layout-taste.md` first, including every entry under
   "Lessons from review". Those override the default weights and signals: if
   a lesson says "prefer wide for 3/4 hymns", choose and explain accordingly,
   and edit `W`, `SIGNALS` or `CANDIDATES` at the top of the script when a
   lesson becomes a standing rule.
2. Run without `--apply` and look at the tables. Check the detected phrase
   ends against the lyrics and the music; the script can only see what is in
   the XML (OMR often drops lyric punctuation, and a scan with overfull or
   merged bars gives poor signals).
3. Make two or three candidates with `--apply` into a scratch folder, import
   each into the editor, and export a PDF of each (Sibelius, Dorico or
   MuseScore skills). Show the user the PDFs, not the table.
4. Ask which reads best and why: where a line ended too early, where a phrase
   was split, whether lines looked even.
5. Apply the choice to the real file and **append the lesson** to
   `references/layout-taste.md` using the template there (piece, candidate
   chosen, what was wrong, rule to change). If the lesson changes a rule,
   change the script or the rule list in the same commit.

## What it does

- Phrase-end score per bar from the signals in `SIGNALS` (top of the script).
  Scores add up; 2 or more is a phrase end, 4 or more makes a break free.
- Candidates: `wide` about 5-6 bars per system, `medium` about 4, `narrow`
  about 3, scaled by density (notes per bar, syllable length, bar length) and
  clamped to a factor of 0.75-1.2. A bare number is used as given.
- Stacked verses cap the system length (`VERSE_CAPS`): 3 or more verses under a
  staff allow at most 4 bars per system, 2 verses at most 6. A capped candidate
  says so in the table. Lessons that came from review are in
  `references/layout-taste.md`.
- Costs (weights in `W`): off-phrase breaks, systems far from the target,
  uneven neighbours, a one- or two-bar last system, tied notes split by a
  break, and a break that leaves only the last note on the final line.
  A break between a pickup and its first bar is forbidden.
- Each break in the table says why: phrase end because of ..., weak phrase
  end, or a compromise (broke mid-phrase because the next phrase end is too
  far).
- `--apply NAME` writes `<print new-system="yes"/>` into the first measure of
  each system in every part and keeps existing `<print>` attributes. With
  `--page-bars N` it also adds `new-page="yes"` about every N bars, choosing
  system starts that follow a rest or a strong phrase end. The XML
  declaration and DOCTYPE are preserved, and running it twice on its own
  output gives the same file.

## Limits

- Existing break markers in the input are kept, not removed. OMR output has
  none; for an exported file, strip them first or expect doubled breaks.
- Phrase detection is heuristic. Lyrics without punctuation (common in OMR)
  leave only musical signals and the 4-bar periodicity.
- Page breaks are a rough every-N-bars rule; check them in the editor,
  because page capacity depends on the page size, staff size and part count.
- Only `score-partwise` is supported.
