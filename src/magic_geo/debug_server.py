"""FastAPI + DuckDB server for the GUI debugger.

Serves a debug cache directory produced by ``debug_export.export_debug_cache``:
layer columns as raw little-endian Float32 buffers (or Arrow IPC on request),
per-cell drill-down records with per-stage ledger slices, per-stage summary
tables for sparklines, dict sections (models, graphs, clocks), and the static
three.js frontend from ``magic_geo/debug_ui``.
"""

from __future__ import annotations

import json
import math
import struct
import threading
from pathlib import Path
from typing import Any

import duckdb
from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles

_NAN = float("nan")


class _DebugCache:
    """Query layer over one exported debug cache directory."""

    def __init__(self, debug_dir: Path) -> None:
        self.dir = debug_dir.resolve()
        self.manifest: dict[str, Any] = json.loads((self.dir / "manifest.json").read_text(encoding="utf-8"))
        self.sections: dict[str, Any] = json.loads((self.dir / "sections.json").read_text(encoding="utf-8"))
        self.cell_count: int = int(self.manifest["world"]["cell_count"])
        self.layers: dict[str, dict[str, Any]] = {layer["id"]: layer for layer in self.manifest["layers"]}
        self._con = duckdb.connect()
        self._lock = threading.Lock()

    def _table_path(self, relative: str) -> str:
        path = (self.dir / relative).resolve()
        if not str(path).startswith(str(self.dir)) or not path.exists():
            raise HTTPException(status_code=404, detail=f"missing table {relative}")
        return str(path)

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
        source, name = layer["source"], layer["name"]
        values = [_NAN] * self.cell_count

        if layer["kind"] == "numeric_monthly":
            month_index = 0 if month is None else max(0, min(11, month))
            table = self._table_path(self.manifest["monthly"]["parquet"])
            _, rows = self.query(
                f'SELECT cell_id, "{name}" FROM read_parquet(?) WHERE month = ?',
                [table, month_index],
            )
        elif layer["kind"] == "numeric_stage":
            history = self.manifest["stage_histories"][source]
            stage_index = 0 if stage is None else max(0, min(history["stage_count"] - 1, stage))
            table = self._table_path(history["stage_cells_parquet"])
            _, rows = self.query(
                f'SELECT cell_id, "{name}" FROM read_parquet(?) WHERE stage_idx = ?',
                [table, stage_index],
            )
        else:
            table = self._table_path(self.manifest["cells"]["parquet"])
            _, rows = self.query(f'SELECT id, "{name}" FROM read_parquet(?)', [table])

        if layer["kind"] == "categorical":
            code_of = {category: index for index, category in enumerate(layer["categories"])}
            for cell_id, value in rows:
                if 0 <= cell_id < self.cell_count and value is not None:
                    values[cell_id] = float(code_of.get(str(value), -1))
        else:
            for cell_id, value in rows:
                if 0 <= cell_id < self.cell_count and value is not None:
                    number = float(value)
                    values[cell_id] = number if math.isfinite(number) else _NAN
        return values

    # -- drill-down ----------------------------------------------------------

    def cell_record(self, cell_id: int) -> dict[str, Any]:
        if not 0 <= cell_id < self.cell_count:
            raise HTTPException(status_code=404, detail=f"cell {cell_id} out of range")
        cells_table = self._table_path(self.manifest["cells"]["parquet"])
        columns, rows = self.query(f"SELECT * FROM read_parquet(?) WHERE id = ?", [cells_table, cell_id])
        if not rows:
            raise HTTPException(status_code=404, detail=f"cell {cell_id} not found")
        record = dict(zip(columns, rows[0]))

        ledgers: dict[str, Any] = {}
        for history_name, history in self.manifest["stage_histories"].items():
            table = self._table_path(history["stage_cells_parquet"])
            columns, rows = self.query(
                "SELECT * FROM read_parquet(?) WHERE cell_id = ? ORDER BY stage_idx",
                [table, cell_id],
            )
            if rows:
                ledgers[history_name] = {
                    "stage_idx": [row[columns.index("stage_idx")] for row in rows],
                    "fields": {
                        column: [row[index] for row in rows]
                        for index, column in enumerate(columns)
                        if column not in ("stage_idx", "cell_id")
                    },
                }

        edges: list[dict[str, Any]] = []
        adjacency = self.manifest["families"].get("cell_adjacency_edges")
        if adjacency and "parquet" in adjacency:
            table = self._table_path(adjacency["parquet"])
            columns, rows = self.query(
                "SELECT * FROM read_parquet(?) WHERE cell_a_id = ? OR cell_b_id = ?",
                [table, cell_id, cell_id],
            )
            edges = [dict(zip(columns, row)) for row in rows]

        monthly: dict[str, list[float]] = {}
        monthly_manifest = self.manifest.get("monthly")
        if monthly_manifest:
            table = self._table_path(monthly_manifest["parquet"])
            columns, rows = self.query(
                "SELECT * FROM read_parquet(?) WHERE cell_id = ? ORDER BY month",
                [table, cell_id],
            )
            for index, column in enumerate(columns):
                if column not in ("cell_id", "month"):
                    monthly[column] = [row[index] for row in rows]

        return {"cell": record, "ledgers": ledgers, "adjacency_edges": edges, "monthly": monthly}

    # -- stage summaries -------------------------------------------------------

    def stage_summary(self, history_name: str) -> dict[str, Any]:
        history = self.manifest["stage_histories"].get(history_name)
        if history is None:
            raise HTTPException(status_code=404, detail=f"unknown stage history {history_name}")
        table = self._table_path(history["stages_parquet"])
        columns, rows = self.query("SELECT * FROM read_parquet(?) ORDER BY stage_idx", [table])
        return {
            "name": history_name,
            "stage_count": history["stage_count"],
            "columns": columns,
            "rows": [list(row) for row in rows],
        }

    def family_rows(self, family_name: str, limit: int, offset: int) -> dict[str, Any]:
        family = self.manifest["families"].get(family_name)
        if family is None:
            raise HTTPException(status_code=404, detail=f"unknown family {family_name}")
        if "parquet" in family or "scalars_parquet" in family:
            table = self._table_path(family.get("parquet") or family["scalars_parquet"])
            columns, rows = self.query(
                "SELECT * FROM read_parquet(?) LIMIT ? OFFSET ?", [table, limit, offset]
            )
            records = [dict(zip(columns, row)) for row in rows]
        else:
            path = self.dir / family["jsonl"]
            records = []
            with path.open("r", encoding="utf-8") as handle:
                for index, line in enumerate(handle):
                    if index < offset:
                        continue
                    if len(records) >= limit:
                        break
                    records.append(json.loads(line))
        return {"name": family_name, "total": family["row_count"], "offset": offset, "rows": records}

    def plate_boundary_segments(self) -> list[list[float]]:
        adjacency = self.manifest["families"].get("cell_adjacency_edges")
        if not adjacency or "parquet" not in adjacency:
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


