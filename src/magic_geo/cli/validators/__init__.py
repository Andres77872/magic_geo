"""Pure per-domain validators used by the `validate` command.

Every function takes the world payload plus derived lookups and returns a
list of failure strings; none of them raise or exit.
"""

from __future__ import annotations

from ._shared import _nominal_time_record_valid
from .hydrology import (
    _validate_hydrologic_water_budget,
    _validate_groundwater_recharge,
    _validate_aquifer_resources,
    _validate_groundwater_flow,
)
from .rivers import _validate_river_channel_morphology, _validate_river_hydraulics
from .settlement import _validate_settlement_selection, _validate_route_network
from .political import (
    _political_clamp,
    _political_neighbors,
    _political_has_water_neighbor,
    _political_angular_distance,
    _political_endpoint_barrier,
    _political_local_relief,
    _validate_political_regions,
    _validate_political_borders,
    _validate_trade_flows,
)
from .navigability import _validate_navigability
from .ports import _validate_port_sites
from .corridors import _validate_route_corridors
from .sediment import (
    _validate_fluvial_sediment_routing,
    _validate_hillslope_sediment_transport,
    _validate_glacial_sediment_transport,
    _validate_sediment_inventory,
)

__all__ = [
    "_nominal_time_record_valid",
    "_political_angular_distance",
    "_political_clamp",
    "_political_endpoint_barrier",
    "_political_has_water_neighbor",
    "_political_local_relief",
    "_political_neighbors",
    "_validate_aquifer_resources",
    "_validate_fluvial_sediment_routing",
    "_validate_glacial_sediment_transport",
    "_validate_groundwater_flow",
    "_validate_groundwater_recharge",
    "_validate_hillslope_sediment_transport",
    "_validate_hydrologic_water_budget",
    "_validate_navigability",
    "_validate_political_borders",
    "_validate_political_regions",
    "_validate_port_sites",
    "_validate_river_channel_morphology",
    "_validate_river_hydraulics",
    "_validate_route_corridors",
    "_validate_route_network",
    "_validate_sediment_inventory",
    "_validate_settlement_selection",
    "_validate_trade_flows",
]
