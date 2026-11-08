#!/usr/bin/env python3
"""Fix metadata defects in a MusicXML file before it is imported into an editor.

Standard library only, so the skill runs without the rest of this repository.

Usage:
    fix_metadata.py IN OUT [--title T] [--subtitle S] [--composer C] [--arranger A]
        [--lyricist L] [--rights-template public-domain|in-copyright|own-arrangement|verbatim]
        [--source S] [--notice N] [--year Y] [--name NAME]
        [--parts "Soprano,Alto,Tenor,Bass"] [--normalize-title] [--merge-credits]
        [--tempo once|none]

IN may be .xml, .musicxml or .mxl; OUT is plain MusicXML. Only metadata is
touched (title, creators, rights, credits, part names and abbreviations, and
with --tempo the tempo directions); notes, lyrics and layout are copied unchanged, and so is the XML declaration
and DOCTYPE. Nothing is invented: a composer, arranger, lyricist or rights
line is written only when you pass it.

Exit status: 0 on success, 2 on bad arguments or an unreadable file.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "from", "in", "nor", "of", "on", "or", "the", "to", "up", "with"}
GENERIC_PART = re.compile(r"^(voice|staff|part|track|instrument)\s*\d*$", re.I)
ABBREVIATIONS = {"soprano": "S.", "alto": "A.", "tenor": "T.", "bass": "B.", "piano": "Pno.", "treble": "Tr."}
LIST_NUMBER = re.compile(r"^\s*\d+\s*[.)]\s*")
DEFAULT_HEADER = '<?xml version="1.0" encoding="UTF-8"?>\n'
ENCODING_ATTR = re.compile(r'(<\?xml[^>]*encoding=)(["\'])[^"\']*\2')


# ---------------------------------------------------------------- reading ---

def read_text(path: Path) -> str:
    if path.suffix.lower() == ".mxl":
        with zipfile.ZipFile(path) as z:
            name = next(n for n in z.namelist() if n.endswith((".xml", ".musicxml")) and not n.startswith("META-INF"))
            data = z.read(name)
    else:
        data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def header_of(text: str) -> str:
    """Everything before <score-partwise: XML declaration, comments, DOCTYPE."""
    i = text.find("<score-partwise")
    return text[:i] if i > 0 else ""


def parse(text: str) -> ET.Element:
    # Keep comments; ElementTree keeps whitespace text and tails already.
    # We hold decoded text, so any declared encoding is rewritten to utf-8.
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    parser.feed(ENCODING_ATTR.sub(r'\1"utf-8"', text, count=1).encode("utf-8"))
    return parser.close()


# ----------------------------------------------------------------- titles ---

def _cap_word(word: str) -> str:
    # "it's" -> "It's", "o'er" -> "O'er"; keep leading digits and punctuation.
    for i, ch in enumerate(word):
        if ch.isalpha():
            return word[:i] + ch.upper() + word[i + 1:].lower()
    return word


def title_case(s: str) -> str:
    tokens = s.split(" ")
    out = []
    for i, tok in enumerate(tokens):
        parts = tok.split("-")
        fixed = []
        for j, p in enumerate(parts):
            edge = (i == 0 and j == 0) or (i == len(tokens) - 1 and j == len(parts) - 1)
            bare = re.sub(r"[^\w']", "", p).lower()
            fixed.append(p.lower() if bare in SMALL_WORDS and not edge else _cap_word(p))
        out.append("-".join(fixed))
    return " ".join(out)


def normalize_title(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    s = LIST_NUMBER.sub("", s)
    if any(c.isalpha() for c in s) and (s == s.lower() or (s == s.upper() and len(s) > 3)):
        s = title_case(s)
    return s


# ------------------------------------------------------------ tree helpers ---

def insert_child(parent: ET.Element, index: int, child: ET.Element) -> None:
    """Insert child at index, copying the indentation style of the parent."""
    kids = list(parent)
    ws = parent.text if parent.text and not parent.text.strip() else "\n"
    if not kids:
        parent.text = ws
        child.tail = ws[:-2] if len(ws) > 2 else "\n"
        parent.append(child)
    elif index >= len(kids):
        last = kids[-1]
        child.tail = last.tail  # closing whitespace moves to the new last child
        last.tail = ws if not kids[-2:-1] else kids[-2].tail
        parent.append(child)
    else:
        parent.insert(index, child)
        child.tail = ws if index == 0 else kids[index - 1].tail


def top_index(root: ET.Element, before: tuple[str, ...]) -> int:
    for i, ch in enumerate(list(root)):
        if ch.tag in before:
            return i
    return len(root)


# ------------------------------------------------------------- part names ---

def abbreviate(name: str) -> str:
    name = name.strip()
    m = re.fullmatch(r"([A-Za-z]+)\s*(\d+)?", name)
    if m and m.group(1).lower() in ABBREVIATIONS:
        return ABBREVIATIONS[m.group(1).lower()] + (f" {m.group(2)}" if m.group(2) else "")
    # Voice-letter names for a choral reduction ("S A", "T B", "S", "A & B") abbreviate to themselves.
    if re.fullmatch(r"[A-Za-z](\s*[&/,]?\s*[A-Za-z])*", name) and len(re.sub(r"[^A-Za-z]", "", name)) <= 4 and name == name.upper():
        return name
    letters = re.sub(r"[^A-Za-z]", "", name)
    return (letters[:3] or name[:3]).capitalize() + "."


def _set_display(sp: ET.Element, tag: str, text: str) -> None:
    disp = sp.find(tag)
    if disp is not None:
        dt = disp.find("display-text")
        if dt is not None:
            dt.text = text


def _set_abbreviation(sp: ET.Element, text: str) -> None:
    ab = sp.find("part-abbreviation")
    if ab is None:
        idx = 0
        for i, ch in enumerate(list(sp)):
            if ch.tag in ("part-name", "part-name-display"):
                idx = i + 1
        ab = ET.Element("part-abbreviation")
        insert_child(sp, idx, ab)
    ab.text = text
    _set_display(sp, "part-abbreviation-display", text)


def rename_part(sp: ET.Element, name: str | None, abbrev: str, old_name: str) -> None:
    pn = sp.find("part-name")
    if name is not None and pn is not None:
        pn.text = name
        pn.attrib.pop("print-object", None)  # a named part should print its name
        _set_display(sp, "part-name-display", name)
        for si in sp.findall("score-instrument"):
            iname = si.find("instrument-name")
            cur = (iname.text or "").strip() if iname is not None else ""
            if iname is not None and (not cur or GENERIC_PART.match(cur) or cur == old_name):
                iname.text = name
            iab = si.find("instrument-abbreviation")
            if iab is not None:
                iab.text = abbrev
    _set_abbreviation(sp, abbrev)


def fix_parts(root: ET.Element, names: list[str] | None) -> list[str]:
    log = []
    for i, sp in enumerate(root.findall("part-list/score-part")):
        pn = sp.find("part-name")
        old = (pn.text or "").strip() if pn is not None else ""
        if names is not None and i < len(names):
            rename_part(sp, names[i], abbreviate(names[i]), old)
            log.append(f"{sp.get('id')}: {old!r} -> {names[i]!r} ({abbreviate(names[i])})")
        elif old and not GENERIC_PART.match(old) and not (sp.findtext("part-abbreviation") or "").strip():
            rename_part(sp, None, abbreviate(old), old)
            log.append(f"{sp.get('id')}: abbreviation {abbreviate(old)!r} added")
    return log


# --------------------------------------------------------------- metadata ---

def rights_text(template: str, source: str | None, notice: str | None, year: str | None, name: str | None) -> str:
    if template == "public-domain":
        if not source:
            raise ValueError("--rights-template public-domain needs --source")
        return f"Public domain. Transcribed from {source.strip()} for rehearsal use."
    if template == "verbatim":
        if not notice:
            raise ValueError("--rights-template verbatim needs --notice (the copyright line exactly as printed)")
        return notice.strip()
    if template == "in-copyright":
        if not notice:
            raise ValueError("--rights-template in-copyright needs --notice (the original copyright notice)")
        return f"{notice.strip()} Transcribed for rehearsal use only. Not for distribution."
    if not year or not name:
        raise ValueError("--rights-template own-arrangement needs --year and --name")
    return f"Arrangement © {year.strip()} {name.strip()}."


def ensure_identification(root: ET.Element) -> ET.Element:
    ident = root.find("identification")
    if ident is None:
        ident = ET.Element("identification")
        insert_child(root, top_index(root, ("defaults", "credit", "part-list")), ident)
    return ident


def set_creator(root: ET.Element, kind: str, value: str) -> None:
    ident = ensure_identification(root)
    existing = [c for c in ident.findall("creator") if c.get("type") == kind]
    if existing:
        existing[0].text = value
        return
    last = max((i for i, c in enumerate(list(ident)) if c.tag == "creator"), default=-1)
    el = ET.Element("creator", {"type": kind})
    el.text = value
    insert_child(ident, last + 1, el)  # creators come first in <identification>


def set_rights(root: ET.Element, text: str) -> None:
    ident = ensure_identification(root)
    rights = ident.findall("rights")
    if rights:
        rights[0].text = text
        for extra in rights[1:]:
            ident.remove(extra)
        return
    idx = 0
    for i, c in enumerate(list(ident)):
        if c.tag in ("creator", "rights"):
            idx = i + 1
    el = ET.Element("rights")
    el.text = text
    insert_child(ident, idx, el)


def set_title(root: ET.Element, title: str) -> str:
    """Set work-title and movement-title (whichever exist; work-title if none)."""
    old = root.findtext("work/work-title") or root.findtext("movement-title") or ""
    found = False
    for path in ("work/work-title", "movement-title"):
        el = root.find(path)
        if el is not None:
            el.text = title
            found = True
    if not found:
        work = root.find("work")
        if work is None:
            work = ET.Element("work")
            insert_child(root, 0, work)
        wt = ET.Element("work-title")
        wt.text = title
        insert_child(work, len(work), wt)
    sync_title_credit(root, old, title)
    return old


def sync_title_credit(root: ET.Element, old: str, new: str) -> None:
    """Keep an existing credit that repeats the old title in step."""
    if not old.strip():
        return
    for cw in root.findall("credit/credit-words"):
        if (cw.text or "").strip().lower() == old.strip().lower():
            cw.text = new


def _page(root: ET.Element, tag: str, default: float) -> float:
    try:
        return float(root.findtext(f"defaults/page-layout/{tag}") or default)
    except ValueError:
        return default


def add_credits(root: ET.Element, subtitle: str | None = None) -> list[str]:
    """Add title/subtitle/composer/arranger/lyricist credits when the score has none."""
    if root.find("credit") is not None:
        return []
    width, height = _page(root, "page-width", 1233), _page(root, "page-height", 1600)
    title = (root.findtext("work/work-title") or root.findtext("movement-title") or "").strip()
    people = {c.get("type"): (c.text or "").strip() for c in root.findall("identification/creator")}
    rows = []
    if title:
        rows.append(("title", title, width / 2, height - 100, "center", 24))
    if subtitle:
        rows.append(("subtitle", subtitle, width / 2, height - 135, "center", 14))
    if people.get("lyricist"):
        rows.append(("lyricist", people["lyricist"], 80, height - 150, "left", 12))
    if people.get("composer"):
        rows.append(("composer", people["composer"], width - 80, height - 150, "right", 12))
    if people.get("arranger"):
        rows.append(("arranger", people["arranger"], width - 80, height - 175, "right", 12))
    idx = top_index(root, ("part-list",))
    for ctype, text, x, y, just, size in rows:
        credit = ET.Element("credit", {"page": "1"})
        ET.SubElement(credit, "credit-type").text = ctype
        cw = ET.SubElement(credit, "credit-words", {
            "default-x": f"{x:g}", "default-y": f"{y:g}", "justify": just,
            "valign": "top", "font-size": str(size),
        })
        cw.text = text
        credit.text = "\n    "
        kids = list(credit)
        for i, k in enumerate(kids):
            k.tail = "\n    " if i < len(kids) - 1 else "\n  "
        insert_child(root, idx, credit)
        idx += 1
    return [r[0] for r in rows]


# ---------------------------------------------------------- merge credits ---
# OMR and PDF readers write one <credit> per printed line, so a two-line
# composer/arranger block or a multi-line footer arrives as separate items and
# Sibelius keeps only one of them (or imports each as its own text). These
# helpers find runs of lines that belong to one block and join them.

CREATOR_TYPES = {"composer", "arranger", "lyricist", "poet", "translator"}
NEVER_MERGE = {"title", "subtitle", "page number", "part name"}
SAME_STYLE = ("justify", "halign", "valign", "font-size", "font-family", "font-style", "font-weight")
X_TOLERANCE = 2.0  # tenths
GAP_FACTOR = 3.0  # a line gap above 3 x font size (tenths vs points, generous) starts a new block


def _num(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _credit_line(credit: ET.Element) -> dict | None:
    """A credit that is one plain positioned line of text, or None."""
    kids = [k for k in credit if isinstance(k.tag, str)]
    words = [k for k in kids if k.tag == "credit-words"]
    if len(words) != 1 or any(k.tag not in ("credit-type", "credit-words") for k in kids):
        return None
    cw = words[0]
    types = [(t.text or "").strip().lower() for t in credit.findall("credit-type")]
    x, y = _num(cw.get("default-x")), _num(cw.get("default-y"))
    text = (cw.text or "").strip()
    if x is None or y is None or not text or len(cw) or set(types) & NEVER_MERGE:
        return None
    kind = "creator" if types and set(types) <= CREATOR_TYPES else "|".join(sorted(set(types) - {"rights"})) or "text"
    return {"credit": credit, "words": cw, "types": types, "x": x, "y": y, "text": text, "kind": kind,
            "page": credit.get("page", "1"), "style": tuple(cw.get(a) for a in SAME_STYLE)}


def credit_blocks(root: ET.Element) -> list[list[dict]]:
    """Runs of two or more credit lines that read as one block, top line first.

    Lines join when they are on the same page, have the same alignment and
    font, start at the same x, are close together vertically, and are both
    creator credits (composer/arranger/lyricist) or both plain/rights text.
    Titles, subtitles and credits with images or several words are left alone.
    """
    lines = [ln for ln in (_credit_line(c) for c in root.findall("credit")) if ln]
    groups: dict[tuple, list[dict]] = {}
    for ln in lines:
        groups.setdefault((ln["page"], ln["style"], ln["kind"]), []).append(ln)
    blocks = []
    for group in groups.values():
        group.sort(key=lambda ln: (round(ln["x"]), -ln["y"]))
        run: list[dict] = []
        for ln in group:
            if run:
                prev = run[-1]
                size = _num(prev["words"].get("font-size")) or 12.0
                if abs(ln["x"] - prev["x"]) > X_TOLERANCE or not 0 < prev["y"] - ln["y"] <= GAP_FACTOR * size:
                    if len(run) > 1:
                        blocks.append(run)
                    run = []
            run.append(ln)
        if len(run) > 1:
            blocks.append(run)
    return sorted(blocks, key=lambda b: (b[0]["page"], -b[0]["y"]))


def merge_credits(root: ET.Element) -> list[str]:
    """Join each block into its first credit, lines separated by newlines."""
    log = []
    for block in credit_blocks(root):
        first = block[0]
        first["words"].text = "\n".join(ln["text"] for ln in block)
        have = set(first["types"])
        for ln in block[1:]:
            for t in ln["types"]:
                if t not in have:  # keep every credit-type (MusicXML allows several), first one leads
                    have.add(t)
                    idx = max((i + 1 for i, k in enumerate(list(first["credit"])) if k.tag == "credit-type"), default=0)
                    el = ET.Element("credit-type")
                    el.text = t
                    insert_child(first["credit"], idx, el)
            root.remove(ln["credit"])
        label = "/".join(dict.fromkeys(t for ln in block for t in ln["types"])) or "text"
        log.append(f"credits merged ({label}, page {first['page']}, {first['words'].get('justify') or first['words'].get('halign') or 'left'}): "
                   + " | ".join(ln["text"] for ln in block))
    return log


# ------------------------------------------------------------------ tempo ---
# What Sibelius did with tempo directions in the Nelson Carol Book run:
#  - <direction><sound tempo="84"/></direction> with no printed direction-type
#    imported as tempo text "q = 84" (Away in a Manger, We Three Kings, O Come
#    All Ye Faithful); the print has no tempo.
#  - <words>Langsam</words> + <sound tempo="78"/> imported as "Langsam q = 78"
#    (Stille Nacht); the print has the word only.
#  - <metronome> + <sound tempo> imported as one correct tempo text.
# So a <sound tempo> stays (playback) but moves out of any direction that has
# no <metronome>, to a measure-level <sound> at the same place (valid
# MusicXML). --tempo none also drops the printed metronome and words.

TEMPO_MODES = ("none", "once")
PRINTED_TEMPO = ("metronome", "words")


def _tempo_sound(direction: ET.Element) -> ET.Element | None:
    sound = direction.find("sound")
    return sound if sound is not None and sound.get("tempo") is not None else None


def _is_tempo(direction: ET.Element) -> bool:
    return _tempo_sound(direction) is not None or direction.find("direction-type/metronome") is not None


def _divisions(attributes: ET.Element, current: int) -> int:
    try:
        return int(attributes.findtext("divisions") or current) or current
    except ValueError:
        return current


def tempo_directions(root: ET.Element) -> list[tuple[ET.Element, ET.Element, tuple[int, Fraction]]]:
    """(measure, direction, (bar, onset in quarters)) for every tempo direction, parts in order."""
    out = []
    for part in root.findall("part"):
        divisions = 1
        for bar, measure in enumerate(part.findall("measure"), start=1):
            pos = 0
            for child in measure:
                if child.tag == "attributes":
                    divisions = _divisions(child, divisions)
                elif child.tag == "direction" and _is_tempo(child):
                    out.append((measure, child, (bar, Fraction(pos, divisions))))
                elif child.tag in ("note", "forward", "backup"):
                    if child.tag == "note" and (child.find("chord") is not None or child.find("grace") is not None):
                        continue
                    try:
                        dur = int(child.findtext("duration") or 0)
                    except ValueError:
                        dur = 0
                    pos += -dur if child.tag == "backup" else dur
    return out


def _signature(dt: ET.Element) -> str:
    return re.sub(r"\s+", "", ET.tostring(dt, encoding="unicode").split(">", 1)[-1])


def _describe(direction: ET.Element) -> str:
    bits = []
    for dt in direction.findall("direction-type"):
        m = dt.find("metronome")
        if m is not None:
            bits.append(f"{m.findtext('beat-unit') or '?'}{'.' * len(m.findall('beat-unit-dot'))} = {m.findtext('per-minute') or '?'}")
        for w in dt.findall("words"):
            bits.append((w.text or "").strip())
    sound = _tempo_sound(direction)
    if sound is not None:
        bits.append(f"sound tempo {sound.get('tempo')}")
    return ", ".join(b for b in bits if b) or "empty"


def _detach_sound(measure: ET.Element, direction: ET.Element) -> None:
    """Move the direction's <sound> to a measure-level <sound> just before it; drop an empty direction."""
    sound = direction.find("sound")
    direction.remove(sound)
    idx = list(measure).index(direction)
    sound.tail = direction.tail
    measure.insert(idx, sound)
    if direction.find("direction-type") is None:
        measure.remove(direction)


