from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence


CRUST_PROCESS_REASON_ORDER = (
    "quiet_oceanic_aging",
    "oceanic_ridge_rejuvenation",
    "oceanic_ridge_creation_relaxation",
    "divergent_continental_rifting",
    "oceanic_convergence_subduction_proxy",
    "continental_collision_orogeny",
    "plate_crossing_accretion_proxy",
    "age_bound_enforcement",
    "thickness_bound_enforcement",
    "density_bound_enforcement",
)

_EXTENSIVE_FIELDS = (
    "crust_volume_km3",
    "density_weighted_crust_volume",
    "crust_age_volume_moment_km3_ma",
)

_CRUST_NAMES = (
    "oceanic",
    "continental",
    "transitional",
    "volcanic_arc",
    "craton",
    "orogen",
    "rift_basin",
    "sedimentary_basin",
    "accreted_terrane",
)

_LITHOLOGY_NAMES = (
    "basalt",
    "granite",
    "limestone",
    "sandstone",
    "shale",
    "volcanic",
    "metamorphic",
)


@dataclass(frozen=True)
class _CrustState:
    crust_type: int
    lithology: int
    age_ma: float
    thickness_km: float
    density: float


@dataclass
class _CellReasonDelta:
    triggered: bool = False
    changed: bool = False
    crust_volume_km3: float = 0.0
    density_weighted_crust_volume: float = 0.0
    crust_age_volume_moment_km3_ma: float = 0.0


@dataclass
class _ReasonAggregate:
    triggered_cell_count: int = 0
    extensive_state_changed_cell_count: int = 0


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _timestep_scaled_fraction(
    reference_fraction: float,
    timestep_scale: float,
) -> float:
    bounded_fraction = _clamp(reference_fraction, 0.0, 1.0)
    bounded_scale = max(0.0, timestep_scale)
    if bounded_fraction <= 0.0 or bounded_scale <= 0.0:
        return 0.0
    if bounded_scale == 1.0:
        return bounded_fraction
    if bounded_fraction >= 1.0:
        return 1.0
    return -math.expm1(bounded_scale * math.log1p(-bounded_fraction))


def _is_oceanic_crust_state(
    crust_type: int,
    lithology: int,
    age_ma: float,
    thickness_km: float,
    density: float,
) -> bool:
    if crust_type == 0:
        return True
    if crust_type == 2:
        return lithology == 0
    if crust_type != 3:
        return False
    return age_ma <= 320.0 and thickness_km <= 18.0 and density >= 2.84


def _state_extensives(
    area_km2: float,
    state: _CrustState,
) -> tuple[float, float, float]:
    volume = area_km2 * state.thickness_km
    return volume, volume * state.density, volume * state.age_ma


def _record_transition(
    *,
    area_km2: float,
    triggered: bool,
    before: _CrustState,
    after: _CrustState,
    delta: _CellReasonDelta,
) -> None:
    before_extensives = _state_extensives(area_km2, before)
    after_extensives = _state_extensives(area_km2, after)
    delta.triggered = delta.triggered or triggered
    delta.changed = delta.changed or (
        before.age_ma != after.age_ma
        or before.thickness_km != after.thickness_km
        or before.density != after.density
    )
    delta.crust_volume_km3 += after_extensives[0] - before_extensives[0]
    delta.density_weighted_crust_volume += (
        after_extensives[1] - before_extensives[1]
    )
    delta.crust_age_volume_moment_km3_ma += (
        after_extensives[2] - before_extensives[2]
    )


def _require_equal_lengths(
    arrays: dict[str, Sequence[Any]],
) -> int:
    lengths = {name: len(values) for name, values in arrays.items()}
    if len(set(lengths.values())) != 1:
        raise ValueError(f"crust process input lengths differ: {lengths}")
    cell_count = next(iter(lengths.values()), 0)
    if cell_count == 0:
        raise ValueError("crust process replay requires at least one cell")
    return cell_count


def _validated_floats(name: str, values: Sequence[float]) -> list[float]:
    result: list[float] = []
    for index, value in enumerate(values):
        if isinstance(value, bool):
            raise TypeError(f"{name}[{index}] must be numeric")
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{name}[{index}] must be finite")
        result.append(number)
    return result


