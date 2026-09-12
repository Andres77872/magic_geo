"""Manufactured layer evidence: no native generation or retained-world replay."""
from copy import deepcopy

import pytest

from magic_geo.commodity_resources import _commodity_potential, _formation_evidence
from magic_geo.petroleum_migration import enrich_world_with_petroleum_migration
from magic_geo.sedimentary_resource_systems import enrich_world_with_sedimentary_resource_systems


QUALITY_KEYS = ("organic_potential", "reservoir_quality", "seal_quality")
OUTPUT_KEYS = ("source_rock_index", "reservoir_quality_index", "seal_quality_index", "coal_potential_index")


def layer(value, thickness=1.0):
    return {"thickness_m": thickness, "facies": "unknown", **dict.fromkeys(QUALITY_KEYS, value)}


def column(layers):
    return {
        "id": 7, "basin_id": 3, "layers": layers,
        "preservation_potential": 0.0, "mean_accommodation_to_deposition_ratio": 0.0,
    }


def source_world(source_column):
    # An evaporite deposit admits the system without requiring large fuel
    # potentials. Its only contribution to the four tested indices is seal=.1.
    return {
        "planet_parameters": {"radius_km": 6371.0},
        "cells": [{"id": 0, "basin_id": 3, "area_km2": 1.0, "neighbors": []}],
        "sedimentary_basins": [{"id": 2, "basin_id": 3, "cell_count": 1}],
        "resource_deposits": [{"id": 4, "cell_id": 0, "basin_id": 3, "resource": "evaporites"}],
        "stratigraphic_columns": [] if source_column is None else [deepcopy(source_column)],
        "summary": {},
    }


def enriched(source_column):
    world = source_world(source_column)
    enrich_world_with_sedimentary_resource_systems(world)
    assert len(world["sedimentary_resource_systems"]) == 1
    return world


def indices(source_column):
    system = enriched(source_column)["sedimentary_resource_systems"][0]
    return tuple(system[key] for key in OUTPUT_KEYS)


@pytest.mark.parametrize("index, expected", list(enumerate((0.0, 0.0, 0.1, 0.0))))
def test_explicit_zero_never_uses_missing_source_default(index, expected):
    assert indices(column([layer(0.0)]))[index] == expected


@pytest.mark.parametrize("index, expected", list(enumerate((0.00004, 0.00005, 0.100056, 0.000024))))
def test_positive_near_zero_retains_small_contribution(index, expected):
    tiny = indices(column([layer(0.0001)]))[index]
    assert tiny == expected
    assert tiny > indices(column([layer(0.0)]))[index]


@pytest.mark.parametrize("source_column", [
    None,
    {"id": 7, "basin_id": 3},
    column([]),
    column(None),
    column({}),
    column([None, "ignored"]),
    column([{"thickness_m": 1.0}]),
], ids=["absent-column", "absent-layers", "empty-layers", "null-layers", "nonlist-layers", "nondict-layers", "missing-keys"])
def test_unavailable_source_keeps_existing_defaults(source_column):
    assert indices(source_column) == (0.14, 0.14, 0.268, 0.084)


@pytest.mark.parametrize("key, expected", [
    ("organic_potential", (0.14, 0.0, 0.1, 0.084)),
    ("reservoir_quality", (0.0, 0.14, 0.1, 0.0)),
    ("seal_quality", (0.0, 0.0, 0.268, 0.0)),
])
def test_missing_property_defaults_independently_of_known_zero_properties(key, expected):
    source_layer = layer(0.0)
    del source_layer[key]
    assert indices(column([source_layer])) == expected


def test_positive_source_values_are_unchanged():
    assert indices(column([layer(0.4)])) == (0.16, 0.2, 0.324, 0.096)


@pytest.mark.parametrize("second", [layer(0.0, 3.0), {"thickness_m": 3.0}], ids=["known-zero", "missing-properties"])
def test_partial_source_keeps_existing_thickness_denominator(second):
    # Missing properties retain their old zero contribution and layer weight;
    # they are neither imputed defaults nor removed from the denominator.
    assert indices(column([layer(0.8), second])) == (0.08, 0.1, 0.212, 0.048)


def test_known_zero_among_missing_properties_stays_zero():
    assert indices(column([layer(0.0), {"thickness_m": 3.0}])) == (0.0, 0.0, 0.1, 0.0)


def test_malformed_present_property_is_not_silently_reclassified_as_missing():
    source_layer = layer(0.0)
    source_layer["organic_potential"] = None
    with pytest.raises(TypeError):
        enriched(column([source_layer]))


def test_petroleum_consumer_uses_corrected_source_and_potential():
    world = enriched(column([layer(0.0)]))
    system = world["sedimentary_resource_systems"][0]
    assert system["petroleum_potential_index"] == 0.026
    assert system["gas_potential_index"] == 0.0312
    enrich_world_with_petroleum_migration(world)
    # No lithology/landform/fuel bonuses: source is petroleum*.08 here.
    assert world["cells"][0]["petroleum_source_rock_index"] == 0.00208


def test_commodity_evidence_and_fuel_potentials_use_corrected_parent():
    world = enriched(column([layer(0.0)]))
    system = world["sedimentary_resource_systems"][0]
    cell, deposit = world["cells"][0], world["resource_deposits"][0]
    evidence = _formation_evidence(deposit, cell, system)
    assert evidence["sedimentary_resource_system_id"] == system["id"]
    assert evidence["petroleum_potential_index"] == 0.026
    assert evidence["gas_potential_index"] == 0.0312
    assert evidence["coal_potential_index"] == 0.0
    assert _commodity_potential("petroleum", deposit, cell, system) == pytest.approx(0.01404)
    assert _commodity_potential("coal", deposit, cell, system) == 0.0