def fix_tempo(root: ET.Element, mode: str) -> list[str]:
    """Write each tempo once; keep <sound tempo> but out of directions without a metronome.

    once: tempo directions at the same bar and beat in several parts (or
    several in one part) become one, in the first part, merging any printed
    marks that differ. none: the print has no tempo, so the metronome and
    words of tempo directions go as well.
    """
    log: list[str] = []
    groups: dict[tuple[int, Fraction], list[tuple[ET.Element, ET.Element]]] = {}
    for measure, direction, key in tempo_directions(root):
        groups.setdefault(key, []).append((measure, direction))
    for (bar, onset), items in groups.items():
        where = f"bar {bar}" + (f" beat +{onset}" if onset else "")
        keep_m, keep = next(((m, d) for m, d in items if d.find("direction-type") is not None), items[0])
        if len(items) > 1:
            have = {_signature(dt) for dt in keep.findall("direction-type")}
            for m, d in items:
                if d is keep:
                    continue
                for dt in d.findall("direction-type"):
                    if _signature(dt) not in have:
                        have.add(_signature(dt))
                        keep.insert(max((i + 1 for i, k in enumerate(keep) if k.tag == "direction-type"), default=0), dt)
                if _tempo_sound(keep) is None and _tempo_sound(d) is not None:
                    snd = d.find("sound")
                    d.remove(snd)
                    keep.append(snd)
                m.remove(d)
            log.append(f"tempo {where}: {len(items)} tempo directions -> 1 ({_describe(keep)})")
        if mode == "none":
            dropped = []
            for dt in keep.findall("direction-type"):
                if any(k.tag in PRINTED_TEMPO for k in dt):
                    dropped.append(_describe_dt(dt))
                    keep.remove(dt)
            if dropped:
                log.append(f"tempo {where}: printed tempo removed ({', '.join(dropped)})")
        if _tempo_sound(keep) is not None and keep.find("direction-type/metronome") is None:
            tempo = _tempo_sound(keep).get("tempo")
            _detach_sound(keep_m, keep)
            log.append(f"tempo {where}: <sound tempo=\"{tempo}\"> kept for playback as a measure-level <sound>, "
                       "out of the printed direction")
        elif keep.find("direction-type") is None and _tempo_sound(keep) is None:
            keep_m.remove(keep)  # nothing printed, nothing played
    return log


