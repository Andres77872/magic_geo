"""Complete retained WATER-v1 controls, with their actual seasonal climate.

These fixtures exercise historical water equations and exact legacy CLI errors.
They do not select legacy climate or replace the generic current-world cache.
The manifest retains original archive/configuration and both content hashes.
"""

from copy import deepcopy
from functools import lru_cache
import gzip
import hashlib
import json
from pathlib import Path


FIXTURES = Path(__file__).parents[1] / "fixtures/legacy_human_water"


@lru_cache(maxsize=None)
def legacy_human_water_world_readonly(key="small_smoke"):
    """Load the exact complete historical output; callers must not mutate it."""
    entry = json.loads((FIXTURES / "manifest.json").read_text())[key]
    compressed = (FIXTURES / entry["fixture"]).read_bytes()
    assert hashlib.sha256(compressed).hexdigest() == entry["fixture_gzip_sha256"]
    raw = gzip.decompress(compressed)
    assert hashlib.sha256(raw).hexdigest() == entry["world_sha256"]
    world = json.loads(raw)
    assert world.get("generation_scope", "full_world") == "full_world"
    assert len(world["cells"]) == entry["cell_count"]
    assert world["climate_model"]["model_type"] == "prescribed_seasonal_surface_energy_v1"
    for field, model_type in entry["water_models"].items():
        assert world[field]["model_type"] == model_type
        assert world["summary"][field] == model_type
        assert model_type.endswith("_v1")
    return world


def legacy_human_water_world(key="small_smoke"):
    """Private copy for a historical equation or CLI mutation."""
    return deepcopy(legacy_human_water_world_readonly(key))
