from __future__ import annotations

import asyncio
import json
import os
import shutil
import struct
import threading
import tomllib
import time
import xml.etree.ElementTree as ET
from importlib import resources
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import quote, unquote, urlsplit
from unittest import SkipTest, TestCase
from unittest.mock import Mock, patch

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    from fastapi import HTTPException
    from fastapi.routing import APIRoute
except ImportError as exc:  # The server is covered when the optional debug extra is installed.
    raise SkipTest(f"debug server tests require magic-geo[debug]: {exc}") from exc

from magic_geo.debug_export import (
    FORMAT_NAME,
    FORMAT_VERSION,
    _export_cells,
    _export_family,
    _export_stage_history,
    _write_vtu_stages,
)
from magic_geo.debug_server import (
    CacheSelectRequest,
    ConfigSaveRequest,
    ConfigTextRequest,
    _CacheManager,
    _DebugCache,
    create_app,
)
from magic_geo.cli import app as cli_app
from magic_geo.web_jobs import _OPERATIONS, JobInputError, JobManager, operation_catalog
from typer.main import get_command


def _write_parquet(path: Path, values: dict[str, list[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(values), path)


def _make_cache(root: Path) -> Path:
    cache = root / "runs" / "debug"
    (cache / "events").mkdir(parents=True)
    (cache / "mesh").mkdir(parents=True)
    _write_parquet(
        cache / "tables/cells.parquet",
        {"id": [0, 1], "elevation_m": [10.0, -20.0], "biome": ["forest", "ocean"]},
    )
    _write_parquet(
        cache / "tables/monthly.parquet",
        {
            "cell_id": [0, 0, 1, 1],
            "month": [0, 1, 0, 1],
            "temperature_c": [12.0, 13.0, 2.0, 3.0],
        },
    )
    _write_parquet(
        cache / "tables/history_cells.parquet",
        {
            "stage_idx": [0, 1, 0, 1],
            "cell_id": [0, 0, 1, 1],
            "runoff": [1.0, 2.0, 3.0, 4.0],
            "phase": ["wet", "dry", "wet", "dry"],
        },
    )
    _write_parquet(
        cache / "tables/history_stages.parquet",
        {"stage_idx": [0, 1], "mean_runoff": [2.0, 3.0]},
    )
    _write_parquet(cache / "tables/flat.parquet", {"id": [0, 1], "value": [5.0, 6.0]})
    _write_parquet(cache / "tables/nested_scalars.parquet", {"id": [0], "score": [0.5]})
    _write_parquet(
        cache / "tables/edges.parquet",
        {
            "cell_a_id": [0],
            "cell_b_id": [1],
            "plate_boundary": [True],
            "boundary_segment_start_lat_deg": [0.0],
            "boundary_segment_start_lon_deg": [1.0],
            "boundary_segment_end_lat_deg": [2.0],
            "boundary_segment_end_lon_deg": [3.0],
        },
    )
    (cache / "events/nested.jsonl").write_text(
        json.dumps({"id": 0, "score": 0.5, "cell_ids": [0, 1]}) + "\n",
        encoding="utf-8",
    )
    (cache / "events/history_extras.jsonl").write_text(
        json.dumps({"stage_idx": 0, "nested_meta": {"source": "fixture"}}) + "\n",
        encoding="utf-8",
    )
    detail_line = json.dumps({"neighbors": [1], "boundary_ring": [[0.0, 1.0]]}) + "\n"
    (cache / "events/cell_details.jsonl").write_text(detail_line, encoding="utf-8")
    (cache / "tables/cell_details_index.json").write_text('{"0":0}', encoding="utf-8")
    (cache / "mesh/positions.f32").write_bytes(struct.pack("<3f", 0.0, 0.0, 1.0))
    (cache / "mesh/cell_ids.u32").write_bytes(struct.pack("<I", 0))
    (cache / "mesh/indices.u32").write_bytes(b"")
    (cache / "mesh/pos_equirect.f32").write_bytes(struct.pack("<2f", 0.0, 0.0))
    (cache / "mesh/pos_mollweide.f32").write_bytes(struct.pack("<2f", 0.0, 0.0))
    manifest = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "world": {"name": "tiny", "cell_count": 2, "mesh_backend": "test", "generation_scope": "full"},
        "layers": [
            {"id": "cells/elevation_m", "source": "cells", "name": "elevation_m", "kind": "numeric", "stats": {"min": -20.0, "max": 10.0}},
            {"id": "cells/biome", "source": "cells", "name": "biome", "kind": "categorical", "categories": ["forest", "ocean"]},
            {"id": "history/runoff", "source": "history", "name": "runoff", "kind": "numeric_stage", "stage_count": 2},
            {"id": "history/phase", "source": "history", "name": "phase", "kind": "categorical_stage", "stage_count": 2, "categories": ["dry", "wet"]},
        ],
        "cells": {
            "parquet": "tables/cells.parquet",
            "row_count": 2,
            "details_jsonl": "events/cell_details.jsonl",
            "details_index": "tables/cell_details_index.json",
            "skipped_fields": {"neighbors": "nested"},
        },
        "monthly": {"parquet": "tables/monthly.parquet", "row_count": 4},
        "stage_histories": {
            "history": {
                "stage_count": 2,
                "stage_cells_parquet": "tables/history_cells.parquet",
                "stages_parquet": "tables/history_stages.parquet",
                "extras_jsonl": "events/history_extras.jsonl",
            }
        },
        "families": {
            "flat": {"parquet": "tables/flat.parquet", "row_count": 2},
            "nested": {
                "jsonl": "events/nested.jsonl",
                "scalars_parquet": "tables/nested_scalars.parquet",
                "row_count": 1,
            },
            "cell_adjacency_edges": {"parquet": "tables/edges.parquet", "row_count": 1},
        },
        "sections": ["model"],
        "scalars": {"name": "tiny"},
        "skipped_sections": {"empty_records": "empty list"},
        "mesh": {
            "vertex_count": 1,
            "triangle_count": 0,
            "cell_count": 2,
            "cells_without_ring": 1,
            "endianness": "little",
            "buffers": {
                "positions": {"file": "mesh/positions.f32", "dtype": "float32", "components": 3},
                "cell_ids": {"file": "mesh/cell_ids.u32", "dtype": "uint32", "components": 1},
                "indices": {"file": "mesh/indices.u32", "dtype": "uint32", "components": 3},
                "pos_equirect": {"file": "mesh/pos_equirect.f32", "dtype": "float32", "components": 2},
                "pos_mollweide": {"file": "mesh/pos_mollweide.f32", "dtype": "float32", "components": 2},
            },
        },
    }
    (cache / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (cache / "sections.json").write_text(json.dumps({"model": {"type": "tiny-v1"}}), encoding="utf-8")
    return cache


def _wait_for_job(manager: JobManager, job_id: str, timeout: float = 10.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = manager.get(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish: {manager.get(job_id)}")


def endpoint(app: object, path: str, method: str = "GET") -> object:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route.endpoint
    raise AssertionError(f"route not found: {method} {path}")


def asgi_get(app: object, path: str) -> tuple[int, bytes]:
    """Issue one dependency-free ASGI GET through real routing/serialization."""

    messages: list[dict[str, object]] = []
    request_sent = False

    async def receive() -> dict[str, object]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    async def run_inline(function: object, *args: object, **kwargs: object) -> object:
        # The minimal debug-test environment intentionally omits Starlette's
        # optional HTTP client/thread-portal extra. Routing and response
        # serialization are what this harness needs to exercise.
        return function(*args, **kwargs)

    parsed = urlsplit(path)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": unquote(parsed.path),
        "raw_path": parsed.path.encode("utf-8"),
        "query_string": parsed.query.encode("ascii"),
        "root_path": "",
        "headers": [(b"accept", b"application/json")],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
    }
    with patch("fastapi.routing.run_in_threadpool", new=run_inline):
        asyncio.run(app(scope, receive, send))
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return int(start["status"]), body


class DebugServerTests(TestCase):
    def test_web_assets_are_declared_as_package_data(self) -> None:
        package_data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))[
            "tool"
        ]["setuptools"]["package-data"]["magic_geo"]
        self.assertIn("debug_ui/*.html", package_data)
        self.assertIn("debug_ui/*.css", package_data)
        self.assertIn("debug_ui/*.js", package_data)
        self.assertIn("debug_ui/vendor/*.js", package_data)
        self.assertIn("magic_geo_native.dll", package_data)
        self.assertIn("libmagic_geo_native.dylib", package_data)
        setup_text = Path("setup.py").read_text(encoding="utf-8")
        self.assertIn("has_ext_modules", setup_text)
        self.assertIn("ctypes.CDLL", setup_text)
        manifest_text = Path("MANIFEST.in").read_text(encoding="utf-8")
        self.assertIn("recursive-include cpp", manifest_text)
        self.assertIn("global-exclude", manifest_text)
        self.assertIn("*.so", manifest_text)
        cmake_text = Path("CMakeLists.txt").read_text(encoding="utf-8")
        self.assertIn("RUNTIME_OUTPUT_DIRECTORY_RELEASE", cmake_text)
        self.assertIn("RUNTIME DESTINATION magic_geo", cmake_text)
        ui = resources.files("magic_geo").joinpath("debug_ui")
        for relative in (
            "index.html",
            "style.css",
            "app.js",
            "layer_docs.js",
            "vendor/three.module.js",
        ):
            self.assertTrue(ui.joinpath(relative).is_file(), relative)

    def test_cell_export_retains_nested_fields_and_handles_ragged_monthly_lists(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest: dict[str, object] = {"layers": []}
            cells = [
                {
                    "id": 0,
                    "elevation_m": 10.0,
                    "position_3d": [1.0, 0.0, 0.0],
                    "neighbors": [1],
                    "diagnostic": {"nonfinite": float("nan")},
                    "temperature_monthly_c": [float(index) for index in range(12)],
                },
                {
                    "id": 1,
                    "elevation_m": -20.0,
                    "position_3d": [0.0, 1.0, 0.0],
                    "neighbors": [0],
                    # A malformed/ragged list is retained for inspection rather
                    # than crashing or being partially flattened.
                    "temperature_monthly_c": [float(index) for index in range(11)],
                },
            ]
            _export_cells(cells, root / "tables", root / "events", manifest)
            cell_manifest = manifest["cells"]
            self.assertIn("neighbors", cell_manifest["detail_fields"])
            self.assertIn("temperature_monthly_c", cell_manifest["detail_fields"])
            self.assertNotIn("monthly", manifest)
            offsets = json.loads(
                (root / cell_manifest["details_index"]).read_text(encoding="utf-8")
            )
            with (root / cell_manifest["details_jsonl"]).open("rb") as handle:
                handle.seek(offsets["1"])
                details = json.loads(handle.readline())
            self.assertEqual(details["neighbors"], [0])
            self.assertEqual(len(details["temperature_monthly_c"]), 11)
            with (root / cell_manifest["details_jsonl"]).open("rb") as handle:
                handle.seek(offsets["0"])
                first_details = json.loads(handle.readline())
            self.assertIsNone(first_details["diagnostic"]["nonfinite"])

    def test_exported_world_keys_cannot_escape_cache_directories(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tables = root / "tables"
            events = root / "events"
            malicious = "../../../../outside"
            manifest: dict[str, object] = {
                "layers": [],
                "families": {},
                "stage_histories": {},
            }
            _export_family(
                malicious,
                [{"id": 0, "value": 1.0}],
                tables,
                events,
                manifest,
            )
            _export_stage_history(
                malicious + "-history",
                [{"cell_ids": [0], "value_by_cell": [1.0]}],
                tables,
                events,
                manifest,
            )

            family_path = root / manifest["families"][malicious]["parquet"]
            history = manifest["stage_histories"][malicious + "-history"]
            for path in (
                family_path,
                root / history["stage_cells_parquet"],
                root / history["stages_parquet"],
            ):
                self.assertTrue(path.is_file())
                self.assertTrue(path.resolve().is_relative_to(root.resolve()))
                self.assertNotIn("..", path.relative_to(root).parts)

    def test_stage_extras_and_categorical_vtu_are_lossless_and_safe(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            manifest: dict[str, object] = {
                "layers": [],
                "families": {},
                "stage_histories": {},
            }
            records = [
                {
                    "cell_ids": [0],
                    "elevation_m_by_cell": [10.0],
                    "phase_by_cell": ["wet"],
                    "nested_meta": {"source": "initial"},
                },
                {
                    "cell_ids": [0],
                    "elevation_m_by_cell": [12.0],
                    "phase_by_cell": ["dry"],
                    "nested_meta": ["changed"],
                },
            ]
            _export_stage_history(
                "hydrologic_water_budget_history",
                records,
                root / "tables",
                root / "events",
                manifest,
            )
            history = manifest["stage_histories"]["hydrologic_water_budget_history"]
            self.assertIn("nested_meta", history["skipped_summary_fields"])
            extras_path = root / history["extras_jsonl"]
            extras = [json.loads(line) for line in extras_path.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(extras[0]["nested_meta"], {"source": "initial"})
            self.assertEqual(extras[1]["nested_meta"], ["changed"])

            world = {
                "cells": [
                    {
                        "id": 0,
                        "boundary_ring": [[0.0, 0.0], [0.0, 1.0], [1.0, 0.0]],
                    }
                ],
                "hydrologic_water_budget_history": [
                    {
                        "cell_ids": [0],
                        "elevation_m_by_cell": [10.0],
                        "phase_by_cell": ["wet"],
                        'unsafe\"<&_by_cell': [2.0],
                    }
                ],
            }
            vtu_manifest: dict[str, object] = {}
            _write_vtu_stages(
                world,
                root / "vtu",
                vtu_manifest,
                elevation_exaggeration=1.0,
            )
            tree = ET.parse(root / "vtu" / "stage_0000.vtu")
            names = {
                element.attrib.get("Name")
                for element in tree.iter("DataArray")
                if "Name" in element.attrib
            }
            self.assertNotIn("phase", names)
            self.assertIn('unsafe\"<&', names)

    def test_fixed_cache_metadata_symlinks_are_rejected(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory() as outside_dir:
            root = Path(temp_dir)
            cache_dir = _make_cache(root)
            outside = Path(outside_dir) / "outside.json"
            outside.write_text('{"model":{"secret":true}}', encoding="utf-8")
            sections = cache_dir / "sections.json"
            sections.unlink()
            sections.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "sections file must stay inside"):
                _DebugCache(cache_dir)

    def test_cacheless_workbench_exposes_config_and_operation_surface(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            app = create_app(None, project_root=root, workspace=Path("runs"))
            try:
                status_payload = endpoint(app, "/api/status")()
                self.assertFalse(status_payload["cache_available"])

                catalog = endpoint(app, "/api/operations")()
                self.assertEqual(catalog["coverage"]["cli_command_count"], 14)
                self.assertEqual(
                    {entry["id"] for entry in catalog["equivalents"]},
                    {"init-config", "backend", "serve"},
                )

                schema = endpoint(app, "/api/config/schema")()
                self.assertTrue(schema["properties"]["planet"]["description"])
                for definition in schema["$defs"].values():
                    for field_schema in definition.get("properties", {}).values():
                        self.assertTrue(field_schema.get("description"))

                valid = endpoint(app, "/api/config/validate", "POST")(
                    ConfigTextRequest(
                        yaml="mesh:\n  cell_count: 128\ntectonics:\n  plate_count: 8\n"
                    )
                )
                self.assertTrue(valid["valid"])

                saved = endpoint(app, "/api/config/save", "POST")(
                    ConfigSaveRequest(yaml=valid["yaml"], name="browser-smoke")
                )
                self.assertEqual(saved["path"], "runs/configs/browser-smoke.yaml")
                self.assertTrue((root / saved["path"]).is_file())

                with self.assertRaises(HTTPException) as conflict_context:
                    endpoint(app, "/api/config/save", "POST")(
                        ConfigSaveRequest(yaml=valid["yaml"], name="browser-smoke")
                    )
                self.assertEqual(conflict_context.exception.status_code, 409)
                replaced = endpoint(app, "/api/config/save", "POST")(
                    ConfigSaveRequest(
                        yaml=valid["yaml"],
                        name="browser-smoke",
                        force=True,
                    )
                )
                self.assertTrue(replaced["saved"])

                with self.assertRaises(HTTPException):
                    endpoint(app, "/api/config/save", "POST")(
                        ConfigSaveRequest(yaml=valid["yaml"], name="../escape")
                    )

                with self.assertRaises(HTTPException) as invalid_context:
                    endpoint(app, "/api/config/validate", "POST")(
                        ConfigTextRequest(yaml="run:\n  seed: 1\n  seed: 2\n")
                    )
                self.assertEqual(invalid_context.exception.status_code, 422)
                self.assertIn("duplicate key", invalid_context.exception.detail["message"])

                deeply_nested = "[" * 80 + "0" + "]" * 80
                with self.assertRaises(HTTPException) as depth_context:
                    endpoint(app, "/api/config/validate", "POST")(
                        ConfigTextRequest(yaml=deeply_nested)
                    )
                self.assertEqual(depth_context.exception.status_code, 422)
                self.assertIn("nesting exceeds", depth_context.exception.detail["message"])

                with self.assertRaises(HTTPException) as size_context:
                    endpoint(app, "/api/config/validate", "POST")(
                        ConfigTextRequest(yaml="😀" * 250_001)
                    )
                self.assertEqual(size_context.exception.status_code, 413)
                self.assertIn("1000000-byte", size_context.exception.detail)

                for invalid_yaml in (
                    "run:\n  seed: " + "1" * 4301 + "\n",
                    "run:\n  name: 2020-02-30\n",
                    "\ud800",
                ):
                    with self.subTest(invalid_yaml=invalid_yaml[:40]):
                        with self.assertRaises(HTTPException) as invalid_yaml_context:
                            endpoint(app, "/api/config/validate", "POST")(
                                ConfigTextRequest(yaml=invalid_yaml)
                            )
                        self.assertEqual(invalid_yaml_context.exception.status_code, 422)

                with self.assertRaises(HTTPException) as manifest_context:
                    endpoint(app, "/api/manifest")()
                self.assertEqual(manifest_context.exception.status_code, 409)
                self.assertIn("no debug cache", manifest_context.exception.detail)

                openapi = app.openapi()
                for route in (
                    "/api/config/schema",
                    "/api/jobs",
                    "/api/catalog",
                    "/api/family/{family_name}",
                ):
                    self.assertIn(route, openapi["paths"])
            finally:
                app.state.job_manager.close()
                app.state.cache_manager.close()

    def test_cache_endpoints_expose_every_export_class_and_full_nested_rows(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = _make_cache(root)
            app = create_app(cache_dir, project_root=root, workspace=Path("runs"))
            try:
                catalog = endpoint(app, "/api/catalog")()
                self.assertIn("flat", catalog["families"])
                self.assertEqual(catalog["sections"], ["model"])
                self.assertEqual(catalog["skipped_sections"]["empty_records"], "empty list")

                layer_response = endpoint(app, "/api/layer/{layer_id:path}")(
                    "cells/elevation_m", None, None, "f32"
                )
                self.assertEqual(layer_response.media_type, "application/octet-stream")
                self.assertEqual(struct.unpack("<2f", layer_response.body), (10.0, -20.0))

                categorical_stage = endpoint(app, "/api/layer/{layer_id:path}")(
                    "history/phase", 0, None, "f32"
                )
                self.assertEqual(struct.unpack("<2f", categorical_stage.body), (1.0, 1.0))

                cell = endpoint(app, "/api/cell/{cell_id}")(0)
                self.assertTrue(cell["complete"])
                self.assertEqual(cell["cell"]["neighbors"], [1])

                nested = endpoint(app, "/api/family/{family_name:path}")(
                    "nested", 100, 0, "full"
                )
                self.assertEqual(nested["detail"], "full")
                self.assertEqual(nested["rows"][0]["cell_ids"], [0, 1])

                scalars = endpoint(app, "/api/family/{family_name:path}")(
                    "nested", 100, 0, "scalars"
                )
                self.assertNotIn("cell_ids", scalars["rows"][0])

                section = endpoint(app, "/api/section/{section_name:path}")("model")
                self.assertEqual(section["type"], "tiny-v1")

                stage = endpoint(app, "/api/stage-summary/{history_name:path}")("history")
                self.assertEqual(stage["stage_count"], 2)
                self.assertEqual(
                    stage["extras"][0]["nested_meta"],
                    {"source": "fixture"},
                )

                boundaries = endpoint(app, "/api/plate-boundaries")()
                self.assertEqual(boundaries, [[0.0, 1.0, 2.0, 3.0]])

                worlds = endpoint(app, "/api/worlds")()["worlds"]
                self.assertEqual([world["cache_dir"] for world in worlds], ["runs/debug"])
                self.assertTrue(worlds[0]["selected"])
                selected = endpoint(app, "/api/worlds/select", "POST")(
                    CacheSelectRequest(cache_dir="runs/debug")
                )
                self.assertTrue(selected["cache_available"])
            finally:
                app.state.job_manager.close()
                app.state.cache_manager.close()

    def test_real_asgi_routes_support_slash_names_and_strict_nonfinite_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = _make_cache(root)
            manifest_path = cache_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["families"]["nested/records"] = dict(
                manifest["families"]["nested"]
            )
            manifest["stage_histories"]["history/alternate"] = dict(
                manifest["stage_histories"]["history"]
            )
            section_name = "model?/diagnostics%"
            manifest["sections"].append(section_name)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            sections_path = cache_dir / "sections.json"
            sections = json.loads(sections_path.read_text(encoding="utf-8"))
            sections[section_name] = {"nonfinite": float("inf")}
            sections_path.write_text(json.dumps(sections), encoding="utf-8")
            _write_parquet(
                cache_dir / "tables/cells.parquet",
                {
                    "id": [0, 1],
                    "elevation_m": [float("nan"), -20.0],
                    "biome": ["forest", "ocean"],
                },
            )

            app = create_app(cache_dir, project_root=root, workspace=Path("runs"))
            try:
                status, body = asgi_get(app, "/api/family/nested/records")
                self.assertEqual(status, 200, body)
                self.assertEqual(json.loads(body)["name"], "nested/records")
                status, body = asgi_get(app, "/api/stage-summary/history/alternate")
                self.assertEqual(status, 200, body)
                status, body = asgi_get(
                    app,
                    f"/api/section/{quote(section_name, safe='')}",
                )
                self.assertEqual(status, 200, body)
                self.assertIsNone(json.loads(body)["nonfinite"])
                status, body = asgi_get(app, "/api/cell/0")
                self.assertEqual(status, 200, body)
                self.assertIsNone(json.loads(body)["cell"]["elevation_m"])
                status, body = asgi_get(app, "/api/status")
                revision = json.loads(body)["cache_revision"]
                status, body = asgi_get(app, f"/api/manifest?revision={revision}")
                self.assertEqual(status, 200, body)
                status, body = asgi_get(app, "/api/manifest?revision=stale")
                self.assertEqual(status, 409, body)
            finally:
                app.state.job_manager.close()
                app.state.cache_manager.close()

    def test_cache_paths_are_confined_with_component_aware_check(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = _make_cache(root)
            sibling = cache_dir.parent / "debug-secret"
            sibling.mkdir()
            (sibling / "secret.parquet").write_text("secret", encoding="utf-8")
            cache = _DebugCache(cache_dir)
            try:
                with self.assertRaisesRegex(Exception, "escapes root"):
                    cache._data_path("../debug-secret/secret.parquet")
                with self.assertRaisesRegex(Exception, "escapes mesh root"):
                    cache.mesh_path("../manifest.json")
            finally:
                cache.close()

    def test_cache_format_version_and_selection_are_strict_and_transactional(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected = _make_cache(root)
            manager = _CacheManager(root, root / "runs", selected)
            try:
                original = manager.get()
                assert original is not None
                original_revision = manager.status()["cache_revision"]
                invalid = root / "runs" / "invalid"
                shutil.copytree(selected, invalid)
                invalid_manifest = json.loads(
                    (invalid / "manifest.json").read_text(encoding="utf-8")
                )
                invalid_manifest["version"] = FORMAT_VERSION + 1
                (invalid / "manifest.json").write_text(
                    json.dumps(invalid_manifest), encoding="utf-8"
                )

                with self.assertRaisesRegex(ValueError, "expected"):
                    manager.select(invalid)
                self.assertIs(manager.get(), original)
                self.assertEqual(manager.selected_relative(), "runs/debug")
                self.assertEqual(manager.status()["cache_revision"], original_revision)

                staging = root / "runs" / ".debug.rollback.staging"
                shutil.copytree(selected, staging)
                real_replace = os.replace
                replace_calls = 0

                def fail_new_directory_move(source: object, target: object) -> None:
                    nonlocal replace_calls
                    replace_calls += 1
                    if replace_calls == 2:
                        raise OSError("injected publication failure")
                    real_replace(source, target)

                with patch(
                    "magic_geo.debug_server.os.replace",
                    side_effect=fail_new_directory_move,
                ):
                    with self.assertRaisesRegex(OSError, "injected"):
                        manager.publish(staging, selected)
                self.assertTrue((selected / "manifest.json").is_file())
                self.assertEqual(manager.get().manifest["world"]["name"], "tiny")
                self.assertFalse(any((root / "runs").glob(".debug.*.backup")))

                for invalid_version in (str(FORMAT_VERSION), True, None):
                    invalid_manifest["version"] = invalid_version
                    (invalid / "manifest.json").write_text(
                        json.dumps(invalid_manifest), encoding="utf-8"
                    )
                    with self.subTest(version=invalid_version):
                        with self.assertRaisesRegex(ValueError, "version"):
                            _DebugCache(invalid)
            finally:
                manager.close()

    def test_invalid_hot_reload_keeps_last_good_cache_then_recovers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected = _make_cache(root)
            manager = _CacheManager(root, root / "runs", selected)
            try:
                original = manager.get()
                assert original is not None
                original_revision = manager.status()["cache_revision"]
                manifest_path = selected / "manifest.json"
                valid_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

                manifest_path.write_text("{", encoding="utf-8")
                status = manager.status()
                self.assertTrue(status["cache_available"])
                self.assertTrue(status["cache_error"])
                self.assertEqual(status["cache_revision"], original_revision)
                self.assertIs(manager.get(), original)

                valid_manifest["world"]["name"] = "recovered-after-invalid-revision"
                manifest_path.write_text(json.dumps(valid_manifest), encoding="utf-8")
                recovered = manager.get()
                assert recovered is not None
                self.assertIsNot(recovered, original)
                self.assertEqual(
                    recovered.manifest["world"]["name"],
                    "recovered-after-invalid-revision",
                )
                self.assertIsNone(manager.status()["cache_error"])
            finally:
                manager.close()

    def test_cache_revision_rejects_cross_revision_reads_even_with_same_size_and_time(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            selected = _make_cache(root)
            manager = _CacheManager(root, root / "runs", selected)
            try:
                original_revision = manager.status()["cache_revision"]
                manifest = selected / "manifest.json"
                original_stat = manifest.stat()
                replacement = selected / "manifest.next"
                replacement.write_bytes(manifest.read_bytes())
                os.utime(
                    replacement,
                    ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
                )
                os.replace(replacement, manifest)

                next_revision = manager.status()["cache_revision"]
                self.assertNotEqual(next_revision, original_revision)
                with self.assertRaises(HTTPException) as context:
                    manager.with_cache(
                        lambda cache: cache.manifest,
                        original_revision,
                    )
                self.assertEqual(context.exception.status_code, 409)
            finally:
                manager.close()

    def test_config_save_rejects_symlinked_workspace_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "runs"
            outside = root / "outside"
            outside.mkdir()
            workspace.mkdir()
            (workspace / "configs").symlink_to(outside, target_is_directory=True)
            app = create_app(None, project_root=root, workspace=Path("runs"))
            try:
                with self.assertRaises(HTTPException) as context:
                    endpoint(app, "/api/config/save", "POST")(
                        ConfigSaveRequest(yaml="{}\n", name="escaped.yaml")
                    )
                self.assertEqual(context.exception.status_code, 422)
                self.assertFalse((outside / "escaped.yaml").exists())
            finally:
                app.state.job_manager.close()
                app.state.cache_manager.close()

    def test_config_save_rejects_file_level_symlinks(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            configs = root / "runs" / "configs"
            configs.mkdir(parents=True)
            (configs / "alias.yaml").symlink_to("victim.yaml")
            outside = root / "outside.yaml"
            (configs / "outside-alias.yaml").symlink_to(outside)
            app = create_app(None, project_root=root, workspace=Path("runs"))
            try:
                for name in ("alias.yaml", "outside-alias.yaml"):
                    with self.subTest(name=name):
                        with self.assertRaises(HTTPException) as context:
                            endpoint(app, "/api/config/save", "POST")(
                                ConfigSaveRequest(yaml="{}\n", name=name, force=True)
                            )
                        self.assertEqual(context.exception.status_code, 422)
                self.assertFalse((configs / "victim.yaml").exists())
                self.assertFalse(outside.exists())
            finally:
                app.state.job_manager.close()
                app.state.cache_manager.close()

    def test_job_schema_confines_paths_and_covers_every_cli_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "configs").mkdir()
            (root / "configs/config.yaml").write_text("{}", encoding="utf-8")
            manager = JobManager(root, Path("runs"))
            try:
                normalized, command, artifacts = manager._build_command(
                    "generate",
                    {
                        "config": "configs/config.yaml",
                        "output": "runs/example/world.json",
                        "cells": 128,
                        "geo_only": True,
                        "open_in_web": False,
                    },
                )
                self.assertIn("--geo-only", command)
                self.assertEqual(normalized["cells"], 128)
                self.assertEqual(artifacts[0]["path"], "runs/example/world.json")
                with self.assertRaises(JobInputError):
                    manager._build_command(
                        "generate",
                        {"config": "configs/config.yaml", "output": "../outside.json"},
                    )
                with self.assertRaisesRegex(JobInputError, "outputs overlap"):
                    manager._build_command(
                        "generate",
                        {
                            "config": "configs/config.yaml",
                            "output": "runs/debug/world.json",
                            "debug_output": "runs/debug",
                            "open_in_web": True,
                        },
                    )
                with self.assertRaises(JobInputError):
                    manager._build_command("validate", {"world": "/etc/passwd"})

                (root / "runs/dummy-world.json").write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(
                    JobInputError,
                    "directory path|contain an input|must not replace an input",
                ):
                    manager._build_command(
                        "export-debug",
                        {
                            "world": "runs/dummy-world.json",
                            "output": "runs/dummy-world.json",
                        },
                    )
                cache_input_dir = root / "runs" / "cache-input"
                cache_input_dir.mkdir()
                (cache_input_dir / "config.yaml").write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(JobInputError, "contain an input"):
                    manager._build_command(
                        "generate",
                        {
                            "config": "runs/cache-input/config.yaml",
                            "output": "runs/world.json",
                            "debug_output": "runs/cache-input",
                            "open_in_web": True,
                        },
                    )
                with patch.object(manager, "_spawn", return_value=0):
                    submitted = manager.submit(
                        "validate", {"world": "runs/dummy-world.json"}
                    )
                    for _ in range(100):
                        completed = manager.get(submitted["id"])
                        if completed["status"] not in {"queued", "running"}:
                            break
                        time.sleep(0.005)
                self.assertEqual(completed["status"], "succeeded")
                self.assertEqual(completed["exit_code"], 0)
                self.assertIn("magic_geo validate", completed["log"])
            finally:
                manager.close()

            catalog = operation_catalog()
            command_ids = {entry["id"] for entry in catalog["operations"]}
            equivalent_ids = {entry["id"] for entry in catalog["equivalents"]}
            self.assertEqual(
                command_ids | equivalent_ids,
                {
                    "init-config",
                    "backend",
                    "generate",
                    "validate-geo",
                    "validate-geo-suite",
                    "validate",
                    "calibrate",
                    "calibrate-ensemble",
                    "derive-targets",
                    "render",
                    "render-raster",
                    "export-debug",
                    "export-rerun",
                    "serve",
                },
            )

            click_root = get_command(cli_app)
            for operation_id, operation_spec in _OPERATIONS.items():
                with self.subTest(operation=operation_id):
                    click_params = {
                        parameter.name: parameter
                        for parameter in click_root.commands[operation_id].params
                    }
                    web_fields = {
                        field["name"]: field
                        for field in operation_spec["fields"]
                        if field.get("cli", True)
                    }
                    self.assertEqual(set(web_fields), set(click_params))
                    for name, field in web_fields.items():
                        options = set(click_params[name].opts) | set(
                            click_params[name].secondary_opts
                        )
                        self.assertIn(field["flag"], options)
                        if field.get("negative_flag"):
                            self.assertIn(field["negative_flag"], options)

            custom_manager = JobManager(root, Path("runs/custom-workspace"))
            try:
                custom_catalog = operation_catalog(root, custom_manager.workspace)
                generate_spec = next(
                    entry for entry in custom_catalog["operations"] if entry["id"] == "generate"
                )
                output_field = next(
                    field for field in generate_spec["fields"] if field["name"] == "output"
                )
                config_field = next(
                    field for field in generate_spec["fields"] if field["name"] == "config"
                )
                self.assertEqual(
                    output_field["default"],
                    "runs/custom-workspace/world.json",
                )
                self.assertEqual(
                    config_field["default"],
                    "runs/custom-workspace/configs/world.yaml",
                )
            finally:
                custom_manager.close()

    def test_job_schema_confines_transitive_inputs_and_protects_inputs_from_outputs(self) -> None:
        with TemporaryDirectory() as temp_dir, TemporaryDirectory() as outside_dir:
            root = Path(temp_dir)
            outside = Path(outside_dir)
            (root / "configs").mkdir()
            (root / "runs").mkdir()
            (root / "configs/config.yaml").write_text("{}", encoding="utf-8")
            (root / "runs/world.json").write_text("{}", encoding="utf-8")
            local_data = root / "configs/data.asc"
            local_data.write_text("local", encoding="utf-8")
            external_data = outside / "external.asc"
            external_data.write_text("external", encoding="utf-8")
            manager = JobManager(root, Path("runs"))
            try:
                local_sources = root / "configs/sources.json"
                local_sources.write_text(
                    json.dumps({"sources": [{"path": "data.asc"}]}),
                    encoding="utf-8",
                )
                normalized, _, _ = manager._build_command(
                    "derive-targets",
                    {"sources": "configs/sources.json"},
                )
                self.assertEqual(normalized["sources"], str(local_sources))

                escaping_sources = root / "configs/escaping-sources.json"
                escaping_sources.write_text(
                    json.dumps({"sources": [{"path": str(external_data)}]}),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(JobInputError, "indirect input path"):
                    manager._build_command(
                        "derive-targets",
                        {"sources": "configs/escaping-sources.json"},
                    )

                linked_data = root / "configs/linked.asc"
                linked_data.symlink_to(external_data)
                escaping_sources.write_text(
                    json.dumps({"sources": [{"path": "linked.asc"}]}),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(JobInputError, "indirect input path"):
                    manager._build_command(
                        "derive-targets",
                        {"sources": "configs/escaping-sources.json"},
                    )

                catalog = root / "configs/hydro-catalog.json"
                catalog.write_text(
                    json.dumps({"archives": [{"path": str(external_data)}]}),
                    encoding="utf-8",
                )
                escaping_sources.write_text(
                    json.dumps(
                        {
                            "sources": [
                                {
                                    "path": "hydro-catalog.json",
                                    "format": "hydrobasins_archive_catalog",
                                }
                            ]
                        }
                    ),
                    encoding="utf-8",
                )
                with self.assertRaisesRegex(JobInputError, "HydroBASINS archives"):
                    manager._build_command(
                        "derive-targets",
                        {"sources": "configs/escaping-sources.json"},
                    )

                bundle = root / "configs/bundle.json"
                derivation = root / "configs/derivation.json"
                derivation.write_text("{}", encoding="utf-8")
                bundle.write_text(
                    json.dumps(
                        {
                            "derivation": {
                                "source_manifests": [
                                    {"path": "derivation.json", "sha256": "0" * 64}
                                ]
                            }
                        }
                    ),
                    encoding="utf-8",
                )
                matrix = root / "configs/matrix.yaml"
                matrix.write_text(
                    "scenarios:\n"
                    "  - empirical_calibration:\n"
                    "      target_bundle: bundle.json\n",
                    encoding="utf-8",
                )
                manager._build_command(
                    "validate-geo-suite",
                    {
                        "config": "configs/config.yaml",
                        "matrix": "configs/matrix.yaml",
                    },
                )
                matrix.write_text(
                    "scenarios:\n"
                    "  - empirical_calibration:\n"
                    f"      target_bundle: {outside / 'bundle.json'}\n",
                    encoding="utf-8",
                )
                (outside / "bundle.json").write_text("{}", encoding="utf-8")
                with self.assertRaisesRegex(JobInputError, "indirect input path"):
                    manager._build_command(
                        "validate-geo-suite",
                        {
                            "config": "configs/config.yaml",
                            "matrix": "configs/matrix.yaml",
                        },
                    )

                with self.assertRaisesRegex(JobInputError, "must not replace an input"):
                    manager._build_command(
                        "render",
                        {
                            "world": "runs/world.json",
                            "output": "runs/world.json",
                        },
                    )
            finally:
                manager.close()

    def test_job_artifacts_are_produced_snapshots_including_policy_failures(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "runs").mkdir()
            world = root / "world.json"
            world.write_text("{}", encoding="utf-8")
            report = root / "runs" / "report.json"
            report.write_bytes(b"pre-existing secret")
            manager = JobManager(root, Path("runs"))
            try:
                def write_failed_report(_job: object, command: list[str]) -> int:
                    output = Path(command[command.index("--output") + 1])
                    output.write_bytes(b'{"passed":false}')
                    return 1

                with patch.object(manager, "_spawn", side_effect=write_failed_report):
                    submitted = manager.submit(
                        "validate-geo",
                        {"world": str(world), "output": str(report)},
                    )
                    failed = _wait_for_job(manager, submitted["id"])

                self.assertEqual(failed["status"], "failed")
                self.assertEqual(failed["exit_code"], 1)
                self.assertTrue(failed["artifacts"][0]["available"])
                snapshot = manager.artifact_path(submitted["id"], 0)
                self.assertEqual(snapshot.name, "report.json")
                self.assertEqual(snapshot.read_bytes(), b'{"passed":false}')

                # A later job or manual edit cannot change an older download.
                report.write_bytes(b"later replacement")
                self.assertEqual(
                    manager.artifact_path(submitted["id"], 0).read_bytes(),
                    b'{"passed":false}',
                )
                with self.assertRaises(KeyError):
                    manager.artifact_path(submitted["id"], -1)

                svg = root / "runs" / "existing.svg"
                svg.write_text("old", encoding="utf-8")
                with patch.object(manager, "_spawn", return_value=0):
                    untouched_job = manager.submit(
                        "render", {"world": str(world), "output": str(svg)}
                    )
                    untouched = _wait_for_job(manager, untouched_job["id"])
                self.assertEqual(untouched["status"], "succeeded")
                self.assertFalse(untouched["artifacts"][0]["available"])
                with self.assertRaises(FileNotFoundError):
                    manager.artifact_path(untouched_job["id"], 0)

                with self.assertRaises(JobInputError):
                    manager._build_command(
                        "render",
                        {
                            "world": str(world),
                            "output": str(root / "runs" / "huge.svg"),
                            "width": 10**400,
                        },
                    )
            finally:
                manager.close()

    def test_web_debug_export_is_staged_and_failed_replacement_preserves_cache(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = _make_cache(root)
            world = root / "world.json"
            world.write_text("{}", encoding="utf-8")
            app = create_app(cache_dir, project_root=root, workspace=Path("runs"))
            jobs = app.state.job_manager
            release = threading.Event()
            stage_ready = threading.Event()
            staged_paths: list[Path] = []
            try:
                self.assertEqual(
                    endpoint(app, "/api/manifest")()["world"]["name"], "tiny"
                )

                def prepare_complete_stage(_job: object, command: list[str]) -> int:
                    staged = Path(command[command.index("--output") + 1])
                    staged_paths.append(staged)
                    self.assertNotEqual(staged.resolve(), cache_dir.resolve())
                    shutil.copytree(cache_dir, staged, dirs_exist_ok=True)
                    manifest_path = staged / "manifest.json"
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest["world"]["name"] = "published"
                    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                    stage_ready.set()
                    self.assertTrue(release.wait(5.0))
                    return 0

                with patch.object(jobs, "_spawn", side_effect=prepare_complete_stage):
                    submitted = jobs.submit(
                        "export-debug",
                        {"world": str(world), "output": str(cache_dir), "vtu": False},
                    )
                    self.assertTrue(stage_ready.wait(5.0))
                    # The selected cache remains wholly readable while export is
                    # still writing its private sibling directory.
                    self.assertEqual(
                        endpoint(app, "/api/manifest")()["world"]["name"], "tiny"
                    )
                    release.set()
                    completed = _wait_for_job(jobs, submitted["id"])

                self.assertEqual(completed["status"], "succeeded", completed["log"])
                self.assertEqual(completed["cache_dir"], "runs/debug")
                self.assertEqual(
                    endpoint(app, "/api/manifest")()["world"]["name"], "published"
                )
                self.assertFalse(any(path.exists() for path in staged_paths))

                failed_stages: list[Path] = []

                def fail_partial_stage(_job: object, command: list[str]) -> int:
                    staged = Path(command[command.index("--output") + 1])
                    failed_stages.append(staged)
                    (staged / "partial.txt").write_text("partial", encoding="utf-8")
                    return 2

                with patch.object(jobs, "_spawn", side_effect=fail_partial_stage):
                    failed_submit = jobs.submit(
                        "export-debug",
                        {"world": str(world), "output": str(cache_dir), "vtu": False},
                    )
                    failed = _wait_for_job(jobs, failed_submit["id"])
                self.assertEqual(failed["status"], "failed")
                self.assertIsNone(failed["cache_dir"])
                self.assertEqual(
                    endpoint(app, "/api/manifest")()["world"]["name"], "published"
                )
                self.assertFalse(any(path.exists() for path in failed_stages))
            finally:
                release.set()
                jobs.close()
                app.state.cache_manager.close()

    def test_job_manager_close_finishes_running_and_queued_jobs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "runs").mkdir()
            first_world = root / "first.json"
            second_world = root / "second.json"
            first_world.write_text("{}", encoding="utf-8")
            second_world.write_text("{}", encoding="utf-8")
            manager = JobManager(root, Path("runs"))
            started = threading.Event()
            spawn_count = 0

            def wait_for_cancel(job: object, _command: list[str]) -> int:
                nonlocal spawn_count
                spawn_count += 1
                started.set()
                deadline = time.monotonic() + 5.0
                while not job._cancel_requested and time.monotonic() < deadline:
                    time.sleep(0.005)
                return 143

            with patch.object(manager, "_spawn", side_effect=wait_for_cancel):
                running = manager.submit("validate", {"world": str(first_world)})
                self.assertTrue(started.wait(5.0))
                queued = manager.submit("validate", {"world": str(second_world)})
                manager.close()

            self.assertEqual(spawn_count, 1)
            for job_id in (running["id"], queued["id"]):
                job = manager.get(job_id)
                self.assertEqual(job["status"], "cancelled")
                self.assertIsNotNone(job["finished_at"])
            with self.assertRaises(JobInputError):
                manager.submit("validate", {"world": str(first_world)})

    def test_cache_publication_and_cancellation_have_an_atomic_commit_boundary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "runs").mkdir()
            world = root / "world.json"
            world.write_text("{}", encoding="utf-8")
            publisher = Mock(return_value=root / "runs" / "debug")
            manager = JobManager(root, Path("runs"), publish_cache=publisher)
            validation_started = threading.Event()
            release_validation = threading.Event()

            def blocked_validation(_path: Path) -> None:
                validation_started.set()
                self.assertTrue(release_validation.wait(5.0))

            try:
                with (
                    patch.object(manager, "_spawn", return_value=0),
                    patch.object(
                        manager,
                        "_validate_debug_cache",
                        side_effect=blocked_validation,
                    ),
                ):
                    submitted = manager.submit(
                        "export-debug",
                        {
                            "world": str(world),
                            "output": str(root / "runs" / "debug"),
                            "vtu": False,
                        },
                    )
                    self.assertTrue(validation_started.wait(5.0))
                    manager.cancel(submitted["id"])
                    release_validation.set()
                    cancelled = _wait_for_job(manager, submitted["id"])
                self.assertEqual(cancelled["status"], "cancelled")
                publisher.assert_not_called()

                publish_started = threading.Event()
                release_publish = threading.Event()

                def blocked_publisher(staging: Path, destination: Path) -> Path:
                    publish_started.set()
                    self.assertTrue(release_publish.wait(5.0))
                    os.replace(staging, destination)
                    return destination

                manager._publish_cache = blocked_publisher
                with (
                    patch.object(manager, "_spawn", return_value=0),
                    patch.object(manager, "_validate_debug_cache", return_value=None),
                ):
                    committed_submit = manager.submit(
                        "export-debug",
                        {
                            "world": str(world),
                            "output": str(root / "runs" / "debug"),
                            "vtu": False,
                        },
                    )
                    self.assertTrue(publish_started.wait(5.0))
                    late_cancel = manager.cancel(committed_submit["id"])
                    self.assertEqual(late_cancel["status"], "running")
                    release_publish.set()
                    committed = _wait_for_job(manager, committed_submit["id"])
                self.assertEqual(committed["status"], "succeeded")
                self.assertEqual(committed["cache_dir"], "runs/debug")
            finally:
                release_validation.set()
                manager.close()

    def test_terminal_job_state_is_published_after_artifact_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "runs").mkdir()
            world = root / "world.json"
            world.write_text("{}", encoding="utf-8")
            output = root / "runs" / "world.svg"
            manager = JobManager(root, Path("runs"))
            copy_started = threading.Event()
            release_copy = threading.Event()
            real_copy = shutil.copy2

            def write_output(_job: object, _command: list[str]) -> int:
                output.write_text("<svg/>", encoding="utf-8")
                return 0

            def blocked_copy(source: object, target: object, *args: object, **kwargs: object):
                copy_started.set()
                self.assertTrue(release_copy.wait(5.0))
                return real_copy(source, target, *args, **kwargs)

            try:
                with (
                    patch.object(manager, "_spawn", side_effect=write_output),
                    patch("magic_geo.web_jobs.shutil.copy2", side_effect=blocked_copy),
                ):
                    submitted = manager.submit(
                        "render", {"world": str(world), "output": str(output)}
                    )
                    self.assertTrue(copy_started.wait(5.0))
                    during_copy = manager.get(submitted["id"])
                    self.assertEqual(during_copy["status"], "running")
                    self.assertIsNone(during_copy["finished_at"])
                    self.assertFalse(during_copy["artifacts"][0]["available"])
                    release_copy.set()
                    completed = _wait_for_job(manager, submitted["id"])
                self.assertEqual(completed["status"], "succeeded")
                self.assertIsNotNone(completed["finished_at"])
                self.assertTrue(completed["artifacts"][0]["available"])
            finally:
                release_copy.set()
                manager.close()

    def test_generate_job_prepares_a_complete_browser_cache(self) -> None:
        root = Path.cwd().resolve()
        (root / "runs").mkdir(exist_ok=True)
        with TemporaryDirectory(dir=root / "runs", prefix="web-job-test-") as directory:
            workspace = Path(directory)
            manager = JobManager(root, workspace)
            try:
                job = manager.submit(
                    "generate",
                    {
                        "config": "configs/earthlike_seed.yaml",
                        "output": str(workspace / "world.json"),
                        "cells": 128,
                        "geo_only": True,
                        "open_in_web": True,
                        "debug_output": str(workspace / "debug"),
                        "debug_vtu": False,
                    },
                )
                deadline = time.monotonic() + 60.0
                while time.monotonic() < deadline:
                    job = manager.get(job["id"])
                    if job["status"] not in {"queued", "running"}:
                        break
                    time.sleep(0.05)
                self.assertEqual(job["status"], "succeeded", job["log"])
                self.assertEqual(job["cache_dir"], workspace.relative_to(root).joinpath("debug").as_posix())
                self.assertTrue((workspace / "world.json").is_file())

                cache = _DebugCache(workspace / "debug")
                try:
                    self.assertGreater(len(cache.manifest["layers"]), 300)
                    self.assertGreater(len(cache.manifest["families"]), 50)
                    self.assertGreater(len(cache.manifest["sections"]), 20)
                    self.assertTrue(cache.cell_record(0)["complete"])
                finally:
                    cache.close()
            finally:
                manager.close()
