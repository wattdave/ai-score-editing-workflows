---
name: score-editing
description: >
  Start here for any request about a music score. Picks the right back end
  (Sibelius, Dorico or MuseScore) for the score the user has open, and the
  right shared workflow (LilyPond import, OMR repair, SATB splitting,
  rehearsal mixes, playback fixes). Use when the user does not name an
  application, or asks what this repository can do.
---

# Score editing: which tool for which score

This repository drives three score editors through the same kind of tools
(`score_overview`, `query_score`, `apply_batch` with `dry_run`, `undo`,
`save_score`, `export_score`) and the same units (1/256 of a quarter note,
MIDI pitches, `staff/bar/index` addresses).

## 1. Find out which editor is in use

Ask the user, or check which one is running. Do not guess: each MCP server
controls only the score open in its own application.

| Editor | MCP server | CLI | Skill |
| --- | --- | --- | --- |
| Sibelius (Ultimate 2026.6+) | `sibelius` | `sibelius-cli` | `sibelius` |
| Dorico (6.2+) | `dorico` | `dorico-cli` | `dorico` |
| MuseScore 4 (4.6+) | `musescore` | `musescore-cli` | `musescore` |

If no editor is open, or only a file (MusicXML, PDF, `.ly`) is given, use
the file workflows below, then import the result into the user's editor.

## 2. Then load that editor's skill

Load the skill from the table and follow it. Back ends differ in what they
can do (for example, hairpins cannot be added in MuseScore); each skill
says where its limits are.

## 3. Shared and app-specific workflows

| Task | Skill | Works in |
| --- | --- | --- |
| LilyPond source to a readable score | `lilypond-to-score` | any editor (MusicXML) |
| Sibelius-exported vector PDF to MusicXML (no OMR) | `vector-pdf-score` | any editor (MusicXML) |
| PDF to score with MuseScore's online converter (4.7.6+) | `musescore-pdf-convert` | MuseScore (then MusicXML) |
| Scanned or OMR-imported MusicXML cleanup | `omr-score-repair` | any editor (checked in Sibelius) |
| Rehearsal tracks, per-voice MP3s | `rehearsal-mixes` | Sibelius |
| Split 2-staff choral scores into SATB | `satb-part-splitting` | Sibelius |
| One-note-per-staff playback copy | `playback-divisi-split` | Sibelius |
| Hanging playback notes | `hanging-playback-note-repair` | Sibelius |
| Octave-high tenor playback after import | `tenor-playback-repair` | Sibelius |
| First-time install | `setup` | all |

If a Sibelius-only workflow is wanted for a Dorico or MuseScore score, say
so plainly: do not run `sibelius-cli` against a score open elsewhere.
