"""Successor speaker availability; unchanged independent structural equations.

Legacy implementation remains in its original module. No missing population
is replaced by an area proxy, and no unavailable weighted input is evaluated.
"""
from __future__ import annotations
from typing import Any
from .phonology_history_validation import (LEXICAL_ROOTS,
    RULE_TEMPLATES,
    _articulatory_shift,
    _clamp,
    _derive_form,
    _language_syllable_profile,
    _lexical_similarity,
    _mora_count,
    _population_weighted_mean,
    _prosodic_domain,
    _rule_count,
    _segment_features,
    _sorted_eras,
    _syllable_pattern)

def _nullable_round(value, places=6):
    return round(value, places) if value is not None else None

def _nullable_clamp(value):
    return _clamp(value) if value is not None else None

def _finalize_speakers(records, summary):
    count_fields = {"initial_speaker_population", "final_speaker_population", "estimated_speaker_population"}
    local_means = {"mean_syllable_pressure_index", "mean_speaker_contact_index", "mean_phonetic_reduction_index", "mean_lexical_diffusion_pressure_index"}
    global_means = {"mean_allophonic_variation_index", "mean_population_adoption_index"}
    for record in records:
        fields = count_fields | local_means | global_means | {"population_region_id", "high_contact_speaker_history"}
        record["estimate_availability"] = {key: record[key] is not None for key in sorted(fields)}
        record["estimate_available"] = all(record["estimate_availability"].values())
        for step in record["steps"]:
            fields = set(step) - {"era_id", "stage_index", "start_year_bp", "end_year_bp"}
            step["estimate_availability"] = {key: step[key] is not None for key in sorted(fields)}
            step["estimate_available"] = all(step["estimate_availability"].values())
    associations = {
        "total_estimated_speaker_population": "estimated_speaker_population",
        "mean_speaker_allophonic_variation_index": "mean_allophonic_variation_index",
        "mean_speaker_syllable_pressure_index": "mean_syllable_pressure_index",
        "mean_speaker_contact_index": "mean_speaker_contact_index",
        "mean_speaker_population_adoption_index": "mean_population_adoption_index",
        "mean_speaker_phonetic_reduction_index": "mean_phonetic_reduction_index",
        "mean_speaker_lexical_diffusion_pressure_index": "mean_lexical_diffusion_pressure_index",
        "high_contact_speaker_history_count": "high_contact_speaker_history",
    }
    flags = {key: all(r[field] is not None for r in records) for key, field in associations.items()}
    for key, available in flags.items():
        if not available: summary[key] = None
    summary["speaker_history_summary_availability"] = flags
    summary["available_speaker_population_history_count"] = sum(r["estimate_available"] for r in records)
    summary["available_speaker_population_step_count"] = sum(s["estimate_available"] for r in records for s in r["steps"])


