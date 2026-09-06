"""Sibelius Connect wire protocol: message builders and response parsing.

See SPEC.md section 1 for the empirically verified protocol.
"""

from __future__ import annotations

from typing import Any

HANDSHAKE_VERSION = "1.0"
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 1898
DEFAULT_CLIENT_NAME = "sibelius-websocket-cli"

MSG_CONNECT = "connect"
MSG_CONNECT_RESPONSE = "connectResponse"
MSG_COMMAND = "command"
MSG_COMMAND_RESPONSE = "commandResponse"
MSG_INVOKE_COMMANDS = "invokeCommands"
MSG_INVOKE_COMMANDS_RESPONSE = "invokeCommandsResponse"
MSG_ERROR = "messageProcessingError"


def connect_message(client_name: str, session_token: str | None = None) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message": MSG_CONNECT,
        "clientName": client_name,
        "handshakeVersion": HANDSHAKE_VERSION,
    }
    if session_token is not None:
        message["sessionToken"] = session_token
    return message


def command_message(command_name: str) -> dict[str, Any]:
    return {"message": MSG_COMMAND, "commandName": command_name}


def invoke_commands_message(commands: list[str]) -> dict[str, Any]:
    return {"message": MSG_INVOKE_COMMANDS, "commands": commands}


class ProtocolError(Exception):
    """The server replied with something the protocol does not allow here."""


def parse_connect_response(response: dict[str, Any]) -> str:
    """Validate a connectResponse and return its session token."""
    if response.get("message") != MSG_CONNECT_RESPONSE:
        raise ProtocolError(f"Expected {MSG_CONNECT_RESPONSE}, got: {response}")
    if response.get("result") is not True:
        raise ProtocolError(f"Connection refused by Sibelius: {response}")
    token = response.get("sessionToken")
    if not isinstance(token, str) or not token:
        raise ProtocolError(f"No sessionToken in connectResponse: {response}")
    return token


def is_success(response: dict[str, Any]) -> bool:
    return response.get("result") is True
