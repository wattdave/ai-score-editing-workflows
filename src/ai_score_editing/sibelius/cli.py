"""Command-line interface (docs/sibelius-protocol.md 2.2)."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import math
import os
import sys
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from ai_score_editing import (
    abc_notation,
    agent_output,
    batch_ops,
    batch_lyrics,
    layout,
    lyrics,
    mix_proof,
    music,
    note_patches,
    polychoral,
    rehearsal_mix,
)
from ai_score_editing.barrange import parse_bar_range
from ai_score_editing.intervals import compute_transposition
from ai_score_editing.sibelius import launcher, protocol, repeats
from ai_score_editing.sibelius.client import ConnectionFailed, SibeliusClient, run_sync
from ai_score_editing.token_store import TokenStore

EXIT_OK = 0
EXIT_COMMAND_FAILED = 1
EXIT_CONNECTION_FAILED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sibelius-cli",
        description="Drive Sibelius via its Sibelius Connect WebSocket interface.",
    )
    parser.add_argument("--host", default=protocol.DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=protocol.DEFAULT_PORT)
    parser.add_argument("--client-name", default=protocol.DEFAULT_CLIENT_NAME)
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="seconds to wait for connection approval in Sibelius",
    )
    parser.add_argument(
        "--launch",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="start Sibelius if not already running (default: True)",
    )
    parser.add_argument(
        "--launch-timeout",
        type=float,
        default=30.0,
        help="seconds to wait for Sibelius to start and open port (default: 30)",
    )
    parser.add_argument(
        "--sibelius-path",
        help="custom path to Sibelius application or executable",
    )
    parser.add_argument("--json", action="store_true", help="print raw JSON responses")
    parser.add_argument(
        "--expect-file",
        help="refuse writes unless the active score resolves to this path",
    )
    parser.add_argument(
        "--backup-dir",
        help="put the timestamped .sib backups of write commands in this folder instead of "
        "beside the score (default: the SIBELIUS_BACKUP_DIR environment variable, else beside the score)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log the wire traffic")

    sub = parser.add_subparsers(dest="subcommand", required=True)
    sub.add_parser("ping", help="check that Sibelius responds")
    sub.add_parser("save", help="save the active score in Sibelius")
    cmd = sub.add_parser("command", help="send a single command and print the response")
    cmd.add_argument("command_name")
    invoke = sub.add_parser("invoke", help="send a batch of command IDs via invokeCommands")
    invoke.add_argument("command_ids", nargs="+")
    raw = sub.add_parser("raw", help="send arbitrary JSON (protocol exploration)")
    raw.add_argument("json_message", help="a JSON object, e.g. '{\"message\": \"connect\"}'")
    sub.add_parser(
        "repl",
        help="interactive: bare words are sent as commands, JSON objects as raw messages",
    )
    plugin = sub.add_parser("plugin", help="call a ManuScript plug-in via invokePlugin")
    plugin.add_argument("name", help="plug-in file name without extension")
    plugin.add_argument("method", nargs="?", help="method to call (default: Run)")
    plugin.add_argument(
        "--args",
        dest="plugin_args",
        help='JSON array of arguments, e.g. \'[42, "text"]\'',
    )
    sub.add_parser(
        "score-info",
        help="read info about the open score (requires the bundled ScoreBridge plug-in)",
    )
    sub.add_parser("staves", help="list staves of the open score (requires bridge plug-in)")
    sub.add_parser("selection", help="describe the current selection (requires bridge plug-in)")
    sub.add_parser(
        "inspect",
        help="compact score identity, staff, and selection summary",
    )
    snapshot = sub.add_parser(
        "score-snapshot",
        help="compact structural snapshot from one bridge session",
    )
    snapshot.add_argument("--bars", help="bar range for optional lyrics and barlines, e.g. '1-30'")
    snapshot.add_argument("--staff", type=int, default=0, help="staff for optional lyrics (0 = all)")
    snapshot.add_argument("--lyrics", action="store_true", help="include compact lyric data")
    snapshot.add_argument(
        "--no-barlines",
        dest="barlines",
        action="store_false",
        help="omit special barlines from the snapshot",
    )
    snapshot.set_defaults(barlines=True)
    proofread = sub.add_parser(
        "proofread",
        help="read-only structural and lyric proofreading report",
    )
    proofread.add_argument("--bars", help="bar range to inspect, e.g. '1-30'")
    proofread.add_argument("--staff", type=int, default=0, help="staff to inspect (0 = all lyric-bearing staves)")
    proofread.add_argument("--lyrics", action="store_true", help="include compact lyric data in the report")
    proofread.add_argument("--no-barlines", dest="barlines", action="store_false", help="omit special barlines")
    proofread.set_defaults(barlines=True)
    patch_layout = sub.add_parser(
        "patch-layout",
        help="apply and verify a validated JSON batch of layout corrections",
    )
    patch_layout.add_argument("--file", required=True, help="JSON layout operation array")
    patch_layout.add_argument("--save", action="store_true", help="save after all operations complete")
    patch_layout.add_argument("--dry-run", action="store_true", help="validate and report without connecting or mutating")
    patch_notes = sub.add_parser(
        "patch-notes",
        help="apply a validated JSON batch of pitch, tie, stem, and delete edits",
    )
    patch_notes.add_argument("--file", required=True, help="JSON note operation array")
    patch_notes.add_argument("--save", action="store_true", help="save after all operations complete")
    patch_notes.add_argument("--dry-run", action="store_true", help="validate and report without connecting or mutating")
    apply = sub.add_parser(
        "apply",
        help="apply a JSON batch of edits as one undo step (requires bridge plug-in)",
    )
    apply.add_argument("--file", required=True, help="JSON operation array; see the sibelius skill's command reference")
    apply.add_argument("--save", action="store_true", help="save after the batch succeeds")
    apply.add_argument("--dry-run", action="store_true", help="check every operation against the open score without changing it")
    read = sub.add_parser("read", help="read bar contents (requires bridge plug-in)")
    read.add_argument("--staff", type=int, default=1, help="staff number, from 1")
    read.add_argument("--from", dest="from_bar", type=int, help="first bar, from 1")
    read.add_argument("--to", dest="to_bar", type=int, help="last bar (default: same as --from)")
    read.add_argument("--bar", type=int, help="specific bar number")
    read.add_argument("--bars", type=str, help="bar range, e.g. '1-3' or '5'")
    read.add_argument("--abc", action="store_true", help="format output as ABC notation with aligned lyrics")
    query = sub.add_parser(
        "query",
        help="find bar objects by staff, bars, type, voice and property filters (requires bridge plug-in)",
    )
    query.add_argument("--staff", action="append", default=[], help="staff number or instrument name; repeatable (default: all)")
    query.add_argument("--bars", type=str, help="bar range, e.g. '12-20' or '5' (default: all)")
    query.add_argument("--type", action="append", default=[], help="object type, e.g. NoteRest, LyricItem, Text, Line, Slur; repeatable or comma-separated")
    query.add_argument("--voice", type=int, help="voice 1-4")
    query.add_argument("--where", action="append", default=[], help="property filter, e.g. 'Pitch>=72' or 'Hidden=true'; repeatable, all must match")
    query.add_argument("--field", action="append", default=[], help="extra properties to return, e.g. Dx,Dy; repeatable or comma-separated")
    query.add_argument("--limit", type=int, default=500, help="maximum objects to return (default: 500)")
    read_abc = sub.add_parser("read-abc", help="format bar contents as standard ABC notation")
    read_abc.add_argument("--staff", type=int, default=1, help="staff number, from 1")
    read_abc.add_argument("--from", dest="from_bar", type=int, help="first bar, from 1")
    read_abc.add_argument("--to", dest="to_bar", type=int, help="last bar (default: same as --from)")
    read_abc.add_argument("--bar", type=int, help="specific bar number")
    read_abc.add_argument("--bars", type=str, help="bar range, e.g. '1-3' or '5'")
    sub.add_parser("bridge-version", help="report the installed bridge plug-in version")
    read_lyrics = sub.add_parser("read-lyrics", help="list all lyrics with addresses")
    read_lyrics.add_argument("--staff", type=int, default=0, help="staff number (0 = all)")
    read_lyrics.add_argument("--from", dest="from_bar", type=int, help="first bar (from 1)")
    read_lyrics.add_argument("--to", dest="to_bar", type=int, help="last bar")
    read_lyrics.add_argument("--bar", type=int, help="specific bar number")
    read_lyrics.add_argument("--bars", type=str, help="bar range, e.g. '1-3' or '5'")
    read_lyrics.add_argument(
        "--verse",
        type=int,
        help="filter to a specific verse/line number (1-based; 0 = all)",
    )
    read_lyrics.add_argument(
        "--words",
        action="store_true",
        help="format syllables into words grouped by staff and verse/bar",
    )
    read_lyrics.add_argument(
        "--by-bar",
        action="store_true",
        help="when used with --words, format strictly bar-by-bar rather than grouped by verse",
    )
    read_lyrics.add_argument(
        "--compact",
        action="store_true",
        help="print one address-preserving line per lyric",
    )
    check_lyrics = sub.add_parser(
        "check-lyrics",
        help="lint score lyrics for typos, cross-voice divergence, collisions, and missing text",
    )
    check_lyrics.add_argument("--staff", type=int, default=0, help="staff number (0 = all)")
    check_lyrics.add_argument("--from", dest="from_bar", type=int, help="first bar (from 1)")
    check_lyrics.add_argument("--to", dest="to_bar", type=int, help="last bar")
    check_lyrics.add_argument("--bar", type=int, help="specific bar number")
    check_lyrics.add_argument("--bars", type=str, help="bar range, e.g. '1-3' or '5'")
    check_lyrics.add_argument(
        "--verse",
        type=int,
        help="filter to a specific verse/line number (1-based; 0 = all)",
    )
    set_lyric = sub.add_parser("set-lyric", help="rewrite one lyric syllable (backs up first)")
    set_lyric.add_argument("--staff", type=int, required=True)
    set_lyric.add_argument("--bar", type=int, required=True)
    set_lyric.add_argument("--index", type=int, required=True)
    set_lyric.add_argument("--text", required=True)
    set_lyric.add_argument("--font", help="override font family, e.g. 'Big Caslon'")
    set_lyric.add_argument(
        "--font-size",
        type=int,
        help="styled-string font size in tenths of a point (e.g. 110 = 11 pt)",
    )
    set_lyric.add_argument("--raw", action="store_true", help="do not preserve existing font/size tags")
    set_lyric.add_argument(
        "--allow-style-reset",
        action="store_true",
        help="acknowledge that --raw may reset the lyric to its text style",
    )
    set_lyric.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    patch_lyrics = sub.add_parser(
        "patch-lyrics",
        help="apply and verify a validated JSON batch of lyric corrections",
    )
    patch_lyrics.add_argument("--file", required=True, help="JSON patch array")
    patch_lyrics.add_argument("--font", help="default font family for patched lyrics")
    patch_lyrics.add_argument(
        "--font-size",
        type=int,
        help="default styled-string font size in tenths of a point",
    )
    patch_lyrics.add_argument(
        "--save", action="store_true", help="save active score after all patches verify"
    )
    set_lyric_style = sub.add_parser(
        "set-lyric-style", help="change a lyric item's verse/style line (backs up first)"
    )
    set_lyric_style.add_argument("--staff", type=int, required=True)
    set_lyric_style.add_argument("--bar", type=int, required=True)
    set_lyric_style.add_argument("--index", type=int, required=True)
    set_lyric_style.add_argument(
        "--style",
        required=True,
        help="style identifier or alias: verse1, verse2, verse3, chorus, above, etc.",
    )
    set_lyric_style.add_argument(
        "--save", action="store_true", help="save active score in Sibelius after change"
    )
    transpose = sub.add_parser("transpose", help="transpose a passage or the whole score (backs up first)")
    transpose.add_argument("--from-note", required=True, help="current tonic, e.g. C or Eb")
    transpose.add_argument("--to-note", required=True, help="target tonic, e.g. D or F#")
    direction = transpose.add_mutually_exclusive_group(required=True)
    direction.add_argument("--up", action="store_true")
    direction.add_argument("--down", action="store_true")
    transpose.add_argument("--octaves", type=int, default=0, help="extra octaves in the same direction")
    transpose.add_argument("--from-bar", type=int, help="default: 1")
    transpose.add_argument("--to-bar", type=int, help="default: last bar")
    transpose.add_argument("--top-staff", type=int, help="default: 1")
    transpose.add_argument("--bottom-staff", type=int, help="default: last staff")
    transpose.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_key = sub.add_parser("set-key", help="add a key signature (backs up first)")
    set_key.add_argument("--bar", type=int, default=1)
    set_key.add_argument("--key", required=True, help='key name, e.g. D or Bb')
    set_key.add_argument("--minor", action="store_true")
    set_key.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_time = sub.add_parser("set-time", help="add a time signature (backs up first)")
    set_time.add_argument("--bar", type=int, default=1)
    set_time.add_argument("--top", type=int, required=True)
    set_time.add_argument("--bottom", type=int, required=True)
    set_time.add_argument("--symbol", choices=["common", "cut"], help="draw 4/4 as common time or 2/2 as cut time")
    set_time.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    copyp = sub.add_parser("copy-passage", help="copy a passage to another staff/bar (backs up first)")
    copyp.add_argument("--from-bar", type=int, required=True)
    copyp.add_argument("--to-bar", type=int, required=True)
    copyp.add_argument("--top-staff", type=int, required=True)
    copyp.add_argument("--bottom-staff", type=int, help="default: same as --top-staff")
    copyp.add_argument("--dest-staff", type=int, required=True)
    copyp.add_argument("--dest-bar", type=int, required=True)
    copyp.add_argument("--dest-pos", type=int, default=0, help="1/256th-quarter offset in dest bar")
    copyp.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_note = sub.add_parser("set-note", help="repitch one note in a chord/NoteRest (backs up first)")
    set_note.add_argument("--staff", type=int, required=True)
    set_note.add_argument("--bar", type=int, required=True)
    set_note.add_argument("--index", type=int, required=True)
    set_note.add_argument("--old-pitch", type=int, required=True, help="MIDI pitch to replace")
    set_note.add_argument("--new-pitch", type=int, required=True, help="replacement MIDI pitch")
    set_note.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    tie = sub.add_parser("tie", help="tie a NoteRest to its following matching note (backs up first)")
    tie.add_argument("--staff", type=int, required=True)
    tie.add_argument("--bar", type=int, required=True)
    tie.add_argument("--index", type=int, required=True)
    tie.add_argument("--remove", action="store_true", help="remove the tie instead")
    tie.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    del_obj = sub.add_parser("delete-object", help="delete the object at an address (backs up first)")
    del_obj.add_argument("--staff", type=int, required=True)
    del_obj.add_argument("--bar", type=int, required=True)
    del_obj.add_argument("--index", type=int, required=True)
    del_obj.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    del_voice = sub.add_parser(
        "delete-voice",
        help="remove one voice's contents (incl. rests) from a staff passage (backs up first)",
    )
    del_voice.add_argument("--staff", type=int, required=True)
    del_voice.add_argument("--from-bar", type=int, required=True)
    del_voice.add_argument("--to-bar", type=int, required=True)
    del_voice.add_argument("--voice", type=int, required=True, choices=[1, 2, 3, 4])
    del_voice.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    clear_bars = sub.add_parser(
        "clear-bars",
        help="replace bars of one staff with a bar rest, tuplets and slurs included (backs up first)",
    )
    clear_bars.add_argument("--staff", type=int, required=True)
    clear_bars.add_argument("--from-bar", type=int, required=True)
    clear_bars.add_argument("--to-bar", type=int, required=True)
    clear_bars.add_argument("--voice", type=int, choices=[1, 2, 3, 4], help="only this voice (default: all)")
    clear_bars.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    flip = sub.add_parser("flip-stem", help="flip the stem of a NoteRest (backs up first)")
    flip.add_argument("--staff", type=int, required=True)
    flip.add_argument("--bar", type=int, required=True)
    flip.add_argument("--index", type=int, required=True)
    flip.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    bracket = sub.add_parser("bracket", help="put a note or chord in parentheses (backs up first)")
    bracket.add_argument("--staff", type=int, required=True)
    bracket.add_argument("--bar", type=int, required=True)
    bracket.add_argument("--index", type=int, required=True)
    bracket.add_argument("--remove", action="store_true", help="remove the parentheses instead")
    bracket.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    beam = sub.add_parser("beam", help="beam a contiguous group of NoteRest objects (backs up first)")
    beam.add_argument("--staff", type=int, required=True)
    beam.add_argument("--bar", type=int, required=True)
    beam.add_argument("--from-index", type=int, required=True, help="first NoteRest object index")
    beam.add_argument("--to-index", type=int, required=True, help="last NoteRest object index")
    beam.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    nudge = sub.add_parser("nudge", help="shift an object graphically (1/32 spaces; backs up first)")
    nudge.add_argument("--staff", type=int, required=True)
    nudge.add_argument("--bar", type=int, required=True)
    nudge.add_argument("--index", type=int, required=True)
    nudge.add_argument("--dx", type=int, default=0, help="right positive")
    nudge.add_argument("--dy", type=int, default=0, help="up positive")
    nudge.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    reset_d = sub.add_parser(
        "reset-design",
        help="reset design/formatting overrides (e.g. font styles) on score objects",
    )
    reset_d.add_argument("--lyrics", action="store_true", help="filter to lyrics only")
    reset_d.add_argument("--save", action="store_true", help="save active score in Sibelius after resetting design")
    add_staff = sub.add_parser(
        "add-staff",
        aliases=["create-staff"],
        help="add an instrument staff to the score (backs up first)",
    )
    add_staff.add_argument(
        "--instrument",
        "--style",
        dest="instrument",
        help="instrument alias or style ID, e.g. 'soprano', 'piano', 'violin'",
    )
    add_staff.add_argument(
        "--position",
        choices=["bottom", "top", "auto"],
        default="bottom",
        help="where to place the new staff (default: bottom)",
    )
    add_staff.add_argument("--full-name", help="custom full instrument name")
    add_staff.add_argument("--short-name", help="custom short instrument name")
    add_staff.add_argument("--above-staff", type=int, help="add an extra staff above this staff")
    add_staff.add_argument("--below-staff", type=int, help="add an extra staff below this staff")
    add_staff.add_argument("--ossia", action="store_true", help="make the added staff an ossia staff")
    add_staff.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    add_bars = sub.add_parser(
        "add-bars",
        help="add empty bars to the end of the score (backs up first)",
    )
    add_bars.add_argument("--count", type=int, default=1, help="number of bars to add (default: 1)")
    add_bars.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    add_notes = sub.add_parser(
        "add-notes",
        aliases=["add-note"],
        help="insert notes, chords, or sequences into a staff/bar (backs up first)",
    )
    add_notes.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    add_notes.add_argument("--bar", type=int, required=True, help="bar number (from 1)")
    add_notes.add_argument("--pos", "--position", dest="pos", type=int, default=0, help="position in bar (ticks, default: 0)")
    add_notes.add_argument("--pitch", "--pitches", dest="pitches", help="pitch name(s) or MIDI number(s), e.g. 'C4' or '60' or 'C4,E4,G4'")
    add_notes.add_argument("--duration", "--dur", dest="duration", default="quarter", help="duration name or ticks, e.g. 'quarter', 'half.', '256'")
    add_notes.add_argument("--notes", "--sequence", dest="notes", help="shorthand sequence, e.g. 'C4:quarter D4:quarter E4:half'")
    add_notes.add_argument("--voice", type=int, default=1, choices=[1, 2, 3, 4], help="voice number (1-4, default: 1)")
    add_notes.add_argument("--tied", action="store_true", help="tie note to next")
    add_notes.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    add_abc = sub.add_parser(
        "add-abc",
        help="insert music and lyrics from an ABC notation snippet (backs up first)",
    )
    add_abc.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    add_abc.add_argument("--bar", type=int, default=1, help="starting bar number (default: 1)")
    add_abc.add_argument("--pos", "--position", dest="pos", type=int, default=0, help="starting position in bar (ticks, default: 0)")
    add_abc.add_argument("abc", nargs="?", help="ABC notation string with notes and optional w: lyrics")
    add_abc.add_argument("--abc", dest="abc_opt", help="ABC notation string (alternative to positional argument)")
    add_abc.add_argument("--voice", type=int, default=1, choices=[1, 2, 3, 4], help="voice number (1-4, default: 1)")
    add_abc.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_staff_name = sub.add_parser(
        "set-staff-name",
        help="set full and short instrument names for a staff (backs up first)",
    )
    set_staff_name.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    set_staff_name.add_argument("--full", help="full instrument name (e.g. 'Soprano')")
    set_staff_name.add_argument("--short", help="short instrument name (e.g. 'S.')")
    set_staff_name.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_initial_instrument = sub.add_parser(
        "set-initial-instrument",
        help="set a staff's instrument at score start (backs up first)",
    )
    set_initial_instrument.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    set_initial_instrument.add_argument(
        "--instrument",
        required=True,
        help="instrument alias or style ID, e.g. 'bass' or 'instrument.singers.bass'",
    )
    set_initial_instrument.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    duplicate_octave_down = sub.add_parser(
        "duplicate-octave-down-to-voice2",
        help="add hidden voice-2 copies of octave-down chord tones (backs up first)",
    )
    duplicate_octave_down.add_argument("--staff", type=int, required=True, help="staff number (from 1)")
    duplicate_octave_down.add_argument("--from-bar", type=int, required=True, help="first bar (from 1)")
    duplicate_octave_down.add_argument("--to-bar", type=int, required=True, help="last bar")
    duplicate_octave_down.add_argument("--save", action="store_true", help="save active score after change")
    set_score_info = sub.add_parser(
        "set-score-info",
        help="set title, composer, and lyricist in Score Info (backs up first)",
    )
    set_score_info.add_argument("--title", help="score title")
    set_score_info.add_argument("--composer", help="composer name")
    set_score_info.add_argument("--lyricist", help="lyricist name")
    set_score_info.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_break = sub.add_parser(
        "set-break",
        help="set system or page break at a bar (backs up first)",
    )
    set_break.add_argument("--bar", type=int, required=True, help="bar number (from 1)")
    set_break.add_argument(
        "--type",
        choices=["system", "page", "none"],
        default="system",
        help="break type: system, page, or none to clear an existing break (default: system)",
    )
    set_break.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    set_barline = sub.add_parser(
        "set-barline",
        help="set or change special barline at a bar (backs up first)",
    )
    set_barline.add_argument("--bar", type=int, required=True, help="bar number (from 1)")
    set_barline.add_argument(
        "--type",
        choices=[
            "double", "start_repeat", "end_repeat", "final", "dashed",
            "invisible", "between_staves", "normal", "tick", "short",
            "dotted", "triple", "thick", "none",
        ],
        default="double",
        help="barline type (default: double)",
    )
    set_barline.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    play_order = sub.add_parser(
        "play-order",
        help="read or set the playback roadmap (Play > Interpretation > Repeats, manual repeats playback)",
    )
    play_order.add_argument(
        "order", nargs="?",
        help="bars in the order they play, e.g. '1-12, 1-12, 1-12'; 'auto' returns to automatic repeats playback; "
        "omit to read the current order",
    )
    play_order.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    play_on_pass = sub.add_parser(
        "play-on-pass",
        help="read or set Inspector > Playback > Play on pass (1-8) on a barline",
    )
    play_on_pass.add_argument("--bar", type=int, required=True, help="bar number (from 1) holding the barline")
    play_on_pass.add_argument(
        "--passes",
        help="passes that play, e.g. '1-3' or '1,3' ('none' for no pass, 'all' for 1-8); the rest are cleared. "
        "Omit to read the barline's checkboxes",
    )
    play_on_pass.add_argument(
        "--type", default="end_repeat",
        choices=["start_repeat", "end_repeat", "double", "final", "dashed", "invisible", "between_staves",
                 "tick", "short", "dotted", "triple", "thick"],
        help="which barline in the bar to change (default: %(default)s)",
    )
    play_on_pass.add_argument("--position", type=int, help="barline position in the bar (1/256 quarters), if several match")
    play_on_pass.add_argument("--save", action="store_true", help="save active score in Sibelius after change")
    read_barlines = sub.add_parser(
        "read-barlines",
        help="read special barlines in a bar or range",
    )
    read_barlines.add_argument("--bar", type=int, help="specific bar number")
    read_barlines.add_argument("--bars", help="bar range, e.g. '1-10'")
    read_barlines.add_argument("--from", dest="from_bar", type=int, help="first bar")
    read_barlines.add_argument("--to", dest="to_bar", type=int, help="last bar")
    export = sub.add_parser("export", help="export the active (or a given) score to another format")
    export.add_argument("--format", choices=sorted(EXPORT_FORMATS), default="musicxml")
    export.add_argument("--out", help="output path (default: next to the source file)")
    export.add_argument("--file", dest="sib_file", help=".sib file to open first (default: active score)")
    mixes = sub.add_parser(
        "rehearsal-mixes",
        help="export rehearsal MP3s: all voices, each voice alone, each voice louder",
        description=(
            "Export one audio stem per staff, equalize the voices (staves with lyrics), "
            "and mix: all voices; each voice alone with accompaniment; each voice at 3x "
            "over the others. Accompaniment keeps its Sibelius level. Needs ffmpeg."
        ),
    )
    mixes.add_argument("--out", required=True, help="directory for the MP3s")
    mixes.add_argument("--file", dest="sib_file", help=".sib file to open first (default: active score)")
    mixes.add_argument("--bitrate", default=rehearsal_mix.DEFAULT_BITRATE, help="MP3 bit rate (default: %(default)s)")
    mixes.add_argument(
        "--name", action="append", default=[], metavar="STAFF=NAME",
        help="name a staff in the file names, e.g. --name 1=Soprano (repeatable)",
    )
    mixes.add_argument("--keep-stems", action="store_true", help="keep the per-staff AIFF stems in --out/stems")
    mixes.add_argument(
        "--loudness", type=float, default=rehearsal_mix.TARGET_LUFS, metavar="LUFS",
        help="integrated loudness for every file (default: %(default)s); lowered if a file would clip",
    )
    mixes.add_argument(
        "--all-parts", action="store_true",
        help="treat every staff as a part to mix, not only staves with lyrics (for instrumental scores)",
    )
    mixes.add_argument(
        "--require-sound", metavar="SOUND_SET",
        help="refuse to export unless every voice plays a sound set containing this, e.g. Cantai",
    )
    mixes.add_argument("--no-proof", action="store_true", help="skip the proof-listening checks after mixing")
    proof = sub.add_parser(
        "proof-mixes",
        help="check a folder of rehearsal mixes for shared audio, repeats, level jumps and mismatched files",
        description=(
            "Proof-listen to rehearsal mixes (needs ffmpeg). Finds the same audio in different voices' "
            "files, stretches that repeat sample for sample, runs far louder than the rest of a file, "
            "and files that differ in length or loudness. With --stems, also checks that each mix is "
            "the stems at fixed gains. Exits non-zero on errors."
        ),
    )
    proof.add_argument("folder", help="folder of MP3s named '<score> - <voice> only.mp3' and so on")
    proof.add_argument("--stems", help="folder of the per-staff stems (rehearsal-mixes --keep-stems)")
    proof.add_argument("--json", action="store_true", help="print the report as JSON")
    sounds = sub.add_parser(
        "playback-sounds",
        help="list each staff's playback sound set, patch and sound ID, and any Mixer override",
    )
    sounds.add_argument("--require", metavar="SOUND_SET",
                        help="exit non-zero unless every staff's sound set contains this")
    verify_render = sub.add_parser(
        "verify-render",
        help="export a score and verify that the rendered files are present and non-empty",
    )
    verify_render.add_argument("--format", choices=sorted(EXPORT_FORMATS), default="png")
    verify_render.add_argument("--out", help="output path (default: next to the source file)")
    verify_render.add_argument("--file", dest="sib_file", help=".sib file to open first (default: active score)")
    verify_render.add_argument("--expect-pages", type=int, help="require exactly this many rendered files")
    verify_render.add_argument("--min-bytes", type=int, default=1, help="minimum size for each rendered file")
    verify_render.add_argument("--sha256", action="store_true", help="include SHA-256 hashes in the report")
    backup = sub.add_parser("backup", help="in-file version + save + timestamped file copy")
    backup.add_argument("--name", default="sibelius-websocket-cli backup")
    do = sub.add_parser("do", help="run a named operation (curated command IDs)")
    do.add_argument(
        "operation",
        choices=sorted(NAMED_OPERATIONS),
        metavar="operation",
        help=f"one of: {', '.join(sorted(NAMED_OPERATIONS))}",
    )
    install = sub.add_parser(
        "install-plugin",
        help="copy the bundled ScoreBridge.plg bridge into the Sibelius plug-in folder",
    )
    install.add_argument(
        "--plugin-dir",
        help="override the Sibelius user plug-in directory",
    )
    split_parts = sub.add_parser(
        "split-parts",
        aliases=["demix"],
        help="demix multi-voice / choral scores into discrete vocal staves",
    )
    split_parts.add_argument(
        "score_file",
        nargs="?",
        help="input score file (.sib, .xml, .mxl); defaults to active score in Sibelius",
    )
    split_parts.add_argument(
        "--file",
        "-f",
        dest="file_opt",
        help="alternative to positional score file",
    )
    split_parts.add_argument(
        "--preset",
        choices=["16voices", "satb"],
        default="16voices",
        help="demixing preset (default: 16voices)",
    )
    split_parts.add_argument(
        "--out",
        "-o",
        help="output path (default: <input_stem>_<preset>.mxl)",
    )
    split_parts.add_argument(
        "--validate",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="validate measure durations across generated parts (default: True)",
    )
    split_parts.add_argument(
        "--audit",
        action="store_true",
        help="report layout and routing diagnostics without writing an output score",
    )
    split_parts.add_argument("--soprano-solo", help="SATB solo bars, e.g. 8-15,20")
    split_parts.add_argument("--tenor-solo", help="SATB solo bars, e.g. 8-15,20")
    split_parts.add_argument("--bass-solo", help="SATB solo bars, e.g. 8-15,20")
    split_parts.add_argument(
        "--open",
        action="store_true",
        help="open the resulting score in Sibelius upon completion",
    )
    round_cmd = sub.add_parser(
        "round",
        help="arrange a single-part round as staggered voices for playback (MusicXML in and out)",
    )
    round_cmd.add_argument("score_file", help="single-part round (.xml, .musicxml, .mxl)")
    round_cmd.add_argument("--out", "-o", help="output path (default: <input_stem>_round.musicxml)")
    round_cmd.add_argument("--voices", type=int, help='number of voices (default: highest "N." entry mark)')
    round_cmd.add_argument("--gap", type=int, help='bars between entries (default: from "1." and "2." marks)')
    round_cmd.add_argument("--passes", type=int, default=2, help="times each voice sings the song (default: 2)")
    round_cmd.add_argument(
        "--program", type=int, default=53, help="General MIDI program, 1-based (default: 53, Choir Aahs)"
    )
    round_cmd.add_argument(
        "--no-hold-final",
        dest="hold_final",
        action="store_false",
        help="keep each voice's last bar as written instead of holding its first note",
    )
    round_cmd.add_argument("--open", action="store_true", help="open the result in Sibelius")
    sub.add_parser("forget-token", help="delete the cached session token for host:port")
    return parser


def _emit(args: argparse.Namespace, response: dict[str, Any], human: str) -> int:
    print(json.dumps(response) if args.json else human)
    return EXIT_OK if protocol.is_success(response) else EXIT_COMMAND_FAILED


async def _run_ping(args: argparse.Namespace) -> int:
    async with _client(args) as client:
        response = await client.invoke_commands([])
    return _emit(args, response, f"Sibelius at {args.host}:{args.port} is responding")


async def _run_command(args: argparse.Namespace) -> int:
    async with _client(args) as client:
        response = await client.send_command(args.command_name)
    ok = protocol.is_success(response)
    return _emit(args, response, f"{args.command_name}: {'ok' if ok else f'failed: {response}'}")


async def _run_invoke(args: argparse.Namespace) -> int:
    async with _client(args) as client:
        response = await client.invoke_commands(args.command_ids)
    ok = protocol.is_success(response)
    return _emit(
        args,
        response,
        f"invoked {len(args.command_ids)} command(s): {'ok' if ok else f'failed: {response}'}",
    )


async def _run_raw(args: argparse.Namespace) -> int:
    try:
        message = json.loads(args.json_message)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    if not isinstance(message, dict):
        print("error: message must be a JSON object", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    async with _client(args) as client:
        response = await client.send_raw(message)
    print(json.dumps(response, indent=None if args.json else 2))
    return EXIT_OK if protocol.is_success(response) else EXIT_COMMAND_FAILED


async def _run_repl(args: argparse.Namespace) -> int:
    async with _client(args) as client:
        print("Connected. Enter a command name, or a JSON object for a raw message. Ctrl-D exits.")
        loop = asyncio.get_running_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, input, "sibelius> ")
            except EOFError:
                print()
                return EXIT_OK
            line = line.strip()
            if not line or line in {"exit", "quit"}:
                if line:
                    return EXIT_OK
                continue
            try:
                if line.startswith("{"):
                    response = await client.send_raw(json.loads(line))
                else:
                    response = await client.send_command(line)
            except json.JSONDecodeError as exc:
                print(f"invalid JSON: {exc}")
                continue
            except TimeoutError:
                print("(no response within timeout)")
                continue
            print(json.dumps(response, indent=2))


BRIDGE_PLUGIN = "ScoreBridge"

# CLI format name -> (ManuScript SaveAs type, file extension)
EXPORT_FORMATS = {
    "musicxml": ("MUSICXML", ".musicxml"),
    "mxl": ("MXL", ".mxl"),
    "pdf": ("PDF", ".pdf"),
    "midi": ("Midi", ".mid"),
    "png": ("PNG", ".png"),
}

# Curated friendly names -> ManuScript command IDs (see docs/avid-reference.md).
# Note these are fire-and-forget: Sibelius acknowledges receipt but never
# reports whether the command did anything (docs/sibelius-protocol.md 1.2).
NAMED_OPERATIONS = {
    "undo": "undo",
    "redo": "redo",
    "save": "save",
    "select-all": "select_all",
    "select-none": "select_none",
    "delete": "delete",
    "add-bar": "add_bar_at_end",
    "play": "play_from_selection",
    "play-stop": "play/stop",
    "transpose-dialog": "transpose",
}


async def _run_plugin(args: argparse.Namespace) -> int:
    plugin_args = None
    if args.plugin_args is not None:
        try:
            plugin_args = json.loads(args.plugin_args)
        except json.JSONDecodeError as exc:
            print(f"error: --args is not valid JSON: {exc}", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        if not isinstance(plugin_args, list):
            print("error: --args must be a JSON array", file=sys.stderr)
            return EXIT_COMMAND_FAILED
    async with _client(args, plugins=[args.name]) as client:
        response = await client.invoke_plugin(args.name, args.method, plugin_args)
    if not protocol.is_success(response):
        print(
            f"error: plug-in call failed (is '{args.name}' installed and was it "
            f"declared at connect time?): {json.dumps(response)}",
            file=sys.stderr,
        )
        return EXIT_COMMAND_FAILED
    value = protocol.plugin_return_value(response)
    print(json.dumps(response) if args.json else json.dumps(value, indent=2))
    return EXIT_OK


async def _run_score_info(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "GetScoreInfo")


class BridgeError(Exception):
    def __init__(self, payload: Any) -> None:
        super().__init__(json.dumps(payload))
        self.payload = payload


async def _bridge(client: SibeliusClient, method: str, call_args: list[Any] | None = None) -> Any:
    """Call a bridge method; raise BridgeError on transport or bridge failure."""
    response = await client.invoke_plugin(BRIDGE_PLUGIN, method, call_args)
    if not protocol.is_success(response):
        raise BridgeError(
            "bridge plug-in not reachable — run 'sibelius-cli "
            f"install-plugin' and restart Sibelius. Response: {json.dumps(response)}"
        )
    value = protocol.plugin_return_value(response)
    if isinstance(value, dict) and "error" in value:
        raise BridgeError(value["error"])
    return value


MIN_BRIDGE_VERSION = 7
CURRENT_BRIDGE_VERSION = 60
QUERY_BRIDGE_VERSION = 38
BATCH_BRIDGE_VERSION = 39
NUDGE_BRIDGE_VERSION = 41
STRUCTURAL_BRIDGE_VERSION = 44
STRUCTURE_READ_BRIDGE_VERSION = 45
BEAM_RESULT_BRIDGE_VERSION = 46
SYSTEM_STAFF_BRIDGE_VERSION = 48
LAYOUT_BATCH_BRIDGE_VERSION = 50
HIDE_EMPTY_STAVES_BRIDGE_VERSION = 52
AUDIO_EXPORT_BRIDGE_VERSION = 54
PLAYBACK_SOUNDS_BRIDGE_VERSION = 55
DELETE_BARS_BRIDGE_VERSION = 56
REPEATS_BRIDGE_VERSION = 57
LYRIC_VERSE_BRIDGE_VERSION = 58
SET_LYRIC_VERSE_BRIDGE_VERSION = 59
TUPLET_NOTES_BRIDGE_VERSION = 60


def _batch_bridge_version(operations: list[dict[str, Any]]) -> int:
    """The oldest bridge that runs every operation in a validated batch."""
    names = {operation["op"] for operation in operations}
    if names & {"add-tuplet-notes", "clear-bars"}:
        return TUPLET_NOTES_BRIDGE_VERSION
    if "set-lyric-verse" in names:
        return SET_LYRIC_VERSE_BRIDGE_VERSION
    if any(
        operation["op"] == "add-lyric" and ("verse" in operation or "dy" in operation)
        for operation in operations
    ):
        return LYRIC_VERSE_BRIDGE_VERSION
    if "delete-bars" in names:
        return DELETE_BARS_BRIDGE_VERSION
    if "hide-empty-staves" in names:
        return HIDE_EMPTY_STAVES_BRIDGE_VERSION
    if names & {"set-bar-number", "set-layout"} or any(
        operation.get("prop") == "NumNotes"
        or (operation["op"] == "add-bars" and ("bar" in operation or "length" in operation))
        for operation in operations
    ):
        return LAYOUT_BATCH_BRIDGE_VERSION
    if "add-line" in names or any(operation.get("staff") == batch_ops.SYSTEM_STAFF for operation in operations):
        return SYSTEM_STAFF_BRIDGE_VERSION
    if names & (batch_ops.STRUCTURAL | {"beam"}):
        return STRUCTURAL_BRIDGE_VERSION
    if "nudge" in names:
        return NUDGE_BRIDGE_VERSION
    return BATCH_BRIDGE_VERSION


async def _check_bridge_version(client: SibeliusClient) -> None:
    info = await _bridge(client, "GetBridgeVersion")
    if not (isinstance(info, dict) and info.get("version", 0) >= MIN_BRIDGE_VERSION):
        raise BridgeError(
            f"bridge v{MIN_BRIDGE_VERSION}+ required, got {info!r} — run install-plugin and restart Sibelius"
        )


async def _require_bridge(client: SibeliusClient, version: int, feature: str) -> None:
    info = await _bridge(client, "GetBridgeVersion")
    if not (isinstance(info, dict) and info.get("version", 0) >= version):
        raise BridgeError(
            f"{feature} needs bridge v{version}+, got {info!r} — run install-plugin and restart Sibelius"
        )


async def _apply_batch(
    client: SibeliusClient, operations: list[dict[str, Any]], dry_run: bool
) -> dict[str, Any]:
    """Run ApplyBatch; return its result, including any partial results on failure."""
    response = await client.invoke_plugin(BRIDGE_PLUGIN, "ApplyBatch", [operations, dry_run])
    if not protocol.is_success(response):
        raise BridgeError(f"bridge plug-in not reachable. Response: {json.dumps(response)}")
    value = protocol.plugin_return_value(response)
    if not isinstance(value, dict):
        raise BridgeError(f"unexpected ApplyBatch result: {value!r}")
    return value


async def _assert_expected_score(
    client: SibeliusClient,
    args: argparse.Namespace,
    info: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Fail before mutation when --expect-file does not name the active score."""
    expected_arg = getattr(args, "expect_file", None)
    if not expected_arg:
        return info
    if info is None:
        info = await _bridge(client, "GetScoreInfo")
    actual_arg = info.get("fileName") if isinstance(info, dict) else None
    if not actual_arg:
        raise BridgeError("active score has no file path; --expect-file cannot be verified")
    expected = Path(expected_arg).expanduser().resolve()
    actual = Path(actual_arg).expanduser().resolve()
    if actual != expected:
        raise BridgeError(f"active score mismatch: expected {expected}, got {actual}")
    return info


