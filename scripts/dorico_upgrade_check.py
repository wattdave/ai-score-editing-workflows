#!/usr/bin/env python3
"""Read-only smoke check of the Dorico back end after a Dorico upgrade.

Run with a project open in Dorico (any project; nothing is changed):

    uv run python scripts/dorico_upgrade_check.py [--baseline 6.2.30]

It records the Dorico, Qt and Lua versions, checks the Remote Control
connection, the Lua bridge (read, dump() fallback, layout, blocks, current
layout), the application log the command discovery relies on, and System
Events access, and diffs Dorico's command list and Lua classes against the
baselines in docs/dorico-baseline/. Any command the back end sends that the
new Dorico no longer lists, or a Lua class the bridge needs, is a FAIL.
The live write checks are in docs/dorico-upgrade-checklist.md.
"""

from __future__ import annotations

import argparse
import asyncio
import plistlib
import subprocess
import sys
from pathlib import Path

from sibelius_websocket_cli.dorico.bridge import DoricoBridge
from sibelius_websocket_cli.dorico.client import DoricoClient, DoricoError
from sibelius_websocket_cli.dorico.export import APPLICATION_LOG

ROOT = Path(__file__).resolve().parent.parent
BASELINES = ROOT / "docs" / "dorico-baseline"
APP = Path("/Applications/Dorico 6.app")

#: Every Dorico command the back end sends (a test keeps this in step with
#: the source). A missing one breaks a feature.
REQUIRED_COMMANDS = sorted({
    "Script.RunScript", "Edit.Undo", "Edit.Redo", "Edit.SelectAll", "Edit.SelectMore", "Edit.Copy", "Edit.Paste",
    "Edit.CreateSystemBreak", "Edit.LineOfLyrics", "EventEdit.Select", "EventEdit.Delete",
    "EventEdit.NavigateRightExtendBar", "File.Export", "File.ScoreInfo", "Print.ExportCurrentLayoutAsPDF",
    "Filter.LyricsLine1", "Filter.LyricsLine2", "Filter.LyricsLine3", "Filter.LyricsLine4", "Filter.LyricsLine5",
    "Window.SwitchMode", "Window.SwitchToLayout", "NoteInput.Mode", "NoteInput.CreateDynamic",
    "NoteInput.SetArticulation", "NoteInput.SlurStart", "NoteInput.CreateTempo", "NoteInput.CreateRehearsalMark",
    "NoteInput.CreateTimeSignature", "NoteInput.CreateKeySignature", "NoteInput.CreateBarLine",
    "NoteInput.StartLyricInput", "NoteInput.AcceptCurrentLyricInput", "NoteInput.AdvanceLyricInput",
    "NoteEdit.PitchUpChromatic", "NoteEdit.PitchDownChromatic", "NoteEdit.RespellUsingNoteNameAbove",
    "NoteEdit.RespellUsingNoteNameBelow", "NoteInput.OttavaLineStart", "NoteInput.CreateOrnament",
    "NoteInput.CreatePlayingTechnique", "NoteInput.CreateGlissando", "EventEdit.DurationLengthenByValue",
    "EventEdit.DurationShortenByValue",
})
#: Lua classes bridge.lua constructs or relies on.
REQUIRED_CLASSES = ["DoApp", "MIDIPitch", "MIDIPitchWithSpelling", "NoteName", "PropertyContext",
                    "RhythmicLength", "Score", "ScriptHost", "Variant"]

results: list[tuple[str, str, str]] = []


def report(status: str, check: str, detail: str = "") -> None:
    results.append((status, check, detail))
    print(f"{status:<4} {check}" + (f": {detail}" if detail else ""))


def qt_version(app: Path) -> str | None:
    plist = app / "Contents/Frameworks/QtCore.framework/Resources/Info.plist"
    try:
        return plistlib.loads(plist.read_bytes()).get("CFBundleVersion")
    except OSError:
        return None


def diff(kind: str, baseline: Path, current: list[str], required: list[str]) -> None:
    missing_required = [r for r in required if r not in current]
    if missing_required:
        report("FAIL", f"{kind} the back end needs", f"missing {missing_required}")
    else:
        report("PASS", f"{kind} the back end needs", f"all {len(required)} present")
    if not baseline.exists():
        report("WARN", f"{kind} baseline", f"{baseline.name} not found; nothing to diff")
        return
    old = set(baseline.read_text().split())
    added, removed = sorted(set(current) - old), sorted(old - set(current))
    status = "PASS" if not added and not removed else "WARN"
    report(status, f"{kind} vs {baseline.name}", f"+{len(added)} -{len(removed)}"
           + (f"; removed: {removed[:15]}" if removed else "") + (f"; added: {added[:15]}" if added else ""))


