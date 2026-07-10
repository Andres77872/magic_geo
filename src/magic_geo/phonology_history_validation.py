from __future__ import annotations

from typing import Any


RULE_TEMPLATES = [
    ("lenition", "p", "f", "between_vowels", "intervocalic_weakening", -1),
    ("lenition", "t", "th", "between_vowels", "intervocalic_weakening", -1),
    ("palatalization", "k", "ch", "before_front_vowels", "front_vowel_contact", 0),
    ("vowel_shift", "a", "e", "stressed_open_syllable", "chain_shift", 0),
    ("vowel_shift", "u", "o", "unstressed_syllable", "vowel_lowering", 0),
    ("nasal_assimilation", "n", "m", "before_labials", "place_assimilation", 0),
    ("final_devoicing", "b", "p", "word_final", "coda_devoicing", 0),
    ("vowel_reduction", "e", "schwa", "unstressed_syllable", "centralization", -1),
    ("cluster_simplification", "kt", "t", "coda_cluster", "cluster_loss", -1),
    ("rhotic_change", "r", "l", "after_vowels", "liquid_merger", 0),
    ("epenthesis", "tr", "tir", "complex_onset", "vowel_epenthesis", 1),
    ("affrication", "d", "dz", "before_front_vowels", "coronal_affrication", 0),
]
LEXICAL_ROOTS = [
    ("water", "pana", "hydrology"),
    ("river", "taran", "hydrology"),
    ("mountain", "kartu", "terrain"),
    ("stone", "bakar", "terrain"),
    ("sun", "sala", "sky"),
    ("moon", "luma", "sky"),
    ("fire", "pira", "technology"),
    ("grain", "naku", "subsistence"),
    ("salt", "tasa", "resource"),
    ("king", "raku", "authority"),
    ("road", "traka", "mobility"),
    ("house", "domu", "settlement"),
]
SEGMENT_FEATURES = {
    "p": {"place": "bilabial", "manner": "stop", "voicing": "voiceless"},
    "b": {"place": "bilabial", "manner": "stop", "voicing": "voiced"},
    "m": {"place": "bilabial", "manner": "nasal", "voicing": "voiced"},
    "t": {"place": "alveolar", "manner": "stop", "voicing": "voiceless"},
    "d": {"place": "alveolar", "manner": "stop", "voicing": "voiced"},
    "n": {"place": "alveolar", "manner": "nasal", "voicing": "voiced"},
    "r": {"place": "alveolar", "manner": "rhotic", "voicing": "voiced"},
    "l": {"place": "alveolar", "manner": "lateral", "voicing": "voiced"},
    "s": {"place": "alveolar", "manner": "fricative", "voicing": "voiceless"},
    "k": {"place": "velar", "manner": "stop", "voicing": "voiceless"},
    "f": {"place": "labiodental", "manner": "fricative", "voicing": "voiceless"},
    "th": {"place": "dental", "manner": "fricative", "voicing": "voiceless"},
    "ch": {"place": "postalveolar", "manner": "affricate", "voicing": "voiceless"},
    "dz": {"place": "alveolar", "manner": "affricate", "voicing": "voiced"},
    "a": {"height": "open", "backness": "central", "rounding": "unrounded"},
    "e": {"height": "mid", "backness": "front", "rounding": "unrounded"},
    "i": {"height": "close", "backness": "front", "rounding": "unrounded"},
    "o": {"height": "mid", "backness": "back", "rounding": "rounded"},
    "u": {"height": "close", "backness": "back", "rounding": "rounded"},
    "schwa": {"height": "mid", "backness": "central", "rounding": "unrounded"},
}
VOWELS = set("aeiou")
PHONOLOGY_HISTORY_MODEL = (
    "causal_language_era_sound_rule_lexical_diffusion_speaker_history_v1"
)


def _phonology_history_model() -> dict[str, Any]:
    return {
        "model_type": PHONOLOGY_HISTORY_MODEL,
        "deterministic": True,
        "rule_model": "language_lineage_change_contact_isolation_template_selection_v1",
        "history_model": "era_partitioned_inventory_shift_inheritance_and_prosody_v1",
        "lexicon_model": "twelve_proto_roots_ordered_rule_application_and_correspondence_v1",
        "diffusion_model": "era_staged_adoption_innovation_semantic_shift_v1",
        "speaker_model": "population_weighted_contact_allophony_reduction_and_adoption_v1",
        "annotation_model": "language_history_rule_lexicon_diffusion_and_speaker_backreferences_v1",
        "model_limitation": "synthetic_template_linguistics_without_empirical_language_calibration_individual_speaker_interaction_or_stochastic_transmission",
    }


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, value))


def _segment_features(segment: str) -> dict[str, str]:
    return dict(
        SEGMENT_FEATURES.get(
            segment, {"class": "cluster" if len(segment) > 1 else "segment"}
        )
    )


def _articulatory_shift(source: str, target: str) -> str:
    source_features = SEGMENT_FEATURES.get(source, {})
    target_features = SEGMENT_FEATURES.get(target, {})
    if (
        source_features.get("manner") != target_features.get("manner")
        and "manner" in source_features
    ):
        return "manner_shift"
    if (
        source_features.get("place") != target_features.get("place")
        and "place" in source_features
    ):
        return "place_shift"
    if (
        source_features.get("voicing") != target_features.get("voicing")
        and "voicing" in source_features
    ):
        return "voicing_shift"
    if (
        source_features.get("height") != target_features.get("height")
        and "height" in source_features
    ):
        return "vowel_height_shift"
    if (
        source_features.get("backness") != target_features.get("backness")
        and "backness" in source_features
    ):
        return "vowel_backness_shift"
    if len(source) != len(target):
        return "syllable_structure_shift"
    return "feature_shift"