_BACKUP_DIR: Path | None = None  # set by main() from --backup-dir / SIBELIUS_BACKUP_DIR


async def _backup(client: SibeliusClient, name: str) -> dict[str, Any]:
    """In-file version + save + timestamped filesystem copy. Returns details."""
    import shutil
    from datetime import datetime

    try:
        version = await _bridge(client, "AddVersion", [name, "automatic backup before write"])
    except BridgeError as exc:
        # In-file versioning is best-effort; the filesystem copy below is the
        # real backup. Sibelius sometimes refuses AddVersion (returns null).
        version = {"skipped": str(exc)}
        print(f"warning: in-file version skipped: {exc}", file=sys.stderr)
    saved = await _bridge(client, "Save")
    source = Path(saved["fileName"])
    if not source.is_absolute():
        # Bridges before v36 accept an imported score's bare title as a path.
        raise BridgeError(
            f"score {saved['fileName']!r} has never been saved as a .sib; save it in Sibelius first"
        )
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = _BACKUP_DIR or source.parent
    folder.mkdir(parents=True, exist_ok=True)
    copy = folder / f"{source.stem}.backup-{stamp}{source.suffix}"
    shutil.copy2(source, copy)
    return {"version": version, "savedTo": str(source), "copy": str(copy)}


async def _run_write(
    args: argparse.Namespace, method: str, call_args: list[Any]
) -> int:
    """Backup, then run a bridge write method and print its result."""
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        await _assert_expected_score(client, args)
        backup = await _backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        result = await _bridge(client, method, call_args)
        if getattr(args, "save", False):
            saved = await _bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps(result, indent=2))
    return EXIT_OK


