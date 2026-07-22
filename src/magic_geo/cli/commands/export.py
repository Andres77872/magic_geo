"""`export-debug-map`, `export-debug`, and `export-rerun` commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .._app import _load_world_for_cli, app


@app.command("export-debug-map")
def export_debug_map(
    debug_dir: Annotated[
        Path,
        typer.Option(
            "--debug-dir",
            "-d",
            exists=True,
            file_okay=False,
            help="Debug cache directory produced by export-debug.",
        ),
    ] = Path("runs/debug"),
    layer: Annotated[
        str | None,
        typer.Option(
            "--layer",
            "-l",
            help="Manifest layer id (default: cells/elevation_m, then the first numeric layer).",
        ),
    ] = None,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Output basename; .png and .gpt-image-prompt.md are appended (default: runs/<generated name>).",
        ),
    ] = None,
    projection: Annotated[
        str,
        typer.Option("--projection", help="Map projection: globe, equirect, or mollweide."),
    ] = "globe",
    width: Annotated[int, typer.Option("--width", min=320, max=6400, help="PNG width in pixels.")] = 1600,
    height: Annotated[int, typer.Option("--height", min=160, max=3200, help="PNG height in pixels.")] = 900,
    stage: Annotated[int, typer.Option("--stage", min=0, help="Zero-based stage for *_stage layers.")] = 0,
    month: Annotated[int, typer.Option("--month", min=1, max=12, help="Month (1-12) for monthly layers.")] = 1,
    center_lat: Annotated[
        float,
        typer.Option("--center-lat", min=-90.0, max=90.0, help="Latitude at the center of the exported view."),
    ] = 0.0,
    center_lon: Annotated[
        float,
        typer.Option("--center-lon", min=-360.0, max=360.0, help="Longitude at the center of the exported view."),
    ] = 0.0,
    camera_distance: Annotated[
        float | None,
        typer.Option(
            "--camera-distance",
            min=1.01,
            max=100.0,
            help="Perspective camera distance (default: 3.0 globe, 3.4 flat).",
        ),
    ] = None,
    camera_position: Annotated[
        str | None,
        typer.Option(
            "--camera-position",
            help="Exact Three.js camera position as x,y,z; enables explicit web-camera replay.",
        ),
    ] = None,
    camera_target: Annotated[
        str | None,
        typer.Option(
            "--camera-target",
            help="Exact OrbitControls target as x,y,z (requires --camera-position; default: 0,0,0).",
        ),
    ] = None,
    camera_up: Annotated[
        str | None,
        typer.Option(
            "--camera-up",
            help="Exact Three.js camera up vector as x,y,z (requires --camera-position; default: 0,1,0).",
        ),
    ] = None,
    vertical_fov: Annotated[
        float,
        typer.Option("--vertical-fov", min=1.0, max=179.0, help="Perspective vertical field of view in degrees."),
    ] = 50.0,
    cache_identity: Annotated[
        str | None,
        typer.Option(
            "--cache-identity",
            help="Browser cache identity override for byte-exact view-fingerprint/name parity.",
        ),
    ] = None,
    wireframe: Annotated[
        bool,
        typer.Option("--wireframe/--no-wireframe", help="Include diagnostic cell/triangle edges in the PNG."),
    ] = False,
    plates: Annotated[
        bool,
        typer.Option("--plates/--no-plates", help="Include diagnostic plate-boundary guides in the PNG."),
    ] = False,
    graticule: Annotated[
        bool,
        typer.Option("--graticule/--no-graticule", help="Include diagnostic latitude/longitude guides in the PNG."),
    ] = False,
    image: Annotated[
        bool,
        typer.Option("--image/--no-image", help="Write the diagnostic PNG reference image."),
    ] = True,
    prompt: Annotated[
        bool,
        typer.Option("--prompt/--no-prompt", help="Write the copy/paste GPT Image Markdown prompt and color codex."),
    ] = True,
) -> None:
    """Export a debug layer PNG and matching GPT Image prompt without a browser."""

    try:
        from ...debug_map_export import export_map_reference
    except ImportError as exc:
        typer.echo(
            "Debug map export requires the optional debug dependencies: "
            f"pip install 'magic-geo[debug]' ({exc})",
            err=True,
        )
        raise typer.Exit(2) from exc
    try:
        result = export_map_reference(
            debug_dir,
            layer_id=layer,
            output=output,
            projection=projection,
            width=width,
            height=height,
            stage=stage,
            month=month - 1,
            center_lat=center_lat,
            center_lon=center_lon,
            camera_distance=camera_distance,
            camera_position=camera_position,
            camera_target=camera_target,
            camera_up=camera_up,
            vertical_fov=vertical_fov,
            cache_identity=cache_identity,
            wireframe=wireframe,
            plates=plates,
            graticule=graticule,
            write_image=image,
            write_prompt=prompt,
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"Unable to export debug map: {exc}", err=True)
        raise typer.Exit(2) from exc
    artifacts = [str(path) for path in (result.image_path, result.prompt_path) if path is not None]
    typer.echo(
        f"Wrote {', '.join(artifacts)} | layer={result.layer_id} "
        f"projection={result.projection} stage={result.stage} month={result.month + 1}"
    )


@app.command("export-debug")
def export_debug(
    world: Annotated[Path, typer.Option("--world", "-w", exists=True, help="Generated .json or .mgeo world.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Debug cache directory (default: <world dir>/debug)."),
    ] = None,
    vtu: Annotated[
        bool,
        typer.Option("--vtu/--no-vtu", help="Also emit ParaView .vtu stage files and world.pvd."),
    ] = True,
    elevation_exaggeration: Annotated[
        float,
        typer.Option("--elevation-exaggeration", min=1.0, help="Radial elevation exaggeration for .vtu geometry."),
    ] = 30.0,
) -> None:
    """Export a columnar debug cache (Parquet/JSONL/mesh/VTU) for the web workbench."""
    try:
        from ...debug_export import export_debug_cache
    except ImportError as exc:
        typer.echo(f"Debug export requires the optional debug dependencies: pip install 'magic-geo[debug]' ({exc})", err=True)
        raise typer.Exit(2) from exc
    payload = _load_world_for_cli(world)
    out_dir = output if output is not None else world.parent / "debug"
    try:
        manifest = export_debug_cache(
            payload,
            out_dir,
            source_path=world,
            include_vtu=vtu,
            elevation_exaggeration=elevation_exaggeration,
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    mesh = manifest.get("mesh", {})
    typer.echo(
        f"Wrote {out_dir} | layers={len(manifest.get('layers', []))} "
        f"stage_histories={len(manifest.get('stage_histories', {}))} "
        f"families={len(manifest.get('families', {}))} "
        f"mesh_vertices={mesh.get('vertex_count', 0)} mesh_triangles={mesh.get('triangle_count', 0)}"
    )


@app.command("export-rerun")
def export_rerun(
    world: Annotated[Path, typer.Option("--world", "-w", exists=True, help="Generated .json or .mgeo world.")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Rerun recording path (default: <world dir>/world.rrd)."),
    ] = None,
) -> None:
    """Export a Rerun (.rrd) recording with stage-scrubbable mesh and feedback ledgers."""
    try:
        from ...debug_rerun import export_rerun_recording
    except ImportError as exc:
        typer.echo(f"Rerun export requires the rerun-sdk package: pip install rerun-sdk ({exc})", err=True)
        raise typer.Exit(2) from exc
    payload = _load_world_for_cli(world)
    target = output if output is not None else world.parent / "world.rrd"
    try:
        stats = export_rerun_recording(payload, target)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(
        f"Wrote {target} | stages={stats['stages']} vertices={stats['vertices']} "
        f"feedback_scalars={stats['feedback_scalars']} plate_segments={stats['plate_boundary_segments']}"
    )
