"""CSV must preserve the distinction between zero, unavailable and undeclared."""

import csv
from copy import deepcopy

from magic_geo.io import write_cells_csv


def test_csv_preserves_aquatic_estimate_availability_and_legacy_absence(tmp_path):
    world = {"cells": [
        {"id": 0, "primary_productivity_index": 0, "fishery_productivity_index": 0,
         "aquatic_climate_proxy_applicable": True, "aquatic_primary_climate_supported": False,
         "fishery_climate_supported": True, "fishery_productivity_supported": False},
        {"id": 1, "primary_productivity_index": 0, "fishery_productivity_index": 0,
         "aquatic_climate_proxy_applicable": True, "aquatic_primary_climate_supported": True,
         "fishery_climate_supported": True, "fishery_productivity_supported": True},
        {"id": 2, "primary_productivity_index": 0, "fishery_productivity_index": 0},
    ]}
    before = deepcopy(world)
    path = tmp_path / "cells.csv"
    write_cells_csv(path, world)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["fishery_productivity_index"] for row in rows] == ["0", "0", "0"]
    assert [row["aquatic_climate_proxy_applicable"] for row in rows] == ["True", "True", ""]
    assert [row["aquatic_primary_climate_supported"] for row in rows] == ["False", "True", ""]
    assert [row["fishery_climate_supported"] for row in rows] == ["True", "True", ""]
    assert [row["fishery_productivity_supported"] for row in rows] == ["False", "True", ""]
    assert world == before


def test_csv_keeps_fish_habitat_separate_from_input_support_and_river_applicability(tmp_path):
    world = {"cells": [
        {"id": 0, "species_terrestrial_habitat_eligible": False,
         "species_freshwater_habitat_eligible": True, "species_marine_habitat_eligible": False,
         "species_freshwater_fish_score_supported": False, "species_marine_fish_score_supported": False,
         "species_freshwater_fishery_input_mode": "standing_water_required"},
        {"id": 1, "species_terrestrial_habitat_eligible": True,
         "species_freshwater_habitat_eligible": True, "species_marine_habitat_eligible": False,
         "species_freshwater_fish_score_supported": True, "species_marine_fish_score_supported": False,
         "species_freshwater_fishery_input_mode": "river_inapplicable_omitted"},
        {"id": 2},
    ]}
    path = tmp_path / "cells.csv"
    write_cells_csv(path, world)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        headers = reader.fieldnames
    assert [row["species_terrestrial_habitat_eligible"] for row in rows] == ["False", "True", ""]
    assert [row["species_freshwater_habitat_eligible"] for row in rows] == ["True", "True", ""]
    assert [row["species_marine_habitat_eligible"] for row in rows] == ["False", "False", ""]
    assert [row["species_freshwater_fish_score_supported"] for row in rows] == ["False", "True", ""]
    assert [row["species_marine_fish_score_supported"] for row in rows] == ["False", "False", ""]
    assert [row["species_freshwater_fishery_input_mode"] for row in rows] == [
        "standing_water_required", "river_inapplicable_omitted", "",
    ]
    assert headers.index("aquatic_climate_proxy_applicable") > headers.index("thermal_subsidence_target_m")
