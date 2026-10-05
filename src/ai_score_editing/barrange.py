"""Bar-range option parsing shared by the Sibelius, Dorico and MuseScore CLIs."""

from __future__ import annotations


def parse_bar_range(
    bar: int | None = None,
    bars: str | None = None,
    from_bar: int | None = None,
    to_bar: int | None = None,
) -> tuple[int | None, int | None]:
    """Parse bar range options into (from_bar, to_bar)."""
    if bars:
        cleaned = bars.replace("..", "-").strip()
        if "-" in cleaned:
            parts = cleaned.split("-", 1)
            f = int(parts[0].strip()) if parts[0].strip() else None
            t = int(parts[1].strip()) if parts[1].strip() else None
            return (f, t)
        else:
            b = int(cleaned)
            return (b, b)
    if bar is not None:
        return (bar, bar)
    return (from_bar, to_bar)
