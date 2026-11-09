"""chk.py PDF: report footer vs lowest staff ink on each page (pts from top)."""
import re, subprocess, sys, io
pdf = sys.argv[1]
n = int(re.search(r"Pages:\s+(\d+)", subprocess.run(["pdfinfo", pdf], capture_output=True, text=True).stdout).group(1))
bbox = subprocess.run(["pdftotext", "-bbox", pdf, "-"], capture_output=True, text=True).stdout
pages = bbox.split("<page ")[1:]
for pi, ptxt in enumerate(pages, 1):
    h = float(re.search(r'height="([\d.]+)"', ptxt).group(1))
    w = float(re.search(r'width="([\d.]+)"', ptxt).group(1))
    words = [(float(a), float(b), float(c), float(d), t) for a, b, c, d, t in
             re.findall(r'xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)<', ptxt)]
    foot = [wd for wd in words if wd[4] in ("Public", "domain.") or False]
    fy = None
    if foot:
        fy = foot[0]
        # footer words: same line as 'Public'
        line = [wd for wd in words if abs(wd[1] - fy[1]) < 2]
        fx0 = min(x[0] for x in line); fx1 = max(x[2] for x in line)
        fy0 = min(x[1] for x in line); fy1 = max(x[3] for x in line)
    ppm = subprocess.run(["pdftoppm", "-r", "100", "-f", str(pi), "-l", str(pi), "-gray", pdf], capture_output=True).stdout
    # parse PGM
    m = re.match(rb"P5\s+(\d+)\s+(\d+)\s+(\d+)\s", ppm)
    W, H = int(m.group(1)), int(m.group(2)); data = ppm[m.end():]
    s = 100 / 72
    def ink(row, x0=0, x1=W):
        r = data[row * W:(row + 1) * W]
        return [x for x in range(x0, x1) if r[x] < 128]
    last = max((r for r in range(H) if ink(r)), default=0)
    out = f"p{pi}: pageH={h:.0f}pt lowest ink={last/s:.0f}pt ({(h-last/s)/72:.2f}in from bottom)"
    if foot:
        bad = 0
        for r in range(int(fy0 * s) - 2, int(fy1 * s) + 2):
            xs = ink(r)
            bad += sum(1 for x in xs if x < fx0 * s - 5 or x > fx1 * s + 5)
        # ink in footer extent attributable to staff: rows above/below text
        above = max((r for r in range(int(fy0 * s) - 2) if ink(r)), default=0)
        out += f" | footer y={fy0:.0f}-{fy1:.0f}pt, outside-ink px in band={bad}, last ink above footer={above/s:.0f}pt gap={fy0-above/s:.0f}pt"
    print(out)
