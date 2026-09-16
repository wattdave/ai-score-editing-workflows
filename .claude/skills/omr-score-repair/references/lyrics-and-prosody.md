# Lyric Encoding, Syllable Alignment, and Prosody in MusicXML

OMR software frequently mangles lyrics: reading hymn numbers as lyrics, merging syllables across words, dropping hyphens, and omitting melisma extenders. This reference specifies how to properly encode lyrics in MusicXML.

---

## 1. Core MusicXML `<lyric>` Elements

Every sung note can contain one or more `<lyric number="1">` elements.

### Syllabic Classification (`<syllabic>`)
- `single`: The entire word consists of this single syllable (e.g. `con`, `les`). No hyphens generated.
- `begin`: The first syllable of a multi-syllable word (e.g. `pe-` in `peregrinos`). MusicXML renderers append a hyphen after this syllable.
- `middle`: An interior syllable of a multi-syllable word (e.g. `-re-` in `pe-re-gri-nos`). Renderers place hyphens before and after.
- `end`: The final syllable of a multi-syllable word (e.g. `-nos` in `pe-re-gri-nos`). Renderers place a hyphen before this syllable.

```xml
<!-- Example: pe-re-gri-nos -->
<note>
  <lyric number="1">
    <syllabic>begin</syllabic>
    <text>pe</text>
  </lyric>
</note>
...
<note>
  <lyric number="1">
    <syllabic>middle</syllabic>
    <text>re</text>
  </lyric>
</note>
...
<note>
  <lyric number="1">
    <syllabic>middle</syllabic>
    <text>gri</text>
  </lyric>
</note>
...
<note>
  <lyric number="1">
    <syllabic>end</syllabic>
    <text>nos;</text>
  </lyric>
</note>
```

> [!IMPORTANT]
> **Do not add manual hyphens to `<text>` when using `begin` or `middle`.** MusicXML notation engines (Sibelius, Dorico, Finale, MuseScore) automatically format and position hyphens between syllables based on the `<syllabic>` tag. Adding manual hyphens (e.g. `<text>pe-</text>`) often causes double hyphens in the engraved score.

---

## 2. Melismas and Extender Lines (`<extend/>`)

When a single syllable is held or sung across multiple notes (often indicated by a slur or beam group):
1. The first note of the melisma contains the `<lyric>` with `<text>` and an optional `<extend/>` element.
2. Subsequent notes in the melisma do **not** repeat the lyric, but may include `<extend/>` or rely on the note slur.

```xml
<note>
  <pitch><step>F</step><alter>1</alter><octave>4</octave></pitch>
  <notations><slur type="start" number="1"/></notations>
  <lyric number="1">
    <syllabic>end</syllabic>
    <text>sé y</text>
    <extend/>
  </lyric>
</note>
<note>
  <pitch><step>G</step><octave>4</octave></pitch>
  <notations><slur type="stop" number="1"/></notations>
</note>
```

---

## 3. Song Numbers and Title Metadata

In songbooks and hymnals, a song number (e.g. `10.`) is often printed immediately before the first word:
- **Incorrect OMR pattern:** OCR reads `10.` as the first lyric syllable and attaches it to Note 1, discarding the actual first word (e.g. `Perdón`).
- **Best Practice:** Either:
  1. Prefix the first syllable: `<text>10. Per</text>` (with `<syllabic>begin</syllabic>`), or
  2. Separate the song number into score metadata / title and keep the lyric pure: `<text>Per</text>`.

---

## 4. Contractions and Vocal Synalepha

In Romance languages (Spanish, Italian, French), two vowels across word boundaries are frequently sung on a single beat/note (synalepha):
- Example: *"José y María"* $\to$ *"sé y"* sung together on beat 1.
- Example: *"mucha alegría"* $\to$ *"cha a-"* or *"mu-cha a-le-grí-a"*.
- Encode both words in the same `<text>` tag (e.g. `<text>sé y</text>` or `<text>cha_a</text>`) with `single` or `end` syllabic to ensure proper note alignment.
