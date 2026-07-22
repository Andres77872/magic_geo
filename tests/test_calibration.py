from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest import TestCase
from zipfile import ZIP_DEFLATED, ZipFile

from typer.testing import CliRunner

from magic_geo.calibration import (
    CalibrationError,
    derive_calibration_targets,
    evaluate_calibration_targets,
    load_calibration_sources,
    load_calibration_targets,
    score_range,
    write_calibration_markdown,
    write_target_derivation_markdown,
)
from magic_geo.cli import app
from magic_geo.ensemble_calibration import load_calibration_ensemble_manifest

from support.builders import build_geotiff
from support.shapefiles import (
    write_dbf,
    write_dbf_table,
    write_opendap_ascii_grid,
    write_polygon_shapefile,
    write_polyline_shapefile,
    write_vector_shapefile,
)

_ASCII_GRID_HEADER = [
    "ncols 3",
    "nrows 2",
    "xllcorner 0",
    "yllcorner 0",
    "cellsize 1",
    "NODATA_value -9999",
]


def _source(path: Path, **extra: Any) -> dict[str, Any]:
    """A minimal calibration source for ``derive_calibration_targets``."""
    source: dict[str, Any] = {
        "dataset": "unit_dataset",
        "layer": "unit_layer",
        "metric": "unit_metric",
        "path": str(path),
    }
    source.update(extra)
    return source


def _derive_one(path: Path, **extra: Any) -> dict[str, Any]:
    return derive_calibration_targets([_source(path, **extra)])["targets"][0]


def _write_ascii_grid(path: Path, header: list[str], data_lines: list[str]) -> None:
    path.write_text("\n".join([*header, *data_lines]) + "\n", encoding="utf-8")


def _patch_bytes(data: bytes, patches: dict[int, bytes]) -> bytes:
    output = bytearray(data)
    for offset, raw in patches.items():
        output[offset:offset + len(raw)] = raw
    return bytes(output)


