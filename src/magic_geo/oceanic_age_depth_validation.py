from __future__ import annotations

import math
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .crust_transport_validation import validate_crust_overlap_transport


MODEL = "continuity_adjusted_parsons_sclater_relative_basement_subsidence_v1"
YOUNG_AGE_CUTOFF_MA = 70.0
YOUNG_COEFFICIENT_M_PER_SQRT_MA = 350.0
OLD_AGE_EXPONENTIAL_SCALE_M = 3200.0
OLD_AGE_EFOLDING_TIME_MA = 62.8
THERMAL_TARGET_DIFFERENCE_GAIN = 1.0
ISOSTATIC_TARGET_DIFFERENCE_GAIN = 1.0
CONTINENTAL_ISOSTATIC_FREEBOARD_M = 500.0
OCEANIC_RIDGE_REFERENCE_DEPTH_M = 2500.0
CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM = 30.0
CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM = 12.0
CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3 = 2.72
CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3 = 1800.0
DYNAMIC_RELIEF_MINIMUM_CHANGE_M = -180.0
DYNAMIC_RELIEF_MAXIMUM_CHANGE_M = 220.0
TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION = 0.42

# C++ does not require correctly rounded libm transcendental functions.  Four
# ULP per sqrt/exp result is an explicit finite portability envelope; replay
# compares two implementations, so local propagation uses twice this amount.
LIBM_TRANSCENDENTAL_ULP_ENVELOPE = 4

# These are the existing public configuration bounds.  Preflighting them before
# walking any nested column prevents a malformed external JSON document from
# turning validation into unbounded work.
MAXIMUM_CELL_COUNT = 200_000
MAXIMUM_HISTORY_STEP_COUNT = 251

