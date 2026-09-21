#!/usr/bin/env python3
"""Helper tool for diagnosing and verifying hanging playback notes in Sibelius."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from sibelius_websocket_cli.client import SibeliusClient
    from sibelius_websocket_cli.cli import _bridge, BRIDGE_PLUGIN, _backup
    HAVE_CLIENT = True
except ImportError:
    HAVE_CLIENT = False


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def pitch_to_name(pitch: int) -> str:
    """Return scientific pitch name (e.g. 60 -> C4)."""
    octave = (pitch // 12) - 1
    name = NOTE_NAMES[pitch % 12]
    return f"{name}{octave}"


def parse_midi_events(data: bytes) -> tuple[int, int, list[dict[str, Any]]]:
    """Parse standard MIDI file data into track events."""
    if len(data) < 14:
        raise ValueError("File too short to be valid MIDI")
    header_type, header_len, format_, ntracks, division = struct.unpack(">4sIHHH", data[:14])
    if header_type != b"MThd":
        raise ValueError("Invalid MIDI header")

    tracks_output = []
    offset = 14
    for t_idx in range(ntracks):
        if offset >= len(data):
            break
        track_type, track_len = struct.unpack(">4sI", data[offset:offset+8])
        offset += 8
        track_data = data[offset:offset+track_len]
        offset += track_len

        pos = 0
        current_time = 0
        running_status = None
        events = []
        track_name = f"Track {t_idx}"

        while pos < len(track_data):
            delta = 0
            while True:
                b = track_data[pos]
                pos += 1
                delta = (delta << 7) | (b & 0x7F)
                if not (b & 0x80):
                    break
            current_time += delta

            b = track_data[pos]
            if b & 0x80:
                status = b
                pos += 1
                running_status = status
            else:
                status = running_status

            if status == 0xFF:
                meta_type = track_data[pos]
                pos += 1
                length = 0
                while True:
                    b = track_data[pos]
                    pos += 1
                    length = (length << 7) | (b & 0x7F)
                    if not (b & 0x80):
                        break
                meta_data = track_data[pos:pos+length]
                pos += length
                if meta_type == 0x03:
                    try:
                        track_name = meta_data.decode("utf-8", errors="replace")
                    except Exception:
                        pass
            elif status in (0xF0, 0xF7):
                length = 0
                while True:
                    b = track_data[pos]
                    pos += 1
                    length = (length << 7) | (b & 0x7F)
                    if not (b & 0x80):
                        break
                pos += length
            else:
                msg_type = status & 0xF0
                channel = status & 0x0F
                if msg_type in (0x80, 0x90, 0xA0, 0xB0, 0xE0):
                    p1 = track_data[pos]
                    p2 = track_data[pos+1]
                    pos += 2
                    events.append((current_time, msg_type, channel, p1, p2))
                elif msg_type in (0xC0, 0xD0):
                    p1 = track_data[pos]
                    pos += 1
                    events.append((current_time, msg_type, channel, p1, 0))

        active_notes: dict[tuple[int, int], list[tuple[int, int]]] = {}
        completed_notes = []
        for time_, msg_type, channel, p1, p2 in events:
            key = (channel, p1)
            if msg_type == 0x90 and p2 > 0:
                active_notes.setdefault(key, []).append((time_, p2))
            elif msg_type == 0x80 or (msg_type == 0x90 and p2 == 0):
                if key in active_notes and active_notes[key]:
                    start_t, vel = active_notes[key].pop(0)
                    completed_notes.append({
                        "start_tick": start_t,
                        "end_tick": time_,
                        "duration_ticks": time_ - start_t,
                        "channel": channel,
                        "pitch": p1,
                        "velocity": vel,
                    })

        hanging = []
        for (channel, p1), starts in active_notes.items():
            for start_t, vel in starts:
                hanging.append({
                    "start_tick": start_t,
                    "channel": channel,
                    "pitch": p1,
                    "velocity": vel,
                })

        tracks_output.append({
            "track_index": t_idx,
            "track_name": track_name,
            "completed_notes": completed_notes,
            "hanging_notes": hanging,
        })

    return format_, division, tracks_output


def cmd_audit_midi(args: argparse.Namespace) -> int:
    """Audit a MIDI file for hanging notes or abnormally long sustain."""
    path = Path(args.midi_file)
    if not path.exists():
        print(f"error: MIDI file not found: {path}", file=sys.stderr)
        return 1

    with open(path, "rb") as f:
        data = f.read()

    _, division, tracks = parse_midi_events(data)
    bar_ticks = 4 * division  # default assumption: 4/4 time
    max_beats = args.max_beats

    total_hanging = 0
    total_long = 0

    for trk in tracks:
        name = trk["track_name"]
        hanging = trk["hanging_notes"]
        completed = trk["completed_notes"]

        long_notes = [
            n for n in completed
            if (n["duration_ticks"] / division) > max_beats
        ]

        if hanging or long_notes:
            print(f"\n=== Track {trk['track_index']}: {name} ===")

        if hanging:
            total_hanging += len(hanging)
            print("  [!] HANGING NOTES (Note-On without Note-Off):")
            for h in hanging:
                bar = (h["start_tick"] // bar_ticks) + 1
                beat = ((h["start_tick"] % bar_ticks) / division) + 1
                pname = pitch_to_name(h["pitch"])
                print(f"      Pitch: {pname} (MIDI {h['pitch']}) at Bar {bar}, Beat {beat:.2f} (tick {h['start_tick']})")

        if long_notes:
            total_long += len(long_notes)
            print(f"  [!] ABNORMALLY LONG NOTES (> {max_beats} beats):")
            for n in long_notes:
                bar = (n["start_tick"] // bar_ticks) + 1
                beat = ((n["start_tick"] % bar_ticks) / division) + 1
                dur_beats = n["duration_ticks"] / division
                pname = pitch_to_name(n["pitch"])
                print(f"      Pitch: {pname} (MIDI {n['pitch']}) at Bar {bar}, Beat {beat:.2f} -> dur={dur_beats:.2f} beats")

    if total_hanging == 0 and total_long == 0:
        print(f"Clean MIDI: no hanging notes and no notes exceeding {max_beats} beats found in {path.name}.")
        return 0
    else:
        print(f"\nAudit completed: {total_hanging} hanging note(s), {total_long} long sustain note(s) flagged.")
        return 1 if total_hanging > 0 else 0


def audit_score_data(
    bars_data: list[dict[str, Any]],
    staff_num: int = 1,
) -> dict[str, Any]:
    """Audit score bars for dangling ties, tuplet boundary ties, and same-pitch re-attacks."""
    notes_sequence = []
    tuplets_seen = set()

    for bar in bars_data:
        bar_num = bar.get("barNumber", 0)
        objects = bar.get("objects", [])
        for obj in objects:
            idx = obj.get("index", 0)
            otype = obj.get("type", "")
            pos = obj.get("position", 0)
            if otype == "Tuplet":
                tuplets_seen.add((bar_num, pos))
            elif otype == "NoteRest":
                notes = obj.get("notes", [])
                notes_sequence.append({
                    "bar": bar_num,
                    "index": idx,
                    "position": pos,
                    "duration": obj.get("duration", 0),
                    "voice": obj.get("voice", 1),
                    "is_rest": len(notes) == 0,
                    "notes": notes,
                })

    dangling = []
    tuplet_ties = []
    reattacks = []

    for i, current in enumerate(notes_sequence):
        for n in current["notes"]:
            if n.get("tied") is True:
                curr_pitch = n.get("pitch")
                curr_name = n.get("name")
                next_obj = None
                next_obj_idx = None
                for cand_idx in range(i + 1, len(notes_sequence)):
                    candidate = notes_sequence[cand_idx]
                    if candidate["voice"] == current["voice"]:
                        next_obj = candidate
                        next_obj_idx = cand_idx
                        break

                if not next_obj:
                    dangling.append({
                        "bar": current["bar"],
                        "index": current["index"],
                        "pitch": curr_pitch,
                        "name": curr_name,
                        "reason": "Tie has no following note in passage/score",
                    })
                elif next_obj["is_rest"]:
                    dangling.append({
                        "bar": current["bar"],
                        "index": current["index"],
                        "pitch": curr_pitch,
                        "name": curr_name,
                        "reason": f"Tie connects to a rest in Bar {next_obj['bar']} at index {next_obj['index']}",
                    })
                else:
                    matching_pitch = any(nxt.get("pitch") == curr_pitch for nxt in next_obj["notes"])
                    if not matching_pitch:
                        next_pitches = [nxt.get("name") for nxt in next_obj["notes"]]
                        dangling.append({
                            "bar": current["bar"],
                            "index": current["index"],
                            "pitch": curr_pitch,
                            "name": curr_name,
                            "reason": f"Tie pitch mismatch: current {curr_name} (pitch {curr_pitch}) -> next note is {next_pitches} in Bar {next_obj['bar']} index {next_obj['index']}",
                        })
                    else:
                        # Tuplet boundary check
                        crosses_tuplet = any(
                            (current["bar"] < tb or (current["bar"] == tb and current["position"] <= tp)) and
                            (tb < next_obj["bar"] or (tb == next_obj["bar"] and tp <= next_obj["position"]))
                            for tb, tp in tuplets_seen
                        )
                        if crosses_tuplet:
                            tuplet_ties.append({
                                "bar": current["bar"],
                                "index": current["index"],
                                "pitch": curr_pitch,
                                "name": curr_name,
                                "next_bar": next_obj["bar"],
                                "next_index": next_obj["index"],
                                "reason": f"Tie crosses a tuplet boundary into Bar {next_obj['bar']} index {next_obj['index']}",
                            })

                        # Same-pitch re-attack conflict check
                        if next_obj_idx is not None:
                            for sub_idx in range(next_obj_idx + 1, len(notes_sequence)):
                                sub_cand = notes_sequence[sub_idx]
                                if sub_cand["voice"] == current["voice"]:
                                    if sub_cand["is_rest"]:
                                        break
                                    if sub_cand["bar"] > next_obj["bar"] + 1:
                                        break
                                    if any(sn.get("pitch") == curr_pitch for sn in sub_cand["notes"]):
                                        reattacks.append({
                                            "bar": current["bar"],
                                            "index": current["index"],
                                            "pitch": curr_pitch,
                                            "name": curr_name,
                                            "next_bar": next_obj["bar"],
                                            "next_index": next_obj["index"],
                                            "reattack_bar": sub_cand["bar"],
                                            "reattack_index": sub_cand["index"],
                                            "reattack_position": sub_cand["position"],
                                            "reason": (
                                                f"Note is tied to Bar {next_obj['bar']} idx {next_obj['index']}, but the same pitch {curr_name} "
                                                f"re-attacks at Bar {sub_cand['bar']} pos {sub_cand['position']} in the same voice without voice separation. "
                                                f"SoundWorld drops Note-Off for the tied note when the re-attack ends."
                                            ),
                                        })
                                        break
                                    else:
                                        break

    return {
        "staff": staff_num,
        "dangling": dangling,
        "tuplet_ties": tuplet_ties,
        "reattacks": reattacks,
    }


def format_audit_results(results: dict[str, Any]) -> tuple[str, bool]:
    """Format audit results for a staff into user-readable report. Returns (report_text, has_errors)."""
    lines = []
    staff = results["staff"]
    dangling = results.get("dangling", [])
    tuplet_ties = results.get("tuplet_ties", [])
    reattacks = results.get("reattacks", [])

    has_errors = bool(dangling or reattacks)

    if dangling:
        lines.append(f"\n[!] Flagged {len(dangling)} DEFECTIVE DANGLING TIE(S) on Staff {staff} (Tier 1 Error - Safe to Auto-Remove):")
        for d in dangling:
            lines.append(f"  • Bar {d['bar']} index {d['index']}: {d['name']} (pitch {d['pitch']})")
            lines.append(f"    Reason: {d['reason']}")
            lines.append(f"    Suggested Fix: uv run sibelius-websocket-cli tie --staff {staff} --bar {d['bar']} --index {d['index']} --remove\n")

    if reattacks:
        lines.append(f"\n[!] Flagged {len(reattacks)} SAME-PITCH RE-ATTACK CONFLICT(S) on Staff {staff} (Tier 3 Error - Dropped Note-Off Hazard):")
        for r in reattacks:
            lines.append(f"  • Bar {r['bar']} index {r['index']}: {r['name']} (pitch {r['pitch']}) -> Bar {r['next_bar']} index {r['next_index']}")
            lines.append(f"    Hazard: Re-attacks at Bar {r['reattack_bar']} pos {r['reattack_position']} in same voice")
            lines.append(f"    Reason: {r['reason']}")
            lines.append(f"    Suggested Fix: uv run sibelius-websocket-cli tie --staff {staff} --bar {r['bar']} --index {r['index']} --remove\n")

    if tuplet_ties:
        lines.append(f"\n[i] Found {len(tuplet_ties)} NOTATIONALLY VALID TUPLET BOUNDARY TIE(S) on Staff {staff} (Tier 2 Playback Engine Bug):")
        for t in tuplet_ties:
            lines.append(f"  • Bar {t['bar']} index {t['index']}: {t['name']} (pitch {t['pitch']}) -> Bar {t['next_bar']} index {t['next_index']}")
            lines.append(f"    Notice: Matches sheet music notation. If Sibelius's real-time playback engine hangs on this note,")
            lines.append(f"            remove the tie and replace with a Slur ('S' in Sibelius) to preserve visual engraving and restore clean playback.")
            lines.append(f"    Workaround: uv run sibelius-websocket-cli tie --staff {staff} --bar {t['bar']} --index {t['index']} --remove\n")

    return "\n".join(lines), has_errors


def cmd_audit_score(args: argparse.Namespace) -> int:
    """Audit score bars via sibelius-websocket-cli read to detect playback hang hazards."""
    staff_arg = str(args.staff).lower().strip()
    from_bar = args.from_bar
    to_bar = args.to_bar

    # Determine staves to audit
    target_staves = []
    if staff_arg in ("all", "0"):
        info_res = subprocess.run(["uv", "run", "sibelius-websocket-cli", "score-info"], capture_output=True, text=True)
        if info_res.returncode == 0:
            try:
                staff_count = json.loads(info_res.stdout).get("staffCount", 16)
                target_staves = list(range(1, staff_count + 1))
            except Exception:
                target_staves = list(range(1, 17))
        else:
            target_staves = list(range(1, 17))
    elif "," in staff_arg:
        target_staves = [int(s) for s in staff_arg.split(",") if s.strip().isdigit()]
    elif "-" in staff_arg:
        start_s, end_s = staff_arg.split("-", 1)
        target_staves = list(range(int(start_s), int(end_s) + 1))
    else:
        target_staves = [int(staff_arg)]

    total_issues = 0
    total_clean = 0

    for s in target_staves:
        cmd = ["uv", "run", "sibelius-websocket-cli", "read", "--staff", str(s), "--from", str(from_bar), "--to", str(to_bar)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"error calling sibelius-websocket-cli for staff {s}: {res.stderr}", file=sys.stderr)
            total_issues += 1
            continue

        try:
            bars_data = json.loads(res.stdout)
        except json.JSONDecodeError as exc:
            print(f"error decoding score JSON for staff {s}: {exc}", file=sys.stderr)
            total_issues += 1
            continue

        audit_res = audit_score_data(bars_data, staff_num=s)
        report, has_err = format_audit_results(audit_res)

        if report:
            print(report)
            if has_err:
                total_issues += 1
        else:
            total_clean += 1

    if total_issues == 0:
        if len(target_staves) == 1:
            print(f"Clean score: no hanging note hazards detected on Staff {target_staves[0]} in bars {from_bar}-{to_bar}.")
        else:
            print(f"Clean score: no hanging note hazards detected across all {len(target_staves)} staves in bars {from_bar}-{to_bar}.")
        return 0

    return 1


def cmd_render_pdf(args: argparse.Namespace) -> int:
    """Render a target page of a source PDF to PNG using native macOS PDFKit."""
    pdf_path = Path(args.pdf_file).expanduser().resolve()
    if not pdf_path.exists():
        print(f"error: PDF file not found: {pdf_path}", file=sys.stderr)
        return 1

    page_idx = args.page - 1  # 0-based for PDFKit
    if page_idx < 0:
        print("error: page number must be >= 1", file=sys.stderr)
        return 1

    out_path = Path(args.out).resolve() if args.out else Path(f"/private/tmp/{pdf_path.stem}_p{args.page}.png")

    swift_script = f"""
