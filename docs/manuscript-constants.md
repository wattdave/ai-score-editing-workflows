# ManuScript Language Guide — Chapter 7: Global Constants

Source: *Sibelius ManuScript Language Guide* (Sibelius 2024.8), https://resources.avid.com/SupportFiles/Sibelius/2024.8/ManuScript_Language_Guide.pdf
Chapter 7 spans PDF pages 181–216 (folios clxxxi–ccxvi).

These are variables held internally within ManuScript, accessible from any plug-in; they are called "constants" because you are encouraged not to change them. Many are note-value names usable to specify positions in a bar (e.g. `Quarter+Sixteenth` or `Crotchet+Semiquaver` instead of `320`).

## Truth Values

| Constant | Value |
| --- | --- |
| `True` | 1 |
| `False` | 0 |

## Measurements

| Constant | Value |
| --- | --- |
| `Space` | 32 |
| `StaffHeight` | 128 |

## Positions and Durations

| Constant | Value |
| --- | --- |
| `Long` | 4096 |
| `Breve` | 2048 |
| `DottedBreve` | 3072 |
| `Whole` or `Semibreve` | 1024 |
| `DottedWhole` | 1536 |
| `Half` or `Minim` | 512 |
| `DottedHalf` or `DottedMinim` | 768 |
| `Quarter` or `Crotchet` | 256 |
| `DottedQuarter` or `DottedCrotchet` | 384 |
| `Eighth` or `Quaver` | 128 |
| `DottedEighth` or `DottedQuaver` | 192 |
| `Sixteenth` or `Semiquaver` | 64 |
| `DottedSixteenth` or `DottedSemiquaver` | 96 |
| `ThirtySecond` or `Demisemiquaver` | 32 |
| `DottedThirtySecond` or `DottedDemisemiquaver` | 48 |
| `SixtyFourth` or `Hemidemisemiquaver` | 16 |
| `DottedSixtyFourth` or `DottedHemidemisemiquaver` | 24 |
| `OneHundredTwentyEighth` or `Semihemidemisemiquaver` | 8 |
| `DottedOneHundredTwentyEighth` or `DottedSemihemidemisemiquaver` | 12 |

## Style Names

For the `ApplyStyle()` method of Score objects. Mixed-case variable equivalents of these strings also exist (e.g. `AllStyles`). Note `HOUSE` covers only House Style > Engraving Rules and Layout > Document Setup; use `ALLSTYLES` to apply the entire House Style.

| Constant | Value |
| --- | --- |
| `EngravingRules` | "ENGRAVINGRULES" |
| `House` | "HOUSE" |
| `Text` | "TEXT" |
| `Symbols` | "SYMBOLS" |
| `Lines` | "LINES" |
| `Noteheads` | "NOTEHEADS" |
| `Clefs` | "CLEFS" |
| `DocumentSetup` | "DOCSETUP" |
| `Dictionary` | "DICTIONARY" |
| `SpacingRule` | "SPACINGRULE" |
| `CustomChordNames` | "CUSTOMCHORDNAMES" |
| `DefaultPartAppearance` | "DEFAULTPARTAPPEARANCE" |
| `InstrumentsAndEnsembles` | "INSTRUMENTSANDENSEMBLES" |
| `AllStyles` | "ALLSTYLES" |

## Bar Number Formats

For the format argument of the `AddBarNumber` method.

| Constant | Value |
| --- | --- |
| `BarNumberFormatNormal` | 0 |
| `BarNumberFormatNumberLetterLower` | 1 |
| `BarNumberFormatNumberLetterUpper` | 2 |

## Text Styles

Text style identifiers guaranteed to be present in any Sibelius score (numeric indices are deprecated). English name, then identifier.

