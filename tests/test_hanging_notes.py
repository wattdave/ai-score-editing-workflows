"""Tests for hanging playback notes diagnosis and audit functions."""

from __future__ import annotations

from pathlib import Path

from helpers import load_script

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPT_PATH = ROOT_DIR / ".claude" / "skills" / "hanging-playback-note-repair" / "scripts" / "hanging_notes.py"

hanging_notes = load_script(SCRIPT_PATH)


def test_pitch_to_name() -> None:
    assert hanging_notes.pitch_to_name(60) == "C4"
    assert hanging_notes.pitch_to_name(42) == "F#2"
    assert hanging_notes.pitch_to_name(69) == "A4"


def test_audit_score_data_clean() -> None:
    bars = [
        {
            "barNumber": 1,
            "objects": [
                {
                    "type": "NoteRest",
                    "index": 0,
                    "position": 0,
                    "duration": 512,
                    "voice": 1,
                    "notes": [{"pitch": 60, "name": "C4", "tied": True}],
                },
                {
                    "type": "NoteRest",
                    "index": 1,
                    "position": 512,
                    "duration": 512,
                    "voice": 1,
                    "notes": [{"pitch": 60, "name": "C4", "tied": False}],
                },
            ],
        }
    ]
    res = hanging_notes.audit_score_data(bars, staff_num=1)
    assert len(res["dangling"]) == 0
    assert len(res["tuplet_ties"]) == 0
    assert len(res["reattacks"]) == 0


def test_audit_score_data_dangling_tie_to_rest() -> None:
    bars = [
        {
            "barNumber": 1,
            "objects": [
                {
                    "type": "NoteRest",
                    "index": 0,
                    "position": 0,
                    "duration": 512,
                    "voice": 1,
                    "notes": [{"pitch": 60, "name": "C4", "tied": True}],
                },
                {
                    "type": "NoteRest",
                    "index": 1,
                    "position": 512,
                    "duration": 512,
                    "voice": 1,
                    "notes": [],  # rest
                },
            ],
        }
    ]
    res = hanging_notes.audit_score_data(bars, staff_num=1)
    assert len(res["dangling"]) == 1
    assert "rest" in res["dangling"][0]["reason"]


def test_audit_score_data_dangling_tie_pitch_mismatch() -> None:
    bars = [
        {
            "barNumber": 1,
            "objects": [
                {
                    "type": "NoteRest",
                    "index": 0,
                    "position": 0,
                    "duration": 512,
                    "voice": 1,
                    "notes": [{"pitch": 60, "name": "C4", "tied": True}],
                },
                {
                    "type": "NoteRest",
                    "index": 1,
                    "position": 512,
                    "duration": 512,
                    "voice": 1,
                    "notes": [{"pitch": 62, "name": "D4", "tied": False}],
                },
            ],
        }
    ]
    res = hanging_notes.audit_score_data(bars, staff_num=1)
    assert len(res["dangling"]) == 1
    assert "mismatch" in res["dangling"][0]["reason"]


def test_audit_score_data_tuplet_boundary_tie() -> None:
    bars = [
        {
            "barNumber": 1,
            "objects": [
                {
                    "type": "Tuplet",
                    "index": 0,
                    "position": 256,
                },
                {
                    "type": "NoteRest",
                    "index": 1,
                    "position": 0,
                    "duration": 256,
                    "voice": 1,
                    "notes": [{"pitch": 60, "name": "C4", "tied": True}],
                },
                {
                    "type": "NoteRest",
                    "index": 2,
                    "position": 256,
                    "duration": 170,
                    "voice": 1,
                    "notes": [{"pitch": 60, "name": "C4", "tied": False}],
                },
            ],
        }
    ]
    res = hanging_notes.audit_score_data(bars, staff_num=1)
    assert len(res["tuplet_ties"]) == 1
    assert "tuplet" in res["tuplet_ties"][0]["reason"]


def test_audit_score_data_reattack_conflict() -> None:
    # Bar 59 reproduction:
    # Note 1: F#2 pos=0 dur=512 tied=True
    # Note 2: F#2 pos=512 dur=128 tied=False
    # Note 3: F#2 pos=640 dur=384 tied=False (re-attack!)
    bars = [
        {
            "barNumber": 59,
            "objects": [
                {
                    "type": "NoteRest",
                    "index": 0,
                    "position": 0,
                    "duration": 512,
                    "voice": 1,
                    "notes": [{"pitch": 42, "name": "F#2", "tied": True}],
                },
                {
                    "type": "NoteRest",
                    "index": 1,
                    "position": 512,
                    "duration": 128,
                    "voice": 1,
                    "notes": [{"pitch": 42, "name": "F#2", "tied": False}],
                },
                {
                    "type": "NoteRest",
                    "index": 2,
                    "position": 640,
                    "duration": 384,
                    "voice": 1,
                    "notes": [{"pitch": 42, "name": "F#2", "tied": False}],
                },
            ],
        }
    ]
    res = hanging_notes.audit_score_data(bars, staff_num=16)
    assert len(res["reattacks"]) == 1
    assert res["reattacks"][0]["reattack_bar"] == 59
    assert res["reattacks"][0]["reattack_position"] == 640
    assert "SoundWorld drops Note-Off" in res["reattacks"][0]["reason"]
