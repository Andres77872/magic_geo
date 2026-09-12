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
from magic_geo.config import LegacyWorldConfig, WorldConfig, load_config

REPO_ROOT = Path(__file__).resolve().parents[2]
EARTHLIKE_CONFIG = REPO_ROOT / "configs" / "earthlike_seed.yaml"

#: Current configurations shared by tests. The default proof uses the public
#: constructor; other keys apply dotted overrides to the current earthlike seed.
#: One-off configurations stay inline in their own test.
CANONICAL: dict[str, dict[str, Any]] = {
    # Uses WorldConfig() directly; no climate overrides or profile assumptions.
    "default_128": {
        "mesh.cell_count": 128,
        "tectonics.plate_count": 8,
        "erosion.iterations": 0,
        "compute.backend": "cpu",
        "compute.threads": 2,
    },
    # Neutral current inputs retain a wet inland frontier town after one
    # terrain iteration. No climate or hydrology values are fitted to the test.
    "frontier_default_128": {
        "mesh.cell_count": 128,
        "erosion.iterations": 1,
        "compute.backend": "cpu",
        "compute.threads": 1,
    },
    "small_smoke": {
        "mesh.cell_count": 256,
        "tectonics.plate_count": 8,
        "erosion.iterations": 2,
    },
    # Two current-model languages with their own phonological rules/contact
    # histories. The larger mid_512 world has only one language after migration.
    "language_contact_256": {
        "mesh.cell_count": 256,
        "tectonics.plate_count": 8,
        "erosion.iterations": 1,
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

# Only original posthoc-equation and model-dispatch compatibility controls use
# this namespace. Generic geography, ecology and society fixtures stay current.
LEGACY_CANONICAL: dict[str, dict[str, Any]] = {
    "energy_128": {
        "mesh.cell_count": 128,
        "tectonics.plate_count": 8,
        "erosion.iterations": 0,
        "compute.backend": "cpu",
        "compute.threads": 1,
    },
}
_legacy_cache: dict[str, dict[str, Any]] = {}


def _with_overrides(config: Any, overrides: dict[str, Any]) -> Any:
    data = config.model_dump(mode="python")
    for dotted, value in overrides.items():
        node = data
        *parents, leaf = dotted.split(".")
        for key in parents:
            node = node[key]
        node[leaf] = value
    return type(config).model_validate(data)


def build_config(**overrides: Any) -> WorldConfig:
    """Load the earthlike seed and apply dotted-key overrides.

    ``build_config(**{"mesh.cell_count": 256})`` overrides ``mesh.cell_count``.
    """
    return _with_overrides(load_config(EARTHLIKE_CONFIG), overrides)


def build_legacy_config(**overrides: Any) -> LegacyWorldConfig:
    """Construct an explicit old-model control without loading current YAML.

    Use only when the assertion requires the preserved legacy climate or ABI.
    Current scientific and public-default tests must use ``build_config``.
    """
    return _with_overrides(LegacyWorldConfig(), overrides)


def canonical_config(key: str) -> WorldConfig:
    """A freshly built configuration for the canonical world ``key``."""
    if key in {"default_128", "frontier_default_128"}:
        return _with_overrides(WorldConfig(), CANONICAL[key])
    return build_config(**CANONICAL[key])


def cached_world_readonly(key: str) -> dict[str, Any]:
    """The shared generated world for ``key``. Callers must never mutate it."""
    if key not in _cache:
        _cache[key] = generate_world(canonical_config(key))
    return _cache[key]


def cached_world(key: str) -> dict[str, Any]:
    """A private deep copy of the generated world for ``key``."""
    return copy.deepcopy(cached_world_readonly(key))


def cached_legacy_world_readonly(key: str) -> dict[str, Any]:
    """Shared explicit legacy-model control; callers must never mutate it."""
    if key not in _legacy_cache:
        config = build_legacy_config(**LEGACY_CANONICAL[key])
        _legacy_cache[key] = generate_world(config)
    return _legacy_cache[key]


def cached_legacy_world(key: str) -> dict[str, Any]:
    """Private copy of an explicit legacy-model compatibility control."""
    return copy.deepcopy(cached_legacy_world_readonly(key))
