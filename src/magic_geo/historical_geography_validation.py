from __future__ import annotations

from collections import defaultdict
from typing import Any


HISTORICAL_EVENT_MODEL = "causal_region_culture_language_trade_site_timeline_v1"
EVENT_TYPES = (
    "state_foundation",
    "dynastic_change",
    "migration",
    "language_split",
    "trade_boom",
    "sacred_founding",
    "ruin_abandonment",
)
ERA_DEFINITIONS = (
    (0, "founding", 4200.0, 2400.0),
    (1, "expansion", 2400.0, 1300.0),
    (2, "fragmentation", 1300.0, 450.0),
    (3, "integration", 450.0, 0.0),
)


def _model() -> dict[str, Any]:
    return {
        "model_type": HISTORICAL_EVENT_MODEL,
        "deterministic": True,
        "era_model": "fixed_four_era_strict_year_bp_partition_v1",
        "eras": [
            {"id": era_id, "dominant_process": process, "start_year_bp": start, "end_year_bp": end}
            for era_id, process, start, end in ERA_DEFINITIONS
        ],
        "state_foundation_model": "region_barrier_pressure_and_culture_age_v1",
        "state_foundation_parameters": {
            "base_pressure": 0.18,
            "region_barrier_weight": 0.32,
            "border_barrier_weight": 0.28,
            "small_region_pressure_bonus": 0.18,
            "small_region_settlement_maximum": 2,
            "base_year_bp": 380.0,
            "culture_age_weight": 0.72,
            "minimum_year_bp": 260.0,
            "maximum_year_bp": 3800.0,
        },
        "dynastic_change_model": "foundation_age_region_order_pressure_trade_or_isolation_trigger_v1",
        "dynastic_change_parameters": {
            "pressure_threshold": 0.34,
            "trade_contact_threshold": 0.55,
            "route_count_trigger": 0,
            "foundation_year_weight": 0.48,
            "region_order_year_step": 180.0,
            "minimum_year_bp": 180.0,
            "maximum_year_bp": 2100.0,
            "trade_pressure_weight": 0.18,
        },
        "migration_model": "culture_pressure_or_trade_trigger_same_language_contact_link_v1",
        "migration_parameters": {
            "migration_pressure_threshold": 0.42,
            "trade_contact_threshold": 0.28,
            "base_year_bp": 260.0,
            "migration_pressure_year_weight": 2100.0,
            "culture_order_year_step": 220.0,
            "minimum_year_bp": 120.0,
            "maximum_year_bp": 2600.0,
        },
        "language_split_model": "child_language_divergence_age_change_rate_v1",
        "language_split_minimum_year_bp": 80.0,
        "language_split_maximum_year_bp": 3400.0,
        "trade_boom_model": "top_volume_then_id_trade_flow_friction_timeline_v1",
        "trade_boom_maximum_events": 12,
        "trade_boom_parameters": {
            "base_year_bp": 140.0,
            "friction_year_weight": 820.0,
            "rank_year_step": 42.0,
            "minimum_year_bp": 70.0,
            "maximum_year_bp": 1300.0,
        },
        "sacred_founding_model": "first_twelve_ranked_sacred_sites_significance_timeline_v1",
        "sacred_founding_maximum_events": 12,
        "ruin_abandonment_model": "first_sixteen_ranked_ruins_significance_timeline_v1",
        "ruin_abandonment_maximum_events": 16,
        "event_order": "descending_raw_year_bp_then_native_event_enum_v1",
        "era_aggregate_model": "event_count_and_mean_pressure_continuity_v1",
        "model_limitation": "diagnostic_single-timeline_events_without_agent_causation_duration_uncertainty_or_observed_historical_calibration",
    }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _era_for_year(year_bp: float) -> int:
    if year_bp > 2400.0:
        return 0
    if year_bp > 1300.0:
        return 1
    if year_bp > 450.0:
        return 2
    return 3


def _add_event(
    events: list[dict[str, Any]],
    event_type: str,
    year_bp: float,
    region_id: int,
    related_region_id: int,
    culture_region_id: int,
    related_culture_region_id: int,
    language_region_id: int,
    related_language_region_id: int,
    cell_id: int,
    pressure_index: float,
    continuity_index: float,
) -> None:
    events.append(
        {
            "id": len(events),
            "era_id": _era_for_year(year_bp),
            "type": event_type,
            "region_id": region_id,
            "related_region_id": related_region_id,
            "culture_region_id": culture_region_id,
            "related_culture_region_id": related_culture_region_id,
            "language_region_id": language_region_id,
            "related_language_region_id": related_language_region_id,
            "cell_id": cell_id,
            "year_bp": year_bp,
            "pressure_index": _clamp(pressure_index),
            "continuity_index": _clamp(continuity_index),
        }
    )


def _close(actual: Any, expected: float, tolerance: float) -> bool:
    try:
        return abs(float(actual) - expected) <= tolerance
    except (TypeError, ValueError):
        return False


