"""Plan a printed page layout as an apply batch: breaks, hidden staves, set-layout.

Pure helpers behind ``sibelius-cli auto-layout``. The input is where each
system of the print starts, page by page, plus the number of lyric verses and
staves; the output is a batch of ``set-break``, ``hide-empty-staves`` and one
``set-layout`` (last, because Sibelius ignored a ``set-layout`` that later
breaks or hidden staves re-laid out). The ``set-layout`` values come from the
Nelson Carol Book run (about 40 carols on letter pages, measured in Sibelius);
see ``.claude/skills/sibelius/references/import-and-layout-recipes.md``.

Bar numbers in the input are the print's. When the print numbers a pickup as
bar 0, pass ``offset=1``: the score's bar 1 is then the pickup and printed bar
N is score bar N + 1. A system starting at score bar N needs its break on bar
N - 1, so the first bar never gets one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from ai_score_editing.core.batch_schema import LAYOUT_NUMBERS, ORIENTATIONS, PAGE_SIZES
from ai_score_editing.core.errors import BatchError

#: Pages per spec are separated by "/" or "|"; systems by commas or spaces.
_PAGE_SEPARATORS = re.compile(r"[/|]")


@dataclass
class Preset:
    """A row of the layout table: its name, the settings, and how sure it is."""

    name: str
    settings: dict[str, float]
    measured: bool = True


@dataclass
class Plan:
    """What auto-layout will do, in score bar numbers."""

    pages: list[list[int]]
    batch: list[dict[str, Any]]
    preset: Preset
    notes: list[str] = field(default_factory=list)
    offset: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "pages": len(self.pages),
            "systemsPerPage": [len(page) for page in self.pages],
            "systemStarts": self.pages,
            "barOffset": self.offset,
            "preset": self.preset.name,
            "presetMeasured": self.preset.measured,
            "layout": next(op for op in self.batch if op["op"] == "set-layout"),
            "operations": len(self.batch),
            "notes": self.notes,
        }


def parse_systems(spec: str) -> list[list[int]]:
    """Parse "1,5,9 / 13,17,21" into system-start bars per page.

    Pages are separated by "/" or "|", bars by commas or spaces. The first
    page may leave out bar 1. Bars must rise across the whole list.
    """
    pages: list[list[int]] = []
    for chunk in _PAGE_SEPARATORS.split(spec):
        bars = [b for b in re.split(r"[,\s]+", chunk.strip()) if b]
        if not bars:
            raise BatchError(f"empty page in --systems {spec!r}")
        try:
            pages.append([int(b) for b in bars])
        except ValueError as exc:
            raise BatchError(f"--systems takes bar numbers: {exc}") from exc
    _check_rising(pages)
    return pages


def _check_rising(pages: list[list[int]]) -> None:
    flat = [b for page in pages for b in page]
    if any(b < 0 for b in flat):
        raise BatchError("system-start bars must be 0 or more")
    if any(later <= earlier for earlier, later in zip(flat, flat[1:])):
        raise BatchError(f"system-start bars must rise: {flat}")


def parse_range(text: str) -> tuple[int, int]:
    """Parse "11-18" (or "11") into a bar range."""
    parts = text.replace("..", "-").split("-")
    try:
        if len(parts) == 1:
            first = last = int(parts[0])
        elif len(parts) == 2:
            first, last = int(parts[0]), int(parts[1])
        else:
            raise ValueError(text)
    except ValueError as exc:
        raise BatchError(f"bar range must look like 11-18, not {text!r}") from exc
    if first < 0 or last < first:
        raise BatchError(f"bar range {text!r} must run forwards from bar 0 or later")
    return first, last


def parse_overrides(items: list[str]) -> dict[str, Any]:
    """Parse ["staffSize=5.5", "pageSize=a4"] into set-layout fields."""
    out: dict[str, Any] = {}
    for item in items:
        key, sep, value = item.partition("=")
        key, value = key.strip(), value.strip()
        if not sep or not value:
            raise BatchError(f"--layout takes NAME=VALUE, not {item!r}")
        if key in LAYOUT_NUMBERS:
            try:
                number = float(value)
            except ValueError as exc:
                raise BatchError(f"--layout {key} must be a number") from exc
            out[key] = int(number) if number.is_integer() else number
        elif key in {"pageSize", "orientation"}:
            choices = PAGE_SIZES if key == "pageSize" else ORIENTATIONS
            if value not in choices:
                raise BatchError(f"--layout {key} must be one of: {', '.join(choices)}")
            out[key] = value
        else:
            names = sorted([*LAYOUT_NUMBERS, "pageSize", "orientation"])
            raise BatchError(f"--layout {key!r} is not a set-layout field; one of: {', '.join(names)}")
    return out


def pages_from_ready(data: dict[str, Any]) -> tuple[list[list[int]], int, list[str]]:
    """System starts per page, the bar offset, and notes, from a ready.json.

    ready.json files describe the print's systems in several ways:
    ``breaks`` as ``{"system_starts_at_bars"|..._measures|..._measure_numbers: [...]}``,
    ``{"system_ends_after_bars"|..._measures: [...]}`` or a bare list, and
    ``page_breaks`` as a list. Page breaks follow the convention of the
    system breaks (ends-after when only ends are given). A bare list is read as
    system starts unless a ``post_import`` note says the breaks come "after"
    the bars. A pickup mentioned in ``breaks`` or ``bars`` gives offset 1.
    """
    notes: list[str] = []
    breaks = data.get("breaks")
    total = data.get("bars") if isinstance(data.get("bars"), int) else None
    ends = False
    if isinstance(breaks, dict):
        starts_key = next((k for k in breaks if k.startswith("system_starts")), None)
        ends_key = next((k for k in breaks if k.startswith("system_ends_after")), None)
        if starts_key:
            starts = list(breaks[starts_key])
        elif ends_key:
            ends = True
            starts = [b + 1 for b in breaks[ends_key]]
        else:
            raise BatchError("ready.json breaks has no system_starts_* or system_ends_after_* list")
    elif isinstance(breaks, list):
        said = " ".join(str(n) for n in data.get("post_import", []) if isinstance(n, str)).lower()
        if re.search(r"breaks? after", said) and not re.search(r"breaks? before", said):
            ends = True
            starts = [b + 1 for b in breaks]
            notes.append("ready.json breaks is a bare list; its post_import notes say 'after', read as system ends")
        else:
            starts = list(breaks)
            if not re.search(r"breaks? before|at system starts", said):
                notes.append("ready.json breaks is a bare list, read as system starts; check against the print")
    elif breaks is None:
        starts = []
    else:
        raise BatchError("ready.json breaks must be a list or an object")
    page_breaks = list(data.get("page_breaks") or [])
    page_starts = [b + 1 for b in page_breaks] if ends else page_breaks
    if not all(isinstance(b, int) for b in [*starts, *page_starts]):
        raise BatchError("ready.json breaks and page_breaks must hold bar numbers")
    if ends:
        if total is not None:
            starts = [b for b in starts if b <= total]
        elif starts:
            starts = starts[:-1]
            notes.append("system ends read without a bar count: the last one is taken as the final bar")
    pages = split_pages(sorted(set(starts) | set(page_starts)), page_starts)
    printed = data.get("pages_in_print")
    if isinstance(printed, int) and printed != len(pages):
        notes.append(f"ready.json says {printed} page(s) but its page breaks give {len(pages)}")
    text = json.dumps({"breaks": breaks, "bars": data.get("bars")}).lower()
    offset = 1 if "pickup" in text else 0
    if offset:
        notes.append("ready.json mentions a pickup: printed bar N is score bar N+1 (pass --no-pickup if not)")
    return pages, offset, notes


def split_pages(starts: list[int], page_starts: list[int]) -> list[list[int]]:
    """Group rising system starts into pages, a new page at each page start."""
    pages: list[list[int]] = [[]]
    for bar in starts:
        # The first page may leave out its first bar, so a page start after
        # bar 1 opens a new page even when the first page is still empty.
        if bar in page_starts and (pages[-1] or bar > 1):
            pages.append([])
        pages[-1].append(bar)
    return pages


def to_score_bars(pages: list[list[int]], offset: int) -> list[list[int]]:
    """Printed bars to score bars, with the first page starting at bar 1."""
    shifted = [[b + offset for b in page] for page in pages]
    if any(b < 1 for page in shifted for b in page):
        raise BatchError("a system starts before bar 1; pass --pickup if the print numbers the pickup 0")
    if not shifted or not shifted[0] or shifted[0][0] != 1:
        shifted[0:1] = [[1, *(shifted[0] if shifted else [])]]
    _check_rising(shifted)
    return shifted


def break_ops(pages: list[list[int]]) -> list[dict[str, Any]]:
    """set-break on bar N-1 for each system start N (score bars); never on bar 0."""
    ops: list[dict[str, Any]] = []
    for p, page in enumerate(pages):
        for s, bar in enumerate(page):
            if bar <= 1:
                continue
            kind = "page" if p > 0 and s == 0 else "system"
            ops.append({"op": "set-break", "bar": bar - 1, "type": kind})
    return ops


def choose_preset(staves: int, verses: int, systems_per_page: int) -> Preset:
    """The set-layout values for this many staves, verses and systems per page.

    Rows measured on the Nelson Carol Book run (letter, portrait). Rows marked
    measured=False are interpolated or borrowed from the nearest row.
    """
    gap = {"aboveTopStaveGap": 24}
    if staves <= 2 and systems_per_page >= 8:
        if staves == 1 and systems_per_page >= 10:
            return Preset("1 staff, 10+ systems a page", {"staffSize": 5, "spacesBetweenStaves": 6,
                                                         "spacesBetweenSystems": 7})
        return Preset("8+ systems a page", {"staffSize": 4.6, "spacesBetweenStaves": 13, "spacesBetweenSystems": 4,
                                            "leftMargin": 16, "rightMargin": 16})
    if staves >= 4:
        return Preset("4+ staves", {"staffSize": 5.5, "spacesBetweenStaves": 8, "spacesBetweenSystems": 4},
                      measured=staves == 4 and verses <= 3)
    if staves == 3:
        return Preset("3 staves", {"staffSize": 5, "spacesBetweenStaves": 12, "spacesBetweenSystems": 10,
                                   "aboveTopStaveGap": 20, "bottomMargin": 24, "belowBottomStaveGap": 22},
                      measured=verses == 4)
    prefix = "1 staff (2-staff row)" if staves == 1 else "2 staves"
    measured = staves == 2
    if verses <= 2:
        return Preset(f"{prefix}, 2 verses", {"staffSize": 6, "spacesBetweenStaves": 12,
                                              "spacesBetweenSystems": 9, **gap}, measured)
    if verses == 3:
        return Preset(f"{prefix}, 3 verses (between the 2- and 4-verse rows)",
                      {"staffSize": 6, "spacesBetweenStaves": 14, "spacesBetweenSystems": 9, **gap}, False)
    if verses == 4:
        return Preset(f"{prefix}, 4 verses", {"staffSize": 6.5, "spacesBetweenStaves": 17,
                                              "spacesBetweenSystems": 9, **gap}, measured)
    if verses == 5:
        return Preset(f"{prefix}, 5 verses", {"staffSize": 6, "spacesBetweenStaves": 22,
                                              "spacesBetweenSystems": 8, **gap}, measured)
    return Preset(f"{prefix}, 6+ verses", {"staffSize": 5.5, "spacesBetweenStaves": 24,
                                           "spacesBetweenSystems": 6, **gap}, measured and verses == 6)


#: The copyright/rights footer (the text MusicXML <rights> becomes) is anchored
#: just above the bottom margin line, and a full page is stretched down to the
#: same place, so with the 22-25 mm margin the presets leave (or the ~0 mm an
#: import brings) the last staff prints over the footer or off the page.
#: A small margin plus a large belowBottomStaveGap puts the footer below the
#: last staff with about 4 pt to spare and keeps one page one page. Measured
#: on The Holly and the Ivy (2 staves, 5 verses, 6 / 22 / 8): margin 22 or
#: 24 overflowed to 0.3 in from the edge; 12 + 35 gave footer 0.46 in and
#: staff end 0.62 in from the bottom.
FOOTER_ROOM: dict[str, float] = {"bottomMargin": 12, "belowBottomStaveGap": 35}

#: When staves are hidden, a page that overlaps is overfull: the recipe's
#: first fix is a smaller staff, not bigger gaps.
HIDDEN_STAFF_MAX_SIZE = 5.5


def plan(
    pages: list[list[int]],
    *,
    verses: int,
    staves: int,
    hide: list[tuple[int, int]] | None = None,
    overrides: dict[str, Any] | None = None,
    offset: int = 0,
) -> Plan:
    """The whole batch: breaks, hide-empty-staves, then set-layout last."""
    if verses < 0:
        raise BatchError("--verses must be 0 or more")
    if staves < 1:
        raise BatchError("--staves must be 1 or more")
    score_pages = to_score_bars(pages, offset)
    notes: list[str] = []
    preset = choose_preset(staves, verses, max(len(p) for p in score_pages))
    settings: dict[str, Any] = {**FOOTER_ROOM, **preset.settings}
    if hide and settings.get("staffSize", 0) > HIDDEN_STAFF_MAX_SIZE:
        settings["staffSize"] = HIDDEN_STAFF_MAX_SIZE
        notes.append(f"staffSize capped at {HIDDEN_STAFF_MAX_SIZE} because staves are hidden "
                     "(hidden-staff pages overlapped at 6 and 6.5)")
    if not preset.measured:
        notes.append(f"layout row '{preset.name}' was not measured for this case; check the render")
    settings.update(overrides or {})
    batch = break_ops(score_pages)
    for first, last in hide or []:
        if first + offset < 1:
            raise BatchError(f"hide range {first}-{last} starts before bar 1")
        batch.append({"op": "hide-empty-staves", "fromBar": first + offset, "toBar": last + offset})
    batch.append({"op": "set-layout", **settings})
    return Plan(score_pages, batch, preset, notes, offset)


def actual_pages(rows: list[dict[str, Any]]) -> list[list[int]]:
    """System starts per page from Bar query rows with OnNthPage and OnNthSystem.

    A bar starts a system when its page or system index differs from the
    previous bar's, so it does not matter whether Sibelius counts from 0 or 1
    or numbers systems per page or through the score.
    """
    pages: list[list[int]] = []
    previous: tuple[Any, Any] | None = None
    for row in sorted(rows, key=lambda r: r["bar"]):
        fields = row.get("fields") or {}
        where = (fields.get("OnNthPage"), fields.get("OnNthSystem"))
        if None in where:
            raise BatchError(f"bar {row['bar']} has no OnNthPage/OnNthSystem")
        if previous is None or where[0] != previous[0]:
            pages.append([row["bar"]])
        elif where[1] != previous[1]:
            pages[-1].append(row["bar"])
        previous = where
    return pages


def compare_pages(expected: list[list[int]], actual: list[list[int]]) -> list[str]:
    """Differences between the planned and the rendered systems, as sentences."""
    problems: list[str] = []
    if len(actual) != len(expected):
        problems.append(f"{len(actual)} page(s), expected {len(expected)}")
    for n, (want, got) in enumerate(zip(expected, actual), start=1):
        if want != got:
            problems.append(f"page {n}: systems start at bars {got}, expected {want}")
    return problems


_PDF_PAGE = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")
_PDF_COUNT = re.compile(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)|/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", re.S)


def count_pdf_pages(data: bytes) -> int | None:
    """Pages in a PDF: the page-tree root's /Count, else the /Type /Page objects.

    None when neither can be read (for example pages inside compressed object
    streams).
    """
    counts = [int(a or b) for a, b in _PDF_COUNT.findall(data)]
    if counts:
        return max(counts)
    pages = len(_PDF_PAGE.findall(data))
    return pages or None
