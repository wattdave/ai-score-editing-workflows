---
name: lyric-hyphenation
description: >
  Join separate lyric syllables into hyphenated words ("win ter" -> "win-ter",
  "De cem ber" -> "De-cem-ber") in a MusicXML score before it is imported into
  Sibelius, Dorico or MuseScore. Use when lyrics show no hyphens between the
  syllables of a word, for example after an OMR scan or a score whose lyrics
  were typed one syllable at a time.
---

# Lyric Hyphenation

Lyrics that arrive one syllable at a time have no word connection, so the
editor draws no hyphens. In MusicXML the connection is `<syllabic>`:
`begin`, `middle`, `end` (or `single`). This skill sets it in bulk.

## Run

```bash
# 1. dry run: list the words that would be joined, with counts
python3 ${CLAUDE_SKILL_DIR}/scripts/hyphenate_lyrics.py "Score.xml" --dry-run

# 2. write the corrected file
python3 ${CLAUDE_SKILL_DIR}/scripts/hyphenate_lyrics.py "Score.xml" -o "Score (hyphenated).xml"
```

Options: `--not-word fireside` never joins that word; `--word mistletoe` adds a
word the system dictionary lacks. Both take lowercase words without hyphens
and can be repeated.

## How it decides

- Neighbouring syllables (2 to 4) are joined when their concatenation is a word
  in `/usr/share/dict/words`, plus inflections (-ing, -es, -ed, -er, -ly, -s)
  and a short extra list. Runs are read per part, staff, voice and verse, in
  score order.
- It does not join when a syllable after the first starts with a capital
  ("day Dream-ing"), when the word starts with a function word ("to", "be",
  "the"; "together" and "tonight" are exceptions), or when every fragment is
  already an ordinary word.
- Syllables must be adjacent in the same staff. A word split across two staves
  (for example after splitting voices onto separate staves) is only joined if
  the syllables sit together in one staff's run, so hyphenate after the final
  staff layout is settled, or hyphenate the finished file.

## Always review the dry run

A dictionary cannot tell "win ter" (one word) from "out shine" (two sung words)
or "ba ba" (scat). Read the list and add `--not-word` for false joins and
`--word` for missed words. Report both lists to the user. Unjoined leftovers
usually mean a syllable is missing or sits on another staff.

## Sibelius scores that are already open

Sibelius cannot change a lyric's syllable type in place. Two options:

- Preferred: fix the MusicXML, then re-import. Any manual engraving in the
  open score is lost, so only do this when the score is still a fresh import
  or you rebuild it from a script.
- For a few words: in one `apply` batch, delete the lyric and add it again
  with `add-lyric` and `"syllableType":"middle"` for every syllable except the
  last of a word (`"end"`). Only `end` and `middle` are accepted. Do not use
  `set-lyric` for this; it cannot change the syllable type, and a bare
  `--raw` write can leave the lyric invisible on the page.

Recipe for one hyphen: one `apply` batch holding a `delete` of the lyric and
an `add-lyric` with the same `text`, `staff`, `bar`, `position`, `voice`,
`verse`, `dy` (verse 1 is -192), `"syllableType":"middle"` and `duration` set to the
note's duration (a duration of 0 is rejected). Addresses in a batch are read
before it runs, so one batch can fix many words. A tenor "Christ ma" missing
its "s" is fixed the same way, by deleting and adding it with new text.

Verify with `uv run --project "${CLAUDE_SKILL_DIR}" sibelius-cli read-lyrics --words`, which prints joined
words with hyphens.

**The data can say "middle" and the page can still show no hyphen.** Sibelius
leaves the hyphen out when the two syllables are too close. Re-creating the
lyric does not help. Export a PNG of the page (`sibelius-cli export --format
png`) and look. A system break after the crowded bar (`patch-layout set-break`)
gives it the room; so can widening the spacing. The OMR scan of All I Want For
Christmas wrote "ba by", "Christ mas", "san ta" and "real ly" as separate
words, so check these common ones (baby, Christmas, Santa, really) first.