def _event_matches(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    exact_keys = (
        "id",
        "era_id",
        "type",
        "region_id",
        "related_region_id",
        "culture_region_id",
        "related_culture_region_id",
        "language_region_id",
        "related_language_region_id",
        "cell_id",
    )
    if any(actual.get(key) != expected[key] for key in exact_keys):
        return False
    return (
        _close(actual.get("year_bp"), float(expected["year_bp"]), 0.20)
        and _close(actual.get("pressure_index"), float(expected["pressure_index"]), 0.002)
        and _close(actual.get("continuity_index"), float(expected["continuity_index"]), 0.002)
    )


def _records_are_indexed(records: list[dict[str, Any]]) -> bool:
    return all(int(record.get("id", -1)) == index for index, record in enumerate(records))


def _replay_valid(payload: dict[str, Any]) -> bool:
    summary = payload.get("summary", {})
    regions = payload.get("political_regions", [])
    borders = payload.get("borders", [])
    flows = payload.get("trade_flows", [])
    settlements = payload.get("settlements", [])
    cultures = payload.get("cultures", [])
    languages = payload.get("language_regions", [])
    sacred_areas = payload.get("sacred_areas", [])
    ruins = payload.get("ruins", [])
    actual_eras = payload.get("historical_eras", [])
    actual_events = payload.get("historical_events", [])
    collections = (
        regions,
        borders,
        flows,
        settlements,
        cultures,
        languages,
        sacred_areas,
        ruins,
        actual_eras,
        actual_events,
    )
    if not isinstance(summary, dict) or not all(isinstance(value, list) for value in collections):
        return False
    if not all(all(isinstance(record, dict) for record in records) for records in collections):
        return False
    if (
        payload.get("historical_event_model") != _model()
        or summary.get("historical_event_model") != HISTORICAL_EVENT_MODEL
    ):
        return False
    indexed_sources = (regions, borders, flows, settlements, cultures, languages, sacred_areas, ruins)
    if not all(_records_are_indexed(records) for records in indexed_sources):
        return False

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
            continuity = float(culture.get("continuity_index", 0.5)) if culture is not None else 0.5
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
            culture_age = float(culture.get("estimated_age_years", 1800.0)) if culture is not None else 1800.0
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
                float(culture.get("continuity_index", 0.0)),
            )

        for language in languages:
            parent_id = int(language.get("parent_language_region_id", -1))
            if parent_id < 0:
                continue
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
                float(culture.get("continuity_index", 0.5)) if culture is not None else 0.5,
            )

        for rank, ruin in enumerate(ruins[:16]):
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

    if len(actual_events) != len(events) or any(
        not _event_matches(actual, expected)
        for actual, expected in zip(actual_events, events, strict=True)
    ):
        return False

    eras = [
        {
            "id": era_id,
            "dominant_process": process,
            "start_year_bp": start,
            "end_year_bp": end,
            "event_count": 0,
            "state_event_count": 0,
            "migration_event_count": 0,
            "language_event_count": 0,
            "mean_instability": 0.0,
            "mean_connectivity": 0.0,
        }
        for era_id, process, start, end in ERA_DEFINITIONS
    ]
    for event in events:
        era = eras[int(event["era_id"])]
        era["event_count"] += 1
        era["mean_instability"] += float(event["pressure_index"])
        era["mean_connectivity"] += float(event["continuity_index"])
        if event["type"] in {"state_foundation", "dynastic_change"}:
            era["state_event_count"] += 1
        elif event["type"] == "migration":
            era["migration_event_count"] += 1
        elif event["type"] == "language_split":
            era["language_event_count"] += 1
    for era in eras:
        if int(era["event_count"]) > 0:
            era["mean_instability"] /= int(era["event_count"])
            era["mean_connectivity"] /= int(era["event_count"])
    if len(actual_eras) != len(eras):
        return False
    era_exact_keys = (
        "id",
        "dominant_process",
        "event_count",
        "state_event_count",
        "migration_event_count",
        "language_event_count",
    )
    for actual, expected in zip(actual_eras, eras, strict=True):
        if any(actual.get(key) != expected[key] for key in era_exact_keys):
            return False
        if not all(
            _close(actual.get(key), float(expected[key]), tolerance)
            for key, tolerance in (
                ("start_year_bp", 0.001),
                ("end_year_bp", 0.001),
                ("mean_instability", 0.002),
                ("mean_connectivity", 0.002),
            )
        ):
            return False

    expected_summary = {
        "historical_era_count": len(eras),
        "historical_event_count": len(events),
        "migration_event_count": sum(event["type"] == "migration" for event in events),
        "dynastic_change_count": sum(event["type"] == "dynastic_change" for event in events),
    }
    return all(int(summary.get(key, -1)) == value for key, value in expected_summary.items())


def validate_historical_geography_replay(payload: dict[str, Any]) -> list[str]:
    from .native_social_availability import uses_native_social_availability
    try:
        if uses_native_social_availability(payload):
            from .native_historical_availability_validation import validate_native_historical_availability
            return validate_native_historical_availability(payload)
    except (TypeError, ValueError, OverflowError):
        return ["historical geography model or causal replay invalid"]
    try:
        valid = _replay_valid(payload)
    except (IndexError, KeyError, TypeError, ValueError):
        valid = False
    return [] if valid else ["historical geography model or causal replay invalid"]