def _validated_ints(name: str, values: Sequence[int]) -> list[int]:
    result: list[int] = []
    for index, value in enumerate(values):
        if type(value) is not int:
            raise TypeError(f"{name}[{index}] must be an integer")
        result.append(value)
    return result


def _final_crust_alias_binary64_bound(
    observed: float,
    remapped: float,
    process_delta: float,
    reconstructed: float,
) -> float:
    """Bound the exported final = remapped + process-delta identity.

    Native code forms ``process_delta = fl(observed - remapped)`` and the
    independent replay forms ``reconstructed = fl(remapped + process_delta)``.
    All four operands are binary64 round-trip exports, so decimal display
    precision contributes no error.  A two-operation ``gamma`` bound over the
    two arithmetic input pairs covers those roundings; one ULP of the computed
    residual covers the validator's comparison subtraction.
    """

    values = (observed, remapped, process_delta, reconstructed)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("final crust alias bound operands must be finite")
    unit_roundoff = 0.5 * math.ulp(1.0)
    epsilon_product = 2.0 * unit_roundoff
    gamma = epsilon_product / (1.0 - epsilon_product)
    absolute_input_sum = math.fsum(
        (
            abs(observed),
            abs(remapped),
            abs(remapped),
            abs(process_delta),
        )
    )
    residual_rounding = math.ulp(abs(observed - reconstructed))
    bound = gamma * absolute_input_sum + residual_rounding
    if not math.isfinite(bound):
        raise ValueError("final crust alias binary64 bound overflowed")
    return bound


def _delta_payload(
    crust_volume_km3: float,
    density_weighted_crust_volume: float,
    crust_age_volume_moment_km3_ma: float,
) -> dict[str, float]:
    return {
        "crust_volume_km3": crust_volume_km3,
        "density_weighted_crust_volume": density_weighted_crust_volume,
        "crust_age_volume_moment_km3_ma": (
            crust_age_volume_moment_km3_ma
        ),
    }


def _inventory(
    areas_km2: Sequence[float],
    thicknesses_km: Sequence[float],
    densities: Sequence[float],
    ages_ma: Sequence[float],
) -> tuple[float, float, float]:
    volume = 0.0
    density_volume = 0.0
    age_moment = 0.0
    for area, thickness, density, age in zip(
        areas_km2,
        thicknesses_km,
        densities,
        ages_ma,
        strict=True,
    ):
        cell_volume = area * thickness
        volume += cell_volume
        density_volume += cell_volume * density
        age_moment += cell_volume * age
    return volume, density_volume, age_moment


