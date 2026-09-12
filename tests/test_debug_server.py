from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import struct
import threading
import tomllib
import time
import xml.etree.ElementTree as ET
from importlib import resources
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable
from urllib.parse import quote, unquote, urlsplit
from unittest import SkipTest, TestCase
from unittest.mock import Mock, patch

try:
    import pyarrow as pa
    import pyarrow.ipc as pa_ipc
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
from magic_geo.config import config_schema
from magic_geo.debug_server import (
    CacheSelectRequest,
    ConfigSaveRequest,
    ConfigTextRequest,
    _CacheManager,
    _DebugCache,
    _json_safe,
    _quote_identifier,
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


def asgi_call(
    app: object,
    method: str,
    path: str,
    *,
    json_body: object = None,
) -> tuple[int, dict[str, str], bytes]:
    """Issue one dependency-free ASGI request through real routing/serialization."""

    messages: list[dict[str, object]] = []
    payload = b"" if json_body is None else json.dumps(json_body).encode("utf-8")
    request_sent = False

    async def receive() -> dict[str, object]:
        nonlocal request_sent
        if not request_sent:
            request_sent = True
            return {"type": "http.request", "body": payload, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message: dict[str, object]) -> None:
        messages.append(message)

    async def run_inline(function: object, *args: object, **kwargs: object) -> object:
        # The minimal debug-test environment intentionally omits Starlette's
        # optional HTTP client/thread-portal extra. Routing and response
        # serialization are what this harness needs to exercise.
        return function(*args, **kwargs)

    parsed = urlsplit(path)
    headers = [(b"accept", b"application/json")]
    if json_body is not None:
        headers.append((b"content-type", b"application/json"))
        headers.append((b"content-length", str(len(payload)).encode("ascii")))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": unquote(parsed.path),
        "raw_path": parsed.path.encode("utf-8"),
        "query_string": parsed.query.encode("ascii"),
        "root_path": "",
        "headers": headers,
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
    response_headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start.get("headers", [])
    }
    return int(start["status"]), response_headers, body


def asgi_get(app: object, path: str) -> tuple[int, bytes]:
    """Issue one dependency-free ASGI GET through real routing/serialization."""

    status, _headers, body = asgi_call(app, "GET", path)
    return status, body


def _detail(body: bytes) -> Any:
    """Return the ``detail`` payload of a JSON error response."""

    return json.loads(body)["detail"]


def _drop(manifest: dict[str, Any], *keys: str) -> None:
    """Remove one nested manifest key in place."""

    target: Any = manifest
    for key in keys[:-1]:
        target = target[key]
    target.pop(keys[-1], None)


def _assign(manifest: dict[str, Any], keys: tuple[str, ...], value: Any) -> None:
    """Replace one nested manifest value in place."""

    target: Any = manifest
    for key in keys[:-1]:
        target = target[key]
    target[keys[-1]] = value


def _mutate_manifest(cache_dir: Path, change: Callable[[dict[str, Any]], Any]) -> None:
    """Rewrite manifest.json after an in-place change (or a returned replacement)."""

    path = cache_dir / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    replacement = change(manifest)
    path.write_text(
        json.dumps(manifest if replacement is None else replacement), encoding="utf-8"
    )


def _case_cache(
    parent: Path, name: str, change: Callable[[dict[str, Any]], Any] | None = None
) -> Path:
    """Create an isolated fixture cache under ``parent`` and optionally break it."""

    case_root = parent / name
    case_root.mkdir(parents=True)
    cache_dir = _make_cache(case_root)
    if change is not None:
        _mutate_manifest(cache_dir, change)
    return cache_dir


def _with_extra_layers(manifest: dict[str, Any]) -> None:
    """Publish a monthly layer plus a layer whose stage history does not exist."""

    manifest["layers"].append(
        {
            "id": "monthly/temperature_c",
            "source": "monthly",
            "name": "temperature_c",
            "kind": "numeric_monthly",
            "month_count": 2,
        }
    )
    manifest["layers"].append(
        {
            "id": "ghost/runoff",
            "source": "ghost",
            "name": "runoff",
            "kind": "numeric_stage",
            "stage_count": 2,
        }
    )


def _with_extra_layers_but_no_monthly_table(manifest: dict[str, Any]) -> None:
    _with_extra_layers(manifest)
    _drop(manifest, "monthly")


def _without_cell_details(manifest: dict[str, Any]) -> None:
    _drop(manifest, "cells", "details_jsonl")
    _drop(manifest, "cells", "details_index")


