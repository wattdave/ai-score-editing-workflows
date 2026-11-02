"""Helpers shared by the command modules.

Command modules import from here, never from ``sibelius.cli`` at module level,
so ``cli`` can import them without a cycle.
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from ai_score_editing.sibelius import protocol

EXIT_OK = 0
EXIT_COMMAND_FAILED = 1
EXIT_CONNECTION_FAILED = 2


def emit(args: argparse.Namespace, response: dict[str, Any], human: str) -> int:
    print(json.dumps(response) if args.json else human)
    return EXIT_OK if protocol.is_success(response) else EXIT_COMMAND_FAILED


def client(args: argparse.Namespace, plugins: list[str] | None = None) -> Any:
    """Build the Sibelius client through ``cli._client``.

    The lookup is late on purpose: tests and skill scripts patch
    ``ai_score_editing.sibelius.cli._client`` as the one seam for every handler.
    """
    from ai_score_editing.sibelius import cli

    return cli._client(args, plugins)
