"""Columnar debug-cache export for generated worlds.

Converts a monolithic ``world.json`` payload into an interactive-access debug
cache: Parquet tables per record family, JSONL files for nested provenance and
event families, a triangulated GPU-ready mesh asset with per-vertex cell ids
and precomputed 2D projection positions, ParaView ``.vtu``/``.pvd`` stage
files, and a machine-readable ``manifest.json`` field catalog.

The classifier is generic on purpose: record families are discovered from the
payload shape (scalar list-of-dicts, per-stage ``*_by_cell`` histories, nested
event records, dict sections) instead of hardcoded column lists, so new engine
or enricher output is picked up without touching this module. Anything that is
skipped is recorded in the manifest rather than dropped silently.
"""

from __future__ import annotations

import hashlib
import json
import math
from array import array
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

FORMAT_NAME = "magic-geo-debug-cache"
FORMAT_VERSION = 1

_SCALAR_TYPES = (str, int, float, bool, type(None))
_CATEGORY_LIMIT = 64
_VEC3_FIELDS = ("position_3d", "normal_3d")


def _is_scalar(value: Any) -> bool:
    return isinstance(value, _SCALAR_TYPES)


def _field_kind(values: list[Any]) -> str | None:
    """Classify a column: 'str', 'bool', 'int', 'float', or None when empty."""
    kind: str | None = None
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            candidate = "bool"
        elif isinstance(value, int):
            candidate = "int"
        elif isinstance(value, float):
            candidate = "float"
        elif isinstance(value, str):
            candidate = "str"
        else:
            return "mixed"
        if kind is None:
            kind = candidate
        elif kind != candidate:
            if {kind, candidate} == {"int", "float"}:
                kind = "float"
            else:
                return "mixed"
    return kind


_PA_TYPES = {
    "str": pa.string(),
    "bool": pa.bool_(),
    "int": pa.int64(),
    "float": pa.float64(),
}


def _pa_column(values: list[Any], kind: str) -> pa.Array:
    if kind == "float":
        values = [float(v) if v is not None else None for v in values]
    return pa.array(values, type=_PA_TYPES[kind])


def _write_parquet(path: Path, columns: dict[str, list[Any]], kinds: dict[str, str]) -> int:
    arrays = {name: _pa_column(values, kinds[name]) for name, values in columns.items()}
    table = pa.table(arrays)
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, path, compression="zstd")
    return table.num_rows


def _numeric_stats(values: list[Any]) -> dict[str, float] | None:
    finite = sorted(
        float(v) for v in values if v is not None and isinstance(v, (int, float)) and math.isfinite(float(v))
    )
    if not finite:
        return None
    last = len(finite) - 1
    return {
        "min": finite[0],
        "max": finite[-1],
        "p2": finite[int(0.02 * last)],
        "p98": finite[int(0.98 * last)],
    }


def _categories(values: list[Any]) -> list[str] | None:
    distinct: set[str] = set()
    for value in values:
        if value is None:
            continue
        distinct.add(str(value))
        if len(distinct) > _CATEGORY_LIMIT:
            return None
    return sorted(distinct)


def _layer_entry(layer_id: str, source: str, name: str, kind: str, values: list[Any]) -> dict[str, Any] | None:
    if kind in ("int", "float"):
        stats = _numeric_stats(values)
        if stats is None:
            return None
        return {"id": layer_id, "source": source, "name": name, "kind": "numeric", "stats": stats}
    if kind in ("str", "bool"):
        categories = _categories(values)
        if categories is None:
            return None
        return {"id": layer_id, "source": source, "name": name, "kind": "categorical", "categories": categories}
    return None


# ---------------------------------------------------------------------------
# Cells table


