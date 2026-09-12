"""Hash-checked complete worlds with an ordered Python ecology-tail replay.

Fixtures retain their actual native physics and generated society. Replaying
the consumer tail does not change their climate or substitute native generation.
"""
from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path

from magic_geo import api


FIXTURES = Path(__file__).parents[1] / "fixtures/cli_ecology_parent_availability"


@lru_cache(maxsize=None)
def historical_ecology_world_readonly(label="warm"):
    manifest = json.loads((FIXTURES / "manifest.json").read_text())[label]
    compressed = (FIXTURES / manifest["fixture"]).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == manifest["fixture_gzip_sha256"]
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(raw).hexdigest() == manifest["world_sha256"]
    world = json.loads(raw)
    assert world.get("generation_scope", "full_world") == "full_world"
    assert len(world["cells"]) == 128
    return world


@lru_cache(maxsize=None)
def current_ecology_world_readonly(label="warm"):
    world = deepcopy(historical_ecology_world_readonly(label))
    native_keys = (
        "climate_model", "climate_energy_model", "climate_energy_balance_records",
        "climate_energy_forcing_intervals", "climate_energy_transport_edges",
    )
    native = {k: world[k] for k in native_keys if k in world}
    native_values = deepcopy(native)
    fields = ("temperature_c", "temperature_monthly_c", "ocean_current_temperature_c",
              "elevation_m", "resource", "fertility", "soil_depth_m", "biome", "water_body_type")
    physical = [{k: deepcopy(c[k]) for k in fields if k in c} for c in world["cells"]]
    api._enrich_ecosystems_and_resources(world)
    for enrich in (
        api.enrich_world_with_land_use_zones, api.enrich_world_with_natural_frontiers,
        api.enrich_world_with_worldbuilding_realism, api.enrich_world_with_population_history,
        api.enrich_world_with_economy_history, api.enrich_world_with_dynasty_genealogy,
        api.enrich_world_with_logistics_history, api.enrich_world_with_demographic_agents,
        api.enrich_world_with_market_clearing, api.enrich_world_with_graph_diagnostics,
        api.enrich_world_with_boundary_geometry, api.enrich_world_with_phonology_history,
    ):
        enrich(world)
    assert physical == [{k: c[k] for k in fields if k in c} for c in world["cells"]]
    assert all(world[k] is v and world[k] == native_values[k] for k, v in native.items())
    return world
