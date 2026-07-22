"""`render` and `render-raster` commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .._app import _load_world_for_cli, app
from ...io import write_raster_map, write_svg_map


@app.command("render")
def render(
    world: Annotated[Path, typer.Option("--world", "-w", exists=True, help="Generated .json or .mgeo world.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="SVG map output path.")] = Path(
        "runs/world.svg"
    ),
    width: Annotated[int, typer.Option("--width", min=320, max=6400, help="SVG width in pixels.")] = 1600,
    height: Annotated[int, typer.Option("--height", min=160, max=3200, help="SVG height in pixels.")] = 800,
    projection: Annotated[
        str,
        typer.Option(
            "--projection",
            help="SVG projection: equirectangular, mollweide, or orthographic.",
        ),
    ] = "equirectangular",
    labels: Annotated[bool, typer.Option("--labels/--no-labels", help="Render settlement labels.")] = False,
    max_cells: Annotated[
        int | None,
        typer.Option("--max-cells", min=128, help="Optional maximum cells to render for low-detail maps."),
    ] = None,
    contours: Annotated[bool, typer.Option("--contours/--no-contours", help="Render symbolic elevation contour layer.")] = True,
    contour_interval: Annotated[
        float,
        typer.Option("--contour-interval", min=50.0, help="Contour interval in meters when contours are enabled."),
    ] = 500.0,
) -> None:
    """Render a generated world file as a layer-driven SVG map."""
    payload = _load_world_for_cli(world)
    try:
        write_svg_map(
            output,
            payload,
            width=width,
            height=height,
            projection=projection,
            labels=labels,
            max_cells=max_cells,
            contours=contours,
            contour_interval_m=contour_interval,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"Wrote {output}")


@app.command("render-raster")
def render_raster(
    world: Annotated[Path, typer.Option("--world", "-w", exists=True, help="Generated .json or .mgeo world.")],
    output: Annotated[Path, typer.Option("--output", "-o", help="PPM raster map output path.")] = Path(
        "runs/world.ppm"
    ),
    width: Annotated[int, typer.Option("--width", min=320, max=6400, help="Raster width in pixels.")] = 1600,
    height: Annotated[int, typer.Option("--height", min=160, max=3200, help="Raster height in pixels.")] = 800,
    projection: Annotated[
        str,
        typer.Option(
            "--projection",
            help="Raster projection: equirectangular, mollweide, or orthographic.",
        ),
    ] = "equirectangular",
    max_cells: Annotated[
        int | None,
        typer.Option("--max-cells", min=128, help="Optional maximum cells to render for low-detail rasters."),
    ] = None,
    texture: Annotated[bool, typer.Option("--texture/--no-texture", help="Apply deterministic terrain texture.")] = True,
) -> None:
    """Render a generated world file as a dependency-free PPM raster map."""
    payload = _load_world_for_cli(world)
    try:
        write_raster_map(
            output,
            payload,
            width=width,
            height=height,
            projection=projection,
            max_cells=max_cells,
            texture=texture,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(f"Wrote {output}")
