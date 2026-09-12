#!/usr/bin/env python3
"""Read-only exact-rational audit of new layered topology JSONL receipts.

No native import, world generation, source mutation, or subprocess execution.
The model is conditional on canonical binary64 W, as declared by the producer.
"""
from __future__ import annotations

import argparse
import copy
from fractions import Fraction as F
import json
import math
from pathlib import Path
import layered_topology_geometry as geometry

COUNT = 0
ACCEPTED = 0


def require(ok, message):
    global COUNT
    COUNT += 1
    if not ok:
        raise AssertionError(message)


def frac(x):
    require(type(x) in (int, float) and math.isfinite(x), "finite scalar")
    require(F(x) == F(float(x)), "canonical binary64 numeric operand")
    return F(x)


def contains(box, x):
    lo, hi = frac(box["lower"]), frac(box["upper"])
    require(lo <= x <= hi, f"enclosure misses {x}: {box}")


def same(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def audit_geometry(graph):
    # JSON permits integer-looking doubles. Reproduce binary64 candidate
    # arithmetic in the reused geometry reader, rather than Python bigint
    # products, while keeping indices and limits integral.
    g = copy.deepcopy(graph)
    source = g["input"]
    source["water"] = {k: float(frac(v)) for k, v in source["water"].items()}
    for c in source["columns"]:
        for k in ("area_m2", "top_nonwater_heat_capacity_j_m2_k", "top_longwave_emissivity", "top_absorbed_shortwave_w_m2"):
            c[k] = float(frac(c[k]))
        for l in c["layers"]:
            for k in ("water_mass_kg_m2", "enthalpy_j_m2", "density_kg_m3", "conductivity_w_m_k"):
                l[k] = float(frac(l[k]))
        if c["deep_inventory"] is not None:
            c["deep_inventory"] = {k: float(frac(v)) for k, v in c["deep_inventory"].items()}
    geometry.audit(g)


def key(cell, loc):
    require((loc["deep"] and loc["layer_id"] == -1) or
            (not loc["deep"] and loc["layer_id"] >= 0), "canonical location")
    return cell, loc["layer_id"]


def stores(source):
    result = {}
    for c in source["columns"]:
        for l in c["layers"]:
            result[c["cell_id"], l["layer_id"]] = (
                frac(c["area_m2"]), frac(l["water_mass_kg_m2"]), frac(l["enthalpy_j_m2"]),
                frac(c["top_nonwater_heat_capacity_j_m2_k"]) if l["layer_id"] == 0 else F(0))
        if c["deep_inventory"] is not None:
            d = c["deep_inventory"]
            result[c["cell_id"], -1] = frac(c["area_m2"]), frac(d["water_mass_kg_m2"]), frac(d["enthalpy_j_m2"]), F(0)
    return result


def finite_tree(value):
    if isinstance(value, dict):
        require("nonfinite_binary64_bits" not in value, "accepted finite numeric diagnostics")
        for v in value.values():
            finite_tree(v)
    elif isinstance(value, list):
        for v in value:
            finite_tree(v)
    elif isinstance(value, float):
        require(math.isfinite(value), "accepted finite scalar")


def audit_domains(records, source, E, *, owner=False):
    expected = stores(source)
    if owner:
        expected = {k: v for k, v in expected.items() if k[1] >= 0 or v[1] > 0}
    require(len(records) == len(expected), "complete physical domain records")
    seen = set()
    for d in records:
        k = d["address"]["cell_id"], d["address"]["layer_id"]
        require(k in expected and k not in seen, "unique bound domain coordinate")
        seen.add(k)
        A, W, H, C = expected[k]
        if not owner:
            require((frac(d["area_m2"]), frac(d["water_mass_kg_m2"]), frac(d["enthalpy_j_m2"]),
                     frac(d["nonwater_capacity_j_m2_k"]), frac(d["global_energy_error_j"])) == (A, W, H, C, E), "domain operands")
            require(d["proved"] and d["constrained_empty_deep"] == (k[1] == -1 and W == 0), "domain structural-zero scope")
        if k[1] == -1 and W == 0:
            require(H == 0, "empty deep domain")
            continue
        box = d["enthalpy_box_j_m2" if owner else "enthalpy_ball_j_m2"]
        floor = -(C+W*frac(source["water"]["solid_heat_capacity_j_kg_k"]))*frac(source["water"]["freezing_temperature_k"])
        contains(box, H-E/A); contains(box, H+E/A); contains(d["physical_floor_j_m2"], floor)
        require(box["lower"] >= d["physical_floor_j_m2"]["upper"], "conservative domain proof")


def decompose(W, H, C, water):
    if W == 0:
        return F(0), H
    ci, cl, L = (frac(water[k]) for k in
                  ("solid_heat_capacity_j_kg_k", "liquid_heat_capacity_j_kg_k", "latent_heat_j_kg"))
    qw = W*ci/(C+W*ci)*min(H, 0) + min(max(H, 0), W*L) + W*cl/(C+W*cl)*max(H-W*L, 0)
    return qw, H-qw


def physical(source, E):
    ci, Tf = frac(source["water"]["solid_heat_capacity_j_kg_k"]), frac(source["water"]["freezing_temperature_k"])
    for (cell, layer), (A, W, H, C) in stores(source).items():
        if layer == -1 and W == 0:
            require(H == 0, "empty deep constrained energy")
        else:
            require(W >= 0 and (W > 0 or C > 0), "positive storage")
            require(H-E/A >= -(C+W*ci)*Tf, "full energy ball physical floor")


def upper_add(a, b):
    if a == 0:
        return b
    if b == 0:
        return a
    return math.nextafter(a+b, math.inf)


def audit(r):
    global ACCEPTED
    require(r["model"] == "fixed_canonical_whole_donor_export_and_homogeneous_topology_v1", "topology model")
    require(r["ordinary_generation_changed"] is False and r["original_mass_trajectory_certified"] is False,
            "scope declarations")
    if r["source_graph"] is not None:
        audit_geometry(r["source_graph"])
        require(same(r["source_graph"]["input"], r["request"]["source"]), "source graph binding")
    if not r["accepted"]:
        require(r["final"] is None and bool(r["failure_code"]), "refused component publishes no final")
        for c in r["export_certificates"]:
            A, W = frac(c["source_area_m2"]), frac(c["source_water_mass_kg_m2"])
            contains(c["exact_full_mass_kg"], A*W)
            if c["exact_mass_representable"]:
                require(frac(c["represented_full_mass_kg"]) == A*W, "refusal prefix exact mass")
        if r["failure_code"] == "physical_domain_refusal" and r["final_domain"]:
            require(any(not d["proved"] for d in r["final_domain"]), "final-domain failed coordinate retained")
            water = r["request"]["source"]["water"]
            for d in r["final_domain"]:
                A, W, H, C, E = (frac(d[k]) for k in ("area_m2", "water_mass_kg_m2", "enthalpy_j_m2",
                                                     "nonwater_capacity_j_m2_k", "global_energy_error_j"))
                if not d["constrained_empty_deep"]:
                    contains(d["enthalpy_ball_j_m2"], H-E/A)
                    contains(d["physical_floor_j_m2"], -(C+W*frac(water["solid_heat_capacity_j_kg_k"]))*frac(water["freezing_temperature_k"]))
                    require(d["proved"] == (d["enthalpy_ball_j_m2"]["lower"] >= d["physical_floor_j_m2"]["upper"]),
                            "retained final-domain predicate")
        return False
    q, final = r["request"], r["final"]
    finite_tree(r)
    source = q["source"]
    require(same(r["source_graph"]["input"], source), "source graph binding")
    S = stores(source)
    E = frac(q["inherited_global_energy_error_j"])
    require(0 <= E <= frac(q["maximum_final_energy_error_j"]), "finite nonnegative energy allowance")
    require(all(frac(x) > 0 for x in source["water"].values()) and all(frac(c["area_m2"]) > 0 for c in source["columns"]),
            "positive material properties and areas")
    physical(source, E)
    audit_domains(r["source_domain"], source, E)
    positive = {k for k, (_, W, _, _) in S.items() if W > 0}
    D = {key(d["cell_id"], d["source"]): d for d in q["donors"]}
    X = {(e["donor"]["cell_id"], e["donor"]["layer_id"]): e for e in q["exports"]}
    require(len(D) == len(q["donors"]) and len(X) == len(q["exports"]), "unique source rows")
    require(set(D).isdisjoint(X) and set(D) | set(X) == positive, "complete exclusive water ownership")
    require(len({e["id"] for e in X.values()}) == len(X), "unique event IDs")
    ideal = {}
    for c in q["targets"]:
        for l in c["layers"]:
            ideal[c["cell_id"], l["layer_id"]] = [F(0), F(0)]
        if c["deep_density_kg_m3"] is not None:
            ideal[c["cell_id"], -1] = [F(0), F(0)]
    split = {k: decompose(W, H, C, source["water"]) for k, (_, W, H, C) in S.items()}
    decompositions = {key(d["cell_id"], d["source"]): d for d in r["decompositions"]}
    require(set(decompositions) == set(S) and len(decompositions) == len(r["decompositions"]), "complete decomposition")
    for k, d in decompositions.items():
        A, W, H, C = S[k]
        require((frac(d["initial_water_mass_kg_m2"]), frac(d["initial_complete_enthalpy_j_m2"]),
                 frac(d["nonwater_capacity_j_m2_k"])) == (W, H, C), "decomposition source operands")
        qw, qc = split[k]
        contains(d["ideal_water_enthalpy_j_m2"], qw)
        contains(d["ideal_stationary_nonwater_enthalpy_j_m2"], qc)
        if k[1] == 0:
            ideal[k[0], 0][1] += qc
    transfers = {}
    for t in r["transfers"]:
        k, dest = key(t["cell_id"], t["source"]), key(t["cell_id"], t["destination"])
        require((k, dest) not in transfers, "unique transfer certificate")
        transfers[k, dest] = t
    expected_transfers = 0
    for k, row in D.items():
        total = sum(a["weight"] for a in row["allocations"])
        require(0 < total <= 2**32, "complete positive normalized allocation")
        A, W, H, C = S[k]
        for a in row["allocations"]:
            expected_transfers += 1
            require(0 < a["weight"] <= total, "positive weight")
            dest = key(k[0], a["destination"])
            require(dest in ideal, "declared same-column target")
            ratio = F(a["weight"], total)
            t = transfers[k, dest]
            require(t["weight"] == a["weight"] and t["total_weight"] == total, "exact fraction operands")
            contains(t["ideal_fraction"], ratio)
            contains(t["ideal_water_mass_kg_m2"], W*ratio)
            contains(t["ideal_water_enthalpy_j_m2"], split[k][0]*ratio)
            ideal[dest][0] += W*ratio
            ideal[dest][1] += split[k][0]*ratio
    require(expected_transfers == len(transfers), "complete transfer coverage")
    outM, outJ, outIdealJ, outDefect = F(0), F(0), F(0), F(0)
    require(len(r["export_certificates"]) == len(X) == len(final["parcels"]), "complete new outbox coverage")
    exported_keys, exported_ids = set(), set()
    for c, p in zip(r["export_certificates"], final["parcels"]):
        e = c["selection"]
        k = e["donor"]["cell_id"], e["donor"]["layer_id"]
        require(k not in exported_keys and e["id"] not in exported_ids, "unique export certificate donor and event")
        exported_keys.add(k); exported_ids.add(e["id"])
        require(same(e, X[k]) and same(c["parcel"], p), "selection and final saved parcel bind")
        A, W, H, C = S[k]
        require((frac(c["source_area_m2"]), frac(c["source_water_mass_kg_m2"]),
                 frac(c["source_complete_enthalpy_j_m2"]), frac(c["source_nonwater_capacity_j_m2_k"])) == (A, W, H, C), "whole source operands")
        m = p["movement"]
        require(m["id"] == e["id"] and m["donor"] == e["donor"] and m["phase"] == e["phase"] and
                m["recipient"] == {"cell_id": -1, "layer_id": -1} and m["import_temperature_k"] == 0,
                "whole parcel identity")
        require(c["exact_mass_representable"] and frac(m["mass_kg"]) == A*W == frac(c["represented_full_mass_kg"]), "exact whole mass")
        require(c["whole_phase_proved"] and p["external_outbox"], "whole-phase owned export")
        contains(c["exact_full_mass_kg"], A*W)
        contains(c["source_complete_energy_ball_j"], A*H-E)
        contains(c["source_complete_energy_ball_j"], A*H+E)
        latent = A*W*frac(source["water"]["latent_heat_j_kg"])
        contains(c["full_latent_energy_j"], latent)
        require((m["phase"] == 0 and A*H+E <= 0) or (m["phase"] == 1 and A*H-E >= latent), "exact full-ball phase")
        J = A*split[k][0]
        contains(p["ideal_carried_enthalpy_j"], J)
        contains(p["ideal_specific_enthalpy_j_kg"], split[k][0]/W)
        delta = frac(p["carried_enthalpy_j"])-J
        contains(p["energy_projection_j"], delta)
        outDefect += abs(delta)
        outM += A*W; outJ += frac(p["carried_enthalpy_j"]); outIdealJ += J
    require(exported_keys == set(X), "complete certified export donor coverage")
    audit_geometry(final["graph"])
    output = final["graph"]["input"]
    require(set(output) == set(source), "output input schema preserved")
    for field in source:
        if field != "columns":
            require(same(output[field], source[field]), "fixed source property "+field)
    require(len(output["columns"]) == len(source["columns"]) == len(q["targets"]), "complete target column coverage")
    for index, (c, initial, plan) in enumerate(zip(output["columns"], source["columns"], q["targets"])):
        require(c["cell_id"] == initial["cell_id"] == plan["cell_id"] == index, "canonical target column identity")
        for field in initial:
            if field not in ("layers", "deep_inventory"):
                require(same(c[field], initial[field]), "stationary column field "+field)
        require(len(c["layers"]) == len(plan["layers"]), "complete target layer count")
        for layer, descriptor in zip(c["layers"], plan["layers"]):
            require(all(same(layer[k], v) for k, v in descriptor.items()), "prescribed target material")
        require((c["deep_inventory"] is None) == (plan["deep_density_kg_m3"] is None), "declared deep target")
        if c["deep_inventory"] is not None:
            require(same(c["deep_inventory"]["density_kg_m3"], plan["deep_density_kg_m3"]), "prescribed deep material")
    R = stores(output)
    require(set(R) == set(ideal) and len(r["projections"]) == len(ideal), "complete final coordinates")
    retDefect = F(0)
    projected = set()
    for p in r["projections"]:
        k = key(p["cell_id"], p["destination"])
        require(k not in projected, "unique final projection")
        projected.add(k)
        A, W, H, C = R[k]; wi, hi = ideal[k]
        require(frac(p["represented_water_mass_kg_m2"]) == W and frac(p["represented_complete_enthalpy_j_m2"]) == H, "final W/H binding")
        contains(p["ideal_water_mass_kg_m2"], wi); contains(p["ideal_complete_enthalpy_j_m2"], hi)
        contains(p["mass_projection_difference_kg_m2"], W-wi); contains(p["enthalpy_projection_difference_j_m2"], H-hi)
        retDefect += A*abs(H-hi)
    sourceM = sum(A*W for A, W, _, _ in S.values())
    sourceJ = sum(A*H for A, _, H, _ in S.values())
    retM = sum(A*W for A, W, _, _ in R.values())
    retJ = sum(A*H for A, _, H, _ in R.values())
    require(sum(R[k][0]*v[0] for k, v in ideal.items())+outM == sourceM, "exact ideal mass conservation")
    require(sum(R[k][0]*v[1] for k, v in ideal.items())+outIdealJ == sourceJ, "exact ideal energy conservation")
    for name, value in (("retained_mass_change_kg", retM-sourceM), ("exported_mass_kg", outM),
                        ("mass_balance_residual_kg", retM+outM-sourceM), ("retained_energy_change_j", retJ-sourceJ),
                        ("exported_energy_j", outJ), ("energy_balance_residual_j", retJ+outJ-sourceJ)):
        contains(r[name], value)
    require(frac(r["retained_energy_defect_upper_j"]) >= retDefect and frac(r["outbox_energy_defect_upper_j"]) >= outDefect,
            "direct final L1 projection bound")
    expected_E = upper_add(upper_add(q["inherited_global_energy_error_j"], r["retained_energy_defect_upper_j"]), r["outbox_energy_defect_upper_j"])
    require(r["final_global_energy_error_j"] == expected_E <= q["maximum_final_energy_error_j"], "outward inherited E charged once")
    for k in ("retained_energy_defect_upper_j", "outbox_energy_defect_upper_j", "final_global_energy_error_j"):
        require(same(final[k], r[k]), "final bound binding")
    physical(output, frac(expected_E))
    audit_domains(r["final_domain"], output, frac(expected_E))
    require(r["work"]["exports_completed"] == len(X) and r["work"]["donors_completed"] == len(D) and
            r["work"]["allocations_completed"] == expected_transfers and r["work"]["targets_completed"] == len(R), "completed work inventory")
    ACCEPTED += 1
    return True


def audit_owner(r):
    require(r["model"] == "mapped_atomic_layered_ice_owner_v3", "owner model")
    t = r.get("topology")
    if t is not None:
        audit(t)
    if not r["prepared"]:
        require(r["final"] is None, "refused owner no final")
        return
    require(r["request"]["topology"] is None or t is not None, "accepted requested topology cannot omit receipt")
    if t is None:
        return
    require(t["accepted"] and all(r[k] is None for k in ("material", "remap", "absorption", "thermal", "thermal_ledger")),
            "accepted exclusive topology component")
    finite_tree(r)
    q, before, after = r["request"], r["initial"], r["final"]
    require(same(before["graph"], t["source_graph"]), "complete owner source graph binding")
    require(same(t["request"]["source"], before["graph"]["input"]), "accepted owner source")
    require(t["request"]["inherited_global_energy_error_j"] == before["joint_energy_error_j"], "owner inherited E")
    require(t["request"]["maximum_final_energy_error_j"] == r["maximum_joint_energy_error_j"], "owner budget binding")
    require(q["expected_revision"] == before["revision"], "owner expected source revision")
    for k, v in q["topology"].items():
        require(same(t["request"][k], v), "owner complete plan binding")
    require(not q["movements"] and not q["absorptions"] and q["thermal"] is None and q["forcing"] is None and q["remap"] is None,
            "exclusive topology request")
    require(same(after["graph"], t["final"]["graph"]) and after["joint_energy_error_j"] == t["final_global_energy_error_j"], "owned final graph and bound")
    for k in ("owner_id", "elapsed_seconds", "geographic_epoch", "geographic_cell_ids", "forcing_history"):
        require(same(after[k], before[k]), "stationary owner field "+k)
    require(after["elapsed_seconds"] == q["end_seconds"] and after["revision"] == before["revision"]+1, "zero-time revision")
    expected = copy.deepcopy(before["pending_outboxes"])
    for p in t["final"]["parcels"]:
        expected.append({"transaction_id": q["id"], "source_revision": before["revision"], "parcel": p,
                         "geographic_cell_id": before["geographic_cell_ids"][p["movement"]["donor"]["cell_id"]]})
    require(same(after["pending_outboxes"], expected), "old identity and new historical outbox ownership")
    events = before["consumed_event_ids"] + [p["movement"]["id"] for p in t["final"]["parcels"]]
    require(len(set(events)) == len(events) and after["consumed_event_ids"] == sorted(events), "consume complete export IDs once")
    require(r["work"]["topology_calls_started"] == 1 and all(r["work"][k] == 0 for k in
            ("material_calls_started", "calorimeter_calls_started", "remap_calls_started", "absorption_calls_started", "thermal_calls_started")), "exclusive observed work")
    require(r["work"]["graph_builds_started"] == t["work"]["source_builder_calls_started"]+t["work"]["output_builder_calls_started"] and
            r["work"]["observed_counts_complete"], "complete owner graph work")
    audit_domains(r["initial_domain"], before["graph"]["input"], frac(before["joint_energy_error_j"]), owner=True)
    audit_domains(r["final_domain"], after["graph"]["input"], frac(after["joint_energy_error_j"]), owner=True)
    require(len(after["pending_outboxes"]) <= r["limits"]["max_pending_outboxes"] and
            len(after["consumed_event_ids"]) <= r["limits"]["max_consumed_events"], "owner retained capacity")


def walk(value):
    if isinstance(value, dict):
        if value.get("model") == "mapped_atomic_layered_ice_owner_v3":
            audit_owner(value)
            return
        if value.get("model") == "fixed_canonical_whole_donor_export_and_homogeneous_topology_v1":
            audit(value)
            return
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipts", type=Path, nargs="+")
    parser.add_argument("--component-inventory", type=Path)
    args = parser.parse_args()
    lines = 0
    component_rows = []
    for path in args.receipts:
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if value.get("kind") == "topology":
                component_rows.append(value)
            try:
                list(walk(value))
                if value.get("kind") == "check":
                    require(value["passed"], "native check "+value["name"])
            except (AssertionError, KeyError) as error:
                raise AssertionError(f"{path}:{number}: {error}") from error
            lines += 1
    if args.component_inventory:
        inv = json.loads(args.component_inventory.read_text())
        require(inv["schema"] == "layered_ice_topology_inventory_v1" and inv["execution"] == "none", "serializer inventory schema")
        require([v["name"] for v in component_rows] == [v["name"] for v in inv["cases"]], "fixed complete component case order")
        require(len(component_rows) == inv["topology_call_cap"], "fixed component call envelope")
        for value, plan in zip(component_rows, inv["cases"]):
            r = value["receipt"]
            require(r["failure_code"] == plan["expected_failure"] and r["accepted"] == (plan["expected_failure"] == ""), "declared component outcome")
            require((r["work"]["source_builder_calls_started"], r["work"]["output_builder_calls_started"]) ==
                    (plan["source_builds"], plan["output_builds"]), "fixed observed builder work")
            require(same(r["request"], plan["request"]) if r["request"] is not None else plan["source_builds"] == 0,
                    "predeclared component operands or pre-retention refusal")
    require(COUNT > 100 and ACCEPTED > 0, "substantive accepted receipt content required")
    print(json.dumps({"accepted": True, "jsonl_records": lines, "assertions": COUNT,
                      "accepted_topology_receipts": ACCEPTED,
                      "geometry_assertions": geometry.checks,
                      "scope": "canonical_W_exact_rational_topology_graph_and_prepared_owner_binding",
                      "lifecycle_scope": "commit_replay_and_rollback_rely_on_native_assertions_not_independent_schedule_replay",
                      "diagnostic_scope": "candidate_temperature_specific_and_intermediate_represented_arithmetic_finite_only"}))


if __name__ == "__main__":
    main()