def _expected(payload: dict[str,
    Any]) -> tuple[list[dict[str,
    Any]],
    list[dict[str,
    Any]],
    list[dict[str,
    Any]],
    list[dict[str,
    Any]],
    list[dict[str,
    Any]],
    dict[int,
    dict[str,
    Any]],
    dict[str,
    Any]]:
    annotation_keys = ('phonological_history_id',
        'sound_change_rule_ids',
        'sound_change_rule_count',
        'final_phoneme_inventory_size',
        'phonological_drift_index',
        'syllable_template',
        'stress_system',
        'allowed_coda_count',
        'prosodic_complexity_index',
        'phonotactic_complexity_index',
        'lexical_correspondence_ids',
        'lexical_correspondence_count',
        'lexical_diffusion_history_id',
        'speaker_population_history_id')
    languages = [dict(language) for language in payload['language_regions']]
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
        language_id = int(language.get('id', len(histories)))
        parent_id = int(language.get('parent_language_region_id', -1))
        lineage_depth = max(0, int(language.get('lineage_depth', 0)))
        final_inventory = max(1, int(language.get('phoneme_inventory_size', 24)))
        change_rate = _clamp(float(language.get('change_rate', 0.0)))
        shift = _clamp(float(language.get('sound_shift_index', 0.0)))
        inherited = _clamp(float(language.get('inherited_phonology_fraction', 1.0)))
        contact = _clamp(float(language.get('trade_contact_index', 0.0)))
        isolation = _clamp(float(language.get('barrier_isolation', 0.0)))
        complexity = _clamp(float(language.get('phonological_complexity', 0.0)))
        syllable_profile = _language_syllable_profile(language_id, lineage_depth, complexity, contact, isolation)
        drift = _clamp(shift * 0.54 + change_rate * 0.26 + (1.0 - inherited) * 0.14 + isolation * 0.06)
        count = _rule_count(language, len(eras))
        chosen_templates = [RULE_TEMPLATES[(language_id * 5 + index * 3 + lineage_depth) % len(RULE_TEMPLATES)] for index in range(count)]
        net_inventory_delta = sum((int(template[5]) for template in chosen_templates))
        initial_inventory = max(8, min(72, final_inventory - net_inventory_delta))
        history_rule_ids: list[int] = []
        rule_ids_by_era: dict[int, list[int]] = {int(era.get('id', -1)): [] for era in eras}
        for index, template in enumerate(chosen_templates):
            era = eras[min(len(eras) - 1, int(index * len(eras) / max(1, count)))]
            era_id = int(era.get('id', -1))
            stage_index = index + 1
            progress = stage_index / max(1, count)
            probability = _clamp(0.3 + change_rate * 0.28 + shift * 0.22 + contact * 0.1 + progress * 0.1)
            lexical_replacement = _clamp((1.0 - inherited) * 0.34 + contact * 0.22 + change_rate * 0.24 + progress * 0.1)
            regularity = _clamp(0.82 - contact * 0.16 - lexical_replacement * 0.08 + isolation * 0.12 + inherited * 0.1)
            contact_influence = _clamp(contact * 0.56 + (1.0 - isolation) * 0.24 + (0.1 if parent_id >= 0 else 0.0) + progress * 0.04)
            rule_id = len(rules)
            rules.append({'id': rule_id,
                'language_region_id': language_id,
                'parent_language_region_id': parent_id,
                'era_id': era_id,
                'stage_index': stage_index,
                'rule_type': template[0],
                'source_segment': template[1],
                'target_segment': template[2],
                'source_features': _segment_features(template[1]),
                'target_features': _segment_features(template[2]),
                'articulatory_shift': _articulatory_shift(template[1],
                template[2]),
                'environment': template[3],
                'conditioned_by': template[4],
                'prosodic_domain': _prosodic_domain(template[3]),
                'start_year_bp': round(float(era.get('start_year_bp',
                0.0)),
                6),
                'end_year_bp': round(float(era.get('end_year_bp',
                0.0)),
                6),
                'probability_index': round(probability,
                6),
                'regularity_index': round(regularity,
                6),
                'lexical_replacement_index': round(lexical_replacement,
                6),
                'contact_influence_index': round(contact_influence,
                6),
                'inventory_delta': int(template[5])})
            history_rule_ids.append(rule_id)
            rule_ids_by_era.setdefault(era_id, []).append(rule_id)
        steps: list[dict[str, Any]] = []
        for index, era in enumerate(eras):
            progress = (index + 1) / max(1, len(eras))
            era_id = int(era.get('id', -1))
            inventory_size = round(initial_inventory + (final_inventory - initial_inventory) * progress)
            steps.append({'era_id': era_id,
                'stage_index': index + 1,
                'start_year_bp': round(float(era.get('start_year_bp',
                0.0)),
                6),
                'end_year_bp': round(float(era.get('end_year_bp',
                0.0)),
                6),
                'rule_ids': rule_ids_by_era.get(era_id,
                []),
                'rule_count': len(rule_ids_by_era.get(era_id,
                [])),
                'inventory_size': int(inventory_size),
                'cumulative_sound_shift_index': round(_clamp(shift * progress),
                6),
                'inherited_phonology_fraction': round(_clamp(1.0 - (1.0 - inherited) * progress),
                6),
                'contact_influence_index': round(_clamp(contact * 0.62 + (1.0 - isolation) * 0.18 + progress * 0.08),
                6),
                'syllable_template': syllable_profile['syllable_template'],
                'stress_system': syllable_profile['stress_system'],
                'phonotactic_complexity_index': round(_clamp(float(syllable_profile['phonotactic_complexity_index']) * (0.82 + progress * 0.18)),
                6),
                'prosodic_weight_index': round(_clamp(float(syllable_profile['prosodic_complexity_index']) * 0.68 + progress * 0.18),
                6)})
        if steps:
            steps[-1]['inventory_size'] = final_inventory
            steps[-1]['cumulative_sound_shift_index'] = round(shift, 6)
            steps[-1]['inherited_phonology_fraction'] = round(inherited, 6)
        history_id = len(histories)
        histories.append({'id': history_id,
            'language_region_id': language_id,
            'parent_language_region_id': parent_id,
            'initial_phoneme_inventory_size': initial_inventory,
            'final_phoneme_inventory_size': final_inventory,
            'sound_change_rule_ids': history_rule_ids,
            'sound_change_rule_count': len(history_rule_ids),
            'step_count': len(steps),
            'cumulative_sound_shift_index': round(shift,
            6),
            'phonological_drift_index': round(drift,
            6),
            'syllable_template': syllable_profile['syllable_template'],
            'stress_system': syllable_profile['stress_system'],
            'allowed_coda_count': syllable_profile['allowed_coda_count'],
            'prosodic_complexity_index': syllable_profile['prosodic_complexity_index'],
            'phonotactic_complexity_index': syllable_profile['phonotactic_complexity_index'],
            'steps': steps})
        language['phonological_history_id'] = history_id
        language['sound_change_rule_ids'] = history_rule_ids
        language['sound_change_rule_count'] = len(history_rule_ids)
        language['final_phoneme_inventory_size'] = final_inventory
        language['phonological_drift_index'] = round(drift, 6)
        language['syllable_template'] = syllable_profile['syllable_template']
        language['stress_system'] = syllable_profile['stress_system']
        language['allowed_coda_count'] = syllable_profile['allowed_coda_count']
        language['prosodic_complexity_index'] = syllable_profile['prosodic_complexity_index']
        language['phonotactic_complexity_index'] = syllable_profile['phonotactic_complexity_index']
        drift_sum += drift
        prosodic_complexity_sum += float(syllable_profile['prosodic_complexity_index'])
        phonotactic_complexity_sum += float(syllable_profile['phonotactic_complexity_index'])
    rules_by_language_id: dict[int, list[dict[str, Any]]] = {}
    for rule in rules:
        rules_by_language_id.setdefault(int(rule.get('language_region_id', -1)), []).append(rule)
    for language in languages:
        language_id = int(language.get('id', -1))
        parent_id = int(language.get('parent_language_region_id', -1))
        lineage_depth = max(0, int(language.get('lineage_depth', 0)))
        language_rules = rules_by_language_id.get(language_id, [])
        replacement_pressure = _clamp(float(language.get('change_rate',
            0.0)) * 0.44 + (1.0 - float(language.get('inherited_phonology_fraction',
            1.0))) * 0.36 + float(language.get('trade_contact_index',
            0.0)) * 0.2)
        contact = _clamp(float(language.get('trade_contact_index', 0.0)))
        inherited = _clamp(float(language.get('inherited_phonology_fraction', 1.0)))
        correspondence_ids: list[int] = []
        for index, (meaning, proto_form, semantic_domain) in enumerate(LEXICAL_ROOTS):
            inherited_proto = proto_form if parent_id < 0 else f"{proto_form}{('i' if (language_id + index) % 2 == 0 else 'a')}"
            derived_form, applied_rule_ids, replacement_count = _derive_form(inherited_proto, language_rules)
            if not applied_rule_ids and replacement_pressure > 0.42 and derived_form:
                vowel_index = next((position for position, char in enumerate(derived_form) if char in 'aeiou'), -1)
                if vowel_index >= 0:
                    replacement = 'e' if derived_form[vowel_index] != 'e' else 'a'
                    derived_form = derived_form[:vowel_index] + replacement + derived_form[vowel_index + 1:]
                    replacement_count += 1
            similarity = _lexical_similarity(inherited_proto, derived_form)
            retention = _clamp(similarity * 0.62 + float(language.get('inherited_phonology_fraction', 1.0)) * 0.28 + (1.0 - replacement_pressure) * 0.1)
            stress_pattern = 'initial' if (language_id + index + lineage_depth) % 3 == 0 else 'penultimate'
            syllable_count = max(1, sum((1 for char in derived_form if char in 'aeiou')))
            diffusion_stage = 1 + min(len(eras) - 1, int(index * len(eras) / max(1, len(LEXICAL_ROOTS))))
            diffusion_adoption = _clamp(retention * 0.44 + (1.0 - replacement_pressure) * 0.22 + contact * 0.14 + len(applied_rule_ids) / max(1,
                len(language_rules)) * 0.2)
            semantic_shift = _clamp((1.0 - retention) * 0.48 + contact * 0.2 + index % 4 * 0.04)
            correspondence = {'id': len(correspondences),
                'language_region_id': language_id,
                'parent_language_region_id': parent_id,
                'meaning': meaning,
                'semantic_domain': semantic_domain,
                'proto_form': proto_form,
                'inherited_form': inherited_proto,
                'derived_form': derived_form,
                'applied_rule_ids': applied_rule_ids,
                'applied_rule_count': len(applied_rule_ids),
                'replacement_count': replacement_count,
                'regular_correspondence_fraction': round(retention,
                6),
                'lexical_replacement_index': round(_clamp(1.0 - retention),
                6),
                'stress_pattern': stress_pattern,
                'syllable_count': syllable_count,
                'syllable_pattern': _syllable_pattern(derived_form),
                'mora_count': _mora_count(derived_form),
                'prosodic_weight_index': round(_clamp(syllable_count / 5.0 + (0.08 if stress_pattern == 'initial' else 0.0)),
                6),
                'diffusion_stage_index': diffusion_stage,
                'diffusion_adoption_index': round(diffusion_adoption,
                6),
                'semantic_shift_index': round(semantic_shift,
                6),
                'borrowed': bool(parent_id >= 0 and contact >= 0.62 and (semantic_shift >= 0.34) and (retention < inherited))}
            correspondence_ids.append(correspondence['id'])
            correspondences.append(correspondence)
        language['lexical_correspondence_ids'] = correspondence_ids
        language['lexical_correspondence_count'] = len(correspondence_ids)
        diffusion_steps: list[dict[str, Any]] = []
        for index, era in enumerate(eras):
            stage_index = index + 1
            affected_records = [correspondences[record_id] for record_id in correspondence_ids if int(correspondences[record_id].get('diffusion_stage_index',
                0)) <= stage_index]
            affected_ids = [int(record.get('id', -1)) for record in affected_records]
            affected_domains = {str(record.get('semantic_domain', '')) for record in affected_records if str(record.get('semantic_domain', '')).strip()}
            adoption = sum((float(record.get('diffusion_adoption_index',
                0.0)) for record in affected_records)) / len(affected_records) if affected_records else 0.0
            innovation = sum((float(record.get('lexical_replacement_index',
                0.0)) for record in affected_records)) / len(affected_records) if affected_records else 0.0
            semantic_shift = sum((float(record.get('semantic_shift_index',
                0.0)) for record in affected_records)) / len(affected_records) if affected_records else 0.0
            progress = stage_index / max(1, len(eras))
            diffusion_steps.append({'era_id': int(era.get('id',
                -1)),
                'stage_index': stage_index,
                'start_year_bp': round(float(era.get('start_year_bp',
                0.0)),
                6),
                'end_year_bp': round(float(era.get('end_year_bp',
                0.0)),
                6),
                'affected_correspondence_ids': affected_ids,
                'affected_correspondence_count': len(affected_ids),
                'affected_meanings': [str(record.get('meaning',
                '')) for record in affected_records],
                'affected_domain_count': len(affected_domains),
                'adoption_fraction': round(_clamp(adoption),
                6),
                'innovation_fraction': round(_clamp(innovation),
                6),
                'contact_borrowing_index': round(_clamp(contact * 0.52 + (1.0 - inherited) * 0.22 + progress * 0.08),
                6),
                'regularization_index': round(_clamp(1.0 - innovation * 0.62 + inherited * 0.18),
                6),
                'semantic_shift_index': round(_clamp(semantic_shift),
                6)})
        diffusion_history_id = len(diffusion_histories)
        mean_adoption = sum((float(step.get('adoption_fraction', 0.0)) for step in diffusion_steps)) / len(diffusion_steps) if diffusion_steps else 0.0
        mean_innovation = sum((float(step.get('innovation_fraction', 0.0)) for step in diffusion_steps)) / len(diffusion_steps) if diffusion_steps else 0.0
        mean_semantic_shift = sum((float(step.get('semantic_shift_index',
            0.0)) for step in diffusion_steps)) / len(diffusion_steps) if diffusion_steps else 0.0
        diffusion_histories.append({'id': diffusion_history_id,
            'language_region_id': language_id,
            'parent_language_region_id': parent_id,
            'phonological_history_id': int(language.get('phonological_history_id',
            -1)),
            'lexical_correspondence_ids': correspondence_ids,
            'lexical_correspondence_count': len(correspondence_ids),
            'step_count': len(diffusion_steps),
            'syllable_template': language.get('syllable_template',
            ''),
            'stress_system': language.get('stress_system',
            ''),
            'mean_diffusion_adoption_index': round(_clamp(mean_adoption),
            6),
            'mean_lexical_innovation_index': round(_clamp(mean_innovation),
            6),
            'mean_semantic_shift_index': round(_clamp(mean_semantic_shift),
            6),
            'contact_borrowing_index': round(_clamp(contact * 0.58 + (1.0 - inherited) * 0.24),
            6),
            'steps': diffusion_steps})
        language['lexical_diffusion_history_id'] = diffusion_history_id
    populations_by_language: dict[int, list[dict[str, Any]]] = {}
    for population in payload['population_regions']:
        if not isinstance(population, dict):
            continue
        population_language_id = int(population.get('language_region_id', -1))
        if population_language_id >= 0:
            populations_by_language.setdefault(population_language_id, []).append(population)
    history_by_language = {int(history.get('language_region_id', -1)): history for history in histories}
    diffusion_by_language = {int(history.get('language_region_id', -1)): history for history in diffusion_histories}
    global_population_complete = all((p['population_estimate_available'] for rows in populations_by_language.values() for p in rows))
    total_known_population = sum((max(0.0,
        float(population.get('estimated_population',
        0.0))) for populations in populations_by_language.values() for population in populations)) if global_population_complete else None
    speaker_allophony_sum = 0.0
    speaker_syllable_sum = 0.0
    speaker_contact_sum = 0.0
    speaker_adoption_sum = 0.0
    speaker_reduction_sum = 0.0
    speaker_lexical_pressure_sum = 0.0
    total_estimated_speakers = 0.0
    high_contact_speaker_count = 0
    for language in languages:
        language_id = int(language.get('id', -1))
        parent_id = int(language.get('parent_language_region_id', -1))
        phonological_history = history_by_language.get(language_id, {})
        lexical_diffusion_history = diffusion_by_language.get(language_id, {})
        matched_populations = populations_by_language.get(language_id, [])
        local_population_complete = all((p['population_estimate_available'] for p in matched_populations))
        population_ids = [int(population.get('id', -1)) for population in matched_populations if int(population.get('id', -1)) >= 0]
        primary_population = max(matched_populations,
            key=lambda population: float(population.get('estimated_population',
            0.0)),
            default={}) if local_population_complete else {}
        estimated_speakers = sum((max(0.0,
            float(population.get('estimated_population',
            0.0))) for population in matched_populations)) if local_population_complete else None
        contact = _clamp(float(language.get('trade_contact_index', 0.0)))
        inherited = _clamp(float(language.get('inherited_phonology_fraction', 1.0)))
        drift = _clamp(float(language.get('phonological_drift_index', 0.0)))
        change_rate = _clamp(float(language.get('change_rate', 0.0)))
        phonotactic = _clamp(float(language.get('phonotactic_complexity_index', 0.0)))
        prosodic = _clamp(float(language.get('prosodic_complexity_index', 0.0)))
        population_pressure = _population_weighted_mean(matched_populations, 'population_pressure') if local_population_complete else None
        urbanization = _population_weighted_mean(matched_populations, 'urbanization_fraction') if local_population_complete else None
        migration_balance = _population_weighted_mean(matched_populations, 'migration_balance') if local_population_complete else None
        initial_speakers = estimated_speakers * _clamp(0.7 + inherited * 0.1 - drift * 0.08 - abs(migration_balance) * 0.06,
            0.45,
            0.95) if local_population_complete else None
        phonology_steps = phonological_history.get('steps', []) if isinstance(phonological_history.get('steps', []), list) else []
        diffusion_steps = lexical_diffusion_history.get('steps', []) if isinstance(lexical_diffusion_history.get('steps', []), list) else []
        speaker_steps: list[dict[str, Any]] = []
        for index, era in enumerate(eras):
            stage_index = index + 1
            progress = stage_index / max(1, len(eras))
            phonology_step = phonology_steps[min(index, len(phonology_steps) - 1)] if phonology_steps else {}
            diffusion_step = diffusion_steps[min(index, len(diffusion_steps) - 1)] if diffusion_steps else {}
            speaker_population = initial_speakers + (estimated_speakers - initial_speakers) * progress if local_population_complete else None
            speaker_fraction = _clamp(speaker_population / max(total_known_population, estimated_speakers, 1.0)) if global_population_complete else None
            contact_pressure = _clamp(float(phonology_step.get('contact_influence_index',
                contact)) * 0.4 + float(diffusion_step.get('contact_borrowing_index',
                contact)) * 0.32 + contact * 0.18 + abs(migration_balance) * 0.1) if local_population_complete else None
            lexical_pressure = _clamp(float(diffusion_step.get('adoption_fraction',
                0.0)) * 0.34 + float(diffusion_step.get('innovation_fraction',
                0.0)) * 0.32 + float(diffusion_step.get('semantic_shift_index',
                0.0)) * 0.2 + contact_pressure * 0.14) if local_population_complete else None
            syllable_pressure = _clamp(phonotactic * 0.3 + prosodic * 0.24 + min(1.0,
                float(language.get('allowed_coda_count',
                1)) / 6.0) * 0.18 + float(phonology_step.get('prosodic_weight_index',
                prosodic)) * 0.18 + lexical_pressure * 0.1) if local_population_complete else None
            phonetic_reduction = _clamp(change_rate * 0.28 + syllable_pressure * 0.22 + contact_pressure * 0.18 + urbanization * 0.16 + progress * 0.08 + (1.0 - inherited) * 0.08) if local_population_complete else None
            allophonic_variation = _clamp(phonetic_reduction * 0.28 + contact_pressure * 0.24 + phonotactic * 0.18 + drift * 0.16 + speaker_fraction * 0.08 + (1.0 - inherited) * 0.06) if global_population_complete else None
            population_adoption = _clamp(speaker_fraction * 0.24 + float(diffusion_step.get('adoption_fraction',
                0.0)) * 0.3 + float(diffusion_step.get('regularization_index',
                0.0)) * 0.2 + (1.0 - population_pressure) * 0.1 + urbanization * 0.08 + progress * 0.08) if global_population_complete else None
            register_divergence = _clamp(contact_pressure * 0.3 + urbanization * 0.26 + population_pressure * 0.18 + speaker_fraction * 0.14 + syllable_pressure * 0.12) if global_population_complete else None
            pronunciation_regularization = _clamp(float(diffusion_step.get('regularization_index',
                inherited)) * 0.46 + inherited * 0.22 + (1.0 - allophonic_variation) * 0.18 + (1.0 - contact_pressure) * 0.14) if global_population_complete else None
            speaker_steps.append({'era_id': int(era.get('id',
                -1)),
                'stage_index': stage_index,
                'start_year_bp': round(float(era.get('start_year_bp',
                0.0)),
                6),
                'end_year_bp': round(float(era.get('end_year_bp',
                0.0)),
                6),
                'speaker_population': _nullable_round(speaker_population,
                6),
                'speaker_fraction_index': _nullable_round(speaker_fraction,
                6),
                'allophonic_variation_index': _nullable_round(allophonic_variation,
                6),
                'syllable_pressure_index': _nullable_round(syllable_pressure,
                6),
                'phonetic_reduction_index': _nullable_round(phonetic_reduction,
                6),
                'contact_pressure_index': _nullable_round(contact_pressure,
                6),
                'lexical_diffusion_pressure_index': _nullable_round(lexical_pressure,
                6),
                'population_adoption_index': _nullable_round(population_adoption,
                6),
                'register_divergence_index': _nullable_round(register_divergence,
                6),
                'pronunciation_regularization_index': _nullable_round(pronunciation_regularization,
                6)})
        if speaker_steps and local_population_complete:
            speaker_steps[-1]['speaker_population'] = _nullable_round(estimated_speakers, 6)
        step_divisor = len(speaker_steps) if speaker_steps else 1
        mean_allophony = (sum((float(step.get('allophonic_variation_index',
            0.0)) for step in speaker_steps)) / step_divisor if speaker_steps else 0.0) if global_population_complete else None
        mean_syllable = (sum((float(step.get('syllable_pressure_index',
            0.0)) for step in speaker_steps)) / step_divisor if speaker_steps else 0.0) if local_population_complete else None
        mean_contact = (sum((float(step.get('contact_pressure_index',
            0.0)) for step in speaker_steps)) / step_divisor if speaker_steps else 0.0) if local_population_complete else None
        mean_adoption = (sum((float(step.get('population_adoption_index',
            0.0)) for step in speaker_steps)) / step_divisor if speaker_steps else 0.0) if global_population_complete else None
        mean_reduction = (sum((float(step.get('phonetic_reduction_index',
            0.0)) for step in speaker_steps)) / step_divisor if speaker_steps else 0.0) if local_population_complete else None
        mean_lexical_pressure = (sum((float(step.get('lexical_diffusion_pressure_index',
            0.0)) for step in speaker_steps)) / step_divisor if speaker_steps else 0.0) if local_population_complete else None
        high_contact = mean_contact >= 0.65 or any((float(step.get('contact_pressure_index',
            0.0)) >= 0.75 for step in speaker_steps)) if local_population_complete else None
        speaker_history_id = len(speaker_histories)
        speaker_histories.append({'id': speaker_history_id,
            'language_region_id': language_id,
            'parent_language_region_id': parent_id,
            'population_region_id': int(primary_population.get('id',
            -1)) if local_population_complete else None,
            'population_region_ids': population_ids,
            'population_region_count': len(population_ids),
            'phonological_history_id': int(language.get('phonological_history_id',
            -1)),
            'lexical_diffusion_history_id': int(language.get('lexical_diffusion_history_id',
            -1)),
            'initial_speaker_population': _nullable_round(initial_speakers,
            6),
            'final_speaker_population': _nullable_round(estimated_speakers,
            6),
            'estimated_speaker_population': _nullable_round(estimated_speakers,
            6),
            'mean_allophonic_variation_index': _nullable_round(_nullable_clamp(mean_allophony),
            6),
            'mean_syllable_pressure_index': _nullable_round(_nullable_clamp(mean_syllable),
            6),
            'mean_speaker_contact_index': _nullable_round(_nullable_clamp(mean_contact),
            6),
            'mean_population_adoption_index': _nullable_round(_nullable_clamp(mean_adoption),
            6),
            'mean_phonetic_reduction_index': _nullable_round(_nullable_clamp(mean_reduction),
            6),
            'mean_lexical_diffusion_pressure_index': _nullable_round(_nullable_clamp(mean_lexical_pressure),
            6),
            'high_contact_speaker_history': bool(high_contact) if high_contact is not None else None,
            'step_count': len(speaker_steps),
            'steps': speaker_steps})
        language['speaker_population_history_id'] = speaker_history_id
        if mean_allophony is not None:
            speaker_allophony_sum += mean_allophony
        if mean_syllable is not None:
            speaker_syllable_sum += mean_syllable
        if mean_contact is not None:
            speaker_contact_sum += mean_contact
        if mean_adoption is not None:
            speaker_adoption_sum += mean_adoption
        if mean_reduction is not None:
            speaker_reduction_sum += mean_reduction
        if mean_lexical_pressure is not None:
            speaker_lexical_pressure_sum += mean_lexical_pressure
        if estimated_speakers is not None:
            total_estimated_speakers += estimated_speakers
        if high_contact is not None:
            high_contact_speaker_count += int(high_contact)
    rule_count = len(rules)
    history_count = len(histories)
    lexical_count = len(correspondences)
    diffusion_count = len(diffusion_histories)
    speaker_count = len(speaker_histories)
    summary = {'phonological_history_count': history_count,
        'phonological_history_step_count': sum((int(history.get('step_count',
        0)) for history in histories)),
        'phonological_rule_count': rule_count,
        'phonological_rule_language_count': sum((1 for language in languages if int(language.get('sound_change_rule_count',
        0)) > 0)),
        'max_phonological_shift_stage': max((int(rule.get('stage_index',
        0)) for rule in rules),
        default=0),
        'mean_phonological_rule_probability_index': round(sum((float(rule.get('probability_index',
        0.0)) for rule in rules)) / rule_count,
        6) if rule_count else 0.0,
        'mean_phonological_rule_regularity_index': round(sum((float(rule.get('regularity_index',
        0.0)) for rule in rules)) / rule_count,
        6) if rule_count else 0.0,
        'mean_lexical_replacement_index': round(sum((float(rule.get('lexical_replacement_index',
        0.0)) for rule in rules)) / rule_count,
        6) if rule_count else 0.0,
        'mean_phonological_contact_influence_index': round(sum((float(rule.get('contact_influence_index',
        0.0)) for rule in rules)) / rule_count,
        6) if rule_count else 0.0,
        'mean_phonological_drift_index': round(drift_sum / history_count,
        6) if history_count else 0.0,
        'mean_language_prosodic_complexity_index': round(prosodic_complexity_sum / history_count,
        6) if history_count else 0.0,
        'mean_phonotactic_complexity_index': round(phonotactic_complexity_sum / history_count,
        6) if history_count else 0.0,
        'lexical_correspondence_count': lexical_count,
        'lexical_correspondence_language_count': sum((1 for language in languages if int(language.get('lexical_correspondence_count',
        0)) > 0)),
        'lexical_diffusion_history_count': diffusion_count,
        'lexical_diffusion_step_count': sum((int(history.get('step_count',
        0)) for history in diffusion_histories)),
        'lexical_diffusion_language_count': sum((1 for language in languages if int(language.get('lexical_diffusion_history_id',
        -1)) >= 0)),
        'mean_regular_correspondence_fraction': round(sum((float(record.get('regular_correspondence_fraction',
        0.0)) for record in correspondences)) / lexical_count,
        6) if lexical_count else 0.0,
        'mean_lexical_correspondence_replacement_index': round(sum((float(record.get('lexical_replacement_index',
        0.0)) for record in correspondences)) / lexical_count,
        6) if lexical_count else 0.0,
        'mean_lexical_prosodic_weight_index': round(sum((float(record.get('prosodic_weight_index',
        0.0)) for record in correspondences)) / lexical_count,
        6) if lexical_count else 0.0,
        'mean_lexical_diffusion_adoption_index': round(sum((float(history.get('mean_diffusion_adoption_index',
        0.0)) for history in diffusion_histories)) / diffusion_count,
        6) if diffusion_count else 0.0,
        'mean_lexical_innovation_index': round(sum((float(history.get('mean_lexical_innovation_index',
        0.0)) for history in diffusion_histories)) / diffusion_count,
        6) if diffusion_count else 0.0,
        'mean_semantic_shift_index': round(sum((float(history.get('mean_semantic_shift_index',
        0.0)) for history in diffusion_histories)) / diffusion_count,
        6) if diffusion_count else 0.0,
        'speaker_population_history_count': speaker_count,
        'speaker_population_step_count': sum((int(history.get('step_count',
        0)) for history in speaker_histories)),
        'total_estimated_speaker_population': round(total_estimated_speakers,
        6),
        'mean_speaker_allophonic_variation_index': round(speaker_allophony_sum / speaker_count,
        6) if speaker_count else 0.0,
        'mean_speaker_syllable_pressure_index': round(speaker_syllable_sum / speaker_count,
        6) if speaker_count else 0.0,
        'mean_speaker_contact_index': round(speaker_contact_sum / speaker_count,
        6) if speaker_count else 0.0,
        'mean_speaker_population_adoption_index': round(speaker_adoption_sum / speaker_count,
        6) if speaker_count else 0.0,
        'mean_speaker_phonetic_reduction_index': round(speaker_reduction_sum / speaker_count,
        6) if speaker_count else 0.0,
        'mean_speaker_lexical_diffusion_pressure_index': round(speaker_lexical_pressure_sum / speaker_count,
        6) if speaker_count else 0.0,
        'high_contact_speaker_history_count': high_contact_speaker_count}
    language_annotations = {int(language.get('id',
        -1)): {key: language[key] for key in annotation_keys if key in language} for language in languages if int(language.get('id',
        -1)) >= 0}
    _finalize_speakers(speaker_histories, summary)
    return (rules, histories, correspondences, diffusion_histories, speaker_histories, language_annotations, summary)

