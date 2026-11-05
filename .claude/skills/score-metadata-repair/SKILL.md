---
name: score-metadata-repair
description: >
  Fix the metadata defects that score-engraving-audit reports in a MusicXML
  file before it is imported into Sibelius, Dorico or MuseScore: title missing,
  lower case, ALL CAPS, padded or carrying a list number ("1. Caroling,
  Caroling"); composer, arranger or lyricist missing; no copyright/source
  line; generic part names (Voice0, Voice1) and missing part abbreviations.
  Use after an OMR scan or import, when the audit reports title-*,
  composer-missing, rights-missing, part-name-generic or
  part-abbreviation-missing, or before sharing a score.
---

# Score metadata repair

Writes a corrected copy of a MusicXML file; the input is never modified. It
needs only `python3` (standard library), not this repository or an editor. It
reads `.xml`, `.musicxml` and `.mxl` and writes plain MusicXML. It changes only
metadata: notes, lyrics, beams and layout are copied as they were, and the XML
declaration and DOCTYPE are kept.

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/fix_metadata.py" IN.xml OUT.xml [options]
```

| Option | Effect |
|---|---|
| `--normalize-title` | Trim, drop a leading list number, title-case an all-lower or ALL CAPS title (small words such as "the", "of", "to" stay lower case except first and last) |
| `--title T` | Set the title exactly (work and movement title; a matching title credit follows) |
| `--composer C`, `--arranger A`, `--lyricist L` | Write `<creator type=...>` (replaces an existing one of that type) |
| `--rights-template T` | Write `<rights>` from one of three templates, below |
| `--source`, `--notice`, `--year`, `--name` | Values the templates need |
| `--parts "Soprano,Alto,Tenor,Bass"` | Name the parts in score order and add abbreviations |

With no options the file is copied unchanged. The script never invents a
composer, arranger, lyricist or copyright line: you must pass the value. Ask
the user (or read the source print) for each one first.

## Copyright line templates (decided by the user; use exactly)

| `--rights-template` | Needs | Result |
|---|---|---|
| `public-domain` | `--source` | `Public domain. Transcribed from [source] for rehearsal use.` |
| `in-copyright` | `--notice` (the original notice) | `[notice] Transcribed for rehearsal use only. Not for distribution.` |
| `own-arrangement` | `--year`, `--name` | `Arrangement © [year] [name].` |

Never add a © to a transcription unless the user says it is their own
arrangement. A missing value is an error (exit status 2), not a guess.

## What it writes

- `<identification>`: creators first, then `<rights>`, then the existing
  `<encoding>`; the element order stays valid MusicXML.
- `<credit>` blocks for the title, lyricist, composer and arranger, placed after
  `<defaults>` and before `<part-list>`, only when the score has no credits at
  all (so the editor prints a title page header). If credits exist, a credit
  that repeats the old title is updated and nothing else is added.
- Parts: `<part-name>` set in order, `<part-abbreviation>` added right after it
  (Soprano S., Alto A., Tenor T., Bass B., Piano Pno., Treble Tr.; "Soprano 1"
  gives "S. 1"; anything else its first three letters plus a dot, so "Baritone"
  gives "Bar."). Part and abbreviation display text and generic
  `<score-instrument>` names are kept in step. A hidden name
  (`print-object="no"`, which OMR output uses) is made visible when you name the
  part. Parts that already have a real name get a missing abbreviation filled
  in even without `--parts`. Generic names with no `--parts` are left alone.

## Workflow

1. Run `score-engraving-audit` on the scan; note the metadata findings.
2. Find out the facts: the title as printed, composer, lyricist, arranger, and
   the source's rights status. Look at the PDF if there is one; OMR often reads
   the printed credits as `<words>` text in bar 1 (for example `JOSEPH MOHR, 1818`).
3. Run `fix_metadata.py` with those values, for example:

   ```bash
   python3 "${CLAUDE_SKILL_DIR}/scripts/fix_metadata.py" raw/02.xml fixed/02.xml \
     --normalize-title --composer "Traditional" \
     --rights-template public-domain --source "the Oxford Book of Carols" \
     --parts "Soprano,Alto"
   ```

4. Run the audit again: `title-*`, `composer-missing`, `rights-missing`,
   `part-name-generic` and `part-abbreviation-missing` should be gone. Other
   findings (beams, lyrics, padding) belong to other skills (`beaming-repair`,
   `lyric-hyphenation`, `omr-score-repair`).
5. Import the fixed file into the editor.

Running it twice with the same options gives the same file.

## Notes

- The part count must match: giving more names than parts is an error; giving
  fewer names names the first parts only. Check which voice is on which staff
  before naming (a divisi score may have two Soprano parts, so name them
  "Soprano 1,Soprano 2").
- A file with no title at all needs `--title`; there is nothing to normalize.
- Only `score-partwise` files are supported.
