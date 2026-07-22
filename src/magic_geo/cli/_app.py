"""Typer application object and the shared world loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from ..io import read_world


app = typer.Typer(no_args_is_help=True, help="Causal planet generator CLI.")


def _load_world_for_cli(path: Path) -> dict[str, Any]:
    try:
        # CLI paths are user-selected, so retain strict JSON-model validation.
        # Trusted in-process callers can opt into the faster unchecked API.
        return read_world(path)
    except (OSError, UnicodeError, ValueError) as exc:
        typer.echo(f"Invalid world file: {exc}", err=True)
        raise typer.Exit(2) from exc