| Name | Identifier |
| --- | --- |
| Instrument names | `text.instrumentname` |
| Time signatures (one staff only) | `text.staff.timesig.onestaffonly` |
| 1st and 2nd endings | `text.staff.1st_n_2nd_endings` |
| Tuplets | `text.staff.tuplets` |
| Auto page break warnings | `text.staff.autopagebreak.warnings` |
| Bar numbers | `text.system.barnumber` |
| Boxed text | `text.staff.boxed` |
| Metronome mark | `text.system.metronome` |
| Expression | `text.staff.expression` |
| Multirests (numbers) | `text.system.multirestnumbers` |
| Chord diagram fingering | `text.staff.fingering.chord_diagrams` |
| Composer | `text.system.page_aligned.composer` |
| Footnote | `text.staff.footnote` |
| Composer | `text.system.page_7GlobalConstants(ontitlepage)aligned.composer.ontitlepage` |
| Block lyrics | `text.staff.lyrics.block` |
| Copyright | `text.system.page_aligned.copyright` |
| Multirests (tacet) | `text.staff.multirests.tacet` |
| Dedication | `text.system.page_aligned.dedication` |
| Plain text | `text.staff.plain` |
| Footer (inside edge) | `text.system.page_aligned.footer.inside` |
| Small text | `text.staff.small` |
| Footer (outside edge) | `text.system.page_aligned.footer.outside` |
| Chord symbol | `text.staff.space.chordsymbol` |
| Worksheet footer (first page, l) | `text.system.page_aligned.footer.worksheet.left` |
| Figured bass | `text.staff.space.figuredbass` |
| Header | `text.system.page_aligned.header` |
| Fingering | `text.staff.space.fingering` |
| Worksheet header (first page, l) | `text.system.page_aligned.header.worksheet.left` |
| Chord diagram fret | `text.staff.space.fretnumbers` |
| Worksheet header (first page, r) | `text.system.page_aligned.header.worksheet.right` |
| Lyrics above staff | `text.staff.space.hypen.lyrics.above` |
| Header (after first page) | `text.system.page_aligned.header_notp1` |
| Lyrics (chorus) | `text.staff.space.hypen.lyrics.chorus` |
| Header (after first page, inside edge) | `text.system.page_aligned.header_notp1.inside` |
| Lyrics line 1 | `text.staff.space.hypen.lyrics.verse1` |
| Instrument name at top left | `text.system.page_aligned.instrnametopleft` |
| Lyrics line 2 | `text.staff.space.hypen.lyrics.verse2` |
| Lyricist | `text.system.page_aligned.lyricist` |
| Lyrics line 3 | `text.staff.space.hypen.lyrics.verse3` |
| Page numbers | `text.system.page_aligned.pagenumber` |
| Lyrics line 4 | `text.staff.space.hypen.lyrics.verse4` |
| Subtitle | `text.system.page_aligned.subtitle` |
| Lyrics line 5 | `text.staff.space.hypen.lyrics.verse5` |
| Title | `text.system.page_aligned.title` |
| Nashville chord numbers | `text.staff.space.nashvillechords` |
| Title (on title page) | `text.system.page_aligned.title.ontitlepage` |
| Common symbols | `text.staff.symbol.common` |
| Rehearsal mark | `text.system.rehearsalmarks` |
| Figured bass (extras) | `text.staff.symbol.figured.bass.extras` |
| Repeat (D.C./ D.S./To Coda) | `text.system.repeat` |
| 7 Global Constants Note tails | `text.staff.symbol.noteflags` |
| Tempo | `text.system.tempo` |
| Special noteheads | `text.staff.symbol.noteheads.special` |
| Timecode | `text.system.timecode` |
| Percussion instruments | `text.staff.symbol.percussion` |
| Duration at end of score | `text.system.timecode.duration` |
| Special symbols | `text.staff.symbol.special` |
| Hit points | `text.system.timecode.hitpoints` |
| Tablature letters | `text.staff.tab.letters` |
| Time signatures (huge) | `text.system.timesig.huge` |
| Tablature numbers | `text.staff.tab.numbers` |
| Time signatures (large) | `text.system.timesig.large` |
| Technique | `text.staff.technique` |
| Time signatures | `text.system.timesig.normal` |
| Boxed text (on blank page | `text.blankpage.boxed` |
| Composer (on blank page | `text.blankpage.composer` |
| Dedication (on blank page) | `text.blankpage.dedication` |
| Instrument name at top left (on blank page) | `text.blankpage.instrumentname` |
| Plain text (on blank page) | `text.blankpage.plain` |
| Plain text, centered (on blank page) | `text.blankpage.plain.centered` |
| Plain text, right (on blank page) | `text.blankpage.plain.right` |
| Subtitle (on blank page) | `text.blankpage.subtitle` |
| Title (on blank page) | `text.blankpage.title` |

## Line Styles

| Name | Identifier |
| --- | --- |
| Arpeggio | `line.staff.arpeggio` |
| Bracketed slur below | `line.staff.slur.down.bracketed` |
| Arpeggio down | `line.staff.arpeggio.down` |
| Dashed slur below | `line.staff.slur.down.dashed` |
| Arpeggio up | `line.staff.arpeggio.up` |
| Dotted slur below | `line.staff.slur.down.dotted` |
| Unused 2 | `line.staff.arrow` |
| Slur above | `line.staff.slur.up` |
| Arrow | `line.staff.arrow.black.right` |
| Bracketed slur above | `line.staff.slur.up.bracketed` |
| Dashed arrow | `line.staff.arrow.black.right.dashed` |
| Dashed slur above | `line.staff.slur.up.dashed` |
| Double arrow | `line.staff.arrow.black.right.left` |
| Dotted slur above | `line.staff.slur.up.dotted` |
| 7 Global Constants Vertical arrow (2) | `line.staff.arrow.black.vertical` |
| String indicator above (1) | `line.staff.string.above.1` |
| White arrow | `line.staff.arrow.white.right` |
| String indicator above (2) | `line.staff.string.above.2` |
| Dashed white arrow | `line.staff.arrow.white.right.dashed` |
| String indicator above (3) | `line.staff.string.above.3` |
| Double white arrow | `line.staff.arrow.white.right.left` |
| String indicator above (4) | `line.staff.string.above.4` |
| Vertical arrow | `line.staff.arrow.white.vertical` |
| String indicator above (5) | `line.staff.string.above.5` |
| Beam | `line.staff.beam` |
| String indicator above (6) | `line.staff.string.above.6` |
| Guitar Bend | `line.staff.bend` |
| String indicator above (7) | `line.staff.string.above.7` |
| Guitar hold bend | `line.staff.bend.hold` |
| String indicator above (8) | `line.staff.string.above.8` |
| Box | `line.staff.box` |
| String indicator below (1) | `line.staff.string.below.1` |
| Bracket above | `line.staff.bracket.above` |
| String indicator below (2) | `line.staff.string.below.2` |
| Bracket above (end) | `line.staff.bracket.above.end` |
| String indicator below (3) | `line.staff.string.below.3` |
| Bracket above (start) | `line.staff.bracket.above.start` |
| String indicator below (4) | `line.staff.string.below.4` |
| Bracket below | `line.staff.bracket.below` |
| String indicator below (5) | `line.staff.string.below.5` |
| Bracket below (end) | `line.staff.bracket.below.end` |
| String indicator below (6) | `line.staff.string.below.6` |
| Bracket below (start) | `line.staff.bracket.below.start` |
| String indicator below (7) | `line.staff.string.below.7` |
| Vertical bracket | `line.staff.bracket.vertical` |
| String indicator | `line.staff.string.below.8` |
| 7 Global Constants below (8) Vertical bracket 2 | `line.staff.bracket.vertical.2` |
| Tie | `line.staff.tie` |
| Dashed line | `line.staff.dashed` |
| Trill | `line.staff.trill` |
| Vertical dashed line | `line.staff.dashed.vertical` |
| Tuplet | `line.staff.tuplet` |
| Dotted line | `line.staff.dotted` |
| Vertical line | `line.staff.vertical` |
| Glissando (straight) | `line.staff.gliss.straight` |
| Vibrato | `line.staff.vibrato` |
| Glissando (wavy) | `line.staff.gliss.wavy` |
| Guitar vibrato bar | `line.staff.vibrato.bar` |
| Guitar effect | `line.staff.guitareffect` |
| Wide vibrato | `line.staff.vibrato.wide` |
| Crescendo | `line.staff.hairpin.crescendo` |
| Dashed system line | `line.system.dashed` |
| Bracketed crescendo | `line.staff.hairpin.crescendo.bracketed` |
| Wide dashed system line | `line.system.dashed.wide` |
| Dashed crescendo | `line.staff.hairpin.crescendo.dashed` |
| 1st ending | `line.system.repeat.1st` |
| Dotted crescendo | `line.staff.hairpin.crescendo.dotted` |
| 1st and 2nd ending | `line.system.repeat.1st_n_2nd` |
| Crescendo from silence | `line.staff.hairpin.crescendo.fromsilence` |
| 2nd ending | `line.system.repeat.2nd` |
| Diminuendo | `line.staff.hairpin.diminuendo` |
| 2nd ending (closed) | `line.system.repeat.2nd.closed` |
| Bracketed diminuendo | `line.staff.hairpin.diminuendo.bracketed` |
| 3rd ending | `line.system.repeat.3rd` |
| Dashed diminuendo | `line.staff.hairpin.diminuendo.dashed` |
| Repeat ending (closed) | `line.system.repeat.closed` |
| Dotted diminuendo | `line.staff.hairpin.diminuendo.dotted` |
| Repeat ending (open) | `line.system.repeat.open` |
| Diminuendo to silence | `line.staff.hairpin.diminuendo.tosilence` |
| Accel. | `line.system.tempo.accel` |
| Guitar artificial harmonic | `line.staff.harmonic.artificial` |
| Accel. (italic) | `line.system.tempo.accel.italic` |
| Guitar harp harmonic | `line.staff.harmonic.harp` |
| Accel. (italic, text only) | `line.system.tempo.accel.italic.textonly` |
| Guitar pinch harmonic | `line.staff.harmonic.pinch` |
| Molto accel. | `line.system.tempo.accel.molto` |
| 7 Global Constants Guitar touch harmonic | `line.staff.harmonic.touch` |
| Molto accel. (text only) | `line.system.tempo.accel.molto.textonly` |
| Guitar harmonics | `line.staff.harmonics` |
| Poco accel. | `line.system.tempo.accel.poco` |
| Hauptstimme | `line.staff.hauptstimme` |
| Poco accel. (text only) | `line.system.tempo.accel.poco.textonly` |
| Guitar let ring | `line.staff.letring` |
| Accel. (text only) | `line.system.tempo.accel.textonly` |
| Lyric line | `line.staff.lyric` |
| Tempo change (arrow right) | `line.system.tempo.arrowright` |
| Guitar palm mute | `line.staff.mute.palm` |
| Rall. | `line.system.tempo.rall` |
| Nebenstimme | `line.staff.nebenstimme` |
| Rall. (italic) | `line.system.tempo.rall.italic` |
| 2 octaves down | `line.staff.octava.minus15` |
| Rall. (italic, text only) | `line.system.tempo.rall.italic.textonly` |
| Octave down | `line.staff.octava.minus8` |
| Molto rall. | `line.system.tempo.rall.molto` |
| 2 octaves up | `line.staff.octava.plus15` |
| Molto rall. (text only) | `line.system.tempo.rall.molto.textonly` |
| Octave up | `line.staff.octava.plus8` |
| Poco rall. | `line.system.tempo.rall.poco` |
| Pedal | `line.staff.pedal` |
| Poco rall. (text only) | `line.system.tempo.rall.poco.textonly` |
| Pedal lift | `line.staff.pedal.lift` |
| Rall. (text only) | `line.system.tempo.rall.textonly` |
| Pedal lift again | `line.staff.pedal.lift.again` |
| Rit. | `line.system.tempo.rit` |
| Pedal lift finally | `line.staff.pedal.lift.finally` |
| Rit. (italic) | `line.system.tempo.rit.italic` |
| Pedal (no line) | `line.staff.pedal.noline` |
| Rit. (italic, text only) | `line.system.tempo.rit.italic.textonly` |
| Guitar pick scrape | `line.staff.pick.scrape` |
| Molto rit. | `line.system.tempo.rit.molto` |
| Line | `line.staff.plain` |
| Molto rit. (text only) | `line.system.tempo.rit.molto.textonly` |
| Portamento | `line.staff.port.straight` |
| Poco rit. | `line.system.tempo.rit.poco` |
| Guitar rake | `line.staff.rake` |
| Poco rit. (text only) | `line.system.tempo.rit.poco.textonly` |
| Guitar slide | `line.staff.slide` |
| Rit. (text only) | `line.system.tempo.rit.textonly` |
| Slur below | `line.staff.slur.down` |

## Clef Styles

Clef style identifiers guaranteed to be present in any score, for use with the `Stave.AddClef` method.

| Name | Identifier |
| --- | --- |
| Alto | `clef.alto` |
| Small tab | `clef.tab.small` |
| Baritone C | `clef.baritone.c` |
| Small tab (taller) | `clef.tab.small.taller` |
| Baritone F | `clef.baritone.f` |
| Tab (taller) | `clef.tab.taller` |
| Bass | `clef.bass` |
| Tenor | `clef.tenor` |
| Bass down 8 | `clef.bass.down.8` |
| Tenor down 8 | `clef.tenor.down.8` |
| Bass up 15 | `clef.bass.up.15` |
| Treble | `clef.treble` |
| Bass up 8 | `clef.bass.up.8` |
| Treble down 8 | `clef.treble.down.8` |
| Null | `clef.null` |
| Treble (down 8) | `clef.treble.down.8.bracketed` |
| Percussion | `clef.percussion` |
| Treble down 8 (old) | `clef.treble.down.8.old` |
| Percussion 2 | `clef.percussion_2` |
| Treble up 15 | `clef.treble.up.15` |
| Soprano | `clef.soprano` |
| Treble up 8 | `clef.treble.up.8` |
| Mezzo-soprano | `clef.soprano.mezzo` |
| French violin | `clef.violin.french` |
| Tab | `clef.tab` |
| Sub-bass F | `clef.sub-bass.f` |

## Instrument Types

Instrument type identifiers guaranteed to be present in any score. Only the tablature stave types can be used with guitar frames; the rest are included for completeness.

| Name | Identifier |
| --- | --- |
| Alp-Horn in F | `instrument.brass.alp-horn.f` |
| Alp-Horn in G | `instrument.brass.alp-horn.g` |
| Baritone Bugle in G | `instrument.brass.bugle.baritone.g` |
| Contrabass Bugle in G | `instrument.brass.bugle.contrabass.g` |
| Euphonium Bugle in G | `instrument.brass.bugle.euphonium.g` |
| Mellophone Bugle in G | `instrument.brass.bugle.mellophone.g` |
| Soprano Bugle in G | `instrument.brass.bugle.soprano.g` |
| Cimbasso in Bb | `instrument.brass.cimbasso.bflat` |
| Cimbasso in Eb | `instrument.brass.cimbasso.eflat` |
| Cimbasso in F | `instrument.brass.cimbasso.f` |
| Cornet in A | `instrument.brass.cornet.a` |
| Cornet in Bb | `instrument.brass.cornet.bflat` |
| Soprano Cornet in Eb | `instrument.brass.cornet.soprano.eflat` |
| Euphonium in Bb [treble clef] | `instrument.brass.euphonium` |
| Euphonium in Bb [bass clef, treble transp.] | `instrument.brass.euphonium.bassclef` |
| Euphonium in C [bass clef] | `instrument.brass.euphonium.bassclef.bassclef` |
| 7 Global Constants Euphonium in Bb [bass clef] | `instrument.brass.euphonium.bflat.bassclef.bassclef` |
| Flugelhorn | `instrument.brass.flugelhorn` |
| Horn in A [no key] | `instrument.brass.horn.a.nokeysig` |
| Horn in Ab alto [no key] | `instrument.brass.horn.alto.aflat.nokeysig` |
| Alto Horn in Eb | `instrument.brass.horn.alto.eflat` |
| Alto Horn in F | `instrument.brass.horn.alto.f` |
| Horn in B [no key] | `instrument.brass.horn.b.nokeysig` |
| Baritone in Bb [treble clef] | `instrument.brass.horn.baritone` |
| Baritone in C [treble clef] | `instrument.brass.horn.baritone.2` |
| Baritone in Bb [bass clef, treble transp.] | `instrument.brass.horn.baritone.bassclef` |
| Baritone in C [bass clef] | `instrument.brass.horn.baritone.bassclef.bassclef` |
| Bass in Bb | `instrument.brass.horn.bass.bflat` |
| Bass in Bb [bass clef, treble transp.] | `instrument.brass.horn.bass.bflat.bassclef` |
| Bass in C | `instrument.brass.horn.bass.c` |
| Bass in Eb | `instrument.brass.horn.bass.eflat` |
| Bass in Eb [bass clef, treble transp.] | `instrument.brass.horn.bass.eflat.bassclef` |
| A Basso Horn [no key] | `instrument.brass.horn.basso.a.nokeysig` |
| Bb Basso Horn [no key] | `instrument.brass.horn.basso.bflat.nokeysig` |
| C Basso Horn [no key] | `instrument.brass.horn.basso.c.nokeysig` |
| Horn in Bb [no key] | `instrument.brass.horn.bflat.nokeysig` |
| Horn in C [no key] | `instrument.brass.horn.c.nokeysig` |
| Horn in D [no key] | `instrument.brass.horn.d.nokeysig` |
| Horn in Db [no key] | `instrument.brass.horn.dflat.nokeysig` |
| Horn in E [no key] | `instrument.brass.horn.e.nokeysig` |
| Horn in Eb | `instrument.brass.horn.eflat` |
| Horn in Eb [no key] | `instrument.brass.horn.eflat.nokeysig` |
| Horn in F | `instrument.brass.horn.f` |
| Horn in F [bass clef] | `instrument.brass.horn.f.bassclef` |
| Horn in F [no key] | `instrument.brass.horn.f.nokeysig` |
| Horn in F# [no key] | `instrument.brass.horn.fsharp.nokeysig` |
| Horn in G [no key] | `instrument.brass.horn.g.nokeysig` |
| Tenor Horn | `instrument.brass.horn.tenor` |
| Mellophone in Eb | `instrument.brass.mellophone.eflat` |
| Mellophone in F | `instrument.brass.mellophone.f` |
| Mellophonium in Eb | `instrument.brass.mellophonium.eflat` |
| Mellophonium in F | `instrument.brass.mellophonium.f` |
| 7 Global Constants Ophicleide | `instrument.brass.ophicleide` |
| Brass | `instrument.brass.section` |
| Serpent | `instrument.brass.serpent` |
| Sousaphone in Bb | `instrument.brass.sousaphone.bflat` |
| Sousaphone in Eb | `instrument.brass.sousaphone.eflat` |
| Trombone | `instrument.brass.trombone` |
| Alto Trombone | `instrument.brass.trombone.alto` |
| Bass Trombone | `instrument.brass.trombone.bass` |
| Trombone in Bb [bass clef, treble transp.] | `instrument.brass.trombone.bassclef.trebleclef` |
| Contrabass Trombone | `instrument.brass.trombone.contrabass` |
| Tenor Trombone | `instrument.brass.trombone.tenor` |
| Trombone in Bb [treble clef] | `instrument.brass.trombone.trebleclef` |
| Trumpet in A | `instrument.brass.trumpet.a` |
| Trumpet in B [no key] | `instrument.brass.trumpet.b.nokeysig` |
| Bass Trumpet in Bb | `instrument.brass.trumpet.bass.bflat` |
| Bass Trumpet in Eb | `instrument.brass.trumpet.bass.eflat` |
| Trumpet in Bb | `instrument.brass.trumpet.bflat` |
| Trumpet in Bb [no key] | `instrument.brass.trumpet.bflat.nokeysig` |
| Trumpet in C | `instrument.brass.trumpet.c` |
| Trumpet in D | `instrument.brass.trumpet.d` |
| Trumpet in Db | `instrument.brass.trumpet.dflat` |
| Trumpet in E [no key] | `instrument.brass.trumpet.e.nokeysig` |
| Trumpet in Eb | `instrument.brass.trumpet.eflat` |
| Trumpet in F | `instrument.brass.trumpet.f` |
| Trumpet in G [no key] | `instrument.brass.trumpet.g.nokeysig` |
| Piccolo Trumpet in A | `instrument.brass.trumpet.piccolo.a` |
| Piccolo Trumpet in Bb | `instrument.brass.trumpet.piccolo.bflat` |
| Tenor Trumpet in Eb | `instrument.brass.trumpet.tenor.eflat` |
| Tuba | `instrument.brass.tuba` |
| Tuba in F | `instrument.brass.tuba.f` |
| Tenor Tuba (Wagner, in Bb) | `instrument.brass.tuba.tenor` |
| Tenor Tuba [bass clef] | `instrument.brass.tuba.tenor.bassclef` |
| Wagner Tuba in Bb | `instrument.brass.tuba.wagner.bflat` |
| Wagner Tuba in F | `instrument.brass.tuba.wagner.f` |
| Applause | `instrument.exotic.applause` |
| Birdsong | `instrument.exotic.birdsong` |
| 7 Global Constants Helicopter | `instrument.exotic.helicopter` |
| Ondes Martenot | `instrument.exotic.ondes-martenot` |
| Sampler | `instrument.exotic.sampler` |
| Seashore | `instrument.exotic.seashore` |
| Tape | `instrument.exotic.tape` |
| Telephone | `instrument.exotic.telephone` |
| Theremin | `instrument.exotic.theremin` |
| Bajo [notation] | `instrument.fretted.bajo.5lines` |
| Bajo, 6-string [tab] | `instrument.fretted.bajo.tab` |
| Bajo, 4-string [tab] | `instrument.fretted.bajo.tab.4lines` |
| Bajo, 5-string [tab] | `instrument.fretted.bajo.tab.5lines` |
| Alto Balalaika [notation] | `instrument.fretted.balalaika.alto.5lines` |
| Alto Balalaika [tab] | `instrument.fretted.balalaika.alto.tab` |
| Bass Balalaika [notation] | `instrument.fretted.balalaika.bass.5lines` |
| Bass Balalaika [tab] | `instrument.fretted.balalaika.bass.tab` |
| Contrabass Balalaika [notation] | `instrument.fretted.balalaika.contrabass.5lines` |
| Contrabass Balalaika [tab] | `instrument.fretted.balalaika.contrabass.tab` |
| Prima Balalaika [notation] | `instrument.fretted.balalaika.prima.5lines` |
| Prima Balalaika [tab] | `instrument.fretted.balalaika.prima.tab` |
| Second Balalaika [notation] | `instrument.fretted.balalaika.second.5lines` |
| Second Balalaika [tab] | `instrument.fretted.balalaika.second.tab` |
| Bandola [notation] | `instrument.fretted.bandola.5lines` |
| Bandola [tab] | `instrument.fretted.bandola.tab` |
| Bandolón [notation] | `instrument.fretted.bandolon.5lines` |
| Bandolón [tab] | `instrument.fretted.bandolon.tab` |
| Bandurria [notation] | `instrument.fretted.bandurria.5lines` |
| Bandurria [tab] | `instrument.fretted.bandurria.tab` |
| Banjo [notation] | `instrument.fretted.banjo.5lines` |
| Banjo (aDADE tuning) [tab] | `instrument.fretted.banjo.aDADE.tab` |
| Banjo (aEADE tuning) [tab] | `instrument.fretted.banjo.aEADE.tab` |
| Banjo (gCGBD tuning) [tab] | `instrument.fretted.banjo.gCGBD.tab` |
| Banjo (gCGCD tuning) [tab] | `instrument.fretted.banjo.gCGCD.tab` |
| Banjo (gDF#AD tuning) [tab] | `instrument.fretted.banjo.gDFAD.tab` |
| Banjo (gDGBD tuning) [tab] | `instrument.fretted.banjo.gDGBD.tab` |
| Banjo (gDGCD tuning) [tab] | `instrument.fretted.banjo.gDGCD.tab` |
| Tenor Banjo [notation] | `instrument.fretted.banjo.tenor.5lines` |
| 7 Global Constants Tenor Banjo [tab] | `instrument.fretted.banjo.tenor.tab` |
| Bordonúa [notation] | `instrument.fretted.bordonua.5lines` |
| Bordonúa [tab] | `instrument.fretted.bordonua.tab` |
| Cavaquinho [notation] | `instrument.fretted.cavaquinho.5lines` |
| Cavaquinho [tab] | `instrument.fretted.cavaquinho.tab` |
| Charango [notation] | `instrument.fretted.charango.5lines` |
| Charango [tab] | `instrument.fretted.charango.tab` |
| Cuatro [notation] | `instrument.fretted.cuatro.5lines` |
| Cuatro, Puerto Rico [tab] | `instrument.fretted.cuatro.puerto-rico.tab` |
| Cuatro, Venezuela [tab] | `instrument.fretted.cuatro.venezuela.tab` |
| Resonator guitar [notation] | `instrument.fretted.guitar.resonator.5lines` |
| Resonator Guitar, A6 tuning [tab] | `instrument.fretted.guitar.resonator.a6.tab` |
| Resonator Guitar, B11 tuning [tab] | `instrument.fretted.guitar.resonator.b11.tab` |
| Resonator Guitar, C#m tuning [tab] | `instrument.fretted.guitar.resonator.c#m.tab` |
| Resonator Guitar, C6+A7 tuning [tab] | `instrument.fretted.guitar.resonator.c6-a7.tab` |
| Resonator Guitar, C6 + high G tuning [tab] | `instrument.fretted.guitar.resonator.c6-highg.tab` |
| Resonator Guitar, standard tuning [tab] | `instrument.fretted.guitar.resonator.c6.tab` |
| Resonator Guitar, C#m7 tuning [tab] | `instrument.fretted.guitar.resonator.cm7.tab` |
| Resonator Guitar, E13 Hawaiian tuning [tab] | `instrument.fretted.guitar.resonator.e13-hawaiian.tab` |
| Resonator Guitar, E13 Western tuning [tab] | `instrument.fretted.guitar.resonator.e13-western.tab` |
| Resonator Guitar, open A tuning [tab] | `instrument.fretted.guitar.resonator.open.A.tab` |
| Resonator Guitar, open G tuning [tab] | `instrument.fretted.guitar.resonator.open.G.tab` |
| Dulcimer | `instrument.fretted.dulcimer` |
| Dulcimer [notation] | `instrument.fretted.dulcimer.5lines` |
| Dulcimer (DAA tuning) [tab] | `instrument.fretted.dulcimer.daa.tab` |
| Dulcimer (DAD tuning) [tab] | `instrument.fretted.dulcimer.dad.tab` |
| Gamba [notation] | `instrument.fretted.gamba.5lines` |
| Gamba [tab] | `instrument.fretted.gamba.tab` |
| 12-string Acoustic Guitar [notation] | `instrument.fretted.guitar.12-string.5lines` |
| 12-string Acoustic Guitar, DADGAD tuning [tab] | `instrument.fretted.guitar.12-string.dadgad.tab` |
| 12-string Acoustic Guitar, double D tuning [tab] | `instrument.fretted.guitar.12-string.double-d.tab` |
| 12-string Acoustic Guitar, dropped D tuning [tab] | `instrument.fretted.guitar.12-string.dropped-d.tab` |
| 12-string Acoustic Guitar, open D tuning [tab] | `instrument.fretted.guitar.12-string.open-d.tab` |
| 12-string Acoustic Guitar, open E tuning [tab] | `instrument.fretted.guitar.12-string.open-e.tab` |
| 12-string Acoustic Guitar, open G tuning [tab] | `instrument.fretted.guitar.12-string.open-g.tab` |
| 12-string Acoustic Guitar, standard tuning (no rhythms) [tab] | `instrument.fretted.guitar.12-string.tab` |
| 7 Global Constants 12-string Acoustic Guitar, standard tuning [tab] | `instrument.fretted.guitar.12-string.tab.rhythms` |
| Acoustic Guitar [notation] | `instrument.fretted.guitar.acoustic.5lines` |
| Acoustic Guitar, DADGAD tuning [tab] | `instrument.fretted.guitar.acoustic.dadgad.tab` |
| Acoustic Guitar, double D tuning [tab] | `instrument.fretted.guitar.acoustic.double-d.tab` |
| Acoustic Guitar, dropped D tuning [tab] | `instrument.fretted.guitar.acoustic.dropped-d.tab` |
| Acoustic Guitar, modal D tuning [tab] | `instrument.fretted.guitar.acoustic.modal-d.tab` |
| Acoustic Guitar, Nashville tuning [tab] | `instrument.fretted.guitar.acoustic.nashville.tab` |
| Acoustic Guitar, open A tuning [tab] | `instrument.fretted.guitar.acoustic.open-a.tab` |
| Acoustic Guitar, open C tuning [tab] | `instrument.fretted.guitar.acoustic.open-c.tab` |
| Acoustic Guitar, open D tuning [tab] | `instrument.fretted.guitar.acoustic.open-d.tab` |
| Acoustic Guitar, open Dm cross-note tuning [tab] | `instrument.fretted.guitar.acoustic.open-dm.tab` |
| Acoustic Guitar, open E tuning [tab] | `instrument.fretted.guitar.acoustic.open-e.tab` |
| Acoustic Guitar, open G tuning [tab] | `instrument.fretted.guitar.acoustic.open-g.tab` |
| Acoustic Guitar, standard tuning (no rhythms) [tab] | `instrument.fretted.guitar.acoustic.tab` |
| Acoustic Guitar, standard tuning [tab] | `instrument.fretted.guitar.acoustic.tab.rhythms` |
| 4-string Bass Guitar [notation] | `instrument.fretted.guitar.bass.4-string.5lines` |
| 4-string Bass Guitar [tab] | `instrument.fretted.guitar.bass.4-string.tab` |
| 5-string Bass Guitar [notation] | `instrument.fretted.guitar.bass.5-string.5lines` |
| 5-string Bass Guitar [tab] | `instrument.fretted.guitar.bass.5-string.tab` |
| Bass Guitar [notation] | `instrument.fretted.guitar.bass.5lines` |
| 6-string Bass Guitar [notation] | `instrument.fretted.guitar.bass.6-string.5lines` |
| 6-string Bass Guitar [tab] | `instrument.fretted.guitar.bass.6-string.tab` |
| Acoustic Bass [notation] | `instrument.fretted.guitar.bass.acoustic.5lines` |
| Acoustic Bass [tab] | `instrument.fretted.guitar.bass.acoustic.tab` |
| 5-string Electric Bass [notation] | `instrument.fretted.guitar.bass.electric.5-string.5lines` |
| 5-string Electric Bass [tab] | `instrument.fretted.guitar.bass.electric.5-string.tab` |
| Electric Bass [notation] | `instrument.fretted.guitar.bass.electric.5lines` |
| 6-string Electric Bass [notation] | `instrument.fretted.guitar.bass.electric.6-string.5lines` |
| 6-string Electric Bass [tab] | `instrument.fretted.guitar.bass.electric.6-string.tab` |
| 5-string Fretless Electric Bass | `instrument.fretted.guitar.bass.electric.fretless.5-string.5lines` |
| 5-string Fretless Electric Bass [tab] | `instrument.fretted.guitar.bass.electric.fretless.5-string.tab` |
| Fretless Electric Bass [notation] | `instrument.fretted.guitar.bass.electric.fretless.5lines` |
| 6-string Fretless Electric Bass | `instrument.fretted.guitar.bass.electric.fretless.6-string.5lines` |
| 6-string Fretless Electric Bass [tab] | `instrument.fretted.guitar.bass.electric.fretless.6-string.tab` |
| Fretless Electric Bass [tab] | `instrument.fretted.guitar.bass.electric.fretless.tab` |
| Electric Bass [tab] | `instrument.fretted.guitar.bass.electric.tab` |
| 7 Global Constants 5-string Fretless Bass Guitar [notation] | `instrument.fretted.guitar.bass.fretless.5-string.5lines` |
| 5-string Fretless Bass Guitar [tab] | `instrument.fretted.guitar.bass.fretless.5-string.tab` |
| Fretless Bass Guitar [notation] | `instrument.fretted.guitar.bass.fretless.5lines` |
| 6-string Fretless Bass Guitar [notation] | `instrument.fretted.guitar.bass.fretless.6-string.5lines` |
| 6-string Fretless Bass Guitar [tab] | `instrument.fretted.guitar.bass.fretless.6-string.tab` |
| Fretless Bass Guitar [tab] | `instrument.fretted.guitar.bass.fretless.tab` |
| Semi-Acoustic Bass [notation] | `instrument.fretted.guitar.bass.semi-acoustic.5lines` |
| Semi-Acoustic Bass [tab] | `instrument.fretted.guitar.bass.semi-acoustic.tab` |
| Bass Guitar [tab] | `instrument.fretted.guitar.bass.tab` |
| Bass Guitar [tab, with rhythms] | `instrument.fretted.guitar.bass.tab.rhythms` |
| Classical Guitar [notation] | `instrument.fretted.guitar.classical.5lines` |
| Classical Guitar, DADGAD tuning [tab] | `instrument.fretted.guitar.classical.dadgad.tab` |
| Classical Guitar, double D tuning [tab] | `instrument.fretted.guitar.classical.double-d.tab` |
| Classical Guitar, dropped D tuning [tab] | `instrument.fretted.guitar.classical.dropped-d.tab` |
| Classical Guitar, open D tuning [tab] | `instrument.fretted.guitar.classical.open-d.tab` |
| Classical Guitar, open E tuning [tab] | `instrument.fretted.guitar.classical.open-e.tab` |
| Classical Guitar, open G tuning [tab] | `instrument.fretted.guitar.classical.open-g.tab` |
| Classical Guitar, standard tuning (no rhythms) [tab] | `instrument.fretted.guitar.classical.tab` |
| Classical Guitar, standard tuning [tab] | `instrument.fretted.guitar.classical.tab.rhythms` |
| Electric Guitar [notation] | `instrument.fretted.guitar.electric.5lines` |
| 7-string Electric Guitar, low A tuning [tab] | `instrument.fretted.guitar.electric.7-string.low-a.tab` |
| 7-string Electric Guitar, low B tuning [tab] | `instrument.fretted.guitar.electric.7-string.tab` |
| Electric Guitar, DADGAD tuning [tab] | `instrument.fretted.guitar.electric.dadgad.tab` |
| Electric Guitar, double D tuning [tab] | `instrument.fretted.guitar.electric.double-d.tab` |
| Electric Guitar, dropped D tuning [tab] | `instrument.fretted.guitar.electric.dropped-d.tab` |
| Electric Guitar, open D tuning [tab] | `instrument.fretted.guitar.electric.open-d.tab` |
| Electric Guitar, open E tuning [tab] | `instrument.fretted.guitar.electric.open-e.tab` |
| Electric Guitar, open G tuning [tab] | `instrument.fretted.guitar.electric.open-g.tab` |
| Electric Guitar, standard tuning (no rhythms) [tab] | `instrument.fretted.guitar.electric.tab` |
| Electric Guitar, standard tuning [tab] | `instrument.fretted.guitar.electric.tab.rhythms` |
| Kora | `instrument.fretted.guitar.kora` |
| Semi-acoustic Guitar [notation] | `instrument.fretted.guitar.semi-acoustic.5lines` |
| Semi-acoustic Guitar, DADGAD tuning [tab] | `instrument.fretted.guitar.semi-acoustic.dadgad.tab` |
| Semi-acoustic Guitar, double D tuning [tab] | `instrument.fretted.guitar.semi-acoustic.double-d.tab` |
| Semi-acoustic Guitar, dropped D tuning [tab] | `instrument.fretted.guitar.semi-acoustic.dropped-d.tab` |
| Semi-acoustic Guitar, open D tuning [tab] | `instrument.fretted.guitar.semi-acoustic.open-d.tab` |
| 7 Global Constants Semi-acoustic Guitar, open E tuning [tab] | `instrument.fretted.guitar.semi-acoustic.open-e.tab` |
| Semi-acoustic Guitar, open G tuning [tab] | `instrument.fretted.guitar.semi-acoustic.open-g.tab` |
| Semi-acoustic Guitar, standard tuning (no rhythms) [tab] | `instrument.fretted.guitar.semi-acoustic.tab` |
| Semi-acoustic Guitar, standard tuning [tab] | `instrument.fretted.guitar.semi-acoustic.tab.rhythms` |
| 10-string Hawaiian Steel Guitar [tab] | `instrument.fretted.guitar.steel.hawaiian.10-string.tab` |
| Hawaiian Steel Guitar [notation] | `instrument.fretted.guitar.steel.hawaiian.5lines` |
| 6-string Hawaiian Steel Guitar, standard tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-string.tab` |
| 6-string Hawaiian Steel Guitar, alternate tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-` |
| string.tab.alternative 6-string Hawaiian Steel Guitar, slack key Bb Mauna Loa tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-` |
| string.tab.bflat.mauna.loa 6-string Hawaiian Steel Guitar, slack key C Mauna Loa tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-` |
| string.tab.c.mauna.loa 6-string Hawaiian Steel Guitar, slack key Wahine CGDGBD tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-` |
| string.tab.cgdgbd.wahine 6-string Hawaiian Steel Guitar, slack key Wahine CGDGBE tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-` |
| string.tab.cgdgbe.wahine 6-string Hawaiian Steel Guitar, slack key Wahine DGDF#BD tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-` |
| string.tab.dgdfbd.wahine 6-string Hawaiian Steel Guitar, slack key G Mauna Loa tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-` |
| string.tab.g.mauna.loa 6-string Hawaiian Steel Guitar, slack key G Taro Patch tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-` |
| string.tab.g.taro.patch 6-string Hawaiian Steel Guitar, slack key Wahine GCDGBE tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.6-` |
| string.tab.gcdgbe.wahine 8-string Hawaiian Steel Guitar [tab] | `instrument.fretted.guitar.steel.hawaiian.8-string.tab` |
| 8-string Hawaiian Steel Guitar, alternate tuning [tab] | `instrument.fretted.guitar.steel.hawaiian.8-` |
| string.tab.alternative Hawaiian Steel Guitar [tab] | `instrument.fretted.guitar.steel.hawaiian.tab` |
| Pedal Steel Guitar [notation] | `instrument.fretted.guitar.steel.pedal.5lines` |
| Pedal Steel Guitar [tab] | `instrument.fretted.guitar.steel.pedal.tab` |
| Guitarra [notation] | `instrument.fretted.guitarra.5lines` |
| Guitarra, Coimbra [tab] | `instrument.fretted.guitarra.coimbra.tab` |
| Guitarra, Lisboa [tab] | `instrument.fretted.guitarra.lisboa.tab` |
| Guitarra, Portuguesa [tab] | `instrument.fretted.guitarra.portuguesa.tab` |
| Guitarrón [notation] | `instrument.fretted.guitarron.5lines` |
| Guitarrón [tab] | `instrument.fretted.guitarron.tab` |
| Laúd [notation] | `instrument.fretted.laud.5lines` |
| 7 Global Constants Laúd [tab] | `instrument.fretted.laud.tab` |
| Tenor Lute [notation] | `instrument.fretted.lute.5lines` |
| Bass Lute [notation] | `instrument.fretted.lute.bass-d.french.english.5lines` |
| Bass Lute, D tuning, French/English [tab] | `instrument.fretted.lute.bass-d.french.english.tab` |
| Bass Lute, D tuning, Italian [tab] | `instrument.fretted.lute.bass-d.italian.tab` |
| Bass Lute, D tuning, Spanish [tab] | `instrument.fretted.lute.bass-d.spanish.tab` |
| Tenor Lute, G tuning, Italian [tab] | `instrument.fretted.lute.italian.tab` |
| Tenor Lute, G tuning, Spanish [tab] | `instrument.fretted.lute.spanish.tab` |
| Tenor Lute, G tuning, French/English [tab] | `instrument.fretted.lute.tab` |
| Tenor Lute, A tuning, French/English [tab] | `instrument.fretted.lute.tenor-a.french.english.tab` |
| Tenor Lute, A tuning, Italian [tab] | `instrument.fretted.lute.tenor-a.italian.tab` |
| Tenor Lute, A tuning, Spanish [tab] | `instrument.fretted.lute.tenor-a.spanish.tab` |
| Treble Lute [notation] | `instrument.fretted.lute.treble-d.french.english.5lines` |
| Treble Lute, D tuning, French/English [tab] | `instrument.fretted.lute.treble-d.french.english.tab` |
| Treble Lute, D tuning, Italian [tab] | `instrument.fretted.lute.treble-d.italian.tab` |
| Treble Lute, D tuning, Spanish [tab] | `instrument.fretted.lute.treble-d.spanish.tab` |
| Mandolin [notation] | `instrument.fretted.mandolin.5lines` |
| Mandolin [tab] | `instrument.fretted.mandolin.tab` |
| Oud [notation] | `instrument.fretted.oud.5lines` |
| Oud [tab] | `instrument.fretted.oud.tab` |
| Qanoon | `instrument.fretted.qanoon.5lines` |
| Requinto [notation] | `instrument.fretted.requinto.5lines` |
| Requinto [tab] | `instrument.fretted.requinto.tab` |
| Santoor | `instrument.fretted.santoor.5lines` |
| Sitar [notation] | `instrument.fretted.sitar.5lines` |
| Sitar (Ravi Shankar) [tab] | `instrument.fretted.sitar.ravi-shankkar.tab` |
| Sitar (Vilayat Khan) [tab] | `instrument.fretted.sitar.vilayat-khan.tab` |
| Tambura (Female) [notation] | `instrument.fretted.tambura.female` |
| Tambura (Male) [notation] | `instrument.fretted.tambura.male` |
| Tiple [notation] | `instrument.fretted.tiple.5lines` |
| Tiple, Argentina [tab] | `instrument.fretted.tiple.argentina.tab` |
| Tiple, Colombia ADF#B tuning [tab] | `instrument.fretted.tiple.colombia.tab.adfb` |
| Tiple, Colombia DGBE tuning [tab] | `instrument.fretted.tiple.colombia.tab.dgbe` |
| Tiple, Cuba [tab] | `instrument.fretted.tiple.cuba.tab` |
| Tiple, Peru [tab] | `instrument.fretted.tiple.peru.tab` |
| Tiple, Santo Domingo [tab] | `instrument.fretted.tiple.santo.domingo.tab` |
| 7 Global Constants Tiple, Uruguay [tab] | `instrument.fretted.tiple.uruguay.tab` |
| Tres [notation] | `instrument.fretted.tres.5lines` |
| Tres, GCE tuning [tab] | `instrument.fretted.tres.tab` |
| Tres, ADF# tuning [tab] | `instrument.fretted.tres.tab.adf` |
| Tres, GBE tuning [tab] | `instrument.fretted.tres.tab.gbe` |
| Ukulele [notation] | `instrument.fretted.ukulele.5lines` |
| Ukulele [tab] | `instrument.fretted.ukulele.tab` |
| Vihuela [notation] | `instrument.fretted.vihuela.5lines` |
| Vihuela [tab] | `instrument.fretted.vihuela.tab` |
| Zither | `instrument.fretted.zither` |
| Keyboard | `instrument.keyboard` |
| Accordion | `instrument.keyboard.accordion` |
| Bandoneon | `instrument.keyboard.bandoneon` |
| Celesta | `instrument.keyboard.celesta` |
| Clavichord | `instrument.keyboard.clavichord` |
| Harmonium | `instrument.keyboard.harmonium` |
| Harpsichord | `instrument.keyboard.harpsichord` |
| Keyboards | `instrument.keyboard.keyboards` |
| Tape Sampler Keyboard [Brass] instrument.keyboard.tape sampler.brass Tape Sampler Keyboard [Choir] instrument.keyboard.tape sampler.choir Tape Sampler Keyboard [Flute] instrument.keyboard.tape sampler.flute Tape Sampler Keyboard [Strings] instrument.keyboard.tape sampler Melodeon | `instrument.keyboard.melodeon` |
| Electric Organ | `instrument.keyboard.organ.electric` |
| Organ [manuals] | `instrument.keyboard.organ.manuals` |
| Manual [solo organ manuals] | `instrument.keyboard.organ.manuals.solo` |
| Ped. [Organ pedals] | `instrument.keyboard.organ.pedals` |
| Pedal [solo organ pedals] | `instrument.keyboard.organ.pedals.solo` |
| Piano | `instrument.keyboard.piano` |
| Electric Piano | `instrument.keyboard.piano.electric` |
| Electric Clavichord | `instrument.keyboard.piano.electric.clavichord` |
| Electric Stage Piano | `instrument.keyboard.piano.electric.stage` |
| Overdriven Electric Piano | `instrument.keyboard.piano.electric.overdriven` |
| Honky-tonk Piano | `instrument.keyboard.piano.honky-tonk` |
| Synthesizer | `instrument.keyboard.synthesizer` |
| Unnamed (2 lines) | `instrument.other.2lines` |
| 7 Global Constants Unnamed (3 lines) | `instrument.other.3lines` |
| Unnamed (4 lines) | `instrument.other.4lines` |
| Unnamed (bass staff) | `instrument.other.bassclef` |
| No instrument (barlines shown) | `instrument.other.none.barlines` |
| No instrument (bar rests shown) | `instrument.other.none.barrests` |
| No instrument (hidden) | `instrument.other.none.hidden` |
| Solo | `instrument.other.solo.real` |
| Unnamed (treble staff) | `instrument.other.trebleclef` |
| Almglocken | `instrument.pitchedpercussion.almglocken` |
| Antique Cymbals | `instrument.pitchedpercussion.antiquecymbals` |
| Chimes | `instrument.pitchedpercussion.bells.chimes` |
| Chimes [no key] | `instrument.pitchedpercussion.bells.chimes.nokeysig` |
| Bell lyre [marching band] | `instrument.pitchedpercussion.bells.marching` |
| Orchestral Bells | `instrument.pitchedpercussion.bells.orchestral` |
| Tubular Bells | `instrument.pitchedpercussion.bells.tubular` |
| Cimbalom | `instrument.pitchedpercussion.cimbalom` |
| Crotales | `instrument.pitchedpercussion.crotales` |
| Steel Drums | `instrument.pitchedpercussion.drums.steel` |
| Steel Drums [bass clef, treble transp.] | `instrument.pitchedpercussion.drums.steel.bassclef` |
| Gamelan Kengong | `instrument.pitchedpercussion.gamelan.kengong` |
| Gamelan Slentam | `instrument.pitchedpercussion.gamelan.slentam` |
| Glockenspiel | `instrument.pitchedpercussion.glockenspiel` |
| Alto Glockenspiel | `instrument.pitchedpercussion.glockenspiel.alto` |
| Soprano Glockenspiel | `instrument.pitchedpercussion.glockenspiel.soprano` |
| Handbells | `instrument.pitchedpercussion.handbells` |
| Harp | `instrument.pitchedpercussion.harp` |
| Lever Harp | `instrument.pitchedpercussion.harp.lever` |
| Kalimba | `instrument.pitchedpercussion.kalimba` |
| Marimba [grand staff] | `instrument.pitchedpercussion.marimba` |
| Marimba [treble staff] | `instrument.pitchedpercussion.marimba.trebleclef` |
| Alto Metallophone | `instrument.pitchedpercussion.metallophone.alto` |
| Bass Metallophone | `instrument.pitchedpercussion.metallophone.bass` |
| Soprano Metallophone | `instrument.pitchedpercussion.metallophone.soprano` |
| Roto-toms | `instrument.pitchedpercussion.roto-toms` |
| Temple Blocks | `instrument.pitchedpercussion.templeblocks` |
| Timpani [with key] | `instrument.pitchedpercussion.timpani` |
| 7 Global Constants Timpani [no key] | `instrument.pitchedpercussion.timpani.nokeysig` |
| Vibraphone | `instrument.pitchedpercussion.vibraphone` |
| Wood Blocks [5 lines] | `instrument.pitchedpercussion.woodblocks` |
| Xylophone | `instrument.pitchedpercussion.xylophone` |
| Alto Xylophone | `instrument.pitchedpercussion.xylophone.alto` |
| Bass Xylophone | `instrument.pitchedpercussion.xylophone.bass` |
| Contra Bass Bar | `instrument.pitchedpercussion.xylophone.contrabass.bar` |
| Gyil | `instrument.pitchedpercussion.xylophone.gyil` |
| Soprano Xylophone | `instrument.pitchedpercussion.xylophone.soprano` |
| Xylorimba | `instrument.pitchedpercussion.xylorimba` |
| Alto | `instrument.singers.alto` |
| Solo Alto | `instrument.singers.alto.solo` |
| Altus | `instrument.singers.altus` |
| Baritone | `instrument.singers.baritone` |
| Solo Baritone | `instrument.singers.baritone.solo` |
| Bass | `instrument.singers.bass` |
| Solo Bass | `instrument.singers.bass.solo` |
| Bassus | `instrument.singers.bassus` |
| Cantus | `instrument.singers.cantus` |
| Choir | `instrument.singers.choir` |
| Contralto | `instrument.singers.contralto` |
| Countertenor | `instrument.singers.counter-tenor` |
| Mean | `instrument.singers.mean` |
| Mezzo-soprano | `instrument.singers.mezzo-soprano` |
| Quintus | `instrument.singers.quintus` |
| Secundus | `instrument.singers.secundus` |
| Soprano | `instrument.singers.soprano` |
| Solo Soprano | `instrument.singers.soprano.solo` |
| Tenor | `instrument.singers.tenor` |
| Solo Tenor | `instrument.singers.tenor.solo` |
| Treble | `instrument.singers.treble` |
| Solo Treble | `instrument.singers.treble.solo` |
| Voice | `instrument.singers.voice` |
| Voice [male] | `instrument.singers.voice.male` |
| Contrabass | `instrument.strings.contrabass` |
| Bass [Double] | `instrument.strings.contrabass.bass` |
| 7 Global Constants Double Bass | `instrument.strings.contrabass.double-bass` |
| Solo Contrabass | `instrument.strings.contrabass.solo` |
| String Bass | `instrument.strings.contrabass.string` |
| Upright Bass | `instrument.strings.contrabass.upright` |
| Hurdy-gurdy | `instrument.strings.hurdy-gurdy` |
| Sarangi | `instrument.strings.sarangi` |
| Strings | `instrument.strings.section` |
| Strings [reduction] | `instrument.strings.section.reduction` |
| Bass Viol | `instrument.strings.viol.bass` |
| Tenor Viol | `instrument.strings.viol.tenor` |
| Treble Viol | `instrument.strings.viol.treble` |
| Viola | `instrument.strings.viola` |
| Solo Viola | `instrument.strings.viola.solo` |
| Violin 1 | `instrument.strings.violin.1` |
| Violin 2 | `instrument.strings.violin.2` |
| Violin I | `instrument.strings.violin.I` |
| Violin II | `instrument.strings.violin.ii` |
| Solo Violin | `instrument.strings.violin.solo` |
| Violoncello | `instrument.strings.violoncello` |
| Solo Violoncello | `instrument.strings.violoncello.solo` |
| Anvil | `instrument.unpitched.anvil` |
| Cha-cha bell [1 line] | `instrument.unpitched.bells.cha-cha` |
| Mambo bell [1 line] | `instrument.unpitched.bells.mambo` |
| Sleigh Bells | `instrument.unpitched.bells.sleigh` |
| Brake Drum [1 line] | `instrument.unpitched.brake-drum.1line` |
| Cabasa [1 line] | `instrument.unpitched.cabasa` |
| Cabasa [2 lines] | `instrument.unpitched.cabasa.2lines` |
| Castanets | `instrument.unpitched.castanets` |
| Shaker, Caxixi [1 line] | `instrument.unpitched.caxixi.1line` |
| Claves [1 line] | `instrument.unpitched.claves` |
| Shaker, Cocoa Bean Rattle [1 line] instrument.unpitched.cocoa bean.1line Finger Cymbals [1 line] | `instrument.unpitched.cymbals.finger.1line` |
| Percussion [1 line] | `instrument.unpitched.drums.1line` |
| Percussion [2 lines] | `instrument.unpitched.drums.2lines` |
| Berimbau | `instrument.unpitched.drums.2lines.berimbau` |
| Percussion [3 lines] | `instrument.unpitched.drums.3lines` |
| 7 Global Constants Percussion [4 lines] | `instrument.unpitched.drums.4lines` |
| Percussion [5 lines] | `instrument.unpitched.drums.5lines` |
| Agogos [2 lines] | `instrument.unpitched.drums.agogos` |
| Bass Drum | `instrument.unpitched.drums.bass` |
| Bass Drum [5 lines] | `instrument.unpitched.drums.bass.5lines` |
| Marching Bass Drum [3 lines] | `instrument.unpitched.drums.bass.marching.3lines` |
| Marching Bass Drum [5 lines] | `instrument.unpitched.drums.bass.marching.5lines` |
| Itótele [Batá Drum] | `instrument.unpitched.drums.bata.itotele` |
| Iyá [Batá Drum] | `instrument.unpitched.drums.bata.iya` |
| Okónkolo [Batá Drum] | `instrument.unpitched.drums.bata.okonkolo` |
| Bongos [2 lines] | `instrument.unpitched.drums.bongos` |
| Bongo Bell [High] | `instrument.unpitched.drums.bongos.bell.high` |
| Bongo Bell [Low] | `instrument.unpitched.drums.bongos.bell.low` |
| Box | `instrument.unpitched.drums.box.3lines` |
| Cajon [2 lines] | `instrument.unpitched.drums.cajon` |
| Congas [2 lines] | `instrument.unpitched.drums.congas` |
| Congas [1 line] | `instrument.unpitched.drums.congas.1line` |
| Congas [3 lines] | `instrument.unpitched.drums.congas.3lines` |
| Congas [4 lines] | `instrument.unpitched.drums.congas.4lines` |
| Cuíca [3 lines] | `instrument.unpitched.drums.cuica.3lines` |
| Cymbals | `instrument.unpitched.drums.cymbal` |
| Marching Cymbals [5 lines] | `instrument.unpitched.drums.cymbals.marching.5lines` |
| Djembe [3 lines] | `instrument.unpitched.drums.djembe.3lines` |
| Drum Set (Rock) | `instrument.unpitched.drums.drumset` |
| Drum Set (Alternative) | `instrument.unpitched.drums.drumset.alternative` |
| Drum Set (Brushes) | `instrument.unpitched.drums.drumset.brushes` |
| Drum Set (Dance) | `instrument.unpitched.drums.drumset.dance` |
| Drum Set (Disco) | `instrument.unpitched.drums.drumset.disco` |
| Drum Set (Electronica) | `instrument.unpitched.drums.drumset.electronic` |
| Drum Set (Fusion) | `instrument.unpitched.drums.drumset.fusion` |
| Drum Set (Garage) | `instrument.unpitched.drums.drumset.garage` |
| Drum Set (Hip-hop) | `instrument.unpitched.drums.drumset.hip-hop` |
| Drum Set (Industrial) | `instrument.unpitched.drums.drumset.industrial` |
| Drum Set (Jazz) | `instrument.unpitched.drums.drumset.jazz` |
| Drum Set (Lo-Fi) | `instrument.unpitched.drums.drumset.lo-fi` |
| Drum Set (Metal) | `instrument.unpitched.drums.drumset.metal` |
| 7 Global Constants Drum Set (Motown) | `instrument.unpitched.drums.drumset.motown` |
| Drum Set (New Age) instrument.unpitched.drums.drumset.new age Drum Set (Pop) | `instrument.unpitched.drums.drumset.pop` |
| Drum Set (Reggae) | `instrument.unpitched.drums.drumset.reggae` |
| Drum Set (Stadium Rock) | `instrument.unpitched.drums.drumset.rock.stadium` |
| Drum Set (Rods) | `instrument.unpitched.drums.drumset.rods` |
| Drum Set (Drum Machine) | `instrument.unpitched.drums.drumset.tr-808` |
| Dumbek [3 lines] | `instrument.unpitched.drums.dumbek.3lines` |
| Kidi [Ewe Drum] | `instrument.unpitched.drums.ewe.kidi` |
| Sogo [Ewe Drum] | `instrument.unpitched.drums.ewe.sogo` |
| Gankokwe (Bell) | `instrument.unpitched.drums.gankokwe` |
| Jam Blocks [2 lines] | `instrument.unpitched.drums.jamblocks` |
| Jawbone [1 line] | `instrument.unpitched.drums.jawbone.1line` |
| Pandeiro [2 lines] | `instrument.unpitched.drums.pandeiro` |
| Rain Stick (High) [1 line] | `instrument.unpitched.drums.rainstick.high.1line` |
| Rain Stick (Low) [1 line] | `instrument.unpitched.drums.rainstick.low.1line` |
| Egg Shaker (High) [1 line] | `instrument.unpitched.drums.shaker.high.1line` |
| Egg Shaker (Low) [1 line] | `instrument.unpitched.drums.shaker.low.1line` |
| Egg Shaker (Medium) [1 line] | `instrument.unpitched.drums.shaker.medium.1line` |
| Side Drum | `instrument.unpitched.drums.side` |
| Snare Drum | `instrument.unpitched.drums.snare` |
| Marching Snare Drums [5 lines] | `instrument.unpitched.drums.snare.5lines` |
| Surdo [2 lines] | `instrument.unpitched.drums.surdo` |
| Tabla | `instrument.unpitched.drums.table` |
| Taiko Drum | `instrument.unpitched.drums.taiko` |
| Tenor Drum | `instrument.unpitched.drums.tenor` |
| Marching Tenor Drums [5 lines] | `instrument.unpitched.drums.tenor.marching` |
| Quads [5 lines] | `instrument.unpitched.drums.tenor.marching.quads` |
| Tom-toms [5 lines] | `instrument.unpitched.drums.tom-toms` |
| Tom-toms [4 lines] | `instrument.unpitched.drums.tom-toms.4lines` |
| Udu | `instrument.unpitched.drums.udu` |
| Shaker, Egg Shaker [1 line] instrument.unpitched.egg shaker.1line Finger Click [1 line] | `instrument.unpitched.fingerclick` |
| Gamelan Gong Ageng (High) [1 line] | `instrument.unpitched.gamelan.gong-ageng.high` |
| Gamelan Gong Ageng (Low) [1 line] | `instrument.unpitched.gamelan.gong-ageng.low` |
| Gamelan Kempyang and Ketuk [2 lines] | `instrument.unpitched.gamelan.kempyang-ketuk` |
| 7 Global Constants Gamelan Khendang Ageng [1 line] | `instrument.unpitched.gamelan.khendang-ageng` |
| Gamelan Khendang Ciblon [1 line] | `instrument.unpitched.gamelan.khendang-ciblon` |
| Large Gong [1 line] | `instrument.unpitched.gong.large.1line` |
| Medium Gong [1 line] | `instrument.unpitched.gong.medium.1line` |
| Gourd [1 line] | `instrument.unpitched.gourd` |
| Guira [1 line] | `instrument.unpitched.guira` |
| Guiro (High) [1 line] | `instrument.unpitched.guiro.high` |
| Guiro (Medium) [1 line] | `instrument.unpitched.guiro.medium` |
| Handclap [1 line] | `instrument.unpitched.handclap` |
| Shaker, Kayamba [1 line] | `instrument.unpitched.kayamba.1line` |
| Maracas | `instrument.unpitched.maracas` |
| Shaker, Gourd Maracas [1 line] | `instrument.unpitched.maracas.gourd.1line` |
| Maracas [High] | `instrument.unpitched.maracas.high` |
| Maracas [Medium] | `instrument.unpitched.maracas.medium` |
| Mark tree [1 line] | `instrument.unpitched.marktree` |
| Shaker, Nsak Rattle [1 line] | `instrument.unpitched.nsak.1line` |
| Finger Snaps | `instrument.unpitched.orff.fingersnaps` |
| Hand Claps | `instrument.unpitched.orff.handclaps` |
| Patsch | `instrument.unpitched.orff.patsch` |
| Stamp | `instrument.unpitched.orff.stamp` |
| Salsa bell [1 line] | `instrument.unpitched.salsa.bell` |
| Shaker [1 line] | `instrument.unpitched.shaker` |
| Shaker, Shekere [1 line] | `instrument.unpitched.shekere.1line` |
| Tam-tam | `instrument.unpitched.tam-tam` |
| Tambourine | `instrument.unpitched.tambourine` |
| Timbales [2 lines] | `instrument.unpitched.timbales.2lines` |
| Timbales [5 lines] | `instrument.unpitched.timbales.5lines` |
| Triangle | `instrument.unpitched.triangle` |
| Shaker, Wasembe Rattle (High) [1 line] | `instrument.unpitched.wasembe.high.1line` |
| Shaker, Wasembe Rattle (Low) [1 line] | `instrument.unpitched.wasembe.low.1line` |
| Shaker, Wasembe Rattle (Medium) [1 line] | `instrument.unpitched.wasembe.medium.1line` |
| Whip | `instrument.unpitched.whip` |
| Whistle | `instrument.unpitched.whistle` |
| Wind Chimes [1 line] | `instrument.unpitched.wind-chimes.1line` |
| Wood Block [1 line] | `instrument.unpitched.woodblock.1line` |
| Bagpipes | `instrument.wind.bagpipe` |
| 7 Global Constants Basset Horn | `instrument.wind.basset-horn` |
| Bassoon | `instrument.wind.bassoon` |
| Contrabassoon | `instrument.wind.bassoon.contrabassoon` |
| Quart Bassoon | `instrument.wind.bassoon.quart` |
| Quint Bassoon | `instrument.wind.bassoon.quint` |
| Clarinet in A | `instrument.wind.clarinet.a` |
| Clarinet in Ab | `instrument.wind.clarinet.aflat` |
| Alto Clarinet in Eb | `instrument.wind.clarinet.alto.eflat` |
| Alto Clarinet in Eb [bass clef, treble transp.] | `instrument.wind.clarinet.alto.eflat.bassclef` |
| Bass Clarinet in Bb | `instrument.wind.clarinet.bass.bflat` |
| Bass Clarinet in Bb [score sounds 8vb] | `instrument.wind.clarinet.bass.bflat.8vb-score` |
| Bass Clarinet in Bb [bass clef, treble transp.] | `instrument.wind.clarinet.bass.bflat.bassclef` |
| Clarinet in Bb | `instrument.wind.clarinet.bflat` |
| Clarinet in C | `instrument.wind.clarinet.c` |
| Contra Alto Clarinet in Eb | `instrument.wind.clarinet.contra.alto.eflat` |
| Contra Alto Clarinet in Eb [score sounds 8vb] | `instrument.wind.clarinet.contra.alto.eflat.8vb-score` |
| Contra Alto Clarinet in Eb [bass clef, treble transp.] | `instrument.wind.clarinet.contra.alto.eflat.bassclef` |
| Contrabass Clarinet in Bb | `instrument.wind.clarinet.contrabass.bflat` |
| Contrabass Clarinet in Bb [score sounds 15mb] | `instrument.wind.clarinet.contrabass.bflat.15mb-score` |
| Contrabass Clarinet in Bb [bass clef, treble transp.] | `instrument.wind.clarinet.contrabass.bflat.bassclef` |
| Clarinet in D | `instrument.wind.clarinet.d` |
| Clarinet in Eb | `instrument.wind.clarinet.eflat` |
| Clarinet in G | `instrument.wind.clarinet.g` |
| Cor Anglais | `instrument.wind.coranglais` |
| Didgeridoo | `instrument.wind.didgeridoo` |
| Duduk | `instrument.wind.duduk` |
| English Horn | `instrument.wind.englishhorn` |
| Flageolet | `instrument.wind.flageolet` |
| Flute | `instrument.wind.flute` |
| Alto Flute | `instrument.wind.flute.alto` |
| Bansuri | `instrument.wind.flute.bansuri` |
| Bass Flute | `instrument.wind.flute.bass` |
| Eb Flute | `instrument.wind.flute.eflat` |
| G Flute | `instrument.wind.flute.g` |
| Harmonica | `instrument.wind.harmonica` |
| Heckelphone | `instrument.wind.heckelphone` |
| 7 Global Constants Mey | `instrument.wind.mey` |
| Nai | `instrument.wind.nai` |
| Oboe | `instrument.wind.oboe` |
| Baritone Oboe | `instrument.wind.oboe.baritone` |
| Bass Oboe | `instrument.wind.oboe.bass` |
| Oboe d'Amore | `instrument.wind.oboe.damore` |
| Ocarina | `instrument.wind.ocarina` |
| Panpipes | `instrument.wind.panpipes` |
| Piccolo | `instrument.wind.piccolo` |
| Military Piccolo in Db | `instrument.wind.piccolo.dflat` |
| Alto Recorder | `instrument.wind.recorder.alto` |
| Bass Recorder | `instrument.wind.recorder.bass` |
| Great Bass Recorder | `instrument.wind.recorder.bass.great` |
| Contrabass Recorder | `instrument.wind.recorder.contrabass` |
| Descant Recorder | `instrument.wind.recorder.descant` |
| Sopranino Recorder | `instrument.wind.recorder.sopranino` |
| Soprano Recorder | `instrument.wind.recorder.soprano` |
| Tenor Recorder | `instrument.wind.recorder.tenor` |
| Treble Recorder | `instrument.wind.recorder.treble` |
| Alto Saxophone | `instrument.wind.saxophone.alto` |
| Baritone Saxophone | `instrument.wind.saxophone.baritone` |
| Baritone Saxophone [score sounds 8vb] | `instrument.wind.saxophone.baritone.8vb-score` |
| Baritone Saxophone [bass clef, treble transp.] | `instrument.wind.saxophone.baritone.bassclef` |
| Bass Saxophone | `instrument.wind.saxophone.bass` |
| Bass Saxophone [score sounds 15mb] | `instrument.wind.saxophone.bass.15mb-score` |
| Bass Saxophone [bass clef, treble transp.] | `instrument.wind.saxophone.bass.bassclef` |
| C Melody Saxophone | `instrument.wind.saxophone.c-melody` |
| Contrabass (Tubax) Saxophone | `instrument.wind.saxophone.contrabass` |
| Contrabass (Tubax) Saxophone [score sounds 15mb] | `instrument.wind.saxophone.contrabass.15mb-score` |
| Contrabass (Tubax) Sax [bass clef, treble transp.] | `instrument.wind.saxophone.contrabass.bassclef` |
| F Mezzo Soprano Saxophone | `instrument.wind.saxophone.mezz-soprano.f` |
| Sopranino Saxophone | `instrument.wind.saxophone.sopranino` |
| Piccolo Saxophone in Bb [Soprillo] | `instrument.wind.saxophone.sopranino.bflat` |
| Soprano Saxophone | `instrument.wind.saxophone.soprano` |
| C Soprano Saxophone | `instrument.wind.saxophone.soprano.c` |
| Subcontrabass (Tubax) Saxophone | `instrument.wind.saxophone.subcontrabass` |
| 7 Global Constants Subcontrabass (Tubax) Saxophone [score sounds 15mb] | `instrument.wind.saxophone.subcontrabass.15mb-score` |
| Subcontrabass (Tubax) Sax [bass clef, treble transp.] | `instrument.wind.saxophone.subcontrabass.bassclef` |
| Tenor Saxophone | `instrument.wind.saxophone.tenor` |
| Tenor Saxophone [score sounds 8vb] | `instrument.wind.saxophone.tenor.8vb-score` |
| Tenor Saxophone [bass clef, treble transp.] | `instrument.wind.saxophone.tenor.bassclef` |
| Woodwind | `instrument.wind.section` |
| Shakuhachi | `instrument.wind.shakuhachi` |
| Tin Whistle | `instrument.wind.whistle.tin` |

## Beam Options

For the `Beam` variable of NoteRest objects.

| Constant | Value |
| --- | --- |
| `NoBeam` | 1 |
| `StartBeam` | 2 |
| `ContinueBeam` | 3 |
| `SingleBeam` | 4 |

## Bracket Types

For the `AddBracket()` method of BracketList objects and the `BracketType` variable of Bracket objects.

| Constant | Value |
| --- | --- |
| `BracketFull` | 0 |
| `BracketBrace` | 1 |
| `BracketSub` | 2 |

## Breaks

Used by the `SetBreakType()` method of Score objects.

| Constant | Value / meaning |
| --- | --- |
| `MiddleOfSystem` | 1 — bar can only appear in the middle of a system, not at the end |
| `EndOfSystem` | 2 — (no menu entry; created by Layout > Lock Format) bar can only appear at the end of a mid-page system |
| `MiddleOfPage` | 3 — bar can appear anywhere except at the end of a page |
| `EndOfPage` | 4 — page break; bar can only appear at the end of a page |
| `NotEndOfSystem` | 5 — (no menu entry) bar can appear anywhere except the end of a mid-page system |
| `EndOfSystemOrPage` | 6 — system break; bar can only appear at the end of a mid-page system or end of a page |
| `Default` | 7 — no break; bar can appear anywhere |
| `SpecialPageBreak` | 8 |

Older names `NoBreak` (= `MiddleOfSystem`), `SystemBreak` (= `EndOfSystem`) and `PageBreak` (= `EndOfPage`) are still supported for old plug-ins but deprecated.

## Accidentals

For the `Accidental` variable of Note objects.

| Constant | Value |
| --- | --- |
| `DoubleSharp` | 2 |
| `Sharp` | 1 |
| `Natural` | 0 |
| `Flat` | -1 |
| `DoubleFlat` | -2 |
| `QuarterSharp` | 0.5 |
| `ThreeQuarterSharp` | 1.5 |
| `QuarterFlat` | -0.5 |
| `ThreeQuarterFlat` | -1.5 |

## Note Style Names

For the `NoteStyle` variable of Note objects; correspond to noteheads in the Notes panel of the Properties window.

| Constant | Value |
| --- | --- |
| `NormalNoteStyle` | 0 |
| `CrossNoteStyle` | 1 |
| `DiamondNoteStyle` | 2 |
| `BeatWithoutStemNoteStyle` | 3 |
| `BeatNoteStyle` | 4 |
| `CrossOrDiamondNoteStyle` | 5 |
| `BlackAndWhiteDiamondNoteStyle` | 6 |
| `HeadlessNoteStyle` | 7 |
| `StemlessNoteStyle` | 8 |
| `SilentNoteStyle` | 9 |
| `CueNoteStyle` | 10 |
| `SlashedNoteStyle` | 11 |
| `BackSlashedNoteStyle` | 12 |
| `ArrowDownNoteStyle` | 13 |
| `ArrowUpNoteStyle` | 14 |
| `InvertedTriangleNoteStyle` | 15 |
| `ShapedNote1NoteStyle` | 16 |
| `ShapedNote2NoteStyle` | 17 |
| `ShapedNote3NoteStyle` | 18 |
| `ShapedNote4StemUpNoteStyle` | 19 |
| `ShapedNote5NoteStyle` | 20 |
| `ShapedNote6NoteStyle` | 21 |
| `ShapedNote7NoteStyle` | 22 |
| `ShapedNote4StemDownNoteStyle` | 23 |

## MuteMode Constants

Possible values of `Stave.MuteMode`.

| Constant | Value |
| --- | --- |
| `Muted` | 0 |
| `HalfMuted` | 1 |
| `NotMuted` | 2 |

## Articulations

Used with `Note.GetArticulation` and `Note.SetArticulation`.

| Constant | Value |
| --- | --- |
| `Custom1Artic` | 0 |
| `StaccatoArtic` | 1 |
| `StaccatissimoArtic` | 2 |
| `WedgeArtic` | 3 |
| `TenutoArtic` | 4 |
| `AccentArtic` | 5 |
| `MarcatoArtic` | 6 |
| `HarmonicArtic` | 7 |
| `PlusArtic` | 8 |
| `UpBowArtic` | 9 |
| `DownBowArtic` | 10 |
| `Custom2Artic` | 11 |
| `SquarePauseArtic` | 12 |
| `PauseArtic` | 13 |
| `TriPauseArtic` | 14 |
| `Custom3Artic` | 15 |

## SyllableTypes for LyricItems

Used in LyricItem.

| Constant | Value |
| --- | --- |
| `MiddleOfWord` | 0 |
| `EndOfWord` | 1 |

## Accidental Styles

As used by `Note.AccidentalStyle`.

| Constant | Value |
| --- | --- |
| `NormalAcc` | "0" |
| `HiddenAcc` | "1" |
| `CautionaryAcc` | "2" |
| `BracketedAcc` | "3" |

## Time Signature Strings

Define the unicode characters used to draw common time and alla breve time signatures, for comparison with `TimeSignature.Text`: `CommonTimeString`, `AllaBreveTimeString`. (The guide shows the glyphs, which do not extract as text.)

## Symbols

Named constants for indices of frequently used symbols, passed to `Bar.AddSymbol`. For other symbols, count along in the Create > Symbol dialog or use `Score.SymbolIndex`; group-start constants below help (e.g. the 8va symbol is `OctaveSymbols + 2`).

### Common Symbol Indices

| Constant | Value |
| --- | --- |
| `SegnoSymbol` | "1" |
| `CodaSymbol` | "2" |
| `RepeatBeatSymbol` | "5" |
| `RepeatBarSymbol` | "6" |
| `RepeatTwoBarsSymbol` | "7" |
| `TrillSymbol` | "32" |
| `BracketedTrillSymbol` | "33" |
| `MordentSymbol` | "36" |
| `InvertedMordentSymbol` | "37" |
| `TurnSymbol` | "38" |
| `InvertedTurnSymbol` | "39" |
| `ReversedTurnSymbol` | "40" |
| `TripleMordentSymbol` | "41" |
| `InvertedTripleMordentSymbol` | "42" |
| `PedalSymbol` | "48" |
| `PedalPSymbol` | "49" |
| `PedalUpSymbol` | "50" |
| `LiftPedalSymbol` | "51" |
| `HeelOneSymbol` | "52" |
| `HeelTwoSymbol` | "53" |
| `ToeOneSymbol` | "54" |
| `ToeTwoSymbol` | "55" |
| `CommaSymbol` | "247" |
| `TickSymbol` | "248" |
| `CaesuraSymbol` | "249" |
| `ThickCaesuraSymbol` | "250" |

### Indices at the Start of Each Group of Symbols

| Constant | Value |
| --- | --- |
| `RepeatSymbols` | "0" |
| `GeneralSymbols` | "16" |
| `OrnamentSymbols` | "32" |
| `KeyboardSymbols` | "48" |
| `ChromaticPercussionSymbols` | "64" |
| `DrumPercussionSymbols` | "80" |
| `MetallicPercussionSymbols` | "96" |
| `OtherPercussionSymbols` | "112" |
| `BeaterPercussionSymbols` | "128" |
| `PercussionTechniqueSymbols` | "160" |
| `GuitarSymbols` | "176" |
| `ArticulationSymbols` | "208" |
| `AccidentalSymbols` | "256" |
| `NoteSymbols` | "288" |
| `NoteheadSymbols` | "320" |
| `RestSymbols` | "368" |
| `ConductorSymbols` | "400" |
| `ClefSymbols` | "416" |
| `OctaveSymbols` | "448" |
| `BreakSymbols` | "464" |
| `TechniqueSymbols` | "480" |
| `AccordionSymbols` | "496" |
| `HandbellSymbols` | "528" |
| `MiscellaneousSymbols` | "544" |

### Symbol Size Constants

| Constant | Value |
| --- | --- |
| `NormalSize` | "0" |
| `CueSize` | "1" |
| `GraceNoteSize` | "2" |
| `CueGraceNoteSize` | "3" |

## Special Page Break Types

| Constant | Value |
| --- | --- |
| `NoPageBreak` | "0" |
| `MusicRestartsAfterXPages` | "1" |
| `MusicRestartsOnNextLeftPage` | "2" |
| `MusicRestartsOnNextRightPage` | "3" |

## Interval Types

(Used as the interval-type argument to `NoteRest.Transpose` / `Selection.Transpose`.)

| Constant | Value |
| --- | --- |
| `IntervalDiatonic` | "-1" |
| `Interval5xDiminished` | "0" |
| `Interval4xDiminished` | "1" |
| `Interval3xDiminished` | "2" |
| `Interval2xDiminished` | "3" |
| `IntervalDiminished` | "4" |
| `IntervalMinor` | "4" |
| `IntervalMajor` | "5" |
| `IntervalPerfect` | "5" |
| `IntervalAugmented` | "6" |
| `Interval2xAugmented` | "7" |
| `Interval3xAugmented` | "8" |
| `Interval4xAugmented` | "9" |
| `Interval5xAugmented` | "10" |

Note: as printed in the guide, `IntervalDiminished` and `IntervalMinor` share value "4", and `IntervalMajor` and `IntervalPerfect` share value "5" (minor/major apply to 2nds/3rds/6ths/7ths; perfect to unisons/4ths/5ths/octaves).

## InMultirest Values

| Constant | Value |
| --- | --- |
| `NoMultirest` | "0" |
| `StartsMultirest` | "1" |
| `EndsMultirest` | "2" |
| `MidMultirest` | "3" |

## Page Number Visibility Values

| Constant | Value |
| --- | --- |
| `PageNumberShowAll` | "0" |
| `PageNumberHideFirst` | "1" |
| `PageNumberHideAll` | "2" |

## Page Number Format Values

| Constant | Value |
| --- | --- |
| `PageNumberFormatNormal` | "0" |
| `PageNumberFormatRomanUpper` | "1" |
| `PageNumberFormatRomanLower` | "2" |
| `PageNumberFormatLetterLower` | "3" |

## Special Barlines

| Constant | Value |
| --- | --- |
| `SpecialBarlineStartRepeat` | "0" |
| `SpecialBarlineEndRepeat` | "1" |
| `SpecialBarlineDashed` | "2" |
| `SpecialBarlineDouble` | "3" |
| `SpecialBarlineFinal` | "4" |
| `SpecialBarlineInvisible` | "5" |
| `SpecialBarlineBetweenStaves` | "6" |
| `SpecialBarlineNormal` | "7" |
| `SpecialBarlineTick` | "8" |
| `SpecialBarlineShort` | "9" |
| `SpecialBarlineDotted` | "10" |
| `SpecialBarlineTriple` | "11" |
| `SpecialBarlineThick` | "12" |

## Bar Rest Type Values

| Constant | Value |
| --- | --- |
| `WholeBarRest` | "0" |
| `BreveBarRest` | "1" |
| `OneBarRepeat` | "2" |
| `TwoBarRepeat` | "3" |
| `FourBarRepeat` | "4" |

## GuitarScaleDiagram Type Values

| Constant | Value |
| --- | --- |
| `ScaleTypeMajor` | "0" |
| `ScaleTypeMinor` | "1" |
| `ScaleTypeHarmonicMinor` | "2" |
| `ScaleTypeMelodicMinor` | "3" |
| `ScaleTypeDorian` | "4" |
| `ScaleTypePhrygian` | "5" |
| `ScaleTypeLydian` | "6" |
| `ScaleTypeMixolydian` | "7" |
| `ScaleTypeLocrian` | "8" |
| `ScaleTypeWholeTone` | "9" |
| `ScalrTypeDiminishedHalfWhole` | "10" (sic — typo in the guide) |
| `ScaleTypeDiminishedWholeHalf` | "11" |
| `ScaleTypeAlteredDominant` | "12" |
| `ScaleTypeLocrianSharp2` | "13" |
| `ScaleTypeLydianFlat7` | "14" |
| `ScaleTypeMajorBebop` | "15" |
| `ScaleTypeDominantBebop` | "16" |
| `ScaleTypeLydianSharp5` | "17" |
| `ScaleTypePhrygianDominant` | "18" |
| `ScaleTypeAugmentedArpeggio` | "19" |
| `ScaleTypeMajor7thArpeggio` | "20" |
| `ScaleType7thArpeggio` | "21" |
| `ScaleTypeMin7Flat5Arpeggio` | "22" |
| `ScaleTypeDiminished7thArpeggio` | "23" |
| `ScaleTypeMajorPentatonic` | "24" |
| `ScaleTypeMinorPentatonic` | "25" |
| `ScaleTypeOther` | "26" |

## FeatheredBeamType Values

For the `FeatheredBeamType` variable of NoteRest objects.

| Constant | Value |
| --- | --- |
| `FeatheredBeamNone` | "0" |
| `FeatheredBeamAccel` | "1" |
| `FeatheredBeamRit` | "2" |

## Units Values

For the DocumentSetup object.

| Constant | Value |
| --- | --- |
| `DocumentSetupUnitsmm` | "0" |
| `DocumentSetupUnitsInches` | "1" |
| `DocumentSetupUnitsPoints` | "2" |

## Orientation Values

For the `Orientation` variable of DocumentSetup objects.

| Constant | Value |
| --- | --- |
| `OrientationPortrait` | "0" |
| `OrientationLandscape` | "1" |

## PageSize Values

For the `PageSize` variable of DocumentSetup objects.

| Constant | Value |
| --- | --- |
| `PageSizeLetter` | "0" |
| `PageSizeTabloid` | "1" |
| `PageSizeA5` | "2" |
| `PageSizeB5` | "3" |
| `PageSizeA4` | "4" |
| `PageSizeB4` | "5" |
| `PageSizeA3` | "6" |
| `PageSizeUSBand` | "7" |
| `PageSizeStatement` | "8" |
| `PageSizeHymn` | "9" |
| `PageSizeOctavo` | "10" |
| `PageSizeExecutive` | "11" |
| `PageSizeQuarto` | "12" |
| `PageSizeConcert` | "13" |
| `PageSizeFolio` | "14" |
| `PageSizeLegal` | "15" |
| `PageSize9_5x12_5` | "16" |
| `PageSize10x13` | "17" |
| `PageSizeCustom` | "18" |

## MarginType Values

For the `MarginType` variable of DocumentSetup objects.

| Constant | Value |
| --- | --- |
| `PageMarginsSame` | "0" |
| `PageMarginsMirrored` | "1" |
| `PageMarginsDifferent` | "2" |

## StaffScaleFactor Values

For the `StaffScaleFactor` variable of Staff objects.

| Constant | Value |
| --- | --- |
| `NormalSize` | "0" |
| `MediumSize` | "1" |
| `SmallSize` | "2" |
| `ExtraSmallSize` | "3" |

## Tuplets

Constants for the style parameter of `Bar.AddTuplet()` and `Tuplet.AddNestedTuplet()`:

| Constant | Value |
| --- | --- |
| `TupletNoNumber` | "0" |
| `TupletLeft` | "1" |
| `TupletLeftRight` | "2" |
| `TupletLeftRightNote` | "3" |

Constants for the bracket parameter:

| Constant | Value |
| --- | --- |
| `TupletBracketOff` | "0" |
| `TupletBracketOn` | "1" |
| `TupletBracketAuto` | "2" |

## SingleTremolos

For the `SingleTremolos` variable of NoteRest objects: numbers 0–7 give the number of tremolo beams on the stem. For a "z on stem" (buzz roll), use -1 or the constant `ZOnStem`.

## DoubleTremolo Values

For the double tremolo style variables of EngravingRules objects.

| Constant | Value |
| --- | --- |
| `DoubleTremolosTouchingStems` | "0" |
| `DoubleTremolosBetweenStems` | "1" |
| `DoubleTremolosOuterTremoloTouchingStems` | "2" |

## BarNumberFrequencyCategory Values

For the `BarNumberFrequencyCategory` variable of EngravingRules objects.

| Constant | Value |
| --- | --- |
| `EverySystem` | "0" |
| `NoBarNumbers` | "1" |
| `EveryNthBar` | "2" |

## Instrument Name Values

For the instrument name variables of EngravingRules objects.

| Constant | Value |
| --- | --- |
| `InstrumentNamesFull` | "0" |
| `InstrumentNamesShort` | "1" |
| `InstrumentNamesNone` | "2" |

## Types of Objects in a Bar

The `Type` field for objects in a bar can return one of:

- `Clef`, `SpecialBarline`, `TimeSignature`, `KeySignature`
- `Line`, `ArpeggioLine`, `Bend`, `CrescendoLine`, `DiminuendoLine`, `GlissandoLine`, `OctavaLine`, `PedalLine`, `RepeatTimeLine`, `Slur`, `Trill`, `Box`, `BeamLine`, `Tuplet`, `RitardLine`, `HighLight`
- `LyricItem`, `Text`, `SystemTextItem`, `GuitarFrame`, `GuitarScaleDiagram`, `RehearsalMark`, `InstrumentChange`
- `BarRest`, `NoteRest`, `Graphic`, `Comment`, `Bracket`, `BarNumber`
- `SymbolItem`, `SystemSymbolItem`

## Interpreter Options

| Option | Meaning |
| --- | --- |
| `IncludeScoreSubsetsInDynamicPartCollection` | When enabled, score subsets are included in the DynamicPartCollection obtained via Score's `DynamicParts` variable. As of Sibelius 2024.3 score subsets are no longer included by default. |
| `TreatSingleCharacterAsString` | When enabled, literals such as "1" are treated as strings, not characters: a single digit has the digit's value (not its ASCII code); non-digit values like "a" convert to 0 (use `Asc` for the ASCII value); comparisons like "ManuScript" = "M" are false. |
| `SupportHalfSemitonePitchValues` | When enabled, floating-point pitch values are accepted so scripts can manipulate quarter-tones (0.5 semitone = one quarter-tone; likewise for accidentals). Accepting floating-point pitches: `NoteRest.AddNote`, `Bar.AddNote`, `Stave.AddNote`. Returning floating-point values: `Note.Pitch`, `Note.WrittenPitch`, `Note.Accidental`, `Note.WrittenAccidental`. |

