# MusiXTeX font code table (musix20 family), from musixtex.tex 1.41 (CTAN, GPL v2+)

Code = character number in the music font (`\musixchar N`, or `\musixfont\<chardef>`). Only codes that musixtex.tex names directly; flags and beam stubs are derived (first flag code + offsets) and are listed under 'Derived'.

| code | macro(s) using it (context) |
|---|---|
| 0 | \C@pspt |
| 4 | \@Fl, \@Na, \@Sh, \bigna, \cna, \smallna, \t@bbbbl, \t@bbbbu, \upperna |
| 5 | \t@bbbbbl, \t@bbbbbu |
| 6 | \@beam, \C@cresc |
| 7 | \q@symbol, \tzqu |
| 8 | \h@symbol, \tzhu |
| 9 | \tzwh, \tzwhp, \wh, \whp, \whpp |
| 12 | \@grcu |
| 14 | \writ@staffs |
| 15 | \writ@staffs |
| 20 | \v@rline, \varline |
| 22 | \downbow |
| 23 | \C@TO, \octfinup, \upbow |
| 25 | \C@TO, \octfindown |
| 29 | \v@rline, \varline |
| 32 | \breve, \l@ngasymbol, \zbreve |
| 33 | \Dep |
| 34 | \sPed |
| 35 | \Ped |
| 36 | \maxima, \zmaxima |
| 39 | \longa, \zlonga |
| 40 | parenleft | 40 | eighth flag, stem up (`\@cu`, `\@xl`=40); 41 = sixteenth flag |
| 41 | \@ccu, \@ccup, \tzccu, \tzccup |
| 45 | hyphen | 45 | flag, stem down (`\@cl`, `\@xlv`=45; not a hyphen) |
| 50 | \C@acc, \W@Fl, \w@cancelflats, \writ@sign |
| 52 | \W@Sh, \w@cancelsharps, \writ@sign |
| 54 | \W@canFl, \W@canSh, \w@cancelflats, \w@cancelsharps, \writ@slur |
| 56 | \wq, \zwq |
| 58 | \PAuse, \cPAuse |
| 59 | \PAUSe, \cPAUSe |
| 60 | \chpause, \hpause |
| 61 | \cpause, \pause |
| 62 | \qp, \qpp, \qppp |
| 63 | \ds, \dsp, \dspp, \qp |
| 64 | \qs, \qsp, \qspp |
| 65 | \hs, \hsp, \hspp |
| 66 | \qqs, \qqsp, \qqspp |
| 69 | \C@TR, \trill@ |
| 70 | \arpeggio |
| 79 | \caesura |
| 104 | \sDep |
| 127 | \wqq, \zwqq |
| 128 | \@beam, \@bracks, \w@st, \writ@slur |

## Confirmed against the Reinecke Silent Night PDF (TeXMUSIX20 embedded font)

| code | glyph name in the embedded font | PDF char (decimal) | meaning |
|---|---|---|---|
| 0 | grave | 96 | augmentation dot (`C@pspt`) |
| 7 | caron | 711 | quarter/eighth/sixteenth notehead (`q@symbol` uses chardef `\s@v@n`=7) |
| 8 | breve | 728 | half-note head (`h@symbol` uses `\@ight`=8) |
| 14, 15 | guilsinglleft/right | 8249, 8250 | system brace halves (`writ@staffs`) |
| 40 | parenleft | 40 | eighth flag, stem up (`\@cu`, `\@xl`=40); 41 = sixteenth flag |
| 45 | hyphen | 45 | flag, stem down (`\@cl`, `\@xlv`=45; not a hyphen) |
| 71 | G | 71 | treble clef (`\trebleclef` = `\keychar71`) |
| 73 | I | 73 | bass clef (`\bassclef` = `\keychar73`) |
| 193, 196, 197, 199, 202, 203 | Aacute, Adieresis, Aring, Ccedilla, Ecircumflex, Edieresis | same | sloped beam segments (see below) |

## How to map a PDF to codes (no font install needed)

1. Extract each embedded TeXMUSIX font with `doc.extract_font(xref)` (it is a Type 1 program).
2. Read its `Encoding` array: lines `dup N /glyphname put`. N is the MusiXTeX code, the glyph name is only a Fontographer placeholder.
3. PyMuPDF `get_texttrace()` gives each glyph's Unicode and origin (x, y); convert the Unicode back to the glyph name (Adobe Glyph List: 711 = caron, 728 = breve, 96 = grave) and then to N.
4. Pitch: find the staff lines (thin horizontal drawings, spacing about 5 pt at this size), then pitch = steps from the bottom line (treble E4, bass G2) with `round((bottom_line_y - head_y) / (spacing/2))`.
5. Rhythm: heads, dots, flags and the beams (filled rectangles) plus stems (thin vertical rectangles); in a 6/8 bar the totals must sum.

Fonts for the same family: musix16, musix20 (this PDF), musix24 ... differ only in size. Type 1 font files (not needed) are in CTAN `fonts/musixtex-fonts`.

## Sloped beams (codes 128-255), verified in musixtex.tex `\@beam`

Flat beams are rules (filled rectangles), not glyphs. A sloped beam is drawn from repeated segment glyphs whose code is `128 + n`:

- slope b > 0 (rising): n = 6*b - 6
- slope b < 0 (falling): n = 58 + 6*(-b)
- then add 0..5 (`\b@adjust`): the segment length class; the larger the number, the shorter the segment.

So in the Reinecke PDF 193 = 128+65 (falling slope 1, class 1), 196 = 128+68 (class 4), 197 = 128+69 (class 5), 199 = 128+71 (falling slope 2, class 1), 202 (class 4), 203 (class 5). Glyph x-positions repeat along the beam: take the first and last segment of a run for the beam's ends, and the y of each to read the slope. Codes 0-63 are the note/rest/accidental symbols above; 104 = sDep, 115 = decrescendo hairpin offset, 127 = `\wqq` whole-note variant.

Still not decoded: rests, accidentals and the slur-font glyphs (TeXXSLU/XSLD/XSLZ). The Reinecke PDF uses none of the rest or accidental glyphs, so they are unverified here.
