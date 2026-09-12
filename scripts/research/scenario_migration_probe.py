"""Bounded shipped-scenario migration probe; run from the repository root.

Generates real seasonal V4 worlds, then applies the public Python geo pipeline
to that same raw state. It does not fit coefficients or relax validation gates.
Outputs under runs are disposable; no cached input is required.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
import gzip
import json
import math
from pathlib import Path
import time
import traceback
from unittest.mock import patch

import yaml
from magic_geo import api, native
from magic_geo.seasonal_config import SeasonalWorldConfig
from magic_geo.geo_validation import validate_geo_world
from magic_geo.native_climate_energy_validation import audit_native_climate_energy

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, default=Path("runs/seasonal-scenario-migration"))
parser.add_argument("--only", nargs="+", help="Scenario stems, or default_seed_128_iteration_1; omitted runs all eleven.")
parser.add_argument("--compare-legacy", action="store_true", help="Also generate V3 at the same resolution using the explicitly retired Celsius controls.")
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
# Historical controls are comparison inputs, never a conversion to optical depth.
retired_controls = {
    "earthlike_seed": (15.0, 6.5), "continental_realm": (14.0, 6.5),
    "cryogenic_slushball": (-10.0, 6.5), "glasswind_desert": (32.0, 7.5),
    "ironroot_super_earth": (14.0, 6.0), "oldstone_stagnant": (8.0, 6.5),
    "pelagic_archipelago": (18.0, 6.0), "solstice_extreme": (12.0, 6.5),
    "verdant_hothouse": (30.0, 5.5), "young_volcanic": (32.0, 7.0),
}
paths = [Path("configs/earthlike_seed.yaml"), *sorted(Path("configs/seeds").glob("*.yaml"))]
cases = [(path.stem, str(path), yaml.safe_load(path.read_text()), 0) for path in paths]
cases.append(("default_seed_128_iteration_1", None, SeasonalWorldConfig(config_version=2).model_dump(), 1))

def save(name, value):
    (args.output / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")

def zipped(name, value):
    (args.output / name).write_bytes(gzip.compress(json.dumps(value, separators=(",", ":"), allow_nan=False).encode(), mtime=0))

def temperatures(world):
    cells = world["cells"]
    area = math.fsum(c["area_km2"] for c in cells)
    return {
        "area_mean_annual_temperature_c": math.fsum(c["area_km2"] * c["temperature_c"] for c in cells) / area,
        "minimum_annual_temperature_c": min(c["temperature_c"] for c in cells),
        "maximum_annual_temperature_c": max(c["temperature_c"] for c in cells),
        "minimum_monthly_temperature_c": min(min(c["temperature_monthly_c"]) for c in cells),
        "maximum_monthly_temperature_c": max(max(c["temperature_monthly_c"]) for c in cells),
    }

unknown = set(args.only or ()) - {case[0] for case in cases}
if unknown:
    parser.error("unknown scenarios: " + ", ".join(sorted(unknown)))

for name, source, data, iterations in cases:
    if args.only and name not in args.only:
        continue
    data = deepcopy(data)
    data["mesh"]["cell_count"] = 128
    data["erosion"]["iterations"] = iterations
    result = {"name": name, "source": source, "requested_config": data,
              "probe_scope": "genuine V4 raw native generation then same-state public geo enrichment; no second native solve",
              "started_unix_seconds": time.time()}
    save(name + ".config.json", data)
    print(json.dumps({"event": "start", "name": name, "mesh": data["mesh"], "compute": data["compute"]}), flush=True)
    started = time.monotonic()
    phase = "config"
    try:
        cfg = SeasonalWorldConfig.model_validate(data, strict=True)
        phase = "native_v4"
        world = native.generate_seasonal_geo_world(cfg)
        result["native_seconds"] = time.monotonic() - started
        result["actual_cell_count"] = len(world["cells"])
        result["temperatures"] = temperatures(world)
        result["achieved"] = deepcopy(world["climate_energy_model"]["achieved"])
        zipped(name + ".native.json.gz", world)
        phase = "independent_budget"
        result["energy_audit"] = audit_native_climate_energy(world)
        phase = "public_geo_enrichment"
        enriched_start = time.monotonic()
        with patch("magic_geo.native.generate_seasonal_geo_world", return_value=world):
            world = api.generate_geo_world(cfg)
        result["enrichment_seconds"] = time.monotonic() - enriched_start
        zipped(name + ".world.json.gz", world)
        phase = "generic_validation"
        report = validate_geo_world(world, profile="generic")
        zipped(name + ".validation.json.gz", report)
        result["generic_passed"] = report["passed"]
        result["generic_summary"] = report["summary"]
        result["metrics"] = report["metrics"]
        result["generic_failures"] = [{k: c.get(k) for k in ("name", "domain", "severity", "message", "observed", "expected")}
                                      for c in report["checks"] if c["status"] == "failed"]
        phase = "legacy_pair"
        if source and args.compare_legacy:
            baseline = deepcopy(data)
            baseline.pop("config_version")
            baseline["climate"].pop("reference_infrared_optical_depth")
            baseline["climate"]["base_temperature_c"], baseline["climate"]["lapse_rate_c_per_km"] = retired_controls[name]
            baseline["mesh"]["cell_count"] = 128
            baseline["erosion"]["iterations"] = iterations
            old = native.generate_geo_world(baseline)
            result["paired_legacy_temperatures"] = temperatures(old)
            result["removed_controls"] = {k: baseline["climate"][k] for k in ("base_temperature_c", "lapse_rate_c_per_km")}
        result["completed"] = True
    except Exception as error:
        result["completed"] = False
        result["failure_phase"] = phase
        result["error"] = str(error)
        result["exception_type"] = type(error).__name__
        result["traceback"] = traceback.format_exc()
    result["total_seconds"] = time.monotonic() - started
    save(name + ".result.json", result)
    print(json.dumps({"event": "finish", "name": name, "completed": result["completed"], "seconds": result["total_seconds"],
                      "generic_passed": result.get("generic_passed"), "temperatures": result.get("temperatures"),
                      "failure_phase": result.get("failure_phase"), "error": result.get("error")}), flush=True)
