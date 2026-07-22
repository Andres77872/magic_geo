"""Coverage for the columnar debug-cache exporter.

``tests/test_debug_server.py`` already exercises the happy-path Parquet tables,
the cell-detail sidecar and one categorical ``.vtu`` stage. This module targets
what that file leaves untested: the classifier helpers, the monthly long table,
the JSONL family writer, the mesh/ParaView geometry paths, the manifest that
:func:`export_debug_cache` assembles, its per-call options, and the failure
modes of an unusable output directory.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import SkipTest, TestCase

try:
    import pyarrow.parquet as pq

    from magic_geo.debug_export import (
        FORMAT_NAME,
        FORMAT_VERSION,
        _categories,
        _export_cells,
        _export_family,
        _export_mesh,
        _export_stage_history,
        _field_kind,
        _is_stage_history,
        _layer_entry,
        _mollweide_normalized,
        _numeric_stats,
        _write_vtu_stages,
        export_debug_cache,
    )
except ImportError as exc:  # The exporter needs the optional debug extra.
    raise SkipTest(f"debug export tests require magic-geo[debug]: {exc}") from exc

from support import worlds


def _blank_manifest() -> dict:
    """The manifest skeleton the private exporters expect to extend."""

    return {"layers": [], "families": {}, "stage_histories": {}}


def _read_parquet(path: Path) -> dict:
    return pq.read_table(path).to_pydict()


def _ring(lat: float, lon: float) -> list[list[float]]:
    """A three-corner boundary ring anchored near ``(lat, lon)``."""

    return [[lat, lon], [lat, lon + 1.0], [lat + 1.0, lon]]


def _points(vtu_path: Path) -> list[tuple[float, float, float]]:
    """Parse the ``Points`` block of a ``.vtu`` stage into xyz triples."""

    text = vtu_path.read_text(encoding="utf-8")
    block = text.split("<Points>", 1)[1].split("</Points>", 1)[0]
    body = block.split("ascii\">", 1)[1].split("</DataArray>", 1)[0]
    numbers = [float(token) for token in body.split()]
    return [tuple(numbers[index : index + 3]) for index in range(0, len(numbers), 3)]


def _data_arrays(vtu_path: Path) -> dict[str, str]:
    """Map ``CellData`` array name -> its raw ascii payload."""

    text = vtu_path.read_text(encoding="utf-8")
    block = text.split("<CellData>", 1)[1].split("</CellData>", 1)[0]
    return {
        match.group(1): match.group(2).strip()
        for match in re.finditer(
            r'<DataArray type="Float32" Name="([^"]*)" format="ascii">\n(.*?)\n\s*</DataArray>',
            block,
            re.DOTALL,
        )
    }


def _tiny_world() -> dict:
    """A compact but structurally complete world payload."""

    return {
        "name": "tiny",
        "schema_version": 2,
        "mesh_backend": "test",
        "generation_scope": "partial",
        "seed": 7,
        "calibrated": True,
        "nan_scalar": float("nan"),
        "planet_parameters": {"radius_km": 6371.0},
        "cells": [
            {
                "id": 0,
                "lat_deg": 0.0,
                "lon_deg": 0.0,
                "elevation_m": 1000.0,
                "biome": "forest",
                "boundary_ring": _ring(0.0, 0.0),
                "position_3d": [1.0, 0.0, 0.0],
                "neighbors": [1],
                "temperature_monthly_c": [float(month) for month in range(12)],
            },
            {
                "id": 1,
                "lat_deg": 10.0,
                "lon_deg": 10.0,
                "elevation_m": -500.0,
                "biome": "ocean",
                "boundary_ring": _ring(10.0, 10.0),
                "position_3d": [0.0, 1.0, 0.0],
                "neighbors": [0],
                "temperature_monthly_c": [float(month) * 2.0 for month in range(12)],
            },
        ],
        "hydrologic_water_budget_history": [
            {"cell_ids": [0, 1], "elevation_m_by_cell": [1000.0, -500.0], "mean_runoff": 1.0},
            {"cell_ids": [0, 1], "elevation_m_by_cell": [1100.0, -500.0], "mean_runoff": 2.0},
        ],
        "settlements": [{"id": 0, "cell_id": 1, "name": "port", "population": 120}],
        "empty_family": [],
        "loose_numbers": [1, 2, 3],
        "unhandled": {1, 2},
        "simulation_clock": {"clock_type": "test_clock", "stage_count": 2, "time_unit": "model_step"},
    }


class FieldClassificationTests(TestCase):
    """The generic column classifier and the manifest layer summaries."""

    def test_field_kind_widens_numbers_and_flags_mixed_columns(self) -> None:
        cases = [
            ("empty column", [], None),
            ("all null column", [None, None], None),
            ("bools ignore nulls", [None, True, False], "bool"),
            ("ints", [1, 2], "int"),
            ("floats", [1.5, None], "float"),
            ("strings", ["a", "b"], "str"),
            ("int then float widens", [1, 2.5], "float"),
            ("float then int widens", [2.5, 1], "float"),
            ("bool then int is mixed", [True, 1], "mixed"),
            ("str then int is mixed", ["a", 1], "mixed"),
            ("leading list is mixed", [[1, 2], [3, 4]], "mixed"),
            ("trailing dict is mixed", [1, {"a": 1}], "mixed"),
        ]
        for label, values, expected in cases:
            with self.subTest(label):
                self.assertEqual(_field_kind(values), expected)

    def test_numeric_stats_use_sorted_percentile_positions(self) -> None:
        stats = _numeric_stats([float(value) for value in range(100)])
        self.assertEqual(stats, {"min": 0.0, "max": 99.0, "p2": 1.0, "p98": 97.0})

        filtered = _numeric_stats([None, float("nan"), float("inf"), "text", 3])
        self.assertEqual(filtered, {"min": 3.0, "max": 3.0, "p2": 3.0, "p98": 3.0})

        self.assertIsNone(_numeric_stats([None, float("nan"), float("-inf")]))

    def test_categories_stringify_distinct_values_up_to_the_limit(self) -> None:
        self.assertEqual(_categories([None, "b", "a", "a", True]), ["True", "a", "b"])
        self.assertEqual(
            _categories([f"v{index:02d}" for index in range(64)] * 2),
            [f"v{index:02d}" for index in range(64)],
        )
        self.assertIsNone(_categories([f"v{index}" for index in range(65)]))

    def test_layer_entry_describes_usable_columns_and_rejects_the_rest(self) -> None:
        self.assertEqual(
            _layer_entry(
                "cells/elevation_m",
                "cells",
                "elevation_m",
                "float",
                [float(value) for value in range(100)],
            ),
            {
                "id": "cells/elevation_m",
                "source": "cells",
                "name": "elevation_m",
                "kind": "numeric",
                "stats": {"min": 0.0, "max": 99.0, "p2": 1.0, "p98": 97.0},
            },
        )
        self.assertEqual(
            _layer_entry("cells/biome", "cells", "biome", "str", ["ocean", "forest"]),
            {
                "id": "cells/biome",
                "source": "cells",
                "name": "biome",
                "kind": "categorical",
                "categories": ["forest", "ocean"],
            },
        )
        # Booleans are categorical too, stringified into two categories.
        self.assertEqual(
            _layer_entry("cells/is_land", "cells", "is_land", "bool", [True, None, False, True]),
            {
                "id": "cells/is_land",
                "source": "cells",
                "name": "is_land",
                "kind": "categorical",
                "categories": ["False", "True"],
            },
        )
        rejected = [
            ("numeric without finite values", "float", [float("nan"), None]),
            ("categorical over the limit", "str", [f"v{index}" for index in range(65)]),
            ("mixed kind", "mixed", [1, "a"]),
        ]
        for label, kind, values in rejected:
            with self.subTest(label):
                self.assertIsNone(_layer_entry("cells/x", "cells", "x", kind, values))


class CellExportTests(TestCase):
    """``_export_cells``: the monthly long table and the lossless sidecars."""

    def test_twelve_long_numeric_lists_become_a_monthly_table_and_layer(self) -> None:
        cells = [
            {
                "id": 0,
                "temperature_monthly_c": [float(month) for month in range(12)],
                "wind_monthly_east": [None] + [1.0] * 11,
                "void_monthly": [float("nan")] * 12,
            },
            {
                "id": 1,
                "temperature_monthly_c": [float(month) + 100.0 for month in range(12)],
                "wind_monthly_east": None,
                "void_monthly": [float("nan")] * 12,
            },
        ]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _export_cells(cells, root / "tables", root / "events", manifest)

            monthly = manifest["monthly"]
            self.assertEqual(monthly["parquet"], "tables/cells_monthly.parquet")
            self.assertEqual(monthly["row_count"], 24)
            self.assertEqual(
                monthly["fields"], ["temperature_monthly_c", "void_monthly", "wind_monthly_east"]
            )
            self.assertEqual(
                monthly["skipped_layers"],
                {"void_monthly": "no finite values (column kept in cells_monthly.parquet)"},
            )

            table = _read_parquet(root / monthly["parquet"])
            self.assertEqual(table["cell_id"], [0] * 12 + [1] * 12)
            self.assertEqual(table["month"], list(range(12)) * 2)
            self.assertEqual(table["temperature_monthly_c"][3], 3.0)
            self.assertEqual(table["temperature_monthly_c"][15], 103.0)
            # A null inside the ring and a wholly missing list both survive as nulls.
            self.assertIsNone(table["wind_monthly_east"][0])
            self.assertEqual(table["wind_monthly_east"][1], 1.0)
            self.assertEqual(table["wind_monthly_east"][12:], [None] * 12)
            self.assertTrue(all(math.isnan(value) for value in table["void_monthly"]))

            monthly_layers = [
                layer for layer in manifest["layers"] if layer["source"] == "cells_monthly"
            ]
            self.assertEqual(
                monthly_layers,
                [
                    {
                        "id": "monthly/temperature_monthly_c",
                        "source": "cells_monthly",
                        "name": "temperature_monthly_c",
                        "kind": "numeric_monthly",
                        "month_count": 12,
                        "stats": {"min": 0.0, "max": 111.0, "p2": 0.0, "p98": 110.0},
                    },
                    {
                        "id": "monthly/wind_monthly_east",
                        "source": "cells_monthly",
                        "name": "wind_monthly_east",
                        "kind": "numeric_monthly",
                        "month_count": 12,
                        "stats": {"min": 1.0, "max": 1.0, "p2": 1.0, "p98": 1.0},
                    },
                ],
            )
            # The monthly columns stay out of the wide cells table.
            self.assertEqual(
                manifest["cells"]["fields"], [{"name": "id", "dtype": "int"}]
            )
            self.assertEqual(manifest["cells"]["detail_fields"], [
                "temperature_monthly_c",
                "wind_monthly_east",
                "void_monthly",
            ])

    def test_unusable_cell_columns_are_reported_but_never_dropped(self) -> None:
        cells = [
            {
                "id": index,
                "code": f"c{index}",
                "always_null": None,
                "void": float("nan"),
                "ragged": [index, index + 1],
            }
            for index in range(70)
        ]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _export_cells(cells, root / "tables", root / "events", manifest)

            cell_manifest = manifest["cells"]
            self.assertEqual(
                cell_manifest["skipped_fields"],
                {
                    "always_null": "all null",
                    "ragged": "non-scalar field retained in indexed cell details",
                },
            )
            self.assertEqual(
                cell_manifest["skipped_layers"],
                {
                    "code": "more than 64 distinct values (column kept in cells.parquet)",
                    "void": "no finite values (column kept in cells.parquet)",
                },
            )
            self.assertEqual(cell_manifest["detail_fields"], ["always_null", "ragged"])
            self.assertEqual([layer["id"] for layer in manifest["layers"]], ["cells/id"])
            # Columns whose *layer* was rejected are still catalogued as fields.
            self.assertEqual(
                cell_manifest["fields"],
                [
                    {"name": "id", "dtype": "int"},
                    {"name": "code", "dtype": "str"},
                    {"name": "void", "dtype": "float"},
                ],
            )
            self.assertNotIn("monthly", manifest)

            # Skipped *layers* keep their column; skipped *fields* keep their values.
            table = _read_parquet(root / cell_manifest["parquet"])
            self.assertEqual(sorted(table), ["code", "id", "void"])
            self.assertEqual(table["code"][5], "c5")
            offsets = json.loads((root / cell_manifest["details_index"]).read_text(encoding="utf-8"))
            with (root / cell_manifest["details_jsonl"]).open("rb") as handle:
                handle.seek(offsets["5"])
                record = json.loads(handle.readline())
            self.assertEqual(record, {"always_null": None, "ragged": [5, 6]})
            self.assertEqual(len(offsets), 70)

    def test_vector_fields_are_split_into_axis_columns_and_kept_verbatim(self) -> None:
        cells = [
            {"id": 0, "position_3d": [0.0, 1.0, 2.0], "normal_3d": [3.0, 4.0, 5.0]},
            {"id": 1, "position_3d": [6.0, 7.0], "normal_3d": None},
        ]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _export_cells(cells, root / "tables", root / "events", manifest)

            cell_manifest = manifest["cells"]
            self.assertEqual(
                cell_manifest["fields"],
                [
                    {"name": "id", "dtype": "int"},
                    {"name": "position_3d_x", "dtype": "float"},
                    {"name": "position_3d_y", "dtype": "float"},
                    {"name": "position_3d_z", "dtype": "float"},
                    {"name": "normal_3d_x", "dtype": "float"},
                    {"name": "normal_3d_y", "dtype": "float"},
                    {"name": "normal_3d_z", "dtype": "float"},
                ],
            )
            self.assertEqual(cell_manifest["detail_fields"], ["position_3d", "normal_3d"])
            self.assertEqual(cell_manifest["skipped_fields"], {})

            table = _read_parquet(root / cell_manifest["parquet"])
            # Each axis becomes its own float column; a wrong-length or missing
            # vector yields nulls instead of a partial row.
            self.assertEqual(table["position_3d_x"], [0.0, None])
            self.assertEqual(table["position_3d_y"], [1.0, None])
            self.assertEqual(table["position_3d_z"], [2.0, None])
            self.assertEqual(table["normal_3d_x"], [3.0, None])
            self.assertEqual(table["normal_3d_y"], [4.0, None])
            self.assertEqual(table["normal_3d_z"], [5.0, None])

            # The unsplit vectors survive verbatim in the detail sidecar.
            offsets = json.loads((root / cell_manifest["details_index"]).read_text(encoding="utf-8"))
            with (root / cell_manifest["details_jsonl"]).open("rb") as handle:
                handle.seek(offsets["1"])
                record = json.loads(handle.readline())
            self.assertEqual(record, {"position_3d": [6.0, 7.0], "normal_3d": None})

            self.assertEqual(
                [layer["id"] for layer in manifest["layers"]],
                [
                    "cells/id",
                    "cells/position_3d_x",
                    "cells/position_3d_y",
                    "cells/position_3d_z",
                    "cells/normal_3d_x",
                    "cells/normal_3d_y",
                    "cells/normal_3d_z",
                ],
            )

    def test_cell_details_are_indexed_by_cell_id_not_row_position(self) -> None:
        cells = [
            {"id": 9, "ring": [9, 90]},
            {"id": 4, "ring": [4, 40]},
            {"ring": [7, 70]},  # No ``id`` at all: the row index stands in.
        ]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _export_cells(cells, root / "tables", root / "events", manifest)

            cell_manifest = manifest["cells"]
            offsets = json.loads((root / cell_manifest["details_index"]).read_text(encoding="utf-8"))
            self.assertEqual(sorted(offsets), ["2", "4", "9"])
            # Records stay in row order, so the ids are deliberately out of order.
            self.assertEqual(offsets["9"], 0)
            self.assertLess(offsets["9"], offsets["4"])
            self.assertLess(offsets["4"], offsets["2"])

            details = {}
            with (root / cell_manifest["details_jsonl"]).open("rb") as handle:
                for key, offset in offsets.items():
                    handle.seek(offset)
                    details[key] = json.loads(handle.readline())
            self.assertEqual(
                details,
                {"9": {"ring": [9, 90]}, "4": {"ring": [4, 40]}, "2": {"ring": [7, 70]}},
            )

    def test_all_scalar_cells_produce_no_detail_sidecar_at_all(self) -> None:
        cells = [{"id": 0, "elevation_m": 1.5}, {"id": 1, "elevation_m": -2.5}]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _export_cells(cells, root / "tables", root / "events", manifest)

            self.assertEqual(
                sorted(manifest["cells"]),
                ["fields", "parquet", "row_count", "skipped_fields", "skipped_layers"],
            )
            self.assertEqual(manifest["cells"]["row_count"], 2)
            self.assertFalse((root / "events").exists())
            self.assertFalse((root / "tables" / "cell_details_index.json").exists())


class FamilyExportTests(TestCase):
    """``_export_family``: the JSONL writer and its optional scalar sidecar."""

    def test_nested_records_are_written_as_jsonl_with_a_scalar_sidecar(self) -> None:
        records = [
            {"id": 0, "name": "a", "score": 1.5, "tags": ["x"], "meta": {"k": float("nan")}},
            {"id": 1, "name": "b", "score": 2.5, "tags": [], "meta": {"k": 3.0}},
        ]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _export_family("events", records, root / "tables", root / "events", manifest)

            entry = manifest["families"]["events"]
            self.assertEqual(entry["kind"], "jsonl+scalars")
            self.assertEqual(entry["row_count"], 2)
            self.assertEqual(entry["scalar_row_count"], 2)

            lines = (root / entry["jsonl"]).read_text(encoding="utf-8").splitlines()
            self.assertEqual(
                lines[0],
                '{"id": 0, "meta": {"k": null}, "name": "a", "score": 1.5, "tags": ["x"]}',
            )
            self.assertEqual(json.loads(lines[1])["meta"], {"k": 3.0})

            sidecar = _read_parquet(root / entry["scalars_parquet"])
            self.assertEqual(
                sidecar, {"id": [0, 1], "name": ["a", "b"], "score": [1.5, 2.5]}
            )

    def test_nested_records_without_enough_flat_structure_stay_jsonl_only(self) -> None:
        cases = [
            ("too few scalar columns", [{"id": 0, "payload": {"a": 1}}, {"id": 1, "payload": {}}]),
            ("single record", [{"id": 0, "name": "a", "score": 1.0, "payload": {"a": 1}}]),
        ]
        for label, records in cases:
            with self.subTest(label), TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                manifest = _blank_manifest()
                _export_family("f", records, root / "tables", root / "events", manifest)

                entry = manifest["families"]["f"]
                self.assertEqual(entry["kind"], "jsonl")
                self.assertNotIn("scalars_parquet", entry)
                self.assertEqual(entry["row_count"], len(records))
                self.assertEqual(
                    [json.loads(line) for line in
                     (root / entry["jsonl"]).read_text(encoding="utf-8").splitlines()],
                    records,
                )
                # No sidecar table is written at all for these shapes.
                self.assertEqual(
                    sorted(path.name for path in (root / "tables").glob("*")), []
                )


class StageHistoryExportTests(TestCase):
    """``_export_stage_history``: summary alignment and unusable stage columns."""

    def test_stage_history_detection_requires_parallel_cell_arrays(self) -> None:
        cases = [
            ("empty list", [], False),
            ("non dict records", [1, 2], False),
            ("dict without cell_ids", [{"value_by_cell": [1.0]}], False),
            ("cell_ids not a list", [{"cell_ids": 3, "value_by_cell": [1.0]}], False),
            ("cell_ids without by_cell", [{"cell_ids": [0]}], False),
            ("full stage record", [{"cell_ids": [0], "value_by_cell": [1.0]}], True),
        ]
        for label, records, expected in cases:
            with self.subTest(label):
                self.assertIs(_is_stage_history(records), expected)

    def test_late_summary_columns_backfill_and_mixed_ones_move_to_metadata(self) -> None:
        records = [
            {
                "cell_ids": [0, 1],
                "value_by_cell": [1.0, 2.0],
                "phase_by_cell": ["wet", "dry"],
                "mean": 1.0,
                "nested_meta": {"src": "a"},
            },
            {
                "cell_ids": [0, 1],
                "value_by_cell": [3.0, 4.0],
                "phase_by_cell": ["dry", "dry"],
                "mean": 2.0,
                "label": "late",
            },
            {"cell_ids": [0], "value_by_cell": [5.0], "phase_by_cell": ["wet"], "mean": "oops"},
            {"cell_ids": [0, 1], "value_by_cell": [9.0], "phase_by_cell": ["wet"]},
        ]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _export_stage_history("hist", records, root / "tables", root / "events", manifest)

            history = manifest["stage_histories"]["hist"]
            self.assertEqual(history["stage_count"], 4)
            self.assertEqual(history["per_cell_fields"], ["phase", "value"])
            self.assertEqual(history["row_count"], 7)
            self.assertEqual(
                history["skipped_summary_fields"],
                {
                    "mean": "mixed scalar types retained in manifest stage metadata",
                    "nested_meta": "non-scalar stage metadata retained in stage extras",
                },
            )
            self.assertEqual(
                manifest["layers"],
                [
                    {
                        "id": "hist/phase",
                        "source": "hist",
                        "name": "phase",
                        "kind": "categorical_stage",
                        "stage_count": 4,
                        "categories": ["dry", "wet"],
                    },
                    {
                        "id": "hist/value",
                        "source": "hist",
                        "name": "value",
                        "kind": "numeric_stage",
                        "stage_count": 4,
                        "stats": {"min": 1.0, "max": 5.0, "p2": 1.0, "p98": 4.0},
                    },
                ],
            )
            extras = [
                json.loads(line)
                for line in (root / history["extras_jsonl"]).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                extras,
                [
                    {"stage_idx": 0, "cell_ids": [0, 1], "nested_meta": {"src": "a"}},
                    {"stage_idx": 1, "cell_ids": [0, 1], "nested_meta": None},
                    {"stage_idx": 2, "cell_ids": [0], "nested_meta": None},
                    {"stage_idx": 3, "cell_ids": [0, 1], "nested_meta": None},
                ],
            )
            # The mixed column is gone from Parquet but preserved per stage.
            self.assertEqual(
                [stage.get("mean") for stage in history["stages"]], [1.0, 2.0, "oops", None]
            )

            summary = _read_parquet(root / history["stages_parquet"])
            self.assertEqual(sorted(summary), ["label", "stage_idx"])
            self.assertEqual(summary["stage_idx"], [0, 1, 2, 3])
            self.assertEqual(summary["label"], [None, "late", None, None])

            stage_cells = _read_parquet(root / history["stage_cells_parquet"])
            self.assertEqual(stage_cells["stage_idx"], [0, 0, 1, 1, 2, 3, 3])
            self.assertEqual(stage_cells["cell_id"], [0, 1, 0, 1, 0, 0, 1])
            # The final stage's ragged arrays are padded rather than misaligned.
            self.assertEqual(stage_cells["value"], [1.0, 2.0, 3.0, 4.0, 5.0, None, None])
            self.assertEqual(
                stage_cells["phase"], ["wet", "dry", "dry", "dry", "wet", None, None]
            )

    def test_stage_columns_that_cannot_become_layers_are_recorded_and_kept(self) -> None:
        cell_ids = list(range(65))
        records = [
            {
                "cell_ids": cell_ids,
                "phase_by_cell": [f"p{index}" for index in cell_ids],
                "void_by_cell": [float("nan")] * 65,
                "nested_by_cell": [{"a": index} for index in cell_ids],
            }
        ]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _export_stage_history("hist", records, root / "tables", root / "events", manifest)

            history = manifest["stage_histories"]["hist"]
            self.assertEqual(history["per_cell_fields"], ["phase", "void"])
            self.assertEqual(
                history["skipped_per_cell_fields"],
                {"nested": "empty or mixed non-scalar stage field retained in stage extras"},
            )
            self.assertEqual(
                history["skipped_layers"],
                {
                    "phase": "more than 64 categories (column kept in stage parquet)",
                    "void": "no finite values (column kept in the stage-cells parquet)",
                },
            )
            self.assertEqual(manifest["layers"], [])

            stage_cells = _read_parquet(root / history["stage_cells_parquet"])
            self.assertEqual(stage_cells["phase"][64], "p64")

            extras = [
                json.loads(line)
                for line in (root / history["extras_jsonl"]).read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(extras), 1)
            self.assertEqual(extras[0]["stage_idx"], 0)
            self.assertEqual(extras[0]["cell_ids"], cell_ids)
            self.assertEqual(extras[0]["nested_by_cell"][7], {"a": 7})


class MeshExportTests(TestCase):
    """``_export_mesh`` and the projection helpers behind the GPU buffers."""

    def test_non_contiguous_cell_ids_are_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir:
            manifest = _blank_manifest()
            with self.assertRaisesRegex(
                ValueError, r"^debug export requires contiguous cell ids 0\.\.n-1$"
            ):
                _export_mesh(
                    [{"id": 0}, {"id": 2}], Path(temp_dir) / "mesh", manifest
                )

    def test_mesh_normalizes_positions_and_counts_cells_without_rings(self) -> None:
        cells = [
            {
                "id": 0,
                "lat_deg": 0.0,
                "lon_deg": 0.0,
                "position_3d": [2.0, 0.0, 0.0],
                "boundary_ring": _ring(0.0, 0.0),
            },
            # Two corners is one short of a drawable polygon.
            {"id": 1, "lat_deg": 5.0, "lon_deg": 5.0, "boundary_ring": [[0.0, 0.0], [1.0, 1.0]]},
            {
                "id": 2,
                "lat_deg": 0.0,
                "lon_deg": 0.0,
                "position_3d": [0.0, 0.0, 0.0],
                "boundary_ring": _ring(20.0, 20.0),
            },
            {"id": 3, "lat_deg": 0.0, "lon_deg": 90.0, "boundary_ring": _ring(0.0, 90.0)},
            # A boundary ring that is not a list at all.
            {"id": 4, "lat_deg": 1.0, "lon_deg": 1.0, "boundary_ring": "0,0 1,1 2,2"},
            # A position_3d of the wrong arity must not be used as a vertex.
            {
                "id": 5,
                "lat_deg": 0.0,
                "lon_deg": -90.0,
                "position_3d": [1.0, 0.0],
                "boundary_ring": _ring(0.0, -90.0),
            },
        ]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            mesh_dir = Path(temp_dir) / "mesh"
            info = _export_mesh(cells, mesh_dir, manifest)

            self.assertEqual(info["vertex_count"], 16)
            self.assertEqual(info["triangle_count"], 12)
            self.assertEqual(info["cell_count"], 6)
            self.assertEqual(info["cells_without_ring"], 2)
            self.assertIs(manifest["mesh"], info)
            self.assertEqual(json.loads((mesh_dir / "mesh.json").read_text(encoding="utf-8")), info)

            positions = struct.unpack("<48f", (mesh_dir / "positions.f32").read_bytes())
            # position_3d is normalized to the unit sphere ...
            self.assertEqual(positions[0:3], (1.0, 0.0, 0.0))
            # ... a degenerate zero vector is left at the origin ...
            self.assertEqual(positions[12:15], (0.0, 0.0, 0.0))
            # ... and a cell without a usable position_3d falls back to lat/lon.
            for component, expected in zip(positions[24:27], (0.0, 1.0, 0.0)):
                self.assertAlmostEqual(component, expected, places=6)
            for component, expected in zip(positions[36:39], (0.0, -1.0, 0.0)):
                self.assertAlmostEqual(component, expected, places=6)

            cell_ids = struct.unpack("<16I", (mesh_dir / "cell_ids.u32").read_bytes())
            self.assertEqual(cell_ids, (0, 0, 0, 0, 2, 2, 2, 2, 3, 3, 3, 3, 5, 5, 5, 5))
            indices = struct.unpack("<36I", (mesh_dir / "indices.u32").read_bytes())
            self.assertEqual(
                indices,
                (
                    0, 1, 2, 0, 2, 3, 0, 3, 1,
                    4, 5, 6, 4, 6, 7, 4, 7, 5,
                    8, 9, 10, 8, 10, 11, 8, 11, 9,
                    12, 13, 14, 12, 14, 15, 12, 15, 13,
                ),
            )

            # The 2D projection buffers carry one xy pair per vertex.
            equirect = struct.unpack("<32f", (mesh_dir / "pos_equirect.f32").read_bytes())
            mollweide = struct.unpack("<32f", (mesh_dir / "pos_mollweide.f32").read_bytes())
            # Cell 0: centre at (0, 0), then the ring corners (0,0), (0,1), (1,0).
            self.assertEqual(equirect[0:4], (0.0, 0.0, 0.0, 0.0))
            self.assertAlmostEqual(equirect[4], 1.0 / 180.0, places=6)
            self.assertEqual(equirect[5], 0.0)
            self.assertEqual(equirect[6], 0.0)
            self.assertAlmostEqual(equirect[7], 1.0 / 90.0, places=6)
            # Cell 3's centre sits on the equator a quarter turn east, cell 5's west.
            self.assertAlmostEqual(equirect[16], 0.5, places=6)
            self.assertEqual(equirect[17], 0.0)
            self.assertAlmostEqual(equirect[24], -0.5, places=6)
            self.assertEqual(equirect[25], 0.0)
            # On the equator Mollweide degenerates to the same scaled longitude.
            self.assertEqual(mollweide[0:4], (0.0, 0.0, 0.0, 0.0))
            self.assertAlmostEqual(mollweide[4], 1.0 / 180.0, places=6)
            self.assertAlmostEqual(mollweide[16], 0.5, places=6)
            self.assertAlmostEqual(mollweide[24], -0.5, places=6)

    def test_projection_buffers_wrap_ring_longitudes_toward_the_cell_centre(self) -> None:
        cells = [
            {
                "id": 0,
                "lat_deg": 0.0,
                "lon_deg": 179.0,
                "boundary_ring": [[0.0, 179.0], [0.0, -179.0], [1.0, 179.0]],
            }
        ]
        manifest = _blank_manifest()
        with TemporaryDirectory() as temp_dir:
            mesh_dir = Path(temp_dir) / "mesh"
            _export_mesh(cells, mesh_dir, manifest)

            equirect = struct.unpack("<8f", (mesh_dir / "pos_equirect.f32").read_bytes())
            mollweide = struct.unpack("<8f", (mesh_dir / "pos_mollweide.f32").read_bytes())
            # The -179 corner is re-expressed as +181 so the polygon does not
            # stretch back across the whole map.
            self.assertAlmostEqual(equirect[0], 179.0 / 180.0, places=6)
            self.assertAlmostEqual(equirect[2], 179.0 / 180.0, places=6)
            self.assertAlmostEqual(equirect[4], 181.0 / 180.0, places=6)
            self.assertAlmostEqual(mollweide[4], 181.0 / 180.0, places=6)

            # The 3D positions keep the unwrapped longitude.
            positions = struct.unpack("<12f", (mesh_dir / "positions.f32").read_bytes())
            expected = (
                math.cos(math.radians(-179.0)),
                math.sin(math.radians(-179.0)),
                0.0,
            )
            for component, want in zip(positions[6:9], expected):
                self.assertAlmostEqual(component, want, places=6)

    def test_mollweide_projection_at_and_next_to_the_poles(self) -> None:
        self.assertEqual(_mollweide_normalized(90.0, 0.0), (0.0, 1.0))
        self.assertEqual(_mollweide_normalized(-90.0, 0.0), (0.0, -1.0))

        # Just outside the pole clamp the Newton denominator underflows, so the
        # solver must bail out with theta still equal to the latitude.
        near_pole_deg = 90.0 - 1e-6
        x_value, y_value = _mollweide_normalized(near_pole_deg, 180.0)
        self.assertEqual(y_value, math.sin(math.radians(near_pole_deg)))
        self.assertAlmostEqual(x_value, math.cos(math.radians(near_pole_deg)), places=12)

        # A mid-latitude point does iterate, and must satisfy the Mollweide
        # auxiliary-angle identity 2*theta + sin(2*theta) == pi * sin(lat).
        x_mid, y_mid = _mollweide_normalized(45.0, 90.0)
        theta = math.asin(y_mid)
        self.assertAlmostEqual(
            2.0 * theta + math.sin(2.0 * theta),
            math.pi * math.sin(math.radians(45.0)),
            places=12,
        )
        self.assertAlmostEqual(x_mid, 0.5 * math.cos(theta), places=12)


class VtuExportTests(TestCase):
    """``_write_vtu_stages``: the ParaView geometry path."""

    def test_export_is_skipped_when_there_is_nothing_to_draw(self) -> None:
        ring_cell = {"id": 0, "boundary_ring": _ring(0.0, 0.0)}
        stage = {"cell_ids": [0], "elevation_m_by_cell": [1.0]}
        cases = [
            ("no history key", {"cells": [ring_cell]}),
            # A non-empty mapping: only the type check can reject this one.
            (
                "history keyed by stage id",
                {"cells": [ring_cell], "hydrologic_water_budget_history": {"0": stage}},
            ),
            ("empty history", {"cells": [ring_cell], "hydrologic_water_budget_history": []}),
            ("no cells", {"cells": [], "hydrologic_water_budget_history": [stage]}),
            (
                "no usable rings",
                {
                    "cells": [{"id": 0, "boundary_ring": [[0.0, 0.0], [1.0, 1.0]]}],
                    "hydrologic_water_budget_history": [stage],
                },
            ),
        ]
        for label, world in cases:
            with self.subTest(label), TemporaryDirectory() as temp_dir:
                vtu_dir = Path(temp_dir) / "vtu"
                manifest: dict = {}
                _write_vtu_stages(world, vtu_dir, manifest, elevation_exaggeration=1.0)
                self.assertEqual(manifest, {})
                self.assertFalse(vtu_dir.exists())
                self.assertFalse((Path(temp_dir) / "world.pvd").exists())

    def test_stage_geometry_uses_planet_radius_and_survives_unusable_values(self) -> None:
        world = {
            "planet_parameters": {"radius_km": 1.0},
            "cells": [
                {"id": 0, "boundary_ring": _ring(0.0, 0.0)},
                {"id": 1, "boundary_ring": _ring(10.0, 10.0)},
                {"id": 2, "boundary_ring": _ring(20.0, 20.0)},
            ],
            "hydrologic_water_budget_history": [
                {
                    "cell_ids": [0, 1],
                    "elevation_m_by_cell": [1000.0, 0.0],
                    "flux_by_cell": [10**400, 2.5],
                    "short_by_cell": [1.0],
                    "void_by_cell": [float("nan"), None],
                    "phase_by_cell": ["wet", "dry"],
                },
                {
                    "cell_ids": [0, 1],
                    "elevation_m_by_cell": ["bad", float("nan")],
                    "flux_by_cell": [1.0, 2.0],
                    "short_by_cell": [1.0],
                    "void_by_cell": [0.0, 0.0],
                },
            ],
        }
        manifest: dict = {}
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_vtu_stages(world, root / "vtu", manifest, elevation_exaggeration=1.0)

            self.assertEqual(
                manifest["paraview"],
                {"pvd": "world.pvd", "stage_count": 2, "elevation_exaggeration": 1.0},
            )
            stage0 = root / "vtu" / "stage_0000.vtu"
            stage1 = root / "vtu" / "stage_0001.vtu"

            header = stage0.read_text(encoding="utf-8")
            self.assertIn('<Piece NumberOfPoints="9" NumberOfCells="3">', header)
            self.assertIn('Name="offsets" format="ascii">\n3 6 9\n', header)
            self.assertIn('Name="types" format="ascii">\n7 7 7\n', header)
            self.assertIn('Name="connectivity" format="ascii">\n0 1 2 3 4 5 6 7 8\n', header)

            # radius_km=1.0 turns a 1000 m elevation into a doubled radius.
            points = _points(stage0)
            self.assertAlmostEqual(math.dist((0.0, 0.0, 0.0), points[0]), 2.0, places=5)
            self.assertAlmostEqual(math.dist((0.0, 0.0, 0.0), points[3]), 1.0, places=5)
            # Cell 2 is absent from the stage, so it stays on the unit sphere.
            self.assertAlmostEqual(math.dist((0.0, 0.0, 0.0), points[6]), 1.0, places=5)

            arrays = _data_arrays(stage0)
            # The string-valued stage column is the only one left out.
            self.assertEqual(sorted(arrays), ["elevation_m", "flux", "short", "void"])
            self.assertEqual(arrays["elevation_m"], "1000.000000 0.000000 0")
            # Overflowing, out-of-range and missing rows all fall back to zero.
            self.assertEqual(arrays["flux"], "0 2.500000 0")
            self.assertEqual(arrays["short"], "1.000000 0 0")
            self.assertEqual(arrays["void"], "nan 0 0")

            # An uncastable and a non-finite elevation both collapse to no relief.
            for point in _points(stage1):
                self.assertAlmostEqual(math.dist((0.0, 0.0, 0.0), point), 1.0, places=5)

            pvd = (root / "world.pvd").read_text(encoding="utf-8")
            self.assertIn(
                '<DataSet timestep="0" group="" part="0" file="vtu/stage_0000.vtu"/>', pvd
            )
            self.assertIn(
                '<DataSet timestep="1" group="" part="0" file="vtu/stage_0001.vtu"/>', pvd
            )

    def test_unusable_planet_radius_falls_back_to_earth(self) -> None:
        cases = [
            ("missing planet_parameters", None),
            ("planet_parameters not a dict", "6371"),
            ("radius missing", {}),
            ("radius not numeric", {"radius_km": "6371"}),
            ("radius nan", {"radius_km": float("nan")}),
            ("radius zero", {"radius_km": 0.0}),
            ("radius negative", {"radius_km": -100.0}),
        ]
        for label, planet in cases:
            with self.subTest(label), TemporaryDirectory() as temp_dir:
                world = {
                    "cells": [{"id": 0, "boundary_ring": _ring(0.0, 0.0)}],
                    "hydrologic_water_budget_history": [
                        {"cell_ids": [0], "elevation_m_by_cell": [6371000.0]}
                    ],
                }
                if planet is not None:
                    world["planet_parameters"] = planet
                manifest: dict = {}
                root = Path(temp_dir)
                _write_vtu_stages(world, root / "vtu", manifest, elevation_exaggeration=1.0)
                point = _points(root / "vtu" / "stage_0000.vtu")[0]
                # 6371 km of relief on a 6371 km radius doubles the radius exactly.
                self.assertAlmostEqual(math.dist((0.0, 0.0, 0.0), point), 2.0, places=5)


class ExportDebugCacheTests(TestCase):
    """The public entry point: manifest assembly, options and failure modes."""

    def test_manifest_catalogs_every_section_of_the_payload(self) -> None:
        world = _tiny_world()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "world.json"
            payload = b'{"name": "tiny"}'
            source.write_bytes(payload)
            out_dir = root / "cache"

            manifest = export_debug_cache(world, out_dir, source_path=source)

            self.assertEqual(manifest["format"], FORMAT_NAME)
            self.assertEqual(manifest["version"], FORMAT_VERSION)
            self.assertEqual(
                manifest["world"],
                {
                    "name": "tiny",
                    "schema_version": 2,
                    "mesh_backend": "test",
                    "generation_scope": "partial",
                    "cell_count": 2,
                },
            )
            # Digest and length are pinned literals, not recomputations, so a
            # different payload cannot quietly agree with the manifest.
            self.assertEqual(
                manifest["source"],
                {
                    "path": str(source),
                    "bytes": 16,
                    "sha256": "cea20a1e01094dac1f23f06d0e348bb48cf1c69f0d84d80283f10ade762aaf13",
                },
            )
            self.assertEqual(hashlib.sha256(payload).hexdigest(), manifest["source"]["sha256"])
            # Top-level scalars are inlined; a non-finite one is JSON-sanitised.
            self.assertEqual(
                manifest["scalars"],
                {
                    "name": "tiny",
                    "schema_version": 2,
                    "mesh_backend": "test",
                    "generation_scope": "partial",
                    "seed": 7,
                    "calibrated": True,
                    "nan_scalar": None,
                },
            )
            self.assertEqual(
                manifest["skipped_sections"],
                {"empty_family": "empty list", "unhandled": "unhandled type set"},
            )
            self.assertEqual(
                manifest["sections"],
                ["loose_numbers", "planet_parameters", "simulation_clock"],
            )
            sections = json.loads((out_dir / "sections.json").read_text(encoding="utf-8"))
            self.assertEqual(sections["loose_numbers"], [1, 2, 3])
            self.assertEqual(sections["planet_parameters"], {"radius_km": 6371.0})

            self.assertEqual(list(manifest["stage_histories"]), ["hydrologic_water_budget_history"])
            self.assertEqual(manifest["families"]["settlements"]["kind"], "parquet")
            self.assertEqual(manifest["families"]["settlements"]["row_count"], 1)
            self.assertEqual(
                _read_parquet(out_dir / manifest["families"]["settlements"]["parquet"]),
                {"id": [0], "cell_id": [1], "name": ["port"], "population": [120]},
            )
            self.assertEqual(
                manifest["simulation_clock"],
                {
                    "clock_type": "test_clock",
                    "time_unit": "model_step",
                    "stage_count": 2,
                    "initial_stage_id": None,
                    "current_stage_id": None,
                    "final_stage_id": None,
                    "feedback_recompute_count": None,
                    "hydrologic_water_budget_recompute_count": None,
                },
            )
            self.assertEqual(manifest["paraview"]["stage_count"], 2)

            on_disk = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(on_disk, manifest)

    def test_optional_manifest_blocks_are_absent_when_the_payload_lacks_them(self) -> None:
        world = _tiny_world()
        del world["simulation_clock"]
        with TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "cache"
            manifest = export_debug_cache(world, out_dir, include_vtu=False)

            # No source_path argument and no clock in the payload.
            self.assertNotIn("source", manifest)
            self.assertNotIn("simulation_clock", manifest)
            self.assertNotIn("paraview", manifest)
            self.assertEqual(manifest["world"]["cell_count"], 2)

    def test_family_filenames_stay_distinct_when_keys_slugify_alike(self) -> None:
        world = _tiny_world()
        long_key = "orbital resonance events " * 5
        world["events!"] = [{"id": 0, "kind": "a"}]
        world["events?"] = [{"id": 1, "kind": "b"}]
        world["..."] = [{"id": 2, "kind": "c"}]
        world[long_key] = [{"id": 3, "kind": "d"}]
        with TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "cache"
            manifest = export_debug_cache(world, out_dir, include_vtu=False)

            paths = {name: entry["parquet"] for name, entry in manifest["families"].items()}
            self.assertEqual(len(set(paths.values())), len(paths))
            # Punctuation collapses to the same slug; the digest keeps them apart.
            self.assertEqual(
                paths["events!"],
                f"tables/events-{hashlib.sha256(b'events!').hexdigest()}.parquet",
            )
            self.assertEqual(
                paths["events?"],
                f"tables/events-{hashlib.sha256(b'events?').hexdigest()}.parquet",
            )
            # An all-punctuation key falls back to the "entry" slug ...
            self.assertEqual(
                paths["..."],
                f"tables/entry-{hashlib.sha256(b'...').hexdigest()}.parquet",
            )
            # ... and an over-long one is truncated to 72 slug characters.
            slug = re.sub(r"[^A-Za-z0-9._-]+", "_", long_key).strip("._-")[:72]
            self.assertEqual(len(slug), 72)
            self.assertEqual(
                paths[long_key],
                f"tables/{slug}-{hashlib.sha256(long_key.encode()).hexdigest()}.parquet",
            )
            expected_rows = {"events!": "a", "events?": "b", "...": "c", long_key: "d"}
            for name, kind in expected_rows.items():
                self.assertEqual(_read_parquet(out_dir / paths[name])["kind"], [kind])

    def test_worlds_without_cells_are_rejected_before_anything_is_written(self) -> None:
        message = re.escape(
            "world payload has no cells; generate with output.include_cells enabled"
        )
        for label, world in [
            ("missing key", {}),
            ("empty list", {"cells": []}),
            ("wrong type", {"cells": {"0": {}}}),
        ]:
            with self.subTest(label), TemporaryDirectory() as temp_dir:
                out_dir = Path(temp_dir) / "cache"
                with self.assertRaisesRegex(ValueError, message):
                    export_debug_cache(world, out_dir)
                self.assertFalse(out_dir.exists())

    def test_include_vtu_toggles_the_whole_paraview_companion(self) -> None:
        world = _tiny_world()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            without = export_debug_cache(world, root / "off", include_vtu=False)
            self.assertNotIn("paraview", without)
            self.assertFalse((root / "off" / "vtu").exists())
            self.assertFalse((root / "off" / "world.pvd").exists())

            with_vtu = export_debug_cache(world, root / "on", include_vtu=True)
            self.assertEqual(
                with_vtu["paraview"],
                {"pvd": "world.pvd", "stage_count": 2, "elevation_exaggeration": 30.0},
            )
            self.assertEqual(
                sorted(path.name for path in (root / "on" / "vtu").iterdir()),
                ["stage_0000.vtu", "stage_0001.vtu"],
            )
            # Everything else is identical with or without ParaView output.
            self.assertEqual(with_vtu["mesh"], without["mesh"])
            self.assertEqual(with_vtu["layers"], without["layers"])

    def test_elevation_exaggeration_only_scales_the_vtu_radius(self) -> None:
        world = _tiny_world()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            flat = export_debug_cache(world, root / "flat", elevation_exaggeration=0.0)
            tall = export_debug_cache(world, root / "tall", elevation_exaggeration=100.0)

            self.assertEqual(flat["paraview"]["elevation_exaggeration"], 0.0)
            self.assertEqual(tall["paraview"]["elevation_exaggeration"], 100.0)
            self.assertEqual(flat["mesh"], tall["mesh"])

            for point in _points(root / "flat" / "vtu" / "stage_0000.vtu"):
                self.assertAlmostEqual(math.dist((0.0, 0.0, 0.0), point), 1.0, places=6)

            expected = 1.0 + 100.0 * 1000.0 / (6371.0 * 1000.0)
            tall_points = _points(root / "tall" / "vtu" / "stage_0000.vtu")
            for point in tall_points[:3]:
                self.assertAlmostEqual(math.dist((0.0, 0.0, 0.0), point), expected, places=5)

    def test_export_reuses_a_populated_directory_without_clearing_it(self) -> None:
        world = _tiny_world()
        with TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "cache"
            (out_dir / "tables").mkdir(parents=True)
            (out_dir / "keep.txt").write_text("hand written", encoding="utf-8")
            (out_dir / "tables" / "stale.parquet").write_bytes(b"stale")
            (out_dir / "manifest.json").write_text('{"format": "older"}', encoding="utf-8")

            manifest = export_debug_cache(world, out_dir, include_vtu=False)

            self.assertEqual(manifest["format"], FORMAT_NAME)
            self.assertEqual(
                json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))["format"],
                FORMAT_NAME,
            )
            # Unrelated content is preserved rather than wiped.
            self.assertEqual((out_dir / "keep.txt").read_text(encoding="utf-8"), "hand written")
            self.assertEqual((out_dir / "tables" / "stale.parquet").read_bytes(), b"stale")
            self.assertTrue((out_dir / "tables" / "cells.parquet").is_file())

    def test_unusable_output_locations_surface_the_os_error(self) -> None:
        if os.geteuid() == 0:
            raise SkipTest("root bypasses directory permission bits")
        world = _tiny_world()
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            blocked = root / "blocked"
            blocked.mkdir()
            occupied = root / "occupied"
            occupied.write_text("not a directory", encoding="utf-8")

            blocked.chmod(0o500)
            try:
                with self.assertRaisesRegex(
                    PermissionError,
                    rf"Permission denied: {re.escape(repr(str(blocked / 'cache')))}$",
                ):
                    export_debug_cache(world, blocked / "cache")
                self.assertFalse((blocked / "cache").exists())
            finally:
                blocked.chmod(0o700)

            with self.assertRaisesRegex(
                FileExistsError, rf"File exists: {re.escape(repr(str(occupied)))}$"
            ):
                export_debug_cache(world, occupied)
            self.assertEqual(occupied.read_text(encoding="utf-8"), "not a directory")

    def test_generated_world_exports_a_self_consistent_cache(self) -> None:
        world = worlds.cached_world_readonly("replay_128")
        cells = world["cells"]
        with TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "cache"
            manifest = export_debug_cache(world, out_dir)

            self.assertEqual(manifest["world"]["cell_count"], len(cells))
            self.assertEqual(manifest["world"]["name"], world["name"])
            # The key is absent from generated payloads, so the default applies.
            self.assertNotIn("generation_scope", world)
            self.assertEqual(manifest["world"]["generation_scope"], "full")

            cells_table = _read_parquet(out_dir / "tables" / "cells.parquet")
            self.assertEqual(manifest["cells"]["row_count"], len(cells))
            self.assertEqual(cells_table["id"], [cell["id"] for cell in cells])
            self.assertEqual(
                cells_table["elevation_m"], [float(cell["elevation_m"]) for cell in cells]
            )

            mesh = manifest["mesh"]
            expected_vertices = sum(1 + len(cell["boundary_ring"]) for cell in cells)
            expected_triangles = sum(len(cell["boundary_ring"]) for cell in cells)
            self.assertEqual(mesh["cells_without_ring"], 0)
            self.assertEqual(mesh["vertex_count"], expected_vertices)
            self.assertEqual(mesh["triangle_count"], expected_triangles)
            self.assertEqual(
                (out_dir / "mesh" / "positions.f32").stat().st_size, expected_vertices * 3 * 4
            )
            self.assertEqual(
                (out_dir / "mesh" / "cell_ids.u32").stat().st_size, expected_vertices * 4
            )
            self.assertEqual(
                (out_dir / "mesh" / "indices.u32").stat().st_size, expected_triangles * 3 * 4
            )

            monthly = _read_parquet(out_dir / "tables" / "cells_monthly.parquet")
            self.assertEqual(manifest["monthly"]["row_count"], 12 * len(cells))
            self.assertIn("temperature_monthly_c", manifest["monthly"]["fields"])
            self.assertEqual(
                monthly["temperature_monthly_c"][5 * 12 + 3],
                float(cells[5]["temperature_monthly_c"][3]),
            )

            history = world["hydrologic_water_budget_history"]
            stage_entry = manifest["stage_histories"]["hydrologic_water_budget_history"]
            self.assertEqual(stage_entry["stage_count"], len(history))
            self.assertEqual(
                stage_entry["row_count"], sum(len(record["cell_ids"]) for record in history)
            )
            self.assertEqual(manifest["paraview"]["stage_count"], len(history))
            self.assertEqual(
                (out_dir / "world.pvd").read_text(encoding="utf-8").count("<DataSet "),
                len(history),
            )

            # Every catalogued artifact exists and every layer id is unique.
            referenced = [stage_entry["stage_cells_parquet"], stage_entry["stages_parquet"]]
            for entry in manifest["families"].values():
                referenced.extend(
                    entry[key] for key in ("parquet", "jsonl", "scalars_parquet") if key in entry
                )
            for relative in referenced:
                self.assertTrue((out_dir / relative).is_file(), relative)
            layer_ids = [layer["id"] for layer in manifest["layers"]]
            self.assertEqual(len(layer_ids), len(set(layer_ids)))
            self.assertIn("cells/elevation_m", layer_ids)

            self.assertEqual(
                json.loads((out_dir / "manifest.json").read_text(encoding="utf-8")), manifest
            )
