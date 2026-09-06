"""Command-line interface (SPEC.md 2.2)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from sibelius_websocket_cli import protocol
from sibelius_websocket_cli.client import ConnectionFailed, SibeliusClient, run_sync
from sibelius_websocket_cli.intervals import compute_transposition
from sibelius_websocket_cli.token_store import TokenStore

EXIT_OK = 0
EXIT_COMMAND_FAILED = 1
EXIT_CONNECTION_FAILED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sibelius-websocket-cli",
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
    parser.add_argument("--json", action="store_true", help="print raw JSON responses")
    parser.add_argument("-v", "--verbose", action="store_true", help="log the wire traffic")

    sub = parser.add_subparsers(dest="subcommand", required=True)
    sub.add_parser("ping", help="check that Sibelius responds")
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
        help="read info about the open score (requires the bundled sibwscli plug-in)",
    )
    sub.add_parser("staves", help="list staves of the open score (requires bridge plug-in)")
    sub.add_parser("selection", help="describe the current selection (requires bridge plug-in)")
    read = sub.add_parser("read", help="read bar contents (requires bridge plug-in)")
    read.add_argument("--staff", type=int, default=1, help="staff number, from 1")
    read.add_argument("--from", dest="from_bar", type=int, default=1, help="first bar, from 1")
    read.add_argument("--to", dest="to_bar", type=int, help="last bar (default: same as --from)")
    sub.add_parser("bridge-version", help="report the installed bridge plug-in version")
    read_lyrics = sub.add_parser("read-lyrics", help="list all lyrics with addresses")
    read_lyrics.add_argument("--staff", type=int, default=0, help="staff number (0 = all)")
    set_lyric = sub.add_parser("set-lyric", help="rewrite one lyric syllable (backs up first)")
    set_lyric.add_argument("--staff", type=int, required=True)
    set_lyric.add_argument("--bar", type=int, required=True)
    set_lyric.add_argument("--index", type=int, required=True)
    set_lyric.add_argument("--text", required=True)
    transpose = sub.add_parser("transpose", help="transpose a passage or the whole score (backs up first)")
    transpose.add_argument("--from-note", required=True, help="current tonic, e.g. C or Eb")
    transpose.add_argument("--to-note", required=True, help="target tonic, e.g. D or F#")
    direction = transpose.add_mutually_exclusive_group(required=True)
    direction.add_argument("--up", action="store_true")
    direction.add_argument("--down", action="store_true")
    transpose.add_argument("--from-bar", type=int, help="default: 1")
    transpose.add_argument("--to-bar", type=int, help="default: last bar")
    transpose.add_argument("--top-staff", type=int, help="default: 1")
    transpose.add_argument("--bottom-staff", type=int, help="default: last staff")
    set_key = sub.add_parser("set-key", help="add a key signature (backs up first)")
    set_key.add_argument("--bar", type=int, default=1)
    set_key.add_argument("--key", required=True, help='key name, e.g. D or Bb')
    set_key.add_argument("--minor", action="store_true")
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
        help="copy the bundled sibwscli.plg bridge into the Sibelius plug-in folder",
    )
    install.add_argument(
        "--plugin-dir",
        help="override the Sibelius user plug-in directory",
    )
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


BRIDGE_PLUGIN = "sibwscli"

# Curated friendly names -> ManuScript command IDs (see docs/commands.md).
# Note these are fire-and-forget: Sibelius acknowledges receipt but never
# reports whether the command did anything (SPEC.md 1.2).
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
            "bridge plug-in not reachable — run 'sibelius-websocket-cli "
            f"install-plugin' and restart Sibelius. Response: {json.dumps(response)}"
        )
    value = protocol.plugin_return_value(response)
    if isinstance(value, dict) and "error" in value:
        raise BridgeError(value["error"])
    return value


async def _check_bridge_version(client: SibeliusClient) -> None:
    info = await _bridge(client, "GetBridgeVersion")
    if not (isinstance(info, dict) and info.get("version") == 3):
        raise BridgeError(
            f"bridge v3 required, got {info!r} — run install-plugin and restart Sibelius"
        )


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
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    copy = source.with_name(f"{source.stem}.backup-{stamp}{source.suffix}")
    shutil.copy2(source, copy)
    return {"version": version, "savedTo": str(source), "copy": str(copy)}


async def _run_write(
    args: argparse.Namespace, method: str, call_args: list[Any]
) -> int:
    """Backup, then run a bridge write method and print its result."""
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        backup = await _backup(client, f"before {args.subcommand}")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        result = await _bridge(client, method, call_args)
    print(json.dumps(result, indent=2))
    return EXIT_OK


async def _run_bridge_call(
    args: argparse.Namespace, method: str, call_args: list[Any] | None = None
) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        response = await client.invoke_plugin(BRIDGE_PLUGIN, method, call_args)
    if not protocol.is_success(response):
        print(
            "error: bridge plug-in not reachable — run "
            "'sibelius-websocket-cli install-plugin' and restart Sibelius. "
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


async def _run_read(args: argparse.Namespace) -> int:
    to_bar = args.to_bar if args.to_bar is not None else args.from_bar
    return await _run_bridge_call(args, "ReadBars", [args.staff, args.from_bar, to_bar])


async def _run_do(args: argparse.Namespace) -> int:
    command_id = NAMED_OPERATIONS[args.operation]
    async with _client(args) as client:
        response = await client.invoke_commands([command_id])
    return _emit(args, response, f"sent {args.operation} ({command_id})")


async def _run_bridge_version(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "GetBridgeVersion")


async def _run_read_lyrics(args: argparse.Namespace) -> int:
    return await _run_bridge_call(args, "ReadLyrics", [args.staff])


async def _run_set_lyric(args: argparse.Namespace) -> int:
    return await _run_write(args, "SetLyricText", [args.staff, args.bar, args.index, args.text])


async def _run_transpose(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
        info = await _bridge(client, "GetScoreInfo")
        from_bar = args.from_bar or 1
        to_bar = args.to_bar or info["barCount"]
        top = args.top_staff or 1
        bottom = args.bottom_staff or info["staffCount"]
        degree, interval_type = compute_transposition(
            args.from_note, args.to_note, bool(args.up)
        )
        backup = await _backup(client, "before transpose")
        print(f"backed up: {backup['copy']}", file=sys.stderr)
        result = await _bridge(
            client,
            "TransposePassage",
            [from_bar, to_bar, top, bottom, degree, interval_type],
        )
    print(json.dumps(result, indent=2))
    return EXIT_OK


async def _run_set_key(args: argparse.Namespace) -> int:
    return await _run_write(args, "SetKeySignature", [args.bar, args.key, not args.minor])


async def _run_backup(args: argparse.Namespace) -> int:
    async with _client(args, plugins=[BRIDGE_PLUGIN]) as client:
        await _check_bridge_version(client)
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
    dest_dir = plugin_root / "Websocket CLI"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / source.name
    shutil.copyfile(source, dest)
    print(f"Installed {dest}")
    print("Restart Sibelius (or re-scan plug-ins) for it to load.")
    return EXIT_OK


def _client(args: argparse.Namespace, plugins: list[str] | None = None) -> SibeliusClient:
    return SibeliusClient(
        host=args.host,
        port=args.port,
        client_name=args.client_name,
        approval_timeout=args.timeout,
        plugins=plugins,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
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
        "read": _run_read,
        "do": _run_do,
        "bridge-version": _run_bridge_version,
        "read-lyrics": _run_read_lyrics,
        "set-lyric": _run_set_lyric,
        "transpose": _run_transpose,
        "set-key": _run_set_key,
        "backup": _run_backup,
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
