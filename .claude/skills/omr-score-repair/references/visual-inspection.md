# Visual Ground Truth Inspection for Sheet Music Scans

When repairing Optical Music Recognition (OMR) output or reconciling MusicXML discrepancies, **never guess or trust OMR metadata alone**. Inspect the printed visual source to establish ground truth.

---

## 1. Quick PDF-to-Image Rendering on macOS

Prefer the bundled PDFKit script, which needs nothing installed and renders **every** page. Poppler (`pdfinfo`, `pdftoppm`) is an optional setup item (`brew install poppler`); use `pdfinfo` for page counts and sizes when it is present, but do not assume it is:

```bash
swift .claude/skills/omr-score-repair/scripts/render_pdf_pages.swift "<pdf_path>" <scratch_dir> [scale]
```

- Writes `<scratch_dir>/page1.png`, `page2.png`, ... and prints each path.
- The default scale of 1.8 gives about 1100x1425 px for a Letter page, which is enough for notes and lyrics without exceeding image-viewing limits.
- Check the page count first with `mdls -name kMDItemNumberOfPages "<pdf_path>"`.

QuickLook (`qlmanage -t -s 2000 -o <scratch_dir> "<pdf_path>"`) is faster for a one-page preview, but it renders **only the first page** and writes a single `<pdf_name>.pdf.png`. Never use it as evidence about later pages.

---

## 2. Visual Layout Analysis

Use Python with Pillow (`PIL`) to analyze layout geometry:

```python
from PIL import Image

img = Image.open("preview.pdf.png")
gray = img.convert("L")
pixels = gray.load()
w, h = img.size

# 1. Detect content bounding box (ignoring page margins)
min_x, max_x = w, 0
min_y, max_y = h, 0
for y in range(h):
    for x in range(w):
        if pixels[x, y] < 240:
            if x < min_x: min_x = x
            if x > max_x: max_x = x
            if y < min_y: min_y = y
            if y > max_y: max_y = y

# 2. Find vertical line gaps (system separators)
dark_rows = [
    sum(1 for x in range(min_x, max_x + 1) if pixels[x, y] < 240)
    for y in range(min_y, max_y + 1)
]
```

---

## 3. Distinguishing Barlines from Note Stems

OMR scanners frequently miscount measures when note stems or accidentals are confused with barlines, or when spacing compresses measures.

To visually confirm barlines in a system:
1. **Staff Height**: Identify the 5 horizontal staff lines (y-coordinates with high horizontal black pixel density).
2. **Barline Span**: A normal barline spans strictly from the top staff line (line 5) to the bottom staff line (line 1), and does not extend above or below the staff lines.
3. **Note Stems**: Note stems frequently extend above or below the staff, or connect into horizontal beam bands.
4. **Final Barlines**: Look for double lines or thick-thin `light-heavy` bars at the end of sections or pieces.

---

## 4. Visual Verification Checklist

Before editing MusicXML:
- [ ] **System count**: How many printed lines/systems are on the page?
- [ ] **Score type**: Is it truly multi-part (choral/orchestral), or a single melody line flowing across systems?
- [ ] **Measure count per system**: Count barlines on each printed line individually. (Line 1 often has fewer measures due to title, clef, key, and time signatures).
- [ ] **Key & Accidentals**: Check printed key signature sharps/flats against in-measure accidentals (e.g. naturals, sharps not in key signature).
- [ ] **Lyrics & Song Numbers**: Verify whether initial text numbers (e.g. "10.") are song/hymn identifiers rather than lyric syllables.
