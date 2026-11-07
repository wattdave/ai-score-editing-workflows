#!/usr/bin/env python3
"""Audit a MusicXML file for what makes a score unfit to print or share.

Standard library only, so the skill runs without the rest of this repository.

Usage:
    audit_musicxml.py SCORE.xml|SCORE.mxl [--json]

Exit status: 0 when there are no errors, 1 when something must be fixed,
2 when the file cannot be read.

Severity:
    error  fix before sharing (missing title, generic part names, ...)
    warn   probably wrong; compare with the source print
    info   a fact worth knowing (for example, no beams: editors auto-beam)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from collections import Counter
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

BEAMABLE = {"eighth", "16th", "32nd", "64th", "128th"}
GENERIC_PART = re.compile(r"^(voice|staff|part|track|instrument)\s*\d*$", re.I)
CHORD_LIKE = re.compile(r"^[a-g](#|b)?(m|maj|min|dim|aug|sus|add)?\d*(/[a-g](#|b)?)?$", re.I)
OMR_SOFTWARE = ("halbestunde", "photoscore", "smartscore", "playscore", "audiveris", "musescore pdf", "capella")


def load(path: Path) -> ET.Element:
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            return ET.fromstring(z.read(name))
    return ET.parse(path).getroot()


def finding(code: str, severity: str, message: str, where: str = "") -> dict:
    return {"code": code, "severity": severity, "message": message, "where": where}


def check_metadata(root: ET.Element) -> list[dict]:
    out = []
    title = (root.findtext("work/work-title") or root.findtext("movement-title") or "").strip()
    raw_title = root.findtext("work/work-title") or root.findtext("movement-title") or ""
    if not title:
        out.append(finding("title-missing", "error", "No work or movement title."))
    else:
        if raw_title != raw_title.strip():
            out.append(finding("title-whitespace", "warn", f"Title has leading/trailing space: {raw_title!r}"))
        if title == title.lower() or (title == title.upper() and len(title) > 3):
            out.append(finding("title-case", "warn", f"Title is all lower or all upper case: {title!r}"))
        if re.match(r"^\d+[.)]\s", title):
            out.append(finding("title-numbered", "warn", f"Title starts with a list number: {title!r}"))
    creators = [(c.get("type"), (c.text or "").strip()) for c in root.findall("identification/creator") if (c.text or "").strip()]
    credit_words = [(w.text or "").strip() for w in root.findall("credit/credit-words") if (w.text or "").strip()]
    if not creators and not credit_words:
        out.append(finding("composer-missing", "warn", "No composer, arranger or credit text."))
    if not (root.findtext("identification/rights") or "").strip():
        out.append(finding("rights-missing", "warn", "No copyright/source line (see the three templates in SKILL.md)."))
    return out


CREDIT_CREATORS = {"composer", "arranger", "lyricist", "poet", "translator"}
CREDIT_NEVER_MERGE = {"title", "subtitle", "page number", "part name"}
CREDIT_STYLE = ("justify", "halign", "valign", "font-size", "font-family", "font-style", "font-weight")


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def check_credits_split(root: ET.Element) -> list[dict]:
    """One printed block (composer + arranger, a multi-line footer) stored as
    one <credit> per line. Same rule as score-metadata-repair --merge-credits:
    same page, alignment, font and x, line gap at most 3 x font size, both
    creator credits or both plain/rights text; titles and subtitles never."""
    groups: dict[tuple, list[tuple[float, float, str, float]]] = {}
    for credit in root.findall("credit"):
        kids = list(credit)
        words = credit.findall("credit-words")
        if len(words) != 1 or any(k.tag not in ("credit-type", "credit-words") for k in kids):
            continue
        cw = words[0]
        types = {(t.text or "").strip().lower() for t in credit.findall("credit-type")}
        x, y, text = _float(cw.get("default-x")), _float(cw.get("default-y")), (cw.text or "").strip()
        if x is None or y is None or not text or len(cw) or types & CREDIT_NEVER_MERGE:
            continue
        kind = "creator" if types and types <= CREDIT_CREATORS else "|".join(sorted(types - {"rights"})) or "text"
        key = (credit.get("page", "1"), tuple(cw.get(a) for a in CREDIT_STYLE), kind)
        groups.setdefault(key, []).append((x, y, text, _float(cw.get("font-size")) or 12.0))
    blocks = []
    for lines in groups.values():
        lines.sort(key=lambda ln: (round(ln[0]), -ln[1]))
        run: list = []
        for ln in lines:
            if run and (abs(ln[0] - run[-1][0]) > 2 or not 0 < run[-1][1] - ln[1] <= 3 * run[-1][3]):
                if len(run) > 1:
                    blocks.append(run)
                run = []
            run.append(ln)
        if len(run) > 1:
            blocks.append(run)
    if not blocks:
        return []
    sample = "; ".join(" / ".join(ln[2] for ln in b) for b in blocks[:3])
    return [finding("credits-split", "warn", f"{len(blocks)} credit block(s) stored one line per credit, so the editor imports each line as its own text (or drops one): {sample}. Use score-metadata-repair --merge-credits.")]


def check_parts(root: ET.Element) -> list[dict]:
    out = []
    for sp in root.findall("part-list/score-part"):
        pid = sp.get("id")
        name = (sp.findtext("part-name") or "").strip()
        if not name or GENERIC_PART.match(name):
            out.append(finding("part-name-generic", "error", f"Part {pid} is named {name!r}.", pid))
        elif not (sp.findtext("part-abbreviation") or "").strip():
            out.append(finding("part-abbreviation-missing", "warn", f"Part {pid} ({name}) has no abbreviation.", pid))
    return out


class NoteRec:
    __slots__ = ("onset", "beams", "has_lyric", "syllabic", "measure", "voice")

    def __init__(self, onset, beams, has_lyric, syllabic, measure, voice):
        self.onset, self.beams, self.has_lyric, self.syllabic, self.measure, self.voice = onset, beams, has_lyric, syllabic, measure, voice


def beat_length(divisions: int, beats: int, beat_type: int) -> int:
    if beat_type == 8 and beats % 3 == 0 and beats >= 6:
        return divisions * 3 // 2  # three eighths
    return divisions * 4 // beat_type


def check_beams(root: ET.Element, software: str) -> list[dict]:
    out, stats = [], Counter()
    mixed = []
    for part in root.findall("part"):
        pid = part.get("id")
        divisions, beats, beat_type = 1, 4, 4
        for m in part.findall("measure"):
            mnum = m.get("number")
            cursor = 0
            by_voice: dict[tuple[str, str], list[NoteRec]] = {}
            last_onset = 0
            for el in m:
                if el.tag == "attributes":
                    if el.findtext("divisions"):
                        divisions = int(el.findtext("divisions"))
                    t = el.find("time")
                    if t is not None and t.findtext("beats", "").isdigit():
                        beats, beat_type = int(t.findtext("beats")), int(t.findtext("beat-type"))
                elif el.tag == "backup":
                    cursor -= int(el.findtext("duration") or 0)
                elif el.tag == "forward":
                    cursor += int(el.findtext("duration") or 0)
                elif el.tag == "note":
                    is_chord = el.find("chord") is not None
                    onset = last_onset if is_chord else cursor
                    dur = int(el.findtext("duration") or 0)
                    if not is_chord:
                        last_onset = onset
                        cursor += dur if el.find("grace") is None else 0
                    if is_chord or el.find("rest") is not None or el.find("grace") is not None:
                        continue
                    if el.findtext("type") not in BEAMABLE:
                        continue
                    lyr = el.find("lyric")
                    beams = {b.get("number", "1"): b.text for b in el.findall("beam")}
                    key = (el.findtext("staff") or "1", el.findtext("voice") or "1")
                    by_voice.setdefault(key, []).append(
                        NoteRec(onset, beams, lyr is not None, lyr.findtext("syllabic") if lyr is not None else None, mnum, key)
                    )
            bl = beat_length(divisions, beats, beat_type) or 1
            for key, notes in by_voice.items():
                groups: dict[int, list[NoteRec]] = {}
                for n in notes:
                    groups.setdefault(n.onset // bl, []).append(n)
                for g in groups.values():
                    if len(g) < 2:
                        stats["beamable_single"] += len(g)
                        continue
                    joined = [
                        a.beams.get("1") in ("begin", "continue") and b.beams.get("1") in ("continue", "end")
                        for a, b in zip(g, g[1:])
                    ]
                    stats["beamable_in_groups"] += len(g)
                    if all(joined):
                        stats["groups_fully_beamed"] += 1
                    elif not any(joined):
                        stats["groups_unbeamed"] += 1
                    else:
                        stats["groups_mixed"] += 1
                        mixed.append(f"{pid} bar {mnum}")
    if stats["groups_unbeamed"] and not stats["groups_fully_beamed"] and not stats["groups_mixed"]:
        out.append(finding("beams-none", "info", f"{stats['groups_unbeamed']} beat groups have no beams. Some imports beam these by meter, but Sibelius left them flagged in the Brumel file. Compare with the source print: if it beams its eighths, run beaming-repair --scope all."))
    elif stats["groups_unbeamed"] and stats["groups_fully_beamed"]:
        sev = "warn" if software.lower().startswith(OMR_SOFTWARE) else "info"
        out.append(finding("beams-some-unbeamed", sev, f"{stats['groups_unbeamed']} beat groups unbeamed while {stats['groups_fully_beamed']} are beamed: syllabic style, or beams the scan missed."))
    if stats["groups_mixed"]:
        out.append(finding("beams-mixed", "warn", f"{stats['groups_mixed']} beat groups are partly beamed (some notes joined, others not). Sibelius keeps explicit beams, so these print wrong unless the source is syllabic. Compare with the source print; first: {', '.join(mixed[:5])}.", ", ".join(mixed[:5])))
    return out


STEP_INDEX = {"C": 0, "D": 1, "E": 2, "F": 3, "G": 4, "A": 5, "B": 6}
# Diatonic number (octave * 7 + step) of the pitch each clef sign names.
CLEF_REF = {"G": 4 * 7 + 4, "F": 3 * 7 + 3, "C": 4 * 7 + 0}


def parse_events(root: ET.Element) -> list[dict]:
    """Flatten the score into note/chord events with the context the newer checks need.

    Each event is one note or chord: part, measure, staff, voice, onset, dur
    (divisions), divisions, beat_len, bar_quarters, rest, grace, type, stem,
    beams, lyrics [(verse, text, syllabic)] and positions (diatonic steps of
    each pitch above the staff's middle line, negative below).
    """
    events: list[dict] = []
    for part in root.findall("part"):
        pid = part.get("id")
        divisions, beats, beat_type = 1, 4, 4
        clefs: dict[str, tuple[str, int, int]] = {}
        for m in part.findall("measure"):
            mnum = m.get("number")
            cursor = last_onset = 0
            cur: dict | None = None
            for el in m:
                if el.tag == "attributes":
                    if el.findtext("divisions"):
                        divisions = int(el.findtext("divisions"))
                    t = el.find("time")
                    if t is not None and t.findtext("beats", "").isdigit():
                        beats, beat_type = int(t.findtext("beats")), int(t.findtext("beat-type"))
                    for c in el.findall("clef"):
                        sign = (c.findtext("sign") or "G").strip()
                        line = (c.findtext("line") or "").strip()
                        line = int(line) if line.isdigit() else {"G": 2, "F": 4, "C": 3}.get(sign, 2)
                        oc = (c.findtext("clef-octave-change") or "0").strip()
                        clefs[c.get("number", "1")] = (sign, line, int(oc) if oc.lstrip("-").isdigit() else 0)
                elif el.tag == "backup":
                    cursor -= int(el.findtext("duration") or 0)
                elif el.tag == "forward":
                    cursor += int(el.findtext("duration") or 0)
                elif el.tag == "note":
                    is_chord = el.find("chord") is not None
                    grace = el.find("grace") is not None
                    dur = int(el.findtext("duration") or 0)
                    onset = last_onset if is_chord else cursor
                    staff = el.findtext("staff") or "1"
                    pos = None
                    pitch = el.find("pitch")
                    if pitch is not None and pitch.findtext("step") in STEP_INDEX and (pitch.findtext("octave") or "").strip().lstrip("-").isdigit():
                        sign, line, oc = clefs.get(staff, ("G", 2, 0))
                        middle = CLEF_REF.get(sign, 34) + (3 - line) * 2 + 7 * oc
                        pos = int(pitch.findtext("octave")) * 7 + STEP_INDEX[pitch.findtext("step")] - middle
                    if is_chord and cur is not None:
                        if pos is not None:
                            cur["positions"].append(pos)
                        continue
                    last_onset = onset
                    cursor += 0 if grace else dur
                    lyrics = []
                    for ly in el.findall("lyric"):
                        text = "".join(t.text or "" for t in ly.findall("text")).strip()
                        if text:
                            lyrics.append((ly.get("number", "1"), text, ly.findtext("syllabic") or "single"))
                    cur = {
                        "part": pid, "measure": mnum, "staff": staff, "voice": el.findtext("voice") or "1",
                        "onset": onset, "dur": dur, "divisions": divisions,
                        "beat_len": beat_length(divisions, beats, beat_type) or 1,
                        "bar_quarters": beats * 4 / beat_type,
                        "rest": el.find("rest") is not None, "grace": grace, "type": el.findtext("type"),
                        "stem": (el.findtext("stem") or "").strip(),
                        "beams": {b.get("number", "1"): b.text for b in el.findall("beam")},
                        "lyrics": lyrics, "positions": [pos] if pos is not None else [],
                    }
                    events.append(cur)
    return events


def _bars_text(bars: list[tuple[str, str]], limit: int = 5) -> str:
    return ", ".join(f"{p} bar {b}" for p, b in bars[:limit])


def check_lyrics_crowded(events: list[dict]) -> list[dict]:
    """Estimate lyric collisions (MusicXML has no layout; heuristic documented in SKILL.md)."""
    verses: dict[tuple, set] = {}
    bars: dict[tuple, list[dict]] = {}
    for e in events:
        if e["rest"] or e["grace"] or not e["lyrics"] or not e["dur"]:
            continue
        verses.setdefault((e["part"], e["staff"], e["voice"]), set()).update(n for n, _, _ in e["lyrics"])
        bars.setdefault((e["part"], e["staff"], e["voice"], e["measure"]), []).append(e)
    scored = []
    for (pid, staff, voice, mnum), evs in bars.items():
        stacked = len(verses[(pid, staff, voice)])
        limit = 5.5 if stacked >= 3 else 7.0
        total = crowded = 0
        for e in evs:
            chars = max(len(t) + (1 if syl in ("begin", "middle") else 0) for _, t, syl in e["lyrics"])
            total += chars
            if chars >= 4 and e["dur"] / e["divisions"] < 0.5:
                crowded += 1
        span = max(e["onset"] + e["dur"] for e in evs) / evs[0]["divisions"]  # OMR bars can outgrow the stated meter
        density = total / max(evs[0]["bar_quarters"], span)
        if crowded or density > limit:
            scored.append((crowded * 3 + density, density, crowded, stacked, pid, mnum))
    if not scored:
        return []
    scored.sort(key=lambda r: -r[0])
    worst = ", ".join(
        f"{pid} bar {mnum} ({d:.1f} chars/beat" + (f", {c} long syllable(s) on short notes" if c else "") + ")"
        for _, d, c, _, pid, mnum in scored[:5]
    )
    maxv = max(r[3] for r in scored)
    extra = f" {maxv} verses are stacked under one staff, so lines can also collide with the staff below in tight systems." if maxv >= 3 else ""
    return [finding("lyrics-crowded", "warn", f"{len(scored)} bars have lyrics likely to collide (estimated from text length and note length; compare with the source print).{extra} Worst: {worst}.", _bars_text([(r[4], r[5]) for r in scored]))]


def _expected_stem(positions: list[int]) -> str | None:
    """Direction for a note/chord/beamed group: the pitch farthest from the middle line decides."""
    if not positions:
        return None
    far = max(abs(p) for p in positions)
    if far == 0:
        return None  # on the middle line either direction is acceptable
    if far in positions and -far in positions:
        return None  # equally far above and below: either way is correct
    return "down" if far in positions else "up"


def check_stems(events: list[dict]) -> list[dict]:
    if not any(e["stem"] for e in events):
        return [finding("stems-wrong-direction", "info", "No <stem> elements (typical of editor exports): stem directions not checked; editors choose them on import.")]
    voices: dict[tuple, set] = {}
    for e in events:
        voices.setdefault((e["part"], e["measure"], e["staff"]), set()).add(e["voice"])
    units: dict[tuple, list[list[dict]]] = {}
    open_group: dict[tuple, list[dict] | None] = {}
    for e in events:
        if e["rest"] or e["grace"] or e["stem"] not in ("up", "down"):
            continue
        key = (e["part"], e["measure"], e["staff"], e["voice"])
        grp = open_group.get(key)
        b = e["beams"].get("1")
        if grp is not None:
            grp.append(e)
            if b in ("end", None):
                open_group[key] = None
        elif b == "begin":
            grp = [e]
            units.setdefault(key, []).append(grp)
            open_group[key] = grp
        else:
            units.setdefault(key, []).append([e])
    checked = wrong = 0
    bad: list[tuple[str, str]] = []
    # A staff whose stems all point one way (at least 12 of them, every bar single-voice)
    # is a deliberate open-score style (stem direction names the voice), not OMR noise.
    dirs: dict[tuple, Counter] = {}
    for (pid, mnum, staff, voice), groups in units.items():
        if len(voices[(pid, mnum, staff)]) == 1:
            dirs.setdefault((pid, staff), Counter()).update(g[0]["stem"] for g in groups)
    uniform = {k for k, c in dirs.items() if len(c) == 1 and sum(c.values()) >= 12}
    skipped = sorted(f"{p}/staff {st}" for p, st in uniform)
    for (pid, mnum, staff, voice), groups in units.items():
        if (pid, staff) in uniform:
            continue
        vs = sorted(voices[(pid, mnum, staff)], key=lambda v: (len(v), v))
        for g in groups:
            if len(vs) == 1:
                want = _expected_stem([p for e in g for p in e["positions"]])
            elif len(vs) == 2:
                want = "up" if voice == vs[0] else "down"
            else:
                want = None
            if want is None:
                continue
            checked += 1
            if g[0]["stem"] != want:
                wrong += 1
                if (pid, mnum) not in bad:
                    bad.append((pid, mnum))
    note = f" Skipped staves whose stems all point one way (voice-by-stem style): {', '.join(skipped)}." if skipped else ""
    if not checked:
        return [finding("stems-wrong-direction", "info", f"Stems not checked.{note}")] if skipped else []
    if wrong >= 3 and wrong / checked >= 0.05:
        return [finding("stems-wrong-direction", "warn", f"{wrong} of {checked} notes or beamed groups have a stem against the usual rule (one voice on the staff: down on or above the middle line, up below; two voices: voice 1 up, voice 2 down; a beamed group by its note farthest from the middle line). Likely OMR errors; compare with the source print.{note} First: {_bars_text(bad)}.", _bars_text(bad))]
    return [finding("stems-wrong-direction", "info", f"Stems checked: {wrong} of {checked} differ from the usual rule, too few to matter.{note}")]


def check_beam_style(events: list[dict]) -> list[dict]:
    """Detect syllabic versus modern (by-beat) beaming from the beamed groups."""
    by_voice: dict[tuple, list[dict]] = {}
    for e in events:
        if e["rest"] or e["grace"] or e["type"] not in BEAMABLE:
            continue
        by_voice.setdefault((e["part"], e["measure"], e["staff"], e["voice"]), []).append(e)
    beamed = modern = syllabic = 0
    for notes in by_voice.values():
        groups: dict[int, list[dict]] = {}
        for n in notes:
            groups.setdefault(n["onset"] // n["beat_len"], []).append(n)
        for g in groups.values():
            joins = [
                a["beams"].get("1") in ("begin", "continue") and b["beams"].get("1") in ("continue", "end")
                for a, b in zip(g, g[1:])
            ]
            beamed += any(joins)
            for (a, b), j in zip(zip(g, g[1:]), joins):
                if b["lyrics"]:
                    modern += j
                    syllabic += not j
    if beamed < 6:
        return [finding("beam-style", "info", f"Beam style undetermined: only {beamed} beamed groups (need about 6). Look at the source print before choosing beaming-repair --style.")]
    if modern + syllabic == 0:
        return [finding("beam-style", "info", f"Beam style undetermined: {beamed} beamed groups, but none has a new syllable inside a beat to tell the styles apart.")]
    counts = f"{beamed} beamed groups; {modern} joined note pairs start a new syllable, {syllabic} such pairs are broken"
    share = modern / (modern + syllabic)
    if share >= 0.7:
        return [finding("beam-style", "info", f"Beam style looks modern (beamed by the beat regardless of syllables): {counts}. Use beaming-repair --style meter.")]
    if share <= 0.3:
        return [finding("beam-style", "info", f"Beam style looks syllabic (beams break where a new syllable starts): {counts}. Use beaming-repair --style syllabic --scope all. Beams the scan missed also count as broken pairs, so confirm with the source print.")]
    return [finding("beam-style", "info", f"Beam style undetermined (mixed evidence): {counts}. Look at the source print before choosing beaming-repair --style.")]


def check_text(root: ET.Element) -> list[dict]:
    out, words = [], Counter()
    harmony = len(root.findall(".//harmony"))
    for d in root.iter("direction"):
        for w in d.iter("words"):
            t = (w.text or "").strip()
            if t:
                words[t] += 1
    chordish = {t: n for t, n in words.items() if CHORD_LIKE.match(t)}
    if chordish and not harmony:
        out.append(finding("chords-as-text", "warn", f"{sum(chordish.values())} chord-symbol-like words are plain text, not <harmony> (e.g. {', '.join(sorted(chordish)[:6])}). Check capitalisation (c vs C) and convert to chord symbols."))
    lowercase = [t for t in chordish if t[0].islower()]
    if lowercase:
        out.append(finding("chords-lowercase", "warn", f"Lowercase chord roots, probably misread capitals: {', '.join(sorted(lowercase)[:8])}."))
    return out


def check_lyrics(root: ET.Element) -> list[dict]:
    syll = Counter()
    for ly in root.iter("lyric"):
        syll[ly.findtext("syllabic") or "none"] += 1
    total = sum(syll.values())
    if total >= 30 and not syll["begin"] and not syll["middle"]:
        return [finding("lyrics-unjoined", "warn", f"{total} lyric syllables, none joined into words (all single); hyphens will be missing. Use the lyric-hyphenation skill.")]
    return []


def check_layout(root: ET.Element) -> list[dict]:
    out, systems, pages, clefs, keys, padding, measures = 0, 0, 0, 0, 0, 0, 0
    for part in root.findall("part"):
        for i, m in enumerate(part.findall("measure")):
            measures += 1
            for p in m.findall("print"):
                systems += p.get("new-system") == "yes"
                pages += p.get("new-page") == "yes"
            if i > 0:
                clefs += len(m.findall("attributes/clef"))
                keys += len(m.findall("attributes/key"))
            notes = m.findall("note")
            if notes and all(n.find("rest") is not None for n in notes) and all(n.find("rest").get("measure") == "yes" for n in notes):
                padding += 1
    res = []
    if not systems and not pages:
        res.append(finding("layout-no-breaks", "info", "No system or page breaks; the editor will lay the score out. Choose breaks by phrase after import."))
    if measures and padding / measures > 0.5:
        res.append(finding("padding-bars", "error", f"{padding} of {measures} bars are whole-bar rests: likely OMR padding. Use omr-score-repair."))
    if clefs > 4:
        res.append(finding("clefs-after-bar1", "warn", f"{clefs} clef changes after bar 1; check for redundant clefs (omr-score-repair)."))
    return res


def _tempo_directions(root: ET.Element) -> list[tuple[tuple[int, Fraction], ET.Element]]:
    """((bar, onset in quarters), direction) for each direction with a metronome or a <sound tempo>."""
    out = []
    for part in root.findall("part"):
        divisions = 1
        for bar, measure in enumerate(part.findall("measure"), start=1):
            pos = 0
            for child in measure:
                if child.tag == "attributes" and (child.findtext("divisions") or "").strip().isdigit():
                    divisions = int(child.findtext("divisions")) or divisions
                elif child.tag == "direction":
                    sound = child.find("sound")
                    if (sound is not None and sound.get("tempo") is not None) or child.find("direction-type/metronome") is not None:
                        out.append(((bar, Fraction(pos, divisions)), child))
                elif child.tag in ("note", "forward", "backup"):
                    if child.find("chord") is not None or child.find("grace") is not None:
                        continue
                    dur = int(child.findtext("duration") or 0) if (child.findtext("duration") or "0").strip().isdigit() else 0
                    pos += -dur if child.tag == "backup" else dur
    return out


def check_tempo(root: ET.Element) -> list[dict]:
    """Tempo directions Sibelius prints differently from what the file says (Nelson Carol Book run)."""
    out = []
    found = _tempo_directions(root)
    seen = Counter(key for key, _ in found)
    twice = sorted(key for key, n in seen.items() if n > 1)
    if twice:
        where = ", ".join(f"bar {b}" + (f" +{o}" if o else "") for b, o in twice[:5])
        out.append(finding("tempo-twice", "warn", f"More than one tempo direction at the same place ({where}); the editor draws each one. Use score-metadata-repair --tempo once."))
    unprinted = []
    for (bar, _), d in found:
        sound = d.find("sound")
        if sound is not None and sound.get("tempo") is not None and d.find("direction-type/metronome") is None:
            words = " ".join((w.text or "").strip() for w in d.findall("direction-type/words")).strip()
            unprinted.append(f"bar {bar}: " + (f"{words!r} + " if words else "") + f"sound tempo {sound.get('tempo')}")
    if unprinted:
        out.append(finding("tempo-sound-printed", "warn", f"A <sound tempo> inside a direction with no metronome: Sibelius prints it as 'q = N' (after any words), which the print may not have ({'; '.join(unprinted[:4])}). Use score-metadata-repair --tempo once (or none if the print has no tempo)."))
    return out


def check_hidden_time(root: ET.Element) -> list[dict]:
    bars = sorted({n for part in root.findall("part") for n, m in enumerate(part.findall("measure"), start=1)
                   if any(t.get("print-object") == "no" for t in m.iter("time"))})
    if not bars:
        return []
    return [finding("time-hidden", "info", f"{len(bars)} bar(s) with a hidden time signature (print-object=\"no\"), from bar {bars[0]}; Sibelius ignores this and shows them. After import run sibelius-cli hide-time-signatures --musicxml FILE.")]


VERSE_NUMBER = re.compile(r"^\d+\.?$")


def _voice_ends(events: list[dict]) -> dict[tuple[str, str], dict[tuple[str, str], int]]:
    """(part, bar) -> {(staff, voice): where the voice's last note or rest ends}, in divisions."""
    ends: dict[tuple[str, str], dict[tuple[str, str], int]] = {}
    for e in events:
        bar = ends.setdefault((e["part"], e["measure"]), {})
        key = (e["staff"], e["voice"])
        bar[key] = max(bar.get(key, 0), e["onset"] + (0 if e["grace"] else e["dur"]))
    return ends


def check_bar_sums(root: ET.Element, events: list[dict]) -> list[dict]:
    """OMR bar faults: an empty first bar, an invented or padded pickup, and voices short of the meter.

    Uses the per-voice onsets from parse_events. Rules and the cases behind
    them are in references/bar-checks.md.
    """
    if not any(not e["rest"] and not e["grace"] for e in events):
        return [finding("score-empty", "error", "The score has no notes: the scan returned an empty result. Scan again (Halbestunde: clean_pdf.py --pad 100).")]
    ends = _voice_ends(events)
    full_len = {(e["part"], e["measure"]): round(e["bar_quarters"] * e["divisions"]) for e in events}
    sounding = {(e["part"], e["measure"]) for e in events if not e["rest"] and not e["grace"]}
    out, pickup, short = [], [], []
    parts = [(p.get("id"), [m for m in p.findall("measure")]) for p in root.findall("part")]
    firsts = [(pid, ms[0].get("number")) for pid, ms in parts if ms]
    if firsts and not any(f in sounding for f in firsts):
        where = _bars_text(firsts)
        out.append(finding("bar1-empty", "warn", f"Bar 1 holds no notes in any part ({where}): usually an empty leading bar the scan added. Delete it unless the print opens with a rest bar.", where))
    for pid, measures in parts:
        if not measures:
            continue
        first, last = measures[0].get("number"), measures[-1].get("number")
        if (pid, first) not in sounding:
            continue
        bar1 = ends.get((pid, first), {})
        bar1_events = [e for e in events if e["part"] == pid and e["measure"] == first and not e["grace"]]
        full = full_len[(pid, first)]
        length = max(bar1.values())
        last_len = max(ends.get((pid, last), {}).values(), default=full) if last != first else full
        reasons = []
        if length > full:
            reasons.append(f"a voice lasts {length} of {full} divisions")
        if length < full:
            if len(set(bar1.values())) > 1:
                reasons.append(f"its voices last {sorted(set(bar1.values()))} of {full} divisions")
            opening: dict[tuple[str, str], dict] = {}
            for e in bar1_events:
                key = (e["staff"], e["voice"])
                if key not in opening or e["onset"] < opening[key]["onset"]:
                    opening[key] = e
            leading = sorted(v for (_, v), e in opening.items() if e["rest"])
            if leading:
                reasons.append(f"voice {', '.join(leading)} opens with a rest")
            if last_len < full and length + last_len != full:
                reasons.append(f"it lasts {length} and the last bar {last_len}, which do not add up to a bar of {full}")
        elif last_len < full:
            reasons.append(f"it is a full bar but the last bar lasts {last_len} of {full}, so the print probably opens with a pickup of {full - last_len}")
        if any(e["lyrics"] and all(VERSE_NUMBER.match(t) for _, t, _ in e["lyrics"]) for e in bar1_events):
            reasons.append("a note carries only a verse number ('1.') as its lyric")
        if reasons:
            pickup.append(f"{pid} bar {first}: {'; '.join(reasons)}")
        for i, m in enumerate(measures[1:], start=1):
            mnum = m.get("number")
            voices = ends.get((pid, mnum))
            # a bar split in two (implicit="yes" on one half, as Dorico writes) is short on purpose
            split = any(n.get("implicit") == "yes" for n in measures[i - 1:i + 2])
            if not voices or split or m.find("forward") is not None:
                continue
            full = full_len[(pid, mnum)]
            if max(voices.values()) >= full or mnum != last:
                low = sorted(f"{s}/{v}" for (s, v), end in voices.items() if end < full)
                if low:
                    short.append((pid, mnum, ", ".join(low)))
    if pickup:
        out.append(finding("bar1-pickup-suspect", "warn", "Bar 1 does not look like the print's first bar or pickup: " + " | ".join(pickup[:5]) + ". The scan may have invented notes from verse numbers or flecks, padded a pickup with rests, or read a pickup as a full bar; compare with the print.", "; ".join(pickup[:5])))
    if short:
        where = ", ".join(f"{p} bar {b} (staff/voice {v})" for p, b, v in short[:5])
        out.append(finding("bars-short", "warn", f"{len(short)} bars where a voice stops before the end of the bar, usually rests the scan dropped (in the last bar, a rest may have been added to another voice instead): {where}. A mid-piece pickup at a repeat is fine.", where))
    return out


def audit(root: ET.Element) -> list[dict]:
    software = (root.findtext(".//encoding/software") or "")
    findings = check_metadata(root) + check_credits_split(root) + check_parts(root) + check_beams(root, software) + check_text(root) + check_lyrics(root) + check_layout(root) + check_tempo(root) + check_hidden_time(root)
    events = parse_events(root)
    return findings + check_bar_sums(root, events) + check_lyrics_crowded(events) + check_stems(events) + check_beam_style(events)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("score")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        root = load(Path(args.score))
    except Exception as exc:  # unreadable or not MusicXML
        print(f"error: cannot read {args.score}: {exc}", file=sys.stderr)
        return 2
    findings = audit(root)
    if args.json:
        print(json.dumps(findings, indent=2))
    else:
        order = {"error": 0, "warn": 1, "info": 2}
        for f in sorted(findings, key=lambda f: order[f["severity"]]):
            print(f"[{f['severity']:5}] {f['code']}: {f['message']}")
        if not findings:
            print("No findings.")
    return 1 if any(f["severity"] == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
