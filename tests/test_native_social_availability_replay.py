"""Independent new social replay on actual native stage/serializer unit outputs."""
from copy import deepcopy

import pytest

from support.native_social_worlds import annotated_environment_social_world, native_social_unit_world
from magic_geo.civilization_geography_validation import validate_civilization_geography_replay
from magic_geo.territorial_geography_validation import validate_territorial_geography_replay
from magic_geo.native_civilization_availability_validation import population_records_v2, _population_matches_v2
from magic_geo.native_territorial_availability_validation import snapshot_records_v2, _matches
from magic_geo.native_social_availability import require_native_social_availability

VALIDATORS = (validate_civilization_geography_replay, validate_territorial_geography_replay)


@pytest.fixture(scope="module", params=["healthy","mixed"])
def source(request):
    return annotated_environment_social_world(request.param)


@pytest.mark.parametrize("validate", VALIDATORS)
def test_environment_derived_sources_replay_without_mutation(source,validate):
    world=deepcopy(source);before=deepcopy(world)
    assert validate(world)==[]
    assert world==before


@pytest.mark.parametrize("name",["healthy","mixed","lake","noarea","unassigned","empty_candidate_culture","selection_stage_healthy","selection_stage_mixed"])
def test_scoped_social_stage_population_and_base_geometry_equations(name):
    # These eight cases have prescribed scores or assignments; this test
    # intentionally checks only the scoped social and geometry equations.
    world=native_social_unit_world(name)
    populations=population_records_v2(world)
    assert all(_population_matches_v2(a,e,8) for a,e in zip(world["population_regions"],populations,strict=True))
    snapshots=snapshot_records_v2(world)
    assert all(_matches(a,e) for a,e in zip(world["territorial_snapshots"],snapshots,strict=True))


def test_lake_area_stays_in_original_denominator_and_unassigned_input_is_local():
    lake=native_social_unit_world("lake")["population_regions"][0]
    assert lake["territory_area_km2"]==300
    assert lake["structural_zero_site_area_km2"]==100
    assert lake["site_input_complete"] is True
    assert lake["site_strength_index"]==pytest.approx(1/3,abs=1e-8)
    unassigned=native_social_unit_world("unassigned")["population_regions"][0]
    assert unassigned["territory_area_km2"]==200
    assert unassigned["population_estimate_available"] is True
    absent=native_social_unit_world("noarea")["population_regions"][0]
    assert absent["site_input_complete"] is True
    assert absent["capacity_estimate_available"] is False
    assert absent["carrying_capacity"] is None


@pytest.mark.parametrize("mutate",[
    lambda w:w["population_regions"][0].update(site_input_complete=not w["population_regions"][0]["site_input_complete"]),
    lambda w:w["population_regions"][0].update(site_input_supported_cell_count=999),
    lambda w:w["population_regions"][0].update(territory_area_km2=1),
    lambda w:w["population_regions"][0].update(estimated_population=0.0 if w["population_regions"][0]["estimated_population"] is None else None),
    lambda w:w["population_regions"][0].update(water_security_index=.999),
    lambda w:w["population_regions"][0].update(population_estimate_available=1),
    lambda w:w["native_social_availability"].update(conflict_candidate_pair_count=999),
    lambda w:w["native_social_availability"].update(conflict_inference_available=not w["native_social_availability"]["conflict_inference_available"]),
    lambda w:w["native_social_availability"].update(dynasty_available_region_count=999),
    lambda w:w["population_region_model"].update(extra=True),
    lambda w:w["population_region_model"].update(source_settlement_model="old"),
    lambda w:w["summary"].update(estimated_world_population=0.0 if w["summary"]["estimated_world_population"] is None else None),
    lambda w:w["summary"]["native_social_summary_availability"].update(mean_population_pressure=1),
])
def test_population_conflict_dynasty_tampering_is_rejected(source,mutate):
    world=deepcopy(source);mutate(world)
    assert validate_civilization_geography_replay(world)


@pytest.mark.parametrize("mutate",[
    lambda w:w["territorial_snapshots"][0]["regions"][0].update(base_area_km2=1),
    lambda w:w["territorial_snapshots"][0]["regions"][0].update(base_boundary_perimeter_km=1),
    lambda w:w["territorial_snapshots"][0]["regions"][0].update(geometry_estimate_available=1),
    lambda w:w["territorial_snapshots"][0]["regions"][0].update(area_km2=0.0 if w["territorial_snapshots"][0]["regions"][0]["area_km2"] is None else None),
    lambda w:w["territorial_snapshots"][0]["regions"][0].update(estimated_population=0.0 if w["territorial_snapshots"][0]["regions"][0]["estimated_population"] is None else None),
    lambda w:w["territorial_snapshots"][0]["regions"].pop(),
    lambda w:w["territorial_snapshots"].reverse(),
    lambda w:w["territorial_snapshot_model"].update(geometry_radius_source="inferred_area"),
    lambda w:w["planet_parameters"].update(radius_km=1.0),
    lambda w:w["native_social_availability"].update(territorial_snapshot_inference_available=not w["native_social_availability"]["territorial_snapshot_inference_available"]),
    lambda w:w["summary"].update(mean_snapshot_fragmentation_index=0.0 if w["summary"]["mean_snapshot_fragmentation_index"] is None else None),
])
def test_snapshot_tampering_is_rejected(source,mutate):
    world=deepcopy(source);mutate(world)
    assert validate_territorial_geography_replay(world)


def test_empty_local_ruin_domain_is_known_zero_under_incomplete_global_ranking():
    world=native_social_unit_world("empty_candidate_culture")
    assert world["native_social_availability"]["ruin_inference_available"] is False
    empty=[c for c in world["cultures"] if c["ruin_candidate_cell_count"]==0]
    assert empty
    assert all(c["ruin_count_available"] and c["ruin_count"]==0 and c["continuity_estimate_available"] for c in empty)