def _rewrite_shapefile(
    path: Path,
    *,
    content: bytes | None = None,
    content_patches: dict[int, bytes] | None = None,
    header_patches: dict[int, bytes] | None = None,
    content_length_words: int | None = None,
    trailing: bytes = b"",
) -> None:
    """Rewrite a shapefile written by ``write_vector_shapefile`` with defects.

    The shared writer only emits well-formed files, so the malformed-record
    tests start from one and patch the header, the record header, or the
    single record's content in place.
    """
    data = path.read_bytes()
    body = bytearray(data[108:] if content is None else content)
    if content_patches:
        body = bytearray(_patch_bytes(bytes(body), content_patches))
    header = bytearray(data[:100])
    words = len(body) // 2 if content_length_words is None else content_length_words
    struct.pack_into(">i", header, 24, (100 + 8 + len(body) + len(trailing)) // 2)
    if header_patches:
        header = bytearray(_patch_bytes(bytes(header), header_patches))
    path.write_bytes(
        bytes(header) + struct.pack(">2i", 1, words) + bytes(body) + trailing
    )


def _write_worldclim_archive(
    path: Path,
    monthly_values: dict[int, list[float]],
    *,
    variable: str = "tavg",
    nodata: float | None = -9999.0,
    grid_shape: tuple[int, int] = (4, 4),
    month_grid_shape: dict[int, tuple[int, int]] | None = None,
    empty_months: tuple[int, ...] = (),
    duplicate_months: tuple[int, ...] = (),
) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for month, values in monthly_values.items():
            member = f"wc2.1_10m_{variable}_{month:02}.tif"
            if month in empty_months:
                archive.writestr(member, b"")
                continue
            width, height = (month_grid_shape or {}).get(month, grid_shape)
            payload = build_geotiff(
                list(values),
                width,
                height,
                bits_per_sample=32,
                sample_format=3,
                compression=8,
                nodata=nodata,
            )
            archive.writestr(member, payload)
            if month in duplicate_months:
                archive.writestr(f"nested/{member}", payload)


_HYDRORIVERS_FIELDS = ["NEXT_DOWN", "ENDORHEIC", "ORD_CLAS", "UPLAND_SKM", "DIST_UP_KM"]


def _hydrorivers_dbf_bytes(root: Path, columns: dict[str, list[float | None]]) -> bytes:
    staging = root / "_hydrorivers_staging.dbf"
    write_dbf_table(staging, columns)
    return staging.read_bytes()


def _write_hydrorivers_archive(
    path: Path,
    dbf_payloads: dict[str, bytes],
) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for member, payload in dbf_payloads.items():
            archive.writestr(member, payload)


def _hydrorivers_source(path: Path, **extra: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "metric": "hydrorivers_hack_fitted_exponent",
        "world_metric": "exorheic_watershed_backbone_hack_fitted_exponent",
        "format": "hydrorivers_shapefile_zip",
        "statistic": "hydrorivers_hack_fitted_exponent",
        "tolerance_abs": 0.0,
    }
    options.update(extra)
    return _source(path, **options)


class CalibrationSourceTests(TestCase):
    def test_calibration_ensemble_reports_grouped_coverage_and_fit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            matrix_path = root / "matrix.json"
            target_path = root / "targets.json"
            output_path = root / "ensemble.json"
            summary_path = root / "ensemble.md"
            matrix_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "test_matrix",
                        "members": [
                            {
                                "id": "seed_1",
                                "seed": 1,
                                "cell_count": 128,
                                "groups": ["reference", "seed_sweep"],
                            },
                            {
                                "id": "seed_2",
                                "seed": 2,
                                "cell_count": 128,
                                "groups": ["seed_sweep"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            target_path.write_text(
                json.dumps(
                    {
                        "targets": [
                            {
                                "dataset": "Broad Contract",
                                "layer": "summary",
                                "metric": "ocean_fraction",
                                "target_min": 0.0,
                                "target_max": 1.0,
                            },
                            {
                                "dataset": "Impossible Contract",
                                "layer": "summary",
                                "metric": "mean_land_elevation_m",
                                "target_min": 1000000000.0,
                                "target_max": 1000000001.0,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            runner = CliRunner()
            result = runner.invoke(
                app,
                [
                    "calibrate-ensemble",
                    "--config",
                    "configs/earthlike_seed.yaml",
                    "--matrix",
                    str(matrix_path),
                    "--targets",
                    str(target_path),
                    "--output",
                    str(output_path),
                    "--summary",
                    str(summary_path),
                    "--require-all-metrics",
                ],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            report = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(report["report_type"], "calibration_ensemble_v1")
            self.assertEqual(report["summary"]["member_count"], 2)
            self.assertEqual(report["summary"]["target_count"], 2)
            self.assertEqual(report["summary"]["complete_member_count"], 2)
            self.assertTrue(report["summary"]["reference_matrix_complete"])
            self.assertEqual(report["summary"]["all_targets_passed_member_count"], 0)
            self.assertFalse(report["summary"]["reference_matrix_all_passed"])
            self.assertEqual([member["id"] for member in report["members"]], ["seed_1", "seed_2"])
            self.assertEqual(report["members"][0]["groups"], ["all", "reference", "seed_sweep"])
            metric_results = {metric["metric"]: metric for metric in report["metrics"]}
            self.assertEqual(metric_results["ocean_fraction"]["pass_count"], 2)
            self.assertEqual(metric_results["mean_land_elevation_m"]["pass_count"], 0)
            dataset_results = {dataset["dataset"]: dataset for dataset in report["datasets"]}
            self.assertEqual(
                dataset_results["Broad Contract"]["all_metrics_passed_member_count"],
                2,
            )
            self.assertEqual(
                dataset_results["Impossible Contract"]["all_metrics_passed_member_count"],
                0,
            )
            groups = {group["name"]: group for group in report["groups"]}
            self.assertEqual(groups["reference"]["member_count"], 1)
            self.assertEqual(groups["seed_sweep"]["member_count"], 2)
            self.assertEqual(len(report["provenance"]["base_config_sha256"]), 64)
            self.assertEqual(len(report["provenance"]["matrix_sha256"]), 64)
            self.assertIn("## Dataset Fit", summary_path.read_text(encoding="utf-8"))

            strict_result = runner.invoke(
                app,
                [
                    "calibrate-ensemble",
                    "--config",
                    "configs/earthlike_seed.yaml",
                    "--matrix",
                    str(matrix_path),
                    "--targets",
                    str(target_path),
                    "--output",
                    str(root / "strict.json"),
                    "--require-all-passed",
                ],
            )
            self.assertEqual(strict_result.exit_code, 1, strict_result.output)
            self.assertIn("failed members: seed_1, seed_2", strict_result.output)
            self.assertTrue((root / "strict.json").exists())
            self.assertEqual(
                output_path.read_bytes(),
                (root / "strict.json").read_bytes(),
            )

    def test_calibration_ensemble_rejects_duplicate_seed_resolution_coordinates(self) -> None:
        with TemporaryDirectory() as temp_dir:
            matrix_path = Path(temp_dir) / "matrix.json"
            matrix_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "name": "duplicate_matrix",
                        "members": [
                            {"id": "first", "seed": 7, "cell_count": 128},
                            {"id": "second", "seed": 7, "cell_count": 128},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(CalibrationError, "duplicates seed/cell_count"):
                load_calibration_ensemble_manifest(matrix_path)

    def test_derives_targets_from_ascii_grid_and_geojson(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raster = root / "worldclim_temperature.asc"
            raster.write_text(
                "\n".join(
                    [
                        "ncols 3",
                        "nrows 2",
                        "xllcorner 0",
                        "yllcorner 0",
                        "cellsize 1",
                        "NODATA_value -9999",
                        "10 12 14",
                        "16 -9999 18",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            vector = root / "natural_earth_coast.geojson"
            vector.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            {"type": "Feature", "properties": {"length_km": 100.0}, "geometry": None},
                            {"type": "Feature", "properties": {"length_km": 140.0}, "geometry": None},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manifest = root / "sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "dataset": "custom_worldclim",
                                "layer": "temperature",
                                "metric": "mean_temperature_c",
                                "world_metric": "global_mean_temperature_c",
                                "path": "worldclim_temperature.asc",
                                "format": "esri_ascii_grid",
                                "statistic": "mean",
                                "tolerance_abs": 1.0,
                            },
                            {
                                "dataset": "custom_natural_earth",
                                "layer": "coastline",
                                "metric": "coastline_feature_count",
                                "path": "natural_earth_coast.geojson",
                                "format": "geojson",
                                "statistic": "feature_count",
                                "tolerance_abs": 0.0,
                            },
                            {
                                "dataset": "custom_natural_earth",
                                "layer": "coastline",
                                "metric": "mean_coastline_length_km",
                                "path": "natural_earth_coast.geojson",
                                "format": "geojson",
                                "statistic": "mean",
                                "property": "length_km",
                                "tolerance_fraction": 0.10,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = derive_calibration_targets(load_calibration_sources(manifest))

        self.assertEqual(report["summary"]["derived_target_count"], 3)
        self.assertEqual(report["summary"]["mapped_target_count"], 1)
        self.assertEqual(report["summary"]["unique_world_metric_count"], 3)
        targets = {target["metric"]: target for target in report["targets"]}

        self.assertEqual(targets["global_mean_temperature_c"]["source_metric"], "mean_temperature_c")
        self.assertEqual(targets["global_mean_temperature_c"]["source_format"], "esri_ascii_grid")
        self.assertAlmostEqual(targets["global_mean_temperature_c"]["source_value"], 14.0)
        self.assertAlmostEqual(targets["global_mean_temperature_c"]["target_min"], 13.0)
        self.assertAlmostEqual(targets["global_mean_temperature_c"]["target_max"], 15.0)

        self.assertEqual(targets["coastline_feature_count"]["source_format"], "geojson")
        self.assertEqual(targets["coastline_feature_count"]["source_value"], 2.0)
        self.assertEqual(targets["coastline_feature_count"]["target_min"], 2.0)
        self.assertEqual(targets["coastline_feature_count"]["target_max"], 2.0)

        self.assertAlmostEqual(targets["mean_coastline_length_km"]["source_value"], 120.0)
        self.assertAlmostEqual(targets["mean_coastline_length_km"]["target_min"], 108.0)
        self.assertAlmostEqual(targets["mean_coastline_length_km"]["target_max"], 132.0)

        source_summaries = {summary["metric"]: summary for summary in report["source_summaries"]}
        self.assertEqual(source_summaries["mean_temperature_c"]["world_metric"], "global_mean_temperature_c")

    def test_calibration_coverage_and_strict_cli_gate(self) -> None:
        world = {
            "calibration_checks": [
                {"metric": "ocean_fraction", "value": 0.7},
                {"metric": "global_mean_temperature_c", "value": 12.0},
            ]
        }
        targets = [
            {
                "dataset": "coverage_test",
                "layer": "ocean",
                "metric": "ocean_fraction",
                "source_metric": "mean_ocean_mask_fraction",
                "target_min": 0.6,
                "target_max": 0.8,
            },
            {
                "dataset": "coverage_test",
                "layer": "coast",
                "metric": "coastal_land_fraction",
                "target_min": 0.2,
                "target_max": 0.5,
            },
        ]

        report = evaluate_calibration_targets(world, targets)
        summary = report["summary"]
        self.assertEqual(summary["external_calibration_evaluated_metric_count"], 1)
        self.assertEqual(summary["external_calibration_missing_metric_count"], 1)
        self.assertEqual(summary["external_calibration_metric_coverage_fraction"], 0.5)
        self.assertEqual(summary["external_calibration_pass_fraction"], 0.5)
        self.assertEqual(summary["external_calibration_evaluated_pass_fraction"], 1.0)
        self.assertFalse(summary["external_calibration_complete"])
        self.assertEqual(report["missing_world_metrics"], ["coastal_land_fraction"])
        self.assertIn("ocean_fraction", report["available_world_metrics"])

        with self.assertRaises(CalibrationError):
            evaluate_calibration_targets(
                world,
                [{**targets[0], "target_min": float("nan")}],
            )

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            world_path = root / "world.json"
            targets_path = root / "targets.json"
            output_path = root / "report.json"
            world_path.write_text(json.dumps(world), encoding="utf-8")
            targets_path.write_text(json.dumps({"targets": targets}), encoding="utf-8")

            result = CliRunner().invoke(
                app,
                [
                    "calibrate",
                    "--world",
                    str(world_path),
                    "--targets",
                    str(targets_path),
                    "--output",
                    str(output_path),
                    "--require-all-metrics",
                ],
            )

            self.assertEqual(result.exit_code, 1)
            self.assertTrue(output_path.exists())
            self.assertIn("coverage=0.500", result.output)
            self.assertIn("coastal_land_fraction", result.output)
            written = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(written["missing_world_metrics"], ["coastal_land_fraction"])

            fit_targets = [{**targets[0], "target_min": 0.1, "target_max": 0.2}]
            targets_path.write_text(json.dumps({"targets": fit_targets}), encoding="utf-8")
            fit_output_path = root / "fit-report.json"
            fit_result = CliRunner().invoke(
                app,
                [
                    "calibrate",
                    "--world",
                    str(world_path),
                    "--targets",
                    str(targets_path),
                    "--output",
                    str(fit_output_path),
                    "--require-all-passed",
                ],
            )
            self.assertEqual(fit_result.exit_code, 1)
            self.assertTrue(fit_output_path.exists())
            self.assertIn("Calibration fit failed", fit_result.output)
            self.assertIn("ocean_fraction", fit_result.output)

            targets_path.write_text(json.dumps({"targets": [targets[0]]}), encoding="utf-8")
            passing_fit_result = CliRunner().invoke(
                app,
                [
                    "calibrate",
                    "--world",
                    str(world_path),
                    "--targets",
                    str(targets_path),
                    "--output",
                    str(root / "passing-fit-report.json"),
                    "--require-all-passed",
                ],
            )
            self.assertEqual(passing_fit_result.exit_code, 0)

            targets_path.write_text(json.dumps({"targets": []}), encoding="utf-8")
            empty_result = CliRunner().invoke(
                app,
                [
                    "calibrate",
                    "--world",
                    str(world_path),
                    "--targets",
                    str(targets_path),
                    "--output",
                    str(root / "empty-report.json"),
                    "--require-all-metrics",
                ],
            )
            self.assertEqual(empty_result.exit_code, 1)
            self.assertIn("no calibration targets were evaluated", empty_result.output)

    def test_derives_targets_from_shapefile_geometry(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shapefile = root / "natural_earth_coastline.shp"
            write_polyline_shapefile(shapefile)
            write_dbf(root / "natural_earth_coastline.dbf", "LEN_KM", [123.5])
            manifest = root / "sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "dataset": "custom_natural_earth",
                                "layer": "coastline",
                                "metric": "coastline_shapefile_feature_count",
                                "path": "natural_earth_coastline.shp",
                                "format": "shapefile",
                                "statistic": "feature_count",
                                "tolerance_abs": 0.0,
                            },
                            {
                                "dataset": "custom_natural_earth",
                                "layer": "coastline",
                                "metric": "coastline_shapefile_length_km",
                                "path": "natural_earth_coastline.shp",
                                "format": "shapefile",
                                "geometry_metric": "length_km",
                                "statistic": "sum",
                                "tolerance_fraction": 0.05,
                            },
                            {
                                "dataset": "custom_natural_earth",
                                "layer": "coastline",
                                "metric": "mean_coastline_dbf_length_km",
                                "path": "natural_earth_coastline.shp",
                                "format": "shapefile",
                                "property": "LEN_KM",
                                "statistic": "mean",
                                "tolerance_abs": 1.5,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = derive_calibration_targets(load_calibration_sources(manifest))

        self.assertEqual(report["summary"]["derived_target_count"], 3)
        targets = {target["metric"]: target for target in report["targets"]}
        self.assertEqual(targets["coastline_shapefile_feature_count"]["source_format"], "shapefile")
        self.assertEqual(targets["coastline_shapefile_feature_count"]["source_value"], 1.0)
        self.assertEqual(targets["coastline_shapefile_feature_count"]["target_min"], 1.0)
        self.assertEqual(targets["coastline_shapefile_feature_count"]["target_max"], 1.0)
        self.assertEqual(targets["coastline_shapefile_length_km"]["source_format"], "shapefile")
        self.assertAlmostEqual(targets["coastline_shapefile_length_km"]["source_value"], 111.19, places=1)
        self.assertEqual(targets["mean_coastline_dbf_length_km"]["source_format"], "shapefile")
        self.assertEqual(targets["mean_coastline_dbf_length_km"]["source_property"], "LEN_KM")
        self.assertTrue(targets["mean_coastline_dbf_length_km"]["source_dbf"].endswith("natural_earth_coastline.dbf"))
        self.assertAlmostEqual(targets["mean_coastline_dbf_length_km"]["source_value"], 123.5)
        self.assertAlmostEqual(targets["mean_coastline_dbf_length_km"]["target_min"], 122.0)
        self.assertAlmostEqual(targets["mean_coastline_dbf_length_km"]["target_max"], 125.0)

    def test_derives_projected_shapefile_geometry_from_manifest_and_prj(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            projected_line = root / "projected_line.shp"
            write_polyline_shapefile(projected_line, [(0.0, 0.0), (3000.0, 4000.0)])

            projected_square = root / "projected_square.shp"
            write_polygon_shapefile(
                projected_square,
                [(0.0, 0.0), (1000.0, 0.0), (1000.0, 1000.0), (0.0, 1000.0), (0.0, 0.0)],
            )
            projected_square.with_suffix(".prj").write_text(
                'PROJCS["Local_Meter",GEOGCS["WGS 84"],UNIT["metre",1]]',
                encoding="utf-8",
            )

            manifest = root / "sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "dataset": "custom_projected",
                                "layer": "line",
                                "metric": "projected_line_length_km",
                                "path": "projected_line.shp",
                                "format": "shapefile",
                                "coordinate_system": "projected_m",
                                "geometry_metric": "length_km",
                                "statistic": "sum",
                                "tolerance_abs": 0.0,
                            },
                            {
                                "dataset": "custom_projected",
                                "layer": "square",
                                "metric": "projected_square_area_km2",
                                "path": "projected_square.shp",
                                "format": "shapefile",
                                "geometry_metric": "area_km2",
                                "statistic": "sum",
                                "tolerance_abs": 0.0,
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = derive_calibration_targets(load_calibration_sources(manifest))

        targets = {target["metric"]: target for target in report["targets"]}
        self.assertAlmostEqual(targets["projected_line_length_km"]["source_value"], 5.0)
        self.assertEqual(targets["projected_line_length_km"]["source_coordinate_system"], "projected_m")
        self.assertAlmostEqual(targets["projected_square_area_km2"]["source_value"], 1.0)
        self.assertEqual(targets["projected_square_area_km2"]["source_coordinate_system"], "projected_m")
        self.assertTrue(targets["projected_square_area_km2"]["source_prj"].endswith("projected_square.prj"))

        summaries = {summary["metric"]: summary for summary in report["source_summaries"]}
        self.assertEqual(summaries["projected_square_area_km2"]["coordinate_system"], "projected_m")
        self.assertTrue(summaries["projected_square_area_km2"]["prj_path"].endswith("projected_square.prj"))

    def test_derives_scale_matched_coastal_fraction_with_provenance(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shapefile = root / "western_hemisphere.shp"
            write_polygon_shapefile(
                shapefile,
                [(-180.0, -90.0), (0.0, -90.0), (0.0, 90.0), (-180.0, 90.0), (-180.0, -90.0)],
            )
            source_sha256 = hashlib.sha256(shapefile.read_bytes()).hexdigest()
            manifest = root / "sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "dataset": "test_land",
                                "layer": "western_hemisphere",
                                "metric": "fibonacci_128_coastal_land_fraction",
                                "world_metric": "coastal_land_fraction",
                                "path": shapefile.name,
                                "format": "shapefile",
                                "coordinate_system": "geographic",
                                "statistic": "fibonacci_coastal_land_fraction",
                                "sample_cell_count": 128,
                                "sample_neighbor_count": 4,
                                "tolerance_abs": 0.01,
                                "tolerance_basis": "Test-only absolute tolerance.",
                                "source_url": "https://example.test/western_hemisphere.shp",
                                "source_archive_url": "https://example.test/western_hemisphere.zip",
                                "source_version": "1.0",
                                "source_license": "Public domain",
                                "source_license_url": "https://example.test/license",
                                "source_acquired_on": "2026-07-09",
                                "source_sha256": source_sha256,
                                "source_archive_sha256": "a" * 64,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = derive_calibration_targets(load_calibration_sources(manifest))

        target = report["targets"][0]
        self.assertEqual(target["metric"], "coastal_land_fraction")
        self.assertEqual(target["source_value"], 0.28125)
        self.assertEqual(target["target_min"], 0.27125)
        self.assertEqual(target["target_max"], 0.29125)
        self.assertEqual(target["tolerance_basis"], "Test-only absolute tolerance.")
        self.assertEqual(target["source_sha256"], source_sha256)
        self.assertEqual(target["source_archive_sha256"], "a" * 64)
        self.assertEqual(target["source_version"], "1.0")
        self.assertEqual(target["source_license"], "Public domain")
        self.assertEqual(target["source_acquired_on"], "2026-07-09")
        self.assertEqual(target["source_sampling_mesh"], "fibonacci_sphere_v1")
        self.assertEqual(target["source_sample_cell_count"], 128)
        self.assertEqual(target["source_sample_neighbor_count"], 4)
        self.assertEqual(target["source_sample_land_cell_count"], 64)
        self.assertEqual(target["source_sample_land_fraction"], 0.5)
        self.assertEqual(target["source_sample_water_cell_count"], 64)
        self.assertEqual(target["source_sample_coastal_land_cell_count"], 18)
        self.assertEqual(target["source_sample_land_component_count"], 1)
        self.assertEqual(target["source_sample_largest_land_component_cell_count"], 64)
        self.assertEqual(target["source_sample_largest_land_component_fraction"], 1.0)
        self.assertEqual(target["source_sample_land_water_edge_count"], 28)
        self.assertEqual(target["source_coast_definition"], "land_cell_with_symmetric_one_hop_water_neighbor")

        source_summary = report["source_summaries"][0]
        self.assertEqual(source_summary["sample_count"], 128)
        self.assertEqual(source_summary["sample_land_cell_count"], 64)
        self.assertEqual(source_summary["sample_coastal_land_cell_count"], 18)
        self.assertEqual(source_summary["sample_land_component_count"], 1)
        self.assertEqual(source_summary["sample_land_water_edge_count"], 28)
        self.assertEqual(source_summary["sha256"], source_sha256)

        evaluation = evaluate_calibration_targets(
            {"calibration_checks": [{"metric": "coastal_land_fraction", "value": 0.28125}]},
            [target],
        )
        evaluated_check = evaluation["checks"][0]
        self.assertTrue(evaluated_check["passed"])
        self.assertEqual(evaluated_check["source_sha256"], source_sha256)
        self.assertEqual(evaluated_check["source_version"], "1.0")
        self.assertEqual(evaluated_check["source_sample_land_component_count"], 1)
        self.assertEqual(evaluated_check["tolerance_basis"], "Test-only absolute tolerance.")

    def test_derives_scale_matched_relief_statistics_from_opendap_ascii(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            grid_path = root / "relief.dap.txt"
            write_opendap_ascii_grid(
                grid_path,
                [
                    [-1000.0, -1000.0, -1000.0, -1000.0],
                    [-1000.0, -1000.0, -1000.0, -1000.0],
                    [1000.0, 1000.0, 1000.0, 1000.0],
                    [1000.0, 1000.0, 1000.0, 1000.0],
                ],
                [-89.5, -60.0, 60.0, 89.5],
                [-179.5, -60.0, 60.0, 179.5],
            )
            source_sha256 = hashlib.sha256(grid_path.read_bytes()).hexdigest()
            metrics = [
                ("fibonacci_ocean_fraction", "below_sea_level_surface_fraction"),
                ("fibonacci_mean_land_elevation_m", "mean_nonnegative_surface_elevation_m"),
                ("fibonacci_hypsometric_span_m", "surface_elevation_span_m"),
            ]
            manifest = root / "sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "dataset": "test_relief",
                                "layer": "surface",
                                "metric": source_metric,
                                "world_metric": world_metric,
                                "path": grid_path.name,
                                "format": "opendap_ascii_grid",
                                "statistic": source_metric,
                                "sample_cell_count": 128,
                                "tolerance_abs": 0.0,
                                "source_sha256": source_sha256,
                                "source_version": "test-v1",
                            }
                            for source_metric, world_metric in metrics
                        ]
                    }
                ),
                encoding="utf-8",
            )

            report = derive_calibration_targets(load_calibration_sources(manifest))

            malformed_path = root / "malformed.dap.txt"
            malformed_path.write_text(grid_path.read_text(encoding="utf-8").replace("[1],", "[2],", 1), encoding="utf-8")
            malformed_source = {
                "dataset": "test_relief",
                "layer": "surface",
                "metric": "ocean_fraction",
                "path": str(malformed_path),
                "format": "opendap_ascii_grid",
                "statistic": "fibonacci_ocean_fraction",
                "sample_cell_count": 128,
            }
            with self.assertRaisesRegex(CalibrationError, "out-of-order OPeNDAP grid row 1"):
                derive_calibration_targets([malformed_source])

        targets = {target["metric"]: target for target in report["targets"]}
        ocean_metric = "below_sea_level_surface_fraction"
        land_metric = "mean_nonnegative_surface_elevation_m"
        span_metric = "surface_elevation_span_m"
        self.assertEqual(targets[ocean_metric]["source_value"], 0.5)
        self.assertEqual(targets[land_metric]["source_value"], 1000.0)
        self.assertEqual(targets[span_metric]["source_value"], 2000.0)
        self.assertEqual(targets[ocean_metric]["source_format"], "opendap_ascii_grid")
        self.assertEqual(targets[ocean_metric]["source_sample_land_cell_count"], 64)
        self.assertEqual(targets[ocean_metric]["source_sample_ocean_cell_count"], 64)
        self.assertEqual(targets[ocean_metric]["source_grid_latitude_count"], 4)
        self.assertEqual(targets[ocean_metric]["source_grid_longitude_count"], 4)

        summaries = {summary["world_metric"]: summary for summary in report["source_summaries"]}
        self.assertEqual(summaries[ocean_metric]["grid_latitude_count"], 4)
        self.assertEqual(summaries[ocean_metric]["sample_ocean_fraction"], 0.5)

        world = {
            "calibration_checks": [],
            "cells": [
                {
                    "elevation_m": elevation,
                    "is_water": elevation < 0.0,
                    "temperature_monthly_c": [10.0] * 12,
                    "precipitation_mm_y": 500.0,
                }
                for elevation in (-1000.0, -1000.0, 1000.0, 1000.0)
            ],
        }
        evaluation = evaluate_calibration_targets(world, report["targets"])
        self.assertEqual(evaluation["summary"]["external_calibration_pass_count"], 3)
        self.assertTrue(evaluation["summary"]["external_calibration_complete"])

        partial_elevation_world = json.loads(json.dumps(world))
        del partial_elevation_world["cells"][0]["elevation_m"]
        with self.assertRaisesRegex(
            CalibrationError,
            "world cell elevation_m must be present for every cell or no cells",
        ):
            evaluate_calibration_targets(partial_elevation_world, report["targets"])

    def test_rejects_calibration_source_checksum_mismatch(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shapefile = Path(tmpdir) / "land.shp"
            write_polygon_shapefile(
                shapefile,
                [(-180.0, -90.0), (0.0, -90.0), (0.0, 90.0), (-180.0, 90.0), (-180.0, -90.0)],
            )
            source = {
                "dataset": "test_land",
                "layer": "land",
                "metric": "coastal_land_fraction",
                "path": str(shapefile),
                "format": "shapefile",
                "statistic": "fibonacci_coastal_land_fraction",
                "sample_cell_count": 128,
                "sample_neighbor_count": 4,
                "source_sha256": "0" * 64,
            }

            with self.assertRaisesRegex(CalibrationError, "SHA-256 mismatch"):
                derive_calibration_targets([source])

    def test_rejects_invalid_coastal_sampling_parameters(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shapefile = Path(tmpdir) / "land.shp"
            write_polygon_shapefile(
                shapefile,
                [(-180.0, -90.0), (0.0, -90.0), (0.0, 90.0), (-180.0, 90.0), (-180.0, -90.0)],
            )
            base_source = {
                "dataset": "test_land",
                "layer": "land",
                "metric": "coastal_land_fraction",
                "path": str(shapefile),
                "format": "shapefile",
                "statistic": "fibonacci_coastal_land_fraction",
                "sample_neighbor_count": 4,
            }

            with self.assertRaisesRegex(CalibrationError, "sample_cell_count.*at least 128"):
                derive_calibration_targets([{**base_source, "sample_cell_count": 127}])
            with self.assertRaisesRegex(CalibrationError, "sample_neighbor_count.*smaller"):
                derive_calibration_targets([{**base_source, "sample_cell_count": 128, "sample_neighbor_count": 128}])

    def test_derives_hydrobasins_endorheic_count_and_area_fractions(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive_specs = [
                ("aa", [0.0, 1.0], [100.0, 50.0]),
                ("bb", [2.0, 0.0], [25.0, 75.0]),
            ]
            catalog_archives = []
            for region, endorheic, areas in archive_specs:
                dbf_path = root / f"hybas_{region}_lev03_v1c.dbf"
                write_dbf_table(dbf_path, {"ENDO": endorheic, "SUB_AREA": areas})
                archive_path = root / f"hybas_{region}_lev03_v1c.zip"
                with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                    archive.write(dbf_path, dbf_path.name)
                catalog_archives.append(
                    {
                        "region": region,
                        "path": archive_path.name,
                        "url": f"https://example.test/{archive_path.name}",
                        "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                    }
                )

            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps({"pfafstetter_level": 3, "archives": catalog_archives}),
                encoding="utf-8",
            )
            common = {
                "dataset": "test_hydrobasins",
                "layer": "level_3",
                "path": str(catalog_path),
                "format": "hydrobasins_archive_catalog",
                "tolerance_abs": 0.0,
            }
            sources = [
                {
                    **common,
                    "metric": "hydrobasins_endorheic_basin_fraction",
                    "world_metric": "non_antarctic_endorheic_watershed_fraction",
                    "statistic": "hydrobasins_endorheic_basin_fraction",
                },
                {
                    **common,
                    "metric": "hydrobasins_endorheic_area_fraction",
                    "world_metric": "non_antarctic_endorheic_watershed_area_fraction",
                    "statistic": "hydrobasins_endorheic_area_fraction",
                },
            ]
            report = derive_calibration_targets(sources)

            tampered_archive = root / "hybas_aa_lev03_v1c.zip"
            tampered_archive.write_bytes(tampered_archive.read_bytes() + b"tampered")
            with self.assertRaisesRegex(CalibrationError, "archive SHA-256 mismatch for aa"):
                derive_calibration_targets([sources[0]])

        targets = {target["metric"]: target for target in report["targets"]}
        count_metric = "non_antarctic_endorheic_watershed_fraction"
        area_metric = "non_antarctic_endorheic_watershed_area_fraction"
        self.assertEqual(targets[count_metric]["source_value"], 0.5)
        self.assertEqual(targets[area_metric]["source_value"], 0.3)
        self.assertEqual(targets[count_metric]["source_basin_count"], 4)
        self.assertEqual(targets[count_metric]["source_endorheic_basin_count"], 2)
        self.assertEqual(targets[count_metric]["source_endorheic_sink_count"], 1)
        self.assertEqual(targets[count_metric]["source_archive_count"], 2)
        self.assertEqual(report["source_summaries"][0]["sample_count"], 4)

        world = {
            "calibration_checks": [{"metric": "endorheic_watershed_fraction", "value": 0.5}],
            "watersheds": [
                {"area_km2": 100.0, "is_endorheic": False, "outlet_type": "ocean", "centroid_lat_deg": 20.0},
                {"area_km2": 50.0, "is_endorheic": True, "outlet_type": "closed_land", "centroid_lat_deg": 10.0},
                {"area_km2": 25.0, "is_endorheic": True, "outlet_type": "closed_land", "centroid_lat_deg": -10.0},
                {"area_km2": 75.0, "is_endorheic": False, "outlet_type": "ocean", "centroid_lat_deg": -20.0},
            ],
        }
        evaluation = evaluate_calibration_targets(world, report["targets"])
        self.assertEqual(evaluation["summary"]["external_calibration_pass_count"], 2)
        self.assertIn(
            "non_antarctic_endorheic_watershed_area_fraction",
            evaluation["available_world_metrics"],
        )

        world["watersheds"][2]["centroid_lat_deg"] = -70.0
        coverage_evaluation = evaluate_calibration_targets(world, report["targets"])
        coverage_values = {check["metric"]: check["value"] for check in coverage_evaluation["checks"]}
        self.assertAlmostEqual(
            coverage_values["non_antarctic_endorheic_watershed_fraction"],
            1.0 / 3.0,
        )
        self.assertAlmostEqual(
            coverage_values["non_antarctic_endorheic_watershed_area_fraction"],
            50.0 / 225.0,
        )

    def test_rejects_incomplete_hydrobasins_dbf_records(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dbf_path = root / "hybas_aa_lev03_v1c.dbf"
            write_dbf_table(
                dbf_path,
                {
                    "ENDO": [0.0, None, 1.0],
                    "SUB_AREA": [100.0, 50.0, 25.0],
                },
            )
            archive_path = root / "hybas_aa_lev03_v1c.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.write(dbf_path, dbf_path.name)
            catalog_path = root / "catalog.json"
            catalog_path.write_text(
                json.dumps(
                    {
                        "pfafstetter_level": 3,
                        "archives": [
                            {
                                "region": "aa",
                                "path": archive_path.name,
                                "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            source = {
                "dataset": "test_hydrobasins",
                "layer": "level_3",
                "metric": "hydrobasins_endorheic_basin_fraction",
                "world_metric": "endorheic_watershed_fraction",
                "path": str(catalog_path),
                "format": "hydrobasins_archive_catalog",
                "statistic": "hydrobasins_endorheic_basin_fraction",
                "tolerance_abs": 0.0,
            }

            with self.assertRaisesRegex(CalibrationError, "ENDO.*blank.*active record 1"):
                derive_calibration_targets([source])

    def test_derives_hydrorivers_hack_fit_from_streamed_outlet_records(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            dbf_path = root / "HydroRIVERS_v10_test.dbf"
            write_dbf_table(
                dbf_path,
                {
                    "NEXT_DOWN": [0.0, 123.0, 0.0, 0.0, 0.0, 0.0],
                    "ENDORHEIC": [0.0, 0.0, 1.0, 0.0, 0.0, 0.0],
                    "ORD_CLAS": [1.0, 1.0, 1.0, 2.0, 1.0, 1.0],
                    "UPLAND_SKM": [
                        1_000_000.0,
                        1_440_000.0,
                        1_690_000.0,
                        2_560_000.0,
                        3_240_000.0,
                        4_000_000.0,
                    ],
                    "DIST_UP_KM": [
                        2_000.0,
                        2_300.0,
                        2_600.0,
                        3_200.0,
                        3_600.0,
                        4_000.0,
                    ],
                },
            )
            archive_path = root / "HydroRIVERS_v10_test_shp.zip"
            with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
                archive.write(dbf_path, f"nested/{dbf_path.name}")
            source_sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            common = {
                "dataset": "test_hydrorivers",
                "layer": "global_network",
                "path": str(archive_path),
                "format": "hydrorivers_shapefile_zip",
                "minimum_upstream_area_km2": 1_000_000.0,
                "source_sha256": source_sha256,
                "tolerance_abs": 0.000001,
            }
            sources = [
                {
                    **common,
                    "metric": "hydrorivers_hack_fitted_exponent",
                    "world_metric": (
                        "exorheic_watershed_backbone_hack_fitted_exponent"
                    ),
                    "statistic": "hydrorivers_hack_fitted_exponent",
                },
                {
                    **common,
                    "metric": "hydrorivers_hack_fitted_log_rmse",
                    "world_metric": (
                        "exorheic_watershed_backbone_hack_fitted_log_rmse"
                    ),
                    "statistic": "hydrorivers_hack_fitted_log_rmse",
                },
            ]

            report = derive_calibration_targets(sources)

            incomplete_dbf = root / "HydroRIVERS_v10_incomplete.dbf"
            write_dbf_table(
                incomplete_dbf,
                {
                    "NEXT_DOWN": [0.0, 0.0, 0.0],
                    "ENDORHEIC": [0.0, 0.0, 0.0],
                    "ORD_CLAS": [1.0, 1.0, 1.0],
                    "UPLAND_SKM": [100.0, None, 900.0],
                    "DIST_UP_KM": [20.0, 40.0, 60.0],
                },
            )
            incomplete_archive = root / "HydroRIVERS_v10_incomplete_shp.zip"
            with ZipFile(incomplete_archive, "w", compression=ZIP_DEFLATED) as archive:
                archive.write(incomplete_dbf, incomplete_dbf.name)
            incomplete_source = {
                **sources[0],
                "path": str(incomplete_archive),
                "source_sha256": hashlib.sha256(incomplete_archive.read_bytes()).hexdigest(),
            }
            with self.assertRaisesRegex(CalibrationError, "UPLAND_SKM.*blank.*active record 1"):
                derive_calibration_targets([incomplete_source])
            with self.assertRaisesRegex(CalibrationError, "must match the generated Hack-fit floor"):
                derive_calibration_targets(
                    [{**sources[0], "minimum_upstream_area_km2": 999_999.0}]
                )

        targets = {target["metric"]: target for target in report["targets"]}
        exponent = targets[
            "exorheic_watershed_backbone_hack_fitted_exponent"
        ]
        log_rmse = targets[
            "exorheic_watershed_backbone_hack_fitted_log_rmse"
        ]
        self.assertAlmostEqual(exponent["source_value"], 0.5, places=9)
        self.assertAlmostEqual(log_rmse["source_value"], 0.0, places=9)
        self.assertEqual(exponent["source_active_reach_record_count"], 6)
        self.assertEqual(exponent["source_terminal_reach_record_count"], 5)
        self.assertEqual(
            exponent["source_exorheic_terminal_reach_record_count"], 4
        )
        self.assertEqual(
            exponent[
                "source_exorheic_backbone_terminal_reach_record_count"
            ],
            3,
        )
        self.assertEqual(exponent["source_sample_network_count"], 3)
        self.assertEqual(
            exponent["source_network_selection"],
            "next_down_zero_endorheic_zero_order_class_one_with_minimum_upstream_area_v2",
        )
        self.assertEqual(exponent["source_sample_record_count"], 3)

        world = {
            "calibration_checks": [],
            "watersheds": [
                {
                    "area_km2": 1_690_000.0,
                    "main_channel_length_km": 2_600.0,
                    "is_endorheic": False,
                    "outlet_type": "ocean",
                },
                {
                    "area_km2": 1_000_000.0,
                    "main_channel_length_km": 2_000.0,
                    "is_endorheic": False,
                    "outlet_type": "ocean",
                },
                {
                    "area_km2": 2_560_000.0,
                    "main_channel_length_km": 3_200.0,
                    "is_endorheic": False,
                    "outlet_type": "ocean",
                },
                {
                    "area_km2": 4_000_000.0,
                    "main_channel_length_km": 50.0,
                    "is_endorheic": True,
                    "outlet_type": "closed_land",
                },
            ],
        }
        evaluation = evaluate_calibration_targets(world, report["targets"])
        self.assertEqual(evaluation["summary"]["external_calibration_pass_count"], 2)
        self.assertTrue(evaluation["summary"]["external_calibration_complete"])
        self.assertAlmostEqual(
            evaluation["checks"][0]["value"],
            0.5,
            places=12,
        )

        missing_outlet_semantics_world = {
            "calibration_checks": [],
            "watersheds": [
                {
                    "area_km2": watershed["area_km2"],
                    "main_channel_length_km": watershed["main_channel_length_km"],
                }
                for watershed in world["watersheds"]
            ],
        }
        with self.assertRaisesRegex(
            CalibrationError,
            "must provide is_endorheic and outlet_type consistently",
        ):
            evaluate_calibration_targets(
                missing_outlet_semantics_world,
                report["targets"],
            )

        incomplete_outlet_semantics_world = json.loads(json.dumps(world))
        incomplete_outlet_semantics_world["watersheds"][0].pop("outlet_type")
        with self.assertRaisesRegex(
            CalibrationError,
            "must provide is_endorheic and outlet_type consistently",
        ):
            evaluate_calibration_targets(
                incomplete_outlet_semantics_world,
                report["targets"],
            )

        conflicting_world = json.loads(json.dumps(world))
        conflicting_world["watersheds"][0]["is_endorheic"] = True
        with self.assertRaisesRegex(
            CalibrationError,
            "ocean outlet_type conflicts with is_endorheic",
        ):
            evaluate_calibration_targets(conflicting_world, report["targets"])


class ScoreRangeTests(TestCase):
    def test_score_range_interpolates_outside_the_band(self) -> None:
        cases = [
            ("inside", 0.5, 0.0, 1.0, 1.0),
            ("on_lower_bound", 0.0, 0.0, 1.0, 1.0),
            ("on_upper_bound", 1.0, 0.0, 1.0, 1.0),
            ("half_width_below", -0.5, 0.0, 1.0, 0.5),
            ("half_width_above", 1.5, 0.0, 1.0, 0.5),
            ("one_width_below", -1.0, 0.0, 1.0, 0.0),
            ("clamped_far_above", 12.0, 0.0, 1.0, 0.0),
            ("degenerate_band_miss", 6.0, 5.0, 5.0, 0.0),
            ("degenerate_band_hit", 5.0, 5.0, 5.0, 1.0),
        ]
        for label, value, target_min, target_max, expected in cases:
            with self.subTest(case=label):
                self.assertAlmostEqual(score_range(value, target_min, target_max), expected)

    def test_score_range_rejects_non_finite_and_inverted_bounds(self) -> None:
        for label, args in [
            ("value", (float("nan"), 0.0, 1.0)),
            ("target_min", (0.5, float("-inf"), 1.0)),
            ("target_max", (0.5, 0.0, float("inf"))),
        ]:
            with self.subTest(case=label):
                with self.assertRaisesRegex(
                    CalibrationError,
                    r"^calibration values and target bounds must be finite$",
                ):
                    score_range(*args)
        with self.assertRaisesRegex(
            CalibrationError,
            r"^target_max must be greater than or equal to target_min$",
        ):
            score_range(0.5, 1.0, 0.0)


class ManifestLoadingTests(TestCase):
    def test_load_calibration_targets_accepts_list_and_object_payloads(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            bare = root / "bare.json"
            bare.write_text(json.dumps([{"metric": "a"}]), encoding="utf-8")
            wrapped = root / "wrapped.json"
            wrapped.write_text(json.dumps({"targets": [{"metric": "b"}]}), encoding="utf-8")
            self.assertEqual(load_calibration_targets(bare), [{"metric": "a"}])
            self.assertEqual(load_calibration_targets(wrapped), [{"metric": "b"}])

            invalid = root / "invalid.json"
            invalid.write_text(json.dumps({"targets": {"metric": "a"}}), encoding="utf-8")
            with self.assertRaisesRegex(
                CalibrationError,
                r"^calibration targets must be a list or an object with a 'targets' list$",
            ):
                load_calibration_targets(invalid)

            not_objects = root / "not_objects.json"
            not_objects.write_text(json.dumps({"targets": ["a"]}), encoding="utf-8")
            with self.assertRaisesRegex(
                CalibrationError,
                r"^each calibration target must be an object$",
            ):
                load_calibration_targets(not_objects)

    def test_load_calibration_sources_resolves_relative_companion_paths(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "nested"
            nested.mkdir()
            manifest = root / "sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "dataset": "d",
                                "layer": "l",
                                "metric": "m",
                                "path": "nested/lines.shp",
                                "dbf_path": "nested/attributes.dbf",
                                "prj_path": "nested/projection.prj",
                            },
                            {
                                "dataset": "d",
                                "layer": "l",
                                "metric": "m",
                                "path": str(root / "absolute.shp"),
                                "dbf_path": str(root / "absolute.dbf"),
                                "prj_path": str(root / "absolute.prj"),
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            resolved = load_calibration_sources(manifest)

            self.assertEqual(resolved[0]["path"], str(nested / "lines.shp"))
            self.assertEqual(resolved[0]["dbf_path"], str(nested / "attributes.dbf"))
            self.assertEqual(resolved[0]["prj_path"], str(nested / "projection.prj"))
            self.assertEqual(resolved[1]["path"], str(root / "absolute.shp"))
            self.assertEqual(resolved[1]["dbf_path"], str(root / "absolute.dbf"))
            self.assertEqual(resolved[1]["prj_path"], str(root / "absolute.prj"))

    def test_load_calibration_sources_rejects_malformed_payloads(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cases = [
                (
                    "not_a_list",
                    {"sources": {"path": "a"}},
                    r"^calibration sources must be a list or an object with a 'sources' list$",
                ),
                ("not_objects", {"sources": ["a"]}, r"^each calibration source must be an object$"),
                ("missing_path", {"sources": [{"dataset": "d"}]}, r"^calibration target missing 'path'$"),
                ("blank_path", {"sources": [{"path": ""}]}, r"^calibration target missing 'path'$"),
                (
                    "non_string_dbf_path",
                    {"sources": [{"path": "a.shp", "dbf_path": 3}]},
                    r"^calibration target missing 'dbf_path'$",
                ),
                (
                    "non_string_prj_path",
                    {"sources": [{"path": "a.shp", "prj_path": None}]},
                    r"^calibration target missing 'prj_path'$",
                ),
            ]
            for label, payload, message in cases:
                with self.subTest(case=label):
                    manifest = root / f"{label}.json"
                    manifest.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(CalibrationError, message):
                        load_calibration_sources(manifest)


class AsciiGridSourceTests(TestCase):
    def test_numeric_statistics_over_an_ascii_grid(self) -> None:
        with TemporaryDirectory() as tmpdir:
            grid = Path(tmpdir) / "grid.asc"
            _write_ascii_grid(grid, _ASCII_GRID_HEADER, ["-1 0 1", "2 3 -9999"])
            expected = {
                "count": 5.0,
                "min": -1.0,
                "max": 3.0,
                "mean": 1.0,
                "sum": 5.0,
                "p05": -0.8,
                "p50": 1.0,
                "p95": 2.8,
                "fraction_positive": 0.6,
                "fraction_nonzero": 0.8,
            }
            for statistic, value in expected.items():
                with self.subTest(statistic=statistic):
                    target = _derive_one(grid, statistic=statistic, tolerance_abs=0.0)
                    self.assertEqual(target["source_format"], "esri_ascii_grid")
                    self.assertAlmostEqual(target["source_value"], value)
                    self.assertAlmostEqual(target["target_min"], value)
                    self.assertAlmostEqual(target["target_max"], value)
            with self.assertRaisesRegex(
                CalibrationError,
                r"^unsupported calibration statistic 'median'$",
            ):
                _derive_one(grid, statistic="MEDIAN")

    def test_ascii_grid_tolerates_latin1_headers_and_non_header_lines(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            latin1 = root / "latin1.asc"
            latin1.write_bytes(
                b"ncols 3\nnrows 2\nxllcorner 0\nyllcorner 0\ncellsize 1 caf\xe9\n"
                b"NODATA_value -9999\n1 2 3\n4 5 6\n"
            )
            self.assertAlmostEqual(
                _derive_one(latin1, statistic="mean", tolerance_abs=0.0)["source_value"],
                3.5,
            )

            padded = root / "padded.asc"
            _write_ascii_grid(
                padded,
                [
                    "",
                    "ncols 3",
                    "nrows 2",
                    "xllcenter 0",
                    "yllcenter 0",
                    "NODATA_value -9999",
                    "cellsize 1",
                ],
                ["1 2 3", "4 5 6"],
            )
            self.assertAlmostEqual(
                _derive_one(padded, statistic="sum", tolerance_abs=0.0)["source_value"],
                21.0,
            )

    def test_malformed_ascii_grids_are_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cases = [
                (
                    "missing_dimensions",
                    ["xllcorner 0", "yllcorner 0", "cellsize 1"],
                    ["1 2 3"],
                    r"is missing ESRI ASCII ncols/nrows headers$",
                ),
                (
                    "non_numeric_dimensions",
                    ["ncols wide", "nrows 2", "xllcorner 0", "yllcorner 0", "cellsize 1", "NODATA_value -9999"],
                    ["1 2 3", "4 5 6"],
                    r"has invalid ESRI ASCII dimensions$",
                ),
                (
                    "non_numeric_value",
                    _ASCII_GRID_HEADER,
                    ["1 2 3", "4 5 six"],
                    r"contains a non-numeric raster value$",
                ),
                (
                    "value_count_mismatch",
                    _ASCII_GRID_HEADER,
                    ["1 2 3", "4 5"],
                    r"raster value count does not match declared ncols/nrows$",
                ),
                (
                    "all_nodata",
                    _ASCII_GRID_HEADER,
                    ["-9999 -9999 -9999", "-9999 -9999 -9999"],
                    r"has no non-NODATA raster values$",
                ),
            ]
            for label, header, data_lines, message in cases:
                with self.subTest(case=label):
                    grid = root / f"{label}.asc"
                    _write_ascii_grid(grid, header, data_lines)
                    with self.assertRaisesRegex(CalibrationError, message):
                        _derive_one(grid, statistic="mean")

    def test_non_finite_derived_value_is_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            grid = Path(tmpdir) / "overflow.asc"
            _write_ascii_grid(
                grid,
                ["ncols 2", "nrows 1", "xllcorner 0", "yllcorner 0", "cellsize 1", "NODATA_value -9999"],
                ["1e308 1e308"],
            )
            with self.assertRaisesRegex(
                CalibrationError,
                r"^derived source value for 'unit_metric' must be finite$",
            ):
                _derive_one(grid, statistic="sum")


class GeoJsonSourceTests(TestCase):
    def test_geojson_property_values_skip_features_without_the_property(self) -> None:
        with TemporaryDirectory() as tmpdir:
            vector = Path(tmpdir) / "features.json"
            vector.write_text(
                json.dumps(
                    {
                        "type": "FeatureCollection",
                        "features": [
                            "not-an-object",
                            {"type": "Feature", "properties": ["not-a-mapping"]},
                            {"type": "Feature", "properties": {"other": 1.0}},
                            {"type": "Feature", "properties": {"length_km": 4.0}},
                            {"type": "Feature", "properties": {"length_km": 6.0}},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            target = _derive_one(
                vector,
                statistic="mean",
                property="length_km",
                tolerance_abs=0.0,
            )
            self.assertEqual(target["source_format"], "geojson")
            self.assertAlmostEqual(target["source_value"], 5.0)
            self.assertEqual(target["source_property"], "length_km")
            self.assertNotIn("source_dbf", target)

    def test_malformed_geojson_sources_are_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cases = [
                (
                    "not_a_collection",
                    {"type": "Feature"},
                    {"statistic": "feature_count"},
                    r"is not a GeoJSON FeatureCollection$",
                ),
                (
                    "list_payload",
                    [{"type": "Feature"}],
                    {"statistic": "feature_count"},
                    r"is not a GeoJSON FeatureCollection$",
                ),
                (
                    "missing_property",
                    {"features": [{"properties": {"a": 1.0}}]},
                    {"statistic": "mean"},
                    r"^GeoJSON calibration sources require 'property' unless statistic is feature_count$",
                ),
                (
                    "blank_property",
                    {"features": [{"properties": {"a": 1.0}}]},
                    {"statistic": "mean", "property": ""},
                    r"^GeoJSON calibration sources require 'property' unless statistic is feature_count$",
                ),
                (
                    "non_numeric_property",
                    {"features": [{"properties": {"a": "wide"}}]},
                    {"statistic": "mean", "property": "a"},
                    r"^GeoJSON property 'a' must be numeric$",
                ),
                (
                    "no_property_values",
                    {"features": [{"properties": {"b": 1.0}}]},
                    {"statistic": "mean", "property": "a"},
                    r"has no numeric GeoJSON property values for 'a'$",
                ),
            ]
            for label, payload, extra, message in cases:
                with self.subTest(case=label):
                    vector = root / f"{label}.geojson"
                    vector.write_text(json.dumps(payload), encoding="utf-8")
                    with self.assertRaisesRegex(CalibrationError, message):
                        _derive_one(vector, **extra)


class SourceFormatDispatchTests(TestCase):
    def test_format_is_inferred_from_the_file_suffix(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_ascii_grid(root / "grid.asc", _ASCII_GRID_HEADER, ["1 2 3", "4 5 6"])
            _write_ascii_grid(root / "grid.ascii", _ASCII_GRID_HEADER, ["1 2 3", "4 5 6"])
            collection = json.dumps({"features": [{"properties": {}}, {"properties": {}}]})
            (root / "vector.geojson").write_text(collection, encoding="utf-8")
            (root / "vector.json").write_text(collection, encoding="utf-8")
            write_polyline_shapefile(root / "lines.shp")
            cases = [
                ("grid.asc", "esri_ascii_grid", "mean", 3.5),
                ("grid.ascii", "esri_ascii_grid", "mean", 3.5),
                ("vector.geojson", "geojson", "feature_count", 2.0),
                ("vector.json", "geojson", "feature_count", 2.0),
                ("lines.shp", "shapefile", "feature_count", 1.0),
            ]
            for name, source_format, statistic, value in cases:
                with self.subTest(name=name):
                    target = _derive_one(root / name, statistic=statistic, tolerance_abs=0.0)
                    self.assertEqual(target["source_format"], source_format)
                    self.assertAlmostEqual(target["source_value"], value)

            unknown = root / "grid.txt"
            unknown.write_text("1 2 3\n", encoding="utf-8")
            with self.assertRaisesRegex(
                CalibrationError,
                r"cannot infer calibration source format for .*grid\.txt$",
            ):
                _derive_one(unknown, statistic="mean")
            with self.assertRaisesRegex(
                CalibrationError,
                r"^unsupported calibration source format 'netcdf4'$",
            ):
                _derive_one(unknown, statistic="mean", format="NetCDF4")

    def test_missing_source_file_is_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            missing = Path(tmpdir) / "absent.asc"
            with self.assertRaisesRegex(
                CalibrationError,
                r"^calibration source does not exist: .*absent\.asc$",
            ):
                _derive_one(missing, statistic="mean")

    def test_scale_matched_statistics_require_their_own_source_format(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _write_ascii_grid(root / "grid.asc", _ASCII_GRID_HEADER, ["1 2 3", "4 5 6"])
            cases = [
                (
                    "fibonacci_coastal_land_fraction",
                    r"^fibonacci_coastal_land_fraction requires a shapefile source$",
                ),
                (
                    "fibonacci_ocean_fraction",
                    r"^fibonacci_ocean_fraction requires an OPeNDAP ASCII grid source$",
                ),
                (
                    "fibonacci_mean_land_annual_temperature_c",
                    r"^fibonacci_mean_land_annual_temperature_c requires a WorldClim GeoTIFF ZIP source$",
                ),
                (
                    "hydrobasins_endorheic_basin_fraction",
                    r"^hydrobasins_endorheic_basin_fraction requires a HydroBASINS archive catalog$",
                ),
                (
                    "hydrorivers_hack_fitted_exponent",
                    r"^hydrorivers_hack_fitted_exponent requires a HydroRIVERS shapefile ZIP archive$",
                ),
            ]
            for statistic, message in cases:
                with self.subTest(statistic=statistic):
                    with self.assertRaisesRegex(CalibrationError, message):
                        _derive_one(root / "grid.asc", statistic=statistic)


class TargetRangeDerivationTests(TestCase):
    def test_explicit_bounds_and_tolerance_combinations(self) -> None:
        with TemporaryDirectory() as tmpdir:
            grid = Path(tmpdir) / "grid.asc"
            _write_ascii_grid(grid, _ASCII_GRID_HEADER, ["10 10 10", "10 10 10"])

            explicit = _derive_one(grid, statistic="mean", target_min=1.0, target_max=2.0)
            self.assertEqual(explicit["source_value"], 10.0)
            self.assertEqual(explicit["target_min"], 1.0)
            self.assertEqual(explicit["target_max"], 2.0)

            widest = _derive_one(
                grid,
                statistic="mean",
                tolerance_abs=0.5,
                tolerance_fraction=0.25,
            )
            self.assertEqual(widest["target_min"], 7.5)
            self.assertEqual(widest["target_max"], 12.5)

            default_fraction = _derive_one(grid, statistic="mean")
            self.assertEqual(default_fraction["target_min"], 9.5)
            self.assertEqual(default_fraction["target_max"], 10.5)

            with self.assertRaisesRegex(
                CalibrationError,
                r"^derived target range for 'unit_metric' is inverted$",
            ):
                _derive_one(grid, statistic="mean", target_min=2.0, target_max=1.0)

    def test_target_and_tolerance_fields_are_validated(self) -> None:
        with TemporaryDirectory() as tmpdir:
            grid = Path(tmpdir) / "grid.asc"
            _write_ascii_grid(grid, _ASCII_GRID_HEADER, ["10 10 10", "10 10 10"])
            cases = [
                (
                    "non_numeric_bound",
                    {"target_min": "low", "target_max": 2.0},
                    r"^calibration target 'target_min' must be numeric$",
                ),
                (
                    "non_finite_bound",
                    {"target_min": 1.0, "target_max": float("inf")},
                    r"^calibration target 'target_max' must be finite$",
                ),
                (
                    "non_numeric_tolerance",
                    {"tolerance_abs": "wide"},
                    r"^calibration source 'tolerance_abs' must be numeric$",
                ),
                (
                    "non_finite_tolerance",
                    {"tolerance_fraction": float("nan")},
                    r"^calibration source 'tolerance_fraction' must be finite$",
                ),
                (
                    "blank_tolerance_basis",
                    {"tolerance_abs": 0.0, "tolerance_basis": ""},
                    r"^calibration target missing 'tolerance_basis'$",
                ),
                ("missing_dataset", {"dataset": ""}, r"^calibration target missing 'dataset'$"),
                ("missing_layer", {"layer": None}, r"^calibration target missing 'layer'$"),
                ("missing_metric", {"metric": 7}, r"^calibration target missing 'metric'$"),
            ]
            for label, extra, message in cases:
                with self.subTest(case=label):
                    with self.assertRaisesRegex(CalibrationError, message):
                        _derive_one(grid, statistic="mean", **extra)

    def test_sample_count_fields_must_be_integers(self) -> None:
        with TemporaryDirectory() as tmpdir:
            shapefile = Path(tmpdir) / "land.shp"
            write_polygon_shapefile(
                shapefile,
                [(-180.0, -90.0), (0.0, -90.0), (0.0, 90.0), (-180.0, 90.0), (-180.0, -90.0)],
            )
            for label, value in [
                ("bool", True),
                ("float", 128.5),
                ("string", "128.0"),
                ("zero_padded_string", "0128"),
                ("none", None),
            ]:
                with self.subTest(case=label):
                    with self.assertRaisesRegex(
                        CalibrationError,
                        r"^calibration source 'sample_cell_count' must be an integer$",
                    ):
                        _derive_one(
                            shapefile,
                            format="shapefile",
                            statistic="fibonacci_coastal_land_fraction",
                            sample_cell_count=value,
                        )
            self.assertEqual(
                _derive_one(
                    shapefile,
                    format="shapefile",
                    statistic="fibonacci_coastal_land_fraction",
                    sample_cell_count=" 128 ",
                    sample_neighbor_count=4,
                    tolerance_abs=0.0,
                )["source_sample_cell_count"],
                128,
            )


class SourceProvenanceTests(TestCase):
    def test_provenance_fields_are_copied_and_validated(self) -> None:
        with TemporaryDirectory() as tmpdir:
            grid = Path(tmpdir) / "grid.asc"
            _write_ascii_grid(grid, _ASCII_GRID_HEADER, ["1 2 3", "4 5 6"])
            digest = hashlib.sha256(grid.read_bytes()).hexdigest()

            report = derive_calibration_targets(
                [
                    _source(
                        grid,
                        statistic="mean",
                        tolerance_abs=0.0,
                        source_sha256=digest.upper(),
                        source_archive_sha256="B" * 64,
                        source_citation="Example et al. 2026",
                        source_doi="10.0000/example",
                        source_variable_units="degC",
                        source_acquired_on="2026-01-31",
                    )
                ]
            )
            target = report["targets"][0]
            self.assertEqual(target["source_sha256"], digest)
            self.assertEqual(target["source_archive_sha256"], "b" * 64)
            self.assertEqual(target["source_citation"], "Example et al. 2026")
            self.assertEqual(target["source_doi"], "10.0000/example")
            self.assertEqual(target["source_variable_units"], "degC")
            summary = report["source_summaries"][0]
            self.assertEqual(summary["source_citation"], "Example et al. 2026")
            self.assertEqual(summary["source_archive_sha256"], "b" * 64)
            self.assertEqual(summary["sample_count"], 6)

            cases = [
                (
                    "short_sha256",
                    {"source_sha256": "abc"},
                    r"^calibration source 'source_sha256' must be a 64-character hexadecimal digest$",
                ),
                (
                    "non_string_sha256",
                    {"source_sha256": 12},
                    r"^calibration source 'source_sha256' must be a 64-character hexadecimal digest$",
                ),
                (
                    "bad_archive_sha256",
                    {"source_archive_sha256": "zz"},
                    r"^calibration source 'source_archive_sha256' must be a 64-character hexadecimal digest$",
                ),
                (
                    "bad_acquired_on",
                    {"source_acquired_on": "31-01-2026"},
                    r"^calibration source 'source_acquired_on' must use YYYY-MM-DD$",
                ),
            ]
            for label, extra, message in cases:
                with self.subTest(case=label):
                    with self.assertRaisesRegex(CalibrationError, message):
                        _derive_one(grid, statistic="mean", **extra)


class ShapefileRecordParsingTests(TestCase):
    def test_malformed_shapefile_records_are_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cases = [
                (
                    "bad_file_code",
                    {"header_patches": {0: struct.pack(">i", 1234)}},
                    r"is not an ESRI shapefile$",
                ),
                (
                    "bad_version",
                    {"header_patches": {28: struct.pack("<i", 999)}},
                    r"is not an ESRI shapefile$",
                ),
                (
                    "length_header_exceeds_file",
                    {"header_patches": {24: struct.pack(">i", 100_000)}},
                    r"shapefile length header exceeds file size$",
                ),
                (
                    "record_length_too_small",
                    {"content_length_words": 1},
                    r"has a malformed shapefile record length$",
                ),
                (
                    "record_length_exceeds_file",
                    {"content_length_words": 1_000},
                    r"has a malformed shapefile record length$",
                ),
                (
                    "only_null_shapes",
                    {"content": struct.pack("<i", 0)},
                    r"has no non-null shapefile records$",
                ),
                (
                    "mixed_shape_types",
                    {"header_patches": {32: struct.pack("<i", 5)}},
                    r"mixes shapefile shape types$",
                ),
                (
                    "short_point_record",
                    {
                        "header_patches": {32: struct.pack("<i", 1)},
                        "content": struct.pack("<i", 1) + b"\x00" * 12,
                    },
                    r"has a malformed point shapefile record$",
                ),
                (
                    "short_polyline_record",
                    {"content": struct.pack("<i", 3) + b"\x00" * 20},
                    r"has a malformed polyline/polygon shapefile record$",
                ),
                (
                    "non_finite_bbox",
                    {"content_patches": {4: struct.pack("<d", float("nan"))}},
                    r"has a non-finite shapefile bounding box$",
                ),
                (
                    "inverted_bbox",
                    {
                        "content_patches": {
                            4: struct.pack("<d", 10.0),
                            20: struct.pack("<d", -10.0),
                        }
                    },
                    r"has an inverted shapefile bounding box$",
                ),
                (
                    "zero_part_count",
                    {"content_patches": {36: struct.pack("<i", 0)}},
                    r"has malformed shapefile point data$",
                ),
                (
                    "excess_point_count",
                    {"content_patches": {40: struct.pack("<i", 1_000)}},
                    r"has malformed shapefile point data$",
                ),
                (
                    "invalid_part_index",
                    {"content_patches": {44: struct.pack("<i", 5)}},
                    r"^shapefile record has invalid part indexes$",
                ),
                (
                    "short_multipoint_record",
                    {
                        "header_patches": {32: struct.pack("<i", 8)},
                        "content": struct.pack("<i", 8) + b"\x00" * 30,
                    },
                    r"has a malformed multipoint shapefile record$",
                ),
                (
                    "excess_multipoint_count",
                    {
                        "header_patches": {32: struct.pack("<i", 8)},
                        "content_patches": {
                            0: struct.pack("<i", 8),
                            36: struct.pack("<i", 1_000),
                        },
                    },
                    r"has malformed multipoint data$",
                ),
                (
                    "unsupported_shape_type",
                    {
                        "header_patches": {32: struct.pack("<i", 11)},
                        "content_patches": {0: struct.pack("<i", 11)},
                    },
                    r"^unsupported shapefile shape type 11$",
                ),
                (
                    "trailing_bytes",
                    {"trailing": b"\x00\x00\x00\x00"},
                    r"has trailing malformed shapefile bytes$",
                ),
            ]
            for label, rewrite, message in cases:
                with self.subTest(case=label):
                    shapefile = root / f"{label}.shp"
                    write_polyline_shapefile(shapefile)
                    _rewrite_shapefile(shapefile, **rewrite)
                    with self.assertRaisesRegex(CalibrationError, message):
                        _derive_one(shapefile, format="shapefile", statistic="feature_count")

            tiny = root / "tiny.shp"
            tiny.write_bytes(b"\x00" * 10)
            with self.assertRaisesRegex(
                CalibrationError,
                r"is too small to be an ESRI shapefile$",
            ):
                _derive_one(tiny, format="shapefile", statistic="feature_count")

    def test_point_and_multipoint_records_report_point_counts(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            point = root / "point.shp"
            write_polyline_shapefile(point)
            _rewrite_shapefile(
                point,
                header_patches={32: struct.pack("<i", 1)},
                content_patches={0: struct.pack("<i", 1)},
            )
            point_target = _derive_one(
                point,
                format="shapefile",
                geometry_metric="points",
                statistic="sum",
                tolerance_abs=0.0,
            )
            self.assertEqual(point_target["source_value"], 1.0)
            self.assertEqual(point_target["source_geometry_metric"], "points")

            multipoint = root / "multipoint.shp"
            write_polyline_shapefile(multipoint)
            _rewrite_shapefile(
                multipoint,
                header_patches={32: struct.pack("<i", 8)},
                content_patches={0: struct.pack("<i", 8)},
            )
            multipoint_target = _derive_one(
                multipoint,
                format="shp",
                geometry_metric="point_count",
                statistic="sum",
                tolerance_abs=0.0,
            )
            self.assertEqual(multipoint_target["source_value"], 1.0)
            self.assertEqual(multipoint_target["source_format"], "shapefile")

    def test_geometry_metric_aliases_and_degenerate_rings(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            square = root / "square.shp"
            write_polygon_shapefile(square, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0), (0.0, 0.0)])
            for metric, expected in [("points", 5.0), ("parts", 1.0)]:
                with self.subTest(metric=metric):
                    self.assertEqual(
                        _derive_one(
                            square,
                            format="esri_shapefile",
                            geometry_metric=metric,
                            statistic="sum",
                            tolerance_abs=0.0,
                        )["source_value"],
                        expected,
                    )
            area = _derive_one(
                square,
                format="shapefile",
                geometry_metric="total_area_km2",
                statistic="sum",
                tolerance_abs=0.0,
            )["source_value"]
            self.assertAlmostEqual(area, 12308.6, delta=1.0)
            perimeter = _derive_one(
                square,
                format="shapefile",
                geometry_metric="length",
                statistic="sum",
                tolerance_abs=0.0,
            )["source_value"]
            self.assertAlmostEqual(perimeter, 444.74, delta=0.2)

            with self.assertRaisesRegex(
                CalibrationError,
                r"^unsupported shapefile geometry_metric 'volume_km3'$",
            ):
                _derive_one(square, format="shapefile", geometry_metric="volume_km3", statistic="sum")

            degenerate = root / "degenerate.shp"
            write_polygon_shapefile(degenerate, [(0.0, 0.0), (1000.0, 1000.0)])
            for coordinate_system in ("geographic", "projected_m"):
                with self.subTest(coordinate_system=coordinate_system):
                    self.assertEqual(
                        _derive_one(
                            degenerate,
                            format="shapefile",
                            coordinate_system=coordinate_system,
                            geometry_metric="area",
                            statistic="sum",
                            tolerance_abs=0.0,
                        )["source_value"],
                        0.0,
                    )


class VectorCoordinateSystemTests(TestCase):
    def test_coordinate_system_is_inferred_from_projection_text(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shapefile = root / "lines.shp"
            write_polyline_shapefile(shapefile)
            prj_path = shapefile.with_suffix(".prj")
            resolved = [
                ("epsg_3857_authority", 'PROJCS["x",AUTHORITY["EPSG","3857"]]', "projected_m"),
                ("epsg_4326_authority", 'GEOGCS["x",AUTHORITY["EPSG","4326"]]', "geographic"),
                ("epsg_3857_urn", "EPSG:3857", "projected_m"),
                ("projcs_metre_unit", 'PROJCS["x",UNIT["metre",1.0]]', "projected_m"),
                ("projcs_without_units", 'PROJCS["x"]', "projected_m"),
                ("geogcrs", 'GEOGCRS["x",ANGLEUNIT["degree",0.0174]]', "geographic"),
                ("bare_length_unit", 'LENGTHUNIT["metre",1.0]', "projected_m"),
                ("bare_angle_unit", 'ANGLEUNIT["degree",0.0174]', "geographic"),
            ]
            for label, prj_text, expected in resolved:
                with self.subTest(case=label):
                    prj_path.write_text(prj_text, encoding="utf-8")
                    target = _derive_one(
                        shapefile,
                        format="shapefile",
                        geometry_metric="length_km",
                        statistic="sum",
                        tolerance_abs=0.0,
                    )
                    self.assertEqual(target["source_coordinate_system"], expected)
                    self.assertEqual(target["source_prj"], str(prj_path))

            for label, prj_text in [
                ("projected_with_degree_units", 'PROJCS["x",UNIT["Degree",0.0174]]'),
                ("unrecognised", 'LOCAL_CS["x"]'),
            ]:
                with self.subTest(case=label):
                    prj_path.write_text(prj_text, encoding="utf-8")
                    with self.assertRaisesRegex(
                        CalibrationError,
                        r"could not infer vector coordinate system from shapefile projection file: .*lines\.prj$",
                    ):
                        _derive_one(shapefile, format="shapefile", statistic="sum")

            prj_path.write_bytes(b'GEOGCS["caf\xe9 84"]')
            self.assertEqual(
                _derive_one(
                    shapefile,
                    format="shapefile",
                    geometry_metric="length_km",
                    statistic="sum",
                    tolerance_abs=0.0,
                )["source_coordinate_system"],
                "geographic",
            )

    def test_explicit_coordinate_system_aliases_and_projection_paths(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shapefile = root / "lines.shp"
            write_polyline_shapefile(shapefile, [(0.0, 0.0), (3000.0, 4000.0)])
            aliases = [
                ("WGS 84", "geographic"),
                ("lat-lon", "geographic"),
                ("EPSG:4326", "geographic"),
                ("Meters", "projected_m"),
                ("epsg:3857", "projected_m"),
                ("  projected_metres  ", "projected_m"),
            ]
            for raw, expected in aliases:
                with self.subTest(coordinate_system=raw):
                    self.assertEqual(
                        _derive_one(
                            shapefile,
                            format="shapefile",
                            coordinate_system=raw,
                            geometry_metric="length_km",
                            statistic="sum",
                            tolerance_abs=0.0,
                        )["source_coordinate_system"],
                        expected,
                    )
            with self.assertRaisesRegex(
                CalibrationError,
                r"^unsupported vector coordinate_system 'mars_2000'; "
                r"use geographic/lonlat/wgs84 or projected_m/meters$",
            ):
                _derive_one(
                    shapefile,
                    format="shapefile",
                    coordinate_system="mars_2000",
                    geometry_metric="length_km",
                    statistic="sum",
                )

            sidecar = root / "custom.prj"
            sidecar.write_text('PROJCS["Local",UNIT["metre",1.0]]', encoding="utf-8")
            explicit = _derive_one(
                shapefile,
                format="shapefile",
                prj_path=str(sidecar),
                geometry_metric="length_km",
                statistic="sum",
                tolerance_abs=0.0,
            )
            self.assertEqual(explicit["source_coordinate_system"], "projected_m")
            self.assertEqual(explicit["source_prj"], str(sidecar))
            self.assertEqual(explicit["source_value"], 5.0)

            with self.assertRaisesRegex(
                CalibrationError,
                r"^shapefile projection file does not exist: .*absent\.prj$",
            ):
                _derive_one(
                    shapefile,
                    format="shapefile",
                    prj_path=str(root / "absent.prj"),
                    geometry_metric="length_km",
                    statistic="sum",
                )


class DbfAttributeTableTests(TestCase):
    def _write_pair(self, root: Path, name: str, values: list[float]) -> Path:
        shapefile = root / f"{name}.shp"
        write_polyline_shapefile(shapefile)
        write_dbf(root / f"{name}.dbf", "LEN_KM", values)
        return shapefile

    def test_malformed_dbf_attribute_tables_are_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            cases = [
                ("header_length_too_small", {8: struct.pack("<H", 10)}, "LEN_KM", r"has invalid DBF header lengths$"),
                ("header_length_past_eof", {8: struct.pack("<H", 5_000)}, "LEN_KM", r"has invalid DBF header lengths$"),
                ("zero_record_length", {10: struct.pack("<H", 0)}, "LEN_KM", r"has invalid DBF header lengths$"),
                ("truncated_descriptor", {8: struct.pack("<H", 60)}, "LEN_KM", r"has a truncated DBF field descriptor$"),
                ("blank_field_name", {32: b"\x00" * 11}, "LEN_KM", r"has an invalid DBF field descriptor$"),
                ("zero_field_length", {48: b"\x00"}, "LEN_KM", r"has an invalid DBF field descriptor$"),
                ("no_fields", {32: b"\x0d"}, "LEN_KM", r"has no DBF fields$"),
                (
                    "record_width_mismatch",
                    {10: struct.pack("<H", 20)},
                    "LEN_KM",
                    r"DBF field widths do not match its record length$",
                ),
                ("unknown_field", {}, "OTHER", r"has no DBF field named 'OTHER'$"),
                ("character_field", {43: b"C"}, "LEN_KM", r"^DBF field 'LEN_KM' must be numeric$"),
                ("truncated_records", {4: struct.pack("<I", 100)}, "LEN_KM", r"DBF record data is truncated$"),
                (
                    "bad_deletion_flag",
                    {65: b"X"},
                    "LEN_KM",
                    r"has an invalid DBF deletion flag in record 0$",
                ),
                (
                    "non_ascii_value",
                    {66: b"\xff"},
                    "LEN_KM",
                    r"^DBF field 'LEN_KM' contains non-ASCII numeric data$",
                ),
                (
                    "non_numeric_value",
                    {66: b"abcdefghijkl"},
                    "LEN_KM",
                    r"^DBF field 'LEN_KM' contains a non-numeric value$",
                ),
            ]
            for label, patches, property_name, message in cases:
                with self.subTest(case=label):
                    shapefile = self._write_pair(root, label, [10.0, 20.0])
                    dbf_path = shapefile.with_suffix(".dbf")
                    dbf_path.write_bytes(_patch_bytes(dbf_path.read_bytes(), patches))
                    with self.assertRaisesRegex(CalibrationError, message):
                        _derive_one(
                            shapefile,
                            format="shapefile",
                            property=property_name,
                            statistic="mean",
                        )

            tiny = self._write_pair(root, "tiny", [1.0])
            tiny.with_suffix(".dbf").write_bytes(b"\x00" * 10)
            with self.assertRaisesRegex(CalibrationError, r"is too small to be a DBF file$"):
                _derive_one(tiny, format="shapefile", property="LEN_KM", statistic="mean")

            duplicated = root / "duplicated.shp"
            write_polyline_shapefile(duplicated)
            duplicate_dbf = duplicated.with_suffix(".dbf")
            write_dbf_table(duplicate_dbf, {"AAA": [1.0], "BBB": [2.0]})
            duplicate_dbf.write_bytes(
                _patch_bytes(duplicate_dbf.read_bytes(), {64: b"AAA" + b"\x00" * 8})
            )
            with self.assertRaisesRegex(CalibrationError, r"duplicates DBF field 'AAA'$"):
                _derive_one(duplicated, format="shapefile", property="AAA", statistic="mean")

    def test_deleted_and_blank_dbf_records_are_skipped(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            deleted = self._write_pair(root, "deleted", [10.0, 20.0])
            deleted_dbf = deleted.with_suffix(".dbf")
            deleted_dbf.write_bytes(_patch_bytes(deleted_dbf.read_bytes(), {65: b"*"}))
            self.assertEqual(
                _derive_one(
                    deleted,
                    format="shapefile",
                    property="LEN_KM",
                    statistic="mean",
                    tolerance_abs=0.0,
                )["source_value"],
                20.0,
            )

            blank = root / "blank.shp"
            write_polyline_shapefile(blank)
            write_dbf_table(blank.with_suffix(".dbf"), {"LEN_KM": [None, 8.0]})
            self.assertEqual(
                _derive_one(
                    blank,
                    format="shapefile",
                    property="LEN_KM",
                    statistic="mean",
                    tolerance_abs=0.0,
                )["source_value"],
                8.0,
            )

            empty = root / "empty.shp"
            write_polyline_shapefile(empty)
            write_dbf_table(empty.with_suffix(".dbf"), {"LEN_KM": [None, None]})
            with self.assertRaisesRegex(
                CalibrationError,
                r"has no numeric DBF values for 'LEN_KM'$",
            ):
                _derive_one(empty, format="shapefile", property="LEN_KM", statistic="mean")

    def test_explicit_and_missing_dbf_paths(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            shapefile = root / "lines.shp"
            write_polyline_shapefile(shapefile)
            with self.assertRaisesRegex(
                CalibrationError,
                r"^shapefile DBF attribute table does not exist: .*lines\.dbf$",
            ):
                _derive_one(shapefile, format="shapefile", property="LEN_KM", statistic="mean")

            sidecar = root / "attributes.dbf"
            write_dbf(sidecar, "LEN_KM", [4.0, 6.0])
            target = _derive_one(
                shapefile,
                format="shapefile",
                dbf_path=str(sidecar),
                property="LEN_KM",
                statistic="mean",
                tolerance_abs=0.0,
            )
            self.assertEqual(target["source_value"], 5.0)
            self.assertEqual(target["source_dbf"], str(sidecar))


_RELIEF_LATITUDES = [-80.0, -30.0, 30.0, 80.0]
_RELIEF_LONGITUDES = [-170.0, -60.0, 60.0, 170.0]
_RELIEF_ROWS = [
    [-1000.0, -1000.0, -1000.0, -1000.0],
    [-1000.0, -1000.0, -1000.0, -1000.0],
    [1000.0, 1000.0, 1000.0, 1000.0],
    [1000.0, 1000.0, 1000.0, 1000.0],
]


def _relief_source(path: Path, **extra: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "format": "opendap_ascii_grid",
        "statistic": "fibonacci_ocean_fraction",
        "sample_cell_count": 128,
        "tolerance_abs": 0.0,
    }
    options.update(extra)
    return _source(path, **options)


class OpendapReliefTests(TestCase):
    def test_relief_statistics_sample_grid_edges(self) -> None:
        with TemporaryDirectory() as tmpdir:
            grid = Path(tmpdir) / "relief.dap.txt"
            write_opendap_ascii_grid(grid, _RELIEF_ROWS, _RELIEF_LATITUDES, _RELIEF_LONGITUDES)
            expected = {
                "fibonacci_ocean_fraction": 0.5,
                "fibonacci_mean_land_elevation_m": 1000.0,
                "fibonacci_hypsometric_span_m": 2000.0,
            }
            for statistic, value in expected.items():
                with self.subTest(statistic=statistic):
                    target = _derive_one(
                        grid,
                        format="dap_ascii",
                        statistic=statistic,
                        sample_cell_count=128,
                        tolerance_abs=0.0,
                    )
                    self.assertEqual(target["source_format"], "opendap_ascii_grid")
                    self.assertEqual(target["source_value"], value)
            target = derive_calibration_targets([_relief_source(grid)])["targets"][0]
            self.assertEqual(target["source_sample_land_cell_count"], 64)
            self.assertEqual(target["source_sample_ocean_cell_count"], 64)
            self.assertEqual(target["source_grid_latitude_min_deg"], -80.0)
            self.assertEqual(target["source_grid_latitude_max_deg"], 80.0)
            self.assertEqual(target["source_grid_latitude_step_deg"], 50.0)
            self.assertEqual(target["source_grid_longitude_step_deg"], 110.0)
            self.assertEqual(target["source_sample_min_elevation_m"], -1000.0)
            self.assertEqual(target["source_sample_max_elevation_m"], 1000.0)

    def test_malformed_opendap_grids_are_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            reference = root / "reference.dap.txt"
            write_opendap_ascii_grid(reference, _RELIEF_ROWS, _RELIEF_LATITUDES, _RELIEF_LONGITUDES)
            text = reference.read_text(encoding="utf-8")
            cases = [
                (
                    "missing_grid_header",
                    text.replace("z.z[4][4]\n", ""),
                    r"is missing OPeNDAP grid header 'z\.z\[rows\]\[columns\]'$",
                ),
                (
                    "zero_rows",
                    text.replace("z.z[4][4]", "z.z[0][4]"),
                    r"has invalid or excessive OPeNDAP grid dimensions$",
                ),
                (
                    "out_of_order_row",
                    text.replace("[1],", "[3],", 1),
                    r"has malformed or out-of-order OPeNDAP grid row 1$",
                ),
                (
                    "short_row",
                    text.replace("[0], -1000.0, -1000.0, -1000.0, -1000.0", "[0], -1000.0, -1000.0"),
                    r"OPeNDAP grid row 0 has 2 values; expected 4$",
                ),
                (
                    "non_numeric_row_value",
                    text.replace("[0], -1000.0,", "[0], deep,", 1),
                    r"OPeNDAP grid row 0 contains a non-numeric value$",
                ),
                (
                    "non_finite_row_value",
                    text.replace("[0], -1000.0,", "[0], nan,", 1),
                    r"OPeNDAP grid row 0 contains a non-finite value$",
                ),
                (
                    "truncated_rows",
                    text.split("[2],")[0],
                    r"^OPeNDAP ASCII source is missing grid row 2$",
                ),
                (
                    "latitude_dimension_mismatch",
                    text.replace("z.lat[4]", "z.lat[3]"),
                    r"OPeNDAP lat dimension does not match the grid$",
                ),
                (
                    "missing_latitudes",
                    text.replace("z.lat[4]\n", ""),
                    r"is missing OPeNDAP lat coordinates$",
                ),
                (
                    "missing_longitude_values",
                    text[: text.index("z.lon[4]") + len("z.lon[4]")] + "\n",
                    r"^OPeNDAP ASCII source is missing lon coordinate values$",
                ),
                (
                    "unsorted_latitudes",
                    text.replace("-80.0, -30.0, 30.0, 80.0", "-80.0, 30.0, -30.0, 80.0"),
                    r"OPeNDAP latitudes must be strictly increasing$",
                ),
                (
                    "unsorted_longitudes",
                    text.replace("-170.0, -60.0, 60.0, 170.0", "-170.0, 60.0, -60.0, 170.0"),
                    r"OPeNDAP longitudes must be strictly increasing$",
                ),
            ]
            for label, payload, message in cases:
                with self.subTest(case=label):
                    grid = root / f"{label}.dap.txt"
                    grid.write_text(payload, encoding="utf-8")
                    with self.assertRaisesRegex(CalibrationError, message):
                        derive_calibration_targets([_relief_source(grid)])

            binary = root / "binary.dap.txt"
            binary.write_bytes(b"z.z[1][1]\n[0], \xff\n")
            with self.assertRaisesRegex(
                CalibrationError,
                r"is not a UTF-8 OPeNDAP ASCII response$",
            ):
                derive_calibration_targets([_relief_source(binary)])

            with self.assertRaisesRegex(
                CalibrationError,
                r"^calibration source OPeNDAP 'variable' must be an identifier$",
            ):
                derive_calibration_targets([_relief_source(reference, variable="1z")])

    def test_relief_sampling_requires_a_global_two_phase_grid(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            regional = root / "regional.dap.txt"
            write_opendap_ascii_grid(regional, _RELIEF_ROWS, [-70.0, -30.0, 30.0, 70.0], _RELIEF_LONGITUDES)
            with self.assertRaisesRegex(
                CalibrationError,
                r"^matched Fibonacci relief statistics require a global OPeNDAP grid$",
            ):
                derive_calibration_targets([_relief_source(regional)])

            dry = root / "dry.dap.txt"
            write_opendap_ascii_grid(
                dry,
                [[1000.0] * 4 for _ in range(4)],
                _RELIEF_LATITUDES,
                _RELIEF_LONGITUDES,
            )
            with self.assertRaisesRegex(
                CalibrationError,
                r"^matched Fibonacci relief statistics require both land and ocean samples$",
            ):
                derive_calibration_targets([_relief_source(dry)])

            filled = root / "filled.dap.txt"
            write_opendap_ascii_grid(
                filled,
                [[-99999.0] * 4 for _ in range(4)],
                _RELIEF_LATITUDES,
                _RELIEF_LONGITUDES,
            )
            with self.assertRaisesRegex(
                CalibrationError,
                r"has a fill value at a sampled Fibonacci point$",
            ):
                derive_calibration_targets([_relief_source(filled)])

            reference = root / "reference.dap.txt"
            write_opendap_ascii_grid(reference, _RELIEF_ROWS, _RELIEF_LATITUDES, _RELIEF_LONGITUDES)
            with self.assertRaisesRegex(
                CalibrationError,
                r"^calibration source 'sample_cell_count' must be at least 128$",
            ):
                derive_calibration_targets(
                    [_relief_source(reference, sample_cell_count=127)]
                )
            with self.assertRaisesRegex(
                CalibrationError,
                r"^calibration source 'fill_value' must be numeric$",
            ):
                derive_calibration_targets(
                    [_relief_source(reference, fill_value="deep")]
                )


class CoastalSamplingTests(TestCase):
    def test_coastal_sampling_rejects_unsuitable_geometry(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            western = [(-180.0, -90.0), (0.0, -90.0), (0.0, 90.0), (-180.0, 90.0), (-180.0, -90.0)]

            projected = root / "projected.shp"
            write_polygon_shapefile(projected, western)
            with self.assertRaisesRegex(
                CalibrationError,
                r"^fibonacci_coastal_land_fraction requires geographic lon/lat polygons$",
            ):
                _derive_one(
                    projected,
                    format="shapefile",
                    statistic="fibonacci_coastal_land_fraction",
                    coordinate_system="projected_m",
                    sample_cell_count=128,
                )

            lines = root / "lines.shp"
            write_polyline_shapefile(lines)
            with self.assertRaisesRegex(
                CalibrationError,
                r"^fibonacci_coastal_land_fraction requires a polygon shapefile$",
            ):
                _derive_one(
                    lines,
                    format="shapefile",
                    statistic="fibonacci_coastal_land_fraction",
                    sample_cell_count=128,
                )

            whole_globe = root / "globe.shp"
            write_polygon_shapefile(
                whole_globe,
                [(-180.0, -90.0), (180.0, -90.0), (180.0, 90.0), (-180.0, 90.0), (-180.0, -90.0)],
            )
            degenerate = root / "degenerate.shp"
            write_polygon_shapefile(degenerate, [(-10.0, -10.0), (10.0, 10.0)])
            for label, shapefile in [("all_land", whole_globe), ("all_water", degenerate)]:
                with self.subTest(case=label):
                    with self.assertRaisesRegex(
                        CalibrationError,
                        r"^fibonacci_coastal_land_fraction requires sampled polygons "
                        r"containing both land and water cells$",
                    ):
                        _derive_one(
                            shapefile,
                            format="shapefile",
                            statistic="fibonacci_coastal_land_fraction",
                            sample_cell_count=128,
                            sample_neighbor_count=4,
                        )


def _worldclim_source(path: Path, **extra: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "format": "worldclim_geotiff_zip",
        "statistic": "fibonacci_mean_land_annual_temperature_c",
        "sample_cell_count": 128,
        "tolerance_abs": 0.0,
    }
    options.update(extra)
    return _source(path, **options)


class WorldClimArchiveTests(TestCase):
    def test_monthly_geotiff_members_drive_annual_land_statistics(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            temperature = root / "wc2.1_10m_tavg.zip"
            _write_worldclim_archive(temperature, {month: [float(month)] * 16 for month in range(1, 13)})

            target = derive_calibration_targets([_worldclim_source(temperature)])["targets"][0]
            self.assertEqual(target["source_format"], "worldclim_geotiff_zip")
            self.assertEqual(target["source_value"], 6.5)
            self.assertEqual(target["source_sample_cell_count"], 128)
            self.assertEqual(target["source_sample_complete_land_cell_count"], 128)
            self.assertEqual(target["source_sample_complete_land_fraction"], 1.0)
            self.assertEqual(target["source_sample_excluded_cell_count"], 0)
            self.assertEqual(target["source_sample_month_count"], 12)
            self.assertEqual(target["source_grid_width"], 4)
            self.assertEqual(target["source_grid_height"], 4)
            self.assertEqual(target["source_grid_origin_lon_deg"], -180.0)
            self.assertEqual(target["source_grid_origin_lat_deg"], 90.0)
            self.assertEqual(target["source_grid_pixel_width_deg"], 90.0)
            self.assertEqual(target["source_grid_pixel_height_deg"], 45.0)
            self.assertEqual(target["source_sample_min_value"], 1.0)
            self.assertEqual(target["source_sample_max_value"], 12.0)
            self.assertEqual(target["source_sample_mean_land_annual_temperature_c"], 6.5)
            self.assertEqual(target["source_sample_mean_land_annual_temperature_range_c"], 11.0)

            range_target = derive_calibration_targets(
                [
                    _worldclim_source(
                        temperature,
                        statistic="fibonacci_mean_land_annual_temperature_range_c",
                        format="geotiff_zip",
                    )
                ]
            )["targets"][0]
            self.assertEqual(range_target["source_value"], 11.0)

            scaled = derive_calibration_targets(
                [_worldclim_source(temperature, value_scale=2.0, value_offset=1.0)]
            )["targets"][0]
            self.assertEqual(scaled["source_value"], 14.0)
            self.assertEqual(scaled["source_sample_min_value"], 3.0)
            self.assertEqual(scaled["source_sample_max_value"], 25.0)

            precipitation = root / "wc2.1_10m_prec.zip"
            _write_worldclim_archive(
                precipitation,
                {month: [10.0 * month] * 16 for month in range(1, 13)},
                variable="prec",
            )
            precipitation_target = derive_calibration_targets(
                [
                    _worldclim_source(
                        precipitation,
                        statistic="fibonacci_mean_land_annual_precipitation_mm",
                    )
                ]
            )["targets"][0]
            self.assertEqual(precipitation_target["source_value"], 780.0)
            self.assertEqual(
                precipitation_target["source_sample_mean_land_annual_precipitation_mm"],
                780.0,
            )
            self.assertNotIn("source_sample_mean_land_annual_temperature_c", precipitation_target)

    def test_nodata_pixels_exclude_incomplete_cells(self) -> None:
        with TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "partial.zip"
            monthly = {month: [float(month)] * 16 for month in range(1, 13)}
            monthly[1] = [-9999.0] + [1.0] * 15
            _write_worldclim_archive(archive, monthly)

            target = derive_calibration_targets([_worldclim_source(archive)])["targets"][0]

            self.assertEqual(target["source_sample_complete_land_cell_count"], 124)
            self.assertEqual(target["source_sample_excluded_cell_count"], 4)
            self.assertEqual(target["source_sample_complete_land_fraction"], 124 / 128)
            self.assertEqual(target["source_value"], 6.5)

    def test_malformed_worldclim_archives_are_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            complete = {month: [float(month)] * 16 for month in range(1, 13)}

            missing_month = root / "missing_month.zip"
            _write_worldclim_archive(
                missing_month,
                {month: values for month, values in complete.items() if month != 12},
            )
            with self.assertRaisesRegex(
                CalibrationError,
                r"must contain exactly one WorldClim member ending in '_tavg_12\.tif'$",
            ):
                derive_calibration_targets([_worldclim_source(missing_month)])

            duplicated = root / "duplicated.zip"
            _write_worldclim_archive(duplicated, complete, duplicate_months=(1,))
            with self.assertRaisesRegex(
                CalibrationError,
                r"must contain exactly one WorldClim member ending in '_tavg_01\.tif'$",
            ):
                derive_calibration_targets([_worldclim_source(duplicated)])

            empty_member = root / "empty_member.zip"
            _write_worldclim_archive(empty_member, complete, empty_months=(3,))
            with self.assertRaisesRegex(
                CalibrationError,
                r"WorldClim member 'wc2\.1_10m_tavg_03\.tif' has an invalid size$",
            ):
                derive_calibration_targets([_worldclim_source(empty_member)])

            misaligned = root / "misaligned.zip"
            misaligned_months = dict(complete)
            misaligned_months[2] = [2.0] * 4
            _write_worldclim_archive(
                misaligned,
                misaligned_months,
                month_grid_shape={2: (2, 2)},
            )
            with self.assertRaisesRegex(
                CalibrationError,
                r"WorldClim monthly GeoTIFF grids do not align$",
            ):
                derive_calibration_targets([_worldclim_source(misaligned)])

            not_a_zip = root / "not_a_zip.zip"
            not_a_zip.write_bytes(b"definitely not a zip archive")
            with self.assertRaisesRegex(
                CalibrationError,
                r"^invalid WorldClim GeoTIFF archive .*not_a_zip\.zip: ",
            ):
                derive_calibration_targets([_worldclim_source(not_a_zip)])

            corrupt = root / "corrupt.zip"
            with ZipFile(corrupt, "w", compression=ZIP_DEFLATED) as broken:
                for month in range(1, 13):
                    broken.writestr(f"wc2.1_10m_tavg_{month:02}.tif", b"XX not a geotiff")
            with self.assertRaisesRegex(
                CalibrationError,
                r"^invalid WorldClim GeoTIFF archive .*corrupt\.zip: ",
            ):
                derive_calibration_targets([_worldclim_source(corrupt)])

            all_nodata = root / "all_nodata.zip"
            _write_worldclim_archive(
                all_nodata,
                {month: [-9999.0] * 16 for month in range(1, 13)},
            )
            with self.assertRaisesRegex(
                CalibrationError,
                r"has no complete twelve-month WorldClim land samples$",
            ):
                derive_calibration_targets([_worldclim_source(all_nodata)])

    def test_worldclim_sources_validate_their_variable_and_sampling(self) -> None:
        with TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "wc2.1_10m_tavg.zip"
            _write_worldclim_archive(archive, {month: [float(month)] * 16 for month in range(1, 13)})
            cases = [
                (
                    "variable_mismatch",
                    {"variable": "prec"},
                    r"^fibonacci_mean_land_annual_temperature_c requires WorldClim variable 'tavg'$",
                ),
                (
                    "precipitation_variable_mismatch",
                    {
                        "statistic": "fibonacci_mean_land_annual_precipitation_mm",
                        "variable": "tavg",
                    },
                    r"^fibonacci_mean_land_annual_precipitation_mm requires WorldClim variable 'prec'$",
                ),
                (
                    "small_sample",
                    {"sample_cell_count": 64},
                    r"^calibration source 'sample_cell_count' must be at least 128$",
                ),
                (
                    "non_numeric_scale",
                    {"value_scale": "double"},
                    r"^calibration source 'value_scale' must be numeric$",
                ),
                (
                    "non_finite_offset",
                    {"value_offset": float("inf")},
                    r"^calibration source 'value_offset' must be finite$",
                ),
            ]
            for label, extra, message in cases:
                with self.subTest(case=label):
                    with self.assertRaisesRegex(CalibrationError, message):
                        derive_calibration_targets([_worldclim_source(archive, **extra)])


def _hydrobasins_source(path: Path, **extra: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "metric": "hydrobasins_endorheic_basin_fraction",
        "world_metric": "non_antarctic_endorheic_watershed_fraction",
        "format": "hydrobasins_archive_catalog",
        "statistic": "hydrobasins_endorheic_basin_fraction",
        "tolerance_abs": 0.0,
    }
    options.update(extra)
    return _source(path, **options)


class HydrobasinsCatalogTests(TestCase):
    def _write_archive(
        self,
        root: Path,
        region: str,
        columns: dict[str, list[float | None]],
        *,
        extra_members: dict[str, bytes] | None = None,
    ) -> Path:
        dbf_path = root / f"hybas_{region}_lev03_v1c.dbf"
        write_dbf_table(dbf_path, columns)
        archive_path = root / f"hybas_{region}_lev03_v1c.zip"
        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            archive.write(dbf_path, dbf_path.name)
            for name, payload in (extra_members or {}).items():
                archive.writestr(name, payload)
        return archive_path

    def _write_catalog(self, path: Path, payload: Any) -> Path:
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_malformed_hydrobasins_catalogs_are_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            archive = self._write_archive(root, "aa", {"ENDO": [0.0, 1.0], "SUB_AREA": [100.0, 50.0]})
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            entry = {"region": "aa", "path": archive.name, "sha256": digest}
            cases = [
                ("not_an_object", ["archives"], r"HydroBASINS catalog must be an object$"),
                (
                    "missing_archives",
                    {"pfafstetter_level": 3},
                    r"HydroBASINS catalog requires a non-empty 'archives' list$",
                ),
                (
                    "empty_archives",
                    {"pfafstetter_level": 3, "archives": []},
                    r"HydroBASINS catalog requires a non-empty 'archives' list$",
                ),
                (
                    "missing_level",
                    {"archives": [entry]},
                    r"HydroBASINS catalog requires integer pfafstetter_level$",
                ),
                (
                    "non_numeric_level",
                    {"pfafstetter_level": "three", "archives": [entry]},
                    r"HydroBASINS catalog requires integer pfafstetter_level$",
                ),
                (
                    "level_out_of_range",
                    {"pfafstetter_level": 13, "archives": [entry]},
                    r"HydroBASINS Pfafstetter level must be between 1 and 12$",
                ),
                (
                    "archive_entry_not_object",
                    {"pfafstetter_level": 3, "archives": ["aa"]},
                    r"HydroBASINS archive entries must be objects$",
                ),
                (
                    "duplicate_region",
                    {"pfafstetter_level": 3, "archives": [entry, dict(entry)]},
                    r"duplicates HydroBASINS region 'aa'$",
                ),
                (
                    "missing_archive_file",
                    {
                        "pfafstetter_level": 3,
                        "archives": [{**entry, "path": "hybas_zz_lev03_v1c.zip"}],
                    },
                    r"^HydroBASINS archive does not exist: .*hybas_zz_lev03_v1c\.zip$",
                ),
                (
                    "invalid_sha256",
                    {"pfafstetter_level": 3, "archives": [{**entry, "sha256": "abcd"}]},
                    r"^HydroBASINS region 'aa' has an invalid SHA-256$",
                ),
            ]
            for label, payload, message in cases:
                with self.subTest(case=label):
                    catalog = self._write_catalog(root / f"{label}.json", payload)
                    with self.assertRaisesRegex(CalibrationError, message):
                        derive_calibration_targets([_hydrobasins_source(catalog)])

    def test_malformed_hydrobasins_archives_are_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)

            two_dbfs = self._write_archive(
                root,
                "bb",
                {"ENDO": [0.0], "SUB_AREA": [100.0]},
                extra_members={"second.dbf": b"\x00" * 40},
            )
            empty_member = root / "hybas_cc_lev03_v1c.zip"
            with ZipFile(empty_member, "w", compression=ZIP_DEFLATED) as archive:
                archive.writestr("hybas_cc_lev03_v1c.dbf", b"")
            not_a_zip = root / "hybas_dd_lev03_v1c.zip"
            not_a_zip.write_bytes(b"not a zip archive at all")
            bad_endo = self._write_archive(root, "ee", {"ENDO": [3.0], "SUB_AREA": [100.0]})
            bad_area = self._write_archive(root, "ff", {"ENDO": [0.0], "SUB_AREA": [-5.0]})

            cases = [
                ("two_dbfs", two_dbfs, r"must contain exactly one DBF file$"),
                (
                    "empty_dbf_member",
                    empty_member,
                    r"^HydroBASINS DBF member has an invalid size: hybas_cc_lev03_v1c\.dbf$",
                ),
                ("not_a_zip", not_a_zip, r"^invalid HydroBASINS ZIP archive .*hybas_dd_lev03_v1c\.zip$"),
                ("invalid_endo", bad_endo, r"contains invalid ENDO value 3\.0$"),
                ("invalid_sub_area", bad_area, r"contains invalid SUB_AREA value -5\.0$"),
            ]
            for label, archive_path, message in cases:
                with self.subTest(case=label):
                    catalog = self._write_catalog(
                        root / f"{label}.json",
                        {
                            "pfafstetter_level": 3,
                            "archives": [
                                {
                                    "region": label,
                                    "path": str(archive_path),
                                    "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
                                }
                            ],
                        },
                    )
                    with self.assertRaisesRegex(CalibrationError, message):
                        derive_calibration_targets([_hydrobasins_source(catalog)])


class HydroriversArchiveTests(TestCase):
    _COLUMNS = {
        "NEXT_DOWN": [0.0, 0.0, 0.0],
        "ENDORHEIC": [0.0, 0.0, 0.0],
        "ORD_CLAS": [1.0, 1.0, 1.0],
        "UPLAND_SKM": [1_000_000.0, 1_440_000.0, 1_690_000.0],
        "DIST_UP_KM": [2_000.0, 2_400.0, 2_600.0],
    }

    def test_malformed_hydrorivers_archives_are_rejected(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            valid = _hydrorivers_dbf_bytes(root, self._COLUMNS)

            two_dbfs = root / "two_dbfs.zip"
            _write_hydrorivers_archive(two_dbfs, {"a.dbf": valid, "b.dbf": valid})
            empty_member = root / "empty_member.zip"
            _write_hydrorivers_archive(empty_member, {"a.dbf": b""})
            not_a_zip = root / "not_a_zip.zip"
            not_a_zip.write_bytes(b"not a zip archive at all")
            invalid_values = root / "invalid_values.zip"
            _write_hydrorivers_archive(
                invalid_values,
                {"a.dbf": _hydrorivers_dbf_bytes(root, {**self._COLUMNS, "ENDORHEIC": [0.0, 2.0, 0.0]})},
            )
            too_few = root / "too_few.zip"
            _write_hydrorivers_archive(
                too_few,
                {
                    "a.dbf": _hydrorivers_dbf_bytes(
                        root,
                        {**self._COLUMNS, "UPLAND_SKM": [1_000_000.0, 900_000.0, 800_000.0]},
                    )
                },
            )
            single_area = root / "single_area.zip"
            _write_hydrorivers_archive(
                single_area,
                {
                    "a.dbf": _hydrorivers_dbf_bytes(
                        root,
                        {**self._COLUMNS, "UPLAND_SKM": [1_000_000.0, 1_000_000.0, 1_000_000.0]},
                    )
                },
            )

            cases = [
                ("two_dbfs", two_dbfs, r"must contain exactly one DBF file$"),
                ("empty_member", empty_member, r"^HydroRIVERS DBF member has an invalid size: a\.dbf$"),
                ("not_a_zip", not_a_zip, r"^invalid HydroRIVERS ZIP archive .*not_a_zip\.zip$"),
                ("invalid_values", invalid_values, r"contains invalid HydroRIVERS numeric values$"),
                (
                    "too_few_observations",
                    too_few,
                    r"has insufficient HydroRIVERS outlet observations at or above 1000000\.0 km2$",
                ),
                (
                    "single_distinct_area",
                    single_area,
                    r"has insufficient HydroRIVERS outlet observations at or above 1000000\.0 km2$",
                ),
            ]
            for label, archive_path, message in cases:
                with self.subTest(case=label):
                    with self.assertRaisesRegex(CalibrationError, message):
                        derive_calibration_targets([_hydrorivers_source(archive_path)])

    def test_streamed_dbf_records_reject_malformed_tables(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            valid = _hydrorivers_dbf_bytes(root, self._COLUMNS)
            cases = [
                ("header_length_too_small", {8: struct.pack("<H", 10)}, r"has invalid DBF header lengths$"),
                ("zero_record_length", {10: struct.pack("<H", 0)}, r"has invalid DBF header lengths$"),
                ("truncated_header", {8: struct.pack("<H", 4_000)}, r"has a truncated DBF header$"),
                (
                    "truncated_descriptor",
                    {8: struct.pack("<H", 100)},
                    r"has a truncated DBF field descriptor$",
                ),
                ("blank_field_name", {32: b"\x00" * 11}, r"has an invalid DBF field descriptor$"),
                ("zero_field_length", {48: b"\x00"}, r"has an invalid DBF field descriptor$"),
                ("no_fields", {32: b"\x0d"}, r"has no DBF fields$"),
                (
                    "duplicate_field",
                    {64: b"NEXT_DOWN\x00\x00"},
                    r"duplicates DBF field 'NEXT_DOWN'$",
                ),
                (
                    "record_width_mismatch",
                    {10: struct.pack("<H", 80)},
                    r"DBF field widths do not match its record length$",
                ),
                (
                    "renamed_field",
                    {160: b"DIST_UP_XX\x00"},
                    r"has no DBF field named 'DIST_UP_KM'$",
                ),
                ("character_field", {43: b"C"}, r"^DBF field 'NEXT_DOWN' must be numeric$"),
                (
                    "truncated_records",
                    {4: struct.pack("<I", 10)},
                    r"DBF record data is truncated at record 3$",
                ),
                (
                    "bad_deletion_flag",
                    {193: b"X"},
                    r"has an invalid DBF deletion flag in record 0$",
                ),
                (
                    "non_ascii_value",
                    {194: b"\xff"},
                    r"^DBF field 'NEXT_DOWN' contains non-ASCII numeric data$",
                ),
                (
                    "non_numeric_value",
                    {194: b"abcdefghijklmn"},
                    r"^DBF field 'NEXT_DOWN' contains a non-numeric value$",
                ),
            ]
            for label, patches, message in cases:
                with self.subTest(case=label):
                    archive_path = root / f"{label}.zip"
                    _write_hydrorivers_archive(
                        archive_path, {"reaches.dbf": _patch_bytes(valid, patches)}
                    )
                    with self.assertRaisesRegex(CalibrationError, message):
                        derive_calibration_targets([_hydrorivers_source(archive_path)])

            tiny = root / "tiny.zip"
            _write_hydrorivers_archive(tiny, {"reaches.dbf": b"\x00" * 10})
            with self.assertRaisesRegex(CalibrationError, r"is too small to be a DBF file$"):
                derive_calibration_targets([_hydrorivers_source(tiny)])

    def test_deleted_streamed_records_are_skipped(self) -> None:
        # The three active reaches lie exactly on length = 2 * sqrt(area), so the Hack
        # fit must recover exponent 0.5 and coefficient 2.0.  The deleted record is a
        # qualifying outlet (area above the 1e6 km2 floor) that sits far off that line,
        # so including it would move the exponent, the network count, and the sampled
        # area range -- every assertion below fails if the deletion flag is ignored.
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            payload = _hydrorivers_dbf_bytes(
                root,
                {
                    "NEXT_DOWN": [0.0, 0.0, 0.0, 0.0],
                    "ENDORHEIC": [0.0, 0.0, 0.0, 0.0],
                    "ORD_CLAS": [1.0, 1.0, 1.0, 1.0],
                    "UPLAND_SKM": [4_000_000.0, 1_000_000.0, 1_440_000.0, 1_690_000.0],
                    "DIST_UP_KM": [100.0, 2_000.0, 2_400.0, 2_600.0],
                },
            )
            archive_path = root / "deleted.zip"
            _write_hydrorivers_archive(
                archive_path, {"reaches.dbf": _patch_bytes(payload, {193: b"*"})}
            )

            target = derive_calibration_targets([_hydrorivers_source(archive_path)])["targets"][0]

            self.assertEqual(target["source_active_reach_record_count"], 3)
            self.assertEqual(target["source_sample_network_count"], 3)
            self.assertEqual(target["source_sample_min_upstream_area_km2"], 1_000_000.0)
            self.assertEqual(target["source_sample_max_upstream_area_km2"], 1_690_000.0)
            self.assertEqual(target["source_sample_max_upstream_distance_km"], 2_600.0)
            self.assertAlmostEqual(target["source_value"], 0.5, places=9)
            self.assertAlmostEqual(target["source_hack_fitted_coefficient"], 2.0, places=9)
            self.assertAlmostEqual(target["source_hack_fitted_log_rmse"], 0.0, places=9)


def _land_cell(**overrides: Any) -> dict[str, Any]:
    cell: dict[str, Any] = {
        "is_water": False,
        "temperature_monthly_c": [10.0] * 12,
        "precipitation_mm_y": 500.0,
    }
    cell.update(overrides)
    return cell


def _watershed(**overrides: Any) -> dict[str, Any]:
    watershed: dict[str, Any] = {
        "area_km2": 100.0,
        "is_endorheic": False,
        "outlet_type": "ocean",
    }
    watershed.update(overrides)
    return watershed


class WorldMetricValidationTests(TestCase):
    def test_malformed_world_payloads_are_rejected(self) -> None:
        cases = [
            (
                "checks_not_a_list",
                {"calibration_checks": {"metric": "a"}},
                r"^world calibration_checks must be a list$",
            ),
            (
                "check_not_an_object",
                {"calibration_checks": ["a"]},
                r"^each world calibration check must be an object$",
            ),
            (
                "check_value_not_numeric",
                {"calibration_checks": [{"metric": "a", "value": "high"}]},
                r"^world calibration metric 'a' must be numeric$",
            ),
            (
                "check_value_not_finite",
                {"calibration_checks": [{"metric": "a", "value": float("inf")}]},
                r"^world calibration metric 'a' must be finite$",
            ),
            (
                "conflicting_duplicate_check",
                {
                    "calibration_checks": [
                        {"metric": "a", "value": 1.0},
                        {"metric": "a", "value": 2.0},
                    ]
                },
                r"^world calibration metric 'a' is duplicated with conflicting values$",
            ),
            ("cell_not_an_object", {"cells": ["a"]}, r"^each world cell must be an object$"),
            (
                "partial_elevation",
                {"cells": [{"is_water": True, "elevation_m": 1.0}, {"is_water": True}]},
                r"^world cell elevation_m must be present for every cell or no cells$",
            ),
            (
                "elevation_not_numeric",
                {"cells": [{"is_water": True, "elevation_m": "high"}]},
                r"^world cell elevation_m must be numeric$",
            ),
            (
                "elevation_not_finite",
                {"cells": [{"is_water": True, "elevation_m": float("nan")}]},
                r"^world cell elevation_m must be finite$",
            ),
            (
                "no_nonnegative_elevation",
                {"cells": [{"is_water": True, "elevation_m": -100.0}]},
                r"^world has no nonnegative surface elevations$",
            ),
            (
                "elevation_conflicts_with_check",
                {
                    "calibration_checks": [
                        {"metric": "below_sea_level_surface_fraction", "value": 0.9}
                    ],
                    "cells": [
                        {"is_water": True, "elevation_m": -100.0},
                        {"is_water": True, "elevation_m": 100.0},
                    ],
                },
                r"^world calibration metric 'below_sea_level_surface_fraction' "
                r"conflicts with cell-derived value$",
            ),
            (
                "land_cell_without_monthly_temperatures",
                {"cells": [_land_cell(temperature_monthly_c=[1.0])]},
                r"^land cells require twelve monthly temperatures for external climate calibration$",
            ),
            (
                "land_climate_not_numeric",
                {"cells": [_land_cell(temperature_monthly_c=["warm"] * 12)]},
                r"^world land climate values must be numeric$",
            ),
            (
                "land_precipitation_missing",
                {"cells": [{"is_water": False, "temperature_monthly_c": [10.0] * 12}]},
                r"^world land climate values must be numeric$",
            ),
            (
                "land_climate_not_finite",
                {"cells": [_land_cell(precipitation_mm_y=float("inf"))]},
                r"^world land climate values must be finite$",
            ),
            (
                "land_climate_conflicts_with_check",
                {
                    "calibration_checks": [
                        {"metric": "mean_land_annual_temperature_c", "value": 99.0}
                    ],
                    "cells": [_land_cell()],
                },
                r"^world calibration metric 'mean_land_annual_temperature_c' "
                r"conflicts with cell-derived value$",
            ),
            (
                "watershed_not_an_object",
                {"watersheds": ["a"]},
                r"^each world watershed must be an object$",
            ),
            (
                "inconsistent_main_channel_length",
                {
                    "watersheds": [
                        _watershed(main_channel_length_km=10.0),
                        _watershed(),
                    ]
                },
                r"^world watersheds must provide main_channel_length_km consistently$",
            ),
            (
                "watershed_area_not_numeric",
                {"watersheds": [_watershed(area_km2="wide")]},
                r"^world watershed area_km2 must be numeric$",
            ),
            (
                "watershed_area_missing",
                {"watersheds": [{"is_endorheic": False, "outlet_type": "ocean"}]},
                r"^world watershed area_km2 must be numeric$",
            ),
            (
                "watershed_area_not_positive",
                {"watersheds": [_watershed(area_km2=0.0)]},
                r"^world watershed area_km2 must be finite and positive$",
            ),
            (
                "main_channel_length_not_numeric",
                {"watersheds": [_watershed(main_channel_length_km="long")]},
                r"^world watershed main_channel_length_km must be numeric$",
            ),
            (
                "main_channel_length_negative",
                {"watersheds": [_watershed(main_channel_length_km=-1.0)]},
                r"^world watershed main_channel_length_km must be finite and nonnegative$",
            ),
            (
                "is_endorheic_not_boolean",
                {"watersheds": [_watershed(is_endorheic="yes")]},
                r"^world watershed is_endorheic must be boolean$",
            ),
            (
                "outlet_type_not_a_string",
                {"watersheds": [_watershed(outlet_type="")]},
                r"^world watershed outlet_type must be a non-empty string$",
            ),
            (
                "inconsistent_centroids",
                {
                    "watersheds": [
                        _watershed(centroid_lat_deg=10.0),
                        _watershed(),
                    ]
                },
                r"^world watersheds must provide centroid_lat_deg consistently$",
            ),
            (
                "centroid_not_numeric",
                {"watersheds": [_watershed(centroid_lat_deg="north")]},
                r"^world watershed centroid_lat_deg must be numeric$",
            ),
            (
                "centroid_out_of_range",
                {"watersheds": [_watershed(centroid_lat_deg=120.0)]},
                r"^world watershed centroid_lat_deg must be finite and within \[-90, 90\]$",
            ),
            (
                "no_non_antarctic_watersheds",
                {"watersheds": [_watershed(centroid_lat_deg=-80.0)]},
                r"^world has no watersheds in HydroBASINS non-Antarctic coverage$",
            ),
            (
                "watershed_conflicts_with_check",
                {
                    "calibration_checks": [
                        {"metric": "endorheic_watershed_fraction", "value": 0.9}
                    ],
                    "watersheds": [
                        _watershed(),
                        _watershed(is_endorheic=True, outlet_type="closed_land"),
                    ],
                },
                r"^world calibration metric 'endorheic_watershed_fraction' "
                r"conflicts with watershed-derived value$",
            ),
        ]
        for label, world, message in cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(CalibrationError, message):
                    evaluate_calibration_targets(world, [])

    def test_watershed_hack_fits_reject_non_finite_regressions(self) -> None:
        # Control: three ocean outlets on length = 2 * sqrt(area) must fit exactly,
        # so the failures below come from the regression and not from the payloads.
        healthy = [
            _watershed(area_km2=1_000_000.0, main_channel_length_km=2_000.0),
            _watershed(area_km2=1_440_000.0, main_channel_length_km=2_400.0),
            _watershed(area_km2=1_690_000.0, main_channel_length_km=2_600.0),
        ]
        available = evaluate_calibration_targets(
            {"watersheds": healthy}, []
        )["available_world_metrics"]
        self.assertIn("watershed_hack_fitted_exponent", available)
        self.assertIn("exorheic_watershed_backbone_hack_fitted_exponent", available)
        fitted = evaluate_calibration_targets(
            {"watersheds": healthy},
            [
                {
                    "dataset": "d",
                    "layer": "l",
                    "metric": "watershed_hack_fitted_exponent",
                    "target_min": 0.5,
                    "target_max": 0.5,
                },
                {
                    "dataset": "d",
                    "layer": "l",
                    "metric": "exorheic_watershed_backbone_hack_fitted_coefficient",
                    "target_min": 2.0,
                    "target_max": 2.0,
                },
            ],
        )
        self.assertAlmostEqual(fitted["checks"][0]["value"], 0.5, places=9)
        self.assertAlmostEqual(fitted["checks"][1]["value"], 2.0, places=9)

        # Two outlets whose upstream areas differ by 0.1% while their channel lengths
        # differ by 600 orders of magnitude drive the log-space slope to about -1.4e6,
        # so exp(intercept) overflows.  The overflow must surface as a CalibrationError
        # instead of an infinite Hack exponent leaking into the metric table.
        outlier_a = _watershed(area_km2=1_000_000.0, main_channel_length_km=1.0e300)
        outlier_b = _watershed(area_km2=1_001_000.0, main_channel_length_km=1.0e-300)
        with self.assertRaisesRegex(
            CalibrationError,
            r"^world watershed Hack fit is invalid$",
        ):
            evaluate_calibration_targets({"watersheds": [outlier_a, outlier_b]}, [])

        # An endorheic basin joins only the all-watershed regression, so that fit stays
        # finite while the exorheic-backbone regression over the same two outliers still
        # overflows -- proving the two fits are guarded independently.
        endorheic = _watershed(
            area_km2=1.0e12,
            main_channel_length_km=1.0,
            is_endorheic=True,
            outlet_type="closed_land",
        )
        with self.assertRaisesRegex(
            CalibrationError,
            r"^world exorheic watershed-backbone Hack fit is invalid$",
        ):
            evaluate_calibration_targets(
                {"watersheds": [outlier_a, outlier_b, endorheic]}, []
            )


class OceanicCrustAgeLedgerTests(TestCase):
    _THRESHOLDS = [20.0, 40.0, 60.0, 80.0, 100.0, 120.0, 140.0, 160.0, 180.0, 200.0]

    def _world(self, **ledger_overrides: Any) -> dict[str, Any]:
        # Cell 0 is continental (status 0) and must be excluded.  The three oceanic
        # ages are 40, 200 and 50 Ma over equal 100 km2 cells: two of them sit exactly
        # on a CDF threshold, so the recorded CDF below is only reproducible with the
        # inclusive ``age <= threshold`` rule (a strict ``<`` yields 0.0 at 40 Ma and
        # 200/300 at 200 Ma, and the ledger cross-check then rejects the world).
        ledger: dict[str, Any] = {
            "age_ma_by_cell": [10.0, 40.0, 200.0, 50.0],
            "status_id_by_cell": [0, 1, 1, 2],
            "cdf_thresholds_ma": list(self._THRESHOLDS),
            "area_weighted_cdf_le_threshold": [
                0.0,
                100.0 / 300.0,
                *[200.0 / 300.0] * 7,
                1.0,
            ],
            "area_weighted_mean_age_ma": 29_000.0 / 300.0,
        }
        ledger.update(ledger_overrides)
        return {
            "calibration_checks": [],
            "cells": [{"is_water": True, "area_km2": 100.0} for _ in range(4)],
            "initial_oceanic_crust_age_ledger": ledger,
        }

    def test_ledger_derives_area_weighted_age_metrics(self) -> None:
        report = evaluate_calibration_targets(
            self._world(),
            [
                {
                    "dataset": "d",
                    "layer": "l",
                    "metric": "initial_oceanic_crust_age_area_weighted_mean_ma",
                    "target_min": 96.0,
                    "target_max": 97.0,
                },
                {
                    "dataset": "d",
                    "layer": "l",
                    "metric": "initial_oceanic_crust_age_area_weighted_cdf_le_60_ma",
                    "target_min": 0.6,
                    "target_max": 0.7,
                },
                {
                    "dataset": "d",
                    "layer": "l",
                    "metric": "initial_oceanic_crust_age_area_weighted_cdf_le_40_ma",
                    "target_min": 0.33,
                    "target_max": 0.34,
                },
                {
                    "dataset": "d",
                    "layer": "l",
                    "metric": "initial_oceanic_crust_age_area_weighted_cdf_le_200_ma",
                    "target_min": 0.99,
                    "target_max": 1.0,
                },
            ],
        )

        self.assertEqual(report["summary"]["external_calibration_pass_count"], 4)
        self.assertAlmostEqual(report["checks"][0]["value"], 29_000.0 / 300.0)
        self.assertAlmostEqual(report["checks"][1]["value"], 200.0 / 300.0)
        # The 40 Ma and 200 Ma cells land exactly on their thresholds and must be
        # counted: an exclusive comparison would report 0.0 and 200/300 here.
        self.assertAlmostEqual(report["checks"][2]["value"], 100.0 / 300.0)
        self.assertEqual(report["checks"][3]["value"], 1.0)
        self.assertIn(
            "initial_oceanic_crust_age_area_weighted_cdf_le_200_ma",
            report["available_world_metrics"],
        )
        self.assertNotIn(
            "initial_oceanic_crust_age_area_weighted_cdf_le_10_ma",
            report["available_world_metrics"],
        )

    def test_malformed_ledgers_are_rejected(self) -> None:
        cases = [
            (
                "wrong_age_cardinality",
                {"age_ma_by_cell": [10.0, 30.0]},
                r"^world initial oceanic crust age ledger has invalid cardinality$",
            ),
            (
                "thresholds_not_a_list",
                {"cdf_thresholds_ma": 20.0},
                r"^world initial oceanic crust age ledger has invalid cardinality$",
            ),
            (
                "ages_not_numeric",
                {"age_ma_by_cell": ["old", 30.0, 210.0, 50.0]},
                r"^world initial oceanic crust age ledger must be numeric$",
            ),
            (
                "unexpected_thresholds",
                {"cdf_thresholds_ma": [float(index) for index in range(10)]},
                r"^world initial oceanic crust age ledger values are invalid$",
            ),
            (
                "negative_age",
                {"age_ma_by_cell": [-1.0, 30.0, 210.0, 50.0]},
                r"^world initial oceanic crust age ledger values are invalid$",
            ),
            (
                "unknown_status",
                {"status_id_by_cell": [0, 1, 1, 9]},
                r"^world initial oceanic crust age ledger values are invalid$",
            ),
            (
                "cdf_out_of_range",
                {"area_weighted_cdf_le_threshold": [2.0] + [0.5] * 9},
                r"^world initial oceanic crust age ledger values are invalid$",
            ),
            (
                "no_oceanic_cells",
                {"status_id_by_cell": [0, 0, 0, 0]},
                r"^world initial oceanic crust age ledger has no oceanic-like cells$",
            ),
            (
                "mean_age_conflict",
                {"area_weighted_mean_age_ma": 1.0},
                r"^world initial oceanic crust age ledger summaries conflict "
                r"with cell-derived values$",
            ),
            (
                "cdf_conflict",
                {"area_weighted_cdf_le_threshold": [0.5] * 10},
                r"^world initial oceanic crust age ledger summaries conflict "
                r"with cell-derived values$",
            ),
        ]
        for label, overrides, message in cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(CalibrationError, message):
                    evaluate_calibration_targets(self._world(**overrides), [])

        not_an_object = self._world()
        not_an_object["initial_oceanic_crust_age_ledger"] = ["ages"]
        with self.assertRaisesRegex(
            CalibrationError,
            r"^world initial_oceanic_crust_age_ledger must be an object$",
        ):
            evaluate_calibration_targets(not_an_object, [])

        missing_area = self._world()
        missing_area["cells"] = [{"is_water": True} for _ in range(4)]
        with self.assertRaisesRegex(
            CalibrationError,
            r"^world initial oceanic crust age ledger must be numeric$",
        ):
            evaluate_calibration_targets(missing_area, [])

        zero_area = self._world()
        zero_area["cells"] = [{"is_water": True, "area_km2": 0.0} for _ in range(4)]
        with self.assertRaisesRegex(
            CalibrationError,
            r"^world initial oceanic crust age ledger values are invalid$",
        ):
            evaluate_calibration_targets(zero_area, [])


class EvaluateTargetValidationTests(TestCase):
    def test_targets_require_finite_ordered_bounds(self) -> None:
        world = {"calibration_checks": [{"metric": "ocean_fraction", "value": 0.5}]}
        base = {"dataset": "d", "layer": "l", "metric": "ocean_fraction"}
        cases = [
            ("missing_target_min", {"target_max": 1.0}, r"^calibration target missing 'target_min'$"),
            ("missing_target_max", {"target_min": 0.0}, r"^calibration target missing 'target_max'$"),
            (
                "inverted_range",
                {"target_min": 1.0, "target_max": 0.0},
                r"^target range for 'ocean_fraction' is inverted$",
            ),
        ]
        for label, bounds, message in cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(CalibrationError, message):
                    evaluate_calibration_targets(world, [{**base, **bounds}])

    def test_empty_target_lists_report_zeroed_summaries(self) -> None:
        report = evaluate_calibration_targets({"calibration_checks": []}, [])
        summary = report["summary"]
        self.assertEqual(summary["external_calibration_check_count"], 0)
        self.assertEqual(summary["external_calibration_metric_coverage_fraction"], 0.0)
        self.assertEqual(summary["external_calibration_pass_fraction"], 0.0)
        self.assertEqual(summary["external_calibration_evaluated_pass_fraction"], 0.0)
        self.assertEqual(summary["external_mean_calibration_score"], 0.0)
        self.assertEqual(summary["external_mean_evaluated_calibration_score"], 0.0)
        self.assertEqual(summary["external_calibration_evaluated_metric_count"], 0)
        self.assertEqual(summary["external_calibration_pass_count"], 0)
        self.assertEqual(summary["external_calibration_missing_metric_count"], 0)
        # An empty run is *not* complete: zero missing metrics alone must not pass.
        self.assertIs(summary["external_calibration_complete"], False)
        self.assertEqual(report["checks"], [])
        self.assertEqual(report["missing_world_metrics"], [])
        self.assertEqual(report["available_world_metrics"], [])


class CalibrationMarkdownTests(TestCase):
    def test_calibration_report_markdown_lists_status_and_provenance(self) -> None:
        world = {
            "calibration_checks": [
                {"metric": "ocean_fraction", "value": 0.7},
                {"metric": "land_fraction", "value": 0.1},
            ]
        }
        targets = [
            {
                "dataset": "natural_earth",
                "layer": "ocean",
                "metric": "ocean_fraction",
                "source_metric": "mask_fraction",
                "target_min": 0.6,
                "target_max": 0.8,
                "source": "ocean.shp",
                "source_version": "1.0",
                "source_sha256": "a" * 64,
                "tolerance_basis": "Test basis.",
            },
            {
                "dataset": "natural_earth",
                "layer": "land",
                "metric": "land_fraction",
                "target_min": 0.5,
                "target_max": 0.6,
            },
            {
                "dataset": "natural_earth",
                "layer": "coast",
                "metric": "absent_metric",
                "target_min": 0.0,
                "target_max": 1.0,
            },
        ]
        report = evaluate_calibration_targets(world, targets)

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nested" / "calibration.md"
            write_calibration_markdown(path, report)
            lines = path.read_text(encoding="utf-8").splitlines()

        self.assertEqual(lines[0], "# Calibration Report")
        self.assertEqual(lines[2], "## Summary")
        self.assertIn("- `external_calibration_check_count`: 3", lines)
        self.assertIn("- `external_calibration_missing_metric_count`: 1", lines)
        self.assertIn("- `external_calibration_complete`: False", lines)
        self.assertIn("## Checks", lines)
        self.assertIn(
            "- `ocean_fraction` (natural_earth/ocean): pass, value=0.7, target=[0.6, 0.8], "
            "score=1.0, source_metric=mask_fraction, source_version=1.0, "
            f"source_sha256={'a' * 64}, tolerance_basis=Test basis.",
            lines,
        )
        self.assertIn(
            "- `land_fraction` (natural_earth/land): fail, value=0.1, target=[0.5, 0.6], score=0.0",
            lines,
        )
        self.assertIn(
            "- `absent_metric` (natural_earth/coast): missing, value=None, target=[0.0, 1.0], score=0.0",
            lines,
        )

    def test_target_derivation_markdown_lists_sources(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            grid = root / "grid.asc"
            _write_ascii_grid(grid, _ASCII_GRID_HEADER, ["10 10 10", "10 10 10"])
            report = derive_calibration_targets(
                [
                    _source(
                        grid,
                        metric="grid_mean",
                        world_metric="world_mean",
                        statistic="mean",
                        tolerance_abs=1.0,
                        tolerance_basis="Test basis.",
                        source_version="2.0",
                    )
                ]
            )
            path = root / "nested" / "derivation.md"
            write_target_derivation_markdown(path, report)
            lines = path.read_text(encoding="utf-8").splitlines()

            self.assertEqual(lines[0], "# Calibration Target Derivation")
            self.assertIn("- `derived_target_count`: 1", lines)
            self.assertIn("- `source_count`: 1", lines)
            self.assertIn("- `mapped_target_count`: 1", lines)
            self.assertIn("- `unique_world_metric_count`: 1", lines)
            self.assertIn("## Targets", lines)
            digest = hashlib.sha256(grid.read_bytes()).hexdigest()
            self.assertIn(
                "- `world_mean` (unit_dataset/unit_layer): value=10.0, target=[9.0, 11.0], "
                f"source={grid}, source_metric=grid_mean, source_version=2.0, "
                f"source_sha256={digest}, tolerance_basis=Test basis.",
                lines,
            )

    def test_markdown_writers_tolerate_empty_reports(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            calibration = root / "empty-calibration.md"
            derivation = root / "empty-derivation.md"
            write_calibration_markdown(calibration, {})
            write_target_derivation_markdown(derivation, {})
            self.assertEqual(
                calibration.read_text(encoding="utf-8"),
                "# Calibration Report\n\n## Summary\n\n\n## Checks\n\n",
            )
            self.assertEqual(
                derivation.read_text(encoding="utf-8"),
                "# Calibration Target Derivation\n\n## Summary\n\n\n## Targets\n\n",
            )
