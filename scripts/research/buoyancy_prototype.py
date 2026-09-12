#!/usr/bin/env python3
"""Reproduce the offline initial-buoyancy audit without changing generation.

The physical formulas below match the original temporary prototype. Native
generation is imported only when a selected case has no cached input. Analytic
checks and cached replay need only the Python standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_ROOT = REPO_ROOT / "runs"
EARTHLIKE_CONFIG = REPO_ROOT / "configs" / "earthlike_seed.yaml"
CASES = {
    "canonical_424242_4096": (424242, 4096),
    "heldout_42_512": (42, 512),
    "heldout_42_4096": (42, 4096),
}
ORIGINAL_EVIDENCE = {
    "temporary_prototype_sha256": "e01e6b980e92cac37b259e35fec188fb4a6fc0b820ecc52c4a32f37f3325c793",
    "native_library_sha256": "b3c113c599eab3c73bacd0c4849d6bfe79e2c01ffbdc837c18e26b9843bddd30",
    "earthlike_config_sha256": "47ea1f846439ae8dd00b09fb5a687532f7c49150f2c83a50c7f56a44c76875c6",
}
RHO_M = 3.3  # g/cm3, conventional homogeneous-mantle Airy approximation
RHO_W = 1.03
LOAD_FACTOR = RHO_M / (RHO_M - RHO_W)
INVENTORY = 1338000000.0  # km3; configured inventory, never area fitting


def connected_ocean(z, area, neighbors, volume):
    """Exact flood-interval solve matching native ocean.cpp; z is metres."""
    n = len(z)
    order = sorted(range(n), key=lambda i: (z[i], i))
    parent = list(range(n))
    size = [1] * n
    ca = area.copy()
    za = [z[i] * area[i] for i in range(n)]
    minid = list(range(n))
    active = [False] * n
    largest = -1
    best = (math.inf, math.inf, 0.0)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def merge(i, j):
        a, b = find(i), find(j)
        if a == b:
            return
        if size[a] < size[b] or (size[a] == size[b] and b < a):
            a, b = b, a
        parent[b] = a
        size[a] += size[b]
        ca[a] += ca[b]
        za[a] += za[b]
        minid[a] = min(minid[a], minid[b])

    pos = 0
    while pos < n:
        height = z[order[pos]]
        end = pos
        while end < n and z[order[end]] == height:
            active[order[end]] = True
            end += 1
        for i in order[pos:end]:
            for j in neighbors[i]:
                if active[j]:
                    merge(i, j)
        if largest >= 0:
            largest = find(largest)
        for i in order[pos:end]:
            root = find(i)
            if largest < 0 or (ca[root], -minid[root]) > (ca[largest], -minid[largest]):
                largest = root
        lo = math.nextafter(height, math.inf)
        nextz = z[order[end]] if end < n else math.inf
        solved = (volume * 1000 + za[largest]) / ca[largest]
        candidates = [lo]
        exact = lo <= solved < nextz
        if exact:
            candidates.append(solved)
        elif math.isfinite(nextz):
            hi = math.nextafter(nextz, height)
            if hi >= lo:
                candidates.append(hi)
        for level in candidates:
            computed = (ca[largest] * level - za[largest]) / 1000
            candidate = (abs(computed - volume), level, height)
            if candidate < best:
                best = candidate
        pos = end
        if exact:
            break

    error, sea, threshold = best
    below = {i for i, height in enumerate(z) if height <= threshold}
    components = []
    while below:
        start = min(below)
        below.remove(start)
        todo = [start]
        component = [start]
        while todo:
            i = todo.pop()
            for j in neighbors[i]:
                if j in below:
                    below.remove(j)
                    todo.append(j)
                    component.append(j)
        components.append(component)
    marine = set(max(components, key=lambda c: (sum(area[i] for i in c), -min(c))))
    return sea, marine, error


def stats(z, area, neighbors, continental, *, water_load=False):
    factor = LOAD_FACTOR if water_load else 1.0
    sea, marine, error = connected_ocean(z, area, neighbors, INVENTORY / factor)
    e = [(height - sea) * (factor if i in marine else 1.0) for i, height in enumerate(z)]
    total = sum(area)
    positive = [i for i, h in enumerate(e) if h >= 0]
    cont_area = sum(area[i] for i in range(len(z)) if continental[i])
    submerged = sum(area[i] for i in marine if continental[i])
    actual_volume = sum(-e[i] * area[i] / 1000 for i in marine)
    return {
        'sea_datum_m': sea,
        'ocean_area_fraction': sum(area[i] for i in marine) / total,
        'below_datum_cell_fraction': sum(h < 0 for h in e) / len(e),
        'nonnegative_mean_m': sum(e[i] for i in positive) / len(positive),
        'nonnegative_area_mean_m': sum(e[i] * area[i] for i in positive) / sum(area[i] for i in positive),
        'min_m': min(e), 'max_m': max(e), 'span_m': max(e) - min(e),
        'continental_area_fraction': cont_area / total,
        'submerged_continental_global_area_fraction': submerged / total,
        'submerged_fraction_of_continental_area': submerged / cont_area,
        'volume_km3': actual_volume,
        'volume_residual_km3': actual_volume - INVENTORY,
        'solver_residual_km3': error * factor,
        'inventory_admissible': abs(actual_volume - INVENTORY) <= INVENTORY * 1e-10,
    }


def evaluate(data, label):
    cells = data['cells']
    history = data['plate_motion_history']
    area = [c['area_km2'] for c in cells]
    neighbors = [c['neighbors'] for c in cells]
    initial_type = history[0]['crust_type_by_cell']
    initial_cont = [t not in (0, 2, 3) for t in initial_type]
    thick = [c['crust_thickness_km'] - sum(h['crust_thickness_change_km_by_cell'][i] for h in history[1:]) for i, c in enumerate(cells)]
    density = [c['crust_density'] - sum(h['crust_density_change_by_cell'][i] for h in history[1:]) for i, c in enumerate(cells)]
    initial = [c['initial_elevation_m'] for c in cells]
    final = [c['elevation_m'] for c in cells]
    final_cont = [not (c['crust_type'] == 'oceanic' or (c['crust_type'] == 'transitional' and c['lithology'] == 'basalt') or (c['crust_type'] == 'volcanic_arc' and c['crust_age_ma'] <= 320 and c['crust_thickness_km'] <= 18 and c['crust_density'] >= 2.84)) for c in cells]
    # Hold the existing 500 m, 30 km, 2.72 g/cm3 reference fixed. Only replace
    # the thickness/density response with the column mass balance.
    airy = [500 + 1000 * ((RHO_M - density[i]) * thick[i] - (RHO_M - 2.72) * 30) / RHO_M for i in range(len(cells))]
    no_orogen = [initial[i] - (c['initial_orogenic_uplift_m'] if initial_cont[i] else 0) for i, c in enumerate(cells)]
    replaced = [initial[i] - c['initial_isostatic_elevation_m'] + airy[i] if initial_cont[i] else initial[i] for i, c in enumerate(cells)]
    replaced_no_orogen = [replaced[i] - (c['initial_orogenic_uplift_m'] if initial_cont[i] else 0) for i, c in enumerate(cells)]
    # Oceanic age-depth targets are already water-loaded at sea datum zero.
    # Convert to unloaded equivalent before solving water load + inventory.
    def reduced(values):
        return [v if initial_cont[i] else v / LOAD_FACTOR for i, v in enumerate(values)]

    results = {}
    for name, z, continental, loaded in (
        ('native_initial_raw', initial, initial_cont, False),
        ('native_mature', final, final_cont, False),
        ('initial_remove_continental_orogen_only', no_orogen, initial_cont, False),
        ('initial_airy_retain_orogen_rigid_water', replaced, initial_cont, False),
        ('initial_airy_remove_orogen_rigid_water', replaced_no_orogen, initial_cont, False),
        ('initial_airy_remove_orogen_loaded_water', reduced(replaced_no_orogen), initial_cont, True),
    ):
        results[name] = stats(z, area, neighbors, continental, water_load=loaded)
    # Identify the existing transitional-basalt outside-mask ring without
    # pretending its present oceanic material is a stretched continent.
    margins = [i for i, t in enumerate(initial_type) if t == 2]
    metadata = {
        'initial_crust_volume_km3': sum(a * t for a, t in zip(area, thick)),
        'initial_continental_volume_km3': sum(area[i] * thick[i] for i, c in enumerate(initial_cont) if c),
        'initial_continental_thickness_area_mean_km': sum(area[i] * thick[i] for i, c in enumerate(initial_cont) if c) / sum(area[i] for i, c in enumerate(initial_cont) if c),
        'initial_margin_label_area_fraction': sum(area[i] for i in margins) / sum(area),
        'initial_margin_label_thickness_area_mean_km': sum(area[i] * thick[i] for i in margins) / sum(area[i] for i in margins),
        'initial_margin_label_density_area_mean_g_cm3': sum(area[i] * density[i] for i in margins) / sum(area[i] for i in margins),
        'continental_plus_margin_label_area_fraction': sum(area[i] for i in range(len(cells)) if initial_cont[i] or i in margins) / sum(area),
        'extra_crust_volume_if_margin_label_thickened_to_26_km': sum(area[i] * (26.0 - thick[i]) for i in margins),
        'min_initial_thickness_km': min(thick),
        'max_initial_thickness_km': max(thick),
        'prototype_crust_volume_delta_km3': 0.0,
        'prototype_crust_density_moment_delta': 0.0,
    }
    return {'world': label, 'metadata': metadata, 'results': results}


def self_checks():
    # A fully connected two-cell ocean has an analytic common-water surface.
    sea, marine, error = connected_ocean([-2000., -1000.], [2., 3.], [[1], [0]], 10.)
    assert abs(sea - 600.) < 1e-10 and marine == {0, 1} and error < 1e-12
    # Dry/wet column pressure balance, including emergence continuity.
    for thickness, density in ((20_000., 2.75), (30_000., 2.72), (40_000., 2.78)):
        y = 500 + ((RHO_M - density) * thickness - (RHO_M - 2.72) * 30_000.) / RHO_M
        for sea in (y - 1., y, y + 1., y + 3000.):
            surface = y if y >= sea else (RHO_M * y - RHO_W * sea) / (RHO_M - RHO_W)
            reference_mass = RHO_M * 100_000. + RHO_M * 500. - (RHO_M - 2.72) * 30_000.
            column_mass = (density * thickness + RHO_M * (100_000. + surface - thickness)
                           + RHO_W * max(0., sea - surface))
            assert abs(column_mass - reference_mass) < 1e-8
    return {'connected_ocean_closed_form': 'passed', 'dry_wet_column_mass_balance': 'passed', 'emergence_continuity': 'passed'}


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate_input(case: str) -> dict:
    # Keep generation behind the research entry point; production imports and
    # API wiring are unchanged, and --analytic-only never loads the library.
    from magic_geo.config import config_to_native, load_config
    from magic_geo.native import _library_path, generate_geo_world

    seed, count = CASES[case]
    config = config_to_native(load_config(EARTHLIKE_CONFIG))
    config["compute"].update(threads=1, backend="cpu")
    config["output"]["float_precision"] = 8
    config["run"]["seed"] = seed
    config["mesh"]["cell_count"] = count
    if config["planet"]["ocean_water_inventory_km3"] != INVENTORY:
        raise ValueError("the fixed research model requires the original ocean inventory")
    world = generate_geo_world(config)
    return {
        "cells": world["cells"],
        "plate_motion_history": world["plate_motion_history"],
        "feedback": world["earth_system_feedback_history"],
        "research_provenance": {
            "case": case,
            "native_config": config,
            "native_library_sha256": file_digest(_library_path()),
            "earthlike_config_sha256": file_digest(EARTHLIKE_CONFIG),
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir", type=Path,
        default=RUNS_ROOT / "research" / "buoyancy" / "cache",
        help="native input cache directory inside the repository's ignored runs/ tree",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=RUNS_ROOT / "research" / "buoyancy",
        help="results and provenance directory inside the ignored runs/ tree",
    )
    parser.add_argument(
        "--case", dest="cases", action="append", choices=CASES,
        help="evaluate this case; repeat to select several (default: all three)",
    )
    parser.add_argument(
        "--analytic-only", action="store_true",
        help="run column and ocean analytic checks only; no native imports or files written",
    )
    parser.add_argument(
        "--cache-only", action="store_true",
        help="refuse native generation if a selected input cache is missing",
    )
    args = parser.parse_args(argv)
    for name in ("cache_dir", "output_dir"):
        path = getattr(args, name).resolve()
        if not path.is_relative_to(RUNS_ROOT.resolve()):
            parser.error(f"--{name.replace('_', '-')} must be inside {RUNS_ROOT}")
        setattr(args, name, path)
    args.cases = list(dict.fromkeys(args.cases or CASES))
    if args.cache_only and not args.analytic_only:
        for case in args.cases:
            path = args.cache_dir / f"{case}.json"
            if not path.is_file():
                parser.error(f"--cache-only input is missing: {path}")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    checks = self_checks()
    print(json.dumps({"self_checks": checks}), flush=True)
    if args.analytic_only:
        return 0

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    results = []
    inputs = []
    for case in args.cases:
        path = args.cache_dir / f"{case}.json"
        generated = not path.exists()
        if generated:
            started = time.monotonic()
            data = generate_input(case)
            path.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
            print(json.dumps({"generated": case, "seconds": time.monotonic() - started}), flush=True)
        else:
            data = json.loads(path.read_text(encoding="utf-8"))
        if len(data["cells"]) != CASES[case][1]:
            raise ValueError(f"input cell count does not match case {case}: {path}")
        provenance = data.get("research_provenance")
        if provenance is not None and provenance.get("case") != case:
            raise ValueError(f"cached provenance does not match case {case}: {path}")
        result = evaluate(data, case)
        results.append(result)
        inputs.append({
            "case": case, "path": str(path), "sha256": file_digest(path),
            "generated": generated,
            "generator_provenance": provenance or {"status": "unrecorded_legacy_cache"},
        })
        rejected = [name for name, row in result["results"].items() if not row["inventory_admissible"]]
        print(json.dumps({"evaluated": case, "rejected_inventory_variants": rejected}), flush=True)

    results_path = args.output_dir / "buoyancy_prototype_results.json"
    results_path.write_text(json.dumps(results, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    manifest = {
        "model": "offline_initial_buoyancy_prototype_v1",
        "script_sha256": file_digest(Path(__file__)),
        "original_evidence": ORIGINAL_EVIDENCE,
        "physical_constants": {"mantle_density_g_cm3": RHO_M, "water_density_g_cm3": RHO_W, "ocean_inventory_km3": INVENTORY},
        "self_checks": checks,
        "inputs": inputs,
        "results_sha256": file_digest(results_path),
    }
    manifest_path = args.output_dir / "buoyancy_prototype_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"results": str(results_path), "manifest": str(manifest_path)}), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
