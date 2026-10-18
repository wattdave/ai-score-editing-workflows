---
name: melody-line
description: >
  Sibelius (via sibelius-cli). Build a single-staff melody line with lyrics for a song
  that only has a MIDI file or a scan, to make a one-voice practice recording: read a
  MIDI melody track or typed notes, quantize, fit the director's words syllable by
  syllable, import as MusicXML, save .sib and export .musicxml. Use when asked for a
  melody line, a tune-learning track, or notes plus words for a song with no choral score.
---

# Melody line from MIDI or a lead sheet

Worked on nine songs for the OSA carols (Silver Bells, Let It Snow, Rudolph, Last Christmas, Jingle Bell
Rock, Frosty, Santa Claus Is Comin' to Town, I'll Be Home for Christmas, Here Comes Santa Claus). Bundled
scripts are in `scripts/`; run them with `uv run --with mido --with lxml --with pyphen python -I SCRIPT`.

## 1. Pick the source

- **Karaoke or clean MIDI (best).** `read_notes(path, track=N)` / `channel=N` returns `(start, end, pitch)` in
  beats. Pick the track that sounds one note at a time. Karaoke files with embedded lyrics
  (`lyric_events`) tell you which onsets carry a syllable. Check the tempo with `first_tempo`.
- **A clean lead sheet or printed score.** Type the notes (`parse_notes("G4:2 E4:1.5 F4:.5 ...")`,
  duration in beats, `r:1` rest, `Bb4`, `F#4`) and use a MIDI only as a cross-check. Read the pitches from
  an enlarged crop of the staff (`pdftoppm -r 200 -x -y -W -H`) and confirm with the MIDI; judging a pitch
  by eye is unreliable, a MIDI top voice that agrees with the print is not.
- A rights-restricted scan can be an empty "Item Unavailable" page. Check it before relying on it.
- Human-played MIDIs quantize badly (dropped notes, ornaments, notes an octave high or low). If counts
  do not match, compare against a second file and merge, and tell the user what to check.

## 2. Get the words without typing them

Never write a song's lyrics into a script or a message. A full lyric block in the output got blocked by
a content filter ("Output blocked by content filtering policy") twice. Instead:

```bash
pdftoppm -r 300 -f PAGE -l PAGE -png "00 Lyrics.pdf" p      # the director's sheet
tesseract p-PAGE.png pPAGE --psm 4                          # text file
sed -n 'A,Bp' pPAGE.txt | grep -v '^$' | sed "s/[’‘]/'/g" > raw/lyrics/song.txt
```

Fix OCR typos with `sed` (smart quotes, "teiling", "befter"), look at the page image for strike-throughs and
handwritten additions, and keep the director's wording even where the print differs. The scripts read the
file. When a count mismatches, describe where it drifts; do not print the lines.

## 3. Fit syllables to notes

`syllabify(text, overrides)` splits words with pyphen and returns `Syl-la-ble` text. Words of fewer than five
letters stay whole and author hyphens are kept, so give overrides for the rest: `{"santa": "San-ta",
"away": "a-way", "around": "a-round", "frosty": "fros-ty"}`. `dump(events, ...)` prints each bar with its
syllable and ends with `-- N notes, M syllables (MATCH|MISMATCH)`. To find a drift, compare cumulative
syllables per sheet line with cumulative notes per MIDI bar.

Typical causes when counts differ: an unsplit word (4-letter words like "away"), a word sung on two
notes (give the second `_`, a note with no syllable), a held word that runs down several notes
(`sake _ _ _`), an extra word the sheet has and the tune does not ("Oh!" before a one-note pickup;
leave it out and say so), an intro verse the MIDI does not contain (start where the melody does).

## 4. Write and import

Copy `scripts/melody_template.py`, set the constants and run `--dump` until the counts match. Then run it
without `--dump` to write MusicXML (12 divisions per quarter; pickups, tied notes across barlines,
`prefer_flats`, tempo and one lyric verse are handled). Quantize with `grid=0.5` and `unswing=True` for a
swung tune you want printed straight. Round the end of long notes to the beat; for a tune that swings, make
a separate playback copy with the `swing-playback-copy` skill (the template's `--swing`).

Import and save with `scripts/sib_import.py IN.xml OUT.sib`
(`uv run --with pyobjc-framework-Quartz --with pillow --with numpy python -I scripts/sib_import.py ...`).
It opens the MusicXML (the options dialog needs a real click on OK, which the script does only when
Sibelius is the frontmost app and it brings Sibelius forward itself), saves the `.sib`, reopens it, and
exits with an error if a different score is active.

Always check the printed `fileName` and `barCount`. A failed or skipped import leaves the previous score
active, and a later export then writes the wrong score under the new name.

Then export `Song - Melody.musicxml` with `plugin ScoreBridge ExportScore --args '["PATH", "MUSICXML"]'`,
run `proofread` and, for notes against words, `check-lyrics`. Known harmless flags: "n't" as a malformed
syllable, and a low C4 near a lyric.

## 5. Report

Tell the user the judgment calls: split or merged syllables, omitted intro or echoes, rhythm taken from a
human-played file, octave choices (a user check by ear found notes written an octave high in two Frosty
phrases), swing written straight. Playback is a separate step: the user sets the Cantai voice in the Mixer,
then the `rehearsal-mixes` skill exports one mp3 per song.

## Gotchas

- Sibelius may show a "sibelius-websocket-cli wants to connect" dialog. Only the user can approve it.
- `OpenScore` of an already-open file creates another window; several windows of one score pile up.
- `timeout` is not installed on macOS; use `until` loops or run long commands in the background.
