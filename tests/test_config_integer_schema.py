"""Integer schema text must survive browsers without changing validation data."""

from copy import deepcopy
import json
from pathlib import Path

import pytest

from magic_geo.config import _add_exact_integer_schema_display, config_schema, parse_config_yaml


def test_current_seed_schema_keeps_numeric_uint64_bound_and_exact_display_text():
    schema = json.loads(json.dumps(config_schema()))
    run = schema["$defs"][schema["properties"]["run"]["$ref"].rsplit("/", 1)[-1]]
    seed = run["properties"]["seed"]
    assert type(seed["maximum"]) is int
    assert seed["maximum"] == 18446744073709551615
    assert seed["x-magic-geo-integer-display"] == {"maximum": "18446744073709551615"}


@pytest.mark.parametrize("value", [18446744073709551615, -18446744073709551615, 2**53])
def test_unsafe_integer_display_is_generic_and_preserves_original_keywords(value):
    keys = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "default", "const")
    node = {"type": "integer", **dict.fromkeys(keys, value)}
    before = deepcopy(node)
    _add_exact_integer_schema_display(node)
    assert node.pop("x-magic-geo-integer-display") == dict.fromkeys(keys, str(value))
    assert node == before


def test_schema_display_traverses_schema_nodes_without_mutating_literal_defaults():
    literal = {"minimum": 2**64, "properties": {"value": {"default": 2**64}}}
    node = {
        "type": "object", "default": deepcopy(literal), "const": deepcopy(literal),
        "properties": {"safe": {"default": 2**53 - 1}, "boolean": {"const": True},
                       "floating": {"maximum": 1e30}},
        "$defs": {"Nested": {"anyOf": [{"items": {"exclusiveMinimum": -2**64}}, {"type": "null"}]}},
    }
    _add_exact_integer_schema_display(node)
    assert node["default"] == node["const"] == literal
    assert all("x-magic-geo-integer-display" not in child for child in node["properties"].values())
    nested = node["$defs"]["Nested"]["anyOf"][0]["items"]
    assert nested["x-magic-geo-integer-display"] == {"exclusiveMinimum": "-18446744073709551616"}


def test_web_validate_and_save_keep_typed_uint64_seed_exact(tmp_path):
    pytest.importorskip("duckdb")
    from magic_geo.debug_server import create_app
    from test_debug_server import asgi_call

    yaml = "config_version: 2\nrun:\n  seed: 18446744073709551615 # keep my editor text\n"
    app = create_app(None, project_root=tmp_path, workspace=Path("runs"))
    try:
        status, _headers, body = asgi_call(app, "POST", "/api/config/validate", json_body={"yaml": yaml})
        assert status == 200, body
        validated = json.loads(body)
        assert validated["config"]["run"]["seed"] == 2**64 - 1
        assert "seed: 18446744073709551615\n" in validated["yaml"]
        status, _headers, body = asgi_call(app, "POST", "/api/config/save", json_body={"yaml": yaml, "name": "max-seed.yaml"})
        assert status == 200, body
        saved = json.loads(body)
        stored = (tmp_path / saved["path"]).read_text()
        assert stored == saved["yaml"]
        assert "seed: 18446744073709551615\n" in stored
        assert parse_config_yaml(stored).run.seed == 2**64 - 1
        status, _headers, body = asgi_call(app, "POST", "/api/config/validate", json_body={"yaml": yaml.replace("18446744073709551615", "18446744073709551616")})
        assert status == 422, body
    finally:
        app.state.job_manager.close()
        app.state.cache_manager.close()
