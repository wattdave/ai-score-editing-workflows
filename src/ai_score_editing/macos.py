"""macOS helpers shared by the editor back ends: AppleScript and app state."""

from __future__ import annotations

import asyncio
import subprocess

#: Seconds one osascript run may take before it is killed.
OSASCRIPT_TIMEOUT = 60.0


class OsascriptError(RuntimeError):
    """osascript exited with an error. ``accessibility`` is True when macOS
    denied UI scripting."""

    def __init__(self, message: str, accessibility: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.accessibility = accessibility


def _text(data: bytes) -> str:
    """Decode output as subprocess.run(text=True) did, newlines included."""
    return data.decode().replace("\r\n", "\n").replace("\r", "\n")


def _failure(stderr: str) -> OsascriptError:
    message = stderr.strip()
    return OsascriptError(message, accessibility="assistive access" in message or "not allowed" in message)


async def osascript(script: str, *args: str, timeout: float | None = None) -> str:
    """Run an AppleScript with osascript without blocking the event loop.

    Returns stripped stdout. Raises OsascriptError on a non-zero exit and
    subprocess.TimeoutExpired when the script outlives the timeout (the
    process is killed, as it is on cancellation).
    """
    limit = OSASCRIPT_TIMEOUT if timeout is None else timeout
    process = await asyncio.create_subprocess_exec(
        "osascript", "-", *args,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(script.encode()), limit)
    except BaseException as exc:
        # A timeout or cancellation must not leave osascript running.
        if process.returncode is None:
            process.kill()
            await process.wait()
        if isinstance(exc, TimeoutError):
            # As subprocess.run raised: a TimeoutError is an OSError, which
            # the MCP session would take for a dropped connection.
            raise subprocess.TimeoutExpired(["osascript", "-", *args], limit) from None
        raise
    if process.returncode != 0:
        raise _failure(_text(stderr))
    return _text(stdout).strip()


def osascript_sync(script: str, *args: str, timeout: float = 15.0) -> str:
    """Blocking osascript; same results and errors as osascript()."""
    done = subprocess.run(
        ["osascript", "-", *args], input=script, capture_output=True, text=True, timeout=timeout
    )
    if done.returncode != 0:
        raise _failure(done.stderr)
    return done.stdout.strip()


async def bring_to_front(process: str) -> None:
    """Make the System Events process called `process` the frontmost app."""
    await osascript(
        'on run argv\ntell application "System Events" to tell process (item 1 of argv) '
        "to set frontmost to true\nend run",
        process,
    )


def is_running(bundle_id: str) -> bool:
    """True if the app with this bundle id is running (False if osascript fails)."""
    try:
        out = osascript_sync(f'application id "{bundle_id}" is running')
    except (OSError, subprocess.TimeoutExpired, OsascriptError):
        return False
    return out.lower() == "true"
