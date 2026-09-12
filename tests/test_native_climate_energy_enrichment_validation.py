"""Independent optional annual mirrors: raw acceptance and tamper refusal."""

from copy import deepcopy
import math

import pytest

from magic_geo.native_climate_energy import enrich_world_with_native_climate_energy
from magic_geo.native_climate_energy_enrichment_validation import validate_native_climate_energy_enrichment
from support.native_climate_energy import native_climate_world


CELL_FIELDS = (
    "effective_toa_albedo", "effective_longwave_emissivity",
    "annual_absorbed_shortwave_w_m2", "annual_emitted_longwave_w_m2",
    "annual_net_radiative_flux_w_m2", "annual_horizontal_heat_convergence_w_m2",
    "annual_net_heating_w_m2", "annual_heat_storage_tendency_w_m2",
    "annual_energy_balance_residual_w_m2", "annual_mean_abs_energy_balance_residual_w_m2",
    "annual_mean_energy_balance_numerical_allowance_w_m2",
)
SUMMARY_FIELDS = (
    "native_climate_energy_record_count", "native_climate_energy_total_area_m2",
    "native_climate_energy_year_duration_seconds",
    *(f"{prefix}_{field}" for prefix in ("cell_count_mean", "area_weighted_mean") for field in CELL_FIELDS),
)


@pytest.fixture(scope="module")
def native_pair():
    raw = native_climate_world()
    return raw, enrich_world_with_native_climate_energy(deepcopy(raw))


def validate_unchanged(world):
    before = deepcopy(world)
    native_references = {key: value for key, value in world.items() if key.startswith("climate_energy_")}
    result = validate_native_climate_energy_enrichment(world)
    assert world == before
    assert all(world[key] is value for key, value in native_references.items())
    assert len(result) <= 1
    if result:
        assert len(result[0]) <= 435
    return result


def test_raw_and_genuine_enriched_worlds_pass_without_another_budget_audit(native_pair, monkeypatch):
    import magic_geo.native_climate_energy_validation as physical

    def unexpected_audit(*args, **kwargs):
        raise AssertionError("the optional aggregation validator must not repeat native physics")

    monkeypatch.setattr(physical, "audit_native_climate_energy", unexpected_audit)
    for world in native_pair:
        assert validate_unchanged(world) == []


@pytest.mark.parametrize("field", CELL_FIELDS)
def test_every_cell_mirror_rejects_tamper_and_missing_fields(native_pair, field):
    world = deepcopy(native_pair[1])
    world["cells"][0][field] += max(1e-5, abs(world["cells"][0][field]) * 0.01)
    assert field in validate_unchanged(world)[0]
    del world["cells"][0][field]
    assert field in validate_unchanged(world)[0]


@pytest.mark.parametrize("field", SUMMARY_FIELDS)
def test_every_summary_mirror_rejects_tamper_and_missing_fields(native_pair, field):
    world = deepcopy(native_pair[1])
    world["summary"][field] += max(1, abs(world["summary"][field]) * 0.01)
    assert field in validate_unchanged(world)[0]
    del world["summary"][field]
    assert field in validate_unchanged(world)[0]


@pytest.mark.parametrize("location,field", [
    *(("cell", field) for field in CELL_FIELDS),
    *(("summary", field) for field in SUMMARY_FIELDS),
])
def test_each_undeclared_mirror_is_refused_without_native_enrichment_metadata(native_pair, location, field):
    world = deepcopy(native_pair[0])
    target = world["cells"][0] if location == "cell" else world.setdefault("summary", {})
    target[field] = 0.0
    assert "require their enrichment declaration" in validate_unchanged(world)[0]


@pytest.mark.parametrize("declaration", [None, False, [], "native_climate_energy_annual_aggregation_v1", {}, {"model": "future_v2"}])
def test_present_unknown_or_malformed_metadata_is_not_raw_legacy_compatibility(native_pair, declaration):
    world = deepcopy(native_pair[0])
    world["native_climate_energy_enrichment_model"] = declaration
    assert "enrichment declaration" in validate_unchanged(world)[0]


def test_every_known_metadata_clause_is_required_exactly(native_pair):
    for key in native_pair[1]["native_climate_energy_enrichment_model"]:
        world = deepcopy(native_pair[1])
        world["native_climate_energy_enrichment_model"][key] = "changed"
        assert "enrichment declaration" in validate_unchanged(world)[0]
    world = deepcopy(native_pair[1])
    world["native_climate_energy_enrichment_model"]["unversioned_extension"] = True
    assert "enrichment declaration" in validate_unchanged(world)[0]


@pytest.mark.parametrize("invalid", [True, None, "0", float("nan"), float("inf"), -float("inf"), 10 ** 400])
@pytest.mark.parametrize("location", ["cell", "summary"])
def test_alias_values_must_be_finite_real_numbers(native_pair, invalid, location):
    world = deepcopy(native_pair[1])
    if location == "cell":
        world["cells"][0]["annual_absorbed_shortwave_w_m2"] = invalid
    else:
        world["summary"]["area_weighted_mean_annual_absorbed_shortwave_w_m2"] = invalid
    assert validate_unchanged(world)