MODEL = {'annotation_model': 'language_history_rule_lexicon_diffusion_and_speaker_backreferences_v1',
 'availability_policy': 'per_field_typed_speaker_estimates_complete_actual_local_population_and_global_share_scopes',
 'deterministic': True,
 'diffusion_model': 'era_staged_adoption_innovation_semantic_shift_v1',
 'history_model': 'era_partitioned_inventory_shift_inheritance_and_prosody_v1',
 'lexicon_model': 'twelve_proto_roots_ordered_rule_application_and_correspondence_v1',
 'model_limitation': 'synthetic_template_linguistics_without_empirical_language_calibration_individual_speaker_interaction_or_stochastic_transmission',
 'model_type': 'causal_language_era_sound_rule_lexical_diffusion_speaker_history_v2',
 'rule_model': 'language_lineage_change_contact_isolation_template_selection_v1',
 'source_historical_event_model': 'causal_region_culture_language_trade_site_timeline_v2',
 'source_language_region_model': 'causal_trade_union_family_lineage_phonology_v1',
 'source_native_social_availability_model': 'native_settlement_source_complete_social_estimates_v1',
 'source_population_region_model': 'causal_area_weighted_capacity_occupancy_population_regions_v2',
 'speaker_model': 'population_weighted_contact_allophony_reduction_and_adoption_v1',
 'structural_policy': 'independent_sound_lexicon_diffusion_and_actual_era_slots_retained',
 'zero_population_policy': 'known_zero_remains_zero_without_area_proxy'}


