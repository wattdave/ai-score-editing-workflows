# Cantai: the language a score is sung in

Tested 2026-11-25 with Cantai 4.0.2 (engine 4.0.2.953) and Sibelius 26.11 on macOS.

## Summary

- Cantai sings **one language per score**, for every part. Its own language dialog says so:
  "Every part in this score will sing in {Language} and render again." There is no per-staff
  or per-instance language, so two staves of one score cannot sing in different languages.
- The language lives in Cantai's settings file, not in the score or in Sibelius's playback
  configuration, and can be set from the command line with Sibelius quit:
  `sibelius-cli cantai-language`.
- Codes (from the plug-in's language menu): `en` English (US), `la` Latin, `es` Spanish,
  and the experimental `en-GB`, `it`, `pt-PT`, `pt-BR` (`ja` is hidden in the menu).

## Where the language is stored

`~/Library/Application Support/Cantai/Cantai.settings` (a JUCE properties file, XML):

| Key | Meaning |
|---|---|
| `scoreLanguage` | default for a score Cantai has not seen; follows the last language used |
| `sibLang_<md5(scoreId)>` | one score's language |
| `sibVoice_<md5(scoreId + "\|" + trackName)>` | a part's Cantai voice (`5016`, `-103\|ottetto`, ...) |
| `sibReverb_`, `sibLevel_`, `sibPron_` | per-part reverb, per-score level and pronunciation changes |

`scoreId` is a GUID that Sibelius keeps inside the .sib, so a copy of a score shares its
original's language. While a score is active, Sibelius names it in
`~/Library/Application Support/Avid/Sibelius/playback-data-export-config.json`
(`activeScore.scoreId`, `scoreName`, and the folder of per-part JSON it hands Cantai: notes,
lyrics, dynamics; no language). After Sibelius quits `activeScore` is null.

Each Cantai instance's state in the playback configuration
(`Playback Configurations/Cantai data/Cantai_N.fxb`: a 4-byte length, then a JUCE ValueTree
`CantaiState` with `trackName`, `voiceId`, `scoreLanguage`, ...) also has a `scoreLanguage`,
but it does not decide the language: with every instance file at `es`, scores sang in
whatever `Cantai.settings` held.

## What was tested

One 8-staff Latin score (a scratch copy), staves 1 and 8 exported with `export-stem` after the
status bar showed no "Rendering N items":

- Two exports in the same language are bit-identical (difference about -167 dB), also across
  a Sibelius restart.
- `en`, `la` and `es` renders of the same staff are each different (difference about +3 dB:
  unrelated audio), so the language setting changes the singing. Pronunciation itself was not
  judged by ear.
- `sibLang_<id>` edited with Sibelius quit: takes effect when the score is next opened. Edited
  while Sibelius runs: ignored until restart (and Cantai could write its own value over it).
- Entry removed: Cantai used the default `scoreLanguage` and wrote it back as the score's
  entry. Neither the `.fxb` instance state nor anything in the .sib won.

## Re-rendering

Cantai renders lazily: after a restart with a new language nothing renders until playback or
an export asks for audio. The first export after the change still returns the **old**
language's cached audio, and the status bar then shows "Rendering 8 items 0%" (every part of
the score, not only some). For the 8-part, 2-minute score the render took about 80 to 90 s.
Switching back to a language rendered before is fast ("Rendering 6 items", a few seconds):
renders are cached per language. Exports made while "Rendering N items" shows are unreliable;
wait until it clears. The status bar text is readable through Accessibility (window's
"Status Bar" group: an `AXStaticText` "Rendering N items" and an `AXProgressIndicator`
"Plugin background task progress" with the percent), so a script can wait for it.

## Procedure

```bash
sibelius-cli cantai-language                 # score open in Sibelius: prints its id and language
# quit Sibelius (answer any save sheet)
sibelius-cli cantai-language la --score-id <GUID>
# reopen the score, export once (this starts the render), wait for "Rendering N items" to clear
```

`--default` also sets Cantai's default for new scores; `--dry-run` writes nothing. The command
backs up `Cantai.settings` first (to `--backup-dir`, else beside it) and refuses while
Sibelius runs.

## Different languages for different voices

Not possible inside one score. Workarounds, untested end to end:

- Export the stems of the staves that sing in language A, quit, switch the score to language
  B, reopen, wait for the render, export the other staves, then mix the stems.
  `rehearsal-mixes` cannot yet mix stems made in separate runs.
- Or split the voices into two scores with different ids (a fresh MusicXML import gets a new
  id; a copied .sib does not) and give each its own language.
- Cantai's pronunciation editor (per word, "this one" in one part, or the whole score) could in
  principle re-spell single words of one part, but it is built for English and is not a way to
  change a whole part's language.
