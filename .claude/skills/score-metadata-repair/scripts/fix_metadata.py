#!/usr/bin/env python3
"""Fix metadata defects in a MusicXML file before it is imported into an editor.

Standard library only, so the skill runs without the rest of this repository.

Usage:
    fix_metadata.py IN OUT [--title T] [--composer C] [--arranger A]
        [--lyricist L] [--rights-template public-domain|in-copyright|own-arrangement]
        [--source S] [--notice N] [--year Y] [--name NAME]
        [--parts "Soprano,Alto,Tenor,Bass"] [--normalize-title]

IN may be .xml, .musicxml or .mxl; OUT is plain MusicXML. Only metadata is
touched (title, creators, rights, credits, part names and abbreviations);
notes, lyrics and layout are copied unchanged, and so is the XML declaration
and DOCTYPE. Nothing is invented: a composer, arranger, lyricist or rights
line is written only when you pass it.

Exit status: 0 on success, 2 on bad arguments or an unreadable file.
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
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


def add_credits(root: ET.Element) -> list[str]:
    """Add title/composer/arranger/lyricist credits when the score has none."""
    if root.find("credit") is not None:
        return []
    width, height = _page(root, "page-width", 1233), _page(root, "page-height", 1600)
    title = (root.findtext("work/work-title") or root.findtext("movement-title") or "").strip()
    people = {c.get("type"): (c.text or "").strip() for c in root.findall("identification/creator")}
    rows = []
    if title:
        rows.append(("title", title, width / 2, height - 100, "center", 24))
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
    wants_credits = args.title is not None or args.normalize_title or args.composer or args.arranger or args.lyricist
    added = add_credits(root) if wants_credits else []
    if added:
        log.append("credits added: " + ", ".join(added))
    log += fix_parts(root, names)
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
    ap.add_argument("--composer")
    ap.add_argument("--arranger")
    ap.add_argument("--lyricist")
    ap.add_argument("--rights-template", choices=["public-domain", "in-copyright", "own-arrangement"])
    ap.add_argument("--source", help="public-domain: where it was transcribed from")
    ap.add_argument("--notice", help="in-copyright: the original copyright notice")
    ap.add_argument("--year", help="own-arrangement: year")
    ap.add_argument("--name", help="own-arrangement: arranger's name")
    ap.add_argument("--parts", help='comma-separated part names in score order, e.g. "Soprano,Alto,Tenor,Bass"')
    ap.add_argument("--normalize-title", action="store_true", help="strip, drop a list number, fix ALL CAPS / lower case")
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