def _describe_dt(dt: ET.Element) -> str:
    holder = ET.Element("direction")
    holder.append(dt)
    text = _describe(holder)
    holder.remove(dt)
    return text


# ------------------------------------------------------------------- main ---

def repair(root: ET.Element, args: argparse.Namespace) -> list[str]:
    log: list[str] = []
    names = [n.strip() for n in args.parts.split(",") if n.strip()] if args.parts else None
    n_parts = len(root.findall("part-list/score-part"))
    if names is not None and len(names) > n_parts:
        raise ValueError(f"--parts names {len(names)} parts but the score has {n_parts}")
    rights = None
    if args.rights_template:
        rights = rights_text(args.rights_template, args.source, args.notice, args.year, args.name)
    if args.title is not None:
        old = set_title(root, args.title.strip())
        log.append(f"title: {old!r} -> {args.title.strip()!r}")
    elif args.normalize_title:
        for path in ("work/work-title", "movement-title"):
            el = root.find(path)
            if el is not None and el.text is not None:
                new = normalize_title(el.text)
                if new != el.text:
                    log.append(f"title ({path}): {el.text!r} -> {new!r}")
                    sync_title_credit(root, el.text, new)
                    el.text = new
    for kind in ("composer", "arranger", "lyricist"):
        value = getattr(args, kind)
        if value:
            set_creator(root, kind, value.strip())
            log.append(f"{kind}: {value.strip()!r}")
    if rights:
        set_rights(root, rights)
        log.append(f"rights: {rights!r}")
    if args.merge_credits:
        log += merge_credits(root)
    wants_credits = args.title is not None or args.normalize_title or args.composer or args.arranger or args.lyricist or args.subtitle
    added = add_credits(root, args.subtitle.strip() if args.subtitle else None) if wants_credits else []
    if added:
        log.append("credits added: " + ", ".join(added))
    log += fix_parts(root, names)
    if args.tempo:
        log += fix_tempo(root, args.tempo)
    return log


