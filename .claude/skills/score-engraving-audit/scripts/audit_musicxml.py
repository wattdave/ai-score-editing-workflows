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
        out.append(finding("beams-none", "info", f"{stats['groups_unbeamed']} beat groups have no beams. Sibelius, Dorico and MuseScore beam these by meter on import (tested in Sibelius), so this is fine for a beamless OMR file."))
    elif stats["groups_unbeamed"] and stats["groups_fully_beamed"]:
        sev = "warn" if software.lower().startswith(OMR_SOFTWARE) else "info"
        out.append(finding("beams-some-unbeamed", sev, f"{stats['groups_unbeamed']} beat groups unbeamed while {stats['groups_fully_beamed']} are beamed: syllabic style, or beams the scan missed."))
    if stats["groups_mixed"]:
        out.append(finding("beams-mixed", "warn", f"{stats['groups_mixed']} beat groups are partly beamed (some notes joined, others not). Sibelius keeps explicit beams, so these print wrong unless the source is syllabic. Compare with the source print; first: {', '.join(mixed[:5])}.", ", ".join(mixed[:5])))
    return out


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


def audit(root: ET.Element) -> list[dict]:
    software = (root.findtext(".//encoding/software") or "")
    findings = check_metadata(root) + check_parts(root) + check_beams(root, software) + check_text(root) + check_lyrics(root) + check_layout(root)
    return findings


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