def _float32_response(values: list[float]) -> Response:
    return Response(
        content=struct.pack(f"<{len(values)}f", *values),
        media_type="application/octet-stream",
        headers={"Cache-Control": "no-store"},
    )


def _arrow_response(values: list[float]) -> Response:
    import pyarrow as pa
    import pyarrow.ipc as ipc

    table = pa.table({"cell_id": pa.array(range(len(values)), type=pa.int32()),
                      "value": pa.array(values, type=pa.float32())})
    sink = pa.BufferOutputStream()
    with ipc.new_stream(sink, table.schema) as writer:
        writer.write_table(table)
    return Response(content=sink.getvalue().to_pybytes(), media_type="application/vnd.apache.arrow.stream")


def create_app(debug_dir: Path) -> FastAPI:
    cache = _DebugCache(Path(debug_dir))
    app = FastAPI(title="magic-geo debugger", docs_url=None, redoc_url=None)

    @app.get("/api/manifest")
    def manifest() -> dict[str, Any]:
        return cache.manifest

    @app.get("/api/layer/{layer_id:path}")
    def layer(
        layer_id: str,
        stage: int | None = Query(default=None),
        month: int | None = Query(default=None),
        format: str = Query(default="f32"),
    ) -> Response:
        values = cache.layer_values(layer_id, stage, month)
        if format == "arrow":
            return _arrow_response(values)
        return _float32_response(values)

    @app.get("/api/cell/{cell_id}")
    def cell(cell_id: int) -> dict[str, Any]:
        return cache.cell_record(cell_id)

    @app.get("/api/stage-summary/{history_name}")
    def stage_summary(history_name: str) -> dict[str, Any]:
        return cache.stage_summary(history_name)

    @app.get("/api/family/{family_name}")
    def family(
        family_name: str,
        limit: int = Query(default=200, ge=1, le=5000),
        offset: int = Query(default=0, ge=0),
    ) -> dict[str, Any]:
        return cache.family_rows(family_name, limit, offset)

    @app.get("/api/section/{section_name}")
    def section(section_name: str) -> Any:
        if section_name not in cache.sections:
            raise HTTPException(status_code=404, detail=f"unknown section {section_name}")
        return cache.sections[section_name]

    @app.get("/api/plate-boundaries")
    def plate_boundaries() -> list[list[float]]:
        return cache.plate_boundary_segments()

    app.mount("/mesh", StaticFiles(directory=cache.dir / "mesh"), name="mesh")
    app.mount("/", StaticFiles(directory=Path(__file__).parent / "debug_ui", html=True), name="ui")
    return app
