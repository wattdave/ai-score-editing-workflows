"""MuseScore back end: plug-in install, client protocol and version checks.

A fake bridge stands in for the plug-in on a free port; conftest.py fails any
connection to the real bridge's port.
"""

import json
from fractions import Fraction
import stat

import pytest
import websockets

from ai_score_editing.musescore import cli, install
from ai_score_editing.musescore.bridge import MuseScoreBridge, version_text
from ai_score_editing.musescore.client import MuseScoreClient, MuseScoreError

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
    with pytest.raises(MuseScoreError, match="Plugins > ScoreBridge"):
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
    assert out["installed"].endswith("ScoreBridge/msbridge.qml")


# ------------------------------------------------------------------ milestone 2: reads and batches

from ai_score_editing import intervals  # noqa: E402
from ai_score_editing.musescore import score, service  # noqa: E402
from ai_score_editing.musescore.score import MuseScoreBatchError  # noqa: E402

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
    primitives, touched, _ = score.prepare_batch(ops, objects, STAVES, 480, digests, make_read()["bars"])
    return primitives, touched


def prepare_copy(objects, ops, structure=None):
    digests = {(c["staff"], c["bar"]): c["digest"] for c in make_read()["content"]}
    return score.prepare_batch(ops, objects, STAVES, 480, digests, make_read()["bars"], structure)


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


def test_grace_notes_are_listed_before_their_chord_and_read_only() -> None:
    read = make_read()
    grace = {**chord(2400, [71], duration=240), "kind": "GraceNote", "noteType": 1}
    for key in ("beamMode", "inTuplet", "stemDirection", "up"):
        grace.pop(key)
    bar2 = read["content"][3]["objects"]
    bar2.insert(bar2.index(next(o for o in bar2 if o["tick"] == 2400)), grace)
    objects = score.locate(read)
    found = [o for o in objects if o["type"] == "GraceNote"]
    assert len(found) == 1
    g = found[0]
    assert g["graceType"] == "acciaccatura" and g["position"] == 256 and g["notes"][0]["pitch"] == 71
    assert at(objects, 1, 2, g["index"] + 1)["notes"][0]["pitch"] == 69
    assert score.query(objects, {"staves": [], "types": ["GraceNote"], "where": [], "fields": [], "voice": 0,
                                 "limit": 10})["count"] == 1
    digests = {(c["staff"], c["bar"]): c["digest"] for c in read["content"]}
    with pytest.raises(MuseScoreBatchError, match="read-only"):
        score.prepare_batch([{"op": "nudge", "staff": 1, "bar": 2, "index": g["index"], "dx": 1, "dy": 0}],
                            objects, STAVES, 480, digests, read["bars"])


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
    for primitive in score.OBJECT_OPS - {"beam"}:
        assert f'case "{primitive}"' in text
    for primitive in ("add-note", "add-rest", "add-tuplet", "add-text", "add-clef", "add-lyric", "add-line",
                      "add-dynamic", "articulation", "add-tempo", "add-rehearsal-mark", "tie-at"):
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
                if "ref" not in p:
                    results.append({"added": rest(p["at"]["tick"], duration=p.get("ticks", 480))})
                    continue
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


# ------------------------------------------------------------------ milestone 3: adding


def test_note_values() -> None:
    assert score.note_value(480, 480) == Fraction(1, 4)
    assert score.note_value(720, 480) == Fraction(3, 8)  # dotted quarter
    assert score.note_value(900, 480) == Fraction(15, 32)  # triple-dotted quarter
    assert score.note_value(3840, 480) == Fraction(2, 1)  # breve
    assert score.note_value(600, 480) is None  # quarter + sixteenth: two notes


def test_add_note_primitives(objects) -> None:
    primitives, digests = prepare(objects, [
        {"op": "add-note", "staff": 1, "bar": 2, "position": 512, "duration": 384, "pitches": [61, 68],
         "spellings": ["Db", None], "voice": 2, "tied": True},
        {"op": "add-rest", "staff": 1, "bar": 1, "position": 768, "duration": 256},
    ])
    note, rest_, tie = primitives
    assert note["at"] == {"staff": 1, "bar": 2, "tick": 1920 + 960, "track": 1}
    assert (note["ticks"], note["z"], note["n"]) == (720, 3, 8)
    # D♭ concert on the B♭ clarinet is written E♭; no spelling lets MuseScore choose.
    assert note["notes"] == [{"pitch": 61, "tpc1": score.tpc("D", -1), "tpc2": score.tpc("E", -1)}, {"pitch": 68}]
    assert rest_["op"] == "add-rest" and rest_["at"]["tick"] == 1440
    # Ties run last, once every note exists.
    assert tie == {"op": "tie-at", "at": note["at"], "pitches": [61, 68], "label": "op 0"}
    assert digests == {"1:1": "a1", "1:2": "a2"}


