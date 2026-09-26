"""Stable workbench assets revalidate; scientific responses keep their policy."""

import json
from pathlib import Path

import pytest

pytest.importorskip("duckdb")

from magic_geo.debug_server import _WorkbenchStaticFiles, create_app
from test_debug_server import _make_cache, asgi_call


def conditional_get(app, path, etag):
    async def with_header(scope, receive, send):
        await app({**scope, "headers": [*scope["headers"], (b"if-none-match", etag.encode("ascii"))]}, receive, send)

    return asgi_call(with_header, "GET", path)


@pytest.fixture
def workbench(tmp_path):
    app = create_app(_make_cache(tmp_path), project_root=tmp_path, workspace=Path("runs"))
    try:
        yield app
    finally:
        app.state.job_manager.close()
        app.state.cache_manager.close()


@pytest.mark.parametrize("path", [
    "/", "/index.html", "/app.js", "/style.css", "/layer_docs.js",
    "/config-workbench.js", "/operations-workbench.js",
    "/home-workbench.js", "/command-palette.js", "/new-world.js", "/ui.js", "/palettes.js",
    "/colormaps.js", "/map-navigation.js",
    "/landing.html", "/landing.css", "/assets/workbench-map.webp",
    "/vendor/OrbitControls.js", "/vendor/three.module.js", "/vendor/three.core.js",
])
def test_workbench_assets_keep_revalidation_headers_on_200_and_304(workbench, path):
    status, headers, body = asgi_call(workbench, "GET", path)
    assert status == 200 and body
    assert headers["cache-control"] == "no-cache"
    assert headers["etag"] and headers["last-modified"]
    status, conditional_headers, body = conditional_get(workbench, path, headers["etag"])
    assert status == 304 and body == b""
    assert conditional_headers["cache-control"] == "no-cache"
    assert conditional_headers["etag"] == headers["etag"]


def test_changed_static_asset_replaces_cached_version(tmp_path):
    script = tmp_path / "app.js"
    script.write_text("old_script();\n")
    static = _WorkbenchStaticFiles(directory=tmp_path)
    status, headers, body = asgi_call(static, "GET", "/app.js")
    assert status == 200 and body == script.read_bytes()
    script.write_text("updated_script_with_new_contract();\n")
    status, changed_headers, body = conditional_get(static, "/app.js", headers["etag"])
    assert status == 200 and body == script.read_bytes()
    assert changed_headers["etag"] != headers["etag"]
    assert changed_headers["cache-control"] == "no-cache"


def test_api_and_scientific_binary_routes_keep_existing_response_policy(workbench):
    status, headers, body = conditional_get(workbench, "/api/config/schema", '"old-static-etag"')
    assert status == 200 and json.loads(body)["x-magic-geo"]["schema_version"] == 2
    assert "cache-control" not in headers
    for path in ("/mesh/positions.f32", "/api/layer/cells/elevation_m", "/api/layer/cells/elevation_m?format=arrow"):
        status, headers, body = conditional_get(workbench, path, '"old-static-etag"')
        assert status == 200 and body
        assert headers["cache-control"] == "no-store"