async def run(baseline: str, app: Path, write_baseline: bool = False) -> None:
    try:
        client = DoricoClient(allow_approval=False)
        await client.connect()
    except DoricoError as exc:
        report("FAIL", "connect to Dorico", str(exc))
        return
    bridge = DoricoBridge(client)
    try:
        info = await client.app_info()
        report("INFO", "Dorico", f"{info.get('variant')} {info.get('number')}")
        report("INFO", "Qt", qt_version(app) or "unknown")
        status = await client.status()
        report("PASS" if status.get("hasScore") else "FAIL", "a project is open", f"mode {status.get('windowMode')}")

        try:
            version = await bridge.call("version")
            window = await bridge.call("window")
            report("PASS", "Lua bridge runs", f"bridge {version['bridge']}, {version['lua']}, Dorico {window.get('version')}")
            report("PASS" if window.get("layoutID") is not None else "FAIL", "DoApp.currentLayoutID",
                   str(window.get("layoutID")))
        except DoricoError as exc:
            report("FAIL", "Lua bridge runs", str(exc)[:200])
            return

        overview = await bridge.overview()
        layout = overview.get("layout") or {}
        ok = layout.get("staves") and layout.get("instruments") and layout.get("blocks")
        report("PASS" if ok else "FAIL", "raw layout (staves, instruments, blocks)",
               f"{len(layout.get('staves') or [])} staves, {len(layout.get('instruments') or [])} instruments")

        read = await bridge.call("read", flow=1, skipUnreadable=True)
        events = read.get("events") or []
        dumped, unreadable = read.get("dumped") or [], read.get("unreadable") or []
        report("PASS" if events else "WARN", "read events", f"{len(events)} events")
        if dumped:
            ids = [e for e in events if e.get("source") == "dump" and e.get("id") is not None]
            report("PASS" if ids else "FAIL", "dump() fallback", f"{len(dumped)} stream(s) dumped, {len(ids)} events with ids")
        else:
            report("INFO", "dump() fallback", "no stream needed it in this project (open one with lyrics to test it)")
        if unreadable:
            report("FAIL", "streams neither readable nor dumpable", str(unreadable))

        classes = (await bridge.call("classes"))["classes"]
        version = info.get("number")
        diff("Lua classes", BASELINES / f"lua-classes-{baseline}.txt", classes, REQUIRED_CLASSES)
        commands = await client.request({"message": "getcommands"}, "commandlist", timeout=60)
        names = sorted(c["name"] for c in commands.get("commands", []))
        diff("commands", BASELINES / f"commands-{baseline}.txt", names, REQUIRED_COMMANDS)
        if write_baseline and version:
            (BASELINES / f"commands-{version}.txt").write_text("\n".join(names) + "\n")
            (BASELINES / f"lua-classes-{version}.txt").write_text("\n".join(classes) + "\n")
            report("INFO", "baselines written", f"commands-{version}.txt, lua-classes-{version}.txt")
    finally:
        await client.close()

    log = APPLICATION_LOG
    tail = log.read_text(errors="replace")[-200_000:] if log.exists() else ""
    report("PASS" if "Executing command: Script.RunScript" in tail else "FAIL", "application.log records commands", str(log))
    probe = subprocess.run(["osascript", "-e", 'tell application "System Events" to get name of process "Dorico 6"'],
                           capture_output=True, text=True)
    report("PASS" if probe.returncode == 0 else "FAIL", "System Events can see Dorico (Accessibility)",
           probe.stderr.strip()[:120])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--baseline", default="6.2.30", help="Dorico version of the baselines to diff against")
    parser.add_argument("--app", type=Path, default=APP)
    parser.add_argument("--write-baseline", action="store_true",
                        help="also save this Dorico's command and Lua class lists as new baselines")
    args = parser.parse_args(argv)
    asyncio.run(run(args.baseline, args.app, args.write_baseline))
    failed = [r for r in results if r[0] == "FAIL"]
    print(f"\n{len(failed)} failure(s), {sum(r[0] == 'WARN' for r in results)} warning(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
