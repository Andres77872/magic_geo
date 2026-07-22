"""Command-line interface for magic_geo.

Layout: `_app` holds the Typer application and the shared world loader,
`_constants` the domain thresholds, `validators/` the pure per-domain failure
checkers, and `commands/` one module per command group. This module is the
public facade: the console script, `python -m magic_geo`, and the tests all
import from here.
"""

from __future__ import annotations

from ..config import write_config
from ._app import _load_world_for_cli, app
from ._constants import *  # noqa: F401,F403
from .validators import *  # noqa: F401,F403
from .validators import _validate_route_corridors  # noqa: F401
from . import commands as _commands  # noqa: F401  (registers every @app.command)

__all__ = ["app", "main", "write_config"]


def main() -> None:
    app()
