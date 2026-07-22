"""`init-config` and `backend` commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from .._app import app
from ...api import backend_info
from ...config import ConfigError, create_config, parse_config_overrides


@app.command("init-config")
def init_config(
    output: Annotated[Path, typer.Option("--output", "-o", help="New YAML config path.")] = Path(
        "magic-geo.yaml"
    ),
    profile: Annotated[
        str,
        typer.Option(
            "--profile",
            "-p",
            help="Built-in starting profile: default, earthlike, or smoke.",
        ),
    ] = "earthlike",
    overrides: Annotated[
        list[str] | None,
        typer.Option(
            "--set",
            help="Override section.field=YAML_VALUE; repeat for multiple fields.",
        ),
    ] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite the target file.")] = False,
) -> None:
    """Create a validated, editable YAML configuration."""
    try:
        config = create_config(
            profile,
            parse_config_overrides(overrides or ()),
        )
        from magic_geo import cli as _cli

        _cli.write_config(output, config, force=force)
    except (ConfigError, OSError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"Wrote {output} | profile={profile}")


@app.command("backend")
def backend() -> None:
    """Print native backend and OpenCL probe information."""
    typer.echo(json.dumps(backend_info(), indent=2, sort_keys=True))