def _with_paged_families(manifest: dict[str, Any]) -> None:
    _assign(manifest, ("families", "nested", "row_count"), 3)
    _assign(
        manifest,
        ("families", "jsonl_only"),
        {"jsonl": "events/nested.jsonl", "row_count": 3},
    )


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
                self.assertEqual(catalog["coverage"]["cli_command_count"], 15)
                self.assertEqual(
                    {entry["id"] for entry in catalog["equivalents"]},
                    {"init-config", "backend", "export-debug-map", "serve"},
                )

                schema = endpoint(app, "/api/config/schema")()
                self.assertTrue(schema["properties"]["planet"]["description"])
                for definition in schema["$defs"].values():
                    for field_schema in definition.get("properties", {}).values():
                        self.assertTrue(field_schema.get("description"))

                valid = endpoint(app, "/api/config/validate", "POST")(
                    ConfigTextRequest(
                        yaml="config_version: 2\nmesh:\n  cell_count: 128\ntectonics:\n  plate_count: 8\n"
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

    def test_catalog_retains_estimate_display_scope_and_models(self) -> None:
        from magic_geo.public_estimate_display import display_contract

        for scope in ("full", "geo_only"):
            with self.subTest(scope=scope), TemporaryDirectory() as temp_dir:
                root = Path(temp_dir)
                cache_dir = _make_cache(root)
                # Presentation declarations only; no generated-world or model replay.
                contract = display_contract({
                    "generation_scope": scope,
                    "native_social_availability_model": {
                        "model_type": "native_settlement_source_complete_social_estimates_v1",
                    },
                    "population_region_model": {
                        "model_type": "causal_area_weighted_capacity_occupancy_population_regions_v2",
                        "membership_model": "nonwater_political_region_cells_v1",
                    },
                    "population_regions": [],
                })
                _mutate_manifest(cache_dir, lambda manifest: manifest.update(
                    estimate_display=contract,
                ))
                app = create_app(cache_dir, project_root=root, workspace=Path("runs"))
                try:
                    revision = app.state.cache_manager.status()["cache_revision"]
                    status, manifest_body = asgi_get(app, f"/api/manifest?revision={revision}")
                    self.assertEqual(status, 200)
                    status, catalog_body = asgi_get(app, f"/api/catalog?revision={revision}")
                    self.assertEqual(status, 200)
                    manifest = json.loads(manifest_body)
                    catalog = json.loads(catalog_body)
                    self.assertEqual(manifest["estimate_display"], contract)
                    self.assertEqual(catalog.get("estimate_display"), contract)
                    self.assertEqual(catalog["layers"], manifest["layers"])
                    status, _body = asgi_get(app, "/api/catalog?revision=stale")
                    self.assertEqual(status, 409)
                finally:
                    app.state.job_manager.close()
                    app.state.cache_manager.close()

    def test_catalog_does_not_invent_estimate_display_for_legacy_cache(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir = _make_cache(root)
            app = create_app(cache_dir, project_root=root, workspace=Path("runs"))
            try:
                status, manifest_body = asgi_get(app, "/api/manifest")
                self.assertEqual(status, 200)
                status, catalog_body = asgi_get(app, "/api/catalog")
                self.assertEqual(status, 200)
                self.assertNotIn("estimate_display", json.loads(manifest_body))
                self.assertNotIn("estimate_display", json.loads(catalog_body))
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
                        ConfigSaveRequest(yaml="config_version: 2\n", name="escaped.yaml")
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
                                ConfigSaveRequest(yaml="config_version: 2\n", name=name, force=True)
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
            (root / "configs/config.yaml").write_text("config_version: 2\n", encoding="utf-8")
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
                (cache_input_dir / "config.yaml").write_text("config_version: 2\n", encoding="utf-8")
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
                    "export-debug-map",
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
            (root / "configs/config.yaml").write_text("config_version: 2\n", encoding="utf-8")
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


class _WorkbenchTestCase(TestCase):
    """Shared lifecycle helpers; this base class holds no tests of its own."""

    def temp_root(self) -> Path:
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return Path(temporary.name).resolve()

    def serve(self, root: Path, cache_dir: Path | None = None) -> Any:
        app = create_app(cache_dir, project_root=root, workspace=Path("runs"))
        self.addCleanup(app.state.cache_manager.close)
        self.addCleanup(app.state.job_manager.close)
        return app

    def manager(
        self, root: Path, workspace: Path, selected: Path | None = None
    ) -> _CacheManager:
        manager = _CacheManager(root, workspace, selected)
        self.addCleanup(manager.close)
        return manager

    def cache(self, cache_dir: Path) -> _DebugCache:
        cache = _DebugCache(cache_dir)
        self.addCleanup(cache.close)
        return cache


class DebugCacheValidationTests(_WorkbenchTestCase):
    """Manifest validation, confinement guards, and JSON/identifier helpers."""

    def test_manifest_validation_rejects_every_malformed_cache_shape(self) -> None:
        cases: list[tuple[str, Callable[[dict[str, Any]], Any], str]] = [
            (
                "manifest_is_not_an_object",
                lambda manifest: [],
                "manifest and sections must be objects",
            ),
            (
                "world_metadata_missing",
                lambda manifest: _drop(manifest, "world"),
                "missing world/layer metadata",
            ),
            (
                "cell_count_not_numeric",
                lambda manifest: _assign(manifest, ("world", "cell_count"), "many"),
                "missing world/layer metadata",
            ),
            (
                "cell_count_below_one",
                lambda manifest: _assign(manifest, ("world", "cell_count"), 0),
                "invalid cell/layer metadata",
            ),
            (
                "layers_not_a_list",
                lambda manifest: _assign(manifest, ("layers",), {}),
                "invalid cell/layer metadata",
            ),
            (
                "duplicate_layer_ids",
                lambda manifest: manifest["layers"].append(dict(manifest["layers"][0])),
                "duplicate or malformed layer ids",
            ),
            (
                "layer_id_not_a_string",
                lambda manifest: _assign(manifest, ("layers", 0, "id"), 7),
                "duplicate or malformed layer ids",
            ),
            (
                "cells_metadata_not_an_object",
                lambda manifest: _assign(manifest, ("cells",), "tables/cells.parquet"),
                "missing cells metadata",
            ),
            (
                "cells_parquet_path_missing",
                lambda manifest: _drop(manifest, "cells", "parquet"),
                "cells parquet path is missing",
            ),
            (
                "cells_parquet_path_absolute",
                lambda manifest: _assign(manifest, ("cells", "parquet"), "/etc/passwd"),
                "cells parquet path must be relative",
            ),
            (
                "cells_parquet_path_escapes",
                lambda manifest: _assign(
                    manifest, ("cells", "parquet"), "../../outside.parquet"
                ),
                "cells parquet path escapes root",
            ),
            (
                "cells_parquet_file_absent",
                lambda manifest: _assign(
                    manifest, ("cells", "parquet"), "tables/absent.parquet"
                ),
                "missing cells parquet file tables/absent.parquet",
            ),
            (
                "monthly_metadata_not_an_object",
                lambda manifest: _assign(manifest, ("monthly",), 5),
                "malformed monthly metadata",
            ),
            (
                "stage_histories_not_an_object",
                lambda manifest: _assign(manifest, ("stage_histories",), []),
                "malformed stage histories",
            ),
            (
                "stage_history_not_an_object",
                lambda manifest: _assign(manifest, ("stage_histories", "history"), 3),
                "malformed history history",
            ),
            (
                "stage_extras_file_absent",
                lambda manifest: _assign(
                    manifest,
                    ("stage_histories", "history", "extras_jsonl"),
                    "events/absent.jsonl",
                ),
                "missing history stage extras file events/absent.jsonl",
            ),
            (
                "families_not_an_object",
                lambda manifest: _assign(manifest, ("families",), 7),
                "malformed families",
            ),
            (
                "family_not_an_object",
                lambda manifest: _assign(manifest, ("families", "flat"), 1),
                "malformed family flat",
            ),
            (
                "family_without_any_data_file",
                lambda manifest: _assign(manifest, ("families", "flat"), {"row_count": 2}),
                "family flat has no data file",
            ),
            (
                "sections_catalog_not_a_list",
                lambda manifest: _assign(manifest, ("sections",), "model"),
                "malformed section catalog",
            ),
            (
                "section_missing_from_sections_json",
                lambda manifest: manifest["sections"].append("ghost"),
                "malformed section catalog",
            ),
            (
                "mesh_metadata_not_an_object",
                lambda manifest: _assign(manifest, ("mesh",), []),
                "missing mesh buffer catalog",
            ),
            (
                "mesh_buffer_catalog_missing",
                lambda manifest: _drop(manifest, "mesh", "buffers"),
                "missing mesh buffer catalog",
            ),
            (
                "mesh_buffer_descriptor_missing",
                lambda manifest: _drop(manifest, "mesh", "buffers", "indices"),
                "missing mesh buffer indices",
            ),
            (
                "mesh_buffer_file_absent",
                lambda manifest: _assign(
                    manifest, ("mesh", "buffers", "positions", "file"), "mesh/absent.f32"
                ),
                "missing mesh positions file mesh/absent.f32",
            ),
            (
                "paraview_metadata_not_an_object",
                lambda manifest: _assign(manifest, ("paraview",), 4),
                "malformed ParaView metadata",
            ),
            (
                "paraview_collection_absent",
                lambda manifest: _assign(manifest, ("paraview",), {"pvd": "vtu/scene.pvd"}),
                "missing ParaView collection file vtu/scene.pvd",
            ),
        ]
        parent = self.temp_root()
        for index, (label, change, expected) in enumerate(cases):
            with self.subTest(case=label):
                cache_dir = _case_cache(parent, f"case-{index:02d}", change)
                with self.assertRaisesRegex(ValueError, expected):
                    _DebugCache(cache_dir)

    def test_unreadable_metadata_and_backend_failures_become_cache_errors(self) -> None:
        parent = self.temp_root()
        cache_dir = _case_cache(parent, "resolvable")
        real_resolve = Path.resolve

        def refuse(target_name: str) -> Callable[..., Path]:
            def resolve(self_path: Path, *args: object, **kwargs: object) -> Path:
                if self_path.name == target_name:
                    raise OSError(f"injected resolve failure for {target_name}")
                return real_resolve(self_path, *args, **kwargs)

            return resolve

        with patch.object(Path, "resolve", refuse("manifest.json")):
            with self.assertRaisesRegex(ValueError, "metadata path resolution failed"):
                _DebugCache(cache_dir)

        with patch.object(Path, "resolve", refuse("cells.parquet")):
            with self.assertRaisesRegex(
                ValueError, "unable to resolve cells parquet path"
            ):
                _DebugCache(cache_dir)

        with patch(
            "magic_geo.debug_server.duckdb.connect",
            side_effect=RuntimeError("no database handles left"),
        ):
            with self.assertRaisesRegex(
                ValueError, "unable to open DuckDB for debug cache .*no database handles left"
            ):
                _DebugCache(cache_dir)

        # The unpatched fixture still loads, so the guards above are the only cause.
        self.assertEqual(self.cache(cache_dir).cell_count, 2)

    def test_identifier_quoting_and_json_normalisation_reject_unsafe_values(self) -> None:
        self.assertEqual(_quote_identifier('elev"ation'), '"elev""ation"')
        with self.assertRaises(HTTPException) as context:
            _quote_identifier("bad\x00name")
        self.assertEqual(context.exception.status_code, 400)
        self.assertEqual(context.exception.detail, "invalid NUL in field name")

        self.assertEqual(
            _json_safe(
                {
                    "tuple": (1.0, float("inf")),
                    "list": [float("nan"), "text", 3],
                    "scalar": float("-inf"),
                    "finite": -0.5,
                }
            ),
            {
                "tuple": [1.0, None],
                "list": [None, "text", 3],
                "scalar": None,
                "finite": -0.5,
            },
        )

    def test_cache_paths_reject_absolute_missing_and_escaping_targets(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        cache = self.cache(cache_dir)

        with self.assertRaises(HTTPException) as absolute:
            cache._data_path("/etc/passwd")
        self.assertEqual(absolute.exception.status_code, 400)
        self.assertEqual(absolute.exception.detail, "cache paths must be relative")

        with self.assertRaises(HTTPException) as missing:
            cache._data_path("tables/absent.parquet")
        self.assertEqual(missing.exception.status_code, 404)
        self.assertEqual(
            missing.exception.detail, "missing cache file tables/absent.parquet"
        )
        self.assertEqual(
            cache._data_path("tables/absent.parquet", require_file=False),
            cache_dir / "tables" / "absent.parquet",
        )

        with self.assertRaises(HTTPException) as mesh_absolute:
            cache.mesh_path("/etc/positions.f32")
        self.assertEqual(mesh_absolute.exception.status_code, 400)
        self.assertEqual(mesh_absolute.exception.detail, "mesh paths must be relative")

        with self.assertRaises(HTTPException) as mesh_missing:
            cache.mesh_path("absent.f32")
        self.assertEqual(mesh_missing.exception.status_code, 404)
        self.assertEqual(mesh_missing.exception.detail, "missing mesh asset absent.f32")

        # A mesh directory swapped for a symlink after startup stops serving.
        external = root / "external-mesh"
        shutil.move(str(cache_dir / "mesh"), str(external))
        (cache_dir / "mesh").symlink_to(external, target_is_directory=True)
        with self.assertRaises(HTTPException) as escaping:
            cache.mesh_path("positions.f32")
        self.assertEqual(escaping.exception.status_code, 400)
        self.assertEqual(
            escaping.exception.detail, "mesh directory escapes cache root"
        )

    def test_missing_manifest_tables_degrade_to_not_found_responses(self) -> None:
        root = self.temp_root()
        cache = self.cache(_make_cache(root))

        cache.manifest["cells"] = None
        with self.assertRaises(HTTPException) as cells:
            cache.layer_values("cells/elevation_m", None, None)
        self.assertEqual(cells.exception.status_code, 404)
        self.assertEqual(cells.exception.detail, "cells table is unavailable")

        cache.manifest["families"]["orphan"] = {"row_count": 0}
        with self.assertRaises(HTTPException) as family:
            cache.family_rows("orphan", 10, 0, "full")
        self.assertEqual(family.exception.status_code, 404)
        self.assertEqual(
            family.exception.detail, "family orphan has no readable data"
        )


class CacheManagerDegradationTests(_WorkbenchTestCase):
    """Selection, discovery, publication rollback, and cache-loss behaviour."""

    def test_workspace_must_stay_inside_the_project_and_selection_needs_a_manifest(
        self,
    ) -> None:
        root = self.temp_root()
        project = root / "project"
        project.mkdir()
        with self.assertRaisesRegex(
            ValueError, "web workspace must be inside the project directory"
        ):
            _CacheManager(project, root / "outside", None)

        _make_cache(project)
        manager = self.manager(project, Path("runs"), Path("runs/debug"))
        self.assertEqual(manager.selected_relative(), "runs/debug")

        empty = project / "runs" / "empty"
        empty.mkdir()
        with self.assertRaisesRegex(
            ValueError, f"no manifest.json in {re.escape(str(empty))}"
        ):
            manager.select(empty)
        self.assertEqual(manager.selected_relative(), "runs/debug")
        self.assertEqual(manager.get().manifest["world"]["name"], "tiny")

    def test_cacheless_manager_reports_no_selection_revision_or_error(self) -> None:
        root = self.temp_root()
        manager = self.manager(root, Path("runs"), None)
        self.assertIsNone(manager._revision_unlocked())
        self.assertEqual(
            manager.status(),
            {
                "cache_available": False,
                "cache_dir": None,
                "cache_error": None,
                "cache_revision": None,
            },
        )
        self.assertIsNone(manager.get(required=False))
        with self.assertRaises(HTTPException) as context:
            manager.get()
        self.assertEqual(context.exception.status_code, 409)
        self.assertEqual(
            context.exception.detail,
            "no debug cache selected; generate a world or run export-debug",
        )

    def test_default_discovery_prefers_direct_then_newest_nested_cache(self) -> None:
        parent = self.temp_root()
        direct_root = parent / "direct"
        direct_root.mkdir()
        _make_cache(direct_root)
        direct_manager = self.manager(direct_root, Path("runs"), None)
        self.assertEqual(direct_manager.selected_relative(), "runs/debug")
        self.assertTrue(direct_manager.status()["cache_available"])

        nested_root = parent / "nested"
        nested_root.mkdir()
        seed = _make_cache(nested_root)
        alpha = nested_root / "runs" / "alpha" / "debug"
        beta = nested_root / "runs" / "beta" / "debug"
        shutil.copytree(seed, alpha)
        shutil.copytree(seed, beta)
        shutil.rmtree(seed)
        _mutate_manifest(beta, lambda manifest: _assign(manifest, ("world", "name"), "newest"))
        stale = (alpha / "manifest.json").stat()
        os.utime(
            alpha / "manifest.json",
            ns=(stale.st_atime_ns, stale.st_mtime_ns - 5_000_000_000),
        )

        nested_manager = self.manager(nested_root, Path("runs"), None)
        self.assertEqual(nested_manager.selected_relative(), "runs/beta/debug")
        self.assertEqual(nested_manager.get().manifest["world"]["name"], "newest")

    def test_discovery_ignores_caches_that_resolve_outside_the_workspace(self) -> None:
        parent = self.temp_root()
        root = parent / "project"
        (root / "runs" / "linked").mkdir(parents=True)
        external = parent / "external"
        external.mkdir()
        smuggled = _make_cache(external)
        (root / "runs" / "linked" / "debug").symlink_to(smuggled, target_is_directory=True)

        manager = self.manager(root, Path("runs"), None)
        self.assertEqual(
            manager.status(),
            {
                "cache_available": False,
                "cache_dir": None,
                "cache_error": None,
                "cache_revision": None,
            },
        )
        self.assertEqual(manager.available(), [])

    def test_discovery_skips_candidates_whose_metadata_cannot_be_read(self) -> None:
        root = self.temp_root()
        seed = _make_cache(root)
        nested = root / "runs" / "nested" / "debug"
        shutil.copytree(seed, nested)
        shutil.rmtree(seed)
        real_resolve = Path.resolve

        def failing_resolve(self_path: Path, *args: object, **kwargs: object) -> Path:
            if self_path.name == "debug":
                raise OSError("injected discovery failure")
            return real_resolve(self_path, *args, **kwargs)

        with patch.object(Path, "resolve", failing_resolve):
            manager = self.manager(root, Path("runs"), None)
            self.assertIsNone(manager.selected_relative())

        # Without the injected failure the very same workspace is discovered.
        self.assertEqual(
            self.manager(root, Path("runs"), None).selected_relative(),
            "runs/nested/debug",
        )

    def test_select_reports_stat_failures_after_validating_the_candidate(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        manager = self.manager(root, Path("runs"), cache_dir)
        replacement = root / "runs" / "replacement"
        shutil.copytree(cache_dir, replacement)
        _mutate_manifest(
            replacement, lambda manifest: _assign(manifest, ("world", "name"), "replacement")
        )
        real_stat = Path.stat
        real_cache = _DebugCache
        armed = {"value": False}

        def arm_after_validation(path: Path) -> _DebugCache:
            candidate = real_cache(path)
            armed["value"] = True
            return candidate

        def flaky_stat(self_path: Path, *args: object, **kwargs: object) -> os.stat_result:
            if armed["value"] and self_path.name == "manifest.json":
                raise OSError("injected stat failure")
            return real_stat(self_path, *args, **kwargs)

        try:
            with (
                patch("magic_geo.debug_server._DebugCache", arm_after_validation),
                patch.object(Path, "stat", flaky_stat),
            ):
                with self.assertRaisesRegex(OSError, "injected stat failure"):
                    manager.select(replacement)
        finally:
            armed["value"] = False

        self.assertEqual(manager.selected_relative(), "runs/debug")
        self.assertEqual(manager.get().manifest["world"]["name"], "tiny")

    def test_select_and_job_publication_keep_metadata_and_revision_together(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        manager = self.manager(root, Path("runs"), cache_dir)
        original_revision = manager.status()["cache_revision"]
        staging = root / "runs" / ".debug.staging"
        shutil.copytree(cache_dir, staging)
        _mutate_manifest(
            staging, lambda manifest: _assign(manifest, ("world", "name"), "published")
        )
        _write_parquet(
            staging / "tables/cells.parquet",
            {"id": [0, 1], "elevation_m": [101.0, -202.0], "biome": ["forest", "ocean"]},
        )
        candidate_loaded = threading.Event()
        publication_attempted = threading.Event()
        publication_finished = threading.Event()
        failures = []
        real_cache = _DebugCache
        real_lock = manager._lock

        class CoordinatedLock:
            """Expose entry order without changing the real lock's exclusion."""

            def __init__(self) -> None:
                self.local = threading.local()

            def __enter__(self) -> None:
                if threading.current_thread() is publisher:
                    publication_attempted.set()
                real_lock.acquire()
                self.local.depth = getattr(self.local, "depth", 0) + 1

            def __exit__(self, *_args: object) -> None:
                self.local.depth -= 1
                real_lock.release()

            def held_here(self) -> bool:
                return getattr(self.local, "depth", 0) > 0

        coordinated = CoordinatedLock()
        manager._lock = coordinated

        def load_candidate(path: Path) -> _DebugCache:
            candidate = real_cache(path)
            if threading.current_thread() is selector:
                candidate_loaded.set()
                self.assertTrue(publication_attempted.wait(5.0))
                # Complete the competing publication before returning the old
                # candidate whenever select permits that interleaving. If
                # select owns the lock, it must finish before publication can.
                if not coordinated.held_here():
                    self.assertTrue(publication_finished.wait(5.0))
            return candidate

        def choose() -> None:
            try:
                manager.select(cache_dir)
            except Exception as exc:
                failures.append(exc)

        def publish() -> None:
            try:
                manager.publish(staging, cache_dir)
            except Exception as exc:
                failures.append(exc)
            finally:
                publication_finished.set()

        selector = threading.Thread(target=choose, daemon=True)
        publisher = threading.Thread(target=publish, daemon=True)
        with patch("magic_geo.debug_server._DebugCache", load_candidate):
            selector.start()
            self.assertTrue(candidate_loaded.wait(5.0))
            publisher.start()
            selector.join(5.0)
            publisher.join(5.0)
        self.assertFalse(selector.is_alive())
        self.assertFalse(publisher.is_alive())
        self.assertEqual(failures, [])

        revision = manager.status()["cache_revision"]
        self.assertNotEqual(revision, original_revision)
        observed = manager.with_cache(
            lambda cache: {
                "api_manifest_name": cache.manifest["world"]["name"],
                "layer_values": cache.layer_values("cells/elevation_m", None, None),
                "file_manifest_name": json.loads((cache_dir / "manifest.json").read_bytes())["world"]["name"],
            },
            revision,
        )
        self.assertEqual(observed, {
            "api_manifest_name": "published", "layer_values": [101.0, -202.0],
            "file_manifest_name": "published",
        })
        with self.assertRaises(HTTPException) as stale:
            manager.with_cache(lambda cache: cache.manifest, original_revision)
        self.assertEqual(stale.exception.status_code, 409)

    def test_status_and_reads_degrade_when_the_manifest_disappears(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        app = self.serve(root, cache_dir)
        manager = app.state.cache_manager
        self.assertEqual(asgi_call(app, "GET", "/api/manifest")[0], 200)

        (cache_dir / "manifest.json").unlink()
        status, _headers, body = asgi_call(app, "GET", "/api/manifest")
        self.assertEqual(status, 409, body)
        self.assertEqual(_detail(body), f"no manifest.json in {cache_dir}")

        payload = json.loads(asgi_call(app, "GET", "/api/status")[2])
        self.assertFalse(payload["cache_available"])
        self.assertEqual(payload["cache_error"], f"no manifest.json in {cache_dir}")
        self.assertIsNone(payload["cache_revision"])
        self.assertIsNone(manager._cache)

    def test_corrupt_manifest_without_a_live_cache_is_reported_and_recovers(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        valid = json.loads((cache_dir / "manifest.json").read_text(encoding="utf-8"))
        app = self.serve(root, None)

        (cache_dir / "manifest.json").write_text("{", encoding="utf-8")
        status, _headers, body = asgi_call(app, "GET", "/api/catalog")
        self.assertEqual(status, 500, body)
        self.assertRegex(_detail(body), r"^invalid debug cache .*: Expecting")

        payload = json.loads(asgi_call(app, "GET", "/api/status")[2])
        self.assertFalse(payload["cache_available"])
        self.assertRegex(payload["cache_error"], r"^invalid debug cache ")
        self.assertIsNone(payload["cache_revision"])

        (cache_dir / "manifest.json").write_text(json.dumps(valid), encoding="utf-8")
        status, _headers, body = asgi_call(app, "GET", "/api/catalog")
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["world"]["name"], "tiny")
        self.assertIsNone(json.loads(asgi_call(app, "GET", "/api/status")[2])["cache_error"])

    def test_manifest_stat_failures_are_surfaced_as_conflicts(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        manager = self.manager(root, Path("runs"), cache_dir)
        revision = manager.status()["cache_revision"]
        real_stat = Path.stat
        calls = {"count": 0}

        def flaky_stat(self_path: Path, *args: object, **kwargs: object) -> os.stat_result:
            if self_path.name == "manifest.json":
                calls["count"] += 1
                if calls["count"] >= 2:
                    raise OSError("injected stat failure")
            return real_stat(self_path, *args, **kwargs)

        with patch.object(Path, "stat", flaky_stat):
            calls["count"] = 0
            optional = manager.status()
            calls["count"] = 0
            with self.assertRaises(HTTPException) as context:
                manager.get()
        self.assertFalse(optional["cache_available"])
        self.assertRegex(optional["cache_error"], r"^unable to stat .*: injected stat failure$")
        # The fingerprint of the last good load survives the failed stat, but an
        # unavailable cache must never advertise a revision clients could pin to.
        self.assertIsNone(optional["cache_revision"])
        self.assertEqual(optional["cache_dir"], "runs/debug")
        self.assertEqual(context.exception.status_code, 409)
        self.assertRegex(
            context.exception.detail, r"^unable to stat .*: injected stat failure$"
        )
        self.assertTrue(manager.status()["cache_available"])
        self.assertEqual(manager.status()["cache_revision"], revision)

    def test_selected_relative_falls_back_to_the_absolute_path(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        manager = self.manager(root, Path("runs"), cache_dir)
        self.assertEqual(manager.selected_relative(), "runs/debug")
        elsewhere = Path("/var/tmp/magic-geo-elsewhere")
        manager._selected = elsewhere
        self.assertEqual(manager.selected_relative(), str(elsewhere))

    def test_remove_path_deletes_trees_and_swallows_filesystem_errors(self) -> None:
        root = self.temp_root()
        tree = root / "tree"
        (tree / "inner").mkdir(parents=True)
        (tree / "inner" / "file.txt").write_text("payload", encoding="utf-8")
        loose = root / "loose.txt"
        loose.write_text("payload", encoding="utf-8")

        _CacheManager._remove_path(loose)
        self.assertFalse(loose.exists())
        _CacheManager._remove_path(root / "never-existed")

        with patch(
            "magic_geo.debug_server.shutil.rmtree", side_effect=OSError("device busy")
        ):
            _CacheManager._remove_path(tree)
        self.assertTrue((tree / "inner" / "file.txt").is_file())

        _CacheManager._remove_path(tree)
        self.assertFalse(tree.exists())

    def test_publish_rejects_targets_outside_the_workspace(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        manager = self.manager(root, Path("runs"), cache_dir)
        outside = root / "outside-staging"
        shutil.copytree(cache_dir, outside)

        with self.assertRaisesRegex(
            ValueError, "published cache must stay inside the web workspace"
        ):
            manager.publish(outside, root / "runs" / "published")
        with self.assertRaisesRegex(
            ValueError, "published cache must stay inside the web workspace"
        ):
            manager.publish(root / "runs" / "staging", root / "outside-destination")

        blocker = root / "runs" / "blocker.txt"
        blocker.write_text("not a directory", encoding="utf-8")
        staging = root / "runs" / "staging"
        shutil.copytree(cache_dir, staging)
        with self.assertRaisesRegex(
            ValueError, "cache destination is not a directory"
        ):
            manager.publish(staging, blocker)
        self.assertTrue((staging / "manifest.json").is_file())
        self.assertEqual(manager.get().manifest["world"]["name"], "tiny")

    def test_publish_rolls_back_when_the_moved_cache_fails_validation(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        manager = self.manager(root, Path("runs"), cache_dir)
        staging = root / "runs" / ".debug.staging"
        shutil.copytree(cache_dir, staging)
        _mutate_manifest(
            staging, lambda manifest: _assign(manifest, ("world", "name"), "candidate")
        )
        real_cache = _DebugCache
        calls = {"count": 0}

        def fail_after_the_move(path: Path) -> _DebugCache:
            calls["count"] += 1
            if calls["count"] == 2:
                raise ValueError("injected post-move validation failure")
            return real_cache(path)

        with patch("magic_geo.debug_server._DebugCache", fail_after_the_move):
            with self.assertRaisesRegex(
                ValueError, "injected post-move validation failure"
            ):
                manager.publish(staging, cache_dir)

        self.assertEqual(calls["count"], 2)
        self.assertFalse(staging.exists())
        self.assertEqual(manager.get().manifest["world"]["name"], "tiny")
        self.assertEqual(list((root / "runs").glob(".debug.*.backup")), [])

    def test_publish_restores_the_destination_when_the_commit_step_fails(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        manager = self.manager(root, Path("runs"), cache_dir)
        original = (cache_dir / "manifest.json").read_bytes()
        staging = root / "runs" / ".debug.staging"
        shutil.copytree(cache_dir, staging)
        _mutate_manifest(
            staging, lambda manifest: _assign(manifest, ("world", "name"), "half-published")
        )

        def explode(_stat: os.stat_result) -> tuple[int, int, int, int]:
            raise RuntimeError("injected fingerprint failure")

        # The staged cache validates after the move, so the failure lands past
        # the inner rollback and only the outer handler can undo the swap.
        with patch.object(_CacheManager, "_manifest_fingerprint", staticmethod(explode)):
            with self.assertRaisesRegex(RuntimeError, "injected fingerprint failure"):
                manager.publish(staging, cache_dir)

        self.assertEqual((cache_dir / "manifest.json").read_bytes(), original)
        self.assertEqual(json.loads(original)["world"]["name"], "tiny")
        self.assertFalse(staging.exists())
        self.assertEqual(list((root / "runs").glob(".debug.*.backup")), [])
        self.assertEqual(self.cache(cache_dir).manifest["world"]["name"], "tiny")

    def test_publish_survives_a_failing_close_of_the_replaced_cache(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        manager = self.manager(root, Path("runs"), cache_dir)
        previous = manager.get()
        previous.close = Mock(side_effect=RuntimeError("connection already gone"))
        staging = root / "runs" / ".debug.staging"
        shutil.copytree(cache_dir, staging)
        _mutate_manifest(
            staging, lambda manifest: _assign(manifest, ("world", "name"), "republished")
        )

        published = manager.publish(staging, cache_dir)

        self.assertEqual(published, cache_dir)
        previous.close.assert_called_once_with()
        self.assertEqual(manager.get().manifest["world"]["name"], "republished")
        self.assertEqual(list((root / "runs").glob(".debug.*.backup")), [])
        self.assertFalse(staging.exists())

    def test_available_worlds_skip_hidden_unreadable_and_unsupported_manifests(
        self,
    ) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        workspace = root / "runs"
        shutil.copytree(cache_dir, workspace, dirs_exist_ok=True)

        outside = root / "outside-manifest.json"
        outside.write_text(
            json.dumps(
                {"format": FORMAT_NAME, "version": FORMAT_VERSION, "world": {"name": "leak"}}
            ),
            encoding="utf-8",
        )
        (workspace / "linked").mkdir()
        (workspace / "linked" / "manifest.json").symlink_to(outside)
        (workspace / "listy").mkdir()
        (workspace / "listy" / "manifest.json").write_text("[]", encoding="utf-8")
        (workspace / "future").mkdir()
        (workspace / "future" / "manifest.json").write_text(
            json.dumps(
                {
                    "format": FORMAT_NAME,
                    "version": FORMAT_VERSION + 1,
                    "world": {"name": "future"},
                }
            ),
            encoding="utf-8",
        )
        (workspace / "worldless").mkdir()
        (workspace / "worldless" / "manifest.json").write_text(
            json.dumps({"format": FORMAT_NAME, "version": FORMAT_VERSION, "world": []}),
            encoding="utf-8",
        )
        (workspace / "broken").mkdir()
        (workspace / "broken" / "manifest.json").write_text("{", encoding="utf-8")
        (workspace / ".magic-geo-web" / "jobs").mkdir(parents=True)
        shutil.copy2(
            cache_dir / "manifest.json", workspace / ".magic-geo-web" / "jobs" / "manifest.json"
        )
        (workspace / ".debug.abc123.staging").mkdir()
        shutil.copy2(
            cache_dir / "manifest.json", workspace / ".debug.abc123.staging" / "manifest.json"
        )
        (workspace / ".debug.abc123.backup").mkdir()
        shutil.copy2(
            cache_dir / "manifest.json", workspace / ".debug.abc123.backup" / "manifest.json"
        )

        manager = self.manager(root, Path("runs"), cache_dir)
        worlds = {world["id"]: world for world in manager.available()}
        self.assertEqual(sorted(worlds), ["runs", "runs/debug"])
        self.assertEqual(
            {identifier: world["selected"] for identifier, world in worlds.items()},
            {"runs": False, "runs/debug": True},
        )
        self.assertEqual(
            {identifier: world["cell_count"] for identifier, world in worlds.items()},
            {"runs": 2, "runs/debug": 2},
        )
        self.assertEqual(
            {identifier: world["name"] for identifier, world in worlds.items()},
            {"runs": "tiny", "runs/debug": "tiny"},
        )
        self.assertEqual(worlds["runs/debug"]["generation_scope"], "full")


class DebugServerApiErrorTests(_WorkbenchTestCase):
    """Every 4xx/5xx the HTTP surface can return, asserted through real routing."""

    def test_layer_endpoint_rejects_unknown_ids_and_out_of_range_selectors(self) -> None:
        parent = self.temp_root()
        cache_dir = _case_cache(parent, "layers", _with_extra_layers)
        app = self.serve(parent / "layers", cache_dir)

        status, _headers, body = asgi_call(
            app, "GET", "/api/layer/monthly/temperature_c?month=1"
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(struct.unpack("<2f", body), (13.0, 3.0))
        self.assertEqual(
            struct.unpack("<2f", asgi_call(app, "GET", "/api/layer/monthly/temperature_c")[2]),
            (12.0, 2.0),
        )

        for path, expected_status, expected_detail in (
            ("/api/layer/cells/missing", 404, "unknown layer cells/missing"),
            ("/api/layer/monthly/temperature_c?month=5", 400, "month 5 out of range"),
            ("/api/layer/ghost/runoff", 404, "missing stage history ghost"),
            ("/api/layer/history/runoff?stage=7", 400, "stage 7 out of range"),
        ):
            with self.subTest(path=path):
                status, _headers, body = asgi_call(app, "GET", path)
                self.assertEqual(status, expected_status, body)
                self.assertEqual(_detail(body), expected_detail)

        for path, expected_type, expected_loc in (
            ("/api/layer/cells/elevation_m?month=12", "less_than_equal", ["query", "month"]),
            ("/api/layer/cells/elevation_m?stage=-1", "greater_than_equal", ["query", "stage"]),
            ("/api/layer/cells/elevation_m?format=csv", "literal_error", ["query", "format"]),
            ("/api/layer/cells/elevation_m?month=many", "int_parsing", ["query", "month"]),
        ):
            with self.subTest(path=path):
                status, _headers, body = asgi_call(app, "GET", path)
                self.assertEqual(status, 422, body)
                error = _detail(body)[0]
                self.assertEqual(error["type"], expected_type)
                self.assertEqual(error["loc"], expected_loc)

        degraded_dir = _case_cache(
            parent, "monthly-missing", _with_extra_layers_but_no_monthly_table
        )
        degraded_app = self.serve(parent / "monthly-missing", degraded_dir)
        status, _headers, body = asgi_call(
            degraded_app, "GET", "/api/layer/monthly/temperature_c"
        )
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "monthly table is unavailable")

    def test_arrow_layer_response_carries_typed_cell_values(self) -> None:
        root = self.temp_root()
        app = self.serve(root, _make_cache(root))
        status, headers, body = asgi_call(
            app, "GET", "/api/layer/cells/elevation_m?format=arrow"
        )
        self.assertEqual(status, 200, body)
        self.assertEqual(headers["content-type"], "application/vnd.apache.arrow.stream")
        self.assertEqual(headers["cache-control"], "no-store")
        table = pa_ipc.open_stream(pa.py_buffer(body)).read_all()
        self.assertEqual(table.column_names, ["cell_id", "value"])
        # The browser decodes these buffers by fixed width, so the narrow
        # Arrow types are part of the wire contract, not an implementation
        # detail of pyarrow's default inference.
        self.assertEqual(table.schema.field("cell_id").type, pa.int32())
        self.assertEqual(table.schema.field("value").type, pa.float32())
        self.assertEqual(table.column("cell_id").to_pylist(), [0, 1])
        self.assertEqual(table.column("value").to_pylist(), [10.0, -20.0])

    def test_cell_endpoint_rejects_out_of_range_ids_and_degrades_without_details(
        self,
    ) -> None:
        parent = self.temp_root()
        cache_dir = _case_cache(parent, "cells")
        app = self.serve(parent / "cells", cache_dir)

        status, _headers, body = asgi_call(app, "GET", "/api/cell/99")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "cell 99 out of range")

        # Cell 1 has no entry in the detail index, so the record stays partial.
        status, _headers, body = asgi_call(app, "GET", "/api/cell/1")
        self.assertEqual(status, 200, body)
        payload = json.loads(body)
        self.assertTrue(payload["complete"])
        self.assertEqual(payload["cell"]["biome"], "ocean")
        self.assertNotIn("neighbors", payload["cell"])

        sparse_dir = _case_cache(
            parent, "sparse", lambda manifest: _assign(manifest, ("world", "cell_count"), 5)
        )
        sparse_app = self.serve(parent / "sparse", sparse_dir)
        status, _headers, body = asgi_call(sparse_app, "GET", "/api/cell/3")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "cell 3 not found")

        detail_less_dir = _case_cache(parent, "detail-less", _without_cell_details)
        detail_less_app = self.serve(parent / "detail-less", detail_less_dir)
        status, _headers, body = asgi_call(detail_less_app, "GET", "/api/cell/0")
        self.assertEqual(status, 200, body)
        payload = json.loads(body)
        self.assertFalse(payload["complete"])
        self.assertNotIn("neighbors", payload["cell"])
        self.assertEqual(payload["cell"]["elevation_m"], 10.0)

    def test_corrupt_cell_detail_sidecars_report_server_errors(self) -> None:
        parent = self.temp_root()
        index_dir = _case_cache(parent, "bad-index")
        (index_dir / "tables/cell_details_index.json").write_text("[]", encoding="utf-8")
        index_app = self.serve(parent / "bad-index", index_dir)
        status, _headers, body = asgi_call(index_app, "GET", "/api/cell/0")
        self.assertEqual(status, 500, body)
        self.assertEqual(_detail(body), "invalid cell details index")

        record_dir = _case_cache(parent, "bad-record")
        (record_dir / "events/cell_details.jsonl").write_text(
            "this is not json\n", encoding="utf-8"
        )
        record_app = self.serve(parent / "bad-record", record_dir)
        status, _headers, body = asgi_call(record_app, "GET", "/api/cell/0")
        self.assertEqual(status, 500, body)
        self.assertEqual(_detail(body), "invalid cell details record")

    def test_family_endpoint_pages_rejects_and_falls_back_to_jsonl(self) -> None:
        parent = self.temp_root()
        cache_dir = _case_cache(parent, "families", _with_paged_families)
        records = [
            {"id": index, "score": index / 2, "cell_ids": [index]} for index in range(3)
        ]
        (cache_dir / "events/nested.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8"
        )
        app = self.serve(parent / "families", cache_dir)

        status, _headers, body = asgi_call(app, "GET", "/api/family/nested?limit=1&offset=1")
        self.assertEqual(status, 200, body)
        payload = json.loads(body)
        self.assertEqual(payload["rows"], [records[1]])
        self.assertEqual(
            (
                payload["name"],
                payload["total"],
                payload["offset"],
                payload["limit"],
                payload["next_offset"],
                payload["detail"],
            ),
            ("nested", 3, 1, 1, 2, "full"),
        )

        payload = json.loads(asgi_call(app, "GET", "/api/family/nested?offset=2")[2])
        self.assertEqual(payload["rows"], [records[2]])
        self.assertIsNone(payload["next_offset"])

        # A missing sidecar changes storage, not the requested scalar view.
        payload = json.loads(
            asgi_call(app, "GET", "/api/family/jsonl_only?detail=scalars&limit=2")[2]
        )
        self.assertEqual(payload["rows"], [{"id": row["id"], "score": row["score"]} for row in records[:2]])
        self.assertEqual(payload["detail"], "scalars")

        status, _headers, body = asgi_call(app, "GET", "/api/family/ghost")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "unknown family ghost")

        status, _headers, body = asgi_call(app, "GET", "/api/section/ghost")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "unknown section ghost")

        status, _headers, body = asgi_call(app, "GET", "/api/stage-summary/ghost")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "unknown stage history ghost")

        for query, expected_type, field in (
            ("limit=0", "greater_than_equal", "limit"),
            ("limit=5001", "less_than_equal", "limit"),
            ("offset=-1", "greater_than_equal", "offset"),
            ("detail=partial", "literal_error", "detail"),
        ):
            with self.subTest(query=query):
                status, _headers, body = asgi_call(app, "GET", f"/api/family/nested?{query}")
                self.assertEqual(status, 422, body)
                error = _detail(body)[0]
                self.assertEqual(error["type"], expected_type)
                self.assertEqual(error["loc"], ["query", field])

    def test_plate_boundaries_are_empty_without_an_adjacency_family(self) -> None:
        parent = self.temp_root()
        cache_dir = _case_cache(
            parent,
            "no-edges",
            lambda manifest: _drop(manifest, "families", "cell_adjacency_edges"),
        )
        app = self.serve(parent / "no-edges", cache_dir)
        status, _headers, body = asgi_call(app, "GET", "/api/plate-boundaries")
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body), [])
        self.assertEqual(
            json.loads(asgi_call(app, "GET", "/api/cell/0")[2])["adjacency_edges"], []
        )

    def test_mesh_assets_are_served_and_confined_to_the_mesh_directory(self) -> None:
        root = self.temp_root()
        app = self.serve(root, _make_cache(root))

        status, headers, body = asgi_call(app, "GET", "/mesh/positions.f32")
        self.assertEqual(status, 200, body)
        self.assertEqual(struct.unpack("<3f", body), (0.0, 0.0, 1.0))
        self.assertEqual(headers["content-type"], "application/octet-stream")
        self.assertEqual(headers["cache-control"], "no-store")

        status, _headers, body = asgi_call(app, "GET", "/mesh/absent.f32")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "missing mesh asset absent.f32")

        status, _headers, body = asgi_call(app, "GET", "/mesh/../manifest.json")
        self.assertEqual(status, 400, body)
        self.assertEqual(
            _detail(body), "mesh path escapes mesh root: ../manifest.json"
        )

    def test_job_endpoints_reject_unknown_jobs_and_invalid_operations(self) -> None:
        root = self.temp_root()
        app = self.serve(root, None)
        jobs = app.state.job_manager

        status, _headers, body = asgi_call(app, "GET", "/api/jobs")
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body), {"jobs": []})

        status, _headers, body = asgi_call(
            app, "POST", "/api/jobs", json_body={"operation": "teleport", "arguments": {}}
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(_detail(body), "unknown operation: teleport")

        status, _headers, body = asgi_call(
            app,
            "POST",
            "/api/jobs",
            json_body={"operation": "validate", "arguments": {"world": "/etc/passwd"}},
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(_detail(body), f"input path must stay inside {root}: /etc/passwd")

        status, _headers, body = asgi_call(
            app, "POST", "/api/jobs", json_body={"operation": "validate", "unexpected": 1}
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(_detail(body)[0]["type"], "extra_forbidden")
        self.assertEqual(_detail(body)[0]["loc"], ["body", "unexpected"])

        status, _headers, body = asgi_call(app, "GET", "/api/jobs/nope")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "unknown job nope")

        status, _headers, body = asgi_call(app, "POST", "/api/jobs/nope/cancel")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "unknown job nope")

        status, _headers, body = asgi_call(app, "GET", "/api/jobs/nope/artifacts/0")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "unknown artifact")

        artifact = root / "runs" / "report.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b'{"passed":true}')
        with patch.object(jobs, "artifact_path", side_effect=FileNotFoundError("gone")):
            status, _headers, body = asgi_call(app, "GET", "/api/jobs/nope/artifacts/0")
        self.assertEqual(status, 404, body)
        self.assertEqual(_detail(body), "artifact is not available")

        with patch.object(jobs, "artifact_path", return_value=artifact):
            status, headers, body = asgi_call(app, "GET", "/api/jobs/nope/artifacts/0")
        self.assertEqual(status, 200, body)
        self.assertEqual(body, b'{"passed":true}')
        self.assertEqual(
            headers["content-disposition"], 'attachment; filename="report.json"'
        )

    def test_world_selection_rejects_unresolvable_and_out_of_workspace_paths(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        app = self.serve(root, cache_dir)
        (root / "outside").mkdir()

        status, _headers, body = asgi_call(
            app, "POST", "/api/worlds/select", json_body={"cache_dir": "outside"}
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(_detail(body), "cache must be inside the web workspace")

        empty = root / "runs" / "empty"
        empty.mkdir()
        status, _headers, body = asgi_call(
            app, "POST", "/api/worlds/select", json_body={"cache_dir": "runs/empty"}
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(_detail(body), f"no manifest.json in {empty}")

        real_resolve = Path.resolve

        def failing_resolve(self_path: Path, *args: object, **kwargs: object) -> Path:
            if self_path.name == "unresolvable":
                raise OSError("injected resolve failure")
            return real_resolve(self_path, *args, **kwargs)

        with patch.object(Path, "resolve", failing_resolve):
            status, _headers, body = asgi_call(
                app,
                "POST",
                "/api/worlds/select",
                json_body={"cache_dir": "runs/unresolvable"},
            )
        self.assertEqual(status, 422, body)
        self.assertEqual(
            _detail(body), "unable to resolve cache path: injected resolve failure"
        )

        status, _headers, body = asgi_call(
            app, "POST", "/api/worlds/select", json_body={"cache_dir": "runs/debug"}
        )
        self.assertEqual(status, 200, body)
        payload = json.loads(body)
        self.assertTrue(payload["cache_available"])
        self.assertEqual(payload["cache_dir"], "runs/debug")

    def test_config_endpoints_reject_unknown_profiles_overrides_and_names(self) -> None:
        root = self.temp_root()
        app = self.serve(root, None)

        profiles = json.loads(asgi_call(app, "GET", "/api/config/profiles")[2])
        self.assertEqual(profiles["default"], "earthlike")
        self.assertEqual(
            {entry["name"] for entry in profiles["profiles"]},
            {"default", "earthlike", "smoke"},
        )
        # The endpoint projects exactly name/description out of the schema
        # metadata; nothing else about a profile is published to the browser.
        self.assertEqual(
            {entry["name"]: entry["description"] for entry in profiles["profiles"]},
            {
                item["name"]: item["description"]
                for item in config_schema()["x-magic-geo"]["profiles"]
            },
        )
        for entry in profiles["profiles"]:
            with self.subTest(profile=entry["name"]):
                self.assertEqual(sorted(entry), ["description", "name"])
                self.assertIsInstance(entry["description"], str)
                self.assertNotEqual(entry["description"].strip(), "")
                self.assertNotEqual(entry["description"], entry["name"])

        status, _headers, body = asgi_call(app, "GET", "/api/config/template?profile=smoke")
        self.assertEqual(status, 200, body)
        template = json.loads(body)
        self.assertEqual(template["profile"], "smoke")
        revalidated = json.loads(
            asgi_call(
                app, "POST", "/api/config/validate", json_body={"yaml": template["yaml"]}
            )[2]
        )
        self.assertEqual(revalidated["config"], template["config"])

        status, _headers, body = asgi_call(app, "GET", "/api/config/template?profile=nope")
        self.assertEqual(status, 422, body)
        self.assertEqual(
            _detail(body)["message"],
            "unknown configuration profile 'nope'; choose one of: default, earthlike, smoke",
        )
        self.assertEqual(_detail(body)["source"], "<profile>")

        status, _headers, body = asgi_call(
            app,
            "POST",
            "/api/config/render",
            json_body={"profile": "earthlike", "overrides": {"mesh.cell_count": 512}},
        )
        self.assertEqual(status, 200, body)
        rendered = json.loads(body)
        self.assertEqual(rendered["profile"], "earthlike")
        self.assertEqual(rendered["config"]["mesh"]["cell_count"], 512)
        self.assertIn("cell_count: 512", rendered["yaml"])

        status, _headers, body = asgi_call(
            app,
            "POST",
            "/api/config/render",
            json_body={"profile": "earthlike", "overrides": {"mesh.nope": 1}},
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(
            _detail(body)["message"], "unknown configuration override 'mesh.nope'"
        )
        self.assertEqual(_detail(body)["source"], "<web overrides>")

        status, _headers, body = asgi_call(
            app, "POST", "/api/config/save", json_body={"yaml": "config_version: 2\n", "name": "bad name"}
        )
        self.assertEqual(status, 422, body)
        self.assertEqual(
            _detail(body), "name must use only letters, digits, '.', '_', and '-'"
        )

        status, _headers, body = asgi_call(
            app,
            "POST",
            "/api/config/save",
            json_body={"yaml": "run:\n  seed: 1\n  seed: 2\n", "name": "duplicate.yaml"},
        )
        self.assertEqual(status, 422, body)
        self.assertIn("duplicate key", _detail(body)["message"])
        self.assertEqual(_detail(body)["source"], "<web:duplicate.yaml>")
        self.assertFalse((root / "runs" / "configs" / "duplicate.yaml").exists())

        blocked = root / "runs" / "configs" / "blocked.yaml"
        blocked.mkdir(parents=True)
        status, _headers, body = asgi_call(
            app,
            "POST",
            "/api/config/save",
            json_body={"yaml": "config_version: 2\n", "name": "blocked.yaml", "force": True},
        )
        self.assertEqual(status, 500, body)
        self.assertRegex(_detail(body), r"^unable to save configuration: ")
        self.assertTrue(blocked.is_dir())

        with patch(
            "magic_geo.debug_server.write_config",
            side_effect=FileExistsError("configuration already exists: raced.yaml"),
        ):
            status, _headers, body = asgi_call(
                app,
                "POST",
                "/api/config/save",
                json_body={"yaml": "config_version: 2\n", "name": "raced.yaml", "force": True},
            )
        self.assertEqual(status, 409, body)
        self.assertEqual(_detail(body), "configuration already exists: raced.yaml")

    def test_config_save_rechecks_confinement_after_the_symlink_checks(self) -> None:
        root = self.temp_root()
        app = self.serve(root, None)
        outside_dir = root / "outside-configs"
        outside_dir.mkdir()
        configs = root / "runs" / "configs"
        real_mkdir = Path.mkdir

        def racing_mkdir(self_path: Path, *args: object, **kwargs: object) -> None:
            # Simulate the directory being swapped for a symlink between the
            # is_symlink() check and the mkdir() call.
            if self_path == configs and not self_path.exists():
                self_path.symlink_to(outside_dir, target_is_directory=True)
                return None
            return real_mkdir(self_path, *args, **kwargs)

        with patch.object(Path, "mkdir", racing_mkdir):
            status, _headers, body = asgi_call(
                app,
                "POST",
                "/api/config/save",
                json_body={"yaml": "config_version: 2\n", "name": "raced-directory.yaml"},
            )
        self.assertEqual(status, 422, body)
        self.assertEqual(_detail(body), "config directory escapes workspace")
        self.assertFalse((outside_dir / "raced-directory.yaml").exists())

        configs.unlink()
        configs.mkdir(parents=True)
        victim = root / "outside-config.yaml"
        (configs / "raced-file.yaml").symlink_to(victim)
        real_is_symlink = Path.is_symlink

        def lying_is_symlink(self_path: Path) -> bool:
            # Simulate the target becoming a symlink after its own check.
            if self_path.name == "raced-file.yaml":
                return False
            return real_is_symlink(self_path)

        with patch.object(Path, "is_symlink", lying_is_symlink):
            status, _headers, body = asgi_call(
                app,
                "POST",
                "/api/config/save",
                json_body={"yaml": "config_version: 2\n", "name": "raced-file.yaml", "force": True},
            )
        self.assertEqual(status, 422, body)
        self.assertEqual(_detail(body), "invalid configuration name")
        self.assertFalse(victim.exists())

    def test_backend_endpoint_reports_probe_failures(self) -> None:
        root = self.temp_root()
        app = self.serve(root, None)

        status, _headers, body = asgi_call(app, "GET", "/api/backend")
        self.assertEqual(status, 200, body)
        self.assertIn("active_backend", json.loads(body))

        with patch(
            "magic_geo.api.backend_info", side_effect=RuntimeError("probe exploded")
        ):
            status, _headers, body = asgi_call(app, "GET", "/api/backend")
        self.assertEqual(status, 503, body)
        self.assertEqual(_detail(body), "backend probe failed: probe exploded")

    def test_lifespan_shutdown_closes_the_job_manager_and_cache(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        app = self.serve(root, cache_dir)
        caches = app.state.cache_manager
        jobs = app.state.job_manager
        self.assertIsNotNone(caches.get())

        async def run_lifespan() -> None:
            async with app.router.lifespan_context(app):
                pass

        asyncio.run(run_lifespan())

        self.assertIsNone(caches._cache)
        with self.assertRaisesRegex(JobInputError, "web job manager is closed"):
            jobs.submit("validate", {"world": "runs/world.json"})

    def test_completed_job_selection_failures_leave_the_current_cache(self) -> None:
        root = self.temp_root()
        cache_dir = _make_cache(root)
        app = self.serve(root, cache_dir)
        caches = app.state.cache_manager
        on_complete = app.state.job_manager._on_complete
        live = caches.get()

        # A directory that was never exported cannot be selected, and the
        # rejection leaves the live connection untouched.
        on_complete(Mock(status="succeeded", cache_dir="runs/never-exported"))
        self.assertEqual(caches.selected_relative(), "runs/debug")
        self.assertIs(caches.get(), live)

        published = root / "runs" / "second"
        shutil.copytree(cache_dir, published)
        _mutate_manifest(
            published, lambda manifest: _assign(manifest, ("world", "name"), "second")
        )

        # A job that did not succeed never switches the selection, even when its
        # cache directory is a perfectly loadable export.
        on_complete(Mock(status="failed", cache_dir="runs/second"))
        self.assertEqual(caches.selected_relative(), "runs/debug")
        self.assertEqual(caches.get().manifest["world"]["name"], "tiny")
        on_complete(Mock(status="succeeded", cache_dir=None))
        self.assertEqual(caches.selected_relative(), "runs/debug")

        # Re-reporting the directory that is already selected reuses the live
        # connection instead of reopening the cache.
        on_complete(Mock(status="succeeded", cache_dir="runs/debug"))
        self.assertIs(caches.get(), live)

        on_complete(Mock(status="succeeded", cache_dir="runs/second"))
        self.assertEqual(caches.selected_relative(), "runs/second")
        self.assertEqual(caches.get().manifest["world"]["name"], "second")
        self.assertIsNot(caches.get(), live)
