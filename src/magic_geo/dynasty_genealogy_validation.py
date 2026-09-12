from __future__ import annotations

from typing import Any


RULER_GENEALOGY_MODEL = (
    "causal_dynasty_economy_conflict_named_ruler_alliance_cadet_genealogy_v1"
)
NAME_ROOTS = [
    "Aren",
    "Belor",
    "Cadan",
    "Daren",
    "Evan",
    "Faron",
    "Galen",
    "Hadar",
    "Ilyr",
    "Joren",
    "Kalen",
    "Loran",
    "Maren",
    "Nadir",
    "Oran",
    "Pavel",
    "Qadir",
    "Radan",
    "Saren",
    "Tovan",
    "Ulric",
    "Varen",
    "Wystan",
    "Yorin",
    "Zarek",
]


def _ruler_genealogy_model() -> dict[str, Any]:
    return {
        "model_type": RULER_GENEALOGY_MODEL,
        "deterministic": True,
        "ruler_count_model": "dynasty_duration_pressure_bounded_two_to_six_rulers_v1",
        "reign_model": "equal_dynasty_duration_partition_v1",
        "ruler_attribute_model": "dynasty_continuity_pressure_economy_treasury_conflict_v1",
        "succession_model": "ordered_predecessor_successor_and_parent_links_v1",
        "cadet_branch_model": "second_ruler_founder_with_next_three_heirs_v1",
        "marriage_model": "sorted_dynasty_first_available_cross_region_second_ruler_pair_v1",
        "name_model": "deterministic_root_and_regnal_number_v1",
        "model_limitation": "synthetic_regnal_genealogy_without_age_consistent_reproduction_competing_heirs_gender_demography_or_observed_calibration",
    }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _roman(number: int) -> str:
    values = [(10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]
    remaining = max(1, min(20, number))
    parts: list[str] = []
    for value, symbol in values:
        while remaining >= value:
            parts.append(symbol)
            remaining -= value
    return "".join(parts)


def _ruler_name(dynasty_id: int, ruler_index: int, lineage_depth: int) -> str:
    root = NAME_ROOTS[
        (dynasty_id * 7 + ruler_index * 3 + lineage_depth) % len(NAME_ROOTS)
    ]
    return f"{root} {_roman(ruler_index + 1)}"


def _economy_by_region(payload: dict[str, Any]) -> dict[int, dict[str, Any]]:
    histories: dict[int, dict[str, Any]] = {}
    for history in payload.get("economy_histories", []):
        region_id = int(history.get("region_id", -1))
        if region_id >= 0:
            histories[region_id] = history
    return histories


def _conflicts_by_region(payload: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for conflict in payload.get("conflicts", []):
        for key in ("region_a", "region_b"):
            region_id = int(conflict.get(key, -1))
            if region_id >= 0:
                grouped.setdefault(region_id, []).append(conflict)
    return grouped


def _dynasty_ruler_count(dynasty: dict[str, Any]) -> int:
    duration = max(1.0, float(dynasty.get("duration_years", 1.0)))
    pressure = _clamp(float(dynasty.get("succession_pressure", 0.0)))
    return max(2, min(6, int(duration // 420.0) + 2 + int(pressure >= 0.55)))


def _expected_genealogy(
    payload: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[str, Any],
]:
    dynasties = payload["dynasties"]
    economies = _economy_by_region(payload)
    conflicts_by_region = _conflicts_by_region(payload)
    rulers: list[dict[str, Any]] = []
    alliances: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    dynasty_rulers: dict[int, list[int]] = {}
    dynasty_annotations: dict[int, dict[str, Any]] = {}
    legitimacy_sum = 0.0
    succession_risk_sum = 0.0
    ruler_lineage_depth_max = 0
    married_ruler_ids: set[int] = set()

    for dynasty in dynasties:
        dynasty_id = int(dynasty.get("id", len(dynasty_rulers)))
        region_id = int(dynasty.get("region_id", -1))
        economy = economies.get(region_id, {})
        conflicts = conflicts_by_region.get(region_id, [])
        duration = max(1.0, float(dynasty.get("duration_years", 1.0)))
        start_year_bp = float(dynasty.get("start_year_bp", duration))
        end_year_bp = float(dynasty.get("end_year_bp", 0.0))
        count = _dynasty_ruler_count(dynasty)
        reign_span = duration / count
        continuity = _clamp(float(dynasty.get("dynastic_continuity_index", 0.0)))
        pressure = _clamp(float(dynasty.get("succession_pressure", 0.0)))
        economy_strength = _clamp(
            float(
                economy.get(
                    "peak_gross_output_index",
                    economy.get("final_gross_output_index", 0.0),
                )
            )
            / 1200.0
        )
        treasury_strength = _clamp(
            float(
                economy.get(
                    "peak_treasury_index", economy.get("final_treasury_index", 0.0)
                )
            )
            / 250.0
        )
        conflict_pressure = _clamp(
            sum(float(conflict.get("intensity", 0.0)) for conflict in conflicts)
            / max(1, len(conflicts))
        )
        ruler_ids: list[int] = []
        previous_ruler_id = -1
        parent_ruler_id = -1

        for index in range(count):
            ruler_id = len(rulers)
            reign_start = max(end_year_bp, start_year_bp - index * reign_span)
            reign_end = max(end_year_bp, start_year_bp - (index + 1) * reign_span)
            if index == count - 1:
                reign_end = end_year_bp
            lineage_depth = int(dynasty.get("lineage_depth", 0)) + index
            legitimacy = _clamp(
                float(dynasty.get("legitimacy_index", 0.0)) * 0.45
                + continuity * 0.24
                + economy_strength * 0.12
                + treasury_strength * 0.07
                + (1.0 - pressure) * 0.12
            )
            succession_risk = _clamp(
                pressure * 0.42
                + conflict_pressure * 0.24
                + (1.0 - legitimacy) * 0.24
                + (index / max(1, count - 1)) * 0.10
            )
            military_prestige = _clamp(
                conflict_pressure * 0.48
                + float(economy.get("max_army_capacity_population", 0.0))
                / 60_000_000.0
                * 0.32
                + pressure * 0.20
            )
            patronage = _clamp(
                economy_strength * 0.50 + treasury_strength * 0.30 + continuity * 0.20
            )
            rulers.append(
                {
                    "id": ruler_id,
                    "dynasty_id": dynasty_id,
                    "region_id": region_id,
                    "culture_region_id": int(dynasty.get("culture_region_id", -1)),
                    "language_region_id": int(dynasty.get("language_region_id", -1)),
                    "name": _ruler_name(
                        dynasty_id, index, int(dynasty.get("lineage_depth", 0))
                    ),
                    "regnal_number": index + 1,
                    "parent_ruler_id": parent_ruler_id,
                    "predecessor_ruler_id": previous_ruler_id,
                    "successor_ruler_id": -1,
                    "spouse_ruler_id": -1,
                    "marriage_alliance_id": -1,
                    "cadet_branch_id": -1,
                    "birth_year_bp": round(reign_start + 24.0 + pressure * 18.0, 6),
                    "reign_start_year_bp": round(reign_start, 6),
                    "reign_end_year_bp": round(reign_end, 6),
                    "reign_length_years": round(max(0.0, reign_start - reign_end), 6),
                    "ruler_lineage_depth": lineage_depth,
                    "legitimacy_index": round(legitimacy, 6),
                    "succession_claim_strength": round(
                        _clamp(legitimacy * 0.72 + continuity * 0.28), 6
                    ),
                    "military_prestige_index": round(military_prestige, 6),
                    "economic_patronage_index": round(patronage, 6),
                    "succession_crisis_risk": round(succession_risk, 6),
                }
            )
            if previous_ruler_id >= 0:
                rulers[previous_ruler_id]["successor_ruler_id"] = ruler_id
            ruler_ids.append(ruler_id)
            legitimacy_sum += legitimacy
            succession_risk_sum += succession_risk
            ruler_lineage_depth_max = max(ruler_lineage_depth_max, lineage_depth)
            parent_ruler_id = previous_ruler_id if previous_ruler_id >= 0 else ruler_id
            previous_ruler_id = ruler_id

        dynasty_rulers[dynasty_id] = ruler_ids
        dynasty_annotations[dynasty_id] = {
            "founder_ruler_id": ruler_ids[0] if ruler_ids else -1,
            "ruler_count": len(ruler_ids),
            "marriage_alliance_count": 0,
            "cadet_branch_count": 0,
        }
        if len(ruler_ids) >= 3:
            branch_id = len(branches)
            branch_founder_id = ruler_ids[min(1, len(ruler_ids) - 1)]
            branch_heir_ids = ruler_ids[2 : min(len(ruler_ids), 5)]
            branches.append(
                {
                    "id": branch_id,
                    "dynasty_id": dynasty_id,
                    "parent_dynasty_id": int(dynasty.get("parent_dynasty_id", -1)),
                    "founder_ruler_id": branch_founder_id,
                    "heir_ruler_ids": branch_heir_ids,
                    "branch_start_year_bp": rulers[branch_founder_id][
                        "reign_start_year_bp"
                    ],
                    "branch_end_year_bp": rulers[branch_heir_ids[-1]][
                        "reign_end_year_bp"
                    ]
                    if branch_heir_ids
                    else rulers[branch_founder_id]["reign_end_year_bp"],
                    "claim_strength": round(
                        _clamp(
                            rulers[branch_founder_id]["succession_claim_strength"] * 0.72
                            + pressure * 0.28
                        ),
                        6,
                    ),
                    "cadet_legitimacy_index": round(
                        _clamp(
                            rulers[branch_founder_id]["legitimacy_index"] * 0.80
                            + continuity * 0.20
                        ),
                        6,
                    ),
                }
            )
            dynasty_annotations[dynasty_id]["cadet_branch_count"] += 1
            for ruler_id in [branch_founder_id, *branch_heir_ids]:
                rulers[ruler_id]["cadet_branch_id"] = branch_id

    sorted_dynasties = sorted(
        dynasties,
        key=lambda dynasty: (
            int(dynasty.get("region_id", -1)),
            -float(dynasty.get("start_year_bp", 0.0)),
            int(dynasty.get("id", -1)),
        ),
    )
    for index, dynasty in enumerate(sorted_dynasties):
        dynasty_id = int(dynasty.get("id", -1))
        ruler_ids = dynasty_rulers.get(dynasty_id, [])
        if not ruler_ids:
            continue
        partner: dict[str, Any] | None = None
        for candidate in sorted_dynasties[index + 1 :]:
            candidate_id = int(candidate.get("id", -1))
            candidate_rulers = dynasty_rulers.get(candidate_id, [])
            if candidate_rulers and int(candidate.get("region_id", -1)) != int(
                dynasty.get("region_id", -1)
            ):
                partner = candidate
                break
        if partner is None and len(sorted_dynasties) > 1:
            for candidate in sorted_dynasties:
                candidate_id = int(candidate.get("id", -1))
                if candidate_id != dynasty_id and dynasty_rulers.get(candidate_id):
                    partner = candidate
                    break
        if partner is None:
            continue
        partner_id = int(partner.get("id", -1))
        spouse_a = ruler_ids[min(1, len(ruler_ids) - 1)]
        partner_rulers = dynasty_rulers.get(partner_id, [])
        spouse_b = partner_rulers[min(1, len(partner_rulers) - 1)]
        if spouse_a in married_ruler_ids or spouse_b in married_ruler_ids:
            continue
        alliance_id = len(alliances)
        alliance_year = min(
            float(rulers[spouse_a]["reign_start_year_bp"]),
            float(rulers[spouse_b]["reign_start_year_bp"]),
        )
        alliance_year = max(
            float(rulers[spouse_a]["reign_end_year_bp"]),
            alliance_year
            - max(float(rulers[spouse_a]["reign_length_years"]), 1.0) * 0.35,
        )
        alliance_strength = _clamp(
            (
                float(rulers[spouse_a]["legitimacy_index"])
                + float(rulers[spouse_b]["legitimacy_index"])
            )
            * 0.32
            + (
                float(rulers[spouse_a]["economic_patronage_index"])
                + float(rulers[spouse_b]["economic_patronage_index"])
            )
            * 0.18
        )
        alliances.append(
            {
                "id": alliance_id,
                "dynasty_a_id": dynasty_id,
                "dynasty_b_id": partner_id,
                "ruler_a_id": spouse_a,
                "ruler_b_id": spouse_b,
                "region_a_id": int(dynasty.get("region_id", -1)),
                "region_b_id": int(partner.get("region_id", -1)),
                "alliance_year_bp": round(alliance_year, 6),
                "alliance_strength": round(alliance_strength, 6),
                "trade_pact_index": round(_clamp(alliance_strength * 0.65 + 0.18), 6),
                "succession_dispute_risk": round(
                    _clamp(
                        (
                            float(rulers[spouse_a]["succession_crisis_risk"])
                            + float(rulers[spouse_b]["succession_crisis_risk"])
                        )
                        * 0.45
                    ),
                    6,
                ),
            }
        )
        rulers[spouse_a]["spouse_ruler_id"] = spouse_b
        rulers[spouse_b]["spouse_ruler_id"] = spouse_a
        rulers[spouse_a]["marriage_alliance_id"] = alliance_id
        rulers[spouse_b]["marriage_alliance_id"] = alliance_id
        married_ruler_ids.update({spouse_a, spouse_b})
        dynasty_annotations[dynasty_id]["marriage_alliance_count"] += 1
        dynasty_annotations[partner_id]["marriage_alliance_count"] += 1

    ruler_count = len(rulers)
    summary = {
        "ruler_count": ruler_count,
        "named_ruler_dynasty_count": sum(
            int(annotation["ruler_count"]) > 0
            for annotation in dynasty_annotations.values()
        ),
        "ruler_marriage_alliance_count": len(alliances),
        "cadet_branch_count": len(branches),
        "married_ruler_count": len(married_ruler_ids),
        "max_ruler_lineage_depth": ruler_lineage_depth_max,
        "mean_ruler_legitimacy_index": round(legitimacy_sum / ruler_count, 6)
        if ruler_count
        else 0.0,
        "mean_succession_crisis_risk": round(succession_risk_sum / ruler_count, 6)
        if ruler_count
        else 0.0,
        "mean_marriage_alliance_strength": round(
            sum(float(alliance["alliance_strength"]) for alliance in alliances)
            / len(alliances),
            6,
        )
        if alliances
        else 0.0,
        "mean_cadet_branch_claim_strength": round(
            sum(float(branch["claim_strength"]) for branch in branches) / len(branches),
            6,
        )
        if branches
        else 0.0,
    }
    return rulers, alliances, branches, dynasty_annotations, summary


def _contains_expected(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_expected(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(
                _contains_expected(actual_item, expected_item)
                for actual_item, expected_item in zip(actual, expected, strict=True)
            )
        )
    return actual == expected


def validate_dynasty_genealogy_replay(payload: dict[str, Any]) -> list[str]:
    from .native_dynasty_genealogy_validation import genealogy_version
    try:
        if genealogy_version(payload) == 2:
            from .native_dynasty_genealogy_validation import validate_native_dynasty_genealogy
            return validate_native_dynasty_genealogy(payload)
    except (AttributeError, KeyError, TypeError, ValueError, OverflowError):
        return ["ruler genealogy model or causal replay invalid"]
    try:
        summary = payload.get("summary", {})
        required_lists = (
            "dynasties",
            "economy_histories",
            "conflicts",
            "rulers",
            "marriage_alliances",
            "cadet_branches",
        )
        valid = isinstance(summary, dict) and all(
            isinstance(payload.get(name), list) for name in required_lists
        )
        valid = valid and payload.get("ruler_genealogy_model") == _ruler_genealogy_model()
        valid = valid and summary.get("ruler_genealogy_model") == RULER_GENEALOGY_MODEL
        rulers, alliances, branches, dynasty_annotations, expected_summary = (
            _expected_genealogy(payload)
        )
        valid = valid and _contains_expected(payload.get("rulers"), rulers)
        valid = valid and _contains_expected(payload.get("marriage_alliances"), alliances)
        valid = valid and _contains_expected(payload.get("cadet_branches"), branches)
        valid = valid and all(
            summary.get(key) == value for key, value in expected_summary.items()
        )
        dynasties_by_id = {
            int(dynasty.get("id", -1)): dynasty for dynasty in payload["dynasties"]
        }
        valid = valid and all(
            dynasty_id in dynasties_by_id
            and _contains_expected(dynasties_by_id[dynasty_id], annotations)
            for dynasty_id, annotations in dynasty_annotations.items()
        )
    except (
        AttributeError,
        IndexError,
        KeyError,
        OverflowError,
        TypeError,
        ValueError,
        ZeroDivisionError,
    ):
        valid = False
    return [] if valid else ["ruler genealogy model or causal replay invalid"]
