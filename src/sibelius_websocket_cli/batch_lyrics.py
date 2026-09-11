"""Reusable helpers for validating, formatting, and verifying lyric patches."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from sibelius_websocket_cli import lyrics


class BatchLyricsError(ValueError):
    """A batch lyric patch file or operation is invalid."""


@dataclass(frozen=True, slots=True)
class LyricPatch:
    """One lyric replacement, addressed by its position in a Sibelius bar."""

    staff: int
    bar: int
    index: int
    text: str
    font: str | None = None
    font_size: int | None = None

    @property
    def address(self) -> tuple[int, int, int]:
        return (self.staff, self.bar, self.index)


@dataclass(frozen=True, slots=True)
class AffectedRange:
    """Smallest inclusive bar range containing a staff's lyric patches."""

    staff: int
    from_bar: int
    to_bar: int


@dataclass(frozen=True, slots=True)
class PatchVerification:
    """Read-back result for one lyric patch."""

    staff: int
    bar: int
    index: int
    expected: str
    actual: str | None
    verified: bool

    @property
    def address(self) -> tuple[int, int, int]:
        return (self.staff, self.bar, self.index)

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "staff": self.staff,
            "bar": self.bar,
            "index": self.index,
            "expected": self.expected,
            "verified": self.verified,
        }
        if self.actual is not None:
            result["actual"] = self.actual
        return result


_PATCH_FIELDS = {"staff", "bar", "index", "text", "font", "fontSize"}
_FONT_SIZE_PREFIX = re.compile(r"^\\f[^\\]+\\+s\d+\\")
_FONT_PREFIX = re.compile(r"^\\f[^\\]+\\")
_SIZE_PREFIX = re.compile(r"^\\s\d+\\")


def load_lyric_patches(path: str | Path) -> list[LyricPatch]:
    """Load and validate a JSON array of lyric patch objects."""
    source = Path(path).expanduser()
    try:
        payload = json.loads(source.read_text())
    except OSError as exc:
        raise BatchLyricsError(f"cannot read patch file {source}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BatchLyricsError(
            f"invalid JSON in patch file {source}: line {exc.lineno}, column {exc.colno}"
        ) from exc
    return parse_lyric_patches(payload)


def parse_lyric_patches(payload: Any) -> list[LyricPatch]:
    """Validate decoded JSON and return normalized immutable patches."""
    if not isinstance(payload, list) or not payload:
        raise BatchLyricsError("patch file must contain a non-empty JSON array")

    patches: list[LyricPatch] = []
    seen: set[tuple[int, int, int]] = set()
    for position, item in enumerate(payload, start=1):
        label = f"patch {position}"
        if not isinstance(item, dict):
            raise BatchLyricsError(f"{label} must be a JSON object")

        unknown = sorted(set(item) - _PATCH_FIELDS)
        if unknown:
            raise BatchLyricsError(f"{label} has unknown field(s): {', '.join(unknown)}")

        missing = sorted({"staff", "bar", "index", "text"} - set(item))
        if missing:
            raise BatchLyricsError(f"{label} is missing field(s): {', '.join(missing)}")

        staff = _positive_int(item["staff"], f"{label}.staff")
        bar = _positive_int(item["bar"], f"{label}.bar")
        index = _nonnegative_int(item["index"], f"{label}.index")
        text = item["text"]
        if not isinstance(text, str):
            raise BatchLyricsError(f"{label}.text must be a string")

        font = item.get("font")
        if font is not None and (not isinstance(font, str) or not font.strip()):
            raise BatchLyricsError(f"{label}.font must be a non-empty string")
        if isinstance(font, str):
            font = font.strip()

        raw_font_size = item.get("fontSize")
        font_size = (
            None
            if raw_font_size is None
            else _positive_int(raw_font_size, f"{label}.fontSize")
        )

        patch = LyricPatch(staff, bar, index, text, font, font_size)
        if patch.address in seen:
            address = _format_address(patch.address)
            raise BatchLyricsError(f"{label} duplicates lyric address {address}")
        seen.add(patch.address)
        patches.append(patch)

    return patches


def affected_lyric_ranges(patches: Sequence[LyricPatch]) -> list[AffectedRange]:
    """Return one minimal verification/read range per affected staff."""
    bars_by_staff: dict[int, list[int]] = {}
    for patch in patches:
        bars_by_staff.setdefault(patch.staff, []).append(patch.bar)
    return [
        AffectedRange(staff, min(bars), max(bars))
        for staff, bars in sorted(bars_by_staff.items())
    ]


def validate_patch_targets(
    patches: Sequence[LyricPatch], current_lyrics: Sequence[Mapping[str, Any]]
) -> dict[tuple[int, int, int], Mapping[str, Any]]:
    """Require every patch address to exist in a pre-write ReadLyrics result."""
    by_address = {_lyric_address(item): item for item in current_lyrics}
    missing = [patch.address for patch in patches if patch.address not in by_address]
    if missing:
        formatted = ", ".join(_format_address(address) for address in missing)
        raise BatchLyricsError(f"no LyricItem found at: {formatted}")
    return {patch.address: by_address[patch.address] for patch in patches}