def _prosodic_domain(environment: str) -> str:
    if "stressed" in environment:
        return "stressed_syllable"
    if "unstressed" in environment:
        return "unstressed_syllable"
    if "final" in environment or "coda" in environment:
        return "coda"
    if "onset" in environment:
        return "onset"
    if "vowel" in environment:
        return "vocalic_context"
    return "segmental_context"


def _syllable_pattern(form: str) -> str:
    pattern: list[str] = []
    previous = ""
    for char in form:
        marker = "V" if char in VOWELS else "C"
        if marker != previous:
            pattern.append(marker)
            previous = marker
    return "".join(pattern) or "C"


def _mora_count(form: str) -> int:
    vowel_count = sum(1 for char in form if char in VOWELS)
    long_vowels = sum(
        1 for left, right in zip(form, form[1:]) if left == right and left in VOWELS
    )
    final_coda = 1 if form and form[-1] not in VOWELS else 0
    return max(1, vowel_count + long_vowels + final_coda)


def _language_syllable_profile(
    language_id: int,
    lineage_depth: int,
    complexity: float,
    contact: float,
    isolation: float,
) -> dict[str, Any]:
    template_scores = [
        (0.22, "CV"),
        (0.42, "CVC"),
        (0.58, "CVV"),
        (0.74, "CCVC"),
        (1.01, "CVCC"),
    ]
    profile_score = _clamp(
        complexity * 0.50
        + contact * 0.18
        + isolation * 0.16
        + min(1.0, lineage_depth / 6.0) * 0.16
    )
    syllable_template = next(
        template for threshold, template in template_scores if profile_score <= threshold
    )
    if contact >= 0.72:
        stress_system = "mobile_contact_stress"
    elif profile_score >= 0.66:
        stress_system = "weight_sensitive"
    elif isolation >= 0.62:
        stress_system = "initial_stress"
    elif (language_id + lineage_depth) % 2 == 0:
        stress_system = "penultimate_stress"
    else:
        stress_system = "final_stress"
    allowed_coda_count = 1 + int(round(profile_score * 5.0))
    prosodic_complexity = _clamp(
        profile_score * 0.72
        + (0.10 if stress_system == "weight_sensitive" else 0.0)
        + contact * 0.08
    )
    return {
        "syllable_template": syllable_template,
        "stress_system": stress_system,
        "allowed_coda_count": allowed_coda_count,
        "prosodic_complexity_index": round(prosodic_complexity, 6),
        "phonotactic_complexity_index": round(profile_score, 6),
    }


def _apply_rule(form: str, rule: dict[str, Any]) -> tuple[str, bool]:
    source = str(rule.get("source_segment", ""))
    target = str(rule.get("target_segment", ""))
    environment = str(rule.get("environment", ""))
    if not source or source not in form:
        return form, False
    if environment == "word_final" and form.endswith(source):
        return form[: -len(source)] + target, True
    if environment in {"between_vowels", "after_vowels"}:
        vowels = set("aeiou")
        index = form.find(source)
        while index >= 0:
            before = form[index - 1] if index > 0 else ""
            after_index = index + len(source)
            after = form[after_index] if after_index < len(form) else ""
            if (
                environment == "between_vowels"
                and before in vowels
                and after in vowels
            ) or (environment == "after_vowels" and before in vowels):
                return form[:index] + target + form[index + len(source) :], True
            index = form.find(source, index + 1)
        return form, False
    if environment == "before_front_vowels":
        for vowel in ("i", "e"):
            pattern = source + vowel
            if pattern in form:
                return form.replace(pattern, target + vowel, 1), True
        return form, False
    return form.replace(source, target, 1), True


def _lexical_similarity(source_form: str, target_form: str) -> float:
    shared = sum(1 for left, right in zip(source_form, target_form) if left == right)
    return _clamp(shared / max(1, max(len(source_form), len(target_form))))


def _derive_form(
    proto_form: str, rules: list[dict[str, Any]]
) -> tuple[str, list[int], int]:
    form = proto_form
    applied_rule_ids: list[int] = []
    replacement_count = 0
    for rule in sorted(rules, key=lambda item: int(item.get("stage_index", 0))):
        next_form, applied = _apply_rule(form, rule)
        if applied:
            form = next_form
            applied_rule_ids.append(int(rule.get("id", -1)))
            replacement_count += 1
    return form, applied_rule_ids, replacement_count


def _sorted_eras(payload: dict[str, Any]) -> list[dict[str, Any]]:
    eras = payload.get("historical_eras", [])
    if not isinstance(eras, list) or not eras:
        return [
            {
                "id": 0,
                "start_year_bp": 1.0,
                "end_year_bp": 0.0,
                "dominant_process": "undated",
            }
        ]
    return sorted(
        eras,
        key=lambda era: (
            -float(era.get("start_year_bp", 0.0)),
            int(era.get("id", 0)),
        ),
    )


def _rule_count(language: dict[str, Any], era_count: int) -> int:
    change_rate = _clamp(float(language.get("change_rate", 0.0)))
    shift = _clamp(float(language.get("sound_shift_index", 0.0)))
    inherited = _clamp(float(language.get("inherited_phonology_fraction", 1.0)))
    contact = _clamp(float(language.get("trade_contact_index", 0.0)))
    isolation = _clamp(float(language.get("barrier_isolation", 0.0)))
    lineage_depth = max(0, int(language.get("lineage_depth", 0)))
    raw = 1 + int(
        round(
            change_rate * 4.0
            + shift * 3.0
            + (1.0 - inherited) * 2.0
            + lineage_depth * 0.6
        )
    )
    if contact >= 0.70:
        raw += 1
    if isolation >= 0.70:
        raw += 1
    return max(1, min(max(2, era_count + 2), raw))