def _export_cells(cells: list[dict], tables_dir: Path, manifest: dict) -> None:
    ordered_keys: list[str] = []
    seen: set[str] = set()
    for cell in cells:
        for key in cell:
            if key not in seen:
                seen.add(key)
                ordered_keys.append(key)

    columns: dict[str, list[Any]] = {}
    kinds: dict[str, str] = {}
    monthly_columns: dict[str, list[Any]] = {}
    skipped: dict[str, str] = {}

    for key in ordered_keys:
        values = [cell.get(key) for cell in cells]
        if key in _VEC3_FIELDS:
            for axis_index, axis in enumerate("xyz"):
                axis_values = [
                    float(v[axis_index]) if isinstance(v, list) and len(v) == 3 else None for v in values
                ]
                columns[f"{key}_{axis}"] = axis_values
                kinds[f"{key}_{axis}"] = "float"
            continue
        kind = _field_kind(values)
        if kind is None:
            skipped[key] = "all null"
            continue
        if kind != "mixed":
            columns[key] = values
            kinds[key] = kind
            continue
        # List-valued field: keep 12-long numeric arrays as a monthly table.
        sample = next((v for v in values if v is not None), None)
        if (
            isinstance(sample, list)
            and len(sample) == 12
            and all(isinstance(item, (int, float)) for item in sample)
        ):
            monthly_columns[key] = values
        else:
            skipped[key] = "non-scalar field (rings/adjacency live in mesh assets)"

    cells_path = tables_dir / "cells.parquet"
    rows = _write_parquet(cells_path, columns, kinds)

    layers = []
    for name, kind in kinds.items():
        entry = _layer_entry(f"cells/{name}", "cells", name, kind, columns[name])
        if entry is not None:
            layers.append(entry)

    manifest["cells"] = {
        "parquet": "tables/cells.parquet",
        "row_count": rows,
        "fields": [{"name": name, "dtype": kinds[name]} for name in columns],
        "skipped_fields": skipped,
    }
    manifest["layers"].extend(layers)

    if monthly_columns:
        monthly: dict[str, list[Any]] = {"cell_id": [], "month": []}
        monthly_kinds = {"cell_id": "int", "month": "int"}
        for name in monthly_columns:
            monthly[name] = []
            monthly_kinds[name] = "float"
        for index, cell in enumerate(cells):
            cell_id = int(cell["id"])
            for month in range(12):
                monthly["cell_id"].append(cell_id)
                monthly["month"].append(month)
                for name, values in monthly_columns.items():
                    value = values[index]
                    monthly[name].append(float(value[month]) if isinstance(value, list) else None)
        rows = _write_parquet(tables_dir / "cells_monthly.parquet", monthly, monthly_kinds)
        manifest["monthly"] = {
            "parquet": "tables/cells_monthly.parquet",
            "row_count": rows,
            "fields": sorted(monthly_columns),
        }
        for name, values in monthly_columns.items():
            flat = [item for value in values if isinstance(value, list) for item in value]
            stats = _numeric_stats(flat)
            if stats is not None:
                manifest["layers"].append(
                    {
                        "id": f"monthly/{name}",
                        "source": "cells_monthly",
                        "name": name,
                        "kind": "numeric_monthly",
                        "month_count": 12,
                        "stats": stats,
                    }
                )


# ---------------------------------------------------------------------------
# Per-stage histories (records carrying cell_ids + *_by_cell parallel arrays)


def _is_stage_history(records: list[Any]) -> bool:
    if not records or not all(isinstance(record, dict) for record in records):
        return False
    first = records[0]
    return isinstance(first.get("cell_ids"), list) and any(key.endswith("_by_cell") for key in first)


