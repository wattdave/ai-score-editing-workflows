"""MuseScore back end: plug-in install, client protocol and version checks.

A fake bridge stands in for the plug-in on a free port; conftest.py fails any
connection to the real bridge's port.
"""

import json
import stat

import pytest
import websockets

from sibelius_websocket_cli.musescore import cli, install
from sibelius_websocket_cli.musescore.bridge import MuseScoreBridge, version_text
from sibelius_websocket_cli.musescore.client import MuseScoreClient, MuseScoreError

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


def test_install_writes_plugin_with_token_and_keeps_it(config) -> None:
    path = install.install()
    text = path.read_text()
    token = install.read_token()
    assert token and f'"{token}"' in text
    assert not any(f"@{k}@" in text for k in ("TOKEN", "PORT", "VERSION"))
    assert f"port: {install.DEFAULT_PORT}" in text and f"bridgeVersion: {install.BRIDGE_VERSION}" in text
    assert stat.S_IMODE(install.token_path().stat().st_mode) == 0o600
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    install.install()
    assert install.read_token() == token  # reinstalling keeps the running plug-in's token


def test_plugin_properties_come_before_any_block(config) -> None:
    # MuseScore reads title: etc. as text and stops at the first line ending in "{".
    lines = [line.strip() for line in install.render("t").splitlines()]
    start = lines.index("MuseScore {")
    first_block = next(i for i in range(start + 1, len(lines)) if lines[i].endswith("{"))
    assert f'title: "{install.PLUGIN_TITLE}"' in lines[start:first_block]
    # A function named run clashes with the plug-in's run signal and breaks the file.
    assert "function run(" not in install.render("t")


def test_plugin_undo_uses_the_action_name() -> None:
    text = install.TEMPLATE.read_text()
    assert 'cmd("action://notation/undo")' in text and 'cmd("undo")' not in text


async def test_overview_checks_versions(fake) -> None:
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        result = await MuseScoreBridge(client).overview()
    assert result["bridge"] == install.BRIDGE_VERSION and result["mscore"] == "4.7.5"
    assert result["score"]["name"] == "Scratch" and result["staves"][0]["partName"] == "Clarinet in B♭"
    assert result["warnings"] == []
    assert client.last["score"]["staves"] == 3


async def test_old_bridge_and_old_musescore_are_refused(fake) -> None:
    fake.bridge = install.BRIDGE_VERSION - 1
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        with pytest.raises(MuseScoreError, match="install-plugin"):
            await MuseScoreBridge(client).overview()
    fake.bridge, fake.mscore = install.BRIDGE_VERSION, 40502
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        with pytest.raises(MuseScoreError, match="4.5.2 is too old"):
            await MuseScoreBridge(client).overview()


async def test_newer_musescore_warns(fake) -> None:
    fake.mscore = 40800
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        result = await MuseScoreBridge(client).check()
    assert "4.8.0" in result["warnings"][0]


async def test_wrong_token_and_errors(fake) -> None:
    async with MuseScoreClient(port=fake.port, token="wrong") as client:
        with pytest.raises(MuseScoreError, match="refused the token"):
            await client.call("GetBridgeVersion")
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        with pytest.raises(MuseScoreError, match="NoSuchMethod"):
            await client.call("NoSuchMethod")


async def test_undo_sends_steps_and_checks_range(fake) -> None:
    async with MuseScoreClient(port=fake.port, token=TOKEN) as client:
        bridge = MuseScoreBridge(client)
        assert await bridge.undo(3) == {"undone": 3}
        with pytest.raises(MuseScoreError, match="1-20"):
            await bridge.undo(0)
    assert fake.requests[-1]["args"] == {"steps": 3}


async def test_bridge_not_running_says_how_to_start_it(config) -> None:
    client = MuseScoreClient(port=1, token=TOKEN)
    with pytest.raises(MuseScoreError, match="Plugins > sibwscli bridge"):
        await client.connect()


async def test_missing_token_says_to_install(config) -> None:
    with pytest.raises(MuseScoreError, match="install-plugin"):
        await MuseScoreClient(port=1).connect()