def _population_weighted_mean(
    populations: list[dict[str, Any]], field: str
) -> float:
    weighted_sum = 0.0
    weight_sum = 0.0
    for population in populations:
        weight = max(0.0, float(population.get("estimated_population", 0.0)))
        weighted_sum += _clamp(float(population.get(field, 0.0))) * weight
        weight_sum += weight
    return weighted_sum / weight_sum if weight_sum else 0.0


def _expected_phonology_history(
    payload: dict[str, Any],
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[int, dict[str, Any]],
    dict[str, Any],
]:
    annotation_keys = (
        "phonological_history_id",
        "sound_change_rule_ids",
        "sound_change_rule_count",
        "final_phoneme_inventory_size",
        "phonological_drift_index",
        "syllable_template",
        "stress_system",
        "allowed_coda_count",
        "prosodic_complexity_index",
        "phonotactic_complexity_index",
        "lexical_correspondence_ids",
        "lexical_correspondence_count",
        "lexical_diffusion_history_id",
        "speaker_population_history_id",
    )
    languages = [dict(language) for language in payload["language_regions"]]
    for language in languages:
        for key in annotation_keys:
            language.pop(key, None)
    eras = _sorted_eras(payload)
    rules: list[dict[str, Any]] = []
    histories: list[dict[str, Any]] = []
    correspondences: list[dict[str, Any]] = []
    diffusion_histories: list[dict[str, Any]] = []
    speaker_histories: list[dict[str, Any]] = []
    drift_sum = 0.0
    prosodic_complexity_sum = 0.0
    phonotactic_complexity_sum = 0.0

    for language in languages:
        language_id = int(language.get("id", len(histories)))
        parent_id = int(language.get("parent_language_region_id", -1))
        lineage_depth = max(0, int(language.get("lineage_depth", 0)))
        final_inventory = max(1, int(language.get("phoneme_inventory_size", 24)))
        change_rate = _clamp(float(language.get("change_rate", 0.0)))
        shift = _clamp(float(language.get("sound_shift_index", 0.0)))
        inherited = _clamp(
            float(language.get("inherited_phonology_fraction", 1.0))
        )
        contact = _clamp(float(language.get("trade_contact_index", 0.0)))
        isolation = _clamp(float(language.get("barrier_isolation", 0.0)))
        complexity = _clamp(float(language.get("phonological_complexity", 0.0)))
        syllable_profile = _language_syllable_profile(
            language_id, lineage_depth, complexity, contact, isolation
        )
        drift = _clamp(
            shift * 0.54
            + change_rate * 0.26
            + (1.0 - inherited) * 0.14
            + isolation * 0.06
        )
        count = _rule_count(language, len(eras))
        chosen_templates = [
            RULE_TEMPLATES[
                (language_id * 5 + index * 3 + lineage_depth) % len(RULE_TEMPLATES)
            ]
            for index in range(count)
        ]
        net_inventory_delta = sum(int(template[5]) for template in chosen_templates)
        initial_inventory = max(8, min(72, final_inventory - net_inventory_delta))
        history_rule_ids: list[int] = []
        rule_ids_by_era: dict[int, list[int]] = {
            int(era.get("id", -1)): [] for era in eras
        }
        for index, template in enumerate(chosen_templates):
            era = eras[
                min(len(eras) - 1, int(index * len(eras) / max(1, count)))
            ]
            era_id = int(era.get("id", -1))
            stage_index = index + 1
            progress = stage_index / max(1, count)
            probability = _clamp(
                0.30
                + change_rate * 0.28
                + shift * 0.22
                + contact * 0.10
                + progress * 0.10
            )
            lexical_replacement = _clamp(
                (1.0 - inherited) * 0.34
                + contact * 0.22
                + change_rate * 0.24
                + progress * 0.10
            )
            regularity = _clamp(
                0.82
                - contact * 0.16
                - lexical_replacement * 0.08
                + isolation * 0.12
                + inherited * 0.10
            )
            contact_influence = _clamp(
                contact * 0.56
                + (1.0 - isolation) * 0.24
                + (0.10 if parent_id >= 0 else 0.0)
                + progress * 0.04
            )
            rule_id = len(rules)
            rules.append(
                {
                    "id": rule_id,
                    "language_region_id": language_id,
                    "parent_language_region_id": parent_id,
                    "era_id": era_id,
                    "stage_index": stage_index,
                    "rule_type": template[0],
                    "source_segment": template[1],
                    "target_segment": template[2],
                    "source_features": _segment_features(template[1]),
                    "target_features": _segment_features(template[2]),
                    "articulatory_shift": _articulatory_shift(template[1], template[2]),
                    "environment": template[3],
                    "conditioned_by": template[4],
                    "prosodic_domain": _prosodic_domain(template[3]),
                    "start_year_bp": round(float(era.get("start_year_bp", 0.0)), 6),
                    "end_year_bp": round(float(era.get("end_year_bp", 0.0)), 6),
                    "probability_index": round(probability, 6),
                    "regularity_index": round(regularity, 6),
                    "lexical_replacement_index": round(lexical_replacement, 6),
                    "contact_influence_index": round(contact_influence, 6),
                    "inventory_delta": int(template[5]),
                }
            )
            history_rule_ids.append(rule_id)
            rule_ids_by_era.setdefault(era_id, []).append(rule_id)

        steps: list[dict[str, Any]] = []
        for index, era in enumerate(eras):
            progress = (index + 1) / max(1, len(eras))
            era_id = int(era.get("id", -1))
            inventory_size = round(
                initial_inventory + (final_inventory - initial_inventory) * progress
            )
            steps.append(
                {
                    "era_id": era_id,
                    "stage_index": index + 1,
                    "start_year_bp": round(float(era.get("start_year_bp", 0.0)), 6),
                    "end_year_bp": round(float(era.get("end_year_bp", 0.0)), 6),
                    "rule_ids": rule_ids_by_era.get(era_id, []),
                    "rule_count": len(rule_ids_by_era.get(era_id, [])),
                    "inventory_size": int(inventory_size),
                    "cumulative_sound_shift_index": round(
                        _clamp(shift * progress), 6
                    ),
                    "inherited_phonology_fraction": round(
                        _clamp(1.0 - (1.0 - inherited) * progress), 6
                    ),
                    "contact_influence_index": round(
                        _clamp(
                            contact * 0.62
                            + (1.0 - isolation) * 0.18
                            + progress * 0.08
                        ),
                        6,
                    ),
                    "syllable_template": syllable_profile["syllable_template"],
                    "stress_system": syllable_profile["stress_system"],
                    "phonotactic_complexity_index": round(
                        _clamp(
                            float(syllable_profile["phonotactic_complexity_index"])
                            * (0.82 + progress * 0.18)
                        ),
                        6,
                    ),
                    "prosodic_weight_index": round(
                        _clamp(
                            float(syllable_profile["prosodic_complexity_index"])
                            * 0.68
                            + progress * 0.18
                        ),
                        6,
                    ),
                }
            )
        if steps:
            steps[-1]["inventory_size"] = final_inventory
            steps[-1]["cumulative_sound_shift_index"] = round(shift, 6)
            steps[-1]["inherited_phonology_fraction"] = round(inherited, 6)
        history_id = len(histories)
        histories.append(
            {
                "id": history_id,
                "language_region_id": language_id,
                "parent_language_region_id": parent_id,
                "initial_phoneme_inventory_size": initial_inventory,
                "final_phoneme_inventory_size": final_inventory,
                "sound_change_rule_ids": history_rule_ids,
                "sound_change_rule_count": len(history_rule_ids),
                "step_count": len(steps),
                "cumulative_sound_shift_index": round(shift, 6),
                "phonological_drift_index": round(drift, 6),
                "syllable_template": syllable_profile["syllable_template"],
                "stress_system": syllable_profile["stress_system"],
                "allowed_coda_count": syllable_profile["allowed_coda_count"],
                "prosodic_complexity_index": syllable_profile[
                    "prosodic_complexity_index"
                ],
                "phonotactic_complexity_index": syllable_profile[
                    "phonotactic_complexity_index"
                ],
                "steps": steps,
            }
        )
        language["phonological_history_id"] = history_id
        language["sound_change_rule_ids"] = history_rule_ids
        language["sound_change_rule_count"] = len(history_rule_ids)
        language["final_phoneme_inventory_size"] = final_inventory
        language["phonological_drift_index"] = round(drift, 6)
        language["syllable_template"] = syllable_profile["syllable_template"]
        language["stress_system"] = syllable_profile["stress_system"]
        language["allowed_coda_count"] = syllable_profile["allowed_coda_count"]
        language["prosodic_complexity_index"] = syllable_profile[
            "prosodic_complexity_index"
        ]
        language["phonotactic_complexity_index"] = syllable_profile[
            "phonotactic_complexity_index"
        ]
        drift_sum += drift
        prosodic_complexity_sum += float(
            syllable_profile["prosodic_complexity_index"]
        )
        phonotactic_complexity_sum += float(
            syllable_profile["phonotactic_complexity_index"]
        )

    rules_by_language_id: dict[int, list[dict[str, Any]]] = {}
    for rule in rules:
        rules_by_language_id.setdefault(
            int(rule.get("language_region_id", -1)), []
        ).append(rule)
    for language in languages:
        language_id = int(language.get("id", -1))
        parent_id = int(language.get("parent_language_region_id", -1))
        lineage_depth = max(0, int(language.get("lineage_depth", 0)))
        language_rules = rules_by_language_id.get(language_id, [])
        replacement_pressure = _clamp(
            float(language.get("change_rate", 0.0)) * 0.44
            + (1.0 - float(language.get("inherited_phonology_fraction", 1.0)))
            * 0.36
            + float(language.get("trade_contact_index", 0.0)) * 0.20
        )
        contact = _clamp(float(language.get("trade_contact_index", 0.0)))
        inherited = _clamp(
            float(language.get("inherited_phonology_fraction", 1.0))
        )
        correspondence_ids: list[int] = []
        for index, (meaning, proto_form, semantic_domain) in enumerate(LEXICAL_ROOTS):
            inherited_proto = (
                proto_form
                if parent_id < 0
                else f"{proto_form}{'i' if (language_id + index) % 2 == 0 else 'a'}"
            )
            derived_form, applied_rule_ids, replacement_count = _derive_form(
                inherited_proto, language_rules
            )
            if not applied_rule_ids and replacement_pressure > 0.42 and derived_form:
                vowel_index = next(
                    (
                        position
                        for position, char in enumerate(derived_form)
                        if char in "aeiou"
                    ),
                    -1,
                )
                if vowel_index >= 0:
                    replacement = "e" if derived_form[vowel_index] != "e" else "a"
                    derived_form = (
                        derived_form[:vowel_index]
                        + replacement
                        + derived_form[vowel_index + 1 :]
                    )
                    replacement_count += 1
            similarity = _lexical_similarity(inherited_proto, derived_form)
            retention = _clamp(
                similarity * 0.62
                + float(language.get("inherited_phonology_fraction", 1.0)) * 0.28
                + (1.0 - replacement_pressure) * 0.10
            )
            stress_pattern = (
                "initial"
                if (language_id + index + lineage_depth) % 3 == 0
                else "penultimate"
            )
            syllable_count = max(
                1, sum(1 for char in derived_form if char in "aeiou")
            )
            diffusion_stage = 1 + min(
                len(eras) - 1,
                int(index * len(eras) / max(1, len(LEXICAL_ROOTS))),
            )
            diffusion_adoption = _clamp(
                retention * 0.44
                + (1.0 - replacement_pressure) * 0.22
                + contact * 0.14
                + (len(applied_rule_ids) / max(1, len(language_rules))) * 0.20
            )
            semantic_shift = _clamp(
                (1.0 - retention) * 0.48 + contact * 0.20 + (index % 4) * 0.04
            )
            correspondence = {
                "id": len(correspondences),
                "language_region_id": language_id,
                "parent_language_region_id": parent_id,
                "meaning": meaning,
                "semantic_domain": semantic_domain,
                "proto_form": proto_form,
                "inherited_form": inherited_proto,
                "derived_form": derived_form,
                "applied_rule_ids": applied_rule_ids,
                "applied_rule_count": len(applied_rule_ids),
                "replacement_count": replacement_count,
                "regular_correspondence_fraction": round(retention, 6),
                "lexical_replacement_index": round(_clamp(1.0 - retention), 6),
                "stress_pattern": stress_pattern,
                "syllable_count": syllable_count,
                "syllable_pattern": _syllable_pattern(derived_form),
                "mora_count": _mora_count(derived_form),
                "prosodic_weight_index": round(
                    _clamp(
                        syllable_count / 5.0
                        + (0.08 if stress_pattern == "initial" else 0.0)
                    ),
                    6,
                ),
                "diffusion_stage_index": diffusion_stage,
                "diffusion_adoption_index": round(diffusion_adoption, 6),
                "semantic_shift_index": round(semantic_shift, 6),
                "borrowed": bool(
                    parent_id >= 0
                    and contact >= 0.62
                    and semantic_shift >= 0.34
                    and retention < inherited
                ),
            }
            correspondence_ids.append(correspondence["id"])
            correspondences.append(correspondence)
        language["lexical_correspondence_ids"] = correspondence_ids
        language["lexical_correspondence_count"] = len(correspondence_ids)
        diffusion_steps: list[dict[str, Any]] = []
        for index, era in enumerate(eras):
            stage_index = index + 1
            affected_records = [
                correspondences[record_id]
                for record_id in correspondence_ids
                if int(correspondences[record_id].get("diffusion_stage_index", 0))
                <= stage_index
            ]
            affected_ids = [int(record.get("id", -1)) for record in affected_records]
            affected_domains = {
                str(record.get("semantic_domain", ""))
                for record in affected_records
                if str(record.get("semantic_domain", "")).strip()
            }
            adoption = (
                sum(
                    float(record.get("diffusion_adoption_index", 0.0))
                    for record in affected_records
                )
                / len(affected_records)
                if affected_records
                else 0.0
            )
            innovation = (
                sum(
                    float(record.get("lexical_replacement_index", 0.0))
                    for record in affected_records
                )
                / len(affected_records)
                if affected_records
                else 0.0
            )
            semantic_shift = (
                sum(
                    float(record.get("semantic_shift_index", 0.0))
                    for record in affected_records
                )
                / len(affected_records)
                if affected_records
                else 0.0
            )
            progress = stage_index / max(1, len(eras))
            diffusion_steps.append(
                {
                    "era_id": int(era.get("id", -1)),
                    "stage_index": stage_index,
                    "start_year_bp": round(float(era.get("start_year_bp", 0.0)), 6),
                    "end_year_bp": round(float(era.get("end_year_bp", 0.0)), 6),
                    "affected_correspondence_ids": affected_ids,
                    "affected_correspondence_count": len(affected_ids),
                    "affected_meanings": [
                        str(record.get("meaning", "")) for record in affected_records
                    ],
                    "affected_domain_count": len(affected_domains),
                    "adoption_fraction": round(_clamp(adoption), 6),
                    "innovation_fraction": round(_clamp(innovation), 6),
                    "contact_borrowing_index": round(
                        _clamp(
                            contact * 0.52
                            + (1.0 - inherited) * 0.22
                            + progress * 0.08
                        ),
                        6,
                    ),
                    "regularization_index": round(
                        _clamp(1.0 - innovation * 0.62 + inherited * 0.18), 6
                    ),
                    "semantic_shift_index": round(_clamp(semantic_shift), 6),
                }
            )
        diffusion_history_id = len(diffusion_histories)
        mean_adoption = (
            sum(float(step.get("adoption_fraction", 0.0)) for step in diffusion_steps)
            / len(diffusion_steps)
            if diffusion_steps
            else 0.0
        )
        mean_innovation = (
            sum(
                float(step.get("innovation_fraction", 0.0)) for step in diffusion_steps
            )
            / len(diffusion_steps)
            if diffusion_steps
            else 0.0
        )
        mean_semantic_shift = (
            sum(
                float(step.get("semantic_shift_index", 0.0))
                for step in diffusion_steps
            )
            / len(diffusion_steps)
            if diffusion_steps
            else 0.0
        )
        diffusion_histories.append(
            {
                "id": diffusion_history_id,
                "language_region_id": language_id,
                "parent_language_region_id": parent_id,
                "phonological_history_id": int(
                    language.get("phonological_history_id", -1)
                ),
                "lexical_correspondence_ids": correspondence_ids,
                "lexical_correspondence_count": len(correspondence_ids),
                "step_count": len(diffusion_steps),
                "syllable_template": language.get("syllable_template", ""),
                "stress_system": language.get("stress_system", ""),
                "mean_diffusion_adoption_index": round(_clamp(mean_adoption), 6),
                "mean_lexical_innovation_index": round(_clamp(mean_innovation), 6),
                "mean_semantic_shift_index": round(
                    _clamp(mean_semantic_shift), 6
                ),
                "contact_borrowing_index": round(
                    _clamp(contact * 0.58 + (1.0 - inherited) * 0.24), 6
                ),
                "steps": diffusion_steps,
            }
        )
        language["lexical_diffusion_history_id"] = diffusion_history_id

    populations_by_language: dict[int, list[dict[str, Any]]] = {}
    for population in payload["population_regions"]:
        if not isinstance(population, dict):
            continue
        population_language_id = int(population.get("language_region_id", -1))
        if population_language_id >= 0:
            populations_by_language.setdefault(population_language_id, []).append(
                population
            )
    history_by_language = {
        int(history.get("language_region_id", -1)): history for history in histories
    }
    diffusion_by_language = {
        int(history.get("language_region_id", -1)): history
        for history in diffusion_histories
    }
    total_known_population = sum(
        max(0.0, float(population.get("estimated_population", 0.0)))
        for populations in populations_by_language.values()
        for population in populations
    )
    speaker_allophony_sum = 0.0
    speaker_syllable_sum = 0.0
    speaker_contact_sum = 0.0
    speaker_adoption_sum = 0.0
    speaker_reduction_sum = 0.0
    speaker_lexical_pressure_sum = 0.0
    total_estimated_speakers = 0.0
    high_contact_speaker_count = 0

    for language in languages:
        language_id = int(language.get("id", -1))
        parent_id = int(language.get("parent_language_region_id", -1))
        phonological_history = history_by_language.get(language_id, {})
        lexical_diffusion_history = diffusion_by_language.get(language_id, {})
        matched_populations = populations_by_language.get(language_id, [])
        population_ids = [
            int(population.get("id", -1))
            for population in matched_populations
            if int(population.get("id", -1)) >= 0
        ]
        primary_population = max(
            matched_populations,
            key=lambda population: float(population.get("estimated_population", 0.0)),
            default={},
        )
        estimated_speakers = sum(
            max(0.0, float(population.get("estimated_population", 0.0)))
            for population in matched_populations
        )
        if estimated_speakers <= 0.0:
            estimated_speakers = max(
                1.0, float(language.get("area_km2", 0.0)) * 0.5
            )
        contact = _clamp(float(language.get("trade_contact_index", 0.0)))
        inherited = _clamp(
            float(language.get("inherited_phonology_fraction", 1.0))
        )
        drift = _clamp(float(language.get("phonological_drift_index", 0.0)))
        change_rate = _clamp(float(language.get("change_rate", 0.0)))
        phonotactic = _clamp(
            float(language.get("phonotactic_complexity_index", 0.0))
        )
        prosodic = _clamp(float(language.get("prosodic_complexity_index", 0.0)))
        population_pressure = _population_weighted_mean(
            matched_populations, "population_pressure"
        )
        urbanization = _population_weighted_mean(
            matched_populations, "urbanization_fraction"
        )
        migration_balance = _population_weighted_mean(
            matched_populations, "migration_balance"
        )
        initial_speakers = estimated_speakers * _clamp(
            0.70
            + inherited * 0.10
            - drift * 0.08
            - abs(migration_balance) * 0.06,
            0.45,
            0.95,
        )
        phonology_steps = (
            phonological_history.get("steps", [])
            if isinstance(phonological_history.get("steps", []), list)
            else []
        )
        diffusion_steps = (
            lexical_diffusion_history.get("steps", [])
            if isinstance(lexical_diffusion_history.get("steps", []), list)
            else []
        )
        speaker_steps: list[dict[str, Any]] = []
        for index, era in enumerate(eras):
            stage_index = index + 1
            progress = stage_index / max(1, len(eras))
            phonology_step = (
                phonology_steps[min(index, len(phonology_steps) - 1)]
                if phonology_steps
                else {}
            )
            diffusion_step = (
                diffusion_steps[min(index, len(diffusion_steps) - 1)]
                if diffusion_steps
                else {}
            )
            speaker_population = (
                initial_speakers + (estimated_speakers - initial_speakers) * progress
            )
            speaker_fraction = _clamp(
                speaker_population
                / max(total_known_population, estimated_speakers, 1.0)
            )
            contact_pressure = _clamp(
                float(phonology_step.get("contact_influence_index", contact)) * 0.40
                + float(diffusion_step.get("contact_borrowing_index", contact)) * 0.32
                + contact * 0.18
                + abs(migration_balance) * 0.10
            )
            lexical_pressure = _clamp(
                float(diffusion_step.get("adoption_fraction", 0.0)) * 0.34
                + float(diffusion_step.get("innovation_fraction", 0.0)) * 0.32
                + float(diffusion_step.get("semantic_shift_index", 0.0)) * 0.20
                + contact_pressure * 0.14
            )
            syllable_pressure = _clamp(
                phonotactic * 0.30
                + prosodic * 0.24
                + min(1.0, float(language.get("allowed_coda_count", 1)) / 6.0)
                * 0.18
                + float(
                    phonology_step.get("prosodic_weight_index", prosodic)
                )
                * 0.18
                + lexical_pressure * 0.10
            )
            phonetic_reduction = _clamp(
                change_rate * 0.28
                + syllable_pressure * 0.22
                + contact_pressure * 0.18
                + urbanization * 0.16
                + progress * 0.08
                + (1.0 - inherited) * 0.08
            )
            allophonic_variation = _clamp(
                phonetic_reduction * 0.28
                + contact_pressure * 0.24
                + phonotactic * 0.18
                + drift * 0.16
                + speaker_fraction * 0.08
                + (1.0 - inherited) * 0.06
            )
            population_adoption = _clamp(
                speaker_fraction * 0.24
                + float(diffusion_step.get("adoption_fraction", 0.0)) * 0.30
                + float(diffusion_step.get("regularization_index", 0.0)) * 0.20
                + (1.0 - population_pressure) * 0.10
                + urbanization * 0.08
                + progress * 0.08
            )
            register_divergence = _clamp(
                contact_pressure * 0.30
                + urbanization * 0.26
                + population_pressure * 0.18
                + speaker_fraction * 0.14
                + syllable_pressure * 0.12
            )
            pronunciation_regularization = _clamp(
                float(diffusion_step.get("regularization_index", inherited)) * 0.46
                + inherited * 0.22
                + (1.0 - allophonic_variation) * 0.18
                + (1.0 - contact_pressure) * 0.14
            )
            speaker_steps.append(
                {
                    "era_id": int(era.get("id", -1)),
                    "stage_index": stage_index,
                    "start_year_bp": round(float(era.get("start_year_bp", 0.0)), 6),
                    "end_year_bp": round(float(era.get("end_year_bp", 0.0)), 6),
                    "speaker_population": round(speaker_population, 6),
                    "speaker_fraction_index": round(speaker_fraction, 6),
                    "allophonic_variation_index": round(allophonic_variation, 6),
                    "syllable_pressure_index": round(syllable_pressure, 6),
                    "phonetic_reduction_index": round(phonetic_reduction, 6),
                    "contact_pressure_index": round(contact_pressure, 6),
                    "lexical_diffusion_pressure_index": round(lexical_pressure, 6),
                    "population_adoption_index": round(population_adoption, 6),
                    "register_divergence_index": round(register_divergence, 6),
                    "pronunciation_regularization_index": round(
                        pronunciation_regularization, 6
                    ),
                }
            )
        if speaker_steps:
            speaker_steps[-1]["speaker_population"] = round(estimated_speakers, 6)
        step_divisor = len(speaker_steps) if speaker_steps else 1
        mean_allophony = (
            sum(
                float(step.get("allophonic_variation_index", 0.0))
                for step in speaker_steps
            )
            / step_divisor
            if speaker_steps
            else 0.0
        )
        mean_syllable = (
            sum(
                float(step.get("syllable_pressure_index", 0.0))
                for step in speaker_steps
            )
            / step_divisor
            if speaker_steps
            else 0.0
        )
        mean_contact = (
            sum(
                float(step.get("contact_pressure_index", 0.0))
                for step in speaker_steps
            )
            / step_divisor
            if speaker_steps
            else 0.0
        )
        mean_adoption = (
            sum(
                float(step.get("population_adoption_index", 0.0))
                for step in speaker_steps
            )
            / step_divisor
            if speaker_steps
            else 0.0
        )
        mean_reduction = (
            sum(
                float(step.get("phonetic_reduction_index", 0.0))
                for step in speaker_steps
            )
            / step_divisor
            if speaker_steps
            else 0.0
        )
        mean_lexical_pressure = (
            sum(
                float(step.get("lexical_diffusion_pressure_index", 0.0))
                for step in speaker_steps
            )
            / step_divisor
            if speaker_steps
            else 0.0
        )
        high_contact = mean_contact >= 0.65 or any(
            float(step.get("contact_pressure_index", 0.0)) >= 0.75
            for step in speaker_steps
        )
        speaker_history_id = len(speaker_histories)
        speaker_histories.append(
            {
                "id": speaker_history_id,
                "language_region_id": language_id,
                "parent_language_region_id": parent_id,
                "population_region_id": int(primary_population.get("id", -1)),
                "population_region_ids": population_ids,
                "population_region_count": len(population_ids),
                "phonological_history_id": int(
                    language.get("phonological_history_id", -1)
                ),
                "lexical_diffusion_history_id": int(
                    language.get("lexical_diffusion_history_id", -1)
                ),
                "initial_speaker_population": round(initial_speakers, 6),
                "final_speaker_population": round(estimated_speakers, 6),
                "estimated_speaker_population": round(estimated_speakers, 6),
                "mean_allophonic_variation_index": round(
                    _clamp(mean_allophony), 6
                ),
                "mean_syllable_pressure_index": round(_clamp(mean_syllable), 6),
                "mean_speaker_contact_index": round(_clamp(mean_contact), 6),
                "mean_population_adoption_index": round(_clamp(mean_adoption), 6),
                "mean_phonetic_reduction_index": round(_clamp(mean_reduction), 6),
                "mean_lexical_diffusion_pressure_index": round(
                    _clamp(mean_lexical_pressure), 6
                ),
                "high_contact_speaker_history": bool(high_contact),
                "step_count": len(speaker_steps),
                "steps": speaker_steps,
            }
        )
        language["speaker_population_history_id"] = speaker_history_id
        speaker_allophony_sum += mean_allophony
        speaker_syllable_sum += mean_syllable
        speaker_contact_sum += mean_contact
        speaker_adoption_sum += mean_adoption
        speaker_reduction_sum += mean_reduction
        speaker_lexical_pressure_sum += mean_lexical_pressure
        total_estimated_speakers += estimated_speakers
        high_contact_speaker_count += int(high_contact)

    rule_count = len(rules)
    history_count = len(histories)
    lexical_count = len(correspondences)
    diffusion_count = len(diffusion_histories)
    speaker_count = len(speaker_histories)
    summary = {
        "phonological_history_count": history_count,
        "phonological_history_step_count": sum(
            int(history.get("step_count", 0)) for history in histories
        ),
        "phonological_rule_count": rule_count,
        "phonological_rule_language_count": sum(
            1
            for language in languages
            if int(language.get("sound_change_rule_count", 0)) > 0
        ),
        "max_phonological_shift_stage": max(
            (int(rule.get("stage_index", 0)) for rule in rules), default=0
        ),
        "mean_phonological_rule_probability_index": round(
            sum(float(rule.get("probability_index", 0.0)) for rule in rules)
            / rule_count,
            6,
        )
        if rule_count
        else 0.0,
        "mean_phonological_rule_regularity_index": round(
            sum(float(rule.get("regularity_index", 0.0)) for rule in rules)
            / rule_count,
            6,
        )
        if rule_count
        else 0.0,
        "mean_lexical_replacement_index": round(
            sum(float(rule.get("lexical_replacement_index", 0.0)) for rule in rules)
            / rule_count,
            6,
        )
        if rule_count
        else 0.0,
        "mean_phonological_contact_influence_index": round(
            sum(float(rule.get("contact_influence_index", 0.0)) for rule in rules)
            / rule_count,
            6,
        )
        if rule_count
        else 0.0,
        "mean_phonological_drift_index": round(drift_sum / history_count, 6)
        if history_count
        else 0.0,
        "mean_language_prosodic_complexity_index": round(
            prosodic_complexity_sum / history_count, 6
        )
        if history_count
        else 0.0,
        "mean_phonotactic_complexity_index": round(
            phonotactic_complexity_sum / history_count, 6
        )
        if history_count
        else 0.0,
        "lexical_correspondence_count": lexical_count,
        "lexical_correspondence_language_count": sum(
            1
            for language in languages
            if int(language.get("lexical_correspondence_count", 0)) > 0
        ),
        "lexical_diffusion_history_count": diffusion_count,
        "lexical_diffusion_step_count": sum(
            int(history.get("step_count", 0)) for history in diffusion_histories
        ),
        "lexical_diffusion_language_count": sum(
            1
            for language in languages
            if int(language.get("lexical_diffusion_history_id", -1)) >= 0
        ),
        "mean_regular_correspondence_fraction": round(
            sum(
                float(record.get("regular_correspondence_fraction", 0.0))
                for record in correspondences
            )
            / lexical_count,
            6,
        )
        if lexical_count
        else 0.0,
        "mean_lexical_correspondence_replacement_index": round(
            sum(
                float(record.get("lexical_replacement_index", 0.0))
                for record in correspondences
            )
            / lexical_count,
            6,
        )
        if lexical_count
        else 0.0,
        "mean_lexical_prosodic_weight_index": round(
            sum(
                float(record.get("prosodic_weight_index", 0.0))
                for record in correspondences
            )
            / lexical_count,
            6,
        )
        if lexical_count
        else 0.0,
        "mean_lexical_diffusion_adoption_index": round(
            sum(
                float(history.get("mean_diffusion_adoption_index", 0.0))
                for history in diffusion_histories
            )
            / diffusion_count,
            6,
        )
        if diffusion_count
        else 0.0,
        "mean_lexical_innovation_index": round(
            sum(
                float(history.get("mean_lexical_innovation_index", 0.0))
                for history in diffusion_histories
            )
            / diffusion_count,
            6,
        )
        if diffusion_count
        else 0.0,
        "mean_semantic_shift_index": round(
            sum(
                float(history.get("mean_semantic_shift_index", 0.0))
                for history in diffusion_histories
            )
            / diffusion_count,
            6,
        )
        if diffusion_count
        else 0.0,
        "speaker_population_history_count": speaker_count,
        "speaker_population_step_count": sum(
            int(history.get("step_count", 0)) for history in speaker_histories
        ),
        "total_estimated_speaker_population": round(total_estimated_speakers, 6),
        "mean_speaker_allophonic_variation_index": round(
            speaker_allophony_sum / speaker_count, 6
        )
        if speaker_count
        else 0.0,
        "mean_speaker_syllable_pressure_index": round(
            speaker_syllable_sum / speaker_count, 6
        )
        if speaker_count
        else 0.0,
        "mean_speaker_contact_index": round(speaker_contact_sum / speaker_count, 6)
        if speaker_count
        else 0.0,
        "mean_speaker_population_adoption_index": round(
            speaker_adoption_sum / speaker_count, 6
        )
        if speaker_count
        else 0.0,
        "mean_speaker_phonetic_reduction_index": round(
            speaker_reduction_sum / speaker_count, 6
        )
        if speaker_count
        else 0.0,
        "mean_speaker_lexical_diffusion_pressure_index": round(
            speaker_lexical_pressure_sum / speaker_count, 6
        )
        if speaker_count
        else 0.0,
        "high_contact_speaker_history_count": high_contact_speaker_count,
    }
    language_annotations = {
        int(language.get("id", -1)): {
            key: language[key] for key in annotation_keys if key in language
        }
        for language in languages
        if int(language.get("id", -1)) >= 0
    }
    return (
        rules,
        histories,
        correspondences,
        diffusion_histories,
        speaker_histories,
        language_annotations,
        summary,
    )


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


