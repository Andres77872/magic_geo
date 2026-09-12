"""Portable native social-stage units, with explicit synthetic annual context.

The attached climate declaration template supports annual-input/selection unit
replay only. These worlds do not supply a valid full climate energy certificate.
No native library, climate integration or full generator is called.
"""
from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1] / "fixtures"


def _read_units():
    base = ROOT / "native_social_availability"
    manifest = json.loads((base / "manifest.json").read_text())
    raw = (base / manifest["fixture"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == manifest["gzip_sha256"]
    data = gzip.decompress(raw)
    assert hashlib.sha256(data).hexdigest() == manifest["sha256"]
    return json.loads(data)


def _annual_template():
    base = ROOT / "settlement_climate_support"
    entry = json.loads((base / "manifest.json").read_text())["earthlike_seed"]
    raw = (base / entry["fixture"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == entry["gzip_sha256"]
    data = gzip.decompress(raw)
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    return json.loads(data)["seasonal_supported_selection"]


def native_social_unit_world(name):
    return deepcopy(_read_units()[name])


def environment_social_world(name="healthy"):
    from magic_geo.settlement_routes import enrich_world_with_settlement_route_models
    from magic_geo.political_geography import enrich_world_with_political_geography_models

    if name not in {"healthy", "mixed"}:
        raise ValueError("environment-derived unit name required")
    world = native_social_unit_world("environment_stage_" + name)
    source = _annual_template()
    for key in ("climate_model", "climate_energy_model", "climate_energy_forcing_intervals",
                "climate_energy_transport_edges", "native_climate_energy_enrichment_model"):
        world[key] = deepcopy(source[key])
    world["climate_energy_balance_records"] = [
        {"cell_id": c["id"], "monthly_mean_temperature_k": [c["settlement_climate_temperature_c"] + 273.15] * 12}
        for c in world["cells"]
    ]
    enrich_world_with_settlement_route_models(world)
    enrich_world_with_political_geography_models(world)
    return world


def annotated_environment_social_world(name="healthy"):
    from magic_geo.cultural_geography import enrich_world_with_cultural_geography_models
    from magic_geo.historical_geography import enrich_world_with_historical_geography_model
    from magic_geo.civilization_geography import enrich_world_with_civilization_geography_models
    from magic_geo.territorial_geography import enrich_world_with_territorial_geography_model

    world = environment_social_world(name)
    for annotate in (enrich_world_with_cultural_geography_models,
                     enrich_world_with_historical_geography_model,
                     enrich_world_with_civilization_geography_models,
                     enrich_world_with_territorial_geography_model):
        annotate(world)
    return world
