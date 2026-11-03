"""Helpers shared by the command modules."""

from __future__ import annotations

import argparse
import json
from typing import Any

from ai_score_editing.cli_common import EXIT_COMMAND_FAILED, EXIT_CONNECTION_FAILED, EXIT_OK  # noqa: F401
from ai_score_editing.sibelius import protocol


def emit(args: argparse.Namespace, response: dict[str, Any], human: str) -> int:
    print(json.dumps(response) if args.json else human)
    return EXIT_OK if protocol.is_success(response) else EXIT_COMMAND_FAILED