def replay_ordered_crust_process(
    *,
    areas_km2: Sequence[float],
    remapped_crust_type_by_cell: Sequence[int],
    remapped_lithology_by_cell: Sequence[int],
    remapped_crust_age_ma_by_cell: Sequence[float],
    remapped_crust_thickness_km_by_cell: Sequence[float],
    remapped_crust_density_by_cell: Sequence[float],
    previous_plate_ids: Sequence[int],
    current_plate_ids: Sequence[int],
    boundary_convergent_by_cell: Sequence[float],
    boundary_divergent_by_cell: Sequence[float],
    timestep_scale: float,
    reference_oceanic_crust_aging_ma_per_reference_step: float,
    internal_heat: float,
    geological_age_ga: float,
) -> dict[str, Any]:
    """Replay the native ordered crust-rule transition independently.

    Reason deltas are extensive state-moment changes. They deliberately do not
    imply material provenance or exchange with an independently modelled
    reservoir. Positive and negative magnitudes are accumulated per cell before
    being reduced in ascending cell order, matching the native ledger.
    """

    input_arrays: dict[str, Sequence[Any]] = {
        "areas_km2": areas_km2,
        "remapped_crust_type_by_cell": remapped_crust_type_by_cell,
        "remapped_lithology_by_cell": remapped_lithology_by_cell,
        "remapped_crust_age_ma_by_cell": remapped_crust_age_ma_by_cell,
        "remapped_crust_thickness_km_by_cell": (
            remapped_crust_thickness_km_by_cell
        ),
        "remapped_crust_density_by_cell": remapped_crust_density_by_cell,
        "previous_plate_ids": previous_plate_ids,
        "current_plate_ids": current_plate_ids,
        "boundary_convergent_by_cell": boundary_convergent_by_cell,
        "boundary_divergent_by_cell": boundary_divergent_by_cell,
    }
    cell_count = _require_equal_lengths(input_arrays)

    areas = _validated_floats("areas_km2", areas_km2)
    if any(area <= 0.0 for area in areas):
        raise ValueError("areas_km2 values must be positive")
    remapped_types = _validated_ints(
        "remapped_crust_type_by_cell", remapped_crust_type_by_cell
    )
    remapped_lithologies = _validated_ints(
        "remapped_lithology_by_cell", remapped_lithology_by_cell
    )
    remapped_ages = _validated_floats(
        "remapped_crust_age_ma_by_cell", remapped_crust_age_ma_by_cell
    )
    remapped_thicknesses = _validated_floats(
        "remapped_crust_thickness_km_by_cell",
        remapped_crust_thickness_km_by_cell,
    )
    remapped_densities = _validated_floats(
        "remapped_crust_density_by_cell", remapped_crust_density_by_cell
    )
    old_plate_ids = _validated_ints("previous_plate_ids", previous_plate_ids)
    new_plate_ids = _validated_ints("current_plate_ids", current_plate_ids)
    convergent = _validated_floats(
        "boundary_convergent_by_cell", boundary_convergent_by_cell
    )
    divergent = _validated_floats(
        "boundary_divergent_by_cell", boundary_divergent_by_cell
    )

    scalar_inputs = {
        "timestep_scale": float(timestep_scale),
        "reference_oceanic_crust_aging_ma_per_reference_step": float(
            reference_oceanic_crust_aging_ma_per_reference_step
        ),
        "internal_heat": float(internal_heat),
        "geological_age_ga": float(geological_age_ga),
    }
    if any(not math.isfinite(value) for value in scalar_inputs.values()):
        raise ValueError("crust process scalar inputs must be finite")
    if scalar_inputs["timestep_scale"] < 0.0:
        raise ValueError("timestep_scale must be nonnegative")
    if scalar_inputs["geological_age_ga"] < 0.0:
        raise ValueError("geological_age_ga must be nonnegative")

    scale = scalar_inputs["timestep_scale"]
    reference_aging = scalar_inputs[
        "reference_oceanic_crust_aging_ma_per_reference_step"
    ]
    geological_age = scalar_inputs["geological_age_ga"]
    tectonic_activity = _clamp(
        scalar_inputs["internal_heat"]
        * math.sqrt(4.5 / max(0.05, geological_age)),
        0.25,
        2.25,
    )

    result_types: list[int] = []
    result_lithologies: list[int] = []
    result_ages: list[float] = []
    result_thicknesses: list[float] = []
    result_densities: list[float] = []
    cell_reason_deltas = [
        [_CellReasonDelta() for _ in CRUST_PROCESS_REASON_ORDER]
        for _ in range(cell_count)
    ]

    for index in range(cell_count):
        area = areas[index]
        plate_changed = new_plate_ids[index] != old_plate_ids[index]
        old_oceanic = _is_oceanic_crust_state(
            remapped_types[index],
            remapped_lithologies[index],
            remapped_ages[index],
            remapped_thicknesses[index],
            remapped_densities[index],
        )
        conv = convergent[index]
        div = divergent[index]
        crust_type = remapped_types[index]
        lithology = remapped_lithologies[index]
        crust_age = remapped_ages[index]
        crust_thickness = remapped_thicknesses[index]
        crust_density = remapped_densities[index]

        def state() -> _CrustState:
            return _CrustState(
                crust_type,
                lithology,
                crust_age,
                crust_thickness,
                crust_density,
            )

        def record(reason_index: int, triggered: bool, before: _CrustState) -> None:
            _record_transition(
                area_km2=area,
                triggered=triggered,
                before=before,
                after=state(),
                delta=cell_reason_deltas[index][reason_index],
            )

        before = state()
        quiet_aging = old_oceanic and div < 0.10 and conv < 0.10
        if quiet_aging:
            quiet_fraction = _clamp(
                1.0 - max(div, conv) / 0.10,
                0.0,
                1.0,
            )
            crust_age += reference_aging * scale * quiet_fraction
        record(0, quiet_aging, before)

        if plate_changed and max(conv, div) < 0.18:
            crust_type = 2
            lithology = 0 if old_oceanic else 3

        if div >= 0.10:
            if old_oceanic:
                before = state()
                background_reference = _clamp(div * 0.55, 0.0, 0.85)
                if scale == 1.0:
                    rejuvenation = _clamp(
                        div * (0.72 if plate_changed else 0.55),
                        0.0,
                        0.85,
                    )
                else:
                    rejuvenation = _timestep_scaled_fraction(
                        background_reference,
                        scale,
                    )
                    if plate_changed:
                        crossing_reference = _clamp(div * 0.72, 0.0, 0.85)
                        crossing_impulse = _clamp(
                            (crossing_reference - background_reference)
                            / max(1.0e-12, 1.0 - background_reference),
                            0.0,
                            1.0,
                        )
                        rejuvenation = 1.0 - (1.0 - rejuvenation) * (
                            1.0 - crossing_impulse
                        )
                crust_age *= 1.0 - rejuvenation
                record(1, True, before)

                before = state()
                if scale == 1.0:
                    crust_thickness += (7.0 - crust_thickness) * 0.34 * div
                    crust_density += (3.0 - crust_density) * 0.24 * div
                else:
                    crust_thickness += (
                        (7.0 - crust_thickness)
                        * _timestep_scaled_fraction(0.34 * div, scale)
                    )
                    crust_density += (
                        (3.0 - crust_density)
                        * _timestep_scaled_fraction(0.24 * div, scale)
                    )
                record(2, True, before)
                if div >= 0.28:
                    crust_type = 0
                    lithology = 0
            else:
                before = state()
                if scale == 1.0:
                    crust_thickness -= (
                        tectonic_activity
                        * (0.45 + (0.20 if plate_changed else 0.0))
                        * div
                    )
                else:
                    crust_thickness -= (
                        tectonic_activity * 0.45 * div * scale
                    )
                    if plate_changed:
                        crust_thickness -= tectonic_activity * 0.20 * div
                # Match the native ordered-rule invariant: divergent thinning
                # may exhaust a transported crust row, but an intermediate
                # scalar reservoir can never have negative thickness.  The
                # later thickness-bound reason owns any explicit reseeding.
                crust_thickness = max(0.0, crust_thickness)
                crust_density += 0.004 * div * scale
                record(3, True, before)
                if div >= 0.24:
                    crust_type = 6
                    lithology = 3

        if conv >= 0.10:
            if old_oceanic:
                before = state()
                crust_thickness += tectonic_activity * 0.34 * conv * scale
                crust_age *= 1.0 - _timestep_scaled_fraction(
                    0.12 * conv,
                    scale,
                )
                record(4, True, before)
                if conv >= 0.26:
                    crust_type = 3
                    lithology = 5
            else:
                before_collision = state()
                if scale == 1.0:
                    combined_thickness = crust_thickness + (
                        tectonic_activity
                        * (0.72 + (0.38 if plate_changed else 0.0))
                        * conv
                    )
                    crust_thickness += tectonic_activity * 0.72 * conv
                    crust_density -= 0.006 * conv * scale
                    record(5, True, before_collision)
                    before_accretion = state()
                    crust_thickness = combined_thickness
                    record(6, plate_changed, before_accretion)
                else:
                    crust_thickness += (
                        tectonic_activity * 0.72 * conv * scale
                    )
                    crust_density -= 0.006 * conv * scale
                    record(5, True, before_collision)
                    before_accretion = state()
                    if plate_changed:
                        crust_thickness += tectonic_activity * 0.38 * conv
                    record(6, plate_changed, before_accretion)
                if plate_changed and conv >= 0.18:
                    crust_type = 8
                    lithology = 6
                elif conv >= 0.28:
                    crust_type = 5
                    lithology = 6

        new_oceanic = _is_oceanic_crust_state(
            crust_type,
            lithology,
            crust_age,
            crust_thickness,
            crust_density,
        )
        before = state()
        age_upper_bound = max(
            0.0,
            min(320.0 if new_oceanic else 4200.0, geological_age * 1000.0),
        )
        crust_age = _clamp(crust_age, 0.0, age_upper_bound)
        record(
            7,
            before.age_ma < 0.0 or before.age_ma > age_upper_bound,
            before,
        )

        before = state()
        minimum_thickness = 4.5 if new_oceanic else 16.0
        maximum_thickness = 18.0 if new_oceanic else 76.0
        crust_thickness = _clamp(
            crust_thickness,
            minimum_thickness,
            maximum_thickness,
        )
        record(
            8,
            before.thickness_km < minimum_thickness
            or before.thickness_km > maximum_thickness,
            before,
        )

        before = state()
        crust_density = _clamp(crust_density, 2.58, 3.08)
        record(
            9,
            before.density < 2.58 or before.density > 3.08,
            before,
        )

        result_types.append(crust_type)
        result_lithologies.append(lithology)
        result_ages.append(crust_age)
        result_thicknesses.append(crust_thickness)
        result_densities.append(crust_density)

    aggregates = [_ReasonAggregate() for _ in CRUST_PROCESS_REASON_ORDER]
    for cell_deltas in cell_reason_deltas:
        for reason_index, delta in enumerate(cell_deltas):
            aggregate = aggregates[reason_index]
            aggregate.triggered_cell_count += int(delta.triggered)
            aggregate.extensive_state_changed_cell_count += int(delta.changed)

    reason_payloads: list[dict[str, Any]] = []
    attributed = [0.0, 0.0, 0.0]
    for reason_index, (reason, aggregate) in enumerate(
        zip(CRUST_PROCESS_REASON_ORDER, aggregates, strict=True)
    ):
        components = (
            "crust_volume_km3",
            "density_weighted_crust_volume",
            "crust_age_volume_moment_km3_ma",
        )
        positive = tuple(
            math.fsum(
                max(0.0, getattr(cell_deltas[reason_index], component))
                for cell_deltas in cell_reason_deltas
            )
            for component in components
        )
        negative = tuple(
            math.fsum(
                max(0.0, -getattr(cell_deltas[reason_index], component))
                for cell_deltas in cell_reason_deltas
            )
            for component in components
        )
        net = tuple(
            positive[component] - negative[component]
            for component in range(3)
        )
        for component in range(3):
            attributed[component] += net[component]
        reason_payloads.append(
            {
                "reason": reason,
                "triggered_cell_count": aggregate.triggered_cell_count,
                "extensive_state_changed_cell_count": (
                    aggregate.extensive_state_changed_cell_count
                ),
                "positive_delta": _delta_payload(*positive),
                "negative_delta_magnitude": _delta_payload(*negative),
                "net_delta": _delta_payload(*net),
            }
        )

    transported_inventory = _inventory(
        areas,
        remapped_thicknesses,
        remapped_densities,
        remapped_ages,
    )
    post_process_inventory = _inventory(
        areas,
        result_thicknesses,
        result_densities,
        result_ages,
    )
    direct_process_delta = tuple(
        post_process_inventory[index] - transported_inventory[index]
        for index in range(3)
    )
    closure_residual = tuple(
        direct_process_delta[index] - attributed[index]
        for index in range(3)
    )

    return {
        "crust_type_by_cell": result_types,
        "lithology_by_cell": result_lithologies,
        "crust_age_ma_by_cell": result_ages,
        "crust_thickness_km_by_cell": result_thicknesses,
        "crust_density_by_cell": result_densities,
        "crust_age_process_change_ma_by_cell": [
            after - before
            for after, before in zip(result_ages, remapped_ages, strict=True)
        ],
        "crust_thickness_process_change_km_by_cell": [
            after - before
            for after, before in zip(
                result_thicknesses,
                remapped_thicknesses,
                strict=True,
            )
        ],
        "crust_density_process_change_by_cell": [
            after - before
            for after, before in zip(
                result_densities,
                remapped_densities,
                strict=True,
            )
        ],
        "reasons": reason_payloads,
        "attributed_inventory_delta": _delta_payload(*attributed),
        "direct_process_inventory_delta": _delta_payload(*direct_process_delta),
        "numerical_closure_residual": _delta_payload(*closure_residual),
        "tectonic_activity_index": tectonic_activity,
    }