async def _run_op(
    args: argparse.Namespace,
    operation: dict[str, Any] | Callable[[SibeliusClient], Awaitable[dict[str, Any]]],
    legacy: Callable[[dict[str, Any]], Any],
    min_bridge: int = BATCH_BRIDGE_VERSION,
) -> int:
    """Run one edit as a one-operation ApplyBatch.

    The operation is checked against the score before the backup, so a bad
    address fails without saving anything. legacy() maps the batch result to
    the command's historical output shape. An operation that depends on the
    score (such as defaults of "the whole score") is passed as an async
    builder, called once connected.
    """
    batch: list[dict[str, Any]] = []
    if isinstance(operation, dict):
        try:
            batch = batch_ops.validate_batch([operation])
        except batch_ops.BatchError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_COMMAND_FAILED
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        if not batch:
            try:
                batch = batch_ops.validate_batch([await operation(client)])
            except batch_ops.BatchError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
        await _require_bridge(client, max(min_bridge, _batch_bridge_version(batch)), args.subcommand)
        await _assert_expected_score(client, args)
        checked = await _apply_batch(client, batch, True)
        if "error" in checked:
            raise BridgeError(checked["error"])
        backup = await _backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        result = await _apply_batch(client, batch, False)
        if "error" in result:
            raise BridgeError(f"{result['error']}; restore from {backup.get('copy')}")
        if getattr(args, "save", False):
            saved = await _bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps(legacy(result["results"][0]), indent=2))
    return EXIT_OK