def _export_stage_history(name: str, records: list[dict], tables_dir: Path, manifest: dict) -> None:
    summary_columns: dict[str, list[Any]] = {"stage_idx": []}
    summary_kinds: dict[str, str] = {"stage_idx": "int"}
    per_cell_fields = sorted(
        {key[: -len("_by_cell")] for record in records for key in record if key.endswith("_by_cell")}
    )

    stage_columns: dict[str, list[Any]] = {"stage_idx": [], "cell_id": []}
    stage_kinds: dict[str, str] = {"stage_idx": "int", "cell_id": "int"}
    for field in per_cell_fields:
        stage_columns[field] = []
        stage_kinds[field] = "float"

    stage_meta = []
    for stage_idx, record in enumerate(records):
        cell_ids = record.get("cell_ids") or []
        meta: dict[str, Any] = {"stage_idx": stage_idx}
        summary_columns["stage_idx"].append(stage_idx)
        for key, value in record.items():
            if key == "cell_ids" or key.endswith("_by_cell"):
                continue
            if _is_scalar(value):
                if key not in summary_columns:
                    summary_columns[key] = [None] * stage_idx
                    summary_kinds[key] = "float"
                summary_columns[key].append(value)
                if key in ("id", "stage", "erosion_iteration", "feedback_stage_id"):
                    meta[key] = value
        for column in summary_columns.values():
            if len(column) <= stage_idx:
                column.append(None)
        stage_meta.append(meta)

        count = len(cell_ids)
        stage_columns["stage_idx"].extend([stage_idx] * count)
        stage_columns["cell_id"].extend(int(cid) for cid in cell_ids)
        for field in per_cell_fields:
            values = record.get(f"{field}_by_cell")
            if isinstance(values, list) and len(values) == count:
                stage_columns[field].extend(values)
            else:
                stage_columns[field].extend([None] * count)

    for key, values in list(summary_columns.items()):
        kind = _field_kind(values)
        summary_kinds[key] = kind if kind in ("str", "bool", "int", "float") else "float"

    cells_rel = f"tables/{name}_stage_cells.parquet"
    summary_rel = f"tables/{name}_stages.parquet"
    cell_rows = _write_parquet(tables_dir / f"{name}_stage_cells.parquet", stage_columns, stage_kinds)
    _write_parquet(tables_dir / f"{name}_stages.parquet", summary_columns, summary_kinds)

    manifest["stage_histories"][name] = {
        "stage_count": len(records),
        "stage_cells_parquet": cells_rel,
        "stages_parquet": summary_rel,
        "per_cell_fields": per_cell_fields,
        "row_count": cell_rows,
        "stages": stage_meta,
    }
    for field in per_cell_fields:
        stats = _numeric_stats(stage_columns[field])
        if stats is None:
            continue
        manifest["layers"].append(
            {
                "id": f"{name}/{field}",
                "source": name,
                "name": field,
                "kind": "numeric_stage",
                "stage_count": len(records),
                "stats": stats,
            }
        )


# ---------------------------------------------------------------------------
# Generic record families


def _export_family(name: str, records: list[dict], tables_dir: Path, events_dir: Path, manifest: dict) -> None:
    field_values: dict[str, list[Any]] = {}
    flat = True
    for record in records:
        for key, value in record.items():
            field_values.setdefault(key, [])
            if not _is_scalar(value):
                flat = False
    for record in records:
        for key in field_values:
            field_values[key].append(record.get(key))

    scalar_fields = {
        key: kind
        for key, values in field_values.items()
        if (kind := _field_kind(values)) in ("str", "bool", "int", "float")
    }

    if flat:
        rows = _write_parquet(
            tables_dir / f"{name}.parquet",
            {key: field_values[key] for key in scalar_fields},
            scalar_fields,
        )
        manifest["families"][name] = {
            "kind": "parquet",
            "parquet": f"tables/{name}.parquet",
            "row_count": rows,
        }
        return

    events_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = events_dir / f"{name}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")
    entry: dict[str, Any] = {
        "kind": "jsonl",
        "jsonl": f"events/{name}.jsonl",
        "row_count": len(records),
    }
    # Nested families still get a scalar-column Parquet sidecar when there is
    # enough flat structure for sparkline/table queries.
    if len(scalar_fields) >= 3 and len(records) >= 2:
        rows = _write_parquet(
            tables_dir / f"{name}.scalars.parquet",
            {key: field_values[key] for key in scalar_fields},
            scalar_fields,
        )
        entry["kind"] = "jsonl+scalars"
        entry["scalars_parquet"] = f"tables/{name}.scalars.parquet"
        entry["scalar_row_count"] = rows
    manifest["families"][name] = entry