def _compare_float_arrays(
    failures: list[str],
    *,
    step_index: int,
    field: str,
    observed: Any,
    expected: Sequence[float],
    operand_scales: Sequence[float],
) -> float:
    if (
        not isinstance(observed, list)
        or len(observed) != len(expected)
        or len(operand_scales) != len(expected)
    ):
        failures.append(f"step {step_index} {field} shape is invalid")
        return math.inf
    maximum_error = 0.0
    for cell_index, (actual, target) in enumerate(
        zip(observed, expected, strict=True)
    ):
        try:
            if isinstance(actual, bool):
                raise TypeError
            actual_float = float(actual)
        except (TypeError, ValueError, OverflowError):
            failures.append(
                f"step {step_index} {field}[{cell_index}] is not numeric"
            )
            return math.inf
        error = abs(actual_float - target)
        maximum_error = max(maximum_error, error)
        operand_scale = abs(float(operand_scales[cell_index]))
        # Process deltas subtract two replayed states after several bounded
        # binary64 operations. Near-zero changes can accumulate slightly more
        # than 64 ULP of the state scale across libm and compiler variants;
        # 128 ULP remains a forward-error envelope, not an empirical epsilon.
        tolerance = 128.0 * max(
            math.ulp(abs(actual_float)),
            math.ulp(abs(target)),
            math.ulp(operand_scale),
        )
        if not math.isfinite(actual_float) or error > tolerance:
            failures.append(
                f"step {step_index} {field}[{cell_index}] does not replay"
            )
            break
    return maximum_error


