"""Legacy identity preservation and explicit refusal of incomplete migrations."""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from test_settlement_climate_support import enrich, synthetic
from magic_geo.cultural_geography import enrich_world_with_cultural_geography_models
from magic_geo.historical_geography import enrich_world_with_historical_geography_model
from magic_geo.civilization_geography import enrich_world_with_civilization_geography_models
from magic_geo.territorial_geography import enrich_world_with_territorial_geography_model
from support.native_social_worlds import environment_social_world

ANNOTATORS = (
    enrich_world_with_cultural_geography_models,
    enrich_world_with_historical_geography_model,
    enrich_world_with_civilization_geography_models,
    enrich_world_with_territorial_geography_model,
)


@pytest.fixture(scope="module")
def retained_legacy_world():
    root = Path(__file__).parent / "fixtures" / "legacy_human_water"
    entry = json.loads((root / "manifest.json").read_text())["replay_128"]
    raw = (root / entry["fixture"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["fixture_gzip_sha256"]
    data = gzip.decompress(raw)
    assert hashlib.sha256(data).hexdigest() == entry["world_sha256"]
    return json.loads(data)


@pytest.mark.parametrize("annotate", ANNOTATORS)
def test_retained_old_annotations_remain_identical(annotate, retained_legacy_world):
    world = deepcopy(retained_legacy_world)
    before = deepcopy(world)
    assert annotate(world) is world
    assert world == before


@pytest.mark.parametrize("annotate", ANNOTATORS)
def test_selection_only_candidate_cannot_acquire_social_successor_labels(annotate):
    # These existing fixtures contain only the reviewed placement-stage change,
    # not a newly computed native social availability envelope.
    world = enrich(synthetic())
    before = deepcopy(world)
    with pytest.raises(ValueError, match="native availability envelope"):
        annotate(world)
    assert world == before


@pytest.mark.parametrize("annotate", ANNOTATORS)
@pytest.mark.parametrize("field", ["settlement_selection_model", "population_region_model"])
def test_unknown_social_sources_are_not_rewritten_as_legacy(annotate,field,retained_legacy_world):
    world=deepcopy(retained_legacy_world)
    world[field]["model_type"]="unrecognized_future_v99"
    before=deepcopy(world)
    with pytest.raises(ValueError):
        annotate(world)
    assert world==before


@pytest.mark.parametrize("annotate", ANNOTATORS)
@pytest.mark.parametrize("case", ["healthy", "mixed"])
def test_first_annotation_audits_all_raw_social_records_and_publishes_only_owned_models(annotate, case):
    world = environment_social_world(case)
    before = deepcopy(world)
    expected_keys = {
        ANNOTATORS[0]: {"culture_region_model", "cultural_site_model", "language_region_model"},
        ANNOTATORS[1]: {"historical_event_model"},
        ANNOTATORS[2]: {"population_region_model", "conflict_model", "dynasty_model"},
        ANNOTATORS[3]: {"territorial_snapshot_model"},
    }[annotate]
    assert annotate(world) is world
    assert world.keys() - before.keys() == expected_keys
    for key, value in before.items():
        if key != "summary":
            assert world[key] == value
    expected_summary = dict(before["summary"])
    expected_summary.update({key: world[key]["model_type"] for key in expected_keys})
    assert world["summary"] == expected_summary


@pytest.mark.parametrize("annotate", ANNOTATORS)
@pytest.mark.parametrize("collection,field", [
    ("cultures", "continuity_index"),
    ("historical_events", "pressure_index"),
    ("population_regions", "estimated_population"),
    ("territorial_snapshots", "estimated_population"),
])
def test_cross_family_numeric_tampering_prevents_any_annotation(annotate, collection, field):
    world = environment_social_world()
    world[collection][0][field] += 100.0
    before = deepcopy(world)
    with pytest.raises(ValueError, match="invalid native social source"):
        annotate(world)
    assert world == before


@pytest.mark.parametrize("annotate", ANNOTATORS)
@pytest.mark.parametrize("summary_only", [False, True])
def test_stale_sibling_annotation_is_not_hidden_by_private_view(annotate, summary_only):
    world = environment_social_world()
    destination = world["summary"] if summary_only else world
    destination["population_region_model"] = None
    before = deepcopy(world)
    with pytest.raises(ValueError, match="incompatible existing social"):
        annotate(world)
    assert world == before


@pytest.mark.parametrize("annotate", ANNOTATORS)
@pytest.mark.parametrize("collection,field,value", [
    ("cultures", "recorded_ruin_count", 0),
    ("historical_events", "continuity_estimate_available", True),
    ("historical_eras", "recorded_event_count", 0),
    ("population_regions", "site_strength_index", 0.0),
    ("territorial_snapshots", "population_estimate_available", True),
    ("summary", "recorded_dynasty_count", 0),
])
def test_single_orphan_field_cannot_be_annotated_as_legacy(annotate, collection, field, value, retained_legacy_world):
    world = deepcopy(retained_legacy_world)
    row = world["summary"] if collection == "summary" else world[collection][0]
    row[field] = value
    before = deepcopy(world)
    with pytest.raises(ValueError, match="orphan native social"):
        annotate(world)
    assert world == before
