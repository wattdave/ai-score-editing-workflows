#!/usr/bin/env python3
"""Print note ranges and opening notes for each named standard-MIDI track."""

from __future__ import annotations

import argparse
from pathlib import Path


def read_vlq(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    while True:
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset


def track_notes(track: bytes) -> tuple[str, list[int]]:
    offset = 0
    running_status: int | None = None
    name = ""
    notes: list[int] = []
    while offset < len(track):
        _, offset = read_vlq(track, offset)
        status = track[offset]
        if status < 0x80:
            if running_status is None:
                raise ValueError("MIDI running status without a prior status byte")
            status = running_status
        else:
            offset += 1
            if status < 0xF0:
                running_status = status

        if status == 0xFF:
            meta_type = track[offset]
            offset += 1
            length, offset = read_vlq(track, offset)
            payload = track[offset : offset + length]
            offset += length
            if meta_type == 0x03:
                name = payload.decode(errors="replace")
        elif status in (0xF0, 0xF7):
            length, offset = read_vlq(track, offset)
            offset += length
        else:
            message_type = status & 0xF0
            note = track[offset]
            offset += 1
            if message_type not in (0xC0, 0xD0):
                velocity = track[offset]
                offset += 1
                if message_type == 0x90 and velocity:
                    notes.append(note)
    return name, notes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("midi", type=Path)
    args = parser.parse_args()
    data = args.midi.read_bytes()
    if data[:4] != b"MThd":
        raise ValueError("not a standard MIDI file")
    track_count = int.from_bytes(data[10:12], "big")
    offset = 14
    for _ in range(track_count):
        if data[offset : offset + 4] != b"MTrk":
            raise ValueError("missing MIDI track header")
        length = int.from_bytes(data[offset + 4 : offset + 8], "big")
        track = data[offset + 8 : offset + 8 + length]
        offset += 8 + length
        name, notes = track_notes(track)
        if notes:
            print(f"{name or 'Unnamed'}: {min(notes)}–{max(notes)}; opening {notes[:8]}")


if __name__ == "__main__":
    main()
