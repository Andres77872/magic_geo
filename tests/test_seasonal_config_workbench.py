"""Current seasonal YAML through workbench HTTP and job contracts."""

import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("pyarrow")
pytest.importorskip("duckdb")

from magic_geo.config import WorldConfig, load_config, parse_config_yaml
from magic_geo.debug_server import create_app
from test_debug_server import asgi_call, _wait_for_job


SEASONAL_YAML = """config_version: 2
run:
  name: seasonal_workbench
  seed: 3015
mesh:
  cell_count: 128
tectonics:
  plate_count: 8
climate:
  reference_infrared_optical_depth: 0.73
  precipitation_scale: 0.81
erosion:
  iterations: 0
output:
  float_precision: 8
"""


@pytest.fixture
def workbench(tmp_path):
    app = create_app(None, project_root=tmp_path, workspace=Path("runs"))
    try:
        yield app, tmp_path
    finally:
        app.state.job_manager.close()
        app.state.cache_manager.close()


def request(app, method, path, payload=None):
    status, _headers, body = asgi_call(app, method, path, json_body=payload)
    return status, json.loads(body)


def test_validate_normalizes_explicit_v2_without_reintroducing_legacy_temperature_controls(workbench):
    app, root = workbench
    status, result = request(app, "POST", "/api/config/validate", {"yaml": SEASONAL_YAML})
    assert status == 200, result
    assert result["valid"] is True
    parsed = parse_config_yaml(result["yaml"])
    assert type(parsed) is WorldConfig
    assert parsed == parse_config_yaml(SEASONAL_YAML)
    assert result["config"] == parsed.model_dump(mode="json")
    assert result["config"]["config_version"] == 2
    assert type(result["config"]["config_version"]) is int
    assert result["config"]["climate"]["reference_infrared_optical_depth"] == 0.73
    assert "base_temperature_c" not in result["config"]["climate"]
    assert "lapse_rate_c_per_km" not in result["config"]["climate"]
    assert not (root / "runs/configs").exists()


@pytest.mark.parametrize("endpoint", ["validate", "save"])
@pytest.mark.parametrize("version", ["null", "true", "false", '"2"', "2.0", "1", "3"])
def test_strict_version_error_propagates_field_path_and_http422(workbench, endpoint, version):
    app, root = workbench
    payload = {"yaml": f"config_version: {version}\n"}
    if endpoint == "save":
        payload["name"] = "invalid-version.yaml"
    status, result = request(app, "POST", f"/api/config/{endpoint}", payload)
    assert status == 422, result
    detail = result["detail"]
    assert detail["issues"][0]["path"] == "config_version"
    assert detail["source"] == ("<web editor>" if endpoint == "validate" else "<web:invalid-version.yaml>")
    assert not (root / "runs/configs/invalid-version.yaml").exists()


@pytest.mark.parametrize("endpoint", ["validate", "save"])
def test_both_obsolete_temperature_controls_keep_actionable_individual_http_paths(workbench, endpoint):
    app, root = workbench
    text = "config_version: 2\nclimate:\n  base_temperature_c: 15\n  lapse_rate_c_per_km: 6.5\n"
    payload = {"yaml": text}
    if endpoint == "save":
        payload["name"] = "obsolete.yaml"
    status, result = request(app, "POST", f"/api/config/{endpoint}", payload)
    assert status == 422, result
    issues = result["detail"]["issues"]
    assert {issue["path"] for issue in issues} == {"climate.base_temperature_c", "climate.lapse_rate_c_per_km"}
    assert all("no equivalent conversion" in issue["message"] for issue in issues)
    assert all("reference_infrared_optical_depth" in issue["message"] for issue in issues)
    assert not (root / "runs/configs/obsolete.yaml").exists()


@pytest.mark.parametrize("text,path", [
    ('climate:\n  reference_infrared_optical_depth: "0.73"\n', "climate.reference_infrared_optical_depth"),
    ("climate:\n  reference_infrared_optical_depth: true\n", "climate.reference_infrared_optical_depth"),
    ("climate:\n  reference_infrared_optical_depth: .inf\n", "climate.reference_infrared_optical_depth"),
    ("climate:\n  reference_infrared_optical_depth: -0.1\n", "climate.reference_infrared_optical_depth"),
    ("mesh:\n  cell_count: 128.0\n", "mesh.cell_count"),
    ("output:\n  include_cells: 1\n", "output.include_cells"),
])
def test_seasonal_nested_strict_types_and_ranges_remain_http422(workbench, text, path):
    app, _root = workbench
    status, result = request(app, "POST", "/api/config/validate", {"yaml": "config_version: 2\n" + text})
    assert status == 422, result
    assert result["detail"]["issues"][0]["path"] == path


