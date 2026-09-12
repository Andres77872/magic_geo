"""Independent source-complete v2 event, family and era replay.

Unavailable continuity is retained as null. Foundation chronology is never
created from a placeholder age; independent family membership remains intact.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any
from .historical_geography_validation import EVENT_TYPES, ERA_DEFINITIONS, _clamp, _era_for_year
from .native_social_availability import require_native_social_availability
from .native_cultural_availability_validation import (
    validate_native_cultural_availability, cultural_equations_valid, exact, number, close, record_matches,
)

# Literal independent expected declaration, not imported from the annotator.
EXPECTED_MODEL = {'availability_policy': 'retain_independent_event_fields_with_family_coverage_and_complete_era_aggregates',
 'deterministic': True,
 'dynastic_change_model': 'foundation_age_region_order_pressure_trade_or_isolation_trigger_v1',
 'dynastic_change_parameters': {'foundation_year_weight': 0.48,
                                'maximum_year_bp': 2100.0,
                                'minimum_year_bp': 180.0,
                                'pressure_threshold': 0.34,
                                'region_order_year_step': 180.0,
                                'route_count_trigger': 0,
                                'trade_contact_threshold': 0.55,
                                'trade_pressure_weight': 0.18},
 'era_aggregate_model': 'event_count_and_mean_pressure_continuity_v1',
 'era_model': 'fixed_four_era_strict_year_bp_partition_v1',
 'eras': [{'dominant_process': 'founding', 'end_year_bp': 2400.0, 'id': 0, 'start_year_bp': 4200.0},
          {'dominant_process': 'expansion', 'end_year_bp': 1300.0, 'id': 1, 'start_year_bp': 2400.0},
          {'dominant_process': 'fragmentation', 'end_year_bp': 450.0, 'id': 2, 'start_year_bp': 1300.0},
          {'dominant_process': 'integration', 'end_year_bp': 0.0, 'id': 3, 'start_year_bp': 450.0}],
 'event_order': 'descending_raw_year_bp_then_native_event_enum_v1',
 'language_split_maximum_year_bp': 3400.0,
 'language_split_minimum_year_bp': 80.0,
 'language_split_model': 'child_language_divergence_age_change_rate_v1',
 'migration_model': 'culture_pressure_or_trade_trigger_same_language_contact_link_v1',
 'migration_parameters': {'base_year_bp': 260.0,
                          'culture_order_year_step': 220.0,
                          'maximum_year_bp': 2600.0,
                          'migration_pressure_threshold': 0.42,
                          'migration_pressure_year_weight': 2100.0,
                          'minimum_year_bp': 120.0,
                          'trade_contact_threshold': 0.28},
 'model_limitation': 'diagnostic_single-timeline_events_without_agent_causation_duration_uncertainty_or_observed_historical_calibration',
 'model_type': 'causal_region_culture_language_trade_site_timeline_v2',
 'ruin_abandonment_maximum_events': 16,
 'ruin_abandonment_model': 'first_sixteen_ranked_ruins_significance_timeline_v1',
 'sacred_founding_maximum_events': 12,
 'sacred_founding_model': 'first_twelve_ranked_sacred_sites_significance_timeline_v1',
 'source_cultural_site_model': 'causal_terrain_culture_ranked_sacred_ruin_sites_v2',
 'source_culture_region_model': 'causal_political_homeland_barrier_trade_culture_regions_v2',
 'source_language_region_model': 'causal_trade_union_family_lineage_phonology_v1',
 'source_native_social_availability_model': 'native_settlement_source_complete_social_estimates_v1',
 'source_political_border_model': 'causal_adjacent_region_terrain_border_segments_v1',
 'source_political_region_model': 'causal_capital_barrier_partition_political_regions_v1',
 'source_trade_flow_model': 'causal_route_endpoint_complement_trade_flows_v1',
 'state_foundation_model': 'region_barrier_pressure_and_culture_age_v1',
 'state_foundation_parameters': {'base_pressure': 0.18,
                                 'base_year_bp': 380.0,
                                 'border_barrier_weight': 0.28,
                                 'culture_age_weight': 0.72,
                                 'maximum_year_bp': 3800.0,
                                 'minimum_year_bp': 260.0,
                                 'region_barrier_weight': 0.32,
                                 'small_region_pressure_bonus': 0.18,
                                 'small_region_settlement_maximum': 2},
 'trade_boom_maximum_events': 12,
 'trade_boom_model': 'top_volume_then_id_trade_flow_friction_timeline_v1',
 'trade_boom_parameters': {'base_year_bp': 140.0,
                           'friction_year_weight': 820.0,
                           'maximum_year_bp': 1300.0,
                           'minimum_year_bp': 70.0,
                           'rank_year_step': 42.0}}


def _add_event(events, event_type, year_bp, region_id, related_region_id,
        culture_region_id, related_culture_region_id, language_region_id,
        related_language_region_id, cell_id, pressure_index, continuity_index):
    events.append({"id": len(events), "era_id": _era_for_year(year_bp), "type": event_type,
        "region_id": region_id, "related_region_id": related_region_id,
        "culture_region_id": culture_region_id, "related_culture_region_id": related_culture_region_id,
        "language_region_id": language_region_id, "related_language_region_id": related_language_region_id,
        "cell_id": cell_id, "year_bp": year_bp, "pressure_index": _clamp(pressure_index),
        "continuity_estimate_available": continuity_index is not None,
        "continuity_index": _clamp(continuity_index) if continuity_index is not None else None})


def _replay_valid(payload: dict[str, Any]) -> bool:
    require_native_social_availability(payload)
    if validate_native_cultural_availability(payload):
        return False
    if not exact(payload.get("historical_event_model"), EXPECTED_MODEL) or payload["summary"].get("historical_event_model") != EXPECTED_MODEL["model_type"]:
        return False
    return historical_equations_valid(payload)


def historical_equations_valid(payload: dict[str, Any]) -> bool:
    """Scoped stage-equation comparison; public validation retains all header gates."""
    if not cultural_equations_valid(payload):
        return False
    envelope = payload["native_social_availability"]
    summary = payload["summary"]
    regions, borders, flows, settlements, cultures, languages, sacred_areas, ruins, actual_eras, actual_events = (
        payload[k] for k in ("political_regions", "borders", "trade_flows", "settlements", "cultures", "language_regions", "sacred_areas", "ruins", "historical_eras", "historical_events"))
    families = [{"event_type": name, "inference_available": True,
        "applicable_source_count": 0, "available_source_count": 0, "recorded_event_count": 0} for name in EVENT_TYPES]
    def coverage(kind, available):
        family = families[kind]
        family["applicable_source_count"] += 1
        family["available_source_count"] += int(available)
        family["inference_available"] &= available
    events: list[dict[str, Any]] = []
    region_to_culture = {
        int(culture.get("homeland_region_id", -1)): int(culture["id"])
        for culture in cultures
    }
    border_pressure: defaultdict[int, float] = defaultdict(float)
    border_length: defaultdict[int, float] = defaultdict(float)
    for border in borders:
        length = float(border.get("length_km", 0.0))
        weighted_pressure = float(border.get("barrier_score", 0.0)) * length
        for region_id in (int(border.get("region_a", -1)), int(border.get("region_b", -1))):
            border_pressure[region_id] += weighted_pressure
            border_length[region_id] += length
    trade_volume: defaultdict[int, float] = defaultdict(float)
    for flow in flows:
        region_from = int(flow.get("region_from", -1))
        region_to = int(flow.get("region_to", -1))
        volume = float(flow.get("volume_index", 0.0))
        if region_from >= 0:
            trade_volume[region_from] += volume
        if region_to >= 0:
            trade_volume[region_to] += volume

    if regions and cultures:
        for region in regions:
            region_id = int(region["id"])
            culture_id = region_to_culture.get(region_id, -1)
            culture = cultures[culture_id] if 0 <= culture_id < len(cultures) else None
            language_id = int(culture.get("language_region_id", -1)) if culture is not None else -1
            capital_id = int(region.get("capital_settlement_id", -1))
            cell_id = int(settlements[capital_id].get("cell_id", -1)) if 0 <= capital_id < len(settlements) else -1
            complete = culture is not None and culture["continuity_estimate_available"]
            continuity = number(culture["continuity_index"]) if complete else None
            coverage(0, complete)
            mean_border_pressure = (
                border_pressure[region_id] / border_length[region_id]
                if border_length[region_id] > 0.0
                else 0.0
            )
            pressure = _clamp(
                0.18
                + 0.32 * float(region.get("barrier_pressure", 0.0))
                + 0.28 * mean_border_pressure
                + (0.18 if int(region.get("settlement_count", 0)) <= 2 else 0.0)
            )
            if complete:
                culture_age = number(culture["estimated_age_years"])
                foundation_year = _clamp(380.0 + 0.72 * culture_age, 260.0, 3800.0)
                _add_event(
                    events,
                    "state_foundation",
                    foundation_year,
                    region_id,
                    -1,
                    culture_id,
                    -1,
                    language_id,
                    -1,
                    cell_id,
                    pressure,
                    continuity,
                )
            settlement_count = int(region.get("settlement_count", 0))
            trade_contact = trade_volume[region_id] / (100.0 * max(1, settlement_count))
            if pressure > 0.34 or trade_contact > 0.55 or int(region.get("route_count", 0)) == 0:
                coverage(1, complete)
                if not complete:
                    continue
                _add_event(
                    events,
                    "dynastic_change",
                    _clamp(foundation_year * 0.48 + 180.0 * (region_id + 1), 180.0, 2100.0),
                    region_id,
                    -1,
                    culture_id,
                    -1,
                    language_id,
                    -1,
                    cell_id,
                    _clamp(pressure + 0.18 * trade_contact),
                    continuity,
                )

        for culture in cultures:
            migration_pressure = float(culture.get("migration_pressure", 0.0))
            trade_contact = float(culture.get("trade_contact_index", 0.0))
            if migration_pressure < 0.42 and trade_contact < 0.28:
                continue
            coverage(2, culture["continuity_estimate_available"])
            settlement_ids = [int(value) for value in culture.get("settlement_ids", [])]
            settlement_id = settlement_ids[0] if settlement_ids else -1
            cell_id = int(settlements[settlement_id].get("cell_id", -1)) if 0 <= settlement_id < len(settlements) else -1
            related_culture_id = -1
            best_contact = -1.0
            for other in cultures:
                if (
                    int(other["id"]) == int(culture["id"])
                    or int(other.get("language_region_id", -1)) != int(culture.get("language_region_id", -1))
                ):
                    continue
                contact = 1.0 - abs(float(other.get("trade_contact_index", 0.0)) - trade_contact)
                if contact > best_contact:
                    best_contact = contact
                    related_culture_id = int(other["id"])
            _add_event(
                events,
                "migration",
                _clamp(260.0 + 2100.0 * migration_pressure + 220.0 * int(culture["id"]), 120.0, 2600.0),
                int(culture.get("homeland_region_id", -1)),
                -1,
                int(culture["id"]),
                related_culture_id,
                int(culture.get("language_region_id", -1)),
                -1,
                cell_id,
                migration_pressure,
                number(culture["continuity_index"]) if culture["continuity_estimate_available"] else None,
            )

        for language in languages:
            parent_id = int(language.get("parent_language_region_id", -1))
            if parent_id < 0:
                continue
            coverage(3, True)
            culture_ids = [int(value) for value in language.get("culture_ids", [])]
            culture_id = culture_ids[0] if culture_ids else -1
            region_id = -1
            cell_id = -1
            if 0 <= culture_id < len(cultures):
                culture = cultures[culture_id]
                region_id = int(culture.get("homeland_region_id", -1))
                settlement_ids = [int(value) for value in culture.get("settlement_ids", [])]
                settlement_id = settlement_ids[0] if settlement_ids else -1
                if 0 <= settlement_id < len(settlements):
                    cell_id = int(settlements[settlement_id].get("cell_id", -1))
            change_rate = float(language.get("change_rate", 0.0))
            _add_event(
                events,
                "language_split",
                _clamp(float(language.get("divergence_age_years", 0.0)), 80.0, 3400.0),
                region_id,
                -1,
                culture_id,
                -1,
                int(language["id"]),
                parent_id,
                cell_id,
                change_rate,
                _clamp(1.0 - change_rate),
            )

        ranked_flows = sorted(flows, key=lambda flow: (-float(flow.get("volume_index", 0.0)), int(flow["id"])))
        for rank, flow in enumerate(ranked_flows[:12]):
            coverage(4, True)
            region_from = int(flow.get("region_from", -1))
            region_to = int(flow.get("region_to", -1))
            culture_id = region_to_culture.get(region_from, -1)
            related_culture_id = region_to_culture.get(region_to, -1)
            language_id = (
                int(cultures[culture_id].get("language_region_id", -1))
                if 0 <= culture_id < len(cultures)
                else -1
            )
            settlement_id = int(flow.get("from", -1))
            cell_id = int(settlements[settlement_id].get("cell_id", -1)) if 0 <= settlement_id < len(settlements) else -1
            friction = float(flow.get("friction", 0.0))
            continuity = _clamp(1.0 - friction / 2.0)
            _add_event(
                events,
                "trade_boom",
                _clamp(140.0 + 820.0 * continuity + 42.0 * rank, 70.0, 1300.0),
                region_from,
                region_to,
                culture_id,
                related_culture_id,
                language_id,
                -1,
                cell_id,
                _clamp(float(flow.get("volume_index", 0.0)) / 100.0),
                continuity,
            )

        for rank, site in enumerate(sacred_areas[:12]):
            culture_id = int(site.get("culture_region_id", -1))
            culture = cultures[culture_id] if 0 <= culture_id < len(cultures) else None
            complete = culture is not None and culture["continuity_estimate_available"]
            coverage(5, complete)
            significance = float(site.get("significance", 0.0))
            _add_event(
                events,
                "sacred_founding",
                _clamp(220.0 + 1800.0 * significance + 35.0 * rank, 120.0, 2400.0),
                int(culture.get("homeland_region_id", -1)) if culture is not None else -1,
                -1,
                culture_id,
                -1,
                int(site.get("language_region_id", -1)),
                -1,
                int(site.get("cell_id", -1)),
                significance,
                number(culture["continuity_index"]) if complete else None,
            )

        if not envelope["ruin_inference_available"]:
            families[6]["inference_available"] = False
            families[6]["applicable_source_count"] = None
        for rank, ruin in enumerate(ruins[:16]):
            coverage(6, True)
            culture_id = int(ruin.get("culture_region_id", -1))
            culture = cultures[culture_id] if 0 <= culture_id < len(cultures) else None
            significance = float(ruin.get("significance", 0.0))
            _add_event(
                events,
                "ruin_abandonment",
                _clamp(90.0 + 1500.0 * significance + 28.0 * rank, 80.0, 1900.0),
                int(culture.get("homeland_region_id", -1)) if culture is not None else -1,
                -1,
                culture_id,
                -1,
                int(ruin.get("language_region_id", -1)),
                -1,
                int(ruin.get("cell_id", -1)),
                significance,
                float(ruin.get("preservation_score", 0.0)),
            )

    type_order = {event_type: index for index, event_type in enumerate(EVENT_TYPES)}
    events.sort(key=lambda event: (-float(event["year_bp"]), type_order[str(event["type"])]))
    for event_id, event in enumerate(events):
        event["id"] = event_id
        event["era_id"] = _era_for_year(float(event["year_bp"]))

    for event in events:
        families[EVENT_TYPES.index(event["type"])]["recorded_event_count"] += 1
    if not exact(envelope["historical_event_family_coverage"], families):
        return False
    if not exact(envelope["historical_event_inference_available"], all(f["inference_available"] for f in families)):
        return False
    event_tolerances = {"year_bp": .20, "pressure_index": .002, "continuity_index": .002}
    if len(actual_events) != len(events) or any(not record_matches(a, e, event_tolerances) for a, e in zip(actual_events, events)):
        return False

    state_count_available = families[0]["inference_available"] and families[1]["inference_available"]
    event_count_available = state_count_available and families[6]["inference_available"]
    eras = []
    for era_id, process, start, end in ERA_DEFINITIONS:
        recorded = [event for event in events if event["era_id"] == era_id]
        continuity_available = event_count_available and all(e["continuity_estimate_available"] for e in recorded)
        era = {"id": era_id, "dominant_process": process, "start_year_bp": start, "end_year_bp": end,
            "recorded_event_count": len(recorded),
            "event_count_available": event_count_available,
            "state_event_count_available": state_count_available,
            "migration_event_count_available": True, "language_event_count_available": True,
            "mean_instability_available": event_count_available, "mean_connectivity_available": continuity_available,
            "event_count": len(recorded) if event_count_available else None,
            "state_event_count": sum(e["type"] in {"state_foundation", "dynastic_change"} for e in recorded) if state_count_available else None,
            "migration_event_count": sum(e["type"] == "migration" for e in recorded),
            "language_event_count": sum(e["type"] == "language_split" for e in recorded),
            "mean_instability": (sum(e["pressure_index"] for e in recorded)/len(recorded) if recorded else 0.) if event_count_available else None,
            "mean_connectivity": (sum(e["continuity_index"] for e in recorded)/len(recorded) if recorded else 0.) if continuity_available else None}
        eras.append(era)
    era_tolerances = {"start_year_bp": .001, "end_year_bp": .001, "mean_instability": .002, "mean_connectivity": .002}
    if len(actual_eras) != len(eras) or any(not record_matches(a, e, era_tolerances) for a, e in zip(actual_eras, eras)):
        return False
    expected_summary = {
        "historical_era_count": len(eras),
        "recorded_historical_event_count": len(events),
        "historical_event_count": len(events) if event_count_available else None,
        "migration_event_count": sum(e["type"] == "migration" for e in events),
        "dynastic_change_count": sum(e["type"] == "dynastic_change" for e in events) if families[1]["inference_available"] else None,
    }
    if any(not exact(summary.get(k), v) for k, v in expected_summary.items()):
        return False
    instability_available = event_count_available and bool(events)
    if instability_available:
        if not close(summary.get("mean_historical_instability"), sum(e["pressure_index"] for e in events)/len(events), .002):
            return False
    elif summary.get("mean_historical_instability", "missing") is not None:
        return False
    flags = summary.get("native_social_summary_availability")
    return type(flags) is dict and all(exact(flags.get(k), v) for k, v in {
        "historical_event_count": event_count_available,
        "dynastic_change_count": families[1]["inference_available"],
        "mean_historical_instability": instability_available,
    }.items())


def validate_native_historical_availability(payload: dict[str, Any]) -> list[str]:
    try:
        valid = _replay_valid(payload)
    except (IndexError, KeyError, TypeError, ValueError, OverflowError):
        valid = False
    return [] if valid else ["native historical availability model or causal replay invalid"]
