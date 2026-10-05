"""Summarize the notes in a MIDI file, one line per track.

Use it to check a conversion: compare LilyPond's MIDI with a MIDI exported
from the finished score (Sibelius, Dorico or MuseScore). Note counts, ranges and timing should
match exactly. Needs only the standard library.

usage: midi_info.py FILE.mid [FILE.mid ...]
"""

from __future__ import annotations

import struct
import sys
from dataclasses import dataclass

DATA_BYTES = {0x80: 2, 0x90: 2, 0xA0: 2, 0xB0: 2, 0xC0: 1, 0xD0: 1, 0xE0: 2}


@dataclass
class Track:
    name: str
    notes: int
    first: float  # quarter notes from the start
    last: float
    low: int
    high: int


def read_tracks(data: bytes) -> list[Track]:
    if data[:4] != b"MThd":
        raise ValueError("not a MIDI file")
    division = struct.unpack(">H", data[12:14])[0]
    pos = 8 + struct.unpack(">I", data[4:8])[0]
    tracks: list[Track] = []

    def vlq(p: int) -> tuple[int, int]:
        value = 0
        while True:
            byte = data[p]
            p += 1
            value = (value << 7) | (byte & 0x7F)
            if byte < 0x80:
                return value, p

    while pos < len(data):
        length = struct.unpack(">I", data[pos + 4:pos + 8])[0]
        p, end = pos + 8, pos + 8 + length
        status, tick, name, onsets = 0, 0, "", []
        while p < end:
            delta, p = vlq(p)
            tick += delta
            byte = data[p]
            if byte == 0xFF:
                kind = data[p + 1]
                size, q = vlq(p + 2)
                if kind == 3:
                    name = data[q:q + size].decode("latin-1")
                p = q + size
                continue
            if byte in (0xF0, 0xF7):
                size, q = vlq(p + 1)
                p = q + size
                continue
            if byte & 0x80:
                status = byte
                p += 1
            if status & 0xF0 == 0x90 and data[p + 1] > 0:
                onsets.append((tick, data[p]))
            p += DATA_BYTES[status & 0xF0]
        if onsets:
            pitches = [n for _, n in onsets]
            tracks.append(Track(name, len(onsets), onsets[0][0] / division, onsets[-1][0] / division,
                                min(pitches), max(pitches)))
        pos = end
    return tracks


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    for path in sys.argv[1:]:
        with open(path, "rb") as f:
            tracks = read_tracks(f.read())
        print(path)
        for t in tracks:
            print(f"  {t.name[:20]:20} notes={t.notes:4} first={t.first:7.1f} last={t.last:7.1f} "
                  f"range={t.low}-{t.high}")


if __name__ == "__main__":
    main()
