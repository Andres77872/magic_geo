"""Synthetic marine-distance presentation controls; no world generation."""

from copy import deepcopy
import csv
import json

import pytest

from magic_geo.io import write_cells_csv, write_summary_markdown
from magic_geo.marine_distance_validation import MODEL


def display_world(no_source):
    distances = [None, None] if no_source else [0.0, 125.0]
    status = "no_marine_source" if no_source else "reachable_marine"
    return {
        "name": "Marine distance display control",
        "cells": [
            {"id": index, "distance_to_marine_water_km": distance,
             "marine_distance_status": status,
             "oceanic_humidity_availability_index": 0.0}
            for index, distance in enumerate(distances)
        ],
        "climate_continentality_model": deepcopy(MODEL),
        "summary": {
            "mean_distance_to_marine_water_km": None if no_source else 62.5,
            "marine_distance_defined_cell_count": 0 if no_source else 2,
            "no_marine_source_cell_count": 2 if no_source else 0,
        },
    }


@pytest.mark.parametrize("no_source", [True, False])
def test_csv_retains_distance_status_and_distinguishes_null_from_zero(tmp_path, no_source):
    world = display_world(no_source)
    before = deepcopy(world)
    target = tmp_path / "cells.csv"
    write_cells_csv(target, world)
    with target.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        rows = list(reader)
        columns = reader.fieldnames
    assert columns[-1] == "marine_distance_status"
    assert len(columns) == len(set(columns))
    assert columns[445] == "aquifer_natural_limitation_index"
    assert columns[446:450] == [
        "agricultural_habitat_applicable", "agricultural_climate_supported",
        "agricultural_potential_supported", "mining_surface_applicable",
    ]
    assert [row["marine_distance_status"] for row in rows] == [
        cell["marine_distance_status"] for cell in world["cells"]
    ]
    assert [row["distance_to_marine_water_km"] for row in rows] == (
        ["", ""] if no_source else ["0.0", "125.0"]
    )
    assert [row["oceanic_humidity_availability_index"] for row in rows] == ["0.0", "0.0"]
    schema = json.loads(target.with_suffix(".csv.schema.json").read_text())
    assert schema["column_types"]["distance_to_marine_water_km"] == "number"
    assert schema["column_types"]["marine_distance_status"] == "string"
    assert schema["declarations"]["models"]["climate_continentality_model"] == world["climate_continentality_model"]
    assert schema["marine_distance"]["status_field"] == "marine_distance_status"
    assert schema["marine_distance"]["null_meaning"] == "no_marine_source"
    assert world == before


@pytest.mark.parametrize("no_source", [True, False])
def test_summary_keeps_defined_counts_and_explains_no_source_null(tmp_path, no_source):
    world = display_world(no_source)
    before = deepcopy(world)
    target = tmp_path / "summary.md"
    write_summary_markdown(target, world)
    text = target.read_text()
    for key in ("marine_distance_defined_cell_count", "no_marine_source_cell_count"):
        assert f"`{key}`: {world['summary'][key]}" in text
    expected_mean = "Unavailable" if no_source else "62.5"
    assert f"`mean_distance_to_marine_water_km`: {expected_mean}" in text
    assert "mesh shortest-path distance" in text
    assert "no marine source" in text
    assert "Mean distance includes only defined distances" in text
    assert "does not mean absent total humidity or rainfall" in text
    assert world == before


def test_legacy_exports_do_not_invent_a_marine_source_status(tmp_path):
    world = {
        "cells": [{"id": 0, "distance_to_marine_water_km": 0.0}],
        "summary": {"mean_distance_to_marine_water_km": 0.0},
    }
    before = deepcopy(world)
    target = tmp_path / "cells.csv"
    write_cells_csv(target, world)
    with target.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    assert "marine_distance_status" not in rows[0]
    assert rows[0]["distance_to_marine_water_km"] == "0.0"
    schema = json.loads(target.with_suffix(".csv.schema.json").read_text())
    assert "marine_distance" not in schema
    summary = tmp_path / "summary.md"
    write_summary_markdown(summary, world)
    text = summary.read_text()
    assert "`mean_distance_to_marine_water_km`: 0.0" in text
    assert "Marine distance scope" not in text
    assert "`no_marine_source_cell_count`:" not in text
    assert world == before
