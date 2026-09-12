"""Read-only v2 replay: actual public unit positives plus scoped native stage math.

No native build, generator, climate integration, or validator mock is used.
"""
from copy import deepcopy
import ast
import gzip
import hashlib
import json
from pathlib import Path

import pytest
from support.native_social_worlds import annotated_environment_social_world, native_social_unit_world
from magic_geo.cultural_geography_validation import validate_cultural_geography_replay
from magic_geo.historical_geography_validation import validate_historical_geography_replay
from magic_geo.native_cultural_availability_validation import cultural_equations_valid
from magic_geo.native_historical_availability_validation import historical_equations_valid

VALIDATORS = (validate_cultural_geography_replay, validate_historical_geography_replay)
NAMES = ("healthy", "mixed", "lake", "noarea", "unassigned", "empty_candidate_culture",
         "selection_stage_healthy", "selection_stage_mixed", "environment_stage_healthy", "environment_stage_mixed")

@pytest.fixture(scope="module", params=["healthy", "mixed"])
def source(request):
    return annotated_environment_social_world(request.param)

@pytest.mark.parametrize("validate", VALIDATORS)
def test_real_header_environment_public_units_pass_without_mutation(source, validate):
    before = deepcopy(source)
    assert validate(source) == []
    assert source == before

@pytest.mark.parametrize("name", NAMES)
def test_actual_native_stage_equations_under_explicit_supplied_inputs(name):
    world = native_social_unit_world(name)
    before = deepcopy(world)
    # This is only equation/coverage agreement for the supplied native stage
    # inputs. Public entry points separately require the real complete header.
    assert cultural_equations_valid(world)
    assert historical_equations_valid(world)
    assert world == before

@pytest.mark.parametrize("validate", VALIDATORS)
def test_scoped_fixture_is_not_silently_promoted_to_public_world(validate):
    assert validate(native_social_unit_world("healthy"))

CULTURE_MUTATIONS = [
    lambda w: w["cultures"][0].update(migration_pressure=None),
    lambda w: w["cultures"][0].update(mean_fertility=.12345),
    lambda w: w["cultures"][0].update(agricultural_area_km2=123456789.),
    lambda w: w["cultures"][0].update(ruin_count_available=1),
    lambda w: w["cultures"][0].update(continuity_estimate_available=1),
    lambda w: w["cultures"][0].update(ruin_candidate_cell_count=999),
    lambda w: w["cultures"][0].update(recorded_ruin_count=999),
    lambda w: w["cultures"][0].update(continuity_index=None if w["cultures"][0]["continuity_index"] is not None else .5),
    lambda w: w["cultures"][0].update(estimated_age_years=None if w["cultures"][0]["estimated_age_years"] is not None else 1800.),
    lambda w: w["cultures"][0].update(dominant_resource="bogus"),
    lambda w: w["language_regions"][0].update(phoneme_inventory_size=True),
    lambda w: w["language_regions"][0].update(sound_shift_index=.999),
    lambda w: w["language_regions"][0].update(culture_ids=[True]),
    lambda w: w["sacred_areas"][0].update(significance=.99999),
    lambda w: w["sacred_areas"].pop(),
    lambda w: w["culture_region_model"].update(deterministic=1),
    lambda w: w["culture_region_model"].update(source_cultural_site_model="old"),
    lambda w: w["cultural_site_model"].update(extra=True),
    lambda w: w["cultural_site_model"].update(ruin_candidate_threshold=True),
    lambda w: w["language_region_model"].update(model_type="language_v2"),
    lambda w: w["summary"].update(mean_cultural_continuity=None if w["summary"]["mean_cultural_continuity"] is not None else 0.),
    lambda w: w["summary"]["native_social_summary_availability"].update(ruin_count=1),
    lambda w: w["summary"].update(recorded_ruin_count=999),
    lambda w: w["political_regions"][0].update(settlement_count=True),
    lambda w: w["cells"][0].update(culture_region_id=True),
    lambda w: w["cells"][0].update(is_closed_basin=1),
]
@pytest.mark.parametrize("mutate", CULTURE_MUTATIONS)
def test_independent_cultural_fields_and_nulls_reject_nonvacuous_tampers(source, mutate):
    assert validate_cultural_geography_replay(source) == []
    changed = deepcopy(source); mutate(changed)
    assert json.dumps(changed, sort_keys=True) != json.dumps(source, sort_keys=True)
    assert validate_cultural_geography_replay(changed)
    # History validates its complete consumed cultural source too.
    assert validate_historical_geography_replay(changed)

