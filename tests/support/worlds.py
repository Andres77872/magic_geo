"""Canonical world configurations and a per-process generation cache.

Generating a world runs the native simulation core plus the full enrichment
pipeline, so each canonical configuration is generated at most once per process.

Most callers want :func:`cached_world`, which hands out a private deep copy.
:func:`cached_world_readonly` returns the shared object for read-only callers;
mutating it corrupts every later test in the process.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from magic_geo.api import generate_world
from magic_geo.config import WorldConfig, load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
EARTHLIKE_CONFIG = REPO_ROOT / "configs" / "earthlike_seed.yaml"

#: Configurations shared by more than one test, as dotted overrides on the
#: earthlike seed. One-off configurations stay inline in their own test.
CANONICAL: dict[str, dict[str, Any]] = {
    "small_smoke": {
        "mesh.cell_count": 256,
        "tectonics.plate_count": 8,
        "erosion.iterations": 2,
    },
    "mid_512": {
        "mesh.cell_count": 512,
        "tectonics.plate_count": 8,
        "erosion.iterations": 1,
    },
    "routed_512": {"mesh.cell_count": 512},
    "coupled_128": {
        "mesh.cell_count": 128,
        "tectonics.plate_count": 8,
        "erosion.iterations": 1,
    },
    "replay_128": {"mesh.cell_count": 128},
}

_cache: dict[str, dict[str, Any]] = {}


def build_config(**overrides: Any) -> WorldConfig:
    """Load the earthlike seed and apply dotted-key overrides.

    ``build_config(**{"mesh.cell_count": 256})`` overrides ``mesh.cell_count``.
    """
    config = load_config(EARTHLIKE_CONFIG)
    data = config.model_dump(mode="python")
    for dotted, value in overrides.items():
        node = data
        *parents, leaf = dotted.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return type(config).model_validate(data)


def canonical_config(key: str) -> WorldConfig:
    """A freshly built configuration for the canonical world ``key``."""
    return build_config(**CANONICAL[key])


def cached_world_readonly(key: str) -> dict[str, Any]:
    """The shared generated world for ``key``. Callers must never mutate it."""
    if key not in _cache:
        _cache[key] = generate_world(canonical_config(key))
    return _cache[key]


def cached_world(key: str) -> dict[str, Any]:
    """A private deep copy of the generated world for ``key``."""
    return copy.deepcopy(cached_world_readonly(key))