import AppKit
import PDFKit

guard let doc = PDFDocument(url: URL(fileURLWithPath: "{pdf_path}")),
      let page = doc.page(at: {page_idx}) else {{
    print("error: failed to load page {args.page} from {pdf_path}")
    exit(1)
}}
let box = page.bounds(for: .mediaBox)
let img = page.thumbnail(of: CGSize(width: box.width * 2, height: box.height * 2), for: .mediaBox)
if let tiff = img.tiffRepresentation,
   let rep = NSBitmapImageRep(data: tiff),
   let png = rep.representation(using: .png, properties: [:]) {{
    do {{
        try png.write(to: URL(fileURLWithPath: "{out_path}"))
        print("Rendered page {args.page} to {out_path}")
    }} catch {{
        print("error saving png: \\(error)")
        exit(1)
    }}
}}
"""
    res = subprocess.run(["swift", "-"], input=swift_script, text=True, capture_output=True)
    if res.returncode != 0:
        print(f"error running swift renderer:\n{res.stderr}", file=sys.stderr)
        return res.returncode

    print(res.stdout.strip())
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit and diagnose hanging notes in Sibelius scores.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # audit-midi
    p_midi = subparsers.add_parser("audit-midi", help="Scan exported MIDI for unclosed or long-ringing notes")
    p_midi.add_argument("midi_file", help="Path to exported .mid file")
    p_midi.add_argument("--max-beats", type=float, default=8.0, help="Flag notes exceeding this duration in beats (default: 8.0)")
    p_midi.set_defaults(func=cmd_audit_midi)

    # audit-score
    p_score = subparsers.add_parser("audit-score", help="Audit live score structure for dangling ties and re-attack conflicts")
    p_score.add_argument("--staff", default="1", help="Staff number (1, 2, 'all', or range '1-4') (default: 1)")
    p_score.add_argument("--from-bar", type=int, default=1, help="First bar (default: 1)")
    p_score.add_argument("--to-bar", type=int, default=10, help="Last bar (default: 10)")
    p_score.set_defaults(func=cmd_audit_score)

    # render-pdf
    p_pdf = subparsers.add_parser("render-pdf", help="Render a page of source PDF to PNG for visual ground truth")
    p_pdf.add_argument("pdf_file", help="Path to source PDF file")
    p_pdf.add_argument("page", type=int, help="Page number (1-based)")
    p_pdf.add_argument("--out", help="Output PNG path (default: /private/tmp/<name>_p<N>.png)")
    p_pdf.set_defaults(func=cmd_render_pdf)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