def test_add_text_lyric_line_tuplet_clef(objects) -> None:
    primitives, _ = prepare(objects, [
        {"op": "add-text", "staff": 1, "bar": 1, "position": 0, "text": "dolce", "styleId": "text.staff.expression"},
        {"op": "add-text", "staff": 1, "bar": 1, "position": 0, "text": "pizz.", "styleId": "text.staff.technique"},
        {"op": "add-text", "staff": 0, "bar": 2, "position": 0, "text": "rit."},
        {"op": "add-lyric", "staff": 1, "bar": 1, "position": 256, "duration": 256, "text": "ri",
         "syllableType": "middle", "verse": 2},
        {"op": "add-line", "staff": 1, "bar": 1, "position": 0, "duration": 768, "styleId": "line.staff.slur.up"},
        {"op": "add-tuplet", "staff": 1, "bar": 2, "position": 512, "duration": 256, "actual": 3, "normal": 2,
         "notes": [[60], [], [64, 67]]},
        {"op": "add-clef", "staff": 1, "bar": 2, "position": 0, "clef": "clef.bass"},
    ])
    assert [p.get("element") for p in primitives[:3]] == ["EXPRESSION", "STAFF_TEXT", "SYSTEM_TEXT"]
    assert primitives[2]["at"] == {"staff": 0, "bar": 2, "tick": 1920, "track": 0}
    lyric = primitives[3]
    assert (lyric["verse"], lyric["hyphen"], lyric["ticks"]) == (1, True, 480)
    assert primitives[4]["line"] == "slur" and primitives[4]["endTick"] == 1440
    tuplet = primitives[5]
    assert (tuplet["z"], tuplet["n"], tuplet["baseZ"], tuplet["baseN"]) == (1, 4, 1, 8)
    assert tuplet["notes"] == [[{"pitch": 60}], [], [{"pitch": 64}, {"pitch": 67}]]
    assert primitives[6]["clefType"] == score.CLEF_TYPES["bass"] == 20


def test_dorico_note_ops(objects) -> None:
    primitives, _ = prepare(objects, [
        {"op": "add-dynamic", "staff": 1, "bar": 1, "index": 5, "type": "NoteRest", "dynamic": "mf"},
        {"op": "set-articulation", "staff": 1, "bar": 1, "index": 2, "articulation": "accent"},
        {"op": "add-slur", "staff": 1, "bar": 1, "index": 2},
        {"op": "add-tempo", "staff": 1, "bar": 2, "index": 1, "text": "q = 90"},
        {"op": "add-tempo", "staff": 1, "bar": 2, "index": 1, "text": "Allegro", "bpm": 132},
        {"op": "add-rehearsal-mark", "staff": 1, "bar": 2, "index": 1},
    ])
    dynamic, accent, slur, tempo, allegro, mark = primitives
    assert dynamic["text"] == "<sym>dynamicMezzo</sym><sym>dynamicForte</sym>" and dynamic["dynamicType"] == 8
    assert dynamic["at"] == {"staff": 1, "bar": 1, "tick": 480, "track": 0}
    assert accent["action"] == "add-sforzato"
    assert slur == {"op": "add-line", "at": {"staff": 1, "bar": 1, "tick": 0, "track": 0}, "line": "slur",
                    "endTick": None, "label": "op 2"}
    assert tempo["text"] == "<sym>metNoteQuarterUp</sym> = 90" and tempo["tempo"] == 1.5
    assert tempo["at"]["track"] == 0
    assert allegro["text"] == "Allegro" and allegro["tempo"] == 2.2
    assert mark["text"] == "A"
    assert [score._mark_letter(n) for n in (0, 25, 26)] == ["A", "Z", "AA"]


