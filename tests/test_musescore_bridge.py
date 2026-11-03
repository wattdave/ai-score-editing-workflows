"""MuseScore bridge round trips through a fake plug-in: queries, batches, files, parts."""

import pytest
import websockets

from ai_score_editing.musescore.bridge import MuseScoreBridge
from ai_score_editing.musescore.client import MuseScoreClient, MuseScoreError
from ai_score_editing.musescore import service
from ai_score_editing.musescore import window

from musescore_common import STAVES, ScoreBridge, TOKEN, rest  # noqa: F401,F811


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


async def test_service_reports_added_objects(score_bridge) -> None:
    op = {"op": "add-rest", "staff": 1, "bar": 2, "position": 256, "duration": 256}
    async with MuseScoreClient(port=score_bridge.port, token=TOKEN) as client:
        result = await service.apply(MuseScoreBridge(client), [op], dry_run=True)
    [report] = result["results"]
    assert report["primitive"] == "add-rest" and "before" not in report
    assert (report["added"]["bar"], report["added"]["position"], report["added"]["rest"]) == (2, 256, True)
    assert score_bridge.requests[-1]["args"]["digests"] == {"1:2": "a2"}


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