CRUST_NAMES = (
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
LITHOLOGY_NAMES = (
    "basalt",
    "granite",
    "limestone",
    "sandstone",
    "shale",
    "volcanic",
    "metamorphic",
)

MODEL_LITERAL_VALUES: dict[str, Any] = {
    "model": MODEL,
    "authority_scope": "relative_oceanic_thermal_subsidence_target_curve_only",
    "source_doi": "10.1029/JB082i005p00803",
    "source_relation_scope": (
        "parsons_sclater_1977_supplies_young_350_sqrt_t_relation_and_old_"
        "3200_exp_minus_t_over_62_8_shape"
    ),
    "continuity_adjustment": (
        "implementation_switches_at_70_ma_and_adds_an_offset_to_the_old_"
        "branch_for_c0_value_continuity_not_c1_slope_continuity"
    ),
    "age_input_unit": "Ma",
    "thermal_subsidence_output_unit": "m",
    "young_age_cutoff_ma": YOUNG_AGE_CUTOFF_MA,
    "young_age_coefficient_m_per_sqrt_ma": YOUNG_COEFFICIENT_M_PER_SQRT_MA,
    "old_age_exponential_scale_m": OLD_AGE_EXPONENTIAL_SCALE_M,
    "old_age_efolding_time_ma": OLD_AGE_EFOLDING_TIME_MA,
    "young_relative_subsidence_formula": (
        "S_m=350*sqrt(t_ma)_for_0_le_t_ma_le_70"
    ),
    "old_relative_subsidence_formula": (
        "S_m=350*sqrt(70)+3200*(exp(-70/62.8)-exp(-t_ma/62.8))_"
        "for_t_ma_gt_70"
    ),
    "thermal_subsidence_sign_formula": (
        "thermal_subsidence_target_m=-S_m_for_oceanic_like_else_0"
    ),
    "oceanic_like_predicate": (
        "crust_type_0_or_crust_type_2_with_lithology_0_or_crust_type_3_"
        "with_age_le_320_ma_thickness_le_18_km_density_ge_2_84_g_cm3"
    ),
    "history_location": "plate_motion_history[]",
    "final_cell_field": "cells[].thermal_subsidence_target_m",
    "authoritative_formula_root": (
        "plate_motion_history_crust_overlap_remapped_numeric_state_plus_same_"
        "step_process_deltas_and_step_categorical_state"
    ),
    "final_cell_crust_numeric_root_semantics": (
        "binary64_round_trip_aliases_cross_checked_against_authoritative_"
        "history_roots"
    ),
    "previous_local_state_semantics": (
        "same_cell_id_equilibrium_target_immediately_before_same_step_overlap_"
        "transport_and_ordered_crust_process_rules"
    ),
    "post_process_local_state_semantics": (
        "same_cell_id_equilibrium_target_after_same_step_overlap_transport_"
        "ordered_crust_process_rules_and_state_bounds"
    ),
    "initial_step_checkpoint_semantics": (
        "previous_local_target_equals_post_process_initial_target_and_thermal_"
        "equilibrium_change_is_zero"
    ),
    "thermal_target_difference_gain": THERMAL_TARGET_DIFFERENCE_GAIN,
    "thermal_equilibrium_change_formula": (
        "1.0*(post_process_local_thermal_subsidence_target_m-previous_local_"
        "thermal_subsidence_target_m)"
    ),
    "thermal_equilibrium_change_application": (
        "full_target_difference_is_applied_outside_the_bounded_dynamic_relief_"
        "clamp_with_zero_unapplied_equilibrium_residual"
    ),
    "thermal_equilibrium_change_application_replayed": True,
    "array_serialization_model": (
        "general_format_max_digits10_binary64_round_trip_v1"
    ),
    "array_cardinality": (
        "each_thermal_target_or_equilibrium_change_array_length_equals_plate_"
        "motion_step_cell_count"
    ),
    "finite_nonnegative_age_required": True,
    "continuity_at_transition_resolved": True,
    "derivative_continuity_at_transition_resolved": False,
    "authoritative_for_relative_thermal_subsidence_target_curve": True,
    "authoritative_for_realized_thermal_relief_component": False,
    "realized_thermal_relief_state_tracked": False,
    "thermal_relaxation_timescale_calibrated": False,
    "unapplied_thermal_tendency_residual_carried_forward": False,
    "unapplied_thermal_equilibrium_residual_zero_by_construction": True,
    "thermal_contribution_outside_bounded_dynamic_relief_clamp_resolved": True,
    "thermal_contribution_to_tectonic_elevation_change_replayed": True,
    "absolute_basement_depth_calibrated": False,
    "physical_crust_creation_age_provenance": False,
    "ridge_age_distance_consistency": False,
    "thermal_structure_represented": False,
    "heat_flow_represented": False,
    "dynamic_topography_represented": False,
    "flexure_represented": False,
    "physical_dynamics_represented": False,
}

KINEMATIC_EQUILIBRIUM_LITERAL_VALUES: dict[str, Any] = {
    "continental_isostatic_freeboard_m": CONTINENTAL_ISOSTATIC_FREEBOARD_M,
    "oceanic_ridge_reference_depth_m": OCEANIC_RIDGE_REFERENCE_DEPTH_M,
    "continental_reference_crust_thickness_km": (
        CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM
    ),
    "continental_crust_thickness_freeboard_m_per_km": (
        CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM
    ),
    "continental_reference_crust_density_g_cm3": (
        CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3
    ),
    "continental_crust_density_freeboard_m_per_g_cm3": (
        CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3
    ),
    "isostatic_equilibrium_formula": (
        "oceanic_like?-2500:500+12*(crust_thickness_km-30)-1800*"
        "(crust_density_g_cm3-2.72)"
    ),
    "tectonic_process_boundary_input_locations": [
        "plate_motion_history[].boundary_convergent_by_cell",
        "plate_motion_history[].boundary_divergent_by_cell",
        "plate_motion_history[].boundary_transform_by_cell",
    ],
    "tectonic_activity_formula": (
        "clamp(internal_heat*sqrt(4.5/max(0.05,geological_age_ga)),0.25,2.25)"
    ),
    "tectonic_equilibrium_adjustment_model": (
        "quasi_static_full_local_target_difference_plus_bounded_dynamic_"
        "relief_v1"
    ),
    "equilibrium_timescale_separation_basis": (
        "nominal_5_ma_reference_step_is_more_than_three_orders_of_magnitude_"
        "longer_than_3_to_4_ka_degree_2_to_20_viscoelastic_relaxation_estimates"
    ),
    "isostatic_relaxation_source_doi": (
        "10.1111/j.1365-246X.1971.tb01823.x"
    ),
    "isostatic_relaxation_reference_min_years": 3000.0,
    "isostatic_relaxation_reference_max_years": 4000.0,
    "isostatic_target_difference_gain": ISOSTATIC_TARGET_DIFFERENCE_GAIN,
    "thermal_target_difference_gain": THERMAL_TARGET_DIFFERENCE_GAIN,
    "equilibrium_target_difference_clamped": False,
    "equilibrium_operator_physical_time_calibrated": False,
    "combined_tectonic_equilibrium_and_dynamic_clamp_present": False,
    "dynamic_relief_change_formula": (
        "tectonic_uplift_scale*tectonic_activity*(1.5*divergence+8.5*"
        "convergence+2.5_if_volcanic_arc)*maturation_timestep_scale*0.42+80*"
        "(convergence-previous_convergence)+55*(divergence-previous_"
        "divergence)-30*(transform-previous_transform)"
    ),
    "tectonic_uplift_rate_response_fraction": (
        TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION
    ),
    "dynamic_relief_minimum_change_m": DYNAMIC_RELIEF_MINIMUM_CHANGE_M,
    "dynamic_relief_maximum_change_m": DYNAMIC_RELIEF_MAXIMUM_CHANGE_M,
    "bounded_dynamic_relief_formula": (
        "clamp(unbounded_dynamic_relief_change_m,-180,220)"
    ),
    "tectonic_elevation_change_formula": (
        "isostatic_equilibrium_change_m+thermal_equilibrium_change_m+"
        "bounded_dynamic_relief_change_m"
    ),
    "tectonic_equilibrium_history_location": "plate_motion_history[]",
    "tectonic_equilibrium_application_replayable": True,
}

# Hex literals make these fixed-age analytical checks independent of the
# implementation expression while retaining exact binary64 oracle values.
ANALYTICAL_CHECKPOINTS_M = (
    (0.0, float.fromhex("0x0.0p+0")),
    (20.0, float.fromhex("0x1.874fd86b9c07ep+10")),
    (math.nextafter(70.0, -math.inf), float.fromhex("0x1.6e09ec47e186cp+11")),
    (70.0, float.fromhex("0x1.6e09ec47e186dp+11")),
    (math.nextafter(70.0, math.inf), float.fromhex("0x1.6e09ec47e186ep+11")),
    (100.0, float.fromhex("0x1.9fdf626e95a4cp+11")),
    (320.0, float.fromhex("0x1.eecd1dbd7cee1p+11")),
)


class _InvalidOceanicAgeDepth(ValueError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _InvalidOceanicAgeDepth(message)


def _finite(value: Any, field: str) -> float:
    if type(value) not in (int, float):
        raise _InvalidOceanicAgeDepth(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise _InvalidOceanicAgeDepth(f"{field} must be finite")
    return result


def _integer(value: Any, field: str) -> int:
    if type(value) is not int:
        raise _InvalidOceanicAgeDepth(f"{field} must be an integer")
    return value


def _operation_bound(
    actual: float,
    expected: float,
    *,
    operands: Sequence[float],
    operation_count: int,
) -> float:
    """Portable binary64 forward bound derived only from replay operations."""

    _require(operation_count >= 0, "operation count must be nonnegative")
    values = (actual, expected, *operands)
    _require(all(math.isfinite(value) for value in values), "bound operands must be finite")
    absolute_operand_sum = math.fsum(abs(value) for value in operands)
    epsilon_product = operation_count * sys.float_info.epsilon
    _require(epsilon_product < 1.0, "operation count exceeds binary64 bound domain")
    gamma = epsilon_product / (1.0 - epsilon_product)
    scale = max((abs(value) for value in values), default=0.0)
    serialization_rounding = 2.0 * math.ulp(scale)
    bound = gamma * absolute_operand_sum + serialization_rounding
    _require(math.isfinite(bound), "binary64 operation bound overflowed")
    return bound


def _relative_subsidence_and_bound(age_ma: float) -> tuple[float, float]:
    age = _finite(age_ma, "age_ma")
    _require(age >= 0.0, "age_ma must be nonnegative")
    if age <= YOUNG_AGE_CUTOFF_MA:
        root = math.sqrt(age)
        value = YOUNG_COEFFICIENT_M_PER_SQRT_MA * root
        root_error = (
            2.0 * LIBM_TRANSCENDENTAL_ULP_ENVELOPE * math.ulp(root)
        )
        multiplication_error = math.ulp(value)
        return (
            value,
            YOUNG_COEFFICIENT_M_PER_SQRT_MA * root_error
            + multiplication_error,
        )

    cutoff_root = math.sqrt(YOUNG_AGE_CUTOFF_MA)
    cutoff_value = YOUNG_COEFFICIENT_M_PER_SQRT_MA * cutoff_root
    cutoff_quotient = -YOUNG_AGE_CUTOFF_MA / OLD_AGE_EFOLDING_TIME_MA
    age_quotient = -age / OLD_AGE_EFOLDING_TIME_MA
    cutoff_decay = math.exp(cutoff_quotient)
    age_decay = math.exp(age_quotient)
    decay_difference = cutoff_decay - age_decay
    increment = OLD_AGE_EXPONENTIAL_SCALE_M * decay_difference
    value = cutoff_value + increment
    cutoff_root_error = (
        2.0 * LIBM_TRANSCENDENTAL_ULP_ENVELOPE * math.ulp(cutoff_root)
    )
    cutoff_value_error = (
        YOUNG_COEFFICIENT_M_PER_SQRT_MA * cutoff_root_error
        + math.ulp(cutoff_value)
    )
    cutoff_quotient_error = math.ulp(cutoff_quotient)
    age_quotient_error = math.ulp(age_quotient)

    def exp_error(value: float, quotient: float, quotient_error: float) -> float:
        input_propagation = max(
            abs(math.exp(quotient - quotient_error) - value),
            abs(math.exp(quotient + quotient_error) - value),
        )
        libm_error = (
            2.0 * LIBM_TRANSCENDENTAL_ULP_ENVELOPE * math.ulp(value)
        )
        return input_propagation + libm_error

    cutoff_decay_error = exp_error(
        cutoff_decay, cutoff_quotient, cutoff_quotient_error
    )
    age_decay_error = exp_error(age_decay, age_quotient, age_quotient_error)
    difference_error = (
        cutoff_decay_error + age_decay_error + math.ulp(decay_difference)
    )
    increment_error = (
        OLD_AGE_EXPONENTIAL_SCALE_M * difference_error + math.ulp(increment)
    )
    return value, cutoff_value_error + increment_error + math.ulp(value)


def _target_change_operation_bound(
    actual: float,
    previous: float,
    post: float,
    expected: float,
    gain: float,
) -> float:
    difference = post - previous
    subtraction_error = math.ulp(difference)
    multiplication_error = (
        gain * subtraction_error
        + math.ulp(expected)
    )
    # The actual and independently replayed result are each binary64 values.
    return multiplication_error + math.ulp(max(abs(actual), abs(expected)))


def _telescoping_operation_bound(
    actual: float,
    expected: float,
    *,
    absolute_change_sum: float,
    change_rounding_bound_sum: float,
    addition_count: int,
) -> float:
    """Bound a sum of rounded target differences against its endpoints."""

    values = (
        actual,
        expected,
        absolute_change_sum,
        change_rounding_bound_sum,
    )
    _require(all(math.isfinite(value) for value in values), "telescoping operands must be finite")
    _require(
        absolute_change_sum >= 0.0 and change_rounding_bound_sum >= 0.0,
        "telescoping operand sums must be nonnegative",
    )
    _require(addition_count >= 0, "telescoping addition count must be nonnegative")
    epsilon_product = addition_count * sys.float_info.epsilon
    _require(
        epsilon_product < 1.0,
        "telescoping addition count exceeds binary64 bound domain",
    )
    accumulation_rounding = (
        epsilon_product / (1.0 - epsilon_product)
    ) * absolute_change_sum
    # Each per-step change bound includes the rounding of its target
    # subtraction and gain multiplication.  Exact target differences then
    # telescope algebraically.  The remaining terms cover the independent
    # endpoint subtraction and the residual subtraction used by this check.
    endpoint_rounding = math.ulp(expected)
    comparison_rounding = math.ulp(actual - expected)
    bound = (
        accumulation_rounding
        + change_rounding_bound_sum
        + endpoint_rounding
        + comparison_rounding
    )
    _require(math.isfinite(bound), "telescoping binary64 bound overflowed")
    return bound


def oceanic_relative_basement_subsidence_m(age_ma: float) -> float:
    """Return positive ridge-relative basement subsidence for an age in Ma."""

    return _relative_subsidence_and_bound(age_ma)[0]


def is_oceanic_like_crust_state(
    crust_type: int,
    lithology: int,
    age_ma: float,
    thickness_km: float,
    density_g_cm3: float,
) -> bool:
    """Replay the exact categorical/numeric predicate used by the native model."""

    crust = _integer(crust_type, "crust_type")
    rock = _integer(lithology, "lithology")
    _require(0 <= crust < len(CRUST_NAMES), "crust_type is outside its enum range")
    _require(0 <= rock < len(LITHOLOGY_NAMES), "lithology is outside its enum range")
    age = _finite(age_ma, "age_ma")
    thickness = _finite(thickness_km, "thickness_km")
    density = _finite(density_g_cm3, "density_g_cm3")
    _require(
        age >= 0.0 and thickness >= 0.0 and density > 0.0,
        "crust numeric state is invalid",
    )
    if crust == 0:
        return True
    if crust == 2:
        return rock == 0
    if crust != 3:
        return False
    return age <= 320.0 and thickness <= 18.0 and density >= 2.84


@dataclass(frozen=True)
class _EquilibriumInputs:
    timestep_scale: float
    tectonic_activity: float
    tectonic_uplift_scale: float


def _validate_model(model: Any) -> None:
    _require(isinstance(model, dict), "oceanic_age_depth_model must be an object")
    _require(
        set(model) == set(MODEL_LITERAL_VALUES),
        "oceanic_age_depth_model fields do not match the canonical schema",
    )
    for field, expected in MODEL_LITERAL_VALUES.items():
        actual = model[field]
        if type(expected) is bool:
            _require(actual is expected, f"oceanic_age_depth_model.{field} is invalid")
        elif type(expected) is float:
            _require(
                _finite(actual, f"oceanic_age_depth_model.{field}") == expected,
                f"oceanic_age_depth_model.{field} is invalid",
            )
        else:
            _require(actual == expected, f"oceanic_age_depth_model.{field} is invalid")


def _validate_kinematic_equilibrium_model(model: Any) -> _EquilibriumInputs:
    label = "plate_kinematic_model"
    _require(isinstance(model, dict), f"{label} must be an object")
    for field, expected in KINEMATIC_EQUILIBRIUM_LITERAL_VALUES.items():
        _require(field in model, f"{label}.{field} is missing")
        actual = model[field]
        if type(expected) is bool:
            _require(actual is expected, f"{label}.{field} is invalid")
        elif type(expected) is float:
            _require(
                _finite(actual, f"{label}.{field}") == expected,
                f"{label}.{field} is invalid",
            )
        else:
            _require(actual == expected, f"{label}.{field} is invalid")

    nominal_timestep = _finite(
        model.get("nominal_timestep_ma"), f"{label}.nominal_timestep_ma"
    )
    reference_timestep = _finite(
        model.get("reference_timestep_ma"), f"{label}.reference_timestep_ma"
    )
    timestep_scale = _finite(
        model.get("maturation_timestep_scale"),
        f"{label}.maturation_timestep_scale",
    )
    _require(
        0.0 < nominal_timestep <= 5.0 and reference_timestep == 5.0,
        f"{label} timestep operands are invalid",
    )
    expected_timestep_scale = nominal_timestep / reference_timestep
    scale_bound = _operation_bound(
        timestep_scale,
        expected_timestep_scale,
        operands=(nominal_timestep, reference_timestep),
        operation_count=1,
    )
    _require(
        abs(timestep_scale - expected_timestep_scale) <= scale_bound,
        f"{label}.maturation_timestep_scale does not replay",
    )

    internal_heat = _finite(
        model.get("tectonic_process_internal_heat_input"),
        f"{label}.tectonic_process_internal_heat_input",
    )
    geological_age = _finite(
        model.get("tectonic_process_geological_age_ga_input"),
        f"{label}.tectonic_process_geological_age_ga_input",
    )
    tectonic_activity = _finite(
        model.get("tectonic_activity_index"), f"{label}.tectonic_activity_index"
    )
    _require(
        internal_heat >= 0.0 and geological_age > 0.0,
        f"{label} tectonic activity operands are invalid",
    )
    activity_root = math.sqrt(4.5 / max(0.05, geological_age))
    expected_activity = min(2.25, max(0.25, internal_heat * activity_root))
    activity_bound = _operation_bound(
        tectonic_activity,
        expected_activity,
        operands=(internal_heat, geological_age, activity_root),
        operation_count=5,
    ) + (
        2.0
        * LIBM_TRANSCENDENTAL_ULP_ENVELOPE
        * abs(internal_heat)
        * math.ulp(activity_root)
    )
    _require(
        abs(tectonic_activity - expected_activity) <= activity_bound,
        f"{label}.tectonic_activity_index does not replay",
    )

    tectonic_uplift_scale = _finite(
        model.get("tectonic_uplift_scale_input"),
        f"{label}.tectonic_uplift_scale_input",
    )
    _require(
        0.0 <= tectonic_uplift_scale <= 10.0,
        f"{label}.tectonic_uplift_scale_input is invalid",
    )
    return _EquilibriumInputs(
        timestep_scale=timestep_scale,
        tectonic_activity=tectonic_activity,
        tectonic_uplift_scale=tectonic_uplift_scale,
    )


def _validate_analytical_checkpoints() -> tuple[float, float]:
    maximum_residual = 0.0
    maximum_bound = 0.0
    previous = -math.inf
    for age, oracle in ANALYTICAL_CHECKPOINTS_M:
        actual, formula_bound = _relative_subsidence_and_bound(age)
        bound = formula_bound + _operation_bound(
            actual,
            oracle,
            operands=(actual, oracle),
            operation_count=2,
        )
        residual = abs(actual - oracle)
        _require(residual <= bound, f"analytical checkpoint at {age!r} Ma does not replay")
        _require(actual >= previous, "analytical age-depth checkpoints are not monotonic")
        previous = actual
        maximum_residual = max(maximum_residual, residual)
        maximum_bound = max(maximum_bound, bound)

    cutoff = oceanic_relative_basement_subsidence_m(YOUNG_AGE_CUTOFF_MA)
    old_at_cutoff = (
        YOUNG_COEFFICIENT_M_PER_SQRT_MA * math.sqrt(YOUNG_AGE_CUTOFF_MA)
        + OLD_AGE_EXPONENTIAL_SCALE_M
        * (
            math.exp(-YOUNG_AGE_CUTOFF_MA / OLD_AGE_EFOLDING_TIME_MA)
            - math.exp(-YOUNG_AGE_CUTOFF_MA / OLD_AGE_EFOLDING_TIME_MA)
        )
    )
    _require(cutoff == old_at_cutoff, "age-depth branches are not C0-continuous")
    return maximum_residual, maximum_bound


@dataclass
class _CrustState:
    crust_types: list[int]
    lithologies: list[int]
    ages_ma: list[float]
    thicknesses_km: list[float]
    densities_g_cm3: list[float]
    age_error_bounds_ma: list[float]
    thickness_error_bounds_km: list[float]
    density_error_bounds_g_cm3: list[float]


@dataclass
class _FsumAccumulator:
    """Incremental exact-partial accumulator used for nonnegative bounds."""

    partials: list[float] = field(default_factory=list)

    def add(self, value: float) -> None:
        x = value
        kept = 0
        for y in self.partials:
            if abs(x) < abs(y):
                x, y = y, x
            high = x + y
            low = y - (high - x)
            if low != 0.0:
                self.partials[kept] = low
                kept += 1
            x = high
        self.partials[kept:] = [x]

    def total(self) -> float:
        return math.fsum(self.partials)


@dataclass
class _OrderedReplay:
    actual_sum: float = 0.0
    expected_sum: float = 0.0
    absolute_operand_sum: _FsumAccumulator = field(
        default_factory=_FsumAccumulator
    )
    element_bound_sum: _FsumAccumulator = field(
        default_factory=_FsumAccumulator
    )
    count: int = 0

    def add(self, actual: float, expected: float, element_bound: float) -> None:
        self.actual_sum += actual
        self.expected_sum += expected
        self.absolute_operand_sum.add(abs(actual))
        self.absolute_operand_sum.add(abs(expected))
        self.element_bound_sum.add(element_bound)
        self.count += 1

    def residual_and_bound(self) -> tuple[float, float]:
        residual = abs(self.actual_sum - self.expected_sum)
        reduction_bound = _operation_bound(
            self.actual_sum,
            self.expected_sum,
            operands=(self.absolute_operand_sum.total(),),
            operation_count=2 * max(0, self.count - 1),
        )
        return residual, self.element_bound_sum.total() + reduction_bound


def _numeric_array(
    parent: Mapping[str, Any], key: str, count: int, label: str
) -> list[float]:
    value = parent.get(key)
    _require(
        isinstance(value, list) and len(value) == count,
        f"{label}.{key} must contain exactly {count} entries",
    )
    return [_finite(item, f"{label}.{key}[{index}]") for index, item in enumerate(value)]


def _integer_array(
    parent: Mapping[str, Any], key: str, count: int, label: str
) -> list[int]:
    value = parent.get(key)
    _require(
        isinstance(value, list) and len(value) == count,
        f"{label}.{key} must contain exactly {count} entries",
    )
    return [_integer(item, f"{label}.{key}[{index}]") for index, item in enumerate(value)]


def _preflight(world: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cells = world.get("cells")
    history = world.get("plate_motion_history")
    _require(
        isinstance(cells, list) and 0 < len(cells) <= MAXIMUM_CELL_COUNT,
        "cells must be a nonempty array within the configured cell-count bound",
    )
    _require(
        isinstance(history, list)
        and 0 < len(history) <= MAXIMUM_HISTORY_STEP_COUNT,
        "plate_motion_history must be nonempty and within the configured history bound",
    )
    _require(
        all(isinstance(cell, dict) for cell in cells),
        "cells must contain only objects",
    )
    _require(
        all(isinstance(step, dict) for step in history),
        "plate_motion_history must contain only objects",
    )
    typed_cells = list(cells)
    typed_history = list(history)
    cell_count = len(typed_cells)

    kinematic = world.get("plate_kinematic_model")
    _require(isinstance(kinematic, dict), "plate_kinematic_model must be an object")
    configured_steps = _integer(
        kinematic.get("configured_motion_step_count"),
        "plate_kinematic_model.configured_motion_step_count",
    )
    history_steps = _integer(
        kinematic.get("history_step_count"),
        "plate_kinematic_model.history_step_count",
    )
    _require(
        0 <= configured_steps <= MAXIMUM_HISTORY_STEP_COUNT - 1
        and configured_steps + 1 == len(typed_history)
        and history_steps == len(typed_history),
        "plate kinematic history cardinality is invalid",
    )

    relevant_step_arrays = (
        "crust_type_by_cell",
        "lithology_by_cell",
        "crust_age_process_change_ma_by_cell",
        "crust_thickness_process_change_km_by_cell",
        "crust_density_process_change_by_cell",
        "crust_age_change_ma_by_cell",
        "crust_thickness_change_km_by_cell",
        "crust_density_change_by_cell",
        "boundary_convergent_by_cell",
        "boundary_divergent_by_cell",
        "boundary_transform_by_cell",
        "previous_local_isostatic_equilibrium_m",
        "post_process_local_isostatic_equilibrium_m",
        "isostatic_equilibrium_change_m",
        "previous_local_thermal_subsidence_target_m",
        "post_process_local_thermal_subsidence_target_m",
        "thermal_equilibrium_change_m",
        "unbounded_dynamic_relief_change_m",
        "bounded_dynamic_relief_change_m",
        "tectonic_elevation_change_m_by_cell",
    )
    relevant_ledger_arrays = (
        "remapped_crust_age_ma_by_cell",
        "remapped_crust_thickness_km_by_cell",
        "remapped_crust_density_by_cell",
    )
    for step_index, step in enumerate(typed_history):
        label = f"plate_motion_history[{step_index}]"
        _require(
            _integer(step.get("id"), f"{label}.id") == step_index,
            f"{label}.id is not canonical",
        )
        _require(
            _integer(step.get("cell_count"), f"{label}.cell_count") == cell_count,
            f"{label}.cell_count does not match cells",
        )
        for field in relevant_step_arrays:
            value = step.get(field)
            _require(
                isinstance(value, list) and len(value) == cell_count,
                f"{label}.{field} must contain exactly {cell_count} entries",
            )
        ledger = step.get("crust_overlap_ledger")
        _require(isinstance(ledger, dict), f"{label}.crust_overlap_ledger is missing")
        for field in relevant_ledger_arrays:
            value = ledger.get(field)
            _require(
                isinstance(value, list) and len(value) == cell_count,
                f"{label}.crust_overlap_ledger.{field} must contain exactly {cell_count} entries",
            )
    return typed_cells, typed_history


def _reconstruction_bound(left: float, delta: float, result: float) -> float:
    operation_bound = _operation_bound(
        result,
        result,
        operands=(left, delta, result),
        operation_count=2,
    )
    # The serialized delta was itself formed as post-state minus remapped
    # state. Re-adding it can lose low bits under near-total cancellation even
    # though every serialized operand is round-trip binary64. Match the crust
    # process replay's explicit 128-ULP forward envelope for this two-stage
    # subtract/add reconstruction; this is scale-derived, not a fit epsilon.
    cancellation_bound = 128.0 * max(
        math.ulp(abs(left)),
        math.ulp(abs(delta)),
        math.ulp(abs(result)),
    )
    return operation_bound + cancellation_bound


def _build_post_process_state(
    step: Mapping[str, Any],
    *,
    step_index: int,
    cell_count: int,
    previous: _CrustState | None,
) -> tuple[_CrustState, float, float]:
    label = f"plate_motion_history[{step_index}]"
    ledger = step["crust_overlap_ledger"]
    assert isinstance(ledger, dict)
    remapped_ages = _numeric_array(
        ledger, "remapped_crust_age_ma_by_cell", cell_count, f"{label}.crust_overlap_ledger"
    )
    remapped_thicknesses = _numeric_array(
        ledger,
        "remapped_crust_thickness_km_by_cell",
        cell_count,
        f"{label}.crust_overlap_ledger",
    )
    remapped_densities = _numeric_array(
        ledger,
        "remapped_crust_density_by_cell",
        cell_count,
        f"{label}.crust_overlap_ledger",
    )
    process_age = _numeric_array(
        step, "crust_age_process_change_ma_by_cell", cell_count, label
    )
    process_thickness = _numeric_array(
        step, "crust_thickness_process_change_km_by_cell", cell_count, label
    )
    process_density = _numeric_array(
        step, "crust_density_process_change_by_cell", cell_count, label
    )
    total_age = _numeric_array(step, "crust_age_change_ma_by_cell", cell_count, label)
    total_thickness = _numeric_array(
        step, "crust_thickness_change_km_by_cell", cell_count, label
    )
    total_density = _numeric_array(
        step, "crust_density_change_by_cell", cell_count, label
    )
    crust_types = _integer_array(step, "crust_type_by_cell", cell_count, label)
    lithologies = _integer_array(step, "lithology_by_cell", cell_count, label)

    ages: list[float] = []
    thicknesses: list[float] = []
    densities: list[float] = []
    age_errors: list[float] = []
    thickness_errors: list[float] = []
    density_errors: list[float] = []
    maximum_link_residual = 0.0
    maximum_link_bound = 0.0
    for cell_id in range(cell_count):
        _require(
            0 <= crust_types[cell_id] < len(CRUST_NAMES),
            f"{label}.crust_type_by_cell[{cell_id}] is invalid",
        )
        _require(
            0 <= lithologies[cell_id] < len(LITHOLOGY_NAMES),
            f"{label}.lithology_by_cell[{cell_id}] is invalid",
        )
        _require(
            remapped_ages[cell_id] >= 0.0
            and remapped_thicknesses[cell_id] >= 0.0
            and remapped_densities[cell_id] > 0.0,
            f"{label} remapped crust state {cell_id} is invalid",
        )
        _require(
            remapped_thicknesses[cell_id] > 0.0
            or remapped_ages[cell_id] == 0.0,
            f"{label} zero-volume remapped crust state {cell_id} is not canonical",
        )
        age = remapped_ages[cell_id] + process_age[cell_id]
        thickness = remapped_thicknesses[cell_id] + process_thickness[cell_id]
        density = remapped_densities[cell_id] + process_density[cell_id]
        _require(
            math.isfinite(age)
            and math.isfinite(thickness)
            and math.isfinite(density)
            and age >= 0.0
            and thickness > 0.0
            and density > 0.0,
            f"{label} post-process crust state {cell_id} is invalid",
        )
        age_error = _reconstruction_bound(remapped_ages[cell_id], process_age[cell_id], age)
        thickness_error = _reconstruction_bound(
            remapped_thicknesses[cell_id], process_thickness[cell_id], thickness
        )
        density_error = _reconstruction_bound(
            remapped_densities[cell_id], process_density[cell_id], density
        )

        if previous is None:
            _require(
                total_age[cell_id] == 0.0
                and total_thickness[cell_id] == 0.0
                and total_density[cell_id] == 0.0
                and process_age[cell_id] == 0.0
                and process_thickness[cell_id] == 0.0
                and process_density[cell_id] == 0.0,
                f"{label} initial state changes must be exact zero",
            )
        else:
            for field_name, prior_value, prior_error, delta, current, current_error in (
                (
                    "age",
                    previous.ages_ma[cell_id],
                    previous.age_error_bounds_ma[cell_id],
                    total_age[cell_id],
                    age,
                    age_error,
                ),
                (
                    "thickness",
                    previous.thicknesses_km[cell_id],
                    previous.thickness_error_bounds_km[cell_id],
                    total_thickness[cell_id],
                    thickness,
                    thickness_error,
                ),
                (
                    "density",
                    previous.densities_g_cm3[cell_id],
                    previous.density_error_bounds_g_cm3[cell_id],
                    total_density[cell_id],
                    density,
                    density_error,
                ),
            ):
                linked = prior_value + delta
                link_bound = (
                    prior_error
                    + current_error
                    + _reconstruction_bound(prior_value, delta, linked)
                )
                residual = abs(linked - current)
                _require(
                    residual <= link_bound,
                    f"{label} {field_name} state {cell_id} does not link "
                    "to the prior post-process root",
                )
                maximum_link_residual = max(maximum_link_residual, residual)
                maximum_link_bound = max(maximum_link_bound, link_bound)

        ages.append(age)
        thicknesses.append(thickness)
        densities.append(density)
        age_errors.append(age_error)
        thickness_errors.append(thickness_error)
        density_errors.append(density_error)

    return (
        _CrustState(
            crust_types=crust_types,
            lithologies=lithologies,
            ages_ma=ages,
            thicknesses_km=thicknesses,
            densities_g_cm3=densities,
            age_error_bounds_ma=age_errors,
            thickness_error_bounds_km=thickness_errors,
            density_error_bounds_g_cm3=density_errors,
        ),
        maximum_link_residual,
        maximum_link_bound,
    )


def _predicate_options(state: _CrustState, cell_id: int) -> tuple[bool, ...]:
    crust_type = state.crust_types[cell_id]
    lithology = state.lithologies[cell_id]
    if crust_type == 0:
        return (True,)
    if crust_type == 2:
        return (lithology == 0,)
    if crust_type != 3:
        return (False,)

    age = state.ages_ma[cell_id]
    thickness = state.thicknesses_km[cell_id]
    density = state.densities_g_cm3[cell_id]
    age_error = state.age_error_bounds_ma[cell_id]
    thickness_error = state.thickness_error_bounds_km[cell_id]
    density_error = state.density_error_bounds_g_cm3[cell_id]
    true_possible = (
        age - age_error <= 320.0
        and thickness - thickness_error <= 18.0
        and density + density_error >= 2.84
    )
    definitely_true = (
        age + age_error <= 320.0
        and thickness + thickness_error <= 18.0
        and density - density_error >= 2.84
    )
    if definitely_true:
        return (True,)
    if not true_possible:
        return (False,)
    return (False, True)


def _expected_thermal_candidates(
    state: _CrustState,
    cell_id: int,
    *,
    required_oceanic_like: bool | None = None,
) -> list[tuple[float, float, bool]]:
    candidates: list[tuple[float, float, bool]] = []
    for oceanic_like in _predicate_options(state, cell_id):
        if (
            required_oceanic_like is not None
            and oceanic_like is not required_oceanic_like
        ):
            continue
        if not oceanic_like:
            candidates.append((0.0, 0.0, False))
            continue
        age = state.ages_ma[cell_id]
        age_error = state.age_error_bounds_ma[cell_id]
        subsidence, formula_bound = _relative_subsidence_and_bound(age)
        low_age = max(0.0, age - age_error)
        high_age = age + age_error
        low_value, low_bound = _relative_subsidence_and_bound(low_age)
        high_value, high_bound = _relative_subsidence_and_bound(high_age)
        propagation = max(abs(subsidence - low_value), abs(high_value - subsidence))
        candidates.append(
            (
                -subsidence,
                formula_bound + propagation + max(low_bound, high_bound),
                True,
            )
        )
    _require(candidates, "thermal predicate has no consistent candidate")
    return candidates


def _match_thermal(
    actual: float,
    state: _CrustState,
    cell_id: int,
    label: str,
    *,
    required_oceanic_like: bool | None = None,
) -> tuple[float, float, float, bool]:
    _require(actual <= 0.0, f"{label} must be nonpositive")
    candidates = _expected_thermal_candidates(
        state,
        cell_id,
        required_oceanic_like=required_oceanic_like,
    )
    ranked = sorted(
        (
            (abs(actual - expected), expected, bound, oceanic_like)
            for expected, bound, oceanic_like in candidates
        ),
        key=lambda item: item[0],
    )
    residual, expected, bound, oceanic_like = ranked[0]
    _require(residual <= bound, f"{label} does not replay from crust state and age-depth formula")
    return expected, residual, bound, oceanic_like


def _expected_isostatic_candidates(
    state: _CrustState, cell_id: int
) -> list[tuple[float, float, bool]]:
    candidates: list[tuple[float, float, bool]] = []
    for oceanic_like in _predicate_options(state, cell_id):
        if oceanic_like:
            candidates.append((-OCEANIC_RIDGE_REFERENCE_DEPTH_M, 0.0, True))
            continue
        thickness = state.thicknesses_km[cell_id]
        density = state.densities_g_cm3[cell_id]
        thickness_anomaly = thickness - CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM
        density_anomaly = density - CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3
        thickness_contribution = (
            CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM
            * thickness_anomaly
        )
        density_contribution = (
            CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3
            * density_anomaly
        )
        expected = (
            CONTINENTAL_ISOSTATIC_FREEBOARD_M
            + thickness_contribution
            - density_contribution
        )
        propagated_state_bound = (
            CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM
            * state.thickness_error_bounds_km[cell_id]
            + CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3
            * state.density_error_bounds_g_cm3[cell_id]
        )
        arithmetic_bound = _operation_bound(
            expected,
            expected,
            operands=(
                thickness,
                density,
                thickness_anomaly,
                density_anomaly,
                thickness_contribution,
                density_contribution,
                CONTINENTAL_ISOSTATIC_FREEBOARD_M,
            ),
            operation_count=6,
        )
        candidates.append(
            (expected, propagated_state_bound + arithmetic_bound, False)
        )
    return candidates


def _match_isostatic(
    actual: float,
    state: _CrustState,
    cell_id: int,
    label: str,
) -> tuple[float, float, float, bool]:
    candidates = _expected_isostatic_candidates(state, cell_id)
    ranked = sorted(
        (
            (abs(actual - expected), expected, bound, oceanic_like)
            for expected, bound, oceanic_like in candidates
        ),
        key=lambda item: item[0],
    )
    residual, expected, bound, oceanic_like = ranked[0]
    _require(
        residual <= bound,
        f"{label} does not replay from crust state and isostatic formula",
    )
    return expected, residual, bound, oceanic_like


def _expected_dynamic_relief_change(
    inputs: _EquilibriumInputs,
    *,
    crust_type: int,
    convergence: float,
    divergence: float,
    transform: float,
    previous_convergence: float,
    previous_divergence: float,
    previous_transform: float,
    actual: float,
) -> tuple[float, float]:
    volcanic_arc_addend = 2.5 if crust_type == 3 else 0.0
    activity_shape = (
        1.5 * divergence + 8.5 * convergence + volcanic_arc_addend
    )
    uplift_rate = (
        inputs.tectonic_uplift_scale
        * inputs.tectonic_activity
        * activity_shape
        * inputs.timestep_scale
    )
    boundary_change = (
        80.0 * (convergence - previous_convergence)
        + 55.0 * (divergence - previous_divergence)
        - 30.0 * (transform - previous_transform)
    )
    expected = (
        uplift_rate * TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION
        + boundary_change
    )
    bound = _operation_bound(
        actual,
        expected,
        operands=(
            inputs.tectonic_uplift_scale,
            inputs.tectonic_activity,
            inputs.timestep_scale,
            convergence,
            divergence,
            transform,
            previous_convergence,
            previous_divergence,
            previous_transform,
            activity_shape,
            uplift_rate,
            boundary_change,
            volcanic_arc_addend,
        ),
        operation_count=18,
    )
    return expected, bound


def validate_oceanic_age_depth(world: Any) -> dict[str, Any]:
    """Replay age-depth targets and their complete tectonic application."""

    failures: list[str] = []
    metrics: dict[str, Any] = {
        "independent_crust_transport_root_replay_passed": False,
        "kinematic_equilibrium_metadata_replayed": False,
        "analytical_checkpoint_count": 0,
        "cell_count": 0,
        "history_step_count": 0,
        "isostatic_checkpoint_value_count": 0,
        "thermal_checkpoint_value_count": 0,
        "tectonic_application_value_count": 0,
        "oceanic_like_checkpoint_value_count": 0,
        "non_oceanic_checkpoint_value_count": 0,
        "maximum_absolute_isostatic_formula_residual_m": 0.0,
        "maximum_isostatic_formula_binary64_bound_m": 0.0,
        "maximum_absolute_thermal_formula_residual_m": 0.0,
        "maximum_thermal_formula_binary64_bound_m": 0.0,
        "maximum_absolute_tendency_residual_m": 0.0,
        "maximum_tendency_binary64_bound_m": 0.0,
        "maximum_absolute_dynamic_relief_residual_m": 0.0,
        "maximum_dynamic_relief_binary64_bound_m": 0.0,
        "maximum_absolute_tectonic_application_residual_m": 0.0,
        "maximum_tectonic_application_binary64_bound_m": 0.0,
        "maximum_absolute_state_link_residual": 0.0,
        "maximum_state_link_binary64_bound": 0.0,
        "maximum_absolute_ordered_step_formula_residual_m": 0.0,
        "maximum_ordered_step_formula_binary64_bound_m": 0.0,
        "global_ordered_formula_residual_m": 0.0,
        "global_ordered_formula_binary64_bound_m": 0.0,
        "global_ordered_tendency_residual_m": 0.0,
        "global_ordered_tendency_binary64_bound_m": 0.0,
        "maximum_absolute_isostatic_telescoping_residual_m": 0.0,
        "maximum_isostatic_telescoping_binary64_bound_m": 0.0,
        "maximum_absolute_thermal_telescoping_residual_m": 0.0,
        "maximum_thermal_telescoping_binary64_bound_m": 0.0,
        "maximum_absolute_equilibrium_change_m": 0.0,
        "maximum_absolute_tectonic_elevation_change_m": 0.0,
        "equilibrium_change_exceeds_dynamic_clamp_cell_step_count": 0,
        "tectonic_change_exceeds_dynamic_clamp_cell_step_count": 0,
        "initial_isostatic_targets_replayed": False,
        "initial_thermal_checkpoint_replayed": False,
        "final_thermal_target_replayed": False,
        "isostatic_target_application_replayed": False,
        "dynamic_relief_clamp_replayed": False,
        "tectonic_elevation_change_composition_replayed": False,
        "authoritative_for_relative_thermal_subsidence_target_curve": False,
        "authoritative_for_realized_thermal_relief_component": False,
        "realized_thermal_relief_state_tracked": False,
        "thermal_relaxation_timescale_calibrated": False,
        "unapplied_thermal_tendency_residual_carried_forward": False,
        "unapplied_thermal_equilibrium_residual_zero_by_construction": False,
        "thermal_contribution_outside_bounded_dynamic_relief_clamp_resolved": False,
        "thermal_contribution_to_tectonic_elevation_change_replayed": False,
        "thermal_equilibrium_change_application_replayed": False,
        "absolute_basement_depth_calibrated": False,
        "physical_crust_creation_age_provenance": False,
        "ridge_age_distance_consistency": False,
        "thermal_structure_represented": False,
        "heat_flow_represented": False,
        "dynamic_topography_represented": False,
        "flexure_represented": False,
        "physical_dynamics_represented": False,
    }
    try:
        _require(isinstance(world, dict), "world must be an object")
        cells, history = _preflight(world)
        _validate_model(world.get("oceanic_age_depth_model"))
        equilibrium_inputs = _validate_kinematic_equilibrium_model(
            world.get("plate_kinematic_model")
        )
        metrics["kinematic_equilibrium_metadata_replayed"] = True
        checkpoint_residual, checkpoint_bound = _validate_analytical_checkpoints()
        metrics["analytical_checkpoint_count"] = len(ANALYTICAL_CHECKPOINTS_M)
        metrics["maximum_absolute_thermal_formula_residual_m"] = checkpoint_residual
        metrics["maximum_thermal_formula_binary64_bound_m"] = checkpoint_bound

        crust_replay = validate_crust_overlap_transport(world)
        _require(
            isinstance(crust_replay, dict) and crust_replay.get("passed") is True,
            "independent crust transport/process root replay did not pass",
        )
        metrics["independent_crust_transport_root_replay_passed"] = True

        cell_count = len(cells)
        metrics["cell_count"] = cell_count
        metrics["history_step_count"] = len(history)
        global_formula = _OrderedReplay()
        global_tendency = _OrderedReplay()
        cumulative_isostatic_change = [0.0] * cell_count
        cumulative_thermal_change = [0.0] * cell_count
        cumulative_absolute_isostatic_change = [0.0] * cell_count
        cumulative_absolute_thermal_change = [0.0] * cell_count
        cumulative_isostatic_change_rounding_bound = [0.0] * cell_count
        cumulative_thermal_change_rounding_bound = [0.0] * cell_count
        previous_state: _CrustState | None = None
        previous_post_isostatic: list[float] | None = None
        previous_post_thermal: list[float] | None = None
        previous_boundaries: tuple[list[float], list[float], list[float]] | None = None
        initial_post_isostatic: list[float] | None = None
        initial_post_thermal: list[float] | None = None
        final_state: _CrustState | None = None
        final_post_isostatic: list[float] | None = None
        final_post_thermal: list[float] | None = None

        for step_index, step in enumerate(history):
            label = f"plate_motion_history[{step_index}]"
            state, link_residual, link_bound = _build_post_process_state(
                step,
                step_index=step_index,
                cell_count=cell_count,
                previous=previous_state,
            )
            metrics["maximum_absolute_state_link_residual"] = max(
                metrics["maximum_absolute_state_link_residual"], link_residual
            )
            metrics["maximum_state_link_binary64_bound"] = max(
                metrics["maximum_state_link_binary64_bound"], link_bound
            )

            convergence = _numeric_array(
                step, "boundary_convergent_by_cell", cell_count, label
            )
            divergence = _numeric_array(
                step, "boundary_divergent_by_cell", cell_count, label
            )
            transform = _numeric_array(
                step, "boundary_transform_by_cell", cell_count, label
            )
            _require(
                all(
                    0.0 <= value <= 1.0
                    for value in convergence + divergence + transform
                ),
                f"{label} boundary inputs must lie in [0,1]",
            )
            previous_isostatic = _numeric_array(
                step, "previous_local_isostatic_equilibrium_m", cell_count, label
            )
            post_isostatic = _numeric_array(
                step, "post_process_local_isostatic_equilibrium_m", cell_count, label
            )
            isostatic_change = _numeric_array(
                step, "isostatic_equilibrium_change_m", cell_count, label
            )
            previous_thermal = _numeric_array(
                step, "previous_local_thermal_subsidence_target_m", cell_count, label
            )
            post_thermal = _numeric_array(
                step, "post_process_local_thermal_subsidence_target_m", cell_count, label
            )
            thermal_change = _numeric_array(
                step, "thermal_equilibrium_change_m", cell_count, label
            )
            unbounded_dynamic = _numeric_array(
                step, "unbounded_dynamic_relief_change_m", cell_count, label
            )
            bounded_dynamic = _numeric_array(
                step, "bounded_dynamic_relief_change_m", cell_count, label
            )
            tectonic_change = _numeric_array(
                step, "tectonic_elevation_change_m_by_cell", cell_count, label
            )

            if step_index == 0:
                _require(
                    previous_isostatic == post_isostatic
                    and previous_thermal == post_thermal
                    and all(
                        value == 0.0
                        for column in (
                            isostatic_change,
                            thermal_change,
                            unbounded_dynamic,
                            bounded_dynamic,
                            tectonic_change,
                        )
                        for value in column
                    ),
                    "initial equilibrium checkpoint must have equal targets and "
                    "exact-zero changes",
                )
                previous_formula_state = state
                initial_post_isostatic = post_isostatic
                initial_post_thermal = post_thermal
            else:
                assert previous_state is not None
                assert previous_post_isostatic is not None
                assert previous_post_thermal is not None
                _require(
                    previous_isostatic == previous_post_isostatic,
                    f"{label}.previous_local_isostatic_equilibrium_m is not "
                    "the prior round-trip checkpoint",
                )
                _require(
                    previous_thermal == previous_post_thermal,
                    f"{label}.previous_local_thermal_subsidence_target_m is "
                    "not the prior round-trip checkpoint",
                )
                previous_formula_state = previous_state

            step_formula = _OrderedReplay()
            for cell_id in range(cell_count):
                (
                    _,
                    previous_isostatic_residual,
                    previous_isostatic_bound,
                    previous_oceanic,
                ) = _match_isostatic(
                    previous_isostatic[cell_id],
                    previous_formula_state,
                    cell_id,
                    f"{label}.previous_local_isostatic_equilibrium_m[{cell_id}]",
                )
                (
                    _,
                    post_isostatic_residual,
                    post_isostatic_bound,
                    post_oceanic,
                ) = _match_isostatic(
                    post_isostatic[cell_id],
                    state,
                    cell_id,
                    f"{label}.post_process_local_isostatic_equilibrium_m[{cell_id}]",
                )
                (
                    _,
                    previous_thermal_residual,
                    previous_thermal_bound,
                    _,
                ) = _match_thermal(
                    previous_thermal[cell_id],
                    previous_formula_state,
                    cell_id,
                    f"{label}.previous_local_thermal_subsidence_target_m[{cell_id}]",
                    required_oceanic_like=previous_oceanic,
                )
                (
                    post_thermal_expected,
                    post_thermal_residual,
                    post_thermal_bound,
                    _,
                ) = _match_thermal(
                    post_thermal[cell_id],
                    state,
                    cell_id,
                    f"{label}.post_process_local_thermal_subsidence_target_m[{cell_id}]",
                    required_oceanic_like=post_oceanic,
                )
                metrics["maximum_absolute_isostatic_formula_residual_m"] = max(
                    metrics["maximum_absolute_isostatic_formula_residual_m"],
                    previous_isostatic_residual,
                    post_isostatic_residual,
                )
                metrics["maximum_isostatic_formula_binary64_bound_m"] = max(
                    metrics["maximum_isostatic_formula_binary64_bound_m"],
                    previous_isostatic_bound,
                    post_isostatic_bound,
                )
                metrics["maximum_absolute_thermal_formula_residual_m"] = max(
                    metrics["maximum_absolute_thermal_formula_residual_m"],
                    previous_thermal_residual,
                    post_thermal_residual,
                )
                metrics["maximum_thermal_formula_binary64_bound_m"] = max(
                    metrics["maximum_thermal_formula_binary64_bound_m"],
                    previous_thermal_bound,
                    post_thermal_bound,
                )
                metrics["isostatic_checkpoint_value_count"] += 2
                metrics["thermal_checkpoint_value_count"] += 2
                metrics["oceanic_like_checkpoint_value_count"] += int(
                    previous_oceanic
                ) + int(post_oceanic)
                metrics["non_oceanic_checkpoint_value_count"] += int(
                    not previous_oceanic
                ) + int(not post_oceanic)

                expected_isostatic_change = ISOSTATIC_TARGET_DIFFERENCE_GAIN * (
                    post_isostatic[cell_id] - previous_isostatic[cell_id]
                )
                isostatic_change_bound = _target_change_operation_bound(
                    isostatic_change[cell_id],
                    previous_isostatic[cell_id],
                    post_isostatic[cell_id],
                    expected_isostatic_change,
                    ISOSTATIC_TARGET_DIFFERENCE_GAIN,
                )
                isostatic_change_residual = abs(
                    isostatic_change[cell_id] - expected_isostatic_change
                )
                _require(
                    isostatic_change_residual <= isostatic_change_bound,
                    f"{label}.isostatic_equilibrium_change_m[{cell_id}] does not replay",
                )

                expected_thermal_change = THERMAL_TARGET_DIFFERENCE_GAIN * (
                    post_thermal[cell_id] - previous_thermal[cell_id]
                )
                thermal_change_bound = _target_change_operation_bound(
                    thermal_change[cell_id],
                    previous_thermal[cell_id],
                    post_thermal[cell_id],
                    expected_thermal_change,
                    THERMAL_TARGET_DIFFERENCE_GAIN,
                )
                thermal_change_residual = abs(
                    thermal_change[cell_id] - expected_thermal_change
                )
                _require(
                    thermal_change_residual <= thermal_change_bound,
                    f"{label}.thermal_equilibrium_change_m[{cell_id}] does not replay",
                )
                metrics["maximum_absolute_tendency_residual_m"] = max(
                    metrics["maximum_absolute_tendency_residual_m"],
                    isostatic_change_residual,
                    thermal_change_residual,
                )
                metrics["maximum_tendency_binary64_bound_m"] = max(
                    metrics["maximum_tendency_binary64_bound_m"],
                    isostatic_change_bound,
                    thermal_change_bound,
                )

                if step_index == 0:
                    expected_dynamic = 0.0
                    dynamic_bound = 0.0
                else:
                    assert previous_boundaries is not None
                    expected_dynamic, dynamic_bound = _expected_dynamic_relief_change(
                        equilibrium_inputs,
                        crust_type=state.crust_types[cell_id],
                        convergence=convergence[cell_id],
                        divergence=divergence[cell_id],
                        transform=transform[cell_id],
                        previous_convergence=previous_boundaries[0][cell_id],
                        previous_divergence=previous_boundaries[1][cell_id],
                        previous_transform=previous_boundaries[2][cell_id],
                        actual=unbounded_dynamic[cell_id],
                    )
                dynamic_residual = abs(
                    unbounded_dynamic[cell_id] - expected_dynamic
                )
                _require(
                    dynamic_residual <= dynamic_bound,
                    f"{label}.unbounded_dynamic_relief_change_m[{cell_id}] does not replay",
                )
                metrics["maximum_absolute_dynamic_relief_residual_m"] = max(
                    metrics["maximum_absolute_dynamic_relief_residual_m"],
                    dynamic_residual,
                )
                metrics["maximum_dynamic_relief_binary64_bound_m"] = max(
                    metrics["maximum_dynamic_relief_binary64_bound_m"],
                    dynamic_bound,
                )
                expected_bounded_dynamic = min(
                    DYNAMIC_RELIEF_MAXIMUM_CHANGE_M,
                    max(DYNAMIC_RELIEF_MINIMUM_CHANGE_M, unbounded_dynamic[cell_id]),
                )
                _require(
                    bounded_dynamic[cell_id] == expected_bounded_dynamic,
                    f"{label}.bounded_dynamic_relief_change_m[{cell_id}] does not replay",
                )

                equilibrium_change = (
                    isostatic_change[cell_id] + thermal_change[cell_id]
                )
                expected_tectonic_change = (
                    equilibrium_change + bounded_dynamic[cell_id]
                )
                application_bound = _operation_bound(
                    tectonic_change[cell_id],
                    expected_tectonic_change,
                    operands=(
                        isostatic_change[cell_id],
                        thermal_change[cell_id],
                        bounded_dynamic[cell_id],
                        equilibrium_change,
                    ),
                    operation_count=2,
                )
                application_residual = abs(
                    tectonic_change[cell_id] - expected_tectonic_change
                )
                _require(
                    application_residual <= application_bound,
                    f"{label}.tectonic_elevation_change_m_by_cell[{cell_id}] "
                    "does not replay",
                )
                metrics["maximum_absolute_tectonic_application_residual_m"] = max(
                    metrics["maximum_absolute_tectonic_application_residual_m"],
                    application_residual,
                )
                metrics["maximum_tectonic_application_binary64_bound_m"] = max(
                    metrics["maximum_tectonic_application_binary64_bound_m"],
                    application_bound,
                )
                metrics["maximum_absolute_equilibrium_change_m"] = max(
                    metrics["maximum_absolute_equilibrium_change_m"],
                    abs(equilibrium_change),
                )
                metrics["maximum_absolute_tectonic_elevation_change_m"] = max(
                    metrics["maximum_absolute_tectonic_elevation_change_m"],
                    abs(tectonic_change[cell_id]),
                )
                metrics[
                    "equilibrium_change_exceeds_dynamic_clamp_cell_step_count"
                ] += int(abs(equilibrium_change) > DYNAMIC_RELIEF_MAXIMUM_CHANGE_M)
                metrics[
                    "tectonic_change_exceeds_dynamic_clamp_cell_step_count"
                ] += int(
                    tectonic_change[cell_id] < DYNAMIC_RELIEF_MINIMUM_CHANGE_M
                    or tectonic_change[cell_id] > DYNAMIC_RELIEF_MAXIMUM_CHANGE_M
                )
                metrics["tectonic_application_value_count"] += 1
                cumulative_isostatic_change[cell_id] += isostatic_change[cell_id]
                cumulative_thermal_change[cell_id] += thermal_change[cell_id]
                cumulative_absolute_isostatic_change[cell_id] += abs(
                    isostatic_change[cell_id]
                )
                cumulative_absolute_thermal_change[cell_id] += abs(
                    thermal_change[cell_id]
                )
                cumulative_isostatic_change_rounding_bound[cell_id] += (
                    isostatic_change_bound
                )
                cumulative_thermal_change_rounding_bound[cell_id] += (
                    thermal_change_bound
                )
                step_formula.add(
                    post_thermal[cell_id],
                    post_thermal_expected,
                    post_thermal_bound,
                )
                global_formula.add(
                    post_thermal[cell_id],
                    post_thermal_expected,
                    post_thermal_bound,
                )
                global_tendency.add(
                    thermal_change[cell_id],
                    expected_thermal_change,
                    thermal_change_bound,
                )

            step_residual, step_bound = step_formula.residual_and_bound()
            _require(
                step_residual <= step_bound,
                f"{label} ordered thermal formula reduction exceeds its binary64 bound",
            )
            metrics["maximum_absolute_ordered_step_formula_residual_m"] = max(
                metrics["maximum_absolute_ordered_step_formula_residual_m"],
                step_residual,
            )
            metrics["maximum_ordered_step_formula_binary64_bound_m"] = max(
                metrics["maximum_ordered_step_formula_binary64_bound_m"], step_bound
            )
            previous_state = state
            previous_post_isostatic = post_isostatic
            previous_post_thermal = post_thermal
            previous_boundaries = (convergence, divergence, transform)
            final_state = state
            final_post_isostatic = post_isostatic
            final_post_thermal = post_thermal

        assert initial_post_isostatic is not None
        assert initial_post_thermal is not None
        assert final_state is not None
        assert final_post_isostatic is not None
        assert final_post_thermal is not None
        for cell_id, cell in enumerate(cells):
            _require(
                _integer(cell.get("id"), f"cells[{cell_id}].id") == cell_id,
                f"cells[{cell_id}].id is not canonical",
            )
            final_alias = _finite(
                cell.get("thermal_subsidence_target_m"),
                f"cells[{cell_id}].thermal_subsidence_target_m",
            )
            _require(
                final_alias == final_post_thermal[cell_id],
                f"cells[{cell_id}].thermal_subsidence_target_m does not "
                "match the final round-trip checkpoint",
            )
            _require(
                cell.get("crust_type") == CRUST_NAMES[final_state.crust_types[cell_id]]
                and cell.get("lithology")
                == LITHOLOGY_NAMES[final_state.lithologies[cell_id]],
                f"cells[{cell_id}] final categorical crust state does not match the formula root",
            )

            expected_isostatic_total = (
                final_post_isostatic[cell_id] - initial_post_isostatic[cell_id]
            )
            isostatic_telescope_bound = _telescoping_operation_bound(
                cumulative_isostatic_change[cell_id],
                expected_isostatic_total,
                absolute_change_sum=cumulative_absolute_isostatic_change[cell_id],
                change_rounding_bound_sum=(
                    cumulative_isostatic_change_rounding_bound[cell_id]
                ),
                addition_count=len(history),
            )
            isostatic_telescope_residual = abs(
                cumulative_isostatic_change[cell_id] - expected_isostatic_total
            )
            _require(
                isostatic_telescope_residual <= isostatic_telescope_bound,
                f"cell {cell_id} isostatic equilibrium changes do not telescope",
            )
            metrics["maximum_absolute_isostatic_telescoping_residual_m"] = max(
                metrics["maximum_absolute_isostatic_telescoping_residual_m"],
                isostatic_telescope_residual,
            )
            metrics["maximum_isostatic_telescoping_binary64_bound_m"] = max(
                metrics["maximum_isostatic_telescoping_binary64_bound_m"],
                isostatic_telescope_bound,
            )

            expected_thermal_total = (
                final_post_thermal[cell_id] - initial_post_thermal[cell_id]
            )
            thermal_telescope_bound = _telescoping_operation_bound(
                cumulative_thermal_change[cell_id],
                expected_thermal_total,
                absolute_change_sum=cumulative_absolute_thermal_change[cell_id],
                change_rounding_bound_sum=(
                    cumulative_thermal_change_rounding_bound[cell_id]
                ),
                addition_count=len(history),
            )
            thermal_telescope_residual = abs(
                cumulative_thermal_change[cell_id] - expected_thermal_total
            )
            _require(
                thermal_telescope_residual <= thermal_telescope_bound,
                f"cell {cell_id} thermal equilibrium changes do not telescope",
            )
            metrics["maximum_absolute_thermal_telescoping_residual_m"] = max(
                metrics["maximum_absolute_thermal_telescoping_residual_m"],
                thermal_telescope_residual,
            )
            metrics["maximum_thermal_telescoping_binary64_bound_m"] = max(
                metrics["maximum_thermal_telescoping_binary64_bound_m"],
                thermal_telescope_bound,
            )

        metrics["initial_isostatic_targets_replayed"] = True
        metrics["initial_thermal_checkpoint_replayed"] = True
        metrics["final_thermal_target_replayed"] = True
        metrics["isostatic_target_application_replayed"] = True
        metrics["dynamic_relief_clamp_replayed"] = True
        metrics["tectonic_elevation_change_composition_replayed"] = True

        global_formula_residual, global_formula_bound = global_formula.residual_and_bound()
        global_tendency_residual, global_tendency_bound = global_tendency.residual_and_bound()
        _require(
            global_formula_residual <= global_formula_bound,
            "global ordered thermal formula reduction exceeds its binary64 bound",
        )
        _require(
            global_tendency_residual <= global_tendency_bound,
            "global ordered thermal tendency reduction exceeds its binary64 bound",
        )
        metrics["global_ordered_formula_residual_m"] = global_formula_residual
        metrics["global_ordered_formula_binary64_bound_m"] = global_formula_bound
        metrics["global_ordered_tendency_residual_m"] = global_tendency_residual
        metrics["global_ordered_tendency_binary64_bound_m"] = global_tendency_bound

        for field in (
            "authoritative_for_relative_thermal_subsidence_target_curve",
            "authoritative_for_realized_thermal_relief_component",
            "realized_thermal_relief_state_tracked",
            "thermal_relaxation_timescale_calibrated",
            "unapplied_thermal_tendency_residual_carried_forward",
            "unapplied_thermal_equilibrium_residual_zero_by_construction",
            "thermal_contribution_outside_bounded_dynamic_relief_clamp_resolved",
            "thermal_contribution_to_tectonic_elevation_change_replayed",
            "thermal_equilibrium_change_application_replayed",
            "absolute_basement_depth_calibrated",
            "physical_crust_creation_age_provenance",
            "ridge_age_distance_consistency",
            "thermal_structure_represented",
            "heat_flow_represented",
            "dynamic_topography_represented",
            "flexure_represented",
            "physical_dynamics_represented",
        ):
            metrics[field] = world["oceanic_age_depth_model"][field]
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        failures.append(str(exc))

    return {"passed": not failures, "failures": failures, "metrics": metrics}


__all__ = [
    "ANALYTICAL_CHECKPOINTS_M",
    "KINEMATIC_EQUILIBRIUM_LITERAL_VALUES",
    "MODEL",
    "MODEL_LITERAL_VALUES",
    "is_oceanic_like_crust_state",
    "oceanic_relative_basement_subsidence_m",
    "validate_oceanic_age_depth",
]
