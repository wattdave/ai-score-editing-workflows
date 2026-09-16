# Visual Ground Truth Inspection for Sheet Music Scans

When repairing Optical Music Recognition (OMR) output or reconciling MusicXML discrepancies, **never guess or trust OMR metadata alone**. Inspect the printed visual source to establish ground truth.

---

## 1. Quick PDF-to-Image Rendering on macOS

Do not rely on heavy external rasterizers (`pdf2image`, `poppler`, or `pdftoppm`). Use the built-in macOS QuickLook utility:

```bash
qlmanage -t -s 2000 -o <scratch_dir> "<pdf_path>"
```

- `-t`: Thumbnail/rendered page preview.
- `-s 2000`: High resolution (2000px on long edge) for crisp notation and text readability.
- Generates `<pdf_name>.pdf.png` in the specified directory.

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
