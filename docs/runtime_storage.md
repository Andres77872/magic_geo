# Runtime storage and configuration discovery

All locations are resolved once when the workbench starts. CLI defaults use the
same resolver at invocation time. Explicit CLI paths win; then environment
settings; then the repository conventions below. Empty environment values are
ignored. No files are moved automatically.

| Variable | Default | Purpose |
| --- | --- | --- |
| `MAGIC_GEO_PROJECT_ROOT` | Detected project / current directory | Anchor for relative environment paths and browser paths |
| `MAGIC_GEO_WORKSPACE` | `<project>/runs` | Browser workspace and parent for saved configs and internal state |
| `MAGIC_GEO_CONFIG_PATH` | Discovered below | Exact YAML file to open by default and use for default-config operations |
| `MAGIC_GEO_CONFIG_DIR` | `<project>/configs` | Existing world definitions and config/matrix CLI defaults |
| `MAGIC_GEO_SAVED_CONFIG_DIR` | `<workspace>/configs` | New browser configurations and copies |
| `MAGIC_GEO_OUTPUT_DIR` | `<workspace>` | Generated world files |
| `MAGIC_GEO_DEBUG_DIR` | `<output>/debug` | Default browser cache and debug export destination |
| `MAGIC_GEO_REPORTS_DIR` | `<output>` | Default calibration and validation reports |
| `MAGIC_GEO_EXPORTS_DIR` | `<output>` | Default SVG, raster, Rerun and CLI map-reference exports |
| `MAGIC_GEO_STATE_DIR` | `<workspace>/.magic-geo-web` | Internal job artifact snapshots; not a user output destination |
| `MAGIC_GEO_CALIBRATION_DIR` | `<project>/calibration_data` | Allowed calibration input data and manifests |

The existing `MAGIC_GEO_NATIVE_LIBRARY`, `MAGIC_GEO_HOST`, and `MAGIC_GEO_PORT`
settings retain their behavior. Job logs and queue records are held in memory;
relocating state storage does not introduce persistent jobs or logs.

For a checkout, project detection walks upward to the magic-geo `pyproject.toml`
and `src/magic_geo` directory. Outside a checkout, a parent `magic-geo.yaml` can
anchor a project; otherwise the current directory is used. Set
`MAGIC_GEO_PROJECT_ROOT` to make this independent of the launching directory.
Relative explicit CLI filenames continue to resolve against the current directory.

## Default configuration

`MAGIC_GEO_CONFIG_PATH` pins one file, including a file outside the config
directories. A missing or invalid pinned file is reported; it is never silently
replaced by another configuration. Without it, the first valid configuration is
chosen in this order:

1. `<project>/magic-geo.yaml`, then `magic-geo.yml`.
2. `<saved-config-dir>/world.yaml`.
3. `<config-dir>/earthlike_seed.yaml`.
4. Other world YAML files in the saved-config and config directories, in stable
   path order (nested directories included).

Scenario matrices are excluded from the configuration picker. Discovery skips
symlinks, hidden directories and internal files, and bounds the number of
candidates. The browser shows discovered paths and validation problems. If no
world config exists, a built-in profile starts the editor. CLI `generate` asks
for a file instead; `init-config` can create one. `init-config` keeps its
`magic-geo.yaml` default and uses `MAGIC_GEO_CONFIG_PATH` if pinned.

Opening a file retains its exact YAML, including comments. Saving under the
same name updates that source file; changing the name saves a copy in
`MAGIC_GEO_SAVED_CONFIG_DIR`. A revision check detects competing edits before
saving an opened file. Refresh files never replaces unsaved YAML.

## Relocate storage

For bare-metal use, export settings in the shell or service environment:

```bash
export MAGIC_GEO_WORKSPACE="$HOME/.local/share/magic-geo"
export MAGIC_GEO_CONFIG_DIR="$MAGIC_GEO_WORKSPACE/configs"
export MAGIC_GEO_CONFIG_PATH="$MAGIC_GEO_CONFIG_DIR/world.yaml"
magic-geo init-config --profile smoke
magic-geo serve
```

This stores new worlds, configs, caches, reports, exports and job snapshots
outside the checkout. To split locations further, set the individual variables
in the table. Input and output containment applies to the configured roots;
setting an external root permits that root without exposing arbitrary paths.
Generated artifacts remain downloadable when they live outside the project.
Cache publication uses a temporary sibling of its destination, allowing
independent filesystems for cache and state storage.

With no overrides, generation still writes `runs/world.json`; browser config
creation uses `runs/configs`; the browser cache is `runs/debug`. CLI
`export-debug` keeps `<world parent>/debug` and `export-rerun` keeps
`<world parent>/world.rrd` when no relevant storage override is set. Explicit
output flags always win. Browser PNG/Markdown downloads use the browser's
normal download destination.

The workbench first tries the configured debug directory, then valid published
caches under the workspace and output directory, newest first. Cache directories
may have any name. Invalid candidates do not hide healthy caches. Staging,
backup and internal artifact directories are excluded.

Docker Compose reads `.env` automatically; bare-metal Python does not silently
load it. The local development launcher `scripts/dev.sh` explicitly sources
the optional shell-compatible `.env.local`; copy `.env.local.example` to set
local overrides. `.env.example` includes every supported Compose/runtime setting. In
Docker, use container paths inside mounted volumes; see
[Docker deployment](docker_deployment.md) for the host/container distinction.
