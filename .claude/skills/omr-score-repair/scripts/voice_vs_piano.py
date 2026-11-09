"""Compare each voice staff with the piano staves of the score open in Sibelius.
A voice note 'matches' when its pitch class sounds in the piano at that moment (a piano note whose
onset..onset+duration covers the voice onset, any octave). Prints the mismatches per voice and bar.
Usage: voice_vs_piano.py [--exact]   (run from the repo root; needs uv and sibelius-cli)"""
import json, subprocess, sys, os, re
REPO = os.environ.get("REPO", os.getcwd())
def cli(*a):
    r = subprocess.run(["uv", "run", "sibelius-cli", *a], cwd=REPO, capture_output=True, text=True)
    return r.stdout
EXACT = "--exact" in sys.argv   # compare full pitches (octave must agree), not pitch classes
info = json.loads(cli("score-info")); bars = info["barCount"]
staves = json.loads(cli("staves"))
piano = [s["staffNum"] for s in staves if re.search(r"piano|keyboard|organ|accomp", s["instrumentName"], re.I)]
voices = [s for s in staves if s["staffNum"] not in piano]
if not piano:
    print("no piano staff:", info["fileName"]); sys.exit(0)
def notes(staff):
    out = {}
    for b in json.loads(cli("read", "--staff", str(staff), "--bars", f"1-{bars}")):
        ev = []
        for o in b["objects"]:
            if o["type"] == "NoteRest" and o["notes"]:
                ev.append((o["position"], o["duration"], sorted(n["pitch"] if EXACT else n["pitch"] % 12 for n in o["notes"]), [n["name"] for n in o["notes"]], o.get("voice")))
        out[b["barNumber"]] = ev
    return out
P = [notes(s) for s in piano]
bad = total = 0
print(info["fileName"].split("/")[-1], "piano staves", piano)
for s in voices:
    N = notes(s["staffNum"]); miss = []
    for bar, evs in N.items():
        for pos, dur, pcs, names, v in evs:
            for pc, nm in zip(pcs, names):
                total += 1
                ok = False
                for pn in P:
                    for ppos, pdur, ppcs, _, _ in pn.get(bar, []):
                        if ppos <= pos < ppos + pdur and pc in ppcs: ok = True
                if not ok: miss.append((bar, pos, nm)); bad += 1
    byb = {}
    for bar, pos, nm in miss: byb.setdefault(bar, []).append(f"{nm}@{pos}")
    print(f"  {s['instrumentName']}: {len(miss)} not in piano", "; ".join(f"b{b}: {', '.join(v)}" for b, v in sorted(byb.items())))
print(f"  total {bad}/{total} voice notes not found in the piano")
