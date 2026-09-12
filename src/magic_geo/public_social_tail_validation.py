"""Exact audited successor dispatch before the public CLI's legacy arithmetic."""
from __future__ import annotations
from typing import Any


def validate_public_social_tail(world: dict[str, Any]) -> tuple[dict[str, bool], list[str]]:
    modes = dict.fromkeys(("phonology", "population", "economy", "genealogy", "logistics", "demographic", "market"), False)
    try:
        from .history_economy_validation import history_economy_version, validate_history_economy_replay
        from .native_dynasty_genealogy_validation import genealogy_version
        from .native_phonology_history_validation import phonology_version
        from .logistics_availability_validation import uses_logistics_availability
        from .dynasty_genealogy_validation import validate_dynasty_genealogy_replay
        from .phonology_history_validation import validate_phonology_history_replay
        from .logistics_exchange_validation import validate_logistics_exchange_replay
        from .campaign_operations_validation import validate_campaign_operations_replay
        from .demographic_availability_validation import demographic_version
        from .market_availability_validation import market_version
        from .demographic_agents_validation import validate_demographic_agents_replay
        from .market_clearing_validation import validate_market_clearing_replay
        modes.update(population=history_economy_version(world, "population") == 2,
                     economy=history_economy_version(world, "economy") == 2,
                     genealogy=genealogy_version(world) == 2,
                     phonology=phonology_version(world) == 2,
                     logistics=uses_logistics_availability(world),
                     demographic=demographic_version(world) == 2,
                     market=market_version(world) == 2)
        errors = []
        for active, audit in (
            (modes["population"] or modes["economy"], validate_history_economy_replay),
            (modes["genealogy"], validate_dynasty_genealogy_replay),
            (modes["phonology"], validate_phonology_history_replay),
            (modes["logistics"], validate_logistics_exchange_replay),
            (modes["logistics"], validate_campaign_operations_replay),
            (modes["demographic"], validate_demographic_agents_replay),
            (modes["market"], validate_market_clearing_replay),
        ):
            if active:
                errors.extend(audit(world))
        return modes, errors[:16]
    except (ValueError, TypeError, KeyError, IndexError, OverflowError) as error:
        return modes, ["public social tail declaration/source: " + str(error)[:500]]
