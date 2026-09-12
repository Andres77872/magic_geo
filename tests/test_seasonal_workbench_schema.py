"""The public workbench schema, profile list and templates agree on version 2."""
import json
from pathlib import Path

import pytest

pytest.importorskip("duckdb")

from magic_geo.config import parse_config_yaml
from magic_geo.debug_server import create_app
from test_debug_server import asgi_call


def test_public_schema_profiles_and_templates_match_the_current_ui_contract(tmp_path):
    app = create_app(None, project_root=tmp_path, workspace=Path("runs"))

    def get(path):
        status, _headers, body = asgi_call(app, "GET", path)
        assert status == 200, body
        return json.loads(body)

    try:
        schema = get("/api/config/schema")
        profiles = get("/api/config/profiles")
        metadata = schema["x-magic-geo"]
        assert schema["$id"].endswith(":v2")
        assert metadata["schema_version"] == 2
        assert schema["properties"]["config_version"]["const"] == 2
        declared = {profile["name"]: profile for profile in metadata["profiles"]}
        assert set(declared) == {profile["name"] for profile in profiles["profiles"]}
        assert profiles["default"] in declared
        climate_ref = schema["properties"]["climate"]["$ref"].split("/")[-1]
        climate_fields = schema["$defs"][climate_ref]["properties"]
        assert climate_fields["reference_infrared_optical_depth"]["minimum"] == 0.0
        assert "base_temperature_c" not in climate_fields
        assert "lapse_rate_c_per_km" not in climate_fields
        for name, declaration in declared.items():
            template = get(f"/api/config/template?profile={name}")
            assert template["profile"] == name
            assert type(template["config"]["config_version"]) is int
            assert template["config"]["config_version"] == 2
            assert declaration["values"] == template["config"]
            assert parse_config_yaml(template["yaml"]).model_dump(mode="json") == template["config"]
            assert "base_temperature_c" not in template["config"]["climate"]
            assert "lapse_rate_c_per_km" not in template["config"]["climate"]
        assert not (tmp_path / "runs/configs").exists()
    finally:
        app.state.job_manager.close()
        app.state.cache_manager.close()
