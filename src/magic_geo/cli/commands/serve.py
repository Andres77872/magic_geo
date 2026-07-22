"""`serve` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from .._app import app


@app.command("serve")
def serve(
    debug_dir: Annotated[
        Path | None,
        typer.Option(
            "--debug-dir",
            "-d",
            exists=True,
            file_okay=False,
            dir_okay=True,
            help="Optional cache from export-debug; auto-loads <workspace>/debug when present.",
        ),
    ] = None,
    workspace: Annotated[
        Path,
        typer.Option(
            "--workspace",
            envvar="MAGIC_GEO_WORKSPACE",
            help="Directory for browser-created configs, worlds, reports, and exports.",
        ),
    ] = Path("runs"),
    host: Annotated[
        str,
        typer.Option("--host", envvar="MAGIC_GEO_HOST", help="Bind address."),
    ] = "127.0.0.1",
    port: Annotated[
        int,
        typer.Option(
            "--port",
            envvar="MAGIC_GEO_PORT",
            min=1,
            max=65535,
            help="Bind port.",
        ),
    ] = 8642,
) -> None:
    """Serve the browser workbench; an existing debug cache is optional."""
    project_root = Path.cwd().resolve()
    resolved_workspace = (
        workspace.resolve()
        if workspace.is_absolute()
        else (project_root / workspace).resolve()
    )
    try:
        resolved_workspace.relative_to(project_root)
    except ValueError as exc:
        typer.echo(
            f"Web workspace must stay inside {project_root}: {workspace}",
            err=True,
        )
        raise typer.Exit(2) from exc
    default_debug_dir = workspace / "debug"
    selected_debug_dir = (
        debug_dir
        if debug_dir is not None
        else (default_debug_dir if (default_debug_dir / "manifest.json").is_file() else None)
    )
    if debug_dir is not None and not (debug_dir / "manifest.json").is_file():
        typer.echo(
            f"No manifest.json in {debug_dir}; choose an export-debug cache or omit -d.",
            err=True,
        )
        raise typer.Exit(2)
    try:
        import uvicorn

        from ...debug_server import create_app
    except ImportError as exc:
        typer.echo(f"Serving requires the optional debug dependencies: pip install 'magic-geo[debug]' ({exc})", err=True)
        raise typer.Exit(2) from exc
    try:
        web_app = create_app(selected_debug_dir, workspace=workspace)
    except ValueError as exc:
        if debug_dir is None and selected_debug_dir is not None:
            typer.echo(
                f"Ignoring invalid automatic cache {selected_debug_dir}: {exc}",
                err=True,
            )
            selected_debug_dir = None
            try:
                web_app = create_app(None, workspace=workspace)
            except (OSError, ValueError) as fallback_exc:
                typer.echo(f"Unable to start web workbench: {fallback_exc}", err=True)
                raise typer.Exit(2) from fallback_exc
        else:
            typer.echo(f"Unable to start web workbench: {exc}", err=True)
            raise typer.Exit(2) from exc
    except OSError as exc:
        typer.echo(f"Unable to start web workbench: {exc}", err=True)
        raise typer.Exit(2) from exc
    cache_message = (
        f"debug cache {selected_debug_dir}"
        if selected_debug_dir is not None
        else "with automatic workspace cache discovery (Config and Operations remain available)"
    )
    typer.echo(f"Serving web workbench {cache_message} at http://{host}:{port}")
    uvicorn.run(
        web_app,
        host=host,
        port=port,
        log_level="warning",
    )
