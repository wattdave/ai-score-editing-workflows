"""Template for one melody-line generator. Copy it, set the constants, run it with --dump until the note and
syllable counts match, then without --dump to write the MusicXML and import it with sib_import.py.

    uv run --with mido --with lxml --with pyphen python -I melody_template.py --dump
    uv run --with mido --with lxml --with pyphen python -I melody_template.py            # writes OUT
    uv run --with mido --with lxml --with pyphen python -I melody_template.py --swing    # swing playback copy

The words come from a text file made by OCR of the director's sheet (never typed into a script), see SKILL.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from melody_lib import *  # noqa: E402,F403
from syllabify import syllabify  # noqa: E402

SRC = "/path/to/karaoke.mid"          # MIDI with a clean melody track (or hand-typed notes, see parse_notes)
TRACK, CHANNEL = 3, None              # pick whichever reads_notes shows as one note at a time
LYRICS = "/path/to/lyrics.txt"        # OCR text of the director's words for this song
OUT = "/path/to/song - melody.xml"
TITLE, FIFTHS, BEATS, TEMPO = "Song Title", 0, 4, 120
FIRST_BEAT, LAST_BEAT = 24.0, 148.0   # window of the MIDI to use (first = onset of the pickup note)
PICKUP = 0.0                          # length of a pickup in beats (0 = none)
GRID, UNSWING = 0.5, True             # half-beat grid; UNSWING snaps triplet-swing onsets to straight eighths
FIX = {}                              # per-word syllable overrides, e.g. {"santa": "San-ta"}
SUBSTITUTE = {}                       # text tweaks before syllabifying, e.g. {"goodness sake": "goodness sake _ _ _"}

text = open(LYRICS).read()
for old, new in SUBSTITUTE.items():
    text = text.replace(old, new)
lyrics = syllabify(text, FIX)

notes = read_notes(SRC, track=TRACK, channel=CHANNEL)
events = window(quantize(notes, grid=GRID, unswing=UNSWING, rest_gap=1.3), FIRST_BEAT, LAST_BEAT)
while events[-1][2] is None:            # drop trailing rests, then hold the last note to the end of its bar
    events.pop()
last_start = events[-1][0]
bar_end = (int((last_start - PICKUP) // BEATS) + 1) * BEATS + PICKUP
events[-1] = (last_start, bar_end - last_start, events[-1][2])

if "--dump" in sys.argv:
    print(dump(events, BEATS, 4, pickup=PICKUP, fifths=FIFTHS, lyrics=lyrics))
elif "--swing" in sys.argv:
    print(write_swing_xml(events, OUT.replace(".xml", " swing.xml"), TITLE + " (swing playback)", FIFTHS, BEATS, 4,
                          pickup=PICKUP, tempo=TEMPO, lyrics=lyrics))
else:
    print(write_xml(events, OUT, TITLE, FIFTHS, BEATS, 4, pickup=PICKUP, tempo=TEMPO, lyrics=lyrics))
