"""Deliberate ordered upgrades of retained complete natural source meshes."""

from magic_geo import api


def upgrade_natural_water(world):
    """Refresh the physical water tail, preserving unrelated downstream records.

    Callers must rebuild any later consumers they intend to validate. This
    function alone makes no whole-world acceptance claim.
    """
    keys = ("aquifer_resource_model", "groundwater_flow_model",
            "river_channel_morphology_model", "river_hydraulics_model")
    for key in keys:
        assert world[key]["model_type"].endswith("_v1")
        assert world["summary"][key] == world[key]["model_type"]
    assert "karst_diagnostics_model" not in world
    assert "karst_diagnostics_model" not in world["summary"]
    for key in keys:
        del world[key]
        del world["summary"][key]
    for enrich in (
        api.enrich_world_with_aquifer_resources,
        api.enrich_world_with_hydrology_budget,
        api.enrich_world_with_wetland_diagnostics,
        api.enrich_world_with_groundwater_flow,
        api.enrich_world_with_river_channel_morphology,
        api.enrich_world_with_river_hydraulics,
        api.enrich_world_with_karst_diagnostics,
    ):
        enrich(world)
    return world
