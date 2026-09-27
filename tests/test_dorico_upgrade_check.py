"""Keep the upgrade check's command list in step with the Dorico back end."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("dorico_upgrade_check", ROOT / "scripts" / "dorico_upgrade_check.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)

COMMAND = re.compile(r'"((?:Edit|EventEdit|NoteInput|NoteEdit|File|Print|Window|Filter|Script)\.[A-Za-z]+)')


def test_every_command_the_back_end_sends_is_checked() -> None:
    sources = (ROOT / "src" / "sibelius_websocket_cli" / "dorico").glob("*.py")
    used = {m for p in sources for m in COMMAND.findall(p.read_text())}
    # f"Filter.LyricsLine{verse}" is found as its prefix.
    unchecked = [u for u in used if not any(r == u or r.startswith(u) for r in check.REQUIRED_COMMANDS)]
    assert not unchecked, f"add these to REQUIRED_COMMANDS: {sorted(unchecked)}"


def test_required_commands_are_in_the_baseline() -> None:
    baseline = set((ROOT / "docs" / "dorico-baseline" / "commands-6.2.30.txt").read_text().split())
    assert [c for c in check.REQUIRED_COMMANDS if c not in baseline] == []
    classes = set((ROOT / "docs" / "dorico-baseline" / "lua-classes-6.2.30.txt").read_text().split())
    assert [c for c in check.REQUIRED_CLASSES if c not in classes] == []
