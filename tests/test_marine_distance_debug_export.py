"""Preserve no-source distance through debug tables, API and map-export guide."""
import math

import pyarrow.parquet as pq
import pytest

from magic_geo.climate_continentality import enrich_world_with_climate_continentality
from magic_geo.debug_export import export_debug_cache
from magic_geo.debug_map_export import build_color_codex
from magic_geo.debug_server import _DebugCache
from magic_geo.public_estimate_display import validate_layer_display_metadata
from test_marine_distance_sources import world


def test_no_source_distance_remains_a_nullable_debug_layer_and_family_column(tmp_path):
    source = world("land", "land", connected=False)
    enrich_world_with_climate_continentality(source)
    manifest = export_debug_cache(source, tmp_path, include_vtu=False)
    layer = next(item for item in manifest["layers"] if item["id"] == "cells/distance_to_marine_water_km")
    assert layer["kind"] == "numeric" and "stats" not in layer
    assert layer["marine_distance"] == {"status_field": "marine_distance_status", "no_source_cell_count": 2}
    table = pq.read_table(tmp_path / "tables/cells.parquet")
    assert table["distance_to_marine_water_km"].to_pylist() == [None, None]
    assert table.schema.field("distance_to_marine_water_km").type.bit_width == 64
    cache = _DebugCache(tmp_path)
    try:
        assert all(math.isnan(value) for value in cache.layer_values(layer["id"], None, None))
        for index in range(2):
            cell = cache.cell_record(index)
            assert cell["cell"]["distance_to_marine_water_km"] is None
            assert cell["cell"]["marine_distance_status"] == "no_marine_source"
        rows = cache.family_rows("climate_continentality_regions", 10, 0, "scalars")["rows"]
        assert len(rows) == 2
        assert all("mean_distance_to_marine_water_km" in row and row["mean_distance_to_marine_water_km"] is None for row in rows)
    finally:
        cache.close()
    guide = build_color_codex(layer, [math.nan, math.nan])
    assert "No marine source" in guide
    assert "No numeric color scale is inferred" in guide
    assert "Viridis normalized" not in guide


def test_reachable_marine_zero_and_coast_remain_numeric(tmp_path):
    source = world("ocean", "land")
    enrich_world_with_climate_continentality(source)
    manifest = export_debug_cache(source, tmp_path, include_vtu=False)
    layer = next(item for item in manifest["layers"] if item["id"] == "cells/distance_to_marine_water_km")
    assert layer["stats"]["min"] == 0.0
    assert layer["stats"]["max"] == 100.0
    assert layer["marine_distance"]["no_source_cell_count"] == 0
    cache = _DebugCache(tmp_path)
    try:
        assert cache.layer_values(layer["id"], None, None) == [0.0, 100.0]
    finally:
        cache.close()
    assert "No marine source" not in build_color_codex(layer, [0.0, 100.0])


@pytest.mark.parametrize("bad", [-1, 3, True, None, 0])
def test_marine_display_counts_are_typed_and_bounded(bad):
    layer = {"id": "cells/distance_to_marine_water_km", "source": "cells", "name": "distance_to_marine_water_km", "kind": "numeric",
             "marine_distance": {"status_field": "marine_distance_status", "no_source_cell_count": bad}}
    with pytest.raises(ValueError, match="marine distance"):
        validate_layer_display_metadata(layer, 2)