def _compare_delta_payload(
    failures: list[str],
    *,
    context: str,
    observed: Any,
    expected: dict[str, float],
) -> float:
    if not isinstance(observed, dict) or set(observed) != set(_EXTENSIVE_FIELDS):
        failures.append(f"{context} has an invalid schema")
        return math.inf
    maximum_error = 0.0
    for field in _EXTENSIVE_FIELDS:
        try:
            actual = float(observed[field])
        except (KeyError, TypeError, ValueError, OverflowError):
            failures.append(f"{context}.{field} is not numeric")
            return math.inf
        target = expected[field]
        error = abs(actual - target)
        maximum_error = max(maximum_error, error)
        comparison_scale = max(abs(actual), abs(target))
        tolerance = max(1.0e-8, 64.0 * math.ulp(comparison_scale))
        if not math.isfinite(actual) or error > tolerance:
            failures.append(f"{context}.{field} does not replay")
    return maximum_error


def validate_crust_process_reason_ledger(world: dict[str, Any]) -> dict[str, Any]:
    """Replay and validate every ordered reason ledger in a generated world."""

    failures: list[str] = []
    model = world.get("plate_kinematic_model")
    history = world.get("plate_motion_history")
    cells = world.get("cells")
    if (
        not isinstance(model, dict)
        or not isinstance(history, list)
        or not history
        or not isinstance(cells, list)
        or not cells
    ):
        return {
            "passed": False,
            "failures": ["crust process model, history, or cells are missing"],
            "metrics": {},
        }

    try:
        areas = [float(cell["area_km2"]) for cell in cells]
        scale = float(model["maturation_timestep_scale"])
        reference_aging = float(
            model["reference_oceanic_crust_aging_ma_per_reference_step"]
        )
        internal_heat = float(model["tectonic_process_internal_heat_input"])
        geological_age = float(
            model["tectonic_process_geological_age_ga_input"]
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return {
            "passed": False,
            "failures": ["crust process replay inputs are missing or invalid"],
            "metrics": {},
        }

    expected_reason_names = list(CRUST_PROCESS_REASON_ORDER)
    maximum_state_error = 0.0
    maximum_final_cell_state_error = 0.0
    maximum_reason_delta_error = 0.0
    replayed_step_count = 0

    for step_index, step in enumerate(history):
        if not isinstance(step, dict):
            failures.append(f"step {step_index} is not an object")
            continue
        ledger = step.get("crust_overlap_ledger")
        attribution = (
            ledger.get("process_inventory_attribution")
            if isinstance(ledger, dict)
            else None
        )
        reasons = (
            attribution.get("reasons")
            if isinstance(attribution, dict)
            else None
        )
        if not isinstance(reasons, list) or len(reasons) != len(
            CRUST_PROCESS_REASON_ORDER
        ):
            failures.append(f"step {step_index} reason ledger shape is invalid")
            continue
        observed_reason_names = [
            reason.get("reason") if isinstance(reason, dict) else None
            for reason in reasons
        ]
        if observed_reason_names != expected_reason_names:
            failures.append(f"step {step_index} reason order is invalid")
            continue

        if step_index == 0:
            for reason_index, reason in enumerate(reasons):
                if (
                    type(reason.get("triggered_cell_count")) is not int
                    or reason["triggered_cell_count"] != 0
                    or type(
                        reason.get("extensive_state_changed_cell_count")
                    )
                    is not int
                    or reason["extensive_state_changed_cell_count"] != 0
                ):
                    failures.append(
                        f"initial reason {reason_index} counts are not zero"
                    )
                zero = _delta_payload(0.0, 0.0, 0.0)
                for field in (
                    "positive_delta",
                    "negative_delta_magnitude",
                    "net_delta",
                ):
                    maximum_reason_delta_error = max(
                        maximum_reason_delta_error,
                        _compare_delta_payload(
                            failures,
                            context=f"initial reason {reason_index}.{field}",
                            observed=reason.get(field),
                            expected=zero,
                        ),
                    )
            continue

        previous_step = history[step_index - 1]
        try:
            replay = replay_ordered_crust_process(
                areas_km2=areas,
                remapped_crust_type_by_cell=ledger[
                    "remapped_crust_type_by_cell"
                ],
                remapped_lithology_by_cell=ledger[
                    "remapped_lithology_by_cell"
                ],
                remapped_crust_age_ma_by_cell=ledger[
                    "remapped_crust_age_ma_by_cell"
                ],
                remapped_crust_thickness_km_by_cell=ledger[
                    "remapped_crust_thickness_km_by_cell"
                ],
                remapped_crust_density_by_cell=ledger[
                    "remapped_crust_density_by_cell"
                ],
                previous_plate_ids=previous_step["cell_plate_ids"],
                current_plate_ids=step["cell_plate_ids"],
                boundary_convergent_by_cell=step[
                    "boundary_convergent_by_cell"
                ],
                boundary_divergent_by_cell=step[
                    "boundary_divergent_by_cell"
                ],
                timestep_scale=scale,
                reference_oceanic_crust_aging_ma_per_reference_step=(
                    reference_aging
                ),
                internal_heat=internal_heat,
                geological_age_ga=geological_age,
            )
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            failures.append(f"step {step_index} replay inputs are invalid: {error}")
            continue
        replayed_step_count += 1

        for field in ("crust_type_by_cell", "lithology_by_cell"):
            observed = step.get(field)
            expected = replay[field]
            if observed != expected:
                failures.append(f"step {step_index} {field} does not replay")

        for field in (
            "crust_age_process_change_ma_by_cell",
            "crust_thickness_process_change_km_by_cell",
            "crust_density_process_change_by_cell",
        ):
            state_field, remapped_field = {
                "crust_age_process_change_ma_by_cell": (
                    "crust_age_ma_by_cell",
                    "remapped_crust_age_ma_by_cell",
                ),
                "crust_thickness_process_change_km_by_cell": (
                    "crust_thickness_km_by_cell",
                    "remapped_crust_thickness_km_by_cell",
                ),
                "crust_density_process_change_by_cell": (
                    "crust_density_by_cell",
                    "remapped_crust_density_by_cell",
                ),
            }[field]
            maximum_state_error = max(
                maximum_state_error,
                _compare_float_arrays(
                    failures,
                    step_index=step_index,
                    field=field,
                    observed=step.get(field),
                    expected=replay[field],
                    operand_scales=[
                        max(abs(before), abs(after))
                        for before, after in zip(
                            ledger[remapped_field],
                            replay[state_field],
                            strict=True,
                        )
                    ],
                ),
            )

        for reason_index, (observed, expected) in enumerate(
            zip(reasons, replay["reasons"], strict=True)
        ):
            for count_field in (
                "triggered_cell_count",
                "extensive_state_changed_cell_count",
            ):
                if (
                    type(observed.get(count_field)) is not int
                    or observed[count_field] != expected[count_field]
                ):
                    failures.append(
                        f"step {step_index} reason {reason_index} "
                        f"{count_field} does not replay"
                    )
            for delta_field in (
                "positive_delta",
                "negative_delta_magnitude",
                "net_delta",
            ):
                maximum_reason_delta_error = max(
                    maximum_reason_delta_error,
                    _compare_delta_payload(
                        failures,
                        context=(
                            f"step {step_index} reason {reason_index}."
                            f"{delta_field}"
                        ),
                        observed=observed.get(delta_field),
                        expected=expected[delta_field],
                    ),
                )

        maximum_reason_delta_error = max(
            maximum_reason_delta_error,
            _compare_delta_payload(
                failures,
                context=f"step {step_index}.attributed_inventory_delta",
                observed=attribution.get("attributed_inventory_delta"),
                expected=replay["attributed_inventory_delta"],
            ),
        )

    last_step = history[-1]
    last_ledger = (
        last_step.get("crust_overlap_ledger")
        if isinstance(last_step, dict)
        else None
    )
    if not isinstance(last_ledger, dict):
        failures.append("final crust state replay metadata is invalid")
    else:
        final_types = last_step.get("crust_type_by_cell")
        final_lithologies = last_step.get("lithology_by_cell")
        if (
            not isinstance(final_types, list)
            or len(final_types) != len(cells)
            or any(
                type(value) is not int or not 0 <= value < len(_CRUST_NAMES)
                for value in final_types
            )
            or not isinstance(final_lithologies, list)
            or len(final_lithologies) != len(cells)
            or any(
                type(value) is not int
                or not 0 <= value < len(_LITHOLOGY_NAMES)
                for value in final_lithologies
            )
        ):
            failures.append("final crust categorical history is invalid")
        else:
            for cell_index, cell in enumerate(cells):
                if (
                    not isinstance(cell, dict)
                    or cell.get("crust_type")
                    != _CRUST_NAMES[final_types[cell_index]]
                    or cell.get("lithology")
                    != _LITHOLOGY_NAMES[final_lithologies[cell_index]]
                ):
                    failures.append(
                        f"final cell {cell_index} crust category does not "
                        "match the last history step"
                    )
                    break

        final_numeric_fields = (
            (
                "crust_age_ma",
                "remapped_crust_age_ma_by_cell",
                "crust_age_process_change_ma_by_cell",
            ),
            (
                "crust_thickness_km",
                "remapped_crust_thickness_km_by_cell",
                "crust_thickness_process_change_km_by_cell",
            ),
            (
                "crust_density",
                "remapped_crust_density_by_cell",
                "crust_density_process_change_by_cell",
            ),
        )
        for cell_field, remapped_field, process_field in final_numeric_fields:
            remapped = last_ledger.get(remapped_field)
            process = last_step.get(process_field)
            if (
                not isinstance(remapped, list)
                or not isinstance(process, list)
                or len(remapped) != len(cells)
                or len(process) != len(cells)
            ):
                failures.append(
                    f"final {cell_field} history arrays are invalid"
                )
                continue
            for cell_index, cell in enumerate(cells):
                try:
                    observed = cell[cell_field]
                    if isinstance(observed, bool):
                        raise TypeError
                    observed_float = float(observed)
                    remapped_float = float(remapped[cell_index])
                    process_float = float(process[cell_index])
                    expected_float = (
                        remapped_float + process_float
                    )
                except (
                    KeyError,
                    TypeError,
                    ValueError,
                    OverflowError,
                ):
                    failures.append(
                        f"final cell {cell_index} {cell_field} is invalid"
                    )
                    break
                error = abs(observed_float - expected_float)
                maximum_final_cell_state_error = max(
                    maximum_final_cell_state_error,
                    error,
                )
                try:
                    tolerance = _final_crust_alias_binary64_bound(
                        observed_float,
                        remapped_float,
                        process_float,
                        expected_float,
                    )
                except ValueError:
                    tolerance = math.nan
                if (
                    not math.isfinite(observed_float)
                    or not math.isfinite(expected_float)
                    or not math.isfinite(tolerance)
                    or error > tolerance
                ):
                    failures.append(
                        f"final cell {cell_index} {cell_field} does not "
                        "match the last history step"
                    )
                    break

    return {
        "passed": not failures,
        "failures": failures,
        "metrics": {
            "replayed_crust_process_step_count": replayed_step_count,
            "maximum_crust_process_state_replay_error": maximum_state_error,
            "maximum_final_cell_crust_state_replay_error": (
                maximum_final_cell_state_error
            ),
            "maximum_crust_process_reason_delta_replay_error": (
                maximum_reason_delta_error
            ),
        },
    }
