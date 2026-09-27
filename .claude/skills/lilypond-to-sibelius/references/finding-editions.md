# Finding editable editions

For a folder of PDFs, find which pieces have an engraving source online
before scanning anything.

## Where to look

- **CPDL** (cpdl.org, ChoralWiki): most early choral music. Each edition
  lists its files: PDF, MIDI, and often a source file (MusicXML `.mxl`/`.xml`,
  Finale `.mus`, Sibelius `.sib`, MuseScore `.mscz`, LilyPond `.ly`, Capella
  `.capx`, NoteWorthy `.nwc`).
- **IMSLP** (imslp.org): look for "Engraving files" or "typeset by editor"
  entries next to the PDFs.
- **MuseScore.com**: user arrangements; check it is the same edition.

MusicXML is the useful format: Sibelius opens it directly. LilyPond works via
the [LilyPond workflow](../SKILL.md). Finale, Capella and NoteWorthy files
need their own software.

## Matching a PDF to an edition

- **File names.** Downloads keep the site's name: `GIBB-IWE.pdf` or
  `Fortuna_desperata_(Busnois).pdf` match a CPDL file exactly, and
  `IMSLP514554-...pdf` names the IMSLP file number.
- **PDF metadata** (`mdls -raw -name kMDItemCreator file.pdf` on macOS)
  names the program that made it: "Sibelius 7.1.3" means someone has a
  `.sib`; Finale fonts point at Finale-era CPDL editions; "Firefox" or
  "Preview" means it was printed from somewhere else.
- **Page text.** Compare the first page's text and page count with the
  candidate edition's PDF. Identical text is a strong match.
- A different edition of the same piece may still do for playback, but bar
  numbers can differ from the singers' copies.

## Downloading

CPDL and IMSLP block scripted downloads behind a bot check, and bypassing it
is not appropriate. Use the user's browser (Claude in Chrome): once a CPDL
page loads, same-origin `fetch()` of
`/wiki/index.php?title=PAGE&action=raw` gives an edition's wiki source (file
names, editors, formats), and `/wiki/index.php/Special:FilePath/FILE` gives
the file. Chrome asks once before allowing several downloads; the user must
click Allow. Files land in `~/Downloads`: move them into the piece's folder.
Google Drive folders shared publicly can be listed and downloaded with curl.