SUMMARY_FIELDS = ('high_contact_speaker_history_count',
    'lexical_correspondence_count',
    'lexical_correspondence_language_count',
    'lexical_diffusion_history_count',
    'lexical_diffusion_language_count',
    'lexical_diffusion_step_count',
    'max_phonological_shift_stage',
    'mean_language_prosodic_complexity_index',
    'mean_lexical_correspondence_replacement_index',
    'mean_lexical_diffusion_adoption_index',
    'mean_lexical_innovation_index',
    'mean_lexical_prosodic_weight_index',
    'mean_lexical_replacement_index',
    'mean_phonological_contact_influence_index',
    'mean_phonological_drift_index',
    'mean_phonological_rule_probability_index',
    'mean_phonological_rule_regularity_index',
    'mean_phonotactic_complexity_index',
    'mean_regular_correspondence_fraction',
    'mean_semantic_shift_index',
    'mean_speaker_allophonic_variation_index',
    'mean_speaker_contact_index',
    'mean_speaker_lexical_diffusion_pressure_index',
    'mean_speaker_phonetic_reduction_index',
    'mean_speaker_population_adoption_index',
    'mean_speaker_syllable_pressure_index',
    'phonological_history_count',
    'phonological_history_step_count',
    'phonological_rule_count',
    'phonological_rule_language_count',
    'speaker_population_history_count',
    'speaker_population_step_count',
    'total_estimated_speaker_population',
    'phonology_history_model',
    'speaker_history_summary_availability',
    'available_speaker_population_history_count',
    'available_speaker_population_step_count')