def _utf8_unless(m: re.Match) -> str:
    """We write UTF-8; leave a declaration that already says so untouched."""
    return m.group(0) if re.search(r"utf-?8", m.group(0), re.I) else f'{m.group(1)}"UTF-8"'


def serialize(root: ET.Element, header: str) -> str:
    header = ENCODING_ATTR.sub(_utf8_unless, header, count=1) if header.strip() else DEFAULT_HEADER
    if not header.endswith("\n"):
        header += "\n"
    return header + ET.tostring(root, encoding="unicode") + "\n"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--title")
    ap.add_argument("--subtitle", help="printed under the title, e.g. \"(Stille Nacht)\"; written as a credit")
    ap.add_argument("--composer")
    ap.add_argument("--arranger")
    ap.add_argument("--lyricist")
    ap.add_argument("--rights-template", choices=["public-domain", "in-copyright", "own-arrangement", "verbatim"], help="verbatim: write --notice unchanged (only text printed on the source)")
    ap.add_argument("--source", help="public-domain: where it was transcribed from")
    ap.add_argument("--notice", help="in-copyright: the original copyright notice")
    ap.add_argument("--year", help="own-arrangement: year")
    ap.add_argument("--name", help="own-arrangement: arranger's name")
    ap.add_argument("--parts", help='comma-separated part names in score order, e.g. "Soprano,Alto,Tenor,Bass"')
    ap.add_argument("--normalize-title", action="store_true", help="strip, drop a list number, fix ALL CAPS / lower case")
    ap.add_argument("--merge-credits", action="store_true",
                    help="join credit lines of one block (same alignment, stacked) into one credit with line breaks")
    ap.add_argument("--tempo", choices=TEMPO_MODES,
                    help="once: write each tempo mark once (one direction per bar and beat) and keep <sound tempo> "
                    "out of a direction with no metronome, so Sibelius does not print 'q = N' the print lacks; "
                    "none: the print has no tempo, drop the printed metronome and words too (playback tempo stays)")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    src, dst = Path(args.input), Path(args.output)
    try:
        text = read_text(src)
        root = parse(text)
    except Exception as exc:
        print(f"error: cannot read {src}: {exc}", file=sys.stderr)
        return 2
    if root.tag != "score-partwise":
        print("error: only score-partwise MusicXML is supported", file=sys.stderr)
        return 2
    try:
        log = repair(root, args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    dst.write_text(serialize(root, header_of(text)), encoding="utf-8")
    print("\n".join(log) if log else "nothing to change")
    return 0


if __name__ == "__main__":
    sys.exit(main())