async def test_real_port_is_guarded() -> None:
    with pytest.raises(RuntimeError, match="fake bridge"):
        await MuseScoreClient(token=TOKEN).connect()


def test_version_text() -> None:
    assert version_text(40705) == "4.7.5"


def test_cli_install_plugin(config, capsys) -> None:
    assert cli.main(["install-plugin"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["installed"].endswith("sibwscli-bridge/msbridge.qml")


# ------------------------------------------------------------------ milestone 2: reads and batches

from sibelius_websocket_cli.musescore import score, service  # noqa: E402
from sibelius_websocket_cli.musescore.score import MuseScoreBatchError  # noqa: E402

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


def prepare(objects, ops):
    digests = {(c["staff"], c["bar"]): c["digest"] for c in make_read()["content"]}
    return score.prepare_batch(ops, objects, STAVES, 480, digests)


def test_index_order_is_pinned(objects) -> None:
    bar1 = [(o["type"], o["position"]) for o in objects if o["staff"] == 1 and o["bar"] == 1]
    assert bar1 == [("Clef", 0), ("Text", 0), ("NoteRest", 0), ("LyricItem", 0), ("Line", 0),
                    ("NoteRest", 256), ("NoteRest", 512)]
    # The raw ordinal is the bridge's walk position, whatever the index.
    assert at(objects, 1, 1, 0)["_ref"] == {"staff": 1, "bar": 1, "raw": 5, "type": "Clef", "tick": 0}
    bar2 = [(o["type"], o.get("voice")) for o in objects if o["staff"] == 1 and o["bar"] == 2][:3]
    assert bar2 == [("Tuplet", 1), ("NoteRest", 1), ("NoteRest", 2)]


def test_units_and_tuplet_ticks(objects) -> None:
    triplet = [o for o in objects if o["bar"] == 2 and o.get("inTuplet")]
    assert [o["position"] for o in triplet] == [0, 85, 171]
    assert [o["ticks"] for o in triplet] == [0, 160, 320]
    assert triplet[0]["duration"] == 85 and triplet[0]["durationTicks"] == 160
    assert score.to_units(480, 480) == 256 and score.to_units(240, 480) == 128
    with pytest.raises(MuseScoreBatchError, match="whole number"):
        score.to_ticks(1, 480, "op 0")


def test_present_shapes(objects) -> None:
    lyric = at(objects, 1, 1, 3)
    assert lyric["text"] == "Glo" and lyric["verse"] == 1 and lyric["syllabic"] == 1
    assert at(objects, 1, 1, 4)["lineType"] == "Slur"
    rest_ = at(objects, 1, 1, 6)
    assert rest_["rest"] and "notes" not in rest_
    assert at(objects, 0, 1, 0)["text"] == "Allegro" and "voice" not in at(objects, 0, 1, 0)


def test_query_filters(objects) -> None:
    def q(**kw):
        selector = {"staves": [], "types": [], "where": [], "fields": [], "voice": 0, "limit": 500, **kw}
        return score.query(objects, selector)

    assert all(o["staff"] != 0 for o in q()["objects"])
    assert [o["text"] for o in q(staves=[0])["objects"]] == ["Allegro"]
    assert [o["position"] for o in q(types=["Rest"])["objects"]] == [512]
    assert q(types=["Dynamic"])["count"] == 1 and q(types=["Slur"])["count"] == 1
    high = q(where=[{"prop": "Pitch", "op": ">=", "value": 65}])
    assert [o["notes"][-1]["pitch"] for o in high["objects"]][:2] == [65, 67]
    assert q(voice=2)["count"] == 1
    with_fields = q(types=["Chord"], fields=["Dx", "NoteCount"], limit=1)
    assert with_fields["truncated"] and with_fields["objects"][0]["NoteCount"] == 1
    assert "_ref" not in with_fields["objects"][0]


def test_prepare_set_maps_properties(objects) -> None:
    primitives, digests = prepare(objects, [
        {"op": "set", "staff": 1, "bar": 1, "index": 2, "type": "NoteRest", "position": 0, "prop": "Dy", "value": 16},
        {"op": "set", "staff": 1, "bar": 1, "index": 2, "prop": "Hidden", "value": True},
        {"op": "set", "staff": 1, "bar": 1, "index": 3, "prop": "Duration", "value": 512},
        {"op": "set", "staff": 0, "bar": 1, "index": 0, "prop": "Dx", "value": -64},
    ])
    assert [(p["prop"], p.get("value"), p.get("ticks")) for p in primitives] == [
        ("offsetY", -0.5, None), ("visible", False, None), ("lyricTicks", None, 960), ("offsetX", -2.0, None),
    ]
    assert digests == {"0:1": "s1", "1:1": "a1"}
    assert primitives[0]["label"] == "op 0" and primitives[0]["ref"]["raw"] == 0


def test_prepare_refusals(objects) -> None:
    cases = [
        ({"op": "set", "staff": 1, "bar": 1, "index": 2, "type": "Text", "prop": "Dx", "value": 1}, "not a Text"),
        ({"op": "set", "staff": 1, "bar": 1, "index": 2, "position": 256, "prop": "Dx", "value": 1}, "position 0"),
        ({"op": "tie", "staff": 1, "bar": 1, "index": 6}, "needs a chord"),
        ({"op": "set", "staff": 1, "bar": 1, "index": 9, "prop": "Dx", "value": 1}, "nothing at"),
        ({"op": "set", "staff": 1, "bar": 1, "index": 3, "prop": "NumNotes", "value": 2}, "Duration instead"),
        ({"op": "set", "staff": 1, "bar": 1, "index": 2, "prop": "Beam", "value": 9}, "beam mode"),
        ({"op": "set-pitch", "staff": 1, "bar": 1, "index": 5, "oldPitch": 60, "newPitch": 61}, "no note with pitch 60"),
        ({"op": "set-pitch", "staff": 1, "bar": 1, "index": 5, "oldPitch": 62, "newPitch": 65}, "already has"),
        ({"op": "flip-stem", "staff": 1, "bar": 1, "index": 2, "pitch": 61}, "no note of pitch 61"),
        ({"op": "delete", "staff": 1, "bar": 2, "index": 3, "ticks": 0}, "tick 160"),
        ({"op": "add-note", "staff": 1, "bar": 1, "position": 0, "duration": 256, "pitches": [60]}, "milestone 3"),
        ({"op": "set-key", "bar": 1, "key": "D"}, "milestone 4"),
        ({"op": "frobnicate"}, "must be one of"),
    ]
    for op, message in cases:
        with pytest.raises(MuseScoreBatchError, match=message):
            prepare(objects, [op])


def test_set_pitch_spells_concert_and_written(objects) -> None:
    [p], _ = prepare(objects, [{"op": "set-pitch", "staff": 1, "bar": 1, "index": 2, "oldPitch": 60, "newPitch": 62}])
    # Concert D on the B♭ clarinet is written E.
    assert (p["pitch"], p["tpc1"], p["tpc2"]) == (62, 16, 18)
    [p], _ = prepare(objects, [{"op": "set-pitch", "staff": 1, "bar": 1, "index": 2, "oldPitch": 60, "newPitch": 63,
                                "spelling": "D#"}])
    assert p["tpc1"] == score.tpc("D", 1) == 23 and p["tpc2"] == 25
    [p], _ = prepare(objects, [{"op": "set-pitch", "staff": 1, "bar": 1, "index": 2, "oldPitch": 60, "newPitch": 63}])
    assert p["tpc1"] == 11  # E♭ by default


def test_tpc_and_transposition() -> None:
    assert score.tpc("C", 0) == 14 and score.tpc("F", 1) == 20 and score.tpc("B", -1) == 12
    assert score.fifths_of(-1, -2) == -2  # B♭ instrument: concert = written + down a tone
    assert score.fifths_of(-2, -3) == 3  # A instrument: concert = written + down a minor third
    assert score.written_tpc(14, {"transposeDiatonic": -4, "transposeChromatic": -7}) == 15  # F horn: concert C is written G
    assert score.written_tpc(14, {}) == 14


def test_nudge_tie_bracket_flip(objects) -> None:
    primitives, _ = prepare(objects, [
        {"op": "nudge", "staff": 1, "bar": 1, "index": 1, "dx": 32, "dy": 16},
        {"op": "tie", "staff": 1, "bar": 1, "index": 2},
        {"op": "bracket", "staff": 1, "bar": 1, "index": 5, "remove": True},
        {"op": "flip-stem", "staff": 1, "bar": 1, "index": 5, "pitch": 65},
        {"op": "delete", "staff": 1, "bar": 1, "index": 4, "type": "Slur"},
    ])
    assert [(p["op"], p.get("dx"), p.get("dy"), p.get("on")) for p in primitives] == [
        ("nudge", 1.0, -0.5, None), ("tie", None, None, True), ("bracket", None, None, False),
        ("flip-stem", None, None, None), ("delete", None, None, None),
    ]


def test_beam_marks_begin_middle_and_breaks_after(objects) -> None:
    primitives, _ = prepare(objects, [{"op": "beam", "staff": 1, "bar": 2, "firstIndex": 1, "lastIndex": 5}])
    # Index 2 is voice 2, which stays out of a voice-1 beam.
    modes = [(p["ref"]["raw"], p["value"]) for p in primitives]
    assert modes == [(1, 2), (2, 5), (3, 5), (4, 5), (5, 2)]
    with pytest.raises(MuseScoreBatchError, match="endpoints"):
        prepare(objects, [{"op": "beam", "staff": 1, "bar": 2, "firstIndex": 0, "lastIndex": 3}])


def test_plugin_runs_every_primitive_score_emits() -> None:
    text = install.TEMPLATE.read_text()
    for method in ("Read", "ApplyBatch", "WriteCopy"):
        assert f'case "{method}"' in text
    for primitive in score.SUPPORTED - {"beam"}:
        assert f'case "{primitive}"' in text
    # Rolling back on failure and for a dry run, and an exact undo-step name.
    assert "s.endCmd(true)" in text and "s.endCmd(!!args.dryRun)" in text
    assert 'startCmd("AI batch")' in text


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
                before = chord(0, [60])
                after = dict(before, offsetY=-0.5) if p["op"] == "set" else before
                results.append({"before": before, "after": after})
            return {"applied": len(results), "dryRun": args["dryRun"], "results": results}
        raise KeyError(method)


@pytest.fixture
async def score_bridge():
    bridge = ScoreBridge()
    async with websockets.serve(bridge.serve, "127.0.0.1", 0) as server:
        bridge.port = server.sockets[0].getsockname()[1]
        yield bridge


async def test_service_query_resolves_staff_names(score_bridge) -> None:
    async with MuseScoreClient(port=score_bridge.port, token=TOKEN) as client:
        result = await service.query(MuseScoreBridge(client), staves=["clarinet in b♭"], types=["Rest"])
    assert result["count"] == 1
    assert score_bridge.requests[-1]["args"]["staves"] == [1]


async def test_service_dry_run_and_real_run(score_bridge, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    op = {"op": "set", "staff": 1, "bar": 1, "index": 2, "type": "NoteRest", "position": 0, "prop": "Dy", "value": 16}
    async with MuseScoreClient(port=score_bridge.port, token=TOKEN) as client:
        bridge = MuseScoreBridge(client)
        dry = await service.apply(bridge, [op], dry_run=True)
        assert dry["dryRun"] and "backup" not in dry
        assert dry["results"][0]["before"]["position"] == 0 and dry["results"][0]["after"]["dy"] == 16
        sent = score_bridge.requests[-1]["args"]
        assert sent["expect"] == {"name": "Scratch", "measures": 2, "staves": 2}
        assert sent["digests"] == {"1:1": "a1"} and sent["dryRun"] is True
        real = await service.apply(bridge, [op])
    assert real["undoSteps"] == 1 and real["applied"] == 1
    assert real["backup"].startswith(str(tmp_path)) and real["backup"].endswith(".musicxml")
    methods = [r["method"] for r in score_bridge.requests]
    assert methods.index("WriteCopy") < len(methods) - 1 and methods[-1] == "ApplyBatch"


def test_cli_query_parses(monkeypatch) -> None:
    args = cli.build_parser().parse_args(["query", "--staff", "1", "--bars", "2-3", "--where", "Pitch>60"])
    assert args.staves == ["1"] and args.bars == "2-3"
