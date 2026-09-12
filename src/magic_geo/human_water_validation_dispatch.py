"""Public full-world validation of the declared human water transport tail."""

from __future__ import annotations

from typing import Any

from .human_water_transport_validation import (
    human_water_transport_model_version,
    validate_versioned_route_corridors,
)


def validate_public_human_water_transport(
    world: dict[str, Any], *, natural_water: bool
) -> tuple[bool, list[str]]:
    """Require published matching stages before eager full-world consumers.

    The caller first audits the complete natural water chain. A current corridor
    audit also replays navigation and ports against their actual parent outputs.
    Historical worlds retain their original public equation and record checks.
    This full-world boundary is separate from geography-only human exclusion.
    """
    if not isinstance(world, dict):
        return natural_water, ['human water transport: world must be an object']
    try:
        expected = None
        for stage, key in (
            ("navigation", "navigability_model"),
            ("ports", "port_site_model"),
            ("corridors", "route_corridor_model"),
        ):
            if key not in world:
                return natural_water, [f"human water transport: published {key} required"]
            version = human_water_transport_model_version(world, stage)
            if expected is None:
                # Exact declared historical v2 remains v2 even if the retained
                # archive includes the earlier isolated selection-v3 producer.
                # New publication chooses v3 at its own input boundary.
                expected = version
            if version != expected or version not in ((2, 3) if natural_water else (1,)):
                return natural_water, [f"human water transport: {stage} and natural water versions must match"]
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return natural_water, [str(exc)[:600] or "human water transport: malformed model declaration"]
    if not natural_water:
        return False, []
    return True, validate_versioned_route_corridors(world)