def validate_phonology_history_replay(payload: dict[str, Any]) -> list[str]:
    try:
        summary = payload.get("summary", {})
        required_lists = (
            "language_regions",
            "historical_eras",
            "population_regions",
            "phonological_rules",
            "phonological_histories",
            "lexical_correspondences",
            "lexical_diffusion_histories",
            "speaker_population_histories",
        )
        valid = isinstance(summary, dict) and all(
            isinstance(payload.get(name), list) for name in required_lists
        )
        valid = valid and payload.get("phonology_history_model") == _phonology_history_model()
        valid = valid and summary.get("phonology_history_model") == PHONOLOGY_HISTORY_MODEL
        (
            rules,
            histories,
            correspondences,
            diffusion_histories,
            speaker_histories,
            language_annotations,
            expected_summary,
        ) = _expected_phonology_history(payload)
        valid = valid and _contains_expected(payload.get("phonological_rules"), rules)
        valid = valid and _contains_expected(payload.get("phonological_histories"), histories)
        valid = valid and _contains_expected(
            payload.get("lexical_correspondences"), correspondences
        )
        valid = valid and _contains_expected(
            payload.get("lexical_diffusion_histories"), diffusion_histories
        )
        valid = valid and _contains_expected(
            payload.get("speaker_population_histories"), speaker_histories
        )
        valid = valid and all(
            summary.get(key) == value for key, value in expected_summary.items()
        )
        languages_by_id = {
            int(language.get("id", -1)): language
            for language in payload["language_regions"]
        }
        valid = valid and all(
            language_id in languages_by_id
            and _contains_expected(languages_by_id[language_id], annotations)
            for language_id, annotations in language_annotations.items()
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
    return [] if valid else ["phonology history model or causal replay invalid"]
