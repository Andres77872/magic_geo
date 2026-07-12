"""Layer-by-layer evidence contracts for natural planet generation.

The main validator has intentionally detailed checks, but those checks are
grouped by implementation domain.  This module projects that evidence back
onto the natural pipeline described by ``r1.md`` so a green aggregate verdict
cannot hide an unrepresented layer.

``contract_passed`` means that required artifacts exist, every declared
validator domain supplied evidence, upstream layer contracts passed, and every
fatal check assigned to the layer passed. It is deliberately *not* a claim
that the model is empirically realistic. ``evidence_class`` and
``temporal_class`` make that distinction explicit for reports and callers.
"""

from __future__ import annotations

from typing import Any


LAYER_CONTRACT_SCHEMA_VERSION = 1


# Output kinds are part of the contract: an empty list is valid evidence for a
# phenomenon that is absent in a particular scenario, while a missing or
# wrongly typed registry is not.
GEO_LAYER_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "id": "planet_parameters",
        "phase": 0,
        "name": "Planet parameters and boundary conditions",
        "dependencies": (),
        "required_outputs": {
            "planet_parameters": "dict",
            "planet_realism_checks": "list",
        },
        "validator_domains": ("contract",),
        "temporal_class": "configuration_boundary_condition",
        "evidence_class": "internal_contract_and_broad_regime_checks",
    },
    {
        "id": "spherical_mesh",
        "phase": 1,
        "name": "Spherical mesh, areas, geometry, and spatial indices",
        "dependencies": ("planet_parameters",),
        "required_outputs": {
            "cells": "nonempty_list",
            "cell_area_model": "nonempty_str",
            "mesh_lod": "dict",
            "spherical_spatial_index": "dict",
            "cell_adjacency_edges": "list",
        },
        "validator_domains": ("mesh", "geometry_indices", "natural_graphs"),
        "temporal_class": "static_simulation_domain",
        "evidence_class": "independent_geometry_replay",
    },
    {
        "id": "plate_tectonics",
        "phase": 2,
        "name": "Plate domains, kinematics, boundaries, zones, and faults",
        "dependencies": ("spherical_mesh",),
        "required_outputs": {
            "plates": "nonempty_list",
            "plate_kinematic_model": "dict",
            "plate_boundary_segment_model": "dict",
            "crust_overlap_candidate_fate_model": "dict",
            "plate_motion_history": "nonempty_list",
            "tectonic_zones": "list",
            "fault_systems": "list",
        },
        "validator_domains": ("tectonics", "tectonic_zones_faults"),
        "temporal_class": "native_nominal_maturation_intervals",
        "evidence_class": (
            "exact_directed_control_volume_segment_kinematics_and_pair_wide_"
            "diagnostic_overlap_candidate_crosswalk_replay_without_local_"
            "fragment_link_allocation_physical_polarity_or_slab_transfer"
        ),
    },
    {
        "id": "crust_lithology",
        "phase": 3,
        "name": "Crust type, age, thickness, density, and lithology",
        "dependencies": ("plate_tectonics",),
        "required_outputs": {
            "cells": "nonempty_list",
            "plate_motion_history": "nonempty_list",
            "initial_oceanic_crust_age_model": "dict",
            "initial_oceanic_crust_age_ledger": "dict",
            "crust_material_shadow_model": "dict",
            "crust_material_shadow_history": "nonempty_list",
            "crust_dry_rock_accounting_model": "dict",
            "crust_dry_rock_accounting_history": "nonempty_list",
            "sediment_inventory_model": "dict",
        },
        "validator_domains": ("tectonics", "simulation"),
        "temporal_class": "native_nominal_maturation_intervals",
        "evidence_class": "initial_age_graph_witness_state_sparse_overlap_membership_shadow_and_finite_counter_accounting_replay",
    },
    {
        "id": "relief_bathymetry",
        "phase": 4,
        "name": "Relief, isostatic components, bathymetry, and landforms",
        "dependencies": ("crust_lithology",),
        "required_outputs": {
            "cells": "nonempty_list",
            "geology_realism_checks": "list",
            "landmasses": "list",
            "coastal_features": "list",
        },
        "validator_domains": ("tectonics", "coastal_marine_landmass"),
        "temporal_class": "native_evolved_then_diagnostic",
        "evidence_class": "partial_external_relief_calibration",
    },
    {
        "id": "sea_level_ocean",
        "phase": 5,
        "name": "Sea level, water bodies, shelves, and ocean circulation",
        "dependencies": ("relief_bathymetry",),
        "required_outputs": {
            "sea_level_model": "dict",
            "marine_regions": "list",
            "continental_shelves": "list",
            "ocean_current_systems": "list",
            "ocean_current_transport_edges": "list",
        },
        "validator_domains": (
            "sea_level",
            "ocean_circulation",
            "coastal_marine_landmass",
        ),
        "temporal_class": "native_equilibrium_recomputed_per_coupled_stage",
        "evidence_class": "volume_replay_with_diagnostic_circulation",
    },
    {
        "id": "climate_atmosphere",
        "phase": 6,
        "name": "Climate, energy, circulation, moisture, and classification",
        "dependencies": ("sea_level_ocean", "relief_bathymetry"),
        "required_outputs": {
            "climate_model": "dict",
            "climate_energy_balance_records": "nonempty_list",
            "climate_seasonal_histories": "nonempty_list",
            "climate_classification": "dict",
            "climate_continentality_regions": "list",
            "climate_realism_checks": "list",
        },
        "validator_domains": ("climate", "seasonal_climate"),
        "temporal_class": "equilibrium_climatology_not_transient_weather",
        "evidence_class": "formula_replay_and_partial_external_climatology",
    },
    {
        "id": "hydrology",
        "phase": 7,
        "name": "Water budget, drainage, rivers, lakes, and groundwater",
        "dependencies": ("climate_atmosphere", "relief_bathymetry"),
        "required_outputs": {
            "hydrologic_water_budget_model": "dict",
            "hydrologic_water_budget_history": "nonempty_list",
            "lake_basins": "list",
            "watersheds": "list",
            "river_channel_systems": "list",
            "groundwater_recharge_model": "dict",
            "groundwater_flow_model": "dict",
            "groundwater_flow_systems": "list",
            "hydrology_realism_checks": "list",
        },
        "validator_domains": (
            "hydrology",
            "lakes_watersheds",
            "river_evolution_channels",
            "aquifers_wetlands_karst",
        ),
        "temporal_class": "annual_diagnostic_budget_recomputed_per_coupled_stage",
        "evidence_class": "mass_balance_replay_and_partial_external_network_fit",
    },
    {
        "id": "erosion_sediment",
        "phase": 8,
        "name": "Erosion, hillslopes, fluvial routing, sediment, and stratigraphy",
        "dependencies": ("hydrology", "plate_tectonics"),
        "required_outputs": {
            "hillslope_sediment_transport_model": "dict",
            "hillslope_sediment_transport_history": "list",
            "fluvial_sediment_routing_model": "dict",
            "fluvial_sediment_routing_history": "list",
            "glacial_sediment_transport_model": "dict",
            "glacial_sediment_transport_history": "nonempty_list",
            "sediment_inventory_model": "dict",
            "sediment_interface_model": "dict",
            "sediment_transport_histories": "list",
            "sequence_stratigraphy_histories": "list",
            "river_reorganization_histories": "list",
        },
        "validator_domains": (
            "sediment",
            "simulation",
            "river_evolution_channels",
            "sequence_stratigraphy",
        ),
        "temporal_class": "native_nominal_transport_intervals_plus_diagnostic_reconstructions",
        "evidence_class": "canonical_bedrock_mobile_interface_and_bulk_volume_source_partition_replay_without_dry_rock_mass_or_physical_calibration",
    },
    {
        "id": "cryosphere",
        "phase": 9,
        "name": "Cryosphere, ice transport, permafrost, and glacial landforms",
        "dependencies": ("climate_atmosphere", "erosion_sediment"),
        "required_outputs": {
            "glacial_sediment_transport_model": "dict",
            "glacial_sediment_transport_history": "nonempty_list",
            "ice_sheets": "list",
            "ice_sheet_histories": "list",
            "ice_sheet_stability_histories": "list",
            "ice_flowline_histories": "list",
            "permafrost_regions": "list",
            "glacial_landform_systems": "list",
        },
        "validator_domains": ("cryosphere", "cryosphere_permafrost_glacial"),
        "temporal_class": "single_native_bulk_coupling_plus_diagnostic_histories",
        "evidence_class": "mass_replay_without_dynamic_ice_solver",
    },
    {
        "id": "soils_pedogenesis",
        "phase": 10,
        "name": "Soils, horizons, and pedogenesis diagnostics",
        "dependencies": ("erosion_sediment", "climate_atmosphere", "cryosphere"),
        "required_outputs": {
            "soil_pedogenesis_model": "dict",
            "soil_profiles": "list",
            "soil_horizons": "list",
            "soil_profile_histories": "list",
        },
        "validator_domains": ("soil_biome", "soils_and_ecotones"),
        "temporal_class": "posthoc_diagnostic_history",
        "evidence_class": "causal_source_links_without_pedogenic_process_calibration",
    },
    {
        "id": "biomes_ecosystems",
        "phase": 11,
        "name": "Biomes, ecotones, ecosystems, species, wetlands, reefs, and fire",
        "dependencies": ("soils_pedogenesis", "climate_atmosphere", "hydrology"),
        "required_outputs": {
            "biome_diagnostics": "nonempty_list",
            "biome_ecotone_regions": "list",
            "biome_realism_checks": "list",
            "vegetation_succession_histories": "list",
            "species_range_records": "list",
            "wetland_systems": "list",
            "reef_systems": "list",
            "wildfire_spread_histories": "list",
        },
        "validator_domains": (
            "soil_biome",
            "soils_and_ecotones",
            "ecosystems_reefs_species_wildfire",
        ),
        "temporal_class": "posthoc_diagnostic_trajectories",
        "evidence_class": "rule_replay_without_population_evolution",
    },
    {
        "id": "natural_resources",
        "phase": 12,
        "name": "Natural resources and geological formation evidence",
        "dependencies": (
            "crust_lithology",
            "erosion_sediment",
            "hydrology",
            "biomes_ecosystems",
        ),
        "required_outputs": {
            "resource_deposit_model": "dict",
            "resource_deposits": "list",
            "ore_genesis_model": "dict",
            "ore_genesis_systems": "list",
            "sedimentary_resource_systems": "list",
            "petroleum_migration_systems": "list",
            "commodity_occurrences": "list",
            "renewable_resource_records": "list",
        },
        "validator_domains": ("natural_resources", "geologic_resources"),
        "temporal_class": "posthoc_causal_diagnostic",
        "evidence_class": "source_link_replay_without_geochemical_solver",
    },
    {
        "id": "coupled_maturation",
        "phase": 13,
        "name": "Cross-layer coupled generation and maturation clock",
        "dependencies": (
            "plate_tectonics",
            "sea_level_ocean",
            "climate_atmosphere",
            "hydrology",
            "erosion_sediment",
            "cryosphere",
        ),
        "required_outputs": {
            "simulation_clock": "dict",
            "geo_evolution_provenance": "dict",
            "earth_system_feedback_history": "nonempty_list",
            "plate_motion_history": "nonempty_list",
            "hydrologic_water_budget_history": "nonempty_list",
            "glacial_sediment_transport_history": "nonempty_list",
        },
        "validator_domains": (
            "simulation",
            "tectonics",
            "hydrology",
            "sediment",
            "cryosphere",
            "evolution_provenance",
        ),
        "temporal_class": "reference_scaled_nominal_maturation_intervals_without_physical_time",
        "evidence_class": "cross_layer_replay_with_unproven_timestep_convergence_and_no_physical_calibration",
    },
)