# ---------------------------------------------------------------------------
# Triangulated mesh asset


def _xyz_from_lat_lon(lat_deg: float, lon_deg: float) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    cos_lat = math.cos(lat)
    return (cos_lat * math.cos(lon), cos_lat * math.sin(lon), math.sin(lat))


def _mollweide_normalized(lat_deg: float, lon_deg: float) -> tuple[float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    if abs(abs(lat) - math.pi / 2.0) < 1e-9:
        theta = math.copysign(math.pi / 2.0, lat)
    else:
        theta = lat
        for _ in range(8):
            denominator = 2.0 + 2.0 * math.cos(2.0 * theta)
            if abs(denominator) < 1e-12:
                break
            theta -= (2.0 * theta + math.sin(2.0 * theta) - math.pi * math.sin(lat)) / denominator
    return (lon / math.pi) * math.cos(theta), math.sin(theta)


def _wrap_lon_near(lon_deg: float, anchor_deg: float) -> float:
    return anchor_deg + ((lon_deg - anchor_deg + 180.0) % 360.0) - 180.0


def _export_mesh(cells: list[dict], mesh_dir: Path, manifest: dict) -> dict[str, Any]:
    ids = [int(cell.get("id", -1)) for cell in cells]
    if sorted(ids) != list(range(len(cells))):
        raise ValueError("debug export requires contiguous cell ids 0..n-1")
    by_id = sorted(cells, key=lambda cell: int(cell["id"]))

    positions = array("f")
    cell_ids = array("I")
    indices = array("I")
    equirect = array("f")
    mollweide = array("f")
    cells_without_ring = 0

    for cell in by_id:
        cell_id = int(cell["id"])
        ring = cell.get("boundary_ring")
        if not isinstance(ring, list) or len(ring) < 3:
            cells_without_ring += 1
            continue
        center_lat = float(cell.get("lat_deg", 0.0))
        center_lon = float(cell.get("lon_deg", 0.0))
        position = cell.get("position_3d")
        if isinstance(position, list) and len(position) == 3:
            norm = math.sqrt(sum(component * component for component in position)) or 1.0
            center_xyz = tuple(component / norm for component in position)
        else:
            center_xyz = _xyz_from_lat_lon(center_lat, center_lon)

        base_index = len(cell_ids)
        positions.extend(center_xyz)
        cell_ids.append(cell_id)
        equirect.extend((center_lon / 180.0, center_lat / 90.0))
        mollweide.extend(_mollweide_normalized(center_lat, center_lon))

        ring_count = len(ring)
        for lat_deg, lon_deg in ring:
            lon_adj = _wrap_lon_near(float(lon_deg), center_lon)
            positions.extend(_xyz_from_lat_lon(float(lat_deg), float(lon_deg)))
            cell_ids.append(cell_id)
            equirect.extend((lon_adj / 180.0, float(lat_deg) / 90.0))
            mollweide.extend(_mollweide_normalized(float(lat_deg), lon_adj))
        for corner in range(ring_count):
            indices.extend(
                (base_index, base_index + 1 + corner, base_index + 1 + (corner + 1) % ring_count)
            )

    mesh_dir.mkdir(parents=True, exist_ok=True)
    buffers = {
        "positions.f32": positions,
        "cell_ids.u32": cell_ids,
        "indices.u32": indices,
        "pos_equirect.f32": equirect,
        "pos_mollweide.f32": mollweide,
    }
    for filename, buffer in buffers.items():
        (mesh_dir / filename).write_bytes(buffer.tobytes())

    mesh_info = {
        "vertex_count": len(cell_ids),
        "triangle_count": len(indices) // 3,
        "cell_count": len(by_id),
        "cells_without_ring": cells_without_ring,
        "endianness": "little",
        "buffers": {
            "positions": {"file": "mesh/positions.f32", "dtype": "float32", "components": 3},
            "cell_ids": {"file": "mesh/cell_ids.u32", "dtype": "uint32", "components": 1},
            "indices": {"file": "mesh/indices.u32", "dtype": "uint32", "components": 3},
            "pos_equirect": {"file": "mesh/pos_equirect.f32", "dtype": "float32", "components": 2},
            "pos_mollweide": {"file": "mesh/pos_mollweide.f32", "dtype": "float32", "components": 2},
        },
    }
    (mesh_dir / "mesh.json").write_text(json.dumps(mesh_info, indent=2), encoding="utf-8")
    manifest["mesh"] = mesh_info
    return mesh_info


# ---------------------------------------------------------------------------
# ParaView companion export (.vtu per stage + .pvd collection)


def _write_vtu_stages(
    world: dict,
    vtu_dir: Path,
    manifest: dict,
    *,
    elevation_exaggeration: float,
) -> None:
    history = world.get("hydrologic_water_budget_history")
    cells = world.get("cells") or []
    if not isinstance(history, list) or not history or not cells:
        return
    by_id = sorted(cells, key=lambda cell: int(cell["id"]))
    rings = []
    ring_cell_ids = []
    for cell in by_id:
        ring = cell.get("boundary_ring")
        if isinstance(ring, list) and len(ring) >= 3:
            rings.append([_xyz_from_lat_lon(float(lat), float(lon)) for lat, lon in ring])
            ring_cell_ids.append(int(cell["id"]))
    if not rings:
        return

    radius_km = 6371.0
    planet = world.get("planet_parameters")
    if isinstance(planet, dict) and isinstance(planet.get("radius_km"), (int, float)):
        radius_km = float(planet["radius_km"])

    vtu_dir.mkdir(parents=True, exist_ok=True)
    stage_files = []
    for stage_idx, record in enumerate(history):
        cell_ids = record.get("cell_ids") or []
        id_to_row = {int(cid): row for row, cid in enumerate(cell_ids)}
        elevations = record.get("elevation_m_by_cell") or []
        per_cell_arrays = {
            key[: -len("_by_cell")]: value
            for key, value in record.items()
            if key.endswith("_by_cell") and isinstance(value, list)
        }

        points: list[str] = []
        connectivity: list[str] = []
        offsets: list[str] = []
        offset = 0
        for ring, cell_id in zip(rings, ring_cell_ids):
            row = id_to_row.get(cell_id)
            elevation = float(elevations[row]) if row is not None and row < len(elevations) else 0.0
            radial = 1.0 + elevation_exaggeration * elevation / (radius_km * 1000.0)
            start = offset
            for x, y, z in ring:
                points.append(f"{x * radial:.6f} {y * radial:.6f} {z * radial:.6f}")
                connectivity.append(str(offset))
                offset += 1
            offsets.append(str(offset))
            del start

        cell_data_blocks = []
        for field, values in sorted(per_cell_arrays.items()):
            rows = []
            for cell_id in ring_cell_ids:
                row = id_to_row.get(cell_id)
                rows.append(f"{float(values[row]):.6f}" if row is not None and row < len(values) else "0")
            cell_data_blocks.append(
                f'    <DataArray type="Float32" Name="{field}" format="ascii">\n'
                + " ".join(rows)
                + "\n    </DataArray>"
            )

        filename = f"stage_{stage_idx:04d}.vtu"
        content = (
            '<?xml version="1.0"?>\n'
            '<VTKFile type="UnstructuredGrid" version="0.1" byte_order="LittleEndian">\n'
            " <UnstructuredGrid>\n"
            f'  <Piece NumberOfPoints="{offset}" NumberOfCells="{len(rings)}">\n'
            "   <Points>\n"
            '    <DataArray type="Float32" NumberOfComponents="3" format="ascii">\n'
            + " ".join(points)
            + "\n    </DataArray>\n"
            "   </Points>\n"
            "   <Cells>\n"
            '    <DataArray type="Int64" Name="connectivity" format="ascii">\n'
            + " ".join(connectivity)
            + "\n    </DataArray>\n"
            '    <DataArray type="Int64" Name="offsets" format="ascii">\n'
            + " ".join(offsets)
            + "\n    </DataArray>\n"
            '    <DataArray type="UInt8" Name="types" format="ascii">\n'
            + " ".join(["7"] * len(rings))
            + "\n    </DataArray>\n"
            "   </Cells>\n"
            "   <CellData>\n" + "\n".join(cell_data_blocks) + "\n   </CellData>\n"
            "  </Piece>\n"
            " </UnstructuredGrid>\n"
            "</VTKFile>\n"
        )
        (vtu_dir / filename).write_text(content, encoding="utf-8")
        stage_files.append(filename)

    datasets = "\n".join(
        f'  <DataSet timestep="{index}" group="" part="0" file="vtu/{filename}"/>'
        for index, filename in enumerate(stage_files)
    )
    pvd = (
        '<?xml version="1.0"?>\n'
        '<VTKFile type="Collection" version="0.1" byte_order="LittleEndian">\n'
        " <Collection>\n" + datasets + "\n </Collection>\n"
        "</VTKFile>\n"
    )
    (vtu_dir.parent / "world.pvd").write_text(pvd, encoding="utf-8")
    manifest["paraview"] = {
        "pvd": "world.pvd",
        "stage_count": len(stage_files),
        "elevation_exaggeration": elevation_exaggeration,
    }


# ---------------------------------------------------------------------------
# Entry point


def export_debug_cache(
    world: dict,
    out_dir: Path,
    *,
    source_path: Path | None = None,
    include_vtu: bool = True,
    elevation_exaggeration: float = 30.0,
) -> dict:
    """Export ``world`` into a columnar debug cache under ``out_dir``.

    Returns the manifest dict (also written to ``out_dir/manifest.json``).
    """
    cells = world.get("cells")
    if not isinstance(cells, list) or not cells:
        raise ValueError("world payload has no cells; generate with output.include_cells enabled")

    out_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = out_dir / "tables"
    events_dir = out_dir / "events"
    mesh_dir = out_dir / "mesh"

    manifest: dict[str, Any] = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "world": {
            "name": world.get("name"),
            "schema_version": world.get("schema_version"),
            "mesh_backend": world.get("mesh_backend"),
            "generation_scope": world.get("generation_scope", "full"),
            "cell_count": len(cells),
        },
        "layers": [],
        "stage_histories": {},
        "families": {},
        "sections": [],
        "scalars": {},
        "skipped_sections": {},
    }
    if source_path is not None:
        data = Path(source_path).read_bytes()
        manifest["source"] = {
            "path": str(source_path),
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    _export_cells(cells, tables_dir, manifest)
    _export_mesh(cells, mesh_dir, manifest)

    sections: dict[str, Any] = {}
    for key, value in world.items():
        if key == "cells":
            continue
        if _is_scalar(value):
            manifest["scalars"][key] = value
        elif isinstance(value, dict):
            sections[key] = value
        elif isinstance(value, list):
            if not value:
                manifest["skipped_sections"][key] = "empty list"
            elif _is_stage_history(value):
                _export_stage_history(key, value, tables_dir, manifest)
            elif all(isinstance(record, dict) for record in value):
                _export_family(key, value, tables_dir, events_dir, manifest)
            else:
                sections[key] = value
        else:
            manifest["skipped_sections"][key] = f"unhandled type {type(value).__name__}"

    (out_dir / "sections.json").write_text(
        json.dumps(sections, indent=2, sort_keys=True), encoding="utf-8"
    )
    manifest["sections"] = sorted(sections)

    # Stage clock summary for the time controls.
    clock = world.get("simulation_clock")
    if isinstance(clock, dict):
        manifest["simulation_clock"] = {
            key: clock.get(key)
            for key in (
                "clock_type",
                "time_unit",
                "stage_count",
                "initial_stage_id",
                "current_stage_id",
                "final_stage_id",
                "feedback_recompute_count",
                "hydrologic_water_budget_recompute_count",
            )
        }

    if include_vtu:
        _write_vtu_stages(world, out_dir / "vtu", manifest, elevation_exaggeration=elevation_exaggeration)

    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