COLLECTIONS = ("phonological_rules", "phonological_histories", "lexical_correspondences", "lexical_diffusion_histories", "speaker_population_histories")
LANGUAGE_FIELDS = ("phonological_history_id",
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
    "speaker_population_history_id")

def _exact(actual, expected):
    if type(actual) is not type(expected): return False
    if type(expected) is dict: return actual.keys() == expected.keys() and all(_exact(actual[k], v) for k,v in expected.items())
    if type(expected) is list: return len(actual) == len(expected) and all(_exact(a,b) for a,b in zip(actual,expected))
    return actual == expected

def _require(condition, message):
    if not condition: raise ValueError("phonology availability: " + message)

def phonology_version(world):
    from .native_social_availability import uses_native_social_availability
    from .phonology_history_validation import _phonology_history_model
    _require(type(world) is dict and type(world.get("summary",{})) is dict,"world/summary mapping required")
    native=uses_native_social_availability(world)
    declared=world.get("phonology_history_model")
    if "phonology_history_model" in world:
        expected=MODEL if native else _phonology_history_model()
        _require(_exact(declared,expected),"exact own source-matched declaration required")
        _require(world["summary"].get("phonology_history_model")==expected["model_type"],"own summary identity mismatch")
    elif native:
        _require(not any(k in world for k in COLLECTIONS) and not any(k in world.get("summary",
            {}) for k in SUMMARY_FIELDS),
            "undeclared existing outputs require explicit audited clearing")
        _require(not any(any(k in l for k in LANGUAGE_FIELDS) for l in world["language_regions"]),"orphan language annotations")
    if not native:
        new_summary = ("speaker_history_summary_availability", "available_speaker_population_history_count", "available_speaker_population_step_count")
        _require(not any(k in world.get("summary",{}) for k in new_summary) and not any(
            type(r) is dict and ("estimate_availability" in r or "estimate_available" in r or any(
                type(s) is dict and ("estimate_availability" in s or "estimate_available" in s) for s in r.get("steps",[])))
            for r in world.get("speaker_population_histories",[])),"orphan speaker availability")
    return 2 if native else 1