def test_adding_refusals(objects) -> None:
    note = {"op": "add-note", "staff": 1, "bar": 1, "position": 0, "duration": 256, "pitches": [60]}
    cases = [
        ({**note, "duration": 320}, "single note value"),
        ({**note, "position": 1024}, "cross the barline"),
        ({**note, "position": 768, "duration": 512}, "cross the barline"),
        ({**note, "bar": 9}, "no bar 9"),
        ({**note, "pitches": [60, 60]}, "same pitch twice"),
        ({**note, "spellings": ["C"]} | {"pitches": [60, 64]}, "one spelling"),
        ({"op": "add-line", "staff": 1, "bar": 1, "position": 0, "duration": 512,
          "styleId": "line.staff.hairpin.crescendo"}, "crashed MuseScore"),
        ({"op": "add-line", "staff": 1, "bar": 1, "position": 0, "duration": 512,
          "styleId": "line.staff.trill"}, "can add these lines"),
        ({"op": "add-tuplet", "staff": 1, "bar": 1, "position": 0, "duration": 256, "actual": 5, "normal": 3,
          "notes": [[60]]}, "one note value"),
        ({"op": "add-tuplet", "staff": 1, "bar": 1, "position": 0, "duration": 256, "actual": 3, "normal": 2,
          "notes": [[60]] * 4}, "up to 3 chords"),
        ({"op": "set-articulation", "staff": 1, "bar": 1, "index": 2, "articulation": "stress"}, "one of"),
        ({"op": "set-articulation", "staff": 1, "bar": 1, "index": 6, "articulation": "staccato"}, "needs a chord"),
        ({"op": "add-dynamic", "staff": 1, "bar": 1, "index": 1, "dynamic": "f"}, "needs a note or rest"),
        ({"op": "add-tempo", "staff": 1, "bar": 1, "index": 2, "text": "Allegro"}, "give bpm"),
        ({"op": "add-clef", "staff": 1, "bar": 1, "position": 0, "clef": "soprano"}, "clef must be"),
        ({"op": "add-lyric", "staff": 1, "bar": 1, "position": 0, "duration": 256, "text": "a", "verse": 0},
         "verse"),
    ]
    for op, message in cases:
        with pytest.raises(MuseScoreBatchError, match=message):
            prepare(objects, [op])


def test_object_ops_come_before_adding_ops(objects) -> None:
    add = {"op": "add-rest", "staff": 1, "bar": 1, "position": 0, "duration": 256}
    nudge = {"op": "nudge", "staff": 1, "bar": 1, "index": 2, "dx": 1}
    prepare(objects, [nudge, add])
    with pytest.raises(MuseScoreBatchError, match="must come before ops that add"):
        prepare(objects, [add, nudge])


async def test_service_reports_added_objects(score_bridge) -> None:
    op = {"op": "add-rest", "staff": 1, "bar": 2, "position": 256, "duration": 256}
    async with MuseScoreClient(port=score_bridge.port, token=TOKEN) as client:
        result = await service.apply(MuseScoreBridge(client), [op], dry_run=True)
    [report] = result["results"]
    assert report["primitive"] == "add-rest" and "before" not in report
    assert (report["added"]["bar"], report["added"]["position"], report["added"]["rest"]) == (2, 256, True)
    assert score_bridge.requests[-1]["args"]["digests"] == {"1:2": "a2"}


# ------------------------------------------------------------------ milestone 4: structure


def test_keys_and_spelling_helpers() -> None:
    assert score.key_fifths("Bb", True) == -2 and score.key_fifths("F#", False) == 3
    assert score.key_fifths("Cb", True) == -7 and score.key_fifths("A#", False) == 7
    assert [score.tpc_name(v) for v in (14, 20, 12, 7, 26)] == ["C", "F#", "Bb", "Cb", "B#"]
    clarinet = STAVES[0]
    assert score.written_key(0, clarinet) == 2  # concert C, written D
    assert score.written_key(6, clarinet) == -4  # F# major would be G# (8 sharps): written A♭ instead
    assert score.key_name(-3, True) == "Eb" and score.key_name(1, False) == "E"


