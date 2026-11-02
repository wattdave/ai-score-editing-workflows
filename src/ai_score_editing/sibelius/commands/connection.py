"""Connection commands: ping, command, invoke, raw, repl, plugin, install-plugin, forget-token."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ai_score_editing.sibelius import protocol
from ai_score_editing.sibelius.bridge import BRIDGE_PLUGIN
from ai_score_editing.sibelius.commands._common import EXIT_COMMAND_FAILED, EXIT_OK, emit as _emit
from ai_score_editing.sibelius.commands._common import client as _client
from ai_score_editing.token_store import TokenStore


def register(sub: Any) -> dict[str, Callable[..., Any]]:
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
    install = sub.add_parser(
        "install-plugin",
        help="copy the bundled ScoreBridge.plg bridge into the Sibelius plug-in folder",
    )
    install.add_argument(
        "--plugin-dir",
        help="override the Sibelius user plug-in directory",
    )
    sub.add_parser("forget-token", help="delete the cached session token for host:port")
    return {
        "ping": _run_ping,
        "command": _run_command,
        "invoke": _run_invoke,
        "raw": _run_raw,
        "repl": _run_repl,
        "plugin": _run_plugin,
        "install-plugin": _run_install_plugin,
        "forget-token": _run_forget_token,
    }


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


def _run_install_plugin(args: argparse.Namespace) -> int:
    import shutil

    source = Path(__file__).parent.parent / "manuscript" / f"{BRIDGE_PLUGIN}.plg"
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


def _run_forget_token(args: argparse.Namespace) -> int:
    removed = TokenStore().forget(args.host, args.port)
    print("Token removed" if removed else "No token stored")
    return EXIT_OK
