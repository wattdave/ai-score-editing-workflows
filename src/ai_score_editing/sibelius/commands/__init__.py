"""Command areas of ``sibelius-cli``, one module per area.

To add or move an area:

1. Create ``commands/<area>.py`` with ``register(sub) -> dict[str, Callable]``. It
   adds the area's subparsers (aliases included) to ``sub`` and returns a mapping
   of subcommand name (aliases included) to handler. Handlers take ``args`` and
   return an exit code; async handlers are run by ``cli.main``.
2. Move the area's ``_run_*`` handlers into the module. Import helpers from
   ``.bridge``, ``.service`` and ``commands._common`` (``emit``, ``client``,
   ``EXIT_*``), not from ``cli``: ``cli`` imports this package.
3. In ``cli.py`` re-export each moved name that tests or skill scripts import or
   patch (for example ``_run_set_note = <area>._run_set_note``), and delete the
   old parser lines and ``runner`` entries.

There is no list to edit: ``register_all`` discovers every public module in this
package (names not starting with ``_``) in alphabetical order, so each area PR
touches only its own module plus the deletions in ``cli.py``.
``cli._client`` is the single seam tests patch; ``_common.client`` looks it up
at call time.
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
