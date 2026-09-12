"""Cheap upstream climate contracts for model-aware ecology consumers.

Matching declarations establish which already-validated producer is required;
they are not proof of numerical correctness. The native annual energy enricher
owns the independent whole-budget audit before publishing its exact metadata.
"""
from __future__ import annotations

from typing import Any

from .native_climate_energy import ENRICHMENT_MODEL


def ecology_uses_native_seasonal_climate(world: dict[str, Any]) -> bool:
    """Select known native/legacy inputs, rejecting partial explicit models."""
    climate = world.get("climate_model")
    energy = world.get("climate_energy_model")
    native_sections = (
        "climate_energy_forcing_intervals", "climate_energy_transport_edges",
        "native_climate_energy_enrichment_model",
    )
    native = any(key in world for key in native_sections)
    for declaration in (climate, energy):
        if isinstance(declaration, dict):
            native |= (
                declaration.get("native_temperature_forcing_coupled") is True
                or declaration.get("ownership") == "native_temperature_producer"
                or declaration.get("temperature_source") == "climate_energy_balance_records_monthly_mean_temperature_k"
                or any(isinstance(declaration.get(key), str) and declaration[key].startswith((
                    "native_prescribed_seasonal_energy_", "prescribed_seasonal_surface_energy_",
                    "periodic_graybody_storage_conservative_transport_",
                )) for key in ("model", "model_type", "temperature_model"))
            )
    if not native:
        for key, model, field, expected in (
            ("climate_model", climate, "model_type", "equilibrium_latitude_circulation_climate_v5"),
            ("climate_energy_model", energy, "albedo_greenhouse_model", "posthoc_empirical_graybody_surface_diagnostic_v2"),
        ):
            if key in world and (not isinstance(model, dict) or model.get(field) != expected):
                raise ValueError(f"ecology requires a known legacy or native seasonal {key}")
        if isinstance(energy, dict) and "model" in energy:
            raise ValueError("ecology rejects an unknown or mixed climate_energy_model identity")
        return False

    for key, model, required in (
        ("climate_model", climate, {
            "model_type": "prescribed_seasonal_surface_energy_v1",
            "temperature_model": "periodic_graybody_storage_conservative_transport_v1",
            "temperature_source": "climate_energy_balance_records_monthly_mean_temperature_k",
            "native_temperature_forcing_coupled": True,
            "imposed_mean_temperature": False,
            "post_solve_temperature_adjustments": False,
        }),
        ("climate_energy_model", energy, {
            "model": "native_prescribed_seasonal_energy_v1",
            "budget_schema_version": 1,
            "ownership": "native_temperature_producer",
            "native_temperature_forcing_coupled": True,
        }),
    ):
        if not isinstance(model, dict) or any(type(model.get(field)) is not type(value) or model[field] != value for field, value in required.items()):
            raise ValueError(f"native seasonal ecology requires the supported {key} identity")
    if world.get("native_climate_energy_enrichment_model") != ENRICHMENT_MODEL:
        raise ValueError("native seasonal ecology requires exact upstream native climate energy enrichment metadata")
    for key in ("cells", "climate_energy_balance_records", "climate_energy_forcing_intervals"):
        records = world.get(key)
        if not isinstance(records, list) or not records or any(not isinstance(record, dict) for record in records):
            raise ValueError(f"native seasonal ecology requires retained {key}")
    if not isinstance(world.get("climate_energy_transport_edges"), list):
        raise ValueError("native seasonal ecology requires retained climate_energy_transport_edges")
    if len(world["cells"]) != len(world["climate_energy_balance_records"]):
        raise ValueError("native seasonal ecology requires full upstream native cell coverage")
    return True
