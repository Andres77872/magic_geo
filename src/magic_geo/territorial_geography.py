from __future__ import annotations

from typing import Any


TERRITORIAL_SNAPSHOT_MODEL = "causal_era_scaled_spherical_region_territorial_snapshots_v1"


def _legacy_enrich_world_with_territorial_geography_model(world: dict[str, Any]) -> dict[str, Any]:
    snapshots = world.get("territorial_snapshots", [])
    if not isinstance(snapshots, list):
        return world
    world["territorial_snapshot_model"] = {
        "model_type": TERRITORIAL_SNAPSHOT_MODEL,
        "deterministic": True,
        "base_membership_model": "nonwater_political_region_cells_v1",
        "boundary_cell_model": "water_or_other_region_neighbor_v1",
        "centroid_model": "area_weighted_lat_lon_and_cartesian_center_v1",
        "boundary_ring_model": "tangent_plane_angle_sort_uniform_floor_sample_closed_ring_v1",
        "maximum_boundary_ring_points_before_closure": 64,
        "boundary_cell_sample_model": "record_order_uniform_floor_sample_v1",
        "maximum_boundary_cell_ids": 64,
        "perimeter_model": "great_circle_closed_ring_length_v1",
        "dissolved_area_model": "centered_orthographic_shoelace_proxy_v1",
        "era_area_factors": [0.48, 0.78, 0.64, 1.0],
        "era_population_factors": [0.34, 0.58, 0.74, 1.0],
        "stability_model": "culture_continuity_conflict_and_era_connectivity_v1",
        "fragmentation_model": "largest_area_share_and_mean_region_conflict_v1",
        "model_limitation": "scaled_static_regions_with_sampled_centroid_ordered_rings_not_exact_dynamic_cell_edge_territories",
    }
    world.setdefault("summary", {})["territorial_snapshot_model"] = TERRITORIAL_SNAPSHOT_MODEL
    return world


def enrich_world_with_territorial_geography_model(world: dict[str, Any]) -> dict[str, Any]:
    from .native_social_models import annotate_native_social_models

    return annotate_native_social_models(
        world, _legacy_enrich_world_with_territorial_geography_model, ('territorial_snapshot_model',),
    )
