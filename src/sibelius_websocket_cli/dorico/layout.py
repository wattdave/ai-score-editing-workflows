"""Assign Dorico's voice streams to staves.

Dorico's Lua lists stave streams and each instrument's voice streams but has
no link from a voice to its stave (docs/dorico.md). Rules, in order:

1. Staves go to instruments in order. With as many instruments as staves,
   one each; with one instrument, all of them; otherwise the MusicXML
   export's parts say how many staves each instrument has.
2. An instrument with one stave gets all its voices.
3. An instrument with one voice per stave gives them out in id order
   (checked on a piano and an imported SATB score).
4. Otherwise each voice goes to the stave whose MusicXML notes match its
   notes best (by flow position and pitch). A voice with no notes cannot be
   placed and is left out.

Voices are numbered per stave in id order. Anything the rules cannot
settle without MusicXML raises NeedsMusicXML.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from .client import DoricoError


class NeedsMusicXML(Exception):
    """The layout cannot be settled from Lua alone."""


def resolve(
    raw: dict[str, Any],
    events: list[dict[str, Any]],
    musicxml: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Staves as [{staff, name, stream, voiceStreams}], staff numbers from 1."""
    staves = [s["stream"] for s in raw["staves"]]
    instruments = raw["instruments"]
    counts = _staves_per_instrument(len(staves), instruments, musicxml)
    result: list[dict[str, Any]] = []
    first = 0
    for instrument, count in zip(instruments, counts):
        own = list(range(first, first + count))
        first += count
        for i in own:
            result.append({"staff": i + 1, "name": instrument.get("name"), "stream": staves[i], "voiceStreams": []})
        voices = sorted(instrument.get("voiceStreams") or [])
        if count == 1:
            result[own[0]]["voiceStreams"] = voices
        elif len(voices) == count:
            for i, voice in zip(own, voices):
                result[i]["voiceStreams"] = [voice]
        else:
            if musicxml is None:
                raise NeedsMusicXML(f"{instrument.get('name')} has {len(voices)} voices on {count} staves")
            for voice in voices:
                staff = _best_staff(voice, [i + 1 for i in own], events, musicxml)
                if staff is not None:
                    result[staff - 1]["voiceStreams"].append(voice)
    if first != len(staves):
        raise DoricoError(f"the instruments account for {first} staves but the flow has {len(staves)}")
    return result


def _staves_per_instrument(
    total: int, instruments: list[dict[str, Any]], musicxml: dict[str, Any] | None
) -> list[int]:
    if len(instruments) == total:
        return [1] * total
    if len(instruments) == 1:
        return [total]
    if musicxml is None:
        raise NeedsMusicXML(f"{len(instruments)} instruments share {total} staves")
    names = [s["name"] for s in musicxml["staves"]]
    counts = []
    index = 0
    for _ in instruments:
        if index >= len(names):
            break
        run = 1
        while index + run < len(names) and names[index + run] == names[index] and _same_part(musicxml, index, run):
            run += 1
        counts.append(run)
        index += run
    if len(counts) != len(instruments) or sum(counts) != total:
        raise DoricoError("the MusicXML export's parts do not match Dorico's instruments")
    return counts


def _same_part(musicxml: dict[str, Any], index: int, run: int) -> bool:
    staves = musicxml["staves"]
    return staves[index + run].get("part") == staves[index].get("part")


def _best_staff(
    voice: int, candidates: list[int], events: list[dict[str, Any]], musicxml: dict[str, Any]
) -> int | None:
    notes = {(e["position"], e["pitch"]) for e in events if e.get("stream") == voice and e.get("pitch") is not None}
    if not notes:
        return None
    scores: Counter[int] = Counter()
    for e in musicxml["events"]:
        if e["staff"] in candidates and e.get("pitch") is not None and (e["flowPosition"], e["pitch"]) in notes:
            scores[e["staff"]] += 1
    if not scores:
        return None
    return scores.most_common(1)[0][0]


def assign(events: list[dict[str, Any]], staves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Give voice-stream events their staff and voice number; drop unplaced ones."""
    where: dict[int, tuple[int, int]] = {}
    for s in staves:
        for number, stream in enumerate(s["voiceStreams"], start=1):
            where[stream] = (s["staff"], number)
    out = []
    for event in events:
        if event.get("staff") is not None:
            out.append(event)
        elif event.get("stream") in where:
            staff, voice = where[event["stream"]]
            out.append({**event, "staff": staff, "voice": voice})
    return out
