"""Current seasonal cryosphere witnesses, generated once per scope.

The shipped cryogenic scenario's physical forcing is unchanged. A 128-cell,
zero-erosion world retains multiple permafrost regions and ice histories without
requiring a large scenario. Review runners may preload ``_cache`` with an exact
generated archive; ordinary tests have no dependency on ignored artifacts.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from magic_geo.api import generate_geo_world, generate_world
from magic_geo.config import WorldConfig, load_config


_cache: dict[str, dict[str, Any]] = {}
_geodesic_cache: dict[str, dict[str, Any]] = {}


def cold_config() -> WorldConfig:
    path = Path(__file__).resolve().parents[2] / "configs/seeds/cryogenic_slushball.yaml"
    data = load_config(path).model_dump(mode="python")
    data["mesh"]["cell_count"] = 128
    data["erosion"]["iterations"] = 0
    data["compute"]["backend"] = "cpu"
    data["compute"]["threads"] = 1
    return WorldConfig.model_validate(data)


def cached_cold_world_readonly(scope: str = "geo_only") -> dict[str, Any]:
    """Return a shared actual generated world; callers must not mutate it."""
    if scope not in {"geo_only", "full_world"}:
        raise ValueError(f"unsupported cold-world scope: {scope}")
    if scope not in _cache:
        generate = generate_geo_world if scope == "geo_only" else generate_world
        _cache[scope] = generate(cold_config())
    return _cache[scope]


def cached_cold_world(scope: str = "geo_only") -> dict[str, Any]:
    return deepcopy(cached_cold_world_readonly(scope))


def cold_geodesic_config() -> WorldConfig:
    """Shipped cold forcing on unequal-area cells, with one erosion iteration."""
    data = cold_config().model_dump(mode="python")
    data["mesh"]["backend"] = "geodesic_icosahedron"
    data["mesh"]["cell_count"] = 162
    data["erosion"]["iterations"] = 1
    return WorldConfig.model_validate(data)


def cached_cold_geodesic_world_readonly(scope: str = "full_world") -> dict[str, Any]:
    """Keep the original zero-erosion cache/recipe separate and unchanged."""
    if scope not in {"geo_only", "full_world"}:
        raise ValueError(f"unsupported cold-world scope: {scope}")
    if scope not in _geodesic_cache:
        generate = generate_geo_world if scope == "geo_only" else generate_world
        _geodesic_cache[scope] = generate(cold_geodesic_config())
    return _geodesic_cache[scope]
