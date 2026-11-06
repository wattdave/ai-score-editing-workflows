"""MuseScore service layer: turning operations into bridge primitives."""

from fractions import Fraction
import pytest

from ai_score_editing.musescore import install
from ai_score_editing.musescore.client import MuseScoreError
from ai_score_editing.core import intervals
from ai_score_editing.musescore import score, service
from ai_score_editing.musescore.score import MuseScoreBatchError
from ai_score_editing.musescore import window
from ai_score_editing.musescore import instruments

from musescore_common import STAVES, at, chord, make_read, objects, rest  # noqa: F401,F811


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


def test_ficta_hides_the_accidental_and_adds_a_sign_above(objects) -> None:
    primitives, _ = prepare(objects, [{"op": "ficta", "staff": 1, "bar": 1, "index": 2, "accidental": "flat"}])
    assert [p["op"] for p in primitives] == ["ficta-show", "remove-ficta-text", "add-text"]
    assert primitives[0]["on"] is False
    assert primitives[2]["text"] == "<sym>accidentalFlat</sym>"
    assert primitives[2]["element"] == "STAFF_TEXT"
    primitives, _ = prepare(objects, [{"op": "ficta", "staff": 1, "bar": 1, "index": 2, "remove": True}])
    assert [p["op"] for p in primitives] == ["ficta-show", "remove-ficta-text"]
    assert primitives[0]["on"] is True


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
          "styleId": "line.staff.hairpin.diminuendo"}, "only crescendo"),
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


def test_delete_bars_primitive(objects) -> None:
    primitives, _ = prepare(objects, [{"op": "delete-bars", "fromBar": 2, "toBar": 2}])
    assert primitives[0]["op"] == "delete-bars"
    assert (primitives[0]["fromBar"], primitives[0]["toBar"]) == (2, 2)
    with pytest.raises(MuseScoreBatchError, match="every bar"):
        prepare(objects, [{"op": "delete-bars", "fromBar": 1, "toBar": 2}])
    with pytest.raises(MuseScoreBatchError, match="no bar 3"):
        prepare(objects, [{"op": "delete-bars", "fromBar": 2, "toBar": 3}])
    with pytest.raises(MuseScoreBatchError, match="bar after"):
        prepare(objects, [{"op": "delete-bars", "fromBar": 1, "toBar": 1},
                          {"op": "set-key", "bar": 2, "key": "D"}])


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


def test_crescendo_hairpin_is_a_bridge_line(objects) -> None:
    primitives, _ = prepare(objects, [
        {"op": "add-line", "staff": 1, "bar": 1, "position": 0, "duration": 512,
         "styleId": "line.staff.hairpin.crescendo"}])
    assert primitives[0]["line"] == "hairpin" and primitives[0]["endTick"] == 960
    assert score.LINES_REFUSED and "hairpin" in " ".join(score.LINES_REFUSED)  # a diminuendo stays refused
