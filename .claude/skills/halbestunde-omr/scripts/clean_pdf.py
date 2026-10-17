#!/usr/bin/env python3
"""Crop a scanned score PDF and flatten it to an image-only PDF.

A PDF crop box only hides content; Halbestunde uploads the whole page and
scans the hidden parts too. This renders the cropped area to a 300 dpi
grayscale image and writes a new PDF holding only that image.

Run with:  uv run --with pymupdf --with numpy python -I clean_pdf.py ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pymupdf


def content_rect(page: pymupdf.Page, margin: float) -> pymupdf.Rect:
    """Bounding box of dark pixels, ignoring an 8 pt strip at every edge.

    The strip skips the scanner's black edge lines. It does not remove black
    borders inside the page; pass --crop for those.
    """
    pm = page.get_pixmap(dpi=72, colorspace=pymupdf.csGRAY)
    dark = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.h, pm.w) < 140
    dark[:, :8] = dark[:, -8:] = False
    dark[:8] = dark[-8:] = False
    cols = np.where(dark.sum(0) >= 2)[0]
    rows = np.where(dark.sum(1) >= 2)[0]
    return pymupdf.Rect(
        max(cols[0] - margin, 0),
        max(rows[0] - margin, 0),
        min(cols[-1] + margin, pm.w),
        min(rows[-1] + margin, pm.h),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    ap.add_argument("--crop", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                    help="crop rectangle in points, applied to every page")
    ap.add_argument("--auto", action="store_true",
                    help="crop each page to its dark content plus a margin")
    ap.add_argument("--margin", type=float, default=12, help="points around --auto content")
    ap.add_argument("--drop", type=int, nargs="*", default=[], metavar="N",
                    help="1-based page numbers to leave out")
    ap.add_argument("--pad", type=float, default=0, help="white margin to add around each cropped page, in points")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args()
    if args.src.resolve() == args.dst.resolve():
        ap.error("write to a different file, then move it over the original")

    src = pymupdf.open(args.src)
    out = pymupdf.open()
    for number, page in enumerate(src, start=1):
        if number in args.drop:
            continue
        if args.crop:
            page.set_cropbox(pymupdf.Rect(*args.crop))
        elif args.auto:
            page.set_cropbox(content_rect(page, args.margin))
        pm = page.get_pixmap(dpi=args.dpi, colorspace=pymupdf.csGRAY)
        w, h = page.rect.width, page.rect.height
        new = out.new_page(width=w + 2 * args.pad, height=h + 2 * args.pad)
        new.insert_image(pymupdf.Rect(args.pad, args.pad, args.pad + w, args.pad + h), pixmap=pm)
    out.save(args.dst, deflate=True)
    print(f"{args.dst}: {len(out)} pages", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