def _address(args: argparse.Namespace) -> dict[str, Any]:
    return {"staff": args.staff, "bar": args.bar, "index": args.index}


def _notes(description: dict[str, Any] | None) -> list[dict[str, Any]]:
    return list((description or {}).get("notes", []))


async def _run_save(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        await _assert_expected_score(client, args)
        saved = await _bridge(client, "Save")
    print(json.dumps(saved) if args.json else f"saved: {saved.get('fileName', '')}")
    return EXIT_OK


async def _run_reset_design(args: argparse.Namespace) -> int:
    commands = ["select_all"]
    if getattr(args, "lyrics", False):
        commands.append("filter_lyrics")
    commands.append("reset_design")
    commands.append("select_none")

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        await _assert_expected_score(client, args)
        backup = await _backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        response = await client.invoke_commands(commands)
        if not protocol.is_success(response):
            print(f"error resetting design: {json.dumps(response)}", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        if getattr(args, "save", False):
            saved = await _bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    return _emit(
        args,
        response,
        f"reset design ({'lyrics' if getattr(args, 'lyrics', False) else 'all'})",
    )


async def _run_bridge_call(
    args: argparse.Namespace, method: str, call_args: list[Any] | None = None
) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        response = await client.invoke_plugin(BRIDGE_PLUGIN, method, call_args)
    if not protocol.is_success(response):
        print(
            "error: bridge plug-in not reachable — run "
            "'sibelius-cli install-plugin' and restart Sibelius. "
            f"Response: {json.dumps(response)}",
            file=sys.stderr,
        )
        return EXIT_COMMAND_FAILED
    value = protocol.plugin_return_value(response)
    print(json.dumps(response) if args.json else json.dumps(value, indent=2))
    if isinstance(value, dict) and "error" in value:
        return EXIT_COMMAND_FAILED
    return EXIT_OK


async def _run_staves(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "GetStaves")


async def _run_selection(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "GetSelectionInfo")


async def _run_inspect(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        info = await _bridge(client, "GetScoreInfo")
        staves = await _bridge(client, "GetStaves")
        selection = await _bridge(client, "GetSelectionInfo")
    projected = agent_output.project_inspect(info, staves, selection)
    if args.json:
        print(json.dumps(projected, ensure_ascii=False, separators=(",", ":")))
    else:
        print(agent_output.render_compact_inspect(info, staves, selection))
    return EXIT_OK


async def _run_score_snapshot(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(bars=getattr(args, "bars", None))
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        info = await _bridge(client, "GetScoreInfo")
        staves = await _bridge(client, "GetStaves")
        selection = await _bridge(client, "GetSelectionInfo")

        barlines: list[dict[str, Any]] = []
        if args.barlines:
            bar_start = from_b or 1
            bar_end = to_b or int(info.get("barCount", bar_start))
            barlines = await _bridge(client, "GetSpecialBarlines", [bar_start, bar_end])

        lyric_data: list[dict[str, Any]] | None = None
        if args.lyrics:
            lyric_data = await _bridge(
                client,
                "ReadLyrics",
                [args.staff, from_b or 0, to_b or 0],
            )

    snapshot = agent_output.project_score_snapshot(
        info,
        staves,
        selection,
        barlines=barlines,
        lyrics=lyric_data,
    )
    print(agent_output.render_compact_snapshot(snapshot))
    return EXIT_OK


async def _run_proofread(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(bars=getattr(args, "bars", None))
    verse = None
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        info = await _bridge(client, "GetScoreInfo")
        staves_info = await _bridge(client, "GetStaves")
        selection = await _bridge(client, "GetSelectionInfo")
        names = {
            s.get("staffNum", s.get("staffNumber", i + 1)): (
                s.get("fullInstrumentName")
                or s.get("instrumentName")
                or s.get("name")
                or f"Staff {s.get('staffNum', i + 1)}"
            )
            for i, s in enumerate(staves_info)
        }
        raw_lyrics = await _bridge(client, "ReadLyrics", [args.staff, from_b or 0, to_b or 0])
        filtered_lyrics = lyrics.filter_lyrics(raw_lyrics, from_bar=from_b, to_bar=to_b, verse=verse)

        bar_count = int(info.get("barCount", 0))
        start_b = from_b or 1
        end_b = to_b or bar_count
        target_staves = [args.staff] if args.staff > 0 else sorted({s.get("staff", 1) for s in filtered_lyrics})
        staff_bars: dict[int, list[dict[str, Any]]] = {}
        for staff_num in target_staves:
            if end_b >= start_b:
                staff_bars[staff_num] = await _bridge(client, "ReadBars", [staff_num, start_b, end_b])

        barlines: list[dict[str, Any]] = []
        if args.barlines:
            barlines = await _bridge(client, "GetSpecialBarlines", [start_b, end_b])

    score_default_font = info.get("mainTextFontName")
    typography = lyrics.analyze_lyric_typography(
        filtered_lyrics, score_default_font=score_default_font, staff_names=names
    )
    issues = lyrics.lint_lyrics(
        filtered_lyrics, names, staff_bars, score_default_font=score_default_font
    )
    snapshot = agent_output.project_score_snapshot(
        info,
        staves_info,
        selection,
        barlines=barlines,
        lyrics=filtered_lyrics if args.lyrics else None,
    )
    compact_issues = [
        {
            field: issue[field]
            for field in ("type", "severity", "bar", "staff", "staves", "line", "message")
            if field in issue
        }
        for issue in issues
    ]
    report = {
        "snapshot": snapshot,
        "issues": compact_issues,
        "errors": sum(issue.get("severity") == "error" for issue in issues),
        "warnings": sum(issue.get("severity") == "warning" for issue in issues),
        "typography": {
            field: typography[field]
            for field in ("predominant_font", "predominant_size", "has_divergence_from_score_default")
            if field in typography
        },
    }
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return EXIT_COMMAND_FAILED if report["errors"] else EXIT_OK


_LAYOUT_BATCHED = {"nudge", "set-break", "set-barline", "set-time"}


def _layout_batch_op(operation: dict[str, Any]) -> dict[str, Any]:
    """Translate a patch-layout operation into an ApplyBatch operation."""
    op = operation["op"]
    if op == "nudge":
        return {"op": op, "staff": operation["staff"], "bar": operation["bar"],
                "index": operation["index"], "dx": operation.get("dx", 0), "dy": operation.get("dy", 0)}
    if op == "set-break":
        return {"op": op, "bar": operation["bar"], "type": operation.get("type", "system")}
    if op == "set-barline":
        return {"op": op, "bar": operation["bar"], "type": operation.get("type", "double")}
    out = {"op": op, "bar": operation["bar"], "numerator": operation["top"], "denominator": operation["bottom"]}
    if operation.get("symbol"):
        out["symbol"] = operation["symbol"]
    return out


def _legacy_layout(operation: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Map a batch result to what the retired single-purpose handlers returned."""
    if operation["op"] == "set-barline":
        barline = after["barlineType"]
        # SetSpecialBarline reported 'none' and 'normal' as SpecialBarlineNormal.
        return {"bar": after["bar"], "deleted": after["removed"], "barlineType": "7" if barline == "-1" else barline}
    if operation["op"] == "set-time":
        meter = (after["numerator"], after["denominator"])
        style = "numeric"
        if operation.get("symbol"):
            style = {(4, 4): "common", (2, 2): "cut"}.get(meter, "numeric")
        return {"bar": after["bar"], "numerator": after["numerator"],
                "denominator": after["denominator"], "style": style}
    return after


async def _run_patch_layout(args: argparse.Namespace) -> int:
    try:
        operations = layout.load_layout_patches(args.file)
    except layout.LayoutPatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    if args.dry_run:
        print(layout.compact_summary({"operations": len(operations), "validated": True, "dryRun": True}))
        return EXIT_OK

    results: list[dict[str, Any]] = []
    batchable = [_layout_batch_op(o) for o in operations if o["op"] in _LAYOUT_BATCHED]
    try:
        for operation in batchable:
            batch_ops.validate_batch([operation])
    except batch_ops.BatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        if batchable:
            await _require_bridge(client, _batch_bridge_version(batchable), "patch-layout")
        elif any(operation["op"] == "remove-redundant-clefs" for operation in operations):
            await _require_bridge(client, BATCH_BRIDGE_VERSION, "patch-layout remove-redundant-clefs")
        await _assert_expected_score(client, args)
        backup = await _backup(client, "before patch-layout")
        pending: list[dict[str, Any]] = []

        async def flush() -> None:
            # A run of batchable operations is one checked batch and one undo
            # step; a new batch starts where the ordering rules require it.
            if not pending:
                return
            batch = batch_ops.validate_batch(pending)
            outcome = await _apply_batch(client, batch, False)
            if "error" in outcome:
                raise BridgeError(
                    f"patch-layout batch failed: {outcome['error']}; restore from {backup.get('copy')}"
                )
            for operation, result in zip(batch, outcome["results"]):
                results.append({
                    "op": operation["op"], "result": _legacy_layout(operation, result["after"]),
                    "verified": True,
                })
            pending.clear()

        for operation in operations:
            op = operation["op"]
            operation_verified = True
            if op in _LAYOUT_BATCHED:
                candidate = _layout_batch_op(operation)
                try:
                    batch_ops.validate_batch([*pending, candidate])
                except batch_ops.BatchError:
                    await flush()
                pending.append(candidate)
                continue
            await flush()
            if op == "remove-redundant-clefs":
                from .clefs import delete_redundant_clefs, find_redundant_clefs

                target_staff = operation.get("staff")
                findings = await find_redundant_clefs(client, target_staff)
                deleted = await delete_redundant_clefs(client, findings)
                remaining = await find_redundant_clefs(client, target_staff)
                operation_verified = not remaining
                result = {
                    "found": len(findings),
                    "deleted": deleted,
                    "remaining": len(remaining),
                    "staff": target_staff,
                }
                if not operation_verified:
                    raise BridgeError(f"remove-redundant-clefs left {len(remaining)} finding(s)")
            else:  # reset-design
                commands = ["select_all"]
                if operation.get("lyrics", False):
                    commands.append("filter_lyrics")
                commands.extend(["reset_design", "select_none"])
                response = await client.invoke_commands(commands)
                if not protocol.is_success(response):
                    raise BridgeError(f"reset-design failed: {json.dumps(response)}")
                result = {"commands": commands, "ok": True}
            results.append({"op": op, "result": result, "verified": operation_verified})
        await flush()

        saved = None
        if args.save:
            saved = await _bridge(client, "Save")

    summary = {
        "operations": len(operations),
        "verified": len(results),
        "backup": backup.get("copy"),
        "results": results,
    }
    if saved is not None:
        summary["saved"] = saved.get("fileName", "")
    print(layout.compact_summary(summary))
    return EXIT_OK


async def _run_apply(args: argparse.Namespace) -> int:
    try:
        operations = batch_ops.load_batch(args.file)
    except batch_ops.BatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    backup = None
    saved = None
    try:
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _require_bridge(client, _batch_bridge_version(operations), "apply")
            await _assert_expected_score(client, args)
            # Check first so a refused batch neither saves nor backs up.
            result = await _apply_batch(client, operations, True)
            if not args.dry_run and "error" not in result:
                backup = await _backup(client, "before apply")
                result = await _apply_batch(client, operations, False)
            if args.save and not args.dry_run and "error" not in result:
                saved = await _bridge(client, "Save")
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    summary: dict[str, Any] = {"operations": len(operations), **result}
    if backup is not None:
        summary["backup"] = backup.get("copy")
    if saved is not None:
        summary["saved"] = saved.get("fileName", "")
    print(layout.compact_summary(summary))
    if "error" in result:
        applied = result.get("applied", 0)
        hint = (
            "nothing was changed" if not applied
            else f"{applied} op(s) were applied as one undo step; run 'invoke undo' to revert them"
        )
        print(f"error: {result['error']} — {hint}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    return EXIT_OK


async def _run_patch_notes(args: argparse.Namespace) -> int:
    try:
        operations = note_patches.load_note_patches(args.file)
    except note_patches.NotePatchError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    ordered = note_patches.execution_order(operations)
    if args.dry_run:
        print(layout.compact_summary({
            "operations": len(operations),
            "validated": True,
            "dryRun": True,
            "order": [op["op"] for op in ordered],
        }))
        return EXIT_OK

    results: list[dict[str, Any]] = []
    batch = batch_ops.validate_batch(note_patches.batch_operations(ordered))
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _require_bridge(client, _batch_bridge_version(batch), "patch-notes")
        await _assert_expected_score(client, args)
        backup = await _backup(client, "before patch-notes")
        # One round trip and one undo step for the whole file.
        outcome = await _apply_batch(client, batch, False)
        if "error" in outcome:
            raise BridgeError(
                f"patch-notes batch stopped: {outcome['error']} after "
                f"{outcome.get('applied', 0)} applied as one undo step; "
                f"restore from {backup.get('copy')}"
            )
        for operation, result in zip(batch, outcome.get("results", [])):
            results.append({"op": operation["op"], "result": result})

        saved = None
        if args.save:
            saved = await _bridge(client, "Save")

    summary = {
        "operations": len(operations),
        "applied": len(results),
        "backup": backup.get("copy"),
        "results": results,
    }
    if saved is not None:
        summary["saved"] = saved.get("fileName", "")
    print(layout.compact_summary(summary))
    return EXIT_OK


async def _run_query(args: argparse.Namespace) -> int:
    from ai_score_editing.query import QueryError, build_selector, resolve_staves

    from_b, to_b = (None, None)
    if args.bars:
        from_b, to_b = parse_bar_range(bars=args.bars)
    try:
        # Validate everything but staff names before connecting.
        selector = build_selector(
            staves=[],
            from_bar=from_b,
            to_bar=to_b,
            types=args.type,
            voice=args.voice,
            where=args.where,
            fields=args.field,
            limit=args.limit,
        )
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _require_bridge(client, QUERY_BRIDGE_VERSION, "query")
            if args.staff:
                selector["staves"] = resolve_staves(args.staff, await _bridge(client, "GetStaves"))
                if 0 in selector["staves"]:
                    await _require_bridge(client, SYSTEM_STAFF_BRIDGE_VERSION, "query of the system staff")
            result = await _bridge(client, "Query", [selector])
    except QueryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    print(json.dumps(result, indent=None if args.json else 2))
    if result.get("truncated"):
        print(f"warning: truncated at {args.limit} objects; narrow the query or raise --limit", file=sys.stderr)
    return EXIT_OK


async def _run_read(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(
        bar=getattr(args, "bar", None),
        bars=getattr(args, "bars", None),
        from_bar=getattr(args, "from_bar", None),
        to_bar=getattr(args, "to_bar", None),
    )
    start_bar = from_b if from_b is not None else 1
    end_bar = to_b if to_b is not None else start_bar

    if getattr(args, "abc", False) or getattr(args, "subcommand", "") == "read-abc":
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _check_bridge_version(client)
            info = await _bridge(client, "GetScoreInfo")
            staves_info = await _bridge(client, "GetStaves")
            # An unaddressed ABC export is expected to represent the whole
            # staff.  Ordinary `read` retains its one-bar default.
            if from_b is None and to_b is None:
                end_bar = info.get("barCount", end_bar)
            bars = await _bridge(client, "ReadBars", [args.staff, start_bar, end_bar])
            raw_lyrics = await _bridge(
                client, "ReadLyrics", [args.staff, start_bar, end_bar]
            )
            filtered_lyrics = lyrics.filter_lyrics(raw_lyrics, from_bar=start_bar, to_bar=end_bar)

            key_name = "C"
            for ks in info.get("keySignatures", []):
                if ks.get("bar", 1) <= start_bar:
                    key_name = ks.get("name", "C")

            time_sig = None
            for ts in info.get("timeSignatures", []):
                if ts.get("bar", 1) <= start_bar:
                    time_sig = (ts.get("numerator", 4), ts.get("denominator", 4))

            instr_name = None
            for s in staves_info:
                if s.get("staffNum") == args.staff:
                    instr_name = s.get("fullInstrumentName") or s.get("instrumentName")

            abc_str = abc_notation.score_to_abc(
                bars,
                lyrics=filtered_lyrics,
                time_sig=time_sig,
                key=key_name,
                staff_num=args.staff,
                instrument_name=instr_name,
            )
            print(abc_str)
            return EXIT_OK

    return await _run_bridge_call(args, "ReadBars", [args.staff, start_bar, end_bar])


async def _run_read_abc(args: argparse.Namespace) -> int:
    setattr(args, "abc", True)
    return await _run_read(args)


async def _run_do(args: argparse.Namespace) -> int:
    command_id = NAMED_OPERATIONS[args.operation]
    async with _client(args) as client:
        response = await client.invoke_commands([command_id])
    return _emit(args, response, f"sent {args.operation} ({command_id})")


async def _run_bridge_version(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "GetBridgeVersion")


async def _run_read_lyrics(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(
        bar=getattr(args, "bar", None),
        bars=getattr(args, "bars", None),
        from_bar=getattr(args, "from_bar", None),
        to_bar=getattr(args, "to_bar", None),
    )
    verse = getattr(args, "verse", None)
    if verse == 0:
        verse = None
    by_bar = getattr(args, "by_bar", False)

    if getattr(args, "compact", False) and getattr(args, "words", False):
        print("error: --compact and --words cannot be combined", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        raw_lyrics = await _bridge(
            client, "ReadLyrics", [args.staff, from_b or 0, to_b or 0]
        )
        filtered = lyrics.filter_lyrics(raw_lyrics, from_bar=from_b, to_bar=to_b, verse=verse)

        if getattr(args, "compact", False):
            annotated = lyrics.infer_syllable_lines(filtered)
            print(agent_output.render_compact_lyrics(annotated))
            return EXIT_OK

        if args.words:
            if args.json:
                print(json.dumps(filtered))
                return EXIT_OK
            staves_info = await _bridge(client, "GetStaves")
            names = {
                s.get("staffNum", s.get("staffNumber", i + 1)): (
                    s.get("fullInstrumentName")
                    or s.get("instrumentName")
                    or s.get("name")
                    or f"Staff {s.get('staffNum', i + 1)}"
                )
                for i, s in enumerate(staves_info)
            }
            print(lyrics.format_lyrics(filtered, names, by_bar=by_bar, verse=verse))
            return EXIT_OK

    print(json.dumps(filtered) if args.json else json.dumps(filtered, indent=2))
    return EXIT_OK


async def _run_check_lyrics(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(
        bar=getattr(args, "bar", None),
        bars=getattr(args, "bars", None),
        from_bar=getattr(args, "from_bar", None),
        to_bar=getattr(args, "to_bar", None),
    )
    verse = getattr(args, "verse", None)
    if verse == 0:
        verse = None

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        info = await _bridge(client, "GetScoreInfo")
        staves_info = await _bridge(client, "GetStaves")
        names = {
            s.get("staffNum", s.get("staffNumber", i + 1)): (
                s.get("fullInstrumentName")
                or s.get("instrumentName")
                or s.get("name")
                or f"Staff {s.get('staffNum', i + 1)}"
            )
            for i, s in enumerate(staves_info)
        }
        raw_lyrics = await _bridge(
            client, "ReadLyrics", [args.staff, from_b or 0, to_b or 0]
        )
        filtered_lyrics = lyrics.filter_lyrics(
            raw_lyrics, from_bar=from_b, to_bar=to_b, verse=verse
        )

        bar_count = info.get("barCount", 0)
        start_b = from_b or 1
        end_b = to_b or bar_count

        staff_bars: dict[int, list[dict[str, Any]]] = {}
        target_staves = (
            [args.staff]
            if args.staff > 0
            else sorted({s.get("staff", 1) for s in filtered_lyrics})
        )
        for s_num in target_staves:
            if bar_count > 0 and end_b >= start_b:
                bars = await _bridge(client, "ReadBars", [s_num, start_b, end_b])
                staff_bars[s_num] = bars

        score_default_font = info.get("mainTextFontName")
        typography = lyrics.analyze_lyric_typography(
            filtered_lyrics, score_default_font=score_default_font, staff_names=names
        )
        issues = lyrics.lint_lyrics(
            filtered_lyrics, names, staff_bars, score_default_font=score_default_font
        )

    if args.json:
        print(json.dumps(issues, indent=2))
    else:
        print(lyrics.format_lint_report(issues, typography=typography))

    has_errors = any(issue.get("severity") == "error" for issue in issues)
    return EXIT_COMMAND_FAILED if has_errors else EXIT_OK


async def _run_set_lyric(args: argparse.Namespace) -> int:
    if getattr(args, "raw", False) and not getattr(args, "allow_style_reset", False):
        print(
            "error: --raw can reset lyric typography; pass --allow-style-reset to acknowledge",
            file=sys.stderr,
        )
        return EXIT_COMMAND_FAILED
    text = args.text
    if getattr(args, "font", None):
        size = getattr(args, "font_size", None) or 110
        text = f"\\f{args.font}\\\\s{size}\\{text}"
    elif getattr(args, "font_size", None):
        text = f"\\s{args.font_size}\\{text}"
    elif not getattr(args, "raw", False) and not text.startswith("\\f"):
        try:
            async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
                await _check_bridge_version(client)
                score_info = await _bridge(client, "GetScoreInfo")
                score_default_font = score_info.get("mainTextFontName") if isinstance(score_info, dict) else None

                # Read lyrics on this staff to find the predominant font across the part
                staff_lyrics = await _bridge(client, "ReadLyrics", [args.staff, 0, 0])
                typography = lyrics.analyze_lyric_typography(
                    staff_lyrics, score_default_font=score_default_font
                )
                pred_font = typography.get("predominant_font") or score_default_font or "Times New Roman"
                pred_size = typography.get("predominant_size") or 110

                existing = next(
                    (s for s in staff_lyrics if s.get("bar") == args.bar and s.get("index") == args.index),
                    None,
                )
                chosen_font = None
                chosen_size = None

                if existing:
                    existing_font, existing_size = lyrics.extract_font_and_size(existing)
                    if existing_font and (not pred_font or existing_font == pred_font):
                        chosen_font = existing_font
                        chosen_size = existing_size
                    elif pred_font:
                        chosen_font = pred_font
                        chosen_size = pred_size or existing_size
                elif pred_font:
                    chosen_font = pred_font
                    chosen_size = pred_size

                effective_font = chosen_font or pred_font
                if effective_font == "BigCaslon-Medium":
                    effective_font = "Big Caslon"
                effective_size = chosen_size or pred_size or 110

                text = f"\\f{effective_font}\\\\s{effective_size}\\{text}"
        except Exception:
            pass

    return await _run_op(
        args,
        {"op": "set", **_address(args), "type": "LyricItem", "prop": "Text", "value": text},
        lambda result: {"oldText": result["before"]["text"], "newText": result["after"]["text"]},
    )


async def _run_patch_lyrics(args: argparse.Namespace) -> int:
    try:
        patches = batch_lyrics.load_lyric_patches(args.file)
        if getattr(args, "font", None) is not None and not args.font.strip():
            raise batch_lyrics.BatchLyricsError("--font must be a non-empty string")
        if getattr(args, "font_size", None) is not None and args.font_size < 1:
            raise batch_lyrics.BatchLyricsError("--font-size must be a positive integer")
    except batch_lyrics.BatchLyricsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    ranges = batch_lyrics.affected_lyric_ranges(patches)
    needs_inference = any(
        patch.font is None
        and getattr(args, "font", None) is None
        and patch.font_size is None
        and getattr(args, "font_size", None) is None
        and not patch.text.startswith("\\f")
        for patch in patches
    )

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        info: dict[str, Any] | None = None
        if getattr(args, "expect_file", None) or needs_inference:
            info = await _bridge(client, "GetScoreInfo")
        await _assert_expected_score(client, args, info)

        before: list[dict[str, Any]] = []
        for affected in ranges:
            before.extend(
                await _bridge(
                    client,
                    "ReadLyrics",
                    [affected.staff, affected.from_bar, affected.to_bar],
                )
            )
        try:
            batch_lyrics.validate_patch_targets(patches, before)
        except batch_lyrics.BatchLyricsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_COMMAND_FAILED

        staff_lyrics: dict[int, list[dict[str, Any]]] = {}
        if needs_inference:
            for staff in sorted({patch.staff for patch in patches}):
                staff_lyrics[staff] = await _bridge(client, "ReadLyrics", [staff, 0, 0])

        score_default_font = info.get("mainTextFontName") if info else None
        try:
            rendered = [
                batch_lyrics.resolve_lyric_text(
                    patch,
                    default_font=getattr(args, "font", None),
                    default_font_size=getattr(args, "font_size", None),
                    staff_lyrics=staff_lyrics.get(patch.staff, before),
                    score_default_font=score_default_font,
                )
                for patch in patches
            ]
        except batch_lyrics.BatchLyricsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_COMMAND_FAILED

        # One checked batch: nothing changes unless every target is still a
        # lyric, and the whole patch set is one undo step.
        batch = batch_ops.validate_batch([
            {"op": "set", "staff": patch.staff, "bar": patch.bar, "index": patch.index,
             "type": "LyricItem", "prop": "Text", "value": text}
            for patch, text in zip(patches, rendered)
        ])
        await _require_bridge(client, BATCH_BRIDGE_VERSION, args.subcommand)
        checked = await _apply_batch(client, batch, True)
        if "error" in checked:
            print(f"error: {checked['error']}; nothing was changed", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        backup = await _backup(client, f"before {args.subcommand}")
        outcome = await _apply_batch(client, batch, False)
        if "error" in outcome:
            print(
                f"error: lyric batch stopped after {outcome.get('applied', 0)}/{len(patches)} writes "
                f"(one undo step); backup: {backup.get('copy', '')}; {outcome['error']}",
                file=sys.stderr,
            )
            return EXIT_COMMAND_FAILED
        write_results = [{"oldText": result["before"]["text"]} for result in outcome["results"]]

        after: list[dict[str, Any]] = []
        for affected in ranges:
            after.extend(
                await _bridge(
                    client,
                    "ReadLyrics",
                    [affected.staff, affected.from_bar, affected.to_bar],
                )
            )
        verification = batch_lyrics.verify_lyric_patches(patches, after)

        saved = None
        if all(item.verified for item in verification) and getattr(args, "save", False):
            saved = await _bridge(client, "Save")

    summary = batch_lyrics.build_batch_summary(
        patches, write_results, verification, backup=backup, saved=saved
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    else:
        print(batch_lyrics.format_compact_summary(summary))
    return (
        EXIT_OK
        if summary["verified"] == summary["patched"]
        else EXIT_COMMAND_FAILED
    )


async def _run_set_lyric_style(args: argparse.Namespace) -> int:
    return await _run_write(
        args, "SetLyricStyle", [args.staff, args.bar, args.index, args.style]
    )


async def _run_transpose(args: argparse.Namespace) -> int:
    degree, interval_type = compute_transposition(args.from_note, args.to_note, bool(args.up))
    degree += 7 * args.octaves * (1 if args.up else -1)

    built: dict[str, Any] = {}

    async def build(client: SibeliusClient) -> dict[str, Any]:
        info = await _bridge(client, "GetScoreInfo")
        built.update(
            op="transpose",
            fromBar=args.from_bar or 1, toBar=args.to_bar or info["barCount"],
            topStaff=args.top_staff or 1, bottomStaff=args.bottom_staff or info["staffCount"],
            degree=degree, intervalType=interval_type,
        )
        return dict(built)

    def legacy(result: dict[str, Any]) -> dict[str, Any]:
        return {key: built[key] for key in (
            "degree", "intervalType", "fromBar", "toBar", "topStaff", "bottomStaff",
        )}

    return await _run_op(args, build, legacy)


async def _run_set_key(args: argparse.Namespace) -> int:
    key = args.key[:1].upper() + args.key[1:]
    return await _run_op(
        args,
        {"op": "set-key", "bar": args.bar, "key": key, "minor": args.minor},
        lambda result: result["after"],
    )


async def _run_set_time(args: argparse.Namespace) -> int:
    operation = {"op": "set-time", "bar": args.bar, "numerator": args.top, "denominator": args.bottom}
    if args.symbol:
        operation["symbol"] = args.symbol
    return await _run_op(
        args, operation, lambda result: _legacy_layout({"op": "set-time", "symbol": args.symbol}, result["after"])
    )


async def _run_set_staff_name(args: argparse.Namespace) -> int:
    return await _run_write(
        args, "SetStaffName", [args.staff, args.full or "", args.short or ""]
    )


async def _run_set_initial_instrument(args: argparse.Namespace) -> int:
    style_id = music.resolve_instrument_style(args.instrument)
    return await _run_write(args, "SetInitialInstrument", [args.staff, style_id])


async def _run_duplicate_octave_down_to_voice2(args: argparse.Namespace) -> int:
    return await _run_write(
        args,
        "DuplicateOctaveDownToVoice2",
        [args.staff, args.from_bar, args.to_bar],
    )


async def _run_set_score_info(args: argparse.Namespace) -> int:
    return await _run_write(
        args,
        "SetScoreInfo",
        [args.title or "", args.composer or "", args.lyricist or ""],
    )


async def _run_set_break(args: argparse.Namespace) -> int:
    return await _run_op(
        args, {"op": "set-break", "bar": args.bar, "type": args.type}, lambda result: result["after"]
    )


async def _run_set_barline(args: argparse.Namespace) -> int:
    return await _run_op(
        args,
        {"op": "set-barline", "bar": args.bar, "type": args.type},
        lambda result: _legacy_layout({"op": "set-barline"}, result["after"]),
    )


async def _run_read_barlines(args: argparse.Namespace) -> int:
    from_b, to_b = parse_bar_range(
        bar=getattr(args, "bar", None),
        bars=getattr(args, "bars", None),
        from_bar=getattr(args, "from_bar", None),
        to_bar=getattr(args, "to_bar", None),
    )
    if from_b is None:
        from_b = 1
    if to_b is None:
        to_b = from_b
    return await _run_bridge_call(args, "GetSpecialBarlines", [from_b, to_b])


def _read_order(result: dict[str, Any]) -> list[int] | None:
    try:
        return repeats.parse_bar_order(str(result.get("order", "")))
    except ValueError:
        return None


async def _run_play_order(args: argparse.Namespace) -> int:
    if args.order is None:
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _require_bridge(client, REPEATS_BRIDGE_VERSION, "play-order")
            result = await _bridge(client, "GetPlayOrder")
        print(json.dumps(result, indent=2))
        return EXIT_OK
    try:
        bars = None if args.order.strip().lower() == "auto" else repeats.parse_bar_order(args.order)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _require_bridge(client, REPEATS_BRIDGE_VERSION, "play-order")
        await _assert_expected_score(client, args)
        before = await _bridge(client, "GetPlayOrder")
        if bars is not None and (bad := [n for n in bars if n > before["barCount"]]):
            print(f"error: bar {bad[0]} is outside the score ({before['barCount']} bars)", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        backup = await _backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        result = await _bridge(client, "SetPlayOrder", [bars])
        if bars is not None and _read_order(result) != bars:
            # Assigning the array did not take; try the dialog's own text form.
            result = await _bridge(client, "SetPlayOrderText", [repeats.format_bar_order(bars)])
            if _read_order(result) != bars:
                print(f"error: Sibelius reports the order {result.get('order')!r}, not the requested one",
                      file=sys.stderr)
                return EXIT_COMMAND_FAILED
        if getattr(args, "save", False):
            saved = await _bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps({"before": before, "after": result}, indent=2))
    return EXIT_OK


async def _run_play_on_pass(args: argparse.Namespace) -> int:
    if args.passes is None:
        return await _run_bridge_call(args, "GetPlayOnPass", [args.bar])
    try:
        if args.passes.strip().lower() == "all":
            passes = list(range(1, repeats.MAX_PASS + 1))
        else:
            passes = repeats.parse_passes(args.passes)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _require_bridge(client, REPEATS_BRIDGE_VERSION, "play-on-pass")
        await _assert_expected_score(client, args)
        backup = await _backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        result = await _bridge(client, "SetPlayOnPass", [args.bar, args.type, passes, args.position])
        if getattr(args, "save", False):
            saved = await _bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)
    print(json.dumps(result, indent=2))
    return EXIT_OK


async def _run_copy_passage(args: argparse.Namespace) -> int:
    operation = {
        "op": "copy-passage", "fromBar": args.from_bar, "toBar": args.to_bar,
        "topStaff": args.top_staff, "bottomStaff": args.bottom_staff or args.top_staff,
        "destStaff": args.dest_staff, "destBar": args.dest_bar, "destPosition": args.dest_pos,
    }
    return await _run_op(
        args, operation, lambda result: {k: v for k, v in operation.items() if k != "op"}
    )


async def _run_set_note(args: argparse.Namespace) -> int:
    def legacy(result: dict[str, Any]) -> dict[str, Any]:
        missing = {"name": "", "tied": False, "pitch": args.new_pitch}
        old = next((n for n in _notes(result["before"]) if n["pitch"] == args.old_pitch), missing)
        new = next((n for n in _notes(result["after"]) if n["pitch"] == args.new_pitch), missing)
        return {
            "oldPitch": args.old_pitch, "oldName": old["name"],
            "newPitch": new["pitch"], "newName": new["name"], "tied": old["tied"],
        }

    return await _run_op(
        args,
        {"op": "set-pitch", **_address(args), "oldPitch": args.old_pitch, "newPitch": args.new_pitch},
        legacy,
    )


async def _run_tie(args: argparse.Namespace) -> int:
    return await _run_op(
        args,
        {"op": "tie", **_address(args), "remove": args.remove},
        lambda result: {
            **_address(args), "tied": not args.remove, "notes": len(_notes(result["after"])),
        },
    )


async def _run_delete_object(args: argparse.Namespace) -> int:
    return await _run_op(
        args, {"op": "delete", **_address(args)}, lambda result: {"deleted": result["before"]}
    )


async def _run_delete_voice(args: argparse.Namespace) -> int:
    return await _run_op(
        args,
        {"op": "delete-voice", "fromBar": args.from_bar, "toBar": args.to_bar,
         "staff": args.staff, "voice": args.voice},
        lambda result: {
            "fromBar": args.from_bar, "toBar": args.to_bar, "staff": args.staff,
            "deletedVoice": args.voice, "objects": result["after"]["objects"],
        },
    )


async def _run_clear_bars(args: argparse.Namespace) -> int:
    op: dict[str, Any] = {
        "op": "clear-bars", "fromBar": args.from_bar, "toBar": args.to_bar, "staff": args.staff,
    }
    if args.voice is not None:
        op["voice"] = args.voice
    return await _run_op(args, op, lambda result: result["after"])


async def _run_flip_stem(args: argparse.Namespace) -> int:
    return await _run_op(
        args,
        {"op": "flip-stem", **_address(args)},
        lambda result: {"flipped": True, **_address(args)},
    )


async def _run_bracket(args: argparse.Namespace) -> int:
    return await _run_op(
        args,
        {"op": "bracket", **_address(args), "remove": args.remove},
        lambda result: {
            **_address(args), "bracketed": not args.remove, "notes": len(_notes(result["after"])),
        },
    )


async def _run_beam(args: argparse.Namespace) -> int:
    return await _run_op(
        args,
        {"op": "beam", "staff": args.staff, "bar": args.bar,
         "firstIndex": args.from_index, "lastIndex": args.to_index},
        lambda result: result["after"],
        BEAM_RESULT_BRIDGE_VERSION,
    )


async def _run_nudge(args: argparse.Namespace) -> int:
    return await _run_op(
        args,
        {"op": "nudge", **_address(args), "dx": args.dx, "dy": args.dy},
        lambda result: result["after"],
        NUDGE_BRIDGE_VERSION,
    )


async def _run_add_staff(args: argparse.Namespace) -> int:
    if getattr(args, "above_staff", None):
        return await _run_write(
            args,
            "AddStaffToInstrument",
            [args.above_staff, True, bool(getattr(args, "ossia", False))],
        )
    if getattr(args, "below_staff", None):
        return await _run_write(
            args,
            "AddStaffToInstrument",
            [args.below_staff, False, bool(getattr(args, "ossia", False))],
        )
    if not getattr(args, "instrument", None):
        print(
            "error: --instrument is required (unless --above-staff or --below-staff is given)",
            file=sys.stderr,
        )
        return EXIT_COMMAND_FAILED
    style_id = music.resolve_instrument_style(args.instrument)
    return await _run_write(
        args,
        "CreateStaff",
        [style_id, args.position, args.full_name or "", args.short_name or ""],
    )


async def _run_add_bars(args: argparse.Namespace) -> int:
    count = getattr(args, "count", 1)
    return await _run_op(
        args,
        {"op": "add-bars", "count": count},
        lambda result: {"addedBars": result["after"]["addedBars"], "totalBars": result["after"]["barCount"]},
    )


async def _run_add_notes(args: argparse.Namespace) -> int:
    if getattr(args, "notes", None):
        seq = music.parse_note_sequence(args.notes)
        return await _run_write(
            args,
            "AddNoteSequence",
            [args.staff, args.bar, getattr(args, "pos", 0), seq, args.voice],
        )
    if not getattr(args, "pitches", None):
        print("error: either --pitch/--pitches or --notes is required", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    pitches = [music.parse_pitch(p.strip()) for p in args.pitches.split(",") if p.strip()]
    duration = music.parse_duration(args.duration)
    position = getattr(args, "pos", 0)
    voice = args.voice or 1
    return await _run_op(
        args,
        {
            "op": "add-note", "staff": args.staff, "bar": args.bar, "position": position,
            "duration": duration, "pitches": pitches, "voice": voice,
            "tied": bool(getattr(args, "tied", False)),
        },
        lambda result: {
            "staff": args.staff, "bar": args.bar, "position": position,
            "duration": duration, "voice": voice,
            "notes": [
                {"pitch": n["pitch"], "name": n["name"], "tied": n["tied"]}
                for n in _notes(result["after"])
                if n["pitch"] in pitches
            ],
        },
    )


async def _run_add_abc(args: argparse.Namespace) -> int:
    abc_text = args.abc or getattr(args, "abc_opt", None)
    if not abc_text:
        print("error: ABC notation string is required (positional or --abc)", file=sys.stderr)
        return EXIT_COMMAND_FAILED

    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        info = await _bridge(client, "GetScoreInfo")
        await _assert_expected_score(client, args, info)
        default_key = "C"
        for ks in info.get("keySignatures", []):
            if ks.get("bar", 1) <= args.bar:
                default_key = ks.get("name", "C")

        parsed = abc_notation.parse_abc_snippet(abc_text, default_key=default_key)

        sequence = []
        for n in parsed["notes"]:
            actual_bar = args.bar + (n["bar"] - 1)
            actual_pos = n["position"]
            if n["bar"] == 1:
                actual_pos += getattr(args, "pos", 0)
            sequence.append({
                "bar": actual_bar,
                "position": actual_pos,
                "duration": n["duration"],
                "pitches": n["pitches"],
                "tied": n["tied"],
            })

        backup = await _backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)

        note_result = await _bridge(
            client,
            "AddNoteSequence",
            [args.staff, args.bar, getattr(args, "pos", 0), sequence, args.voice],
        )

        added_lyrics = []
        for lyr in parsed["lyrics"]:
            actual_bar = args.bar + (lyr["bar"] - 1)
            actual_pos = lyr["position"]
            if lyr["bar"] == 1:
                actual_pos += getattr(args, "pos", 0)
            lyr_res = await _bridge(
                client,
                "AddLyric",
                [args.staff, actual_bar, actual_pos, lyr["duration"], lyr["text"], lyr["syllableType"]],
            )
            added_lyrics.append(lyr_res)

        if getattr(args, "save", False):
            saved = await _bridge(client, "Save")
            print(f"saved: {saved.get('fileName', '')}", file=sys.stderr)

    result = {
        "notes": note_result,
        "lyricsCount": len(added_lyrics),
    }
    print(json.dumps(result, indent=2))
    return EXIT_OK


def _print_playback_sounds(staves: list[dict]) -> None:
    for staff in staves:
        override = f"  [Mixer override {staff['override']}]" if staff.get("override") else ""
        for i, change in enumerate(staff.get("sounds", [])):
            where = f"staff {staff['staffNum']}" if i == 0 else f"  from bar {change['bar']}"
            print(f"{where}: {change['soundSet']} / {change['patch']} ({change['actualSoundId']})"
                  f"{override if i == 0 else ''}", file=sys.stderr)


async def _run_playback_sounds(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _require_bridge(client, PLAYBACK_SOUNDS_BRIDGE_VERSION, "playback-sounds")
        staves = await _bridge(client, "GetPlaybackSounds")
    _print_playback_sounds(staves)
    print(json.dumps(staves, indent=2))
    if args.require:
        problems = rehearsal_mix.sound_problems(staves, {s["staffNum"] for s in staves}, args.require)
        if problems:
            print(f"error: not every staff plays {args.require}:", file=sys.stderr)
            for problem in problems:
                print(f"  {problem}", file=sys.stderr)
            return EXIT_COMMAND_FAILED
    return EXIT_OK


def _parse_staff_names(pairs: list[str]) -> dict[int, str]:
    names: dict[int, str] = {}
    for pair in pairs:
        staff, sep, name = pair.partition("=")
        if not sep or not staff.strip().isdigit() or not name.strip():
            raise ValueError(f"--name must look like 1=Soprano, got {pair!r}")
        names[int(staff)] = name.strip()
    return names


async def _run_rehearsal_mixes(args: argparse.Namespace) -> int:
    import shutil

    if not shutil.which("ffmpeg"):
        print("error: rehearsal-mixes needs ffmpeg on PATH (brew install ffmpeg)", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    try:
        overrides = _parse_staff_names(args.name)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="rehearsal-mixes-"))
    stem_dir = out_dir / "stems" if args.keep_stems else work
    stem_dir.mkdir(exist_ok=True)
    try:
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _require_bridge(client, AUDIO_EXPORT_BRIDGE_VERSION, "rehearsal-mixes")
            if args.sib_file:
                await _bridge(client, "OpenScore", [str(Path(args.sib_file).expanduser().resolve())])
            await _assert_expected_score(client, args)
            info = await _bridge(client, "GetScoreInfo")
            staves = await _bridge(client, "GetStaves")
            if unknown := sorted(set(overrides) - {s["staffNum"] for s in staves}):
                print(f"error: --name for staves not in the score: {unknown}", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            vocal = set()
            for staff in staves:
                if args.all_parts or await _bridge(client, "ReadLyrics", [staff["staffNum"], 1, info["barCount"]]):
                    vocal.add(staff["staffNum"])
            await _require_bridge(client, PLAYBACK_SOUNDS_BRIDGE_VERSION, "rehearsal-mixes sound check")
            playback = await _bridge(client, "GetPlaybackSounds")
            _print_playback_sounds(playback)
            if args.require_sound:
                problems = rehearsal_mix.sound_problems(playback, vocal, args.require_sound)
                if problems:
                    print(f"error: voices not playing {args.require_sound}; nothing exported:", file=sys.stderr)
                    for problem in problems:
                        print(f"  {problem}", file=sys.stderr)
                    return EXIT_COMMAND_FAILED
            taken: set[str] = set()
            stems: list[rehearsal_mix.Stem] = []
            for staff in staves:
                num = staff["staffNum"]
                name = rehearsal_mix.staff_name(
                    {**staff, "fullInstrumentName": overrides.get(num, staff.get("fullInstrumentName"))}, taken
                )
                path = stem_dir / f"{num:02d} {name}.aiff"
                print(f"exporting staff {num} ({name})...", file=sys.stderr)
                # The first seconds of an export still sound the previous
                # export's voice (Cantai switches voices late), so a throwaway
                # export of the same staff comes first; the second is clean.
                await _bridge(client, "ExportAudio", [str(work / "warm-up.aiff"), num])
                await _bridge(client, "ExportAudio", [str(path), num])
                if not path.exists():
                    raise BridgeError(f"Sibelius reported exporting {path}, but it does not exist")
                stems.append(rehearsal_mix.Stem(num, name, path, vocal=num in vocal))
        voices = [s for s in stems if s.vocal]
        if not voices:
            print("error: no staff has lyrics, so there are no voices to mix (use --all-parts "
                  "for an instrumental score)", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        loudness = {s.staff: rehearsal_mix.integrated_loudness(s.path) for s in voices}
        gains = rehearsal_mix.voice_gains(loudness)
        title = Path(info["fileName"]).stem if info.get("fileName") else "Score"
        by_staff = {s.staff: s for s in stems}
        measured = []
        for i, mix in enumerate(rehearsal_mix.plan_mixes(stems, gains)):
            print(f"mixing {mix.label}...", file=sys.stderr)
            result = rehearsal_mix.mix_to_wav(mix, by_staff, work / f"mix{i}.wav")
            measured.append({**result, "file": out_dir / f"{title} - {mix.label}.mp3"})
        level = rehearsal_mix.common_loudness(measured, args.loudness)
        results = []
        for m in measured:
            gain_db = level - m["loudness"]
            rehearsal_mix.encode(m["wav"], gain_db, m["file"], args.bitrate)
            results.append({
                "file": str(m["file"]), "gains": m["gains"],
                "gainDb": round(gain_db, 2), "peakDb": round(m["peak"] + gain_db, 2),
            })
        proof_report = None
        if not args.no_proof:
            print("proof-listening to the mixes...", file=sys.stderr)
            proof_report = mix_proof.proof_folder(
                out_dir, stems=[s.path for s in stems], loudness_of=rehearsal_mix.integrated_loudness,
                only=[m["file"] for m in measured],
            )
            print(proof_report.format(), file=sys.stderr)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    print(json.dumps({
        "voices": {s.name: {"staff": s.staff, "loudnessLufs": round(loudness[s.staff], 1),
                            "gainDb": round(20 * math.log10(gains[s.staff]), 2)} for s in voices},
        "accompaniment": [s.name for s in stems if not s.vocal],
        "loudnessLufs": round(level, 1),
        "mixes": results,
        "stems": str(stem_dir) if args.keep_stems else None,
        "proof": proof_report.to_json() if proof_report else None,
    }, indent=2))
    if proof_report and not proof_report.ok:
        print("error: the proof-listening checks found errors; do not upload these mixes until they are "
              "fixed (see the rehearsal-mixes skill)", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    return EXIT_OK


async def _run_proof_mixes(args: argparse.Namespace) -> int:
    import shutil

    if not shutil.which("ffmpeg"):
        print("error: proof-mixes needs ffmpeg on PATH (brew install ffmpeg)", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    folder = Path(args.folder).expanduser().resolve()
    stems = Path(args.stems).expanduser().resolve() if args.stems else None
    for path in (folder, stems):
        if path is not None and not path.is_dir():
            print(f"error: {path} is not a folder", file=sys.stderr)
            return EXIT_COMMAND_FAILED
    report = mix_proof.proof_folder(folder, stems=stems, loudness_of=rehearsal_mix.integrated_loudness)
    print(json.dumps(report.to_json(), indent=2) if args.json else report.format())
    return EXIT_OK if report.ok else EXIT_COMMAND_FAILED


def _export_path(requested: str | None, score_file: str, extension: str) -> Path:
    """Resolve an export target that always carries the format's extension.

    Sibelius appends the extension itself when it is missing (``--out proof``
    is written as ``proof.png``), so the path is normalized up front to name
    the file Sibelius actually writes.
    """
    out = Path(requested).expanduser().resolve() if requested else Path(score_file).with_suffix(extension)
    if out.suffix.lower() != extension:
        out = out.with_name(out.name + extension)
    return out


async def _run_export(args: argparse.Namespace) -> int:
    saveas_type, extension = EXPORT_FORMATS[args.format]
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        if args.sib_file:
            source = Path(args.sib_file).expanduser().resolve()
            if not source.exists():
                print(f"error: {source} does not exist", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            opened = await _bridge(client, "OpenScore", [str(source)])
            print(f"opened: {opened['fileName']}", file=sys.stderr)
        info = await _bridge(client, "GetScoreInfo")
        if not info["fileName"] and not args.out:
            print("error: active score has never been saved; pass --out", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        out = _export_path(args.out, info["fileName"], extension)
        result = await _bridge(client, "ExportScore", [str(out), saveas_type])
    # Sibelius appends page suffixes for image formats (foo_0001.png).
    produced = [out] if out.exists() else sorted(out.parent.glob(f"{out.stem}_*{out.suffix}"))
    if not produced:
        print(
            f"error: Sibelius reported the export but {out} does not exist",
            file=sys.stderr,
        )
        return EXIT_COMMAND_FAILED
    result["files"] = [str(f) for f in produced]
    result["size"] = sum(f.stat().st_size for f in produced)
    print(json.dumps(result, indent=2))
    return EXIT_OK


async def _run_verify_render(args: argparse.Namespace) -> int:
    if args.min_bytes < 1:
        print("error: --min-bytes must be positive", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    saveas_type, extension = EXPORT_FORMATS[args.format]
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        if args.sib_file:
            source = Path(args.sib_file).expanduser().resolve()
            if not source.exists():
                print(f"error: {source} does not exist", file=sys.stderr)
                return EXIT_COMMAND_FAILED
            await _bridge(client, "OpenScore", [str(source)])
        info = await _bridge(client, "GetScoreInfo")
        await _assert_expected_score(client, args, info)
        if not info.get("fileName") and not args.out:
            print("error: active score has never been saved; pass --out", file=sys.stderr)
            return EXIT_COMMAND_FAILED
        out = _export_path(args.out, info["fileName"], extension)
        await _bridge(client, "ExportScore", [str(out), saveas_type])

    produced = [out] if out.exists() else sorted(out.parent.glob(f"{out.stem}_*{out.suffix}"))
    files: list[dict[str, Any]] = []
    for path in produced:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        entry: dict[str, Any] = {"path": str(path), "bytes": size}
        if args.sha256:
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            entry["sha256"] = digest.hexdigest()
        files.append(entry)

    reasons: list[str] = []
    if not files:
        reasons.append(f"no rendered files found at {out}")
    if any(item["bytes"] < args.min_bytes for item in files):
        reasons.append(f"a rendered file is smaller than {args.min_bytes} bytes")
    if args.expect_pages is not None and len(files) != args.expect_pages:
        reasons.append(f"expected {args.expect_pages} rendered files, found {len(files)}")
    report = {
        "verified": not reasons,
        "format": args.format,
        "source": info.get("fileName", ""),
        "files": files,
        "pages": len(files),
        "bytes": sum(item["bytes"] for item in files),
    }
    if reasons:
        report["errors"] = reasons
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return EXIT_OK if report["verified"] else EXIT_COMMAND_FAILED


async def _run_backup(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        await _assert_expected_score(client, args)
        result = await _backup(client, args.name)
    print(json.dumps(result, indent=2))
    return EXIT_OK


def _run_install_plugin(args: argparse.Namespace) -> int:
    import shutil

    source = Path(__file__).parent / "manuscript" / f"{BRIDGE_PLUGIN}.plg"
    if args.plugin_dir:
        plugin_root = Path(args.plugin_dir)
    else:
        supports = sorted(Path.home().glob("Library/Application Support/Avid/Sibelius*"))
        if not supports:
            print(
                "error: no Sibelius support folder found under "
                "~/Library/Application Support/Avid — pass --plugin-dir",
                file=sys.stderr,
            )
            return EXIT_COMMAND_FAILED
        plugin_root = supports[-1] / "Plugins"
    legacy_dir = plugin_root / "Websocket CLI"
    legacy = legacy_dir / "sibwscli.plg"
    if legacy.exists():
        legacy.unlink()
        print(f"Removed old bridge {legacy}")
        try:
            legacy_dir.rmdir()
        except OSError:
            pass  # holds other files; leave it
    dest_dir = plugin_root / "ScoreBridge"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.name
    shutil.copyfile(source, dest)
    print(f"Installed {dest}")
    print("Restart Sibelius (or re-scan plug-ins) for it to load.")
    return EXIT_OK


async def _run_split_parts(args: argparse.Namespace) -> int:
    input_str = args.file_opt or args.score_file
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    source_path: Path | None = None

    if input_str:
        source_path = Path(input_str).expanduser().resolve()
        if not source_path.exists():
            print(f"error: {source_path} does not exist", file=sys.stderr)
            return EXIT_COMMAND_FAILED

    # If input is .sib or omitted, connect to Sibelius to export to MusicXML
    if source_path is None or source_path.suffix.lower() == ".sib":
        temp_dir = tempfile.TemporaryDirectory(prefix="sib_split_parts_")
        exported_xml = Path(temp_dir.name) / "source_export.musicxml"
        async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
            await _check_bridge_version(client)
            if source_path is not None:
                opened = await _bridge(client, "OpenScore", [str(source_path)])
                print(f"opened: {opened.get('fileName', str(source_path))}", file=sys.stderr)
            info = await _bridge(client, "GetScoreInfo")
            saveas_type, _ = EXPORT_FORMATS["musicxml"]
            await _bridge(client, "ExportScore", [str(exported_xml), saveas_type])

        xml_input_path = exported_xml
        file_name = info.get("fileName")
        default_stem = source_path.stem if source_path else (Path(file_name).stem if file_name else "score")
        default_parent = source_path.parent if source_path else (Path(file_name).parent if file_name else Path.cwd())
    else:
        xml_input_path = source_path
        default_stem = source_path.stem
        default_parent = source_path.parent

    # Determine destination output path
    if args.out:
        out_path = Path(args.out).expanduser().resolve()
    else:
        out_path = default_parent / f"{default_stem}_{args.preset}.mxl"

    try:
        from ai_score_editing.musicxml_split.profiles.polychoral_16 import split_16voices
        from ai_score_editing.musicxml_split.profiles.satb import SATBOptions, split_satb
        from ai_score_editing.musicxml_split.validation import validate_file

        def parse_ranges(value: str | None) -> frozenset[int]:
            bars: set[int] = set()
            for item in (value or "").split(","):
                item = item.strip()
                if not item:
                    continue
                start, separator, end = item.partition("-")
                bars.update(range(int(start), int(end) + 1) if separator else [int(start)])
            return frozenset(bars)

        if args.preset == "16voices":
            result = split_16voices(xml_input_path, None if args.audit else out_path, audit_only=args.audit)
        elif args.preset == "satb":
            result = split_satb(
                xml_input_path,
                None if args.audit else out_path,
                SATBOptions(
                    soprano_solo_bars=parse_ranges(args.soprano_solo),
                    tenor_solo_bars=parse_ranges(args.tenor_solo),
                    bass_solo_bars=parse_ranges(args.bass_solo),
                ),
                audit_only=args.audit,
            )
        else:
            print(f"error: unknown preset {args.preset}", file=sys.stderr)
            return EXIT_COMMAND_FAILED

        res = result.as_dict(xml_input_path)
        val_issues = validate_file(out_path, expected_parts=len(result.parts)) if args.validate and not args.audit else []
        all_issues = result.issues + val_issues
        res["valid"] = not any(issue.severity == "error" for issue in all_issues)
        res["issues"] = [issue.as_dict() for issue in all_issues]
        if val_issues:
            res["validationIssues"] = [issue.as_dict() for issue in val_issues]

        if args.open and not args.audit:
            launcher.open_score_file(out_path, app_path=args.sibelius_path)
            res["opened"] = True

        if args.json:
            print(json.dumps(res, indent=2))
        else:
            action = "Audited" if args.audit else "Demixed"
            print(f"{action} {res['totalMeasures']} measures across {res['partsCount']} parts ({args.preset}).")
            if not args.audit:
                print(f"Saved to: {res['outputFile']}")
            if args.validate:
                if all_issues:
                    print(
                        f"Validation warning: {len(all_issues)} issue(s) detected:",
                        file=sys.stderr,
                    )
                    for issue in all_issues[:10]:
                        print(f"  - {issue.code}: {issue.message}", file=sys.stderr)
                else:
                    print("Validation passed: 0 discrepancies found.")
        return EXIT_OK
    finally:
        if temp_dir is not None:
            temp_dir.cleanup()


async def _run_round(args: argparse.Namespace) -> int:
    import xml.etree.ElementTree as ET

    from ai_score_editing.musicxml_round import RoundOptions, build_round
    from ai_score_editing.musicxml_split.io import parse_musicxml, save_musicxml

    source = Path(args.score_file).expanduser().resolve()
    if source.suffix.lower() not in {".xml", ".musicxml", ".mxl"}:
        print("error: round needs MusicXML input; export .sib scores first", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    out = Path(args.out).expanduser().resolve() if args.out else source.with_name(f"{source.stem}_round.musicxml")
    try:
        _, root = parse_musicxml(source)
        result = build_round(root, RoundOptions(
            voices=args.voices, gap=args.gap, passes=args.passes,
            program=args.program, hold_final=args.hold_final,
        ))
    except (OSError, ValueError, ET.ParseError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    save_musicxml(result.root, out)
    summary = {**result.as_dict(), "outputFile": str(out)}
    if args.open:
        launcher.open_score_file(out, app_path=args.sibelius_path)
        summary["opened"] = True
    print(layout.compact_summary(summary))
    return EXIT_OK


def _client(args: argparse.Namespace, plugins: list[str] | None = None) -> SibeliusClient:
    return SibeliusClient(
        host=args.host,
        port=args.port,
        client_name=args.client_name,
        approval_timeout=args.timeout,
        plugins=plugins,
        launch_if_needed=args.launch,
        launch_timeout=args.launch_timeout,
        app_path=args.sibelius_path,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    global _BACKUP_DIR
    backup_dir = args.backup_dir or os.environ.get("SIBELIUS_BACKUP_DIR")
    _BACKUP_DIR = Path(backup_dir).expanduser() if backup_dir else None
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(message)s",
    )

    if args.subcommand == "forget-token":
        removed = TokenStore().forget(args.host, args.port)
        print("Token removed" if removed else "No token stored")
        return EXIT_OK
    if args.subcommand == "install-plugin":
        return _run_install_plugin(args)

    runner = {
        "ping": _run_ping,
        "command": _run_command,
        "invoke": _run_invoke,
        "raw": _run_raw,
        "repl": _run_repl,
        "plugin": _run_plugin,
        "score-info": _run_score_info,
        "staves": _run_staves,
        "selection": _run_selection,
        "inspect": _run_inspect,
        "score-snapshot": _run_score_snapshot,
        "proofread": _run_proofread,
        "patch-layout": _run_patch_layout,
        "patch-notes": _run_patch_notes,
        "read": _run_read,
        "do": _run_do,
        "query": _run_query,
        "apply": _run_apply,
        "bridge-version": _run_bridge_version,
        "read-lyrics": _run_read_lyrics,
        "check-lyrics": _run_check_lyrics,
        "set-lyric": _run_set_lyric,
        "patch-lyrics": _run_patch_lyrics,
        "transpose": _run_transpose,
        "set-key": _run_set_key,
        "set-time": _run_set_time,
        "backup": _run_backup,
        "export": _run_export,
        "rehearsal-mixes": _run_rehearsal_mixes,
        "proof-mixes": _run_proof_mixes,
        "playback-sounds": _run_playback_sounds,
        "verify-render": _run_verify_render,
        "copy-passage": _run_copy_passage,
        "set-note": _run_set_note,
        "tie": _run_tie,
        "delete-object": _run_delete_object,
        "delete-voice": _run_delete_voice,
        "clear-bars": _run_clear_bars,
        "save": _run_save,
        "reset-design": _run_reset_design,
        "flip-stem": _run_flip_stem,
        "bracket": _run_bracket,
        "beam": _run_beam,
        "nudge": _run_nudge,
        "read-abc": _run_read_abc,
        "add-staff": _run_add_staff,
        "create-staff": _run_add_staff,
        "add-bars": _run_add_bars,
        "add-notes": _run_add_notes,
        "add-note": _run_add_notes,
        "add-abc": _run_add_abc,
        "set-staff-name": _run_set_staff_name,
        "set-initial-instrument": _run_set_initial_instrument,
        "duplicate-octave-down-to-voice2": _run_duplicate_octave_down_to_voice2,
        "set-score-info": _run_set_score_info,
        "set-break": _run_set_break,
        "set-barline": _run_set_barline,
        "read-barlines": _run_read_barlines,
        "play-order": _run_play_order,
        "play-on-pass": _run_play_on_pass,
        "set-lyric-style": _run_set_lyric_style,
        "split-parts": _run_split_parts,
        "demix": _run_split_parts,
        "round": _run_round,
    }[args.subcommand]
    try:
        return int(run_sync(runner(args)))
    except BridgeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_COMMAND_FAILED
    except ConnectionFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED
    except TimeoutError:
        print("error: timed out waiting for a response from Sibelius", file=sys.stderr)
        return EXIT_CONNECTION_FAILED