def _output_matches_kind(value: Any, kind: str) -> bool:
    if kind == "dict":
        return isinstance(value, dict) and bool(value)
    if kind == "list":
        return isinstance(value, list)
    if kind == "nonempty_list":
        return isinstance(value, list) and bool(value)
    if kind == "nonempty_str":
        return isinstance(value, str) and bool(value.strip())
    raise ValueError(f"unknown geo layer output kind: {kind}")


def evaluate_geo_layer_contracts(
    world: Any,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Map detailed validation evidence onto every planned natural layer."""

    root = world if isinstance(world, dict) else {}
    normalized_checks = [check for check in checks if isinstance(check, dict)]
    geo_only = root.get("generation_scope") == "geo_only"
    layer_outcomes: dict[str, bool] = {}
    layers: list[dict[str, Any]] = []
    for contract in GEO_LAYER_CONTRACTS:
        required_outputs = dict(contract["required_outputs"])
        validator_domains = list(contract["validator_domains"])
        scope_specific_omissions: list[str] = []
        if contract["id"] == "coupled_maturation" and not geo_only:
            required_outputs.pop("geo_evolution_provenance", None)
            validator_domains = [
                domain
                for domain in validator_domains
                if domain != "evolution_provenance"
            ]
            scope_specific_omissions.extend(
                ["geo_evolution_provenance", "evolution_provenance"]
            )
        missing_outputs = [
            key
            for key, kind in required_outputs.items()
            if key not in root or not _output_matches_kind(root.get(key), kind)
        ]
        domains = set(validator_domains)
        evidence = [
            check for check in normalized_checks if str(check.get("domain", "")) in domains
        ]
        evidence_by_domain = {
            domain: [
                check
                for check in evidence
                if str(check.get("domain", "")) == domain
            ]
            for domain in validator_domains
        }
        missing_validation_domains = [
            domain for domain, domain_checks in evidence_by_domain.items()
            if not domain_checks
        ]
        fatal_failures = [
            check
            for check in evidence
            if check.get("status") == "failed" and check.get("severity") == "error"
        ]
        warnings = [
            check
            for check in evidence
            if check.get("status") == "failed" and check.get("severity") == "warning"
        ]
        not_applicable = [
            check for check in evidence if check.get("status") == "not_applicable"
        ]
        passed_evidence = [
            check for check in evidence if check.get("status") == "passed"
        ]
        failed_dependencies = [
            dependency
            for dependency in contract["dependencies"]
            if layer_outcomes.get(dependency) is not True
        ]
        contract_passed = (
            isinstance(world, dict)
            and not missing_outputs
            and not missing_validation_domains
            and not failed_dependencies
            and bool(passed_evidence)
            and not fatal_failures
        )
        layer_outcomes[str(contract["id"])] = contract_passed
        layers.append(
            {
                "id": contract["id"],
                "phase": contract["phase"],
                "name": contract["name"],
                "dependencies": list(contract["dependencies"]),
                "required_outputs": required_outputs,
                "scope_specific_omissions": scope_specific_omissions,
                "missing_or_invalid_outputs": missing_outputs,
                "validator_domains": validator_domains,
                "validation_domain_coverage": {
                    domain: len(domain_checks)
                    for domain, domain_checks in evidence_by_domain.items()
                },
                "missing_validation_domains": missing_validation_domains,
                "failed_dependencies": failed_dependencies,
                "validation_check_count": len(evidence),
                "validation_pass_count": len(passed_evidence),
                "validation_error_failure_count": len(fatal_failures),
                "validation_warning_count": len(warnings),
                "validation_not_applicable_count": len(not_applicable),
                "failed_check_names": [
                    f"{check.get('domain')}.{check.get('name')}"
                    for check in fatal_failures
                ],
                "contract_passed": contract_passed,
                "temporal_class": contract["temporal_class"],
                "evidence_class": contract["evidence_class"],
                "empirical_realism_proven": False,
            }
        )

    passed_count = sum(layer["contract_passed"] for layer in layers)
    return {
        "schema_version": LAYER_CONTRACT_SCHEMA_VERSION,
        "report_type": "geo_layer_contract_audit_v1",
        "scope": "natural generation and maturation layers only",
        "interpretation": (
            "A passing layer contract proves artifact, validator-domain, dependency, "
            "and assigned fatal-check integrity; it does not prove empirical realism "
            "or physical time calibration."
        ),
        "layer_count": len(layers),
        "passed_layer_count": passed_count,
        "failed_layer_count": len(layers) - passed_count,
        "all_layer_contracts_passed": passed_count == len(layers),
        "layers": layers,
    }


__all__ = [
    "GEO_LAYER_CONTRACTS",
    "LAYER_CONTRACT_SCHEMA_VERSION",
    "evaluate_geo_layer_contracts",
]
