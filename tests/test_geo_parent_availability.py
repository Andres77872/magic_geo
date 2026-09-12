"""Public geo integration of historical E4 child contracts; no native generation."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from magic_geo.api import _enrich_ecosystems_and_resources
from magic_geo.aquatic_climate_validation import _EXPECTED_MODELS
from magic_geo.geo_layer_contracts import evaluate_geo_layer_contracts
from magic_geo.geo_evolution_provenance import enrich_world_with_geo_evolution_provenance
from magic_geo.geo_validation import validate_geo_world
from magic_geo.geo_validation_subsystems import _validate_ecosystems, _validate_resources


def consumer_world(temperature=18.0):
    # Explicit downstream-stage inputs. This is not a certified physical world.
    world = {"generation_scope": "geo_only", "planet_parameters": {"radius_km": 6371.0}, "summary": {}, "cells": [{
        "id": 0, "area_km2": 1.0, "neighbors": [], "lat_deg": 0.0, "lon_deg": 0.0,
        "temperature_c": temperature, "precipitation_mm_y": 900.0,
        "is_water": True, "is_lake": False, "water_body_type": "continental_shelf",
        "resource": "coastal_fisheries", "biome": "shallow_marine",
        "flow_accumulation": 1.0, "runoff_mm_y": 0.0,
    }]}
    world['ecosystem_dynamics_model'] = deepcopy(_EXPECTED_MODELS['heuristic_ecosystem_climate_support_v4'])
    _enrich_ecosystems_and_resources(world)
    return world


def checks_for(world, function):
    checks = []
    cells = world["cells"]
    function(checks, world, cells, {c["id"]: c for c in cells}, world["summary"])
    return {check["name"]: check for check in checks}


@pytest.mark.parametrize("temperature,record_count", [(18.0, 1), (80.0, 0), (-60.0, 0)])
def test_public_geo_resource_checks_accept_only_supported_biological_coverage(temperature, record_count):
    world = consumer_world(temperature)
    assert len(world["resource_deposits"]) == record_count
    assert len(world["commodity_occurrences"]) == record_count
    checks = checks_for(world, _validate_resources)
    for name in ("resource_deposit_sources_and_ranges", "commodity_occurrence_deposit_links"):
        assert checks[name]["passed"], checks[name]


@pytest.mark.parametrize("mutation", [
    lambda w: w["cells"][0].update(fishery_resource_proxy_supported=False),
    lambda w: w["resource_deposits"].clear(),
    lambda w: w["resource_deposit_model"].update(model_type="unknown"),
])
def test_geo_resource_validation_rejects_forged_availability_or_missing_sources(mutation):
    world = consumer_world()
    assert checks_for(world, _validate_resources)["resource_deposit_sources_and_ranges"]["passed"]
    mutation(world)
    check = checks_for(world, _validate_resources)["resource_deposit_sources_and_ranges"]
    assert not check["passed"] and check["observed"]["errors"]


@pytest.mark.parametrize("mutation", [
    lambda w: w.pop("commodity_occurrence_model"),
    lambda w: w["commodity_occurrences"].clear(),
    lambda w: w["cells"][0].update(fishery_commodity_supported=False),
])
def test_geo_commodity_validation_requires_its_declared_supported_chain(mutation):
    world = consumer_world()
    assert checks_for(world, _validate_resources)["commodity_occurrence_deposit_links"]["passed"]
    mutation(world)
    check = checks_for(world, _validate_resources)["commodity_occurrence_deposit_links"]
    assert not check["passed"] and check["observed"]["errors"]


def test_complete_v4_output_cannot_hide_species_version_by_deleting_new_fields():
    world = consumer_world()
    key = "species_range_inverse_links_and_envelopes"
    assert checks_for(world, _validate_ecosystems)[key]["passed"]
    world.pop("species_ranges_model")
    for cell in world["cells"]:
        for field in list(cell):
            if field.startswith("species_"):
                del cell[field]
        cell["species_range_record_ids"] = []
    result = checks_for(world, _validate_ecosystems)[key]
    assert not result["passed"]
    assert "ecosystem v4 requires" in " ".join(result["observed"]["errors"])


@pytest.mark.parametrize("field,layer", [
    ("species_ranges_model", "biomes_ecosystems"),
    ("wildfire_disturbance_model", "biomes_ecosystems"),
    ("commodity_occurrence_model", "natural_resources"),
])
def test_layer_contract_lists_missing_new_consumer_declarations(field, layer):
    world = consumer_world()
    del world[field]
    result = evaluate_geo_layer_contracts(world, [])
    item = next(item for item in result["layers"] if item["id"] == layer)
    assert field in item["missing_or_invalid_outputs"]


def test_explicit_historical_material_and_fishery_resource_records_remain_valid():
    path = Path(__file__).parent / "data/biological_resource_legacy_outputs.json"
    world = deepcopy(json.loads(path.read_text())["output"])
    checks = checks_for(world, _validate_resources)
    for name in ("resource_deposit_sources_and_ranges", "commodity_occurrence_deposit_links"):
        assert checks[name]["passed"], checks[name]


@pytest.fixture(scope="module")
def complete_resource_worlds():
    # Share the original complete CLI fixtures. These tests inspect natural
    # resource checks inside the public geo report; they do not claim that a
    # full-world archive is a geo-only output or a physically calibrated world.
    root = Path(__file__).parent / "fixtures/cli_ecology_parent_availability"
    manifest = json.loads((root / "manifest.json").read_text())
    worlds = {}
    for label in ("warm", "cold"):
        entry = manifest[label]
        compressed = (root / entry["fixture"]).read_bytes()
        assert hashlib.sha256(compressed).hexdigest() == entry["fixture_gzip_sha256"]
        raw = gzip.decompress(compressed)
        assert hashlib.sha256(raw).hexdigest() == entry["world_sha256"]
        original = json.loads(raw)
        current = deepcopy(original)
        _enrich_ecosystems_and_resources(current)
        enrich_world_with_geo_evolution_provenance(current)
        worlds[label] = {"historical": original, "current": current}
    return worlds


def public_check(world, name):
    report = validate_geo_world(world)
    assert not any(c["name"] == "malformed_optional_payload" for c in report["checks"]), report
    return next(c for c in report["checks"] if c["name"] == name)


@pytest.mark.parametrize("label", ["warm", "cold"])
@pytest.mark.parametrize("version", ["historical", "current"])
def test_public_geo_resource_report_accepts_both_explicit_version_chains(complete_resource_worlds, label, version):
    check = public_check(complete_resource_worlds[label][version], "deposit_and_commodity_linkage")
    assert check["status"] == "passed", check


@pytest.mark.parametrize("field", ["resource_deposit_model", "commodity_occurrence_model"])
def test_public_geo_report_rejects_missing_biological_consumer_declaration(complete_resource_worlds, field):
    world = deepcopy(complete_resource_worlds["warm"]["current"])
    world.pop(field)
    check = public_check(world, "deposit_and_commodity_linkage")
    assert check["status"] == "failed", check
    assert check["evidence"]["biological_resource_errors"]


@pytest.mark.parametrize("field", ["fishery_resource_proxy_supported", "fishery_commodity_supported"])
def test_public_geo_report_rejects_forged_biological_support(complete_resource_worlds, field):
    world = deepcopy(complete_resource_worlds["warm"]["current"])
    cell = next(c for c in world["cells"] if c[field])
    cell[field] = False
    check = public_check(world, "deposit_and_commodity_linkage")
    assert check["status"] == "failed", check
    assert check["evidence"]["biological_resource_errors"]