def test_set_key_time_break_barline(objects) -> None:
    primitives, digests = prepare(objects, [
        {"op": "set-time", "bar": 2, "numerator": 2, "denominator": 2, "symbol": "cut"},
        {"op": "set-key", "bar": 2, "key": "D"},
        {"op": "set-break", "bar": 1, "type": "page"},
        {"op": "set-barline", "bar": 1, "type": "final"},
        {"op": "set-barline", "bar": 2, "type": "start_repeat"},
    ])
    time, key, brk, final, repeat = primitives
    assert time == {"op": "set-time", "bar": 2, "tick": 1920, "numerator": 2, "denominator": 2,
                    "timesigType": 2, "label": "op 0"}
    assert key["mode"] == 1 and key["tick"] == 1920
    assert key["staves"] == [{"staffIdx": 0, "concertKey": 2, "actualKey": 4},
                             {"staffIdx": 1, "concertKey": 2, "actualKey": 2}]
    assert brk["type"] == "page" and final["code"] == 0x20 and repeat["code"] is None
    assert digests == {}
    with pytest.raises(MuseScoreBatchError, match="no tick barline"):
        prepare(objects, [{"op": "set-barline", "bar": 1, "type": "tick"}])
    with pytest.raises(MuseScoreBatchError, match="no bar 9"):
        prepare(objects, [{"op": "set-break", "bar": 9, "type": "system"}])


def test_bars_numbers_and_hidden_staves(objects) -> None:
    primitives, _ = prepare(objects, [
        {"op": "set-bar-number", "bar": 1, "number": 10, "skip": True},
        {"op": "hide-empty-staves", "fromBar": 1, "toBar": 2},
        {"op": "add-bars", "count": 2, "bar": 2, "length": 768},
    ])
    assert primitives[0]["skip"] and primitives[0]["number"] == 10
    assert primitives[1]["values"] == {"hideEmptyStaves": True}
    assert (primitives[2]["count"], primitives[2]["bar"], primitives[2]["z"], primitives[2]["n"]) == (2, 2, 3, 4)
    cases = [
        ({"op": "set-bar-number", "bar": 2, "number": 5, "skip": True}, "bar after"),
        ({"op": "hide-empty-staves", "fromBar": 1, "toBar": 1}, "whole score"),
        ({"op": "add-bars", "count": 1, "bar": 3}, "no bar 3"),
    ]
    for op, message in cases:
        with pytest.raises(MuseScoreBatchError, match=message):
            prepare(objects, [op])


def test_set_layout_in_inches(objects) -> None:
    current = {"style": {"pageWidth": 8.5, "pageHeight": 11, "pageOddLeftMargin": 0.59,
                         "pagePrintableWidth": 7.32, "spatium": 82.68}}
    [p], _, _ = prepare_copy(objects, [{"op": "set-layout", "pageSize": "a4", "orientation": "landscape",
                                        "leftMargin": 20, "rightMargin": 10, "staffSize": 6,
                                        "aboveTopStaveGap": 12, "spacesBetweenSystems": 9}], current)
    values = p["values"]
    assert values["pageWidth"] == pytest.approx(297 / 25.4) and values["pageHeight"] == pytest.approx(210 / 25.4)
    assert values["pageOddLeftMargin"] == values["pageEvenLeftMargin"] == pytest.approx(20 / 25.4)
    assert values["pagePrintableWidth"] == pytest.approx((297 - 30) / 25.4)
    assert values["spatium"] == pytest.approx(1.5 / 25.4 * 1200)
    assert values["staffUpperBorder"] == pytest.approx(8) and values["minSystemDistance"] == 9
    # Only the margin given changes; the right margin is kept.
    [p], _, _ = prepare_copy(objects, [{"op": "set-layout", "leftMargin": 25.4}], current)
    assert p["values"]["pagePrintableWidth"] == pytest.approx(8.5 - 1 - (8.5 - 0.59 - 7.32))
    for op, message in [({"op": "set-layout", "pageSize": "octavo"}, "not available"),
                        ({"op": "set-layout", "extraSpacesBelowVocalStaves": 2}, "vocal"),
                        ({"op": "set-layout", "leftMargin": 150, "rightMargin": 150}, "no room")]:
        with pytest.raises(MuseScoreBatchError, match=message):
            prepare_copy(objects, [op], current)


