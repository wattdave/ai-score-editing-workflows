# Bar checks (OMR bar 1 and bar sums)

`check_bar_sums` in `audit_musicxml.py` measures where each voice (staff and
voice number) ends in each bar, from the same note onsets the other checks use.
All of these are warnings except `score-empty`: compare with the print before
changing anything. The cases come from the Nelson Carol Book scans (2026-11).

## `score-empty` (error)

No pitched note anywhere. Halbestunde returned a one-bar empty score for four
hymn pages at `clean_pdf.py --pad 40` (Adeste Fideles, Angels We Have Heard On
High, Good King Wenceslas, Joy to the World); scan again at `--pad 100`.

## `bar1-empty`

Bar 1 holds no notes in any part, only rests or nothing. Deck the Hall came
back with a leading bar of one short rest per voice before the 16 real bars.
Delete the bar unless the print opens with a rest bar.

## `bar1-pickup-suspect`

Reported per part, with the reasons found:

- **A voice lasts longer than the bar.** We Three Kings: one bass voice summed
  5 eighths in 3/8.
- **Bar 1 is short and its voices end at different points.** The First Nowell:
  the verse number "1." and a fleck became two extra eighths in the soprano and
  tenor, so those voices last 4 eighths and the others 2.
- **Bar 1 is short and a voice opens with a rest.** A pickup is normally
  written without rests. O Come, All Ye Faithful and I Saw Three Ships came back
  as a half rest plus the pickup note; Away in a Manger had an eighth rest and a
  stray eighth; MuseScore Convert read the bass pickup of We Wish You a Merry
  Christmas as a rest.
- **Bar 1 and the last bar are both short and do not add up to one bar.**
  I Saw Three Ships: bar 1 lasted 5 eighths and the last bar 5 in 6/8.
- **Bar 1 is full but the last bar is short.** We Wish You a Merry Christmas
  (Halbestunde): the one-quarter pickup became a full bar of three invented
  quarters with shifted lyrics; the last bar lasts two beats.
- **A note's only lyric is a verse number** (`1.`, `2`). God Rest Ye Merry,
  Gentlemen: bar 1 held three quarters where the print has a one-quarter
  pickup; the first carried the verse numbers.

A short bar 1 whose voices agree, open with notes and complete the last bar
(or the last bar is full, as in many hymnals) passes.

## `bars-short`

A bar after the first where a voice stops before the end of the bar. Usually
a rest the scan dropped (We Wish You a Merry Christmas, Halbestunde: the
lower voices of bars 9 and 13). The last bar is reported only when some voice
fills it, because a short last bar that completes a pickup is normal; there
the cause may be a rest added to the full voice instead (Away in a Manger).
Bars with `<forward>` and bars split in two (one half `implicit="yes"`, as
Dorico writes a bar broken by a barline) are skipped. A mid-piece pickup at a
repeat is short by design.
