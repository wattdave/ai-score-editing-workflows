"""Sibelius Connect wire protocol: message builders and response parsing.

See docs/sibelius-protocol.md section 1 for the empirically verified protocol.
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
MSG_INVOKE_PLUGIN = "invokePlugin"
MSG_INVOKE_PLUGIN_RESPONSE = "invokePluginResponse"
MSG_ERROR = "messageProcessingError"


def connect_message(
    client_name: str,
    session_token: str | None = None,
    plugins: list[str] | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {
        "message": MSG_CONNECT,
        "clientName": client_name,
        "handshakeVersion": HANDSHAKE_VERSION,
    }
    if session_token is not None:
        message["sessionToken"] = session_token
    # The plug-in list is only honored on a tokenless connect; it cannot be
    # changed when reconnecting with a session token (docs/sibelius-protocol.md 1.1).
    if plugins:
        message["plugins"] = plugins
    return message


def command_message(command_name: str) -> dict[str, Any]:
    return {"message": MSG_COMMAND, "commandName": command_name}


def invoke_commands_message(commands: list[str]) -> dict[str, Any]:
    return {"message": MSG_INVOKE_COMMANDS, "commands": commands}


def invoke_plugin_message(
    name: str,
    method: str | None = None,
    args: list[Any] | None = None,
) -> dict[str, Any]:
    message: dict[str, Any] = {"message": MSG_INVOKE_PLUGIN, "name": name}
    if method is not None:
        message["method"] = method
    if args is not None:
        message["args"] = args
    return message


def plugin_return_value(response: dict[str, Any]) -> Any:
    """Extract the return value from an invokePluginResponse.

    The guide contradicts itself on the field name (return_value in the
    example, returnValue in prose), so accept either.
    """
    if "return_value" in response:
        return response["return_value"]
    return response.get("returnValue")


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
