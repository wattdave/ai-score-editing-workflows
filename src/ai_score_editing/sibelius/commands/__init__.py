"""Command areas of ``sibelius-cli``, one module per area.

To add or move an area:

1. Create ``commands/<area>.py`` with ``register(sub) -> dict[str, Callable]``. It
   adds the area's subparsers (aliases included) to ``sub`` and returns a mapping
   of subcommand name (aliases included) to handler. Handlers take ``args`` and
   return an exit code; async handlers are run by ``cli.main``.
2. Move the area's ``_run_*`` handlers into the module. Import helpers from
   ``sibelius.bridge``, ``sibelius.service``, ``sibelius.runner`` (client factory,
   guards, ``run_op``/``run_write``, backup) and ``commands._common`` (``emit``,
   ``EXIT_*``), not from ``cli``: ``cli`` imports this package. Call bridge and
   runner helpers through their module (``bridge.call(...)``) so tests can patch
   them there.

There is no list to edit: ``register_all`` discovers every public module in this
package (names not starting with ``_``) in alphabetical order.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from typing import Any

Handler = Callable[..., Any]


def register_all(sub: Any) -> dict[str, Handler]:
    """Register every area on ``sub`` and return the merged name -> handler map."""
    handlers: dict[str, Handler] = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        for name, handler in module.register(sub).items():
            if name in handlers:
                raise RuntimeError(f"subcommand {name!r} registered twice")
            handlers[name] = handler
    return handlers