def test_transpose_respells_and_moves_keys(objects) -> None:
    for item in objects:  # the fixture spells every note C; spell them as read from a real score
        for n in item.get("notes", []):
            letter = intervals.spelling_letter(n["pitch"])
            n["tpc1"] = score.tpc(letter, intervals.alteration(n["pitch"], letter))
    keyed = objects + [{
        "staff": 1, "bar": 2, "type": "KeySignature", "position": 0, "ticks": 0, "msType": "KeySig",
        "voice": 1, "hidden": False, "concertKey": -1, "writtenKey": 1, "index": 99,
        "_ref": {"staff": 1, "bar": 2, "raw": 99, "type": "KeySig", "tick": 1920},
    }]
    primitives, _ = prepare(keyed, [{"op": "transpose", "fromBar": 1, "toBar": 2, "topStaff": 1,
                                     "bottomStaff": 1, "fromNote": "C", "toNote": "Eb", "direction": "up"}])
    repitch = [p for p in primitives if p["op"] == "repitch"]
    first = repitch[0]["notes"][0]
    assert (first["oldPitch"], first["pitch"], first["tpc1"]) == (60, 63, score.tpc("E", -1))
    assert first["tpc2"] == score.tpc("F", 0)  # written for the B♭ clarinet
    chord = repitch[1]["notes"]
    assert [n["pitch"] for n in chord] == [65, 68]  # D, F up a minor third: F, A♭
    [key] = [p for p in primitives if p["op"] == "set-key"]
    assert key["mode"] is None and key["staves"] == [{"staffIdx": 0, "concertKey": -4, "actualKey": -2}]


def test_delete_voice_and_copy_passage(objects) -> None:
    primitives, _ = prepare(objects, [{"op": "delete-voice", "staff": 1, "voice": 1, "fromBar": 1, "toBar": 2}])
    # Voice 1: chords only, not rests, and not tuplet members.
    assert [p["ref"]["tick"] for p in primitives] == [0, 480, 2400, 2640, 2880]
    primitives, _ = prepare(objects, [{"op": "delete-voice", "staff": 1, "voice": 2, "fromBar": 2, "toBar": 2}])
    assert len(primitives) == 1
    primitives, _, copy = prepare_copy(objects, [{"op": "copy-passage", "fromBar": 1, "toBar": 1, "topStaff": 1,
                                                  "bottomStaff": 2, "destStaff": 1, "destBar": 2}])
    assert copy == {"startTick": 0, "endTick": 1920, "staffStart": 0, "staffEnd": 2}
    assert primitives == [{"op": "paste", "at": {"staff": 1, "bar": 2, "tick": 1920, "track": 0}, "label": "op 0"}]
    cases = [
        ({"op": "copy-passage", "fromBar": 1, "toBar": 2, "topStaff": 1, "bottomStaff": 1, "destStaff": 1,
          "destBar": 2}, "past the last bar"),
        ({"op": "copy-passage", "fromBar": 1, "toBar": 1, "topStaff": 1, "bottomStaff": 2, "destStaff": 2,
          "destBar": 2}, "past the last staff"),
    ]
    for op, message in cases:
        with pytest.raises(MuseScoreBatchError, match=message):
            prepare(objects, [op])
    copy_op = cases[0][0] | {"toBar": 1}
    with pytest.raises(MuseScoreBatchError, match="one copy-passage"):
        prepare(objects, [copy_op, copy_op])


def test_structural_ordering(objects) -> None:
    add = {"op": "add-rest", "staff": 1, "bar": 1, "position": 0, "duration": 256}
    transpose = {"op": "transpose", "fromBar": 1, "toBar": 1, "topStaff": 1, "bottomStaff": 1, "degree": 1,
                 "intervalType": 4}
    with pytest.raises(MuseScoreBatchError, match="as its own batch"):
        prepare(objects, [add, transpose])
    with pytest.raises(MuseScoreBatchError, match="as its own batch"):
        prepare(objects, [{"op": "add-bars", "count": 1}, transpose | {"op": "delete-voice", "staff": 1,
                                                                        "voice": 2}])
    with pytest.raises(MuseScoreBatchError, match="set-time must come first"):
        prepare(objects, [{"op": "set-bar-number", "bar": 1, "number": 3},
                          {"op": "set-time", "bar": 1, "numerator": 3, "denominator": 4}])
    with pytest.raises(MuseScoreBatchError, match="changes nothing"):
        prepare(objects, [{"op": "delete-voice", "staff": 1, "voice": 3, "fromBar": 1, "toBar": 2}])


