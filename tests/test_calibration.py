import hashlib
import json
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zipfile import ZIP_DEFLATED, ZipFile

from typer.testing import CliRunner

from magic_geo.calibration import (
    CalibrationError,
    derive_calibration_targets,
    evaluate_calibration_targets,
    load_calibration_sources,
)
from magic_geo.cli import app
from magic_geo.ensemble_calibration import load_calibration_ensemble_manifest


def _write_vector_shapefile(path: Path, shape_type: int, points: list[tuple[float, float]]) -> None:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    record_content = bytearray()
    record_content += struct.pack("<i", shape_type)
    record_content += struct.pack("<4d", *bbox)
    record_content += struct.pack("<2i", 1, len(points))
    record_content += struct.pack("<i", 0)
    for x, y in points:
        record_content += struct.pack("<2d", x, y)

    file_length_words = (100 + 8 + len(record_content)) // 2
    header = bytearray(100)
    struct.pack_into(">i", header, 0, 9994)
    struct.pack_into(">i", header, 24, file_length_words)
    struct.pack_into("<i", header, 28, 1000)
    struct.pack_into("<i", header, 32, shape_type)
    struct.pack_into("<4d", header, 36, *bbox)

    record_header = struct.pack(">2i", 1, len(record_content) // 2)
    path.write_bytes(bytes(header) + record_header + bytes(record_content))


def _write_polyline_shapefile(path: Path, points: list[tuple[float, float]] | None = None) -> None:
    _write_vector_shapefile(path, 3, points or [(0.0, 0.0), (0.0, 1.0)])


def _write_polygon_shapefile(path: Path, points: list[tuple[float, float]]) -> None:
    _write_vector_shapefile(path, 5, points)


def _write_dbf(path: Path, field_name: str, values: list[float]) -> None:
    field_length = 12
    decimal_count = 3
    header_length = 32 + 32 + 1
    record_length = 1 + field_length
    header = bytearray(header_length)
    header[0] = 0x03
    struct.pack_into("<I", header, 4, len(values))
    struct.pack_into("<H", header, 8, header_length)
    struct.pack_into("<H", header, 10, record_length)
    encoded_name = field_name.encode("ascii")[:10]
    field_offset = 32
    header[field_offset:field_offset + len(encoded_name)] = encoded_name
    header[field_offset + 11] = ord("N")
    header[field_offset + 16] = field_length
    header[field_offset + 17] = decimal_count
    header[-1] = 0x0D

    records = bytearray()
    for value in values:
        records += b" "
        records += f"{value:>{field_length}.{decimal_count}f}".encode("ascii")
    path.write_bytes(bytes(header) + bytes(records) + b"\x1A")


def _write_dbf_table(path: Path, fields: dict[str, list[float | None]]) -> None:
    if not fields:
        raise ValueError("DBF test table requires fields")
    record_count = len(next(iter(fields.values())))
    if any(len(values) != record_count for values in fields.values()):
        raise ValueError("DBF test fields must have equal lengths")
    field_length = 14
    decimal_count = 3
    header_length = 32 + len(fields) * 32 + 1
    record_length = 1 + len(fields) * field_length
    header = bytearray(header_length)
    header[0] = 0x03
    struct.pack_into("<I", header, 4, record_count)
    struct.pack_into("<H", header, 8, header_length)
    struct.pack_into("<H", header, 10, record_length)
    for field_index, field_name in enumerate(fields):
        descriptor_offset = 32 + field_index * 32
        encoded_name = field_name.encode("ascii")[:10]
        header[descriptor_offset:descriptor_offset + len(encoded_name)] = encoded_name
        header[descriptor_offset + 11] = ord("N")
        header[descriptor_offset + 16] = field_length
        header[descriptor_offset + 17] = decimal_count
    header[-1] = 0x0D

    records = bytearray()
    field_values = list(fields.values())
    for record_index in range(record_count):
        records += b" "
        for values in field_values:
            value = values[record_index]
            records += (
                b" " * field_length
                if value is None
                else f"{value:>{field_length}.{decimal_count}f}".encode("ascii")
            )
    path.write_bytes(bytes(header) + bytes(records) + b"\x1A")


def _write_opendap_ascii_grid(
    path: Path,
    grid: list[list[float]],
    latitudes: list[float],
    longitudes: list[float],
) -> None:
    rows = len(grid)
    columns = len(longitudes)
    lines = [
        "Dataset {",
        "    Grid {",
        "    } z;",
        "}",
        "---------------------------------------------",
        f"z.z[{rows}][{columns}]",
    ]
    for row_index, row in enumerate(grid):
        lines.append(f"[{row_index}], " + ", ".join(str(value) for value in row))
    lines.extend(
        [
            "",
            f"z.lat[{rows}]",
            ", ".join(str(value) for value in latitudes),
            "",
            f"z.lon[{columns}]",
            ", ".join(str(value) for value in longitudes),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
            _write_polyline_shapefile(shapefile)
            _write_dbf(root / "natural_earth_coastline.dbf", "LEN_KM", [123.5])
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
            _write_polyline_shapefile(projected_line, [(0.0, 0.0), (3000.0, 4000.0)])

            projected_square = root / "projected_square.shp"
            _write_polygon_shapefile(
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
            _write_polygon_shapefile(
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
            _write_opendap_ascii_grid(
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
            _write_polygon_shapefile(
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
            _write_polygon_shapefile(
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
                _write_dbf_table(dbf_path, {"ENDO": endorheic, "SUB_AREA": areas})
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
                {"area_km2": 100.0, "is_endorheic": False, "centroid_lat_deg": 20.0},
                {"area_km2": 50.0, "is_endorheic": True, "centroid_lat_deg": 10.0},
                {"area_km2": 25.0, "is_endorheic": True, "centroid_lat_deg": -10.0},
                {"area_km2": 75.0, "is_endorheic": False, "centroid_lat_deg": -20.0},
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
            _write_dbf_table(
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
            _write_dbf_table(
                dbf_path,
                {
                    "NEXT_DOWN": [0.0, 123.0, 0.0, 0.0],
                    "UPLAND_SKM": [1_000_000.0, 1_440_000.0, 1_690_000.0, 2_560_000.0],
                    "DIST_UP_KM": [2_000.0, 2_300.0, 2_600.0, 3_200.0],
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
                    "world_metric": "watershed_hack_fitted_exponent",
                    "statistic": "hydrorivers_hack_fitted_exponent",
                },
                {
                    **common,
                    "metric": "hydrorivers_hack_fitted_log_rmse",
                    "world_metric": "watershed_hack_fitted_log_rmse",
                    "statistic": "hydrorivers_hack_fitted_log_rmse",
                },
            ]

            report = derive_calibration_targets(sources)

            incomplete_dbf = root / "HydroRIVERS_v10_incomplete.dbf"
            _write_dbf_table(
                incomplete_dbf,
                {
                    "NEXT_DOWN": [0.0, 0.0, 0.0],
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
        exponent = targets["watershed_hack_fitted_exponent"]
        log_rmse = targets["watershed_hack_fitted_log_rmse"]
        self.assertAlmostEqual(exponent["source_value"], 0.5, places=9)
        self.assertAlmostEqual(log_rmse["source_value"], 0.0, places=9)
        self.assertEqual(exponent["source_active_reach_record_count"], 4)
        self.assertEqual(exponent["source_terminal_reach_record_count"], 3)
        self.assertEqual(exponent["source_sample_network_count"], 3)
        self.assertEqual(exponent["source_sample_record_count"], 3)
        self.assertEqual(exponent["source_network_selection"], "terminal_reaches_with_minimum_upstream_area_v1")

        world = {
            "calibration_checks": [],
            "watersheds": [
                {"area_km2": 1_690_000.0, "main_channel_length_km": 2_600.0},
                {"area_km2": 1_000_000.0, "main_channel_length_km": 2_000.0},
                {"area_km2": 2_560_000.0, "main_channel_length_km": 3_200.0},
            ],
        }
        evaluation = evaluate_calibration_targets(world, report["targets"])
        self.assertEqual(evaluation["summary"]["external_calibration_pass_count"], 2)
        self.assertTrue(evaluation["summary"]["external_calibration_complete"])