@pytest.mark.parametrize("invalid", [True, 128.0, None, 127])
def test_record_count_is_an_exact_integer(native_pair, invalid):
    world = deepcopy(native_pair[1])
    world["summary"]["native_climate_energy_record_count"] = invalid
    assert "record_count" in validate_unchanged(world)[0]


def test_small_residual_tamper_cannot_hide_behind_large_source_or_producer_tolerances(native_pair):
    world = deepcopy(native_pair[1])
    field = "annual_energy_balance_residual_w_m2"
    old = world["cells"][0][field]
    assert 0 < abs(old) < 1e-7
    world["cells"][0][field] = -old
    for record in world["climate_energy_balance_records"]:
        record["annual_flux_tolerance_w_m2"] = 1e200
    assert field in validate_unchanged(world)[0]


def test_exact_four_ulp_boundary_has_no_fixed_absolute_tolerance(native_pair):
    world = deepcopy(native_pair[1])
    field = "annual_energy_balance_residual_w_m2"
    for _ in range(4):
        world["cells"][0][field] = math.nextafter(world["cells"][0][field], math.inf)
    assert validate_unchanged(world) == []
    world["cells"][0][field] = math.nextafter(world["cells"][0][field], math.inf)
    assert field in validate_unchanged(world)[0]


def test_wrong_count_mean_cannot_replace_physical_area_mean(native_pair):
    world = deepcopy(native_pair[1])
    source = "cell_count_mean_annual_horizontal_heat_convergence_w_m2"
    target = "area_weighted_mean_annual_horizontal_heat_convergence_w_m2"
    assert world["summary"][source] != world["summary"][target]
    world["summary"][target] = world["summary"][source]
    assert target in validate_unchanged(world)[0]


@pytest.mark.parametrize("mutation", ["missing_record", "duplicate_record", "duplicate_cell", "bad_duration", "bad_area"])
def test_bounded_failure_on_missing_invariants_if_called_without_upstream_audit(native_pair, mutation):
    world = deepcopy(native_pair[1])
    if mutation == "missing_record":
        world["climate_energy_balance_records"].pop()
    elif mutation == "duplicate_record":
        world["climate_energy_balance_records"][1] = deepcopy(world["climate_energy_balance_records"][0])
    elif mutation == "duplicate_cell":
        world["cells"][1]["id"] = world["cells"][0]["id"]
    elif mutation == "bad_duration":
        world["climate_energy_model"]["monthly_duration_seconds"][0] = 0.0
    else:
        world["climate_energy_balance_records"][0]["area_m2"] = 0.0
    assert validate_unchanged(world)


def test_finite_extreme_products_and_cancellation_are_replayed_without_overflow(native_pair):
    # Arithmetic-only witness: the caller owns physical validation. We set
    # every retained budget to known constants and calculate mirrors by hand,
    # exercising this helper without invoking any producer aggregation code.
    world = deepcopy(native_pair[1])
    world["cells"] = world["cells"][:2]
    world["climate_energy_balance_records"] = world["climate_energy_balance_records"][:2]
    world["climate_energy_model"]["monthly_duration_seconds"] = [1e200] * 12
    for cell, record in zip(world["cells"], world["climate_energy_balance_records"]):
        record["area_m2"] = 1e200
        for key in list(record):
            if key.startswith("monthly_") and key.endswith("w_m2"):
                record[key] = [0.0] * 12
        record["monthly_absorbed_shortwave_w_m2"] = [1e200] * 12
        record["monthly_emitted_longwave_w_m2"] = [1e200] * 12
        record["monthly_balance_residual_w_m2"] = [1e300, 1.0, -1e300] + [0.0] * 9
        for field in CELL_FIELDS:
            cell[field] = 0.0
        cell["effective_toa_albedo"] = record["top_of_atmosphere_albedo"]
        cell["effective_longwave_emissivity"] = record["effective_longwave_emissivity"]
        cell["annual_absorbed_shortwave_w_m2"] = cell["annual_emitted_longwave_w_m2"] = 1e200
        cell["annual_energy_balance_residual_w_m2"] = 1 / 12
        cell["annual_mean_abs_energy_balance_residual_w_m2"] = 1e300 / 6
    summary = world["summary"]
    summary["native_climate_energy_record_count"] = 2
    summary["native_climate_energy_total_area_m2"] = 2e200
    summary["native_climate_energy_year_duration_seconds"] = 12e200
    for field in CELL_FIELDS:
        for prefix in ("cell_count_mean", "area_weighted_mean"):
            summary[f"{prefix}_{field}"] = sum(cell[field] / 2 for cell in world["cells"])
    assert validate_unchanged(world) == []
    # The final total area itself is not representable, so no success verdict
    # may be issued merely because each input area remains finite.
    for record in world["climate_energy_balance_records"]:
        record["area_m2"] = 1e308
    assert "not representable" in validate_unchanged(world)[0]
