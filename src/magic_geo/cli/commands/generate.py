"""`generate` command."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Annotated

import typer
from pydantic import ValidationError

from .._app import app
from ...api import generate_geo_world, generate_world
from ...config import load_config
from ...io import write_cells_csv, write_summary_markdown, write_world


@app.command("generate")
def generate(
    config: Annotated[Path, typer.Option("--config", "-c", exists=True, help="YAML config path.")] = Path(
        "magic-geo.yaml"
    ),
    output: Annotated[Path, typer.Option("--output", "-o", help="World .json or fast .mgeo output path.")] = Path(
        "runs/world.json"
    ),
    summary: Annotated[Path | None, typer.Option("--summary", help="Optional Markdown summary path.")] = None,
    cells_csv: Annotated[Path | None, typer.Option("--cells-csv", help="Optional cell CSV path.")] = None,
    cells: Annotated[
        int | None, typer.Option("--cells", min=128, help="Override mesh.cell_count for smoke runs.")
    ] = None,
    geo_only: Annotated[
        bool,
        typer.Option(
            "--geo-only",
            help="Generate only natural geography enrichments; omit civilization, settlement, and history layers.",
        ),
    ] = False,
    world_format: Annotated[
        str,
        typer.Option(
            "--format",
            help="World serialization: auto (from suffix), json, or mgeo.",
        ),
    ] = "auto",
) -> None:
    """Generate a planet from YAML config."""
    try:
        world_config = load_config(config)
        if cells is not None:
            data = world_config.model_dump(mode="python")
            data["mesh"]["cell_count"] = cells
            world_config = type(world_config).model_validate(data)
    except (OSError, ValidationError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc

    if world_format not in {"auto", "json", "mgeo"}:
        typer.echo("--format must be auto, json, or mgeo", err=True)
        raise typer.Exit(2)

    scope = "geo_only" if geo_only else "full_world"
    started = time.monotonic()
    typer.echo(
        f"Generating world | scope={scope} cells={world_config.mesh.cell_count}",
        err=True,
    )
    try:
        world = (
            generate_geo_world(world_config)
            if geo_only
            else generate_world(world_config)
        )
    except (RuntimeError, ValueError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    # The generation pipeline owns this object and its JSON-value invariants;
    # skip the otherwise-public recursive preflight on the hot save path.
    write_world(output, world, format=world_format, validate_model=False)
    if summary is not None:
        write_summary_markdown(summary, world)
    if cells_csv is not None:
        write_cells_csv(cells_csv, world)

    s = world["summary"]
    typer.echo(
        f"Wrote {output} | scope={scope} "
        f"cells={s['cell_count']} plates={s['plate_count']} "
        f"ocean={s['ocean_fraction']:.3f} rivers={s['river_count']} "
        f"elapsed={time.monotonic() - started:.1f}s"
    )
