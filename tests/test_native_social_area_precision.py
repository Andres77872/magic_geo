"""Actual low-precision publication plus isolated decimal-bridge controls."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from magic_geo.native_social_availability import native_area_matches, require_native_social_availability
from magic_geo.cultural_geography import enrich_world_with_cultural_geography_models
from magic_geo.historical_geography import enrich_world_with_historical_geography_model
from magic_geo.civilization_geography import enrich_world_with_civilization_geography_models
from magic_geo.territorial_geography import enrich_world_with_territorial_geography_model
from magic_geo.native_social_public_validation import validate_public_native_social

ROOT = Path(__file__).parent / "fixtures/native_social_area_precision"
AREAS = ("territory_area_km2", "site_input_applicable_area_km2", "site_input_supported_area_km2", "structural_zero_site_area_km2")


@pytest.fixture
def source():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    packed = (ROOT / manifest["fixture"]).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == manifest["gzip_sha256"]
    raw = gzip.decompress(packed)
    assert hashlib.sha256(raw).hexdigest() == manifest["sha256"]
    assert hashlib.sha256((ROOT / manifest["source_config"]).read_bytes()).hexdigest() == manifest["source_config_sha256"]
    return json.loads(raw)


def test_actual_p4_source_and_all_native_social_public_replays(source):
    assert source["summary"]["output_float_precision"] == 4
    population = source["population_regions"][0]
    assert population["site_input_supported_cell_count"] == 53
    assert population["site_input_applicable_cell_count"] == 56
    assert population["structural_zero_site_cell_count"] == 2
    assert population["structural_zero_site_area_km2"] == 8143098.8281
    before = deepcopy(source)
    require_native_social_availability(source)
    assert source == before
    for annotate in (
        enrich_world_with_cultural_geography_models,
        enrich_world_with_historical_geography_model,
        enrich_world_with_civilization_geography_models,
        enrich_world_with_territorial_geography_model,
    ):
        annotate(source)
    assert validate_public_native_social(source) == (True, [])
    assert source["population_regions"] == before["population_regions"]


@pytest.mark.parametrize("field", AREAS)
def test_one_extra_published_decimal_unit_is_rejected_atomically(source, field):
    row = source["population_regions"][0]
    row[field] = round(row[field] + .0001, 4)
    before = deepcopy(source)
    with pytest.raises(ValueError, match="area coverage"):
        enrich_world_with_cultural_geography_models(source)
    assert source == before


@pytest.mark.parametrize("precision", range(9))
def test_decimal_bridge_accepts_actual_formatter_rounding_and_rejects_next_unit(precision):
    # A serialization-only scalar control, not a fabricated world/metadata
    # declaration. The unchanged C++ formatter publishes fixed decimal places.
    value = 12.3141592637
    published = float(format(value, f".{precision}f"))
    assert native_area_matches(published, value, 1, precision)
    assert not native_area_matches(round(published + 10.0**-precision, precision), value, 1, precision)


@pytest.mark.parametrize("terms", [0, 5])
def test_known_zero_area_stays_exact_at_coarse_precision(terms):
    assert native_area_matches(0, 0, terms, 0)
    assert not native_area_matches(.1, 0, terms, 0)


@pytest.mark.parametrize("actual", [-1., True, float("inf"), float("nan")])
def test_invalid_area_cannot_gain_a_rounding_allowance(actual):
    if type(actual) is float and actual < 0:
        assert not native_area_matches(actual, 0, 0, 4)
    else:
        with pytest.raises(ValueError):
            native_area_matches(actual, 1, 1, 4)


def test_noncanonical_decimal_and_unbounded_source_are_rejected():
    assert not native_area_matches(1.00001, 1.00001, 1, 4)
    with pytest.raises(ValueError):
        native_area_matches(1, float("inf"), 1, 4)
    with pytest.raises(ValueError):
        native_area_matches(1, 1, 2**53, 4)
