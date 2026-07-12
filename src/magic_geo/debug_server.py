"""FastAPI + DuckDB server for the local magic-geo web workbench.

The server can start without an exported debug cache.  Configuration helpers,
backend diagnostics, operation metadata, and background jobs remain available;
map/data endpoints become available as soon as a cache is selected or created.

Debug-cache reads are confined to the selected directory.  Browser-triggered
jobs accept only the fixed schemas in :mod:`magic_geo.web_jobs`, read inputs
from the current project, and write artifacts below the configured workspace.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import struct
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Literal

import duckdb
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .config import (
    ConfigError,
    apply_config_overrides,
    config_schema,
    create_config,
    dump_config_yaml,
    parse_config_yaml,
    write_config,
)
from .debug_export import FORMAT_NAME, FORMAT_VERSION
from .web_jobs import JobInputError, JobManager, WebJob, operation_catalog

_NAN = float("nan")
_MAX_CONFIG_BYTES = 1_000_000
_CONFIG_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
CacheFingerprint = tuple[int, int, int, int]


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _quote_identifier(value: str) -> str:
    """Quote a DuckDB identifier sourced from a cache manifest."""

    if "\x00" in value:
        raise HTTPException(status_code=400, detail="invalid NUL in field name")
    return '"' + value.replace('"', '""') + '"'


def _json_safe(value: Any) -> Any:
    """Replace non-standard JSON numbers recursively with ``null``.

    Parquet legitimately preserves NaN/Infinity for scientific diagnostics,
    but Starlette's strict JSON renderer rejects those values. Binary layer
    responses keep their existing Float32/Arrow semantics; JSON views expose a
    portable null for each non-finite number.
    """

    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


class _StrictJSONResponse(JSONResponse):
    """Default app response that guarantees RFC-compatible JSON numbers."""

    def render(self, content: Any) -> bytes:
        return super().render(_json_safe(content))


class _DebugCache:
    """Thread-safe query layer over one exported debug cache directory."""

    def __init__(self, debug_dir: Path) -> None:
        self.dir = Path(debug_dir).resolve()
        try:
            manifest_path = (self.dir / "manifest.json").resolve()
            sections_path = (self.dir / "sections.json").resolve()
        except (OSError, RuntimeError) as exc:
            raise ValueError(f"invalid debug cache {self.dir}: metadata path resolution failed") from exc
        for path, context in (
            (manifest_path, "manifest"),
            (sections_path, "sections"),
        ):
            if not _is_relative_to(path, self.dir) or not path.is_file():
                raise ValueError(
                    f"invalid debug cache {self.dir}: {context} file must stay inside the cache"
                )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            sections = json.loads(sections_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"invalid debug cache {self.dir}: {exc}") from exc
        if not isinstance(manifest, dict) or not isinstance(sections, dict):
            raise ValueError(f"invalid debug cache {self.dir}: manifest and sections must be objects")
        version = manifest.get("version")
        if (
            manifest.get("format") != FORMAT_NAME
            or type(version) is not int
            or version != FORMAT_VERSION
        ):
            raise ValueError(
                f"unsupported debug cache {self.dir}: expected {FORMAT_NAME!r} "
                f"version {FORMAT_VERSION}, got {manifest.get('format')!r} "
                f"version {manifest.get('version')!r}"
            )
        try:
            cell_count = int(manifest["world"]["cell_count"])
            raw_layers = manifest["layers"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid debug cache {self.dir}: missing world/layer metadata") from exc
        if cell_count < 1 or not isinstance(raw_layers, list):
            raise ValueError(f"invalid debug cache {self.dir}: invalid cell/layer metadata")

        self.manifest: dict[str, Any] = manifest
        self.sections: dict[str, Any] = sections
        self.cell_count = cell_count
        self.layers: dict[str, dict[str, Any]] = {
            str(layer["id"]): layer
            for layer in raw_layers
            if isinstance(layer, dict) and isinstance(layer.get("id"), str)
        }
        if len(self.layers) != len(raw_layers):
            raise ValueError(f"invalid debug cache {self.dir}: duplicate or malformed layer ids")
        self._validate_manifest_files()
        try:
            self._con = duckdb.connect()
        except Exception as exc:
            raise ValueError(f"unable to open DuckDB for debug cache {self.dir}: {exc}") from exc
        self._lock = threading.RLock()
        self._cell_detail_offsets: dict[str, int] | None = None

    def _required_file(self, relative: Any, context: str) -> Path:
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"invalid debug cache {self.dir}: {context} path is missing")
        candidate = Path(relative)
        if candidate.is_absolute():
            raise ValueError(f"invalid debug cache {self.dir}: {context} path must be relative")
        try:
            path = (self.dir / candidate).resolve()
        except (OSError, RuntimeError) as exc:
            raise ValueError(
                f"invalid debug cache {self.dir}: unable to resolve {context} path"
            ) from exc
        if not _is_relative_to(path, self.dir):
            raise ValueError(f"invalid debug cache {self.dir}: {context} path escapes root")
        if not path.is_file():
            raise ValueError(f"invalid debug cache {self.dir}: missing {context} file {relative}")
        return path

    def _validate_manifest_files(self) -> None:
        """Validate every cache file referenced by the v1 manifest."""

        cells = self.manifest.get("cells")
        if not isinstance(cells, dict):
            raise ValueError(f"invalid debug cache {self.dir}: missing cells metadata")
        self._required_file(cells.get("parquet"), "cells parquet")
        for key in ("details_jsonl", "details_index"):
            if key in cells:
                self._required_file(cells[key], f"cells {key}")

        monthly = self.manifest.get("monthly")
        if monthly is not None:
            if not isinstance(monthly, dict):
                raise ValueError(f"invalid debug cache {self.dir}: malformed monthly metadata")
            self._required_file(monthly.get("parquet"), "monthly parquet")

        histories = self.manifest.get("stage_histories", {})
        if not isinstance(histories, dict):
            raise ValueError(f"invalid debug cache {self.dir}: malformed stage histories")
        for name, history in histories.items():
            if not isinstance(history, dict):
                raise ValueError(f"invalid debug cache {self.dir}: malformed history {name}")
            self._required_file(history.get("stage_cells_parquet"), f"{name} stage cells")
            self._required_file(history.get("stages_parquet"), f"{name} stage summary")
            if "extras_jsonl" in history:
                self._required_file(history["extras_jsonl"], f"{name} stage extras")

        families = self.manifest.get("families", {})
        if not isinstance(families, dict):
            raise ValueError(f"invalid debug cache {self.dir}: malformed families")
        for name, family in families.items():
            if not isinstance(family, dict):
                raise ValueError(f"invalid debug cache {self.dir}: malformed family {name}")
            present = False
            for key in ("parquet", "scalars_parquet", "jsonl"):
                if key in family:
                    self._required_file(family[key], f"{name} {key}")
                    present = True
            if not present:
                raise ValueError(f"invalid debug cache {self.dir}: family {name} has no data file")

        section_names = self.manifest.get("sections", [])
        if not isinstance(section_names, list) or not all(
            isinstance(name, str) and name in self.sections for name in section_names
        ):
            raise ValueError(f"invalid debug cache {self.dir}: malformed section catalog")

        mesh = self.manifest.get("mesh")
        if not isinstance(mesh, dict) or not isinstance(mesh.get("buffers"), dict):
            raise ValueError(f"invalid debug cache {self.dir}: missing mesh buffer catalog")
        buffers = mesh["buffers"]
        for name in ("positions", "cell_ids", "indices", "pos_equirect", "pos_mollweide"):
            descriptor = buffers.get(name)
            if not isinstance(descriptor, dict):
                raise ValueError(f"invalid debug cache {self.dir}: missing mesh buffer {name}")
            self._required_file(descriptor.get("file"), f"mesh {name}")

        paraview = self.manifest.get("paraview")
        if paraview is not None:
            if not isinstance(paraview, dict):
                raise ValueError(f"invalid debug cache {self.dir}: malformed ParaView metadata")
            self._required_file(paraview.get("pvd"), "ParaView collection")

    def close(self) -> None:
        with self._lock:
            self._con.close()

    def _data_path(self, relative: str, *, require_file: bool = True) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute():
            raise HTTPException(status_code=400, detail="cache paths must be relative")
        path = (self.dir / candidate).resolve()
        if not _is_relative_to(path, self.dir):
            raise HTTPException(status_code=400, detail=f"cache path escapes root: {relative}")
        if require_file and not path.is_file():
            raise HTTPException(status_code=404, detail=f"missing cache file {relative}")
        return path

    def _table_path(self, relative: str) -> str:
        return str(self._data_path(relative))

    def mesh_path(self, relative: str) -> Path:
        candidate = Path(relative)
        if candidate.is_absolute():
            raise HTTPException(status_code=400, detail="mesh paths must be relative")
        mesh_root = (self.dir / "mesh").resolve()
        if not _is_relative_to(mesh_root, self.dir):
            raise HTTPException(status_code=400, detail="mesh directory escapes cache root")
        path = (mesh_root / candidate).resolve()
        if not _is_relative_to(path, mesh_root):
            raise HTTPException(status_code=400, detail=f"mesh path escapes mesh root: {relative}")
        if not path.is_file():
            raise HTTPException(status_code=404, detail=f"missing mesh asset {relative}")
        return path

    def query(self, sql: str, params: list[Any] | None = None) -> tuple[list[str], list[tuple]]:
        with self._lock:
            result = self._con.execute(sql, params or [])
            columns = [entry[0] for entry in result.description]
            return columns, result.fetchall()

    # -- layers ------------------------------------------------------------

    def layer_values(self, layer_id: str, stage: int | None, month: int | None) -> list[float]:
        layer = self.layers.get(layer_id)
        if layer is None:
            raise HTTPException(status_code=404, detail=f"unknown layer {layer_id}")
        source = str(layer["source"])
        name = str(layer["name"])
        quoted_name = _quote_identifier(name)
        values = [_NAN] * self.cell_count

        if layer["kind"] == "numeric_monthly":
            month_index = 0 if month is None else month
            if not 0 <= month_index < int(layer.get("month_count", 12)):
                raise HTTPException(status_code=400, detail=f"month {month_index} out of range")
            monthly = self.manifest.get("monthly")
            if not isinstance(monthly, dict):
                raise HTTPException(status_code=404, detail="monthly table is unavailable")
            table = self._table_path(monthly["parquet"])
            _, rows = self.query(
                f"SELECT cell_id, {quoted_name} FROM read_parquet(?) WHERE month = ?",
                [table, month_index],
            )
        elif str(layer["kind"]).endswith("_stage"):
            histories = self.manifest.get("stage_histories", {})
            history = histories.get(source) if isinstance(histories, dict) else None
            if not isinstance(history, dict):
                raise HTTPException(status_code=404, detail=f"missing stage history {source}")
            stage_index = 0 if stage is None else stage
            if not 0 <= stage_index < int(history["stage_count"]):
                raise HTTPException(status_code=400, detail=f"stage {stage_index} out of range")
            table = self._table_path(history["stage_cells_parquet"])
            _, rows = self.query(
                f"SELECT cell_id, {quoted_name} FROM read_parquet(?) WHERE stage_idx = ?",
                [table, stage_index],
            )
        else:
            cells = self.manifest.get("cells")
            if not isinstance(cells, dict):
                raise HTTPException(status_code=404, detail="cells table is unavailable")
            table = self._table_path(cells["parquet"])
            _, rows = self.query(f"SELECT id, {quoted_name} FROM read_parquet(?)", [table])

        if str(layer["kind"]).startswith("categorical"):
            code_of = {
                str(category): index for index, category in enumerate(layer.get("categories", []))
            }
            for cell_id, value in rows:
                if 0 <= int(cell_id) < self.cell_count and value is not None:
                    values[int(cell_id)] = float(code_of.get(str(value), -1))
        else:
            for cell_id, value in rows:
                cell_index = int(cell_id)
                if 0 <= cell_index < self.cell_count and value is not None:
                    number = float(value)
                    values[cell_index] = number if math.isfinite(number) else _NAN
        return values

    # -- drill-down --------------------------------------------------------

    def _cell_details(self, cell_id: int) -> dict[str, Any]:
        cells = self.manifest.get("cells", {})
        details_relative = cells.get("details_jsonl") if isinstance(cells, dict) else None
        index_relative = cells.get("details_index") if isinstance(cells, dict) else None
        if not details_relative or not index_relative:
            return {}
        with self._lock:
            if self._cell_detail_offsets is None:
                payload = json.loads(self._data_path(index_relative).read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    raise HTTPException(status_code=500, detail="invalid cell details index")
                self._cell_detail_offsets = {str(key): int(value) for key, value in payload.items()}
            offset = self._cell_detail_offsets.get(str(cell_id))
            if offset is None:
                return {}
            with self._data_path(details_relative).open("rb") as handle:
                handle.seek(offset)
                line = handle.readline()
        try:
            details = json.loads(line)
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=500, detail="invalid cell details record") from exc
        return details if isinstance(details, dict) else {}

    def cell_record(self, cell_id: int) -> dict[str, Any]:
        if not 0 <= cell_id < self.cell_count:
            raise HTTPException(status_code=404, detail=f"cell {cell_id} out of range")
        cells_table = self._table_path(self.manifest["cells"]["parquet"])
        columns, rows = self.query("SELECT * FROM read_parquet(?) WHERE id = ?", [cells_table, cell_id])
        if not rows:
            raise HTTPException(status_code=404, detail=f"cell {cell_id} not found")
        record = dict(zip(columns, rows[0]))
        record.update(self._cell_details(cell_id))

        ledgers: dict[str, Any] = {}
        for history_name, history in self.manifest.get("stage_histories", {}).items():
            table = self._table_path(history["stage_cells_parquet"])
            history_columns, history_rows = self.query(
                "SELECT * FROM read_parquet(?) WHERE cell_id = ? ORDER BY stage_idx",
                [table, cell_id],
            )
            if history_rows:
                stage_column = history_columns.index("stage_idx")
                ledgers[history_name] = {
                    "stage_idx": [row[stage_column] for row in history_rows],
                    "fields": {
                        column: [row[index] for row in history_rows]
                        for index, column in enumerate(history_columns)
                        if column not in ("stage_idx", "cell_id")
                    },
                }

        edges: list[dict[str, Any]] = []
        adjacency = self.manifest.get("families", {}).get("cell_adjacency_edges")
        if isinstance(adjacency, dict) and "parquet" in adjacency:
            table = self._table_path(adjacency["parquet"])
            edge_columns, edge_rows = self.query(
                "SELECT * FROM read_parquet(?) WHERE cell_a_id = ? OR cell_b_id = ?",
                [table, cell_id, cell_id],
            )
            edges = [dict(zip(edge_columns, row)) for row in edge_rows]

        monthly: dict[str, list[Any]] = {}
        monthly_manifest = self.manifest.get("monthly")
        if isinstance(monthly_manifest, dict):
            table = self._table_path(monthly_manifest["parquet"])
            month_columns, month_rows = self.query(
                "SELECT * FROM read_parquet(?) WHERE cell_id = ? ORDER BY month",
                [table, cell_id],
            )
            for index, column in enumerate(month_columns):
                if column not in ("cell_id", "month"):
                    monthly[column] = [row[index] for row in month_rows]

        return {
            "cell": record,
            "ledgers": ledgers,
            "adjacency_edges": edges,
            "monthly": monthly,
            "complete": bool(self.manifest.get("cells", {}).get("details_jsonl")),
        }

    # -- generic exported records ----------------------------------------

    def stage_summary(self, history_name: str) -> dict[str, Any]:
        history = self.manifest.get("stage_histories", {}).get(history_name)
        if not isinstance(history, dict):
            raise HTTPException(status_code=404, detail=f"unknown stage history {history_name}")
        table = self._table_path(history["stages_parquet"])
        columns, rows = self.query("SELECT * FROM read_parquet(?) ORDER BY stage_idx", [table])
        result = {
            "name": history_name,
            "stage_count": history["stage_count"],
            "columns": columns,
            "rows": [list(row) for row in rows],
        }
        extras = history.get("extras_jsonl")
        if isinstance(extras, str):
            result["extras"] = self._jsonl_rows(
                extras,
                max(1, int(history["stage_count"])),
                0,
            )
        return result

    def _jsonl_rows(self, relative: str, limit: int, offset: int) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        path = self._data_path(relative)
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index < offset:
                    continue
                if len(records) >= limit:
                    break
                value = json.loads(line)
                records.append(value if isinstance(value, dict) else {"value": value})
        return records

    def family_rows(
        self, family_name: str, limit: int, offset: int, detail: Literal["full", "scalars"]
    ) -> dict[str, Any]:
        family = self.manifest.get("families", {}).get(family_name)
        if not isinstance(family, dict):
            raise HTTPException(status_code=404, detail=f"unknown family {family_name}")

        source = "full"
        if detail == "full" and "jsonl" in family:
            records = self._jsonl_rows(family["jsonl"], limit, offset)
        elif "parquet" in family or "scalars_parquet" in family:
            source = "scalars" if "scalars_parquet" in family else "full"
            table = self._table_path(family.get("parquet") or family["scalars_parquet"])
            columns, rows = self.query(
                "SELECT * FROM read_parquet(?) LIMIT ? OFFSET ?", [table, limit, offset]
            )
            records = [dict(zip(columns, row)) for row in rows]
        elif "jsonl" in family:
            records = self._jsonl_rows(family["jsonl"], limit, offset)
        else:
            raise HTTPException(status_code=404, detail=f"family {family_name} has no readable data")

        total = int(family.get("row_count", len(records)))
        return {
            "name": family_name,
            "total": total,
            "offset": offset,
            "limit": limit,
            "next_offset": offset + len(records) if offset + len(records) < total else None,
            "detail": source,
            "rows": records,
        }

    def plate_boundary_segments(self) -> list[list[float]]:
        adjacency = self.manifest.get("families", {}).get("cell_adjacency_edges")
        if not isinstance(adjacency, dict) or "parquet" not in adjacency:
            return []
        table = self._table_path(adjacency["parquet"])
        _, rows = self.query(
            "SELECT boundary_segment_start_lat_deg, boundary_segment_start_lon_deg, "
            "boundary_segment_end_lat_deg, boundary_segment_end_lon_deg "
            "FROM read_parquet(?) WHERE plate_boundary",
            [table],
        )
        return [
            [float(a), float(b), float(c), float(d)]
            for a, b, c, d in rows
            if a is not None and b is not None and c is not None and d is not None
        ]


class _CacheManager:
    """Reloadable cache selection used by cacheless startup and completed jobs."""

    def __init__(self, project_root: Path, workspace: Path, selected: Path | None) -> None:
        self.project_root = Path(project_root).resolve()
        workspace_path = Path(workspace)
        if not workspace_path.is_absolute():
            workspace_path = self.project_root / workspace_path
        self.workspace = workspace_path.resolve()
        if not _is_relative_to(self.workspace, self.project_root):
            raise ValueError("web workspace must be inside the project directory")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self._selected = self._resolve_selected(selected) if selected is not None else None
        self._cache: _DebugCache | None = None
        self._fingerprint: CacheFingerprint | None = None
        self._error: str | None = None
        self._lock = threading.RLock()
        if self._selected is not None:
            self.select(self._selected)
        else:
            self._discover_default()

    def _resolve_selected(self, selected: Path) -> Path:
        path = Path(selected)
        if not path.is_absolute():
            path = self.project_root / path
        return path.resolve()

    def _discover_default(self) -> None:
        if self._selected is not None:
            return
        direct = self.workspace / "debug" / "manifest.json"
        if direct.is_file() and _is_relative_to(direct.parent.resolve(), self.workspace):
            self._selected = direct.parent.resolve()
            return
        candidates: list[tuple[int, str, Path]] = []
        for path in self.workspace.glob("**/debug/manifest.json"):
            try:
                resolved_parent = path.parent.resolve()
                if not _is_relative_to(resolved_parent, self.workspace):
                    continue
                candidates.append((path.stat().st_mtime_ns, path.as_posix(), resolved_parent))
            except OSError:
                continue
        candidates.sort(reverse=True)
        if candidates:
            self._selected = candidates[0][2]

    def close(self) -> None:
        with self._lock:
            if self._cache is not None:
                self._cache.close()
                self._cache = None

    @staticmethod
    def _manifest_fingerprint(stat: os.stat_result) -> CacheFingerprint:
        # Device/inode distinguish atomic replacements even when generated
        # manifests happen to retain the same byte length and timestamp.
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)

    def _revision_unlocked(self) -> str | None:
        if self._fingerprint is None:
            return None
        return "-".join(f"{value:x}" for value in self._fingerprint)

    def select(self, path: Path) -> None:
        selected = self._resolve_selected(path)
        manifest = selected / "manifest.json"
        if not manifest.is_file():
            raise ValueError(f"no manifest.json in {selected}")
        # Fully validate the replacement before changing any live selection.
        candidate = _DebugCache(selected)
        try:
            stat = manifest.stat()
            fingerprint = self._manifest_fingerprint(stat)
        except OSError:
            candidate.close()
            raise
        with self._lock:
            previous = self._cache
            self._selected = selected
            self._cache = candidate
            self._fingerprint = fingerprint
            self._error = None
            if previous is not None:
                previous.close()

    @staticmethod
    def _remove_path(path: Path) -> None:
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
        except OSError:
            pass

    def publish(self, staging: Path, destination: Path) -> Path:
        """Validate and publish a staged cache while cache readers are paused."""

        staging = Path(staging).resolve()
        destination = Path(destination).resolve()
        if not _is_relative_to(staging, self.workspace) or not _is_relative_to(
            destination, self.workspace
        ):
            raise ValueError("published cache must stay inside the web workspace")
        if destination.exists() and not destination.is_dir():
            raise ValueError(f"cache destination is not a directory: {destination}")

        # Validation happens before the manager lock and before the live path is
        # touched. The candidate connection is reopened after the directory move.
        staged_candidate = _DebugCache(staging)
        staged_candidate.close()
        destination.parent.mkdir(parents=True, exist_ok=True)
        backup = destination.parent / f".{destination.name}.{uuid.uuid4().hex}.backup"
        moved_old = False
        moved_new = False
        published = False
        try:
            with self._lock:
                if destination.exists():
                    os.replace(destination, backup)
                    moved_old = True
                os.replace(staging, destination)
                moved_new = True
                try:
                    candidate = _DebugCache(destination)
                    stat = (destination / "manifest.json").stat()
                except Exception:
                    if moved_new:
                        self._remove_path(destination)
                        moved_new = False
                    if moved_old:
                        os.replace(backup, destination)
                        moved_old = False
                    raise
                previous = self._cache
                self._selected = destination
                self._cache = candidate
                self._fingerprint = self._manifest_fingerprint(stat)
                self._error = None
                if previous is not None:
                    try:
                        previous.close()
                    except Exception:
                        # The replacement is already live and validated. A
                        # cleanup failure must not roll the filesystem back
                        # underneath it.
                        pass
                published = True
        except Exception:
            with self._lock:
                if moved_new and destination.exists():
                    self._remove_path(destination)
                    moved_new = False
                if moved_old and backup.exists() and not destination.exists():
                    os.replace(backup, destination)
                    moved_old = False
            raise
        finally:
            if published and moved_old:
                self._remove_path(backup)
        return destination

    def selected_relative(self) -> str | None:
        with self._lock:
            selected = self._selected
        if selected is None:
            return None
        try:
            return selected.relative_to(self.project_root).as_posix()
        except ValueError:
            return str(selected)

    def get(self, *, required: bool = True) -> _DebugCache | None:
        with self._lock:
            self._discover_default()
            selected = self._selected
            if selected is None:
                if required:
                    raise HTTPException(
                        status_code=409,
                        detail="no debug cache selected; generate a world or run export-debug",
                    )
                return None
            manifest = selected / "manifest.json"
            if not manifest.is_file():
                if self._cache is not None:
                    self._cache.close()
                    self._cache = None
                self._fingerprint = None
                self._error = f"no manifest.json in {selected}"
                if required:
                    raise HTTPException(status_code=409, detail=f"no manifest.json in {selected}")
                return None
            try:
                stat = manifest.stat()
            except OSError as exc:
                self._error = f"unable to stat {manifest}: {exc}"
                if required:
                    raise HTTPException(status_code=409, detail=self._error) from exc
                return None
            fingerprint = self._manifest_fingerprint(stat)
            if self._cache is None or fingerprint != self._fingerprint:
                try:
                    candidate = _DebugCache(selected)
                except ValueError as exc:
                    self._error = str(exc)
                    if self._cache is None and required:
                        raise HTTPException(status_code=500, detail=str(exc)) from exc
                    return self._cache
                previous = self._cache
                self._cache = candidate
                self._fingerprint = fingerprint
                self._error = None
                if previous is not None:
                    previous.close()
            return self._cache

    def with_cache(
        self,
        action: Callable[[_DebugCache], Any],
        expected_revision: str | None = None,
    ) -> Any:
        """Run one read against exactly the revision requested by the client."""

        with self._lock:
            cache = self.get(required=True)
            assert cache is not None
            revision = self._revision_unlocked()
            if expected_revision is not None and expected_revision != revision:
                raise HTTPException(
                    status_code=409,
                    detail="debug cache revision changed; refresh status and retry",
                )
            return action(cache)

    def status(self) -> dict[str, Any]:
        with self._lock:
            cache = self.get(required=False)
            return {
                "cache_available": cache is not None,
                "cache_dir": self.selected_relative(),
                "cache_error": self._error,
                "cache_revision": self._revision_unlocked() if cache is not None else None,
            }

    def available(self) -> list[dict[str, Any]]:
        manifests: set[Path] = set()
        direct = self.workspace / "manifest.json"
        if direct.is_file():
            manifests.add(direct)
        manifests.update(self.workspace.glob("**/manifest.json"))
        worlds: list[dict[str, Any]] = []
        for manifest in sorted(manifests):
            try:
                resolved_manifest = manifest.resolve()
                if not _is_relative_to(resolved_manifest, self.workspace):
                    continue
                resolved_parent = resolved_manifest.parent
                if not _is_relative_to(resolved_parent, self.workspace):
                    continue
                payload = json.loads(resolved_manifest.read_text(encoding="utf-8"))
                if not isinstance(payload, dict):
                    continue
                version = payload.get("version")
                if (
                    payload.get("format") != FORMAT_NAME
                    or type(version) is not int
                    or version != FORMAT_VERSION
                ):
                    continue
                world = payload.get("world", {})
                if not isinstance(world, dict):
                    continue
                relative_workspace = resolved_parent.relative_to(self.workspace)
                if ".magic-geo-web" in relative_workspace.parts or any(
                    part.startswith(".")
                    and (part.endswith(".staging") or part.endswith(".backup"))
                    for part in relative_workspace.parts
                ):
                    continue
                relative = resolved_parent.relative_to(self.project_root).as_posix()
                worlds.append(
                    {
                        "id": relative,
                        "cache_dir": relative,
                        "name": world.get("name"),
                        "cell_count": world.get("cell_count"),
                        "generation_scope": world.get("generation_scope"),
                        "selected": relative == self.selected_relative(),
                    }
                )
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
                continue
        return worlds


def _float32_response(values: list[float]) -> Response:
    return Response(
        content=struct.pack(f"<{len(values)}f", *values),
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )


def _arrow_response(values: list[float]) -> Response:
    import pyarrow as pa
    import pyarrow.ipc as ipc

    table = pa.table(
        {
            "cell_id": pa.array(range(len(values)), type=pa.int32()),
            "value": pa.array(values, type=pa.float32()),
        }
    )
    sink = pa.BufferOutputStream()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return Response(
        content=sink.getvalue().to_pybytes(),
        media_type="application/vnd.apache.arrow.stream",
        headers={"Cache-Control": "no-store"},
    )


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConfigTextRequest(_StrictRequest):
    yaml: str


class ConfigRenderRequest(_StrictRequest):
    profile: str = "earthlike"
    overrides: dict[str, Any] = Field(default_factory=dict)


class ConfigSaveRequest(ConfigTextRequest):
    name: str = Field(default="web-config.yaml", min_length=1, max_length=128)
    force: bool = False


class JobRequest(_StrictRequest):
    operation: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class CacheSelectRequest(_StrictRequest):
    cache_dir: str


def _config_error(exc: ConfigError) -> HTTPException:
    return HTTPException(status_code=422, detail=exc.to_dict())


def _check_web_yaml_size(text: str) -> None:
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        error = ConfigError(
            "YAML text must be well-formed UTF-8 Unicode",
            source="<web editor>",
        )
        raise _config_error(error) from exc
    if size > _MAX_CONFIG_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"YAML exceeds the {_MAX_CONFIG_BYTES}-byte request limit ({size} bytes)",
        )


def create_app(
    debug_dir: Path | None = None,
    *,
    workspace: Path = Path("runs"),
    project_root: Path | None = None,
) -> FastAPI:
    """Create the web workbench, with or without an existing debug cache."""

    root = Path.cwd().resolve() if project_root is None else Path(project_root).resolve()
    caches = _CacheManager(root, workspace, debug_dir)

    def on_job_complete(job: WebJob) -> None:
        if job.status == "succeeded" and job.cache_dir:
            try:
                if caches.selected_relative() != job.cache_dir:
                    caches.select(root / job.cache_dir)
            except ValueError:
                pass

    jobs = JobManager(
        root,
        workspace,
        on_complete=on_job_complete,
        publish_cache=caches.publish,
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            jobs.close()
            caches.close()

    app = FastAPI(
        title="magic-geo web workbench API",
        description="Configuration, generation, validation, export, and complete debug-cache access.",
        version="1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
        default_response_class=_StrictJSONResponse,
    )
    # Explicit state handles make lifecycle and embedding testable without
    # relying on closure introspection.
    app.state.cache_manager = caches
    app.state.job_manager = jobs

    # -- always-available workbench APIs ---------------------------------

    @app.get("/api/status", tags=["workbench"])
    def status() -> dict[str, Any]:
        from . import __version__

        return {
            **caches.status(),
            "workspace": jobs.workspace.relative_to(root).as_posix(),
            "project": root.name,
            "version": __version__,
            "api_docs": "/api/docs",
        }

    @app.get("/api/operations", tags=["operations"])
    def operations() -> dict[str, Any]:
        return operation_catalog(root, jobs.workspace)

    @app.get("/api/backend", tags=["operations"])
    def backend() -> dict[str, Any]:
        try:
            from .api import backend_info

            return backend_info()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"backend probe failed: {exc}") from exc

    @app.get("/api/config/schema", tags=["configuration"])
    def get_config_schema() -> dict[str, Any]:
        return config_schema()

    @app.get("/api/config/profiles", tags=["configuration"])
    def get_config_profiles() -> dict[str, Any]:
        metadata = config_schema()["x-magic-geo"]["profiles"]
        return {
            "profiles": [
                {"name": item["name"], "description": item["description"]}
                for item in metadata
            ],
            "default": "earthlike",
        }

    @app.get("/api/config/template", tags=["configuration"])
    def get_config_template(profile: str = Query(default="earthlike")) -> dict[str, Any]:
        try:
            config = create_config(profile)
        except ConfigError as exc:
            raise _config_error(exc) from exc
        return {
            "profile": profile,
            "yaml": dump_config_yaml(config),
            "config": config.model_dump(mode="json"),
        }

    @app.post("/api/config/render", tags=["configuration"])
    def render_config(request: ConfigRenderRequest) -> dict[str, Any]:
        try:
            config = create_config(request.profile)
            if request.overrides:
                config = apply_config_overrides(config, request.overrides, source="<web overrides>")
        except ConfigError as exc:
            raise _config_error(exc) from exc
        return {
            "profile": request.profile,
            "yaml": dump_config_yaml(config),
            "config": config.model_dump(mode="json"),
        }

    @app.post("/api/config/validate", tags=["configuration"])
    def validate_config(request: ConfigTextRequest) -> dict[str, Any]:
        _check_web_yaml_size(request.yaml)
        try:
            config = parse_config_yaml(request.yaml, source="<web editor>")
        except ConfigError as exc:
            raise _config_error(exc) from exc
        return {
            "valid": True,
            "yaml": dump_config_yaml(config),
            "config": config.model_dump(mode="json"),
        }

    @app.post("/api/config/save", tags=["configuration"])
    def save_config(request: ConfigSaveRequest) -> dict[str, Any]:
        _check_web_yaml_size(request.yaml)
        if not _CONFIG_NAME.fullmatch(request.name) or request.name in {".", ".."}:
            raise HTTPException(
                status_code=422,
                detail="name must use only letters, digits, '.', '_', and '-'",
            )
        name = request.name if request.name.endswith((".yaml", ".yml")) else request.name + ".yaml"
        try:
            config = parse_config_yaml(request.yaml, source=f"<web:{name}>")
        except ConfigError as exc:
            raise _config_error(exc) from exc
        target_dir = jobs.workspace / "configs"
        if target_dir.is_symlink():
            raise HTTPException(
                status_code=422,
                detail="workspace config directory must not be a symbolic link",
            )
        target_dir.mkdir(parents=True, exist_ok=True)
        resolved_target_dir = target_dir.resolve()
        if not _is_relative_to(resolved_target_dir, jobs.workspace.resolve()):
            raise HTTPException(status_code=422, detail="config directory escapes workspace")
        requested_target = target_dir / name
        if requested_target.is_symlink():
            raise HTTPException(
                status_code=422,
                detail="configuration target must not be a symbolic link",
            )
        target = requested_target.resolve()
        if not _is_relative_to(target, resolved_target_dir):
            raise HTTPException(status_code=422, detail="invalid configuration name")
        if target.exists() and not request.force:
            raise HTTPException(
                status_code=409,
                detail=f"configuration already exists: {name}; confirm overwrite to replace it",
            )
        try:
            write_config(target, config, force=request.force)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"unable to save configuration: {exc}") from exc
        return {
            "saved": True,
            "path": target.relative_to(root).as_posix(),
            "yaml": dump_config_yaml(config),
        }

    @app.get("/api/jobs", tags=["jobs"])
    def list_jobs() -> dict[str, Any]:
        return {"jobs": jobs.list()}

    @app.post("/api/jobs", status_code=202, tags=["jobs"])
    def create_job(request: JobRequest) -> dict[str, Any]:
        try:
            return jobs.submit(request.operation, request.arguments)
        except JobInputError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/api/jobs/{job_id}", tags=["jobs"])
    def get_job(job_id: str) -> dict[str, Any]:
        try:
            return jobs.get(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown job {job_id}") from exc

    @app.post("/api/jobs/{job_id}/cancel", tags=["jobs"])
    def cancel_job(job_id: str) -> dict[str, Any]:
        try:
            return jobs.cancel(job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown job {job_id}") from exc

    @app.get("/api/jobs/{job_id}/artifacts/{artifact_index}", tags=["jobs"])
    def download_artifact(job_id: str, artifact_index: int) -> FileResponse:
        try:
            path = jobs.artifact_path(job_id, artifact_index)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="unknown artifact") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="artifact is not available") from exc
        return FileResponse(path, filename=path.name)

    @app.get("/api/worlds", tags=["workbench"])
    def worlds() -> dict[str, Any]:
        return {"worlds": caches.available()}

    @app.post("/api/worlds/select", tags=["workbench"])
    def select_world(request: CacheSelectRequest) -> dict[str, Any]:
        path = Path(request.cache_dir)
        if not path.is_absolute():
            path = root / path
        try:
            resolved = path.resolve()
        except (OSError, RuntimeError) as exc:
            raise HTTPException(status_code=422, detail=f"unable to resolve cache path: {exc}") from exc
        if not _is_relative_to(resolved, jobs.workspace):
            raise HTTPException(status_code=422, detail="cache must be inside the web workspace")
        try:
            caches.select(resolved)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return caches.status()

    # -- cache-backed read APIs ------------------------------------------

    @app.get("/api/manifest", tags=["data"])
    def manifest(revision: str | None = None) -> dict[str, Any]:
        return caches.with_cache(lambda cache: cache.manifest, revision)

    @app.get("/api/catalog", tags=["data"])
    def catalog(revision: str | None = None) -> dict[str, Any]:
        def build_catalog(cache: _DebugCache) -> dict[str, Any]:
            manifest_payload = cache.manifest
            return {
                "world": manifest_payload.get("world", {}),
                "scalars": manifest_payload.get("scalars", {}),
                "layers": manifest_payload.get("layers", []),
                "stage_histories": manifest_payload.get("stage_histories", {}),
                "families": manifest_payload.get("families", {}),
                "sections": manifest_payload.get("sections", []),
                "skipped_sections": manifest_payload.get("skipped_sections", {}),
                "cells": manifest_payload.get("cells", {}),
                "monthly": manifest_payload.get("monthly"),
                "mesh": manifest_payload.get("mesh", {}),
            }

        return caches.with_cache(build_catalog, revision)

    @app.get("/api/layer/{layer_id:path}", tags=["data"])
    def layer(
        layer_id: str,
        stage: int | None = Query(default=None, ge=0),
        month: int | None = Query(default=None, ge=0, le=11),
        format: Literal["f32", "arrow"] = Query(default="f32"),
        revision: str | None = None,
    ) -> Response:
        values = caches.with_cache(
            lambda cache: cache.layer_values(layer_id, stage, month),
            revision,
        )
        return _arrow_response(values) if format == "arrow" else _float32_response(values)

    @app.get("/api/cell/{cell_id}", tags=["data"])
    def cell(cell_id: int, revision: str | None = None) -> dict[str, Any]:
        return caches.with_cache(lambda cache: cache.cell_record(cell_id), revision)

    @app.get("/api/stage-summary/{history_name:path}", tags=["data"])
    def stage_summary(
        history_name: str, revision: str | None = None
    ) -> dict[str, Any]:
        return caches.with_cache(
            lambda cache: cache.stage_summary(history_name), revision
        )

    @app.get("/api/family/{family_name:path}", tags=["data"])
    def family(
        family_name: str,
        limit: int = Query(default=100, ge=1, le=5000),
        offset: int = Query(default=0, ge=0, le=2**63 - 1),
        detail: Literal["full", "scalars"] = Query(default="full"),
        revision: str | None = None,
    ) -> dict[str, Any]:
        return caches.with_cache(
            lambda cache: cache.family_rows(family_name, limit, offset, detail),
            revision,
        )

    @app.get("/api/section/{section_name:path}", tags=["data"])
    def section(section_name: str, revision: str | None = None) -> Any:
        def read_section(cache: _DebugCache) -> Any:
            if section_name not in cache.sections:
                raise HTTPException(status_code=404, detail=f"unknown section {section_name}")
            return cache.sections[section_name]

        return caches.with_cache(read_section, revision)

    @app.get("/api/plate-boundaries", tags=["data"])
    def plate_boundaries(revision: str | None = None) -> list[list[float]]:
        return caches.with_cache(
            lambda cache: cache.plate_boundary_segments(), revision
        )

    @app.get("/mesh/{asset_path:path}", include_in_schema=False)
    def mesh_asset(asset_path: str, revision: str | None = None) -> Response:
        # A cache may be atomically replaced at the same directory. Stable mesh
        # URLs must therefore be materialized while the cache-manager read lock
        # is held, rather than streamed from a path that can later be replaced.
        content = caches.with_cache(
            lambda cache: cache.mesh_path(asset_path).read_bytes(), revision
        )
        return Response(
            content=content,
            media_type="application/octet-stream",
            headers={"Cache-Control": "no-store"},
        )

    # StaticFiles must be last so /api and /mesh routes win.
    ui_dir = Path(__file__).parent / "debug_ui"
    app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")
    return app
