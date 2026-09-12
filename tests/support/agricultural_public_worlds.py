"""Complete archived current-water worlds; deliberate land-use-only upgrade.

No native generation and no unannounced model retagging. Readonly cache entries
must be copied before mutation by tests.
"""

from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path

from magic_geo import api
from magic_geo.land_use_availability_validation import validate_land_use_availability


DATA = Path(__file__).parents[1] / "data/agricultural_public"
NATIVE_KEYS = (
    "climate_model", "climate_energy_model", "climate_energy_balance_records",
    "climate_energy_forcing_intervals", "climate_energy_transport_edges",
)


@lru_cache(maxsize=None)
def archived_agricultural_world_readonly(scope="full_world"):
    record = json.loads((DATA / "manifest.json").read_text())[scope]
    packed = (DATA / record["file"]).read_bytes()
    assert hashlib.sha256(packed).hexdigest() == record["gzip_sha256"]
    raw = gzip.decompress(packed)
    assert hashlib.sha256(raw).hexdigest() == record["source_sha256"]
    world = json.loads(raw)
    assert len(world["cells"]) == record["cell_count"]
    assert world.get("generation_scope", "full_world") == record["scope"]
    return world


def upgrade_agricultural_world(world):
    """Audit v1, deliberately remove both identities, then replay API successors."""
    assert world["land_use_zone_model"]["model_type"].endswith("_v1")
    assert validate_land_use_availability(world) == []
    native = {key: world[key] for key in NATIVE_KEYS}
    native_values = deepcopy(native)
    del world["land_use_zone_model"]
    del world["summary"]["land_use_zone_model"]
    for enrich in (
        api.enrich_world_with_land_use_zones, api.enrich_world_with_natural_frontiers,
        api.enrich_world_with_worldbuilding_realism, api.enrich_world_with_population_history,
        api.enrich_world_with_economy_history, api.enrich_world_with_dynasty_genealogy,
        api.enrich_world_with_logistics_history, api.enrich_world_with_demographic_agents,
        api.enrich_world_with_market_clearing, api.enrich_world_with_graph_diagnostics,
        api.enrich_world_with_boundary_geometry, api.enrich_world_with_phonology_history,
    ):
        enrich(world)
    assert all(world[key] is value and value == native_values[key] for key, value in native.items())
    return world


@lru_cache(maxsize=None)
def current_agricultural_world_readonly(label="warm"):
    if label == "warm":
        world = deepcopy(archived_agricultural_world_readonly())
    else:
        assert label == "cold"
        from support.ecology_worlds import current_ecology_world_readonly
        from support.natural_human_worlds import upgrade_natural_human_world

        # The existing hash-checked cold archive keeps its actual native climate.
        # Bring its water and following Python stages forward in API order before
        # deliberately upgrading its independently declared land-use version.
        world = upgrade_natural_human_world(deepcopy(current_ecology_world_readonly("cold")))
    return upgrade_agricultural_world(world)