def test_structure_report() -> None:
    raw = {
        "division": 480, "barCount": 3,
        "bars": [{"bar": 1, "ticks": 1920, "no": 0}, {"bar": 2, "ticks": 1440, "no": 1},
                 {"bar": 3, "ticks": 1920, "no": 9}],
        "timeSignatures": [{"bar": 1, "numerator": 4, "denominator": 4, "timesigType": 1}],
        "keySignatures": [{"bar": 1, "staff": 1, "concertKey": -2, "actualKey": 0, "mode": 1},
                          {"bar": 1, "staff": 2, "concertKey": -2, "actualKey": -2, "mode": 1},
                          {"bar": 3, "staff": 2, "concertKey": 0, "actualKey": 0, "mode": 2}],
        "barlines": [{"bar": 1, "barlineType": 2, "visible": True, "repeatStart": False, "repeatEnd": False},
                     {"bar": 2, "barlineType": 1, "visible": True, "repeatStart": True, "repeatEnd": True}],
        "breaks": [{"bar": 2, "type": "system"}],
        "barNumbers": [{"bar": 2, "noOffset": 0, "irregular": True}, {"bar": 3, "noOffset": 8, "irregular": False}],
        "style": {"pageWidth": 8.5, "pageHeight": 11, "pagePrintableWidth": 7.5, "pageOddLeftMargin": 0.5,
                  "pageOddTopMargin": 0.59, "pageOddBottomMargin": 0.59, "spatium": 82.68,
                  "staffUpperBorder": 7, "staffLowerBorder": 7, "staffDistance": 6.5, "minSystemDistance": 8.5,
                  "hideEmptyStaves": False},
    }
    report = score.structure_report(raw, STAVES)
    assert report["timeSignatures"] == [{"bar": 1, "numerator": 4, "denominator": 4, "symbol": "common"}]
    assert report["keySignatures"] == [
        {"bar": 1, "sharps": -2, "major": True, "name": "Bb", "writtenKeys": {1: 0, 2: -2}},
        {"bar": 3, "sharps": 0, "major": False, "name": "A"},
    ]
    assert report["barlines"] == [{"bar": 1, "type": "double"}, {"bar": 2, "type": "start_repeat"},
                                  {"bar": 2, "type": "end_repeat"}]
    assert report["barNumbers"] == [{"bar": 2, "skip": True}, {"bar": 3, "shownAs": 10}]
    assert report["irregularBars"] == [{"bar": 2, "length": 768}]
    layout = report["layout"]
    assert layout["pageSize"] == "letter" and layout["staffSize"] == 7.0 and layout["rightMargin"] == 12.7


# ------------------------------------------------------------------ milestone 5: files, metadata, lyrics

from ai_score_editing.musescore import window  # noqa: E402


def syllable(bar, ticks, text, syllabic, voice=1, verse=1):
    return {"type": "LyricItem", "staff": 1, "bar": bar, "ticks": ticks, "voice": voice, "verse": verse,
            "text": text, "syllabic": syllabic, "_ref": {"staff": 1, "bar": bar, "raw": ticks, "type": "Lyrics"}}


def test_plugin_has_milestone_5_methods() -> None:
    text = install.TEMPLATE.read_text()
    for method in ("Save", "GetMetaTags", "SetMetaTags"):
        assert f'case "{method}"' in text
    assert 'root.cmd("file-save")' in text
    for ext in ("xml", "png", "svg", "mp3", "wav", "flac", "ogg"):
        assert f'"{ext}": true' in text


def test_lyric_text_and_split() -> None:
    line = [syllable(2, 240, "king", 2), syllable(2, 0, "Ma", 1), syllable(3, 0, "a", 0),
            syllable(3, 0, "x", 0, verse=2), syllable(3, 480, "joy", 1), syllable(4, 0, "ful", 2)]
    ordered = score.lyric_line(line, 1, 1)
    assert [s["text"] for s in ordered] == ["Ma", "king", "a", "joy", "ful"]
    assert score.lyric_text(ordered) == "Ma-king a joy-ful"
    assert score.split_lyrics("Ma-king  a joy-ous-ly") == [
        ("Ma", 1), ("king", 2), ("a", 0), ("joy", 1), ("ous", 3), ("ly", 2)]
    assert score.lyric_text([syllable(1, 0, "dan", 1)]) == "dan"