def resolve_lyric_text(
    patch: LyricPatch,
    *,
    default_font: str | None = None,
    default_font_size: int | None = None,
    staff_lyrics: Sequence[Mapping[str, Any]] = (),
    score_default_font: str | None = None,
) -> str:
    """Resolve formatting tags using explicit defaults or set-lyric's inference rules."""
    font = patch.font or _clean_font(default_font)
    size = patch.font_size or default_font_size
    if size is not None:
        _positive_int(size, "font size")

    if font:
        return _tagged_text(font, size or 110, patch.text)
    if size:
        return f"\\s{size}\\{patch.text}"
    if patch.text.startswith("\\f"):
        return patch.text

    staff_items = [dict(item) for item in staff_lyrics if item.get("staff") == patch.staff]
    typography = lyrics.analyze_lyric_typography(
        staff_items, score_default_font=score_default_font
    )
    predominant_font = typography.get("predominant_font") or score_default_font or "Times New Roman"
    predominant_size = typography.get("predominant_size") or 110
    existing = next(
        (item for item in staff_items if _lyric_address(item) == patch.address), None
    )

    chosen_font: str | None = None
    chosen_size: int | None = None
    if existing:
        existing_font, existing_size = lyrics.extract_font_and_size(existing)
        if existing_font and (not predominant_font or existing_font == predominant_font):
            chosen_font = existing_font
            chosen_size = existing_size
        elif predominant_font:
            chosen_font = predominant_font
            chosen_size = predominant_size or existing_size
    elif predominant_font:
        chosen_font = predominant_font
        chosen_size = predominant_size

    effective_font = chosen_font or predominant_font
    if effective_font == "BigCaslon-Medium":
        effective_font = "Big Caslon"
    return _tagged_text(effective_font, chosen_size or predominant_size or 110, patch.text)


def verify_lyric_patches(
    patches: Sequence[LyricPatch], lyrics_after: Sequence[Mapping[str, Any]]
) -> list[PatchVerification]:
    """Compare requested plain text with a post-write ReadLyrics result."""
    by_address = {_lyric_address(item): item for item in lyrics_after}
    verification: list[PatchVerification] = []
    for patch in patches:
        item = by_address.get(patch.address)
        actual_value = item.get("text") if item is not None else None
        actual = actual_value if isinstance(actual_value, str) else None
        expected_plain = plain_lyric_text(patch.text)
        actual_plain = plain_lyric_text(actual) if actual is not None else None
        verification.append(
            PatchVerification(
                patch.staff,
                patch.bar,
                patch.index,
                expected_plain,
                actual_plain,
                actual_plain == expected_plain,
            )
        )
    return verification


def plain_lyric_text(text: str) -> str:
    """Remove leading Sibelius font and size tags for read-back comparison."""
    # Font and size tags can have one or two slashes at their boundary,
    # depending on whether the value came from Sibelius or was constructed by
    # the CLI.  Strip the combined form before considering individual tags.
    previous = None
    while text != previous:
        previous = text
        text = _FONT_SIZE_PREFIX.sub("", text, count=1)
        text = _FONT_PREFIX.sub("", text, count=1)
        text = _SIZE_PREFIX.sub("", text, count=1)
    return text


def build_batch_summary(
    patches: Sequence[LyricPatch],
    write_results: Sequence[Mapping[str, Any]],
    verification: Sequence[PatchVerification],
    *,
    backup: Mapping[str, Any] | None = None,
    saved: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact, JSON-serializable result for a completed batch."""
    if len(write_results) != len(patches) or len(verification) != len(patches):
        raise BatchLyricsError("patch, write-result, and verification counts must match")

    changes: list[dict[str, Any]] = []
    for patch, write_result, checked in zip(patches, write_results, verification):
        change: dict[str, Any] = {
            "staff": patch.staff,
            "bar": patch.bar,
            "index": patch.index,
            "old": write_result.get("oldText"),
            "new": checked.actual if checked.actual is not None else plain_lyric_text(patch.text),
            "verified": checked.verified,
        }
        changes.append(change)

    result: dict[str, Any] = {
        "patched": len(patches),
        "verified": sum(item.verified for item in verification),
        "changes": changes,
    }
    if backup is not None:
        result["backup"] = backup.get("copy")
    if saved is not None:
        result["savedTo"] = saved.get("fileName")
    return result


def format_compact_summary(summary: Mapping[str, Any]) -> str:
    """Render the JSON-ready batch summary as a short human-readable report."""
    patched = int(summary.get("patched", 0))
    verified = int(summary.get("verified", 0))
    parts = [f"patched {patched}", f"verified {verified}/{patched}"]
    if summary.get("backup"):
        parts.append(f"backup {summary['backup']}")
    if summary.get("savedTo"):
        parts.append(f"saved {summary['savedTo']}")

    failed = [
        _format_address((item["staff"], item["bar"], item["index"]))
        for item in summary.get("changes", [])
        if not item.get("verified", False)
    ]
    if failed:
        parts.append(f"verification failed: {', '.join(failed)}")
    return "; ".join(parts)


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise BatchLyricsError(f"{name} must be a positive integer")
    return value


def _nonnegative_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BatchLyricsError(f"{name} must be a non-negative integer")
    return value


def _clean_font(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise BatchLyricsError("font must be a non-empty string")
    return value.strip()


def _tagged_text(font: str, size: int, text: str) -> str:
    return f"\\f{font}\\\\s{size}\\{text}"


def _lyric_address(item: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    return (item.get("staff"), item.get("bar"), item.get("index"))


def _format_address(address: tuple[Any, Any, Any]) -> str:
    return f"S{address[0]} B{address[1]} I{address[2]}"
