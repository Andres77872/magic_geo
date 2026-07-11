"""Rerun (.rrd) exporter: stage-scrubbable world recording for the Rerun viewer.

Logs the triangulated cell mesh with per-stage vertex colors on a ``stage``
timeline (driven by the hydrologic water-budget history), every numeric scalar
of the earth-system feedback ledger as time series, and plate-boundary line
segments. The result is a professional scrubbing/inspection UI for one
``rr.log`` walk of the payload — the plan's v0 accelerator alongside the full
web debugger.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import rerun as rr

_VIRIDIS = (
    (0.2777273272234177, 0.005407344544966578, 0.3340998053353061),
    (0.1050930431085774, 1.404613529898575, 1.384590162594685),
    (-0.3308618287255563, 0.214847559468213, 0.09509516302823659),
    (-4.634230498983486, -5.799100973351585, -19.33244095627987),
    (6.228269936347081, 14.17993336680509, 56.69055260068105),
    (4.776384997670288, -13.74514537774601, -65.35303263337234),
    (-5.435455855934631, 4.645852612178535, 26.3124352495832),
)


def _viridis_u8(t: float) -> tuple[int, int, int]:
    rgb = []
    for channel in range(3):
        acc = _VIRIDIS[6][channel]
        for k in range(5, -1, -1):
            acc = acc * t + _VIRIDIS[k][channel]
        rgb.append(max(0, min(255, int(acc * 255.0))))
    return rgb[0], rgb[1], rgb[2]


def _xyz(lat_deg: float, lon_deg: float) -> tuple[float, float, float]:
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    return (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat))


def _set_stage(stage_idx: int) -> None:
    # rerun >= 0.23 uses set_time(timeline, sequence=...); older uses set_time_sequence.
    try:
        rr.set_time("stage", sequence=stage_idx)
    except TypeError:
        rr.set_time_sequence("stage", stage_idx)


def _log_scalar(path: str, value: float) -> None:
    scalars = getattr(rr, "Scalars", None) or getattr(rr, "Scalar")
    rr.log(path, scalars(value))


def export_rerun_recording(world: dict, output: Path) -> dict[str, Any]:
    """Write a ``.rrd`` recording for ``world``; returns export statistics."""
    cells = world.get("cells")
    if not isinstance(cells, list) or not cells:
        raise ValueError("world payload has no cells; generate with output.include_cells enabled")
    by_id = sorted(cells, key=lambda cell: int(cell["id"]))

    positions: list[tuple[float, float, float]] = []
    triangles: list[tuple[int, int, int]] = []
    vertex_cell_rows: list[int] = []   # per-vertex row into by_id
    for row, cell in enumerate(by_id):
        ring = cell.get("boundary_ring")
        if not isinstance(ring, list) or len(ring) < 3:
            continue
        base = len(positions)
        positions.append(_xyz(float(cell.get("lat_deg", 0.0)), float(cell.get("lon_deg", 0.0))))
        vertex_cell_rows.append(row)
        for lat, lon in ring:
            positions.append(_xyz(float(lat), float(lon)))
            vertex_cell_rows.append(row)
        count = len(ring)
        for corner in range(count):
            triangles.append((base, base + 1 + corner, base + 1 + (corner + 1) % count))

    rr.init("magic-geo", spawn=False)
    rr.save(str(output))

    def vertex_colors(values_by_row: list[float]) -> list[tuple[int, int, int]]:
        finite = sorted(v for v in values_by_row if isinstance(v, (int, float)) and math.isfinite(v))
        if not finite:
            return [(60, 60, 60)] * len(vertex_cell_rows)
        lo = finite[int(0.02 * (len(finite) - 1))]
        hi = finite[int(0.98 * (len(finite) - 1))]
        span = (hi - lo) or 1.0
        return [
            _viridis_u8(max(0.0, min(1.0, (float(values_by_row[row]) - lo) / span)))
            if isinstance(values_by_row[row], (int, float)) else (60, 60, 60)
            for row in vertex_cell_rows
        ]

    stage_count = 0
    history = world.get("hydrologic_water_budget_history")
    if isinstance(history, list) and history:
        id_to_row = {int(cell["id"]): row for row, cell in enumerate(by_id)}
        for stage_idx, record in enumerate(history):
            _set_stage(stage_idx)
            cell_ids = record.get("cell_ids") or []
            elevations = record.get("elevation_m_by_cell") or []
            values_by_row: list[float] = [math.nan] * len(by_id)
            for cid, value in zip(cell_ids, elevations):
                row = id_to_row.get(int(cid))
                if row is not None and isinstance(value, (int, float)):
                    values_by_row[row] = float(value)
            rr.log(
                "world/mesh",
                rr.Mesh3D(
                    vertex_positions=positions,
                    triangle_indices=triangles,
                    vertex_colors=vertex_colors(values_by_row),
                ),
            )
            stage_count += 1
    else:
        _set_stage(0)
        values_by_row = [float(cell.get("elevation_m", 0.0)) for cell in by_id]
        rr.log(
            "world/mesh",
            rr.Mesh3D(
                vertex_positions=positions,
                triangle_indices=triangles,
                vertex_colors=vertex_colors(values_by_row),
            ),
        )

    scalar_count = 0
    feedback = world.get("earth_system_feedback_history")
    if isinstance(feedback, list):
        for stage_idx, record in enumerate(feedback):
            if not isinstance(record, dict):
                continue
            _set_stage(stage_idx)
            for key, value in record.items():
                if isinstance(value, bool):
                    _log_scalar(f"feedback/{key}", 1.0 if value else 0.0)
                    scalar_count += 1
                elif isinstance(value, (int, float)) and math.isfinite(float(value)):
                    _log_scalar(f"feedback/{key}", float(value))
                    scalar_count += 1

    boundary_count = 0
    edges = world.get("cell_adjacency_edges")
    if isinstance(edges, list):
        strips = []
        for edge in edges:
            if not (isinstance(edge, dict) and edge.get("plate_boundary")):
                continue
            try:
                start = _xyz(float(edge["boundary_segment_start_lat_deg"]), float(edge["boundary_segment_start_lon_deg"]))
                end = _xyz(float(edge["boundary_segment_end_lat_deg"]), float(edge["boundary_segment_end_lon_deg"]))
            except (KeyError, TypeError, ValueError):
                continue
            strips.append([[c * 1.003 for c in start], [c * 1.003 for c in end]])
        if strips:
            _set_stage(0)
            rr.log("world/plate_boundaries", rr.LineStrips3D(strips, colors=[(255, 107, 82)]), static=True)
            boundary_count = len(strips)

    return {
        "output": str(output),
        "vertices": len(positions),
        "triangles": len(triangles),
        "stages": stage_count,
        "feedback_scalars": scalar_count,
        "plate_boundary_segments": boundary_count,
    }