def require_phonology_sources(world):
    from .native_social_availability import require_native_social_availability
    from .cultural_geography_validation import validate_cultural_geography_replay
    from .historical_geography_validation import validate_historical_geography_replay
    from .civilization_geography_validation import validate_civilization_geography_replay
    require_native_social_availability(world)
    for audit in (validate_cultural_geography_replay,validate_historical_geography_replay,validate_civilization_geography_replay):
        errors=audit(world);_require(not errors,"complete native source replay required: "+str(errors))
    _require(bool(world["historical_eras"]) or not world["language_regions"],"actual era slots required")
    for row in world["population_regions"]:
        _require(type(row["language_region_id"]) is int and -1<=row["language_region_id"]<len(world["language_regions"]),
            "population language membership required")

def validate_native_phonology_history(payload):
    try:
        _require(phonology_version(payload)==2,"successor required")
        require_phonology_sources(payload)
        _require(_exact(payload.get("phonology_history_model"),MODEL),"exact own model required")
        rules,histories,lexicon,diffusion,speakers,annotations,summary=_expected(payload)
        for key,value in zip(COLLECTIONS,(rules,histories,lexicon,diffusion,speakers)):
            _require(_exact(payload.get(key),value),"owned records disagree: "+key)
        for key,value in summary.items():_require(key in payload["summary"] and _exact(payload["summary"][key],value),"summary disagreement: "+key)
        for row in payload["language_regions"]:
            for key,value in annotations[row["id"]].items():_require(key in row and _exact(row[key],value),"language annotation disagreement")
        return []
    except (AttributeError,IndexError,KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError):
        return ["phonology history model or causal replay invalid"]
