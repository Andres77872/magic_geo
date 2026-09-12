"""Independent source-link replay for reef annotations over partial port sites.

This audits annotations only. Reef habitat and growth remain physically scoped.
"""
from __future__ import annotations
from typing import Any

PORTS3 = "causal_navigability_coastal_port_site_selection_v3"
MODEL = {
    "model_type": "reef_supported_port_site_links_v1",
    "source_port_site_model": PORTS3,
    "source_domain": "reef_member_cells_and_existing_nonmarine_land_neighbors",
    "link_policy": "retain_supported_emitted_port_ids_with_local_completeness",
    "physical_reef_policy": "unchanged_no_port_support_gate",
}


def validate_reef_port_links(world: Any) -> list[str]:
    try:
        if type(world) is not dict:
            raise ValueError("world must be a mapping")
        current = isinstance(world.get("port_site_model"), dict) and world["port_site_model"].get("model_type") == PORTS3
        declared = "reef_port_links_model" in world
        records = world.get("reef_systems", [])
        if not current:
            if declared or "reef_port_links_model" in world.get("summary", {}) or any("port_site_links_complete" in row for row in records):
                raise ValueError("reef port annotations require matching ports3")
            return []
        from .human_water_transport_validation import validate_versioned_port_sites
        errors = validate_versioned_port_sites(world)
        if errors:
            raise ValueError("port source: " + "; ".join(errors[:3]))
        model = world.get("reef_port_links_model")
        if type(model) is not dict or model != MODEL or model.keys() != MODEL.keys():
            raise ValueError("exact reef port annotation declaration required")
        summary = world["summary"]
        if summary.get("reef_port_links_model") != MODEL["model_type"]:
            raise ValueError("reef port annotation summary declaration mismatch")
        by_id = {row["id"]: row for row in world["cells"]}
        incomplete = 0
        for row in records:
            members = row["cell_ids"]
            if type(members) is not list or any(type(cid) is not int or cid not in by_id for cid in members) or len(set(members)) != len(members):
                raise ValueError("invalid reef member IDs")
            nearby = set(members)
            nearby.update(nid for cid in members for nid in by_id[cid]["neighbors"] if by_id[nid]["is_water"] is False)
            complete = all(by_id[cid]["port_site_selection_supported"] for cid in nearby)
            ids = sorted({by_id[cid]["port_site_id"] for cid in nearby if by_id[cid]["port_site_selection_supported"] and by_id[cid]["port_site_id"] >= 0})
            if type(row.get("port_site_links_complete")) is not bool or row["port_site_links_complete"] != complete:
                raise ValueError("reef local port link coverage mismatch")
            observed = row.get("port_site_ids")
            if type(observed) is not list or any(type(value) is not int for value in observed) or observed != ids:
                raise ValueError("reef supported port IDs mismatch")
            incomplete += not complete
        for key, expected in {"reef_port_links_complete": incomplete == 0,
                              "reef_port_links_incomplete_system_count": incomplete,
                              "reef_source_port_selection_complete": summary["port_site_selection_complete"]}.items():
            if type(summary.get(key)) is not type(expected) or summary[key] != expected:
                raise ValueError("reef annotation coverage mismatch: " + key)
        return []
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        return ["reef port links: " + str(error)[:500]]
