"""Compare a candidate MusicXML (for example one read from a PDF) with a reference MusicXML, note by note.

  python compare_musicxml.py REFERENCE.xml CANDIDATE.xml [--map P1=P1,P2=P2] [--show 20]

Every note is a slot (bar, onset, MIDI pitch) with its duration, ties and first lyric. Parts are matched by part id
(or by --map ref=cand); the staff and voice are ignored, so a condensed staff compares fine against separate parts.
Prints, per part, the slots in both files, the slots only in the reference, only in the candidate, and the
duration / tie / lyric differences among the shared slots, then the time-signature and key-signature changes.
Slots that exist only in the reference are information the PDF may not carry (for example a layout that hides a part)."""
import argparse
import sys
import xml.etree.ElementTree as ET

STEP = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


def load(path):
    """-> ({part id: {(bar, onset, midi): (duration, tie_start, tie_stop, lyric)}}, {'time': [...], 'key': [...]})"""
    root = ET.parse(path).getroot()
    parts, meta = {}, {'time': [], 'key': []}
    for part in root.findall('part'):
        pid = part.get('id')
        slots = parts.setdefault(pid, {})
        div = 1
        for bar, measure in enumerate(part.findall('measure'), 1):
            cur = 0
            last_on = 0
            for el in measure:
                if el.tag == 'attributes':
                    if el.find('divisions') is not None: div = int(el.find('divisions').text)
                    if pid == next(iter(parts)):
                        if el.find('key/fifths') is not None: meta['key'].append((bar, int(el.find('key/fifths').text)))
                        t = el.find('time')
                        if t is not None: meta['time'].append((bar, int(t.find('beats').text), int(t.find('beat-type').text)))
                elif el.tag == 'backup': cur -= int(el.find('duration').text) * 256 // div
                elif el.tag == 'forward': cur += int(el.find('duration').text) * 256 // div
                elif el.tag == 'note':
                    dur = int(el.findtext('duration', '0')) * 256 // div
                    chord = el.find('chord') is not None
                    onset = last_on if chord else cur
                    pn = el.find('pitch')
                    if pn is not None:
                        midi = 12 * (int(pn.findtext('octave')) + 1) + STEP[pn.findtext('step')] + int(float(pn.findtext('alter', '0')))
                        ties = {t.get('type') for t in el.findall('tie')}
                        slots[(bar, onset, midi)] = (dur, 'start' in ties, 'stop' in ties, (el.findtext('lyric/text') or '').strip())
                    if not chord:
                        last_on = cur
                        cur += dur
    return parts, meta


def compare(ref, cand, mapping=None, show=20, out=print):
    """-> dict of counts. `ref` and `cand` are the results of load()."""
    (rp, rm), (cp, cm) = ref, cand
    mapping = mapping or {p: p for p in rp if p in cp}
    totals = {'shared': 0, 'ref_only': 0, 'cand_only': 0, 'duration': 0, 'tie': 0, 'lyric': 0}
    shown = 0
    for rid, cid in mapping.items():
        a, b = rp.get(rid, {}), cp.get(cid, {})
        shared = set(a) & set(b)
        diffs = {'duration': 0, 'tie': 0, 'lyric': 0}
        for k in sorted(shared):
            if a[k][0] != b[k][0]: diffs['duration'] += 1; shown = _show(out, shown, show, rid, k, 'duration', a[k][0], b[k][0])
            if a[k][1:3] != b[k][1:3]: diffs['tie'] += 1; shown = _show(out, shown, show, rid, k, 'tie', a[k][1:3], b[k][1:3])
            if a[k][3] != b[k][3]: diffs['lyric'] += 1; shown = _show(out, shown, show, rid, k, 'lyric', a[k][3], b[k][3])
        ref_only, cand_only = set(a) - set(b), set(b) - set(a)
        bars = sorted({k[0] for k in ref_only})
        out(f'{rid}->{cid}: shared {len(shared)}, only in reference {len(ref_only)}' + (f' (bars {bars[0]}-{bars[-1]})' if bars else '')
            + f', only in candidate {len(cand_only)}, differences {diffs}')
        totals['shared'] += len(shared); totals['ref_only'] += len(ref_only); totals['cand_only'] += len(cand_only)
        for key in diffs: totals[key] += diffs[key]
    out('time signatures: ' + ('same' if rm['time'] == cm['time'] else f"reference {rm['time'][:6]} candidate {cm['time'][:6]}"))
    out('key signatures: ' + ('same' if rm['key'] == cm['key'] else f"reference {rm['key'][:6]} candidate {cm['key'][:6]}"))
    return totals


def _show(out, shown, limit, rid, key, what, ref, cand):
    if shown < limit: out(f'  {rid} bar {key[0]} onset {key[1]} midi {key[2]}: {what} reference {ref!r} candidate {cand!r}')
    return shown + 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('reference'); ap.add_argument('candidate')
    ap.add_argument('--map', default='', help='part id pairs, ref=cand,ref=cand (default: same ids)')
    ap.add_argument('--show', type=int, default=20, help='how many differences to print')
    a = ap.parse_args(argv)
    mapping = dict(kv.split('=') for kv in a.map.split(',') if kv) or None
    compare(load(a.reference), load(a.candidate), mapping, a.show)


if __name__ == '__main__':
    main()