def test_lyric_edits_change_only_what_differs() -> None:
    line = [syllable(2, 0, "Ma", 1), syllable(2, 240, "king", 2), syllable(3, 0, "a", 0)]
    digests = {(1, 2): "d2", (1, 3): "d3"}
    primitives, touched = score.lyric_edits(line, "Mak-ing a", digests, 1, 1)
    assert [(p["prop"], p["value"]) for p in primitives] == [("text", "Mak"), ("text", "ing")]
    assert touched == {"1:2": "d2"}
    primitives, touched = score.lyric_edits(line, "Ma king-a", digests, 1, 1)
    assert [(p["prop"], p["value"]) for p in primitives] == [("syllabic", 0), ("syllabic", 1), ("syllabic", 2)]
    assert touched == {"1:2": "d2", "1:3": "d3"}
    with pytest.raises(MuseScoreBatchError, match="2 syllables"):
        score.lyric_edits(line, "Making a", digests, 1, 1)
    with pytest.raises(MuseScoreBatchError, match="no lyrics"):
        score.lyric_edits([], "x", digests, 1, 2)


def test_score_file_from_window_documents() -> None:
    found = [("Other", "file:///tmp/Other.mscz"),
             ("My Score", "file:///Users/me/Scores/My%20Score.mscz")]
    assert str(window.score_file("My Score", found)) == "/Users/me/Scores/My Score.mscz"
    assert window.score_file("Untitled", found) is None


def test_metadata_names() -> None:
    known = ["workTitle", "composer", "lyricist"]
    assert service._tag_name("Title", known) == "workTitle"
    assert service._tag_name("Composer", known) == "composer"
    with pytest.raises(MuseScoreError, match="unknown metadata field"):
        service._tag_name("Publisher", known)


class FilesBridge(ScoreBridge):
    """ScoreBridge plus Save, metadata and lyric edits."""

    def __init__(self, scorefile):
        super().__init__()
        self.scorefile = scorefile
        self.tags = {"workTitle": "Untitled", "composer": "", "lyricist": ""}

    def respond(self, method, args):
        if method == "Save":
            self.scorefile.write_bytes(self.scorefile.read_bytes() + b"!")
            return {"saved": True}
        if method == "GetMetaTags":
            return dict(self.tags)
        if method == "SetMetaTags":
            before = {t: self.tags[t] for t in args["tags"]}
            self.tags.update(args["tags"])
            return {"before": before, "after": dict(self.tags)}
        if method == "WriteCopy":
            from pathlib import Path
            path = Path(args["path"])
            if args["format"] in {"png", "svg"}:
                for page in (1, 2):
                    path.with_name(f"{path.stem}-{page}{path.suffix}").write_text("page")
            else:
                path.write_text("data")
            return {"written": True, "path": args["path"]}
        return super().respond(method, args)


@pytest.fixture
async def files_bridge(tmp_path):
    scorefile = tmp_path / "Scratch.mscz"
    scorefile.write_bytes(b"PK")
    bridge = FilesBridge(scorefile)
    async with websockets.serve(bridge.serve, "127.0.0.1", 0) as server:
        bridge.port = server.sockets[0].getsockname()[1]
        yield bridge


