"""Scope text and unknown metadata handling in the public Markdown export."""
import pytest

from magic_geo.io import write_summary_markdown


@pytest.mark.parametrize("name", [[], {}, None, False, 5, "unknown_future_model"])
def test_unknown_model_names_do_not_crash_or_claim_prescribed_natural_scope(tmp_path, name):
    # These are display inputs, not a claimed complete ecological certificate.
    world = {"name": "Undeclared display", "cells": [], "summary": {},
             **{key: {"model": name} for key in (
                 "ecosystem_dynamics_model", "species_ranges_model", "wildfire_disturbance_model")}}
    path = tmp_path / "summary.md"
    write_summary_markdown(path, world)
    text = path.read_text()
    assert "Ecosystem activity scope:" not in text
    assert "Wildfire activity scope:" not in text
    assert "Wildfire coverage:" not in text


@pytest.mark.parametrize("fire", [
    "heuristic_wildfire_prescribed_natural_parent_availability_v6",
    "heuristic_wildfire_native_seasonal_prescribed_natural_parent_availability_v7",
])
def test_prescribed_natural_labels_retain_availability_and_qualified_activity_scope(tmp_path, fire):
    world = {"name": "Declared display labels", "cells": [], "summary": {},
             "ecosystem_dynamics_model": {"model": "heuristic_ecosystem_climate_support_v5"},
             "species_ranges_model": {"model": "heuristic_species_parent_support_v4"},
             "wildfire_disturbance_model": {"model": fire}}
    path = tmp_path / "summary.md"
    write_summary_markdown(path, world)
    text = path.read_text()
    assert "All-cell means include those zeros" in text
    assert "complete score coverage can coexist with no range records" in text
    assert "not evidence of physical containment" in text
    assert "Human activity is outside this scenario" in text
    assert "omits settlement suitability" in text
    assert "not a calibrated ignition frequency" in text
