"""Command-line interface (SPEC.md 2.2)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from sibelius_websocket_cli import protocol
from sibelius_websocket_cli.client import ConnectionFailed, SibeliusClient, run_sync
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


def _client(args: argparse.Namespace) -> SibeliusClient:
    return SibeliusClient(
        host=args.host,
        port=args.port,
        client_name=args.client_name,
        approval_timeout=args.timeout,
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

    runner = {
        "ping": _run_ping,
        "command": _run_command,
        "invoke": _run_invoke,
        "raw": _run_raw,
        "repl": _run_repl,
    }[args.subcommand]
    try:
        return int(run_sync(runner(args)))
    except ConnectionFailed as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_CONNECTION_FAILED
    except TimeoutError:
        print("error: timed out waiting for a response from Sibelius", file=sys.stderr)
        return EXIT_CONNECTION_FAILED