async def test_save_writes_in_place_and_copies(files_bridge, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(window, "windows", lambda: [("Scratch", files_bridge.scorefile.as_uri())])
    async with MuseScoreClient(port=files_bridge.port, token=TOKEN) as client:
        bridge = MuseScoreBridge(client)
        result = await service.save(bridge, str(tmp_path / "out" / "copy.mscz"))
        assert result["saved"] == str(files_bridge.scorefile)
        assert (tmp_path / "out" / "copy.mscz").read_bytes() == b"PK!"
        with pytest.raises(MuseScoreError, match="must end in .mscz"):
            await service.save(bridge, str(tmp_path / "copy.pdf"))
        monkeypatch.setattr(window, "windows", lambda: [])
        with pytest.raises(MuseScoreError, match="never been saved"):
            await service.save(bridge)


async def test_export_formats_and_pages(files_bridge, tmp_path) -> None:
    async with MuseScoreClient(port=files_bridge.port, token=TOKEN) as client:
        bridge = MuseScoreBridge(client)
        pdf = await service.export(bridge, "pdf", str(tmp_path / "s.pdf"))
        assert pdf == {"files": [str(tmp_path / "s.pdf")]}
        xml = await service.export(bridge, "musicxml", str(tmp_path / "s.xml"))
        assert files_bridge.requests[-1]["args"]["format"] == "xml" and xml["files"] == [str(tmp_path / "s.xml")]
        png = await service.export(bridge, "png", str(tmp_path / "p.png"))
        assert png["files"] == [str(tmp_path / "p-1.png"), str(tmp_path / "p-2.png")]
        with pytest.raises(MuseScoreError, match="must end in .pdf"):
            await service.export(bridge, "pdf", str(tmp_path / "s.png"))
        with pytest.raises(MuseScoreError, match="format must be one of"):
            await service.export(bridge, "mscz", str(tmp_path / "s.mscz"))


async def test_project_info_round_trip(files_bridge) -> None:
    async with MuseScoreClient(port=files_bridge.port, token=TOKEN) as client:
        bridge = MuseScoreBridge(client)
        result = await service.set_project_info(bridge, {"Title": "Gloria", "composer": "Anon."})
        assert result["before"] == {"workTitle": "Untitled", "composer": ""}
        assert result["after"] == {"workTitle": "Gloria", "composer": "Anon."}
        assert (await service.project_info(bridge))["fields"]["workTitle"] == "Gloria"


async def test_read_lyrics_from_fixture(score_bridge) -> None:
    async with MuseScoreClient(port=score_bridge.port, token=TOKEN) as client:
        result = await service.read_lyrics(MuseScoreBridge(client), "Clarinet in B♭")
    assert result == {"staff": 1, "verse": 1, "text": "Glo", "syllables": 1, "bars": "1-1"}


def test_cli_files_commands_parse() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["export", "--format", "png", "--path", "x.png"]).format == "png"
    assert parser.parse_args(["set-info", "--field", "composer=Anon."]).field == ["composer=Anon."]
    assert parser.parse_args(["edit-lyrics", "--staff", "1", "--text", "a b"]).verse == 1


# ------------------------------------------------------------------ milestone 6: parts and playback

from ai_score_editing.musescore import instruments  # noqa: E402


def test_plugin_has_milestone_6_methods() -> None:
    text = install.TEMPLATE.read_text()
    for method in ("AddPart", "SetStaffPlayback"):
        assert f'case "{method}"' in text
    assert "part.instrumentId !== args.instrumentId" in text and ".play = on" in text


def test_instrument_lookup() -> None:
    assert instruments.resolve("violin") == {"instrumentId": "violin"}
    assert instruments.resolve("Violin") == {"instrumentId": "violin"}
    assert instruments.resolve("voice.soprano") == {"instrumentId": "soprano"}
    with pytest.raises(MuseScoreError, match="several instruments.*bb-clarinet"):
        instruments.resolve("Clarinet")
    with pytest.raises(MuseScoreError, match="close: violin"):
        instruments.resolve("violn")


class PartsBridge(ScoreBridge):
    def respond(self, method, args):
        if method == "AddPart":
            return {"added": {"partName": "Violin", "instrumentId": args["instrumentId"], "staves": 1},
                    "dryRun": args["dryRun"]}
        if method == "SetStaffPlayback":
            return {"staff": args["staff"], "notesChanged": 2,
                    "playback": [v is None for v in args["voices"]]}
        if method == "GetStaves":
            return [dict(s, part=s["staff"], instrumentId="x") for s in STAVES]
        return super().respond(method, args)


@pytest.fixture
async def parts_bridge():
    bridge = PartsBridge()
    async with websockets.serve(bridge.serve, "127.0.0.1", 0) as server:
        bridge.port = server.sockets[0].getsockname()[1]
        yield bridge


async def test_add_instrument_and_playback(parts_bridge) -> None:
    async with MuseScoreClient(port=parts_bridge.port, token=TOKEN) as client:
        bridge = MuseScoreBridge(client)
        dry = await service.add_instrument(bridge, "Violin", dry_run=True)
        assert dry["dryRun"] and "undoSteps" not in dry
        assert parts_bridge.requests[-1]["args"] == {"instrumentId": "violin", "dryRun": True}
        real = await service.add_instrument(bridge, "violin")
        assert real["undoSteps"] == 1 and real["staves"][0]["staff"] == 2
        result = await service.set_staff_playback(bridge, ["Piano", "1", "2"], False, [1, 3])
        assert [s["staff"] for s in result["staves"]] == [2, 1] and result["undoSteps"] == 2
        assert parts_bridge.requests[-1]["args"]["voices"] == [False, None, False, None]
        with pytest.raises(MuseScoreError, match="voices are 1-4"):
            await service.set_staff_playback(bridge, ["1"], True, [5])
