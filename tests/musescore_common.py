"""Shared helpers for the test_musescore test modules."""

import json
import pytest
import websockets

from ai_score_editing.musescore import install
from ai_score_editing.musescore import score


TOKEN = "test-token"


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("MUSESCORE_PLUGIN_DIR", str(tmp_path / "plugins"))
    return tmp_path


class FakeBridge:
    """Answers like msbridge.qml: same envelope, a handful of methods."""

    def __init__(self, mscore=40705, bridge=install.BRIDGE_VERSION, handler=None):
        self.mscore, self.bridge, self.handler = mscore, bridge, handler
        self.requests = []

    async def serve(self, ws):
        async for message in ws:
            request = json.loads(message)
            self.requests.append(request)
            reply = {"id": request["id"], "bridge": self.bridge, "mscoreVersion": self.mscore}
            if request.get("token") != TOKEN:
                reply.update(ok=False, error="unauthorised")
            else:
                try:
                    reply.update(ok=True, result=self.answer(request["method"], request["args"]))
                except KeyError as exc:
                    reply.update(ok=False, error=str(exc))
                reply["score"] = {"name": "Scratch", "measures": 8, "staves": 3, "parts": 2}
            await ws.send(json.dumps(reply))

    def answer(self, method, args):
        if self.handler:
            return self.handler(method, args)
        return {
            "GetBridgeVersion": {"version": self.bridge},
            "GetScoreInfo": {"name": "Scratch", "measures": 8, "staves": 3},
            "GetStaves": [{"staff": 1, "partName": "Clarinet in B♭"}],
            "Undo": {"undone": args.get("steps", 1)},
        }[method]


@pytest.fixture
async def fake():
    bridge = FakeBridge()
    async with websockets.serve(bridge.serve, "127.0.0.1", 0) as server:
        bridge.port = server.sockets[0].getsockname()[1]
        yield bridge

STAVES = [
    {"staff": 1, "partName": "Clarinet in B♭", "shortName": "Cl.", "transposeChromatic": -2, "transposeDiatonic": -1},
    {"staff": 2, "partName": "Piano", "shortName": "Pno.", "transposeChromatic": 0, "transposeDiatonic": 0},
]


def chord(tick, pitches, track=0, duration=480, **extra):
    notes = [{"pitch": p, "tpc1": 14, "tpc2": 16, "tieForward": False, "tieBack": False, "parentheses": 0}
             for p in pitches]
    return {"kind": "NoteRest", "type": "Chord", "tick": tick, "track": track, "visible": True, "offsetX": 0,
            "offsetY": 0, "duration": duration, "small": False, "beamMode": 0, "inTuplet": False,
            "stemDirection": 0, "up": True, "notes": notes, **extra}


def rest(tick, track=0, duration=480):
    return {"kind": "NoteRest", "type": "Rest", "tick": tick, "track": track, "visible": True, "offsetX": 0,
            "offsetY": 0, "duration": duration, "small": False, "beamMode": 0, "inTuplet": False}


def make_read():
    """Two bars of 4/4 on staff 1, one on the system staff, in the bridge's walk order."""
    bar1 = [
        chord(0, [60]),
        {"kind": "LyricItem", "type": "Lyrics", "tick": 0, "track": 0, "visible": True, "offsetX": 0,
         "offsetY": 0, "text": "Glo", "verse": 0, "syllabic": 1, "lyricTicks": 0},
        chord(480, [62, 65]),
        rest(960, duration=960),
        {"kind": "Text", "type": "Dynamic", "tick": 0, "track": 0, "visible": True, "offsetX": 0,
         "offsetY": 0, "text": "mf"},
        {"kind": "Clef", "type": "Clef", "tick": 0, "track": 0, "visible": True, "offsetX": 0, "offsetY": 0,
         "clefType": 0},
        {"kind": "Line", "type": "Slur", "tick": 0, "track": 0, "visible": True, "offsetX": 0, "offsetY": 0,
         "duration": 480},
    ]
    bar2 = [
        {"kind": "Tuplet", "type": "Tuplet", "tick": 1920, "track": 0, "visible": True, "offsetX": 0,
         "offsetY": 0, "actualNotes": 3, "normalNotes": 2, "duration": 480},
        chord(1920, [67], duration=160, beamMode=0, inTuplet=True),
        chord(2080, [67], duration=160, inTuplet=True),
        chord(2240, [67], duration=160, inTuplet=True),
        chord(2400, [69], duration=240),
        chord(2640, [71], duration=240),
        chord(2880, [72], duration=960),
        chord(1920, [48], track=1, duration=1920),
    ]
    system = [{"kind": "Text", "type": "Tempo", "tick": 0, "track": 0, "visible": True, "offsetX": 0,
               "offsetY": 0, "text": "Allegro"}]
    return {
        "division": 480, "barCount": 2,
        "bars": [{"bar": 1, "tick": 0, "ticks": 1920, "no": 0, "noOffset": 0, "irregular": False},
                 {"bar": 2, "tick": 1920, "ticks": 1920, "no": 1, "noOffset": 0, "irregular": False}],
        "content": [
            {"staff": 0, "bar": 1, "digest": "s1", "objects": system},
            {"staff": 0, "bar": 2, "digest": "s2", "objects": []},
            {"staff": 1, "bar": 1, "digest": "a1", "objects": bar1},
            {"staff": 1, "bar": 2, "digest": "a2", "objects": bar2},
        ],
    }


@pytest.fixture
def objects():
    return score.locate(make_read())


def at(objects, staff, bar, index):
    return next(o for o in objects if (o["staff"], o["bar"], o["index"]) == (staff, bar, index))


class ScoreBridge(FakeBridge):
    """A fake bridge with the read above and ApplyBatch/WriteCopy."""

    def __init__(self):
        super().__init__(handler=self.respond)

    def respond(self, method, args):
        if method == "GetBridgeVersion":
            return {"version": install.BRIDGE_VERSION}
        if method == "GetScoreInfo":
            return {"name": "Scratch", "measures": 2, "staves": 2}
        if method == "GetStaves":
            return STAVES
        if method == "Read":
            return make_read()
        if method == "WriteCopy":
            from pathlib import Path
            Path(args["path"]).write_text("<score-partwise/>")
            return {"written": True, "path": args["path"]}
        if method == "ApplyBatch":
            results = []
            for p in args["primitives"]:
                if "ref" not in p:
                    results.append({"added": rest(p["at"]["tick"], duration=p.get("ticks", 480))})
                    continue
                before = chord(0, [60])
                after = dict(before, offsetY=-0.5) if p["op"] == "set" else before
                results.append({"before": before, "after": after})
            return {"applied": len(results), "dryRun": args["dryRun"], "results": results}
        raise KeyError(method)
