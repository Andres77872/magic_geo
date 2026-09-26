"""Typer path defaults: explicit options win over runtime storage settings."""

from pathlib import Path

import typer

from ..config_store import ConfigStore
from ..paths import RuntimePaths


def _runtime_default(ctx: typer.Context, param: typer.CallbackParam, value: Path | None):
    if getattr(ctx.get_parameter_source(param.name), "name", None) != "DEFAULT":
        return value
    paths = RuntimePaths.resolve()
    command = ctx.info_name
    if param.name == "config":
        return ConfigStore(paths).default() or paths.project / "magic-geo.yaml"
    if param.name == "debug_dir":
        return paths.debug_dir if command != "serve" else value
    if command == "init-config" and param.name == "output":
        return paths.config_path or paths.project / "magic-geo.yaml"
    if value is None:
        # Preserve world-relative export defaults unless storage was configured.
        import os
        if command == "export-debug" and param.name == "output" and any(
            os.environ.get(key, "").strip() for key in ("MAGIC_GEO_DEBUG_DIR", "MAGIC_GEO_OUTPUT_DIR", "MAGIC_GEO_WORKSPACE")
        ):
            return paths.debug_dir
        if command == "export-rerun" and param.name == "output" and any(
            os.environ.get(key, "").strip() for key in ("MAGIC_GEO_EXPORTS_DIR", "MAGIC_GEO_OUTPUT_DIR", "MAGIC_GEO_WORKSPACE")
        ):
            return paths.exports_dir / "world.rrd"
        return None
    category = "report" if command in {"calibrate", "calibrate-ensemble", "validate-geo-suite", "derive-targets"} else (
        "export" if command in {"render", "render-raster", "export-rerun"} else "output"
    )
    resolved = paths.rebase_default(value, category=category)
    # Keep familiar relative CLI messages when invoked from the project root.
    return Path(paths.display(resolved)) if paths.project == Path.cwd().resolve() else resolved


def runtime_path(ctx: typer.Context, param: typer.CallbackParam, value):
    try:
        value = _runtime_default(ctx, param, value)
    except (OSError, ValueError, RuntimeError) as exc:
        raise typer.BadParameter(f"Unable to resolve runtime paths: {exc}") from exc
    if param.name in {"config", "matrix", "sources", "targets", "debug_dir"} and value is not None:
        for path in value if isinstance(value, list) else [value]:
            if not Path(path).exists():
                noun = "Directory" if param.name == "debug_dir" else "Path"
                raise typer.BadParameter(f"{noun} '{path}' does not exist.")
    return value
