"""Compare note onsets of two rendered MP3s to see whether a swing (or any timing) change reached the audio.

    uv run python onset_check.py STRAIGHT.mp3 SWUNG.mp3 [N]

Prints the first N detected onsets (seconds) of each file. Swing shows as the off-beat onsets moving later
(about two thirds of the way to the next beat) while the total length stays the same. Needs ffmpeg.
"""
import struct
import subprocess
import sys
import wave
import tempfile
import os


def load(path):
    with tempfile.TemporaryDirectory() as d:
        wav = os.path.join(d, "x.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-ar", "8000", "-ac", "1", wav], check=True)
        w = wave.open(wav)
        raw = w.readframes(w.getnframes())
    return struct.unpack("<%dh" % (len(raw) // 2), raw)


def onsets(x, hop=80):
    env = [sum(abs(v) for v in x[i:i + hop]) / hop for i in range(0, len(x) - hop, hop)]
    out = []
    for i in range(3, len(env)):
        if env[i] > 300 and env[i] > 1.8 * max(env[i - 3], 30) and (not out or i - out[-1] > 12):
            out.append(i)
    return [round(o * hop / 8000, 2) for o in out]


if __name__ == "__main__":
    n = int(sys.argv[3]) if len(sys.argv) > 3 else 16
    for p in sys.argv[1:3]:
        print(os.path.basename(p), onsets(load(p))[:n])