def test_save_roundtrip_conflict_and_failed_overwrite_preserve_version_and_optical_depth(workbench):
    app, root = workbench
    status, saved = request(app, "POST", "/api/config/save", {"yaml": SEASONAL_YAML, "name": "seasonal-world"})
    assert status == 200, saved
    assert saved["saved"] is True
    assert saved["path"] == "runs/configs/seasonal-world.yaml"
    path = root / saved["path"]
    assert path.read_text() == saved["yaml"]
    config = load_config(path)
    assert type(config) is WorldConfig
    assert config.config_version == 2
    assert config.climate.reference_infrared_optical_depth == 0.73
    original = path.read_bytes()
    status, _result = request(app, "POST", "/api/config/save", {"yaml": SEASONAL_YAML, "name": path.name})
    assert status == 409
    assert path.read_bytes() == original
    invalid = "config_version: 2\nclimate:\n  base_temperature_c: 15\n"
    status, result = request(app, "POST", "/api/config/save", {"yaml": invalid, "name": path.name, "force": True})
    assert status == 422, result
    assert result["detail"]["issues"][0]["path"] == "climate.base_temperature_c"
    assert path.read_bytes() == original
    changed = SEASONAL_YAML.replace("0.73", "1.4")
    status, result = request(app, "POST", "/api/config/save", {"yaml": changed, "name": path.name, "force": True})
    assert status == 200, result
    assert load_config(path).config_version == 2
    assert load_config(path).climate.reference_infrared_optical_depth == 1.4


@pytest.mark.parametrize("geo_only", [False, True])
def test_generation_job_passes_exact_saved_v2_file_to_existing_cli(workbench, monkeypatch, geo_only):
    app, root = workbench
    status, saved = request(app, "POST", "/api/config/save", {"yaml": SEASONAL_YAML, "name": "seasonal-job.yaml"})
    assert status == 200, saved
    config_path = root / saved["path"]
    original = config_path.read_bytes()
    commands = []

    def capture_cli(_job, command):
        commands.append(list(command))
        assert command[1:4] == ["-m", "magic_geo", "generate"]
        supplied = Path(command[command.index("--config") + 1])
        assert supplied == config_path.resolve()
        assert supplied.read_bytes() == original
        parsed = load_config(supplied)
        assert type(parsed) is WorldConfig
        assert parsed.config_version == 2
        assert parsed.climate.reference_infrared_optical_depth == 0.73
        # No native generation is performed: this verifies the subprocess
        # input boundary and lets the existing artifact lifecycle complete.
        output = Path(command[command.index("--output") + 1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text('{"test_stub": true}\n')
        return 0

    monkeypatch.setattr(app.state.job_manager, "_spawn", capture_cli)
    status, submitted = request(app, "POST", "/api/jobs", {
        "operation": "generate",
        "arguments": {"config": saved["path"], "output": "runs/seasonal-world.json",
                      "geo_only": geo_only, "open_in_web": False, "world_format": "json"},
    })
    assert status == 202, submitted
    job = _wait_for_job(app.state.job_manager, submitted["id"])
    assert job["status"] == "succeeded", job
    assert len(commands) == 1
    assert ("--geo-only" in commands[0]) is geo_only
    assert commands[0][commands[0].index("--format") + 1] == "json"
    assert config_path.read_bytes() == original


def test_profile_render_and_schema_select_current_seasonal_model(workbench):
    app, _root = workbench
    status, schema = request(app, "GET", "/api/config/schema")
    assert status == 200
    assert schema["properties"]["config_version"]["const"] == 2
    assert "config_version" in schema["required"]
    status, template = request(app, "GET", "/api/config/template?profile=smoke")
    assert status == 200
    assert type(parse_config_yaml(template["yaml"])) is WorldConfig
    assert template["config"]["config_version"] == 2
    assert "base_temperature_c" not in template["config"]["climate"]
    status, rendered = request(app, "POST", "/api/config/render", {
        "profile": "smoke", "overrides": {"climate.reference_infrared_optical_depth": 0.73},
    })
    assert status == 200, rendered
    assert type(parse_config_yaml(rendered["yaml"])) is WorldConfig
    assert rendered["config"]["config_version"] == 2
    assert rendered["config"]["climate"]["reference_infrared_optical_depth"] == 0.73


@pytest.mark.parametrize("payload,expected", [
    ({"yaml": SEASONAL_YAML}, "yaml"),
    ({"config_version": 2}, "config_version"),
    ({"profile": "smoke", "overrides": {"config_version": 1}}, "config_version"),
    ({"profile": "smoke", "overrides": {"climate.base_temperature_c": 15}}, "base_temperature_c"),
])
def test_renderer_refuses_invalid_protocol_and_obsolete_configuration_controls(workbench, payload, expected):
    app, _root = workbench
    status, result = request(app, "POST", "/api/config/render", payload)
    assert status == 422, result
    assert expected in json.dumps(result["detail"])