HISTORY_MUTATIONS = [
    lambda w: w["historical_events"][0].update(year_bp=-1.),
    lambda w: w["historical_events"][0].update(pressure_index=.99999),
    lambda w: w["historical_events"][0].update(continuity_estimate_available=1),
    lambda w: w["historical_events"][0].update(continuity_index=None if w["historical_events"][0]["continuity_index"] is not None else .5),
    lambda w: w["historical_events"].pop(),
    lambda w: w["historical_events"].reverse(),
    lambda w: w["historical_eras"][0].update(recorded_event_count=999),
    lambda w: w["historical_eras"][0].update(event_count_available=1),
    lambda w: w["historical_eras"][0].update(event_count=None if w["historical_eras"][0]["event_count"] is not None else 0),
    lambda w: w["historical_eras"][0].update(migration_event_count=True),
    lambda w: w["historical_eras"][0].update(mean_connectivity_available=1),
    lambda w: w["historical_eras"][0].update(start_year_bp=4000.),
    lambda w: w["native_social_availability"]["historical_event_family_coverage"][0].update(available_source_count=999),
    lambda w: w["native_social_availability"]["historical_event_family_coverage"][1].update(applicable_source_count=999),
    lambda w: w["native_social_availability"]["historical_event_family_coverage"][2].update(recorded_event_count=999),
    lambda w: w["native_social_availability"]["historical_event_family_coverage"][6].update(applicable_source_count=0 if w["native_social_availability"]["historical_event_family_coverage"][6]["applicable_source_count"] is None else None),
    lambda w: w["native_social_availability"].update(historical_event_inference_available=not w["native_social_availability"]["historical_event_inference_available"]),
    lambda w: w["historical_event_model"].update(deterministic=1),
    lambda w: w["historical_event_model"].update(source_culture_region_model="old"),
    lambda w: w["historical_event_model"].update(extra=True),
    lambda w: w["summary"].update(recorded_historical_event_count=999),
    lambda w: w["summary"].update(historical_event_count=None if w["summary"]["historical_event_count"] is not None else 0),
    lambda w: w["summary"].update(mean_historical_instability=None if w["summary"]["mean_historical_instability"] is not None else 0.),
    lambda w: w["summary"]["native_social_summary_availability"].update(dynastic_change_count=1),
]
@pytest.mark.parametrize("mutate", HISTORY_MUTATIONS)
def test_independent_history_families_dates_counts_and_nulls_reject(source, mutate):
    assert validate_historical_geography_replay(source) == []
    changed = deepcopy(source); mutate(changed)
    assert json.dumps(changed, sort_keys=True) != json.dumps(source, sort_keys=True)
    assert validate_historical_geography_replay(changed)


def test_mixed_retains_known_migration_and_trade_but_never_fills_foundations():
    world = annotated_environment_social_world("mixed")
    assert validate_historical_geography_replay(world) == []
    assert all(e["type"] not in {"state_foundation", "dynastic_change", "ruin_abandonment"} for e in world["historical_events"])
    retained = [e for e in world["historical_events"] if e["type"] in {"migration", "sacred_founding"}]
    assert retained and all(e["continuity_index"] is None and e["continuity_estimate_available"] is False for e in retained)
    assert any(e["type"] == "trade_boom" and e["continuity_estimate_available"] for e in world["historical_events"])
    changed = deepcopy(world); changed["historical_events"][0]["type"] = "state_foundation"
    assert validate_historical_geography_replay(changed)


def test_local_empty_candidate_culture_keeps_only_its_known_values():
    world = native_social_unit_world("empty_candidate_culture")
    assert cultural_equations_valid(world) and historical_equations_valid(world)
    assert not world["native_social_availability"]["ruin_inference_available"]
    known = next(c for c in world["cultures"] if c["ruin_candidate_cell_count"] == 0)
    unknown = next(c for c in world["cultures"] if c["ruin_candidate_cell_count"] > 0)
    assert known["ruin_count"] == 0 and known["continuity_estimate_available"]
    assert unknown["ruin_count"] is None and not unknown["continuity_estimate_available"]
    bad = deepcopy(world); bad["cultures"][known["id"]]["continuity_index"] = None
    with pytest.raises(ValueError, match="finite nonboolean"):
        cultural_equations_valid(bad)

@pytest.mark.parametrize("name", ["culture_region_model", "historical_event_model"])
def test_declared_successor_cannot_downgrade_by_deleting_provenance(name):
    world = annotated_environment_social_world("healthy")
    del world["native_social_availability_model"]
    del world["native_social_availability"]
    assert all(validate(world) for validate in VALIDATORS)


def test_orphan_successor_records_cannot_enter_legacy_replay_by_retagging():
    from magic_geo.cultural_geography_validation import _culture_model, _site_model
    from magic_geo.historical_geography_validation import _model
    world = annotated_environment_social_world("healthy")
    for key in ("native_social_availability", "native_social_availability_model",
                "population_region_model", "conflict_model", "dynasty_model",
                "territorial_snapshot_model"):
        world.pop(key, None)
    world["settlement_selection_model"]["model_type"] = (
        "causal_native_score_local_max_separated_settlement_selection_v2")
    for key, declaration in (("culture_region_model", _culture_model()),
                             ("cultural_site_model", _site_model()),
                             ("historical_event_model", _model())):
        world[key] = declaration
        world["summary"][key] = declaration["model_type"]
    assert world["cultures"][0]["continuity_estimate_available"] is True
    before = deepcopy(world)
    assert all(validate(world) for validate in VALIDATORS)
    assert world == before


def test_retained_legacy_model_and_public_error_strings_unchanged():
    base = Path(__file__).parent/"fixtures/legacy_human_water"
    entry = json.loads((base/"manifest.json").read_text())["replay_128"]
    raw = (base/entry["fixture"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["fixture_gzip_sha256"]
    world = json.loads(gzip.decompress(raw))
    before = deepcopy(world)
    assert all(validate(world) == [] for validate in VALIDATORS)
    assert world == before
    broken = deepcopy(world); broken["cultures"][0]["mean_fertility"] = -.5
    assert validate_cultural_geography_replay(broken) == ["cultural geography model or causal replay invalid"]
    broken = deepcopy(world); broken["historical_events"][0]["year_bp"] = -1
    assert validate_historical_geography_replay(broken) == ["historical geography model or causal replay invalid"]


def test_no_producer_model_or_equation_imports():
    root = Path(__file__).parents[1]/"src/magic_geo"
    for name in ("native_cultural_availability_validation.py", "native_historical_availability_validation.py"):
        tree = ast.parse((root/name).read_text())
        imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any(module in imports for module in ("native_social_models", "cultural_geography", "historical_geography"))
