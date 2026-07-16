#include "internal.hpp"
#include "../opencl_compute.hpp"

namespace magic_geo::detail {

Vec3 random_unit_vector(std::mt19937_64& rng) {
    std::uniform_real_distribution<double> uni(0.0, 1.0);
    const double z = 2.0 * uni(rng) - 1.0;
    const double a = 2.0 * PI * uni(rng);
    const double r = std::sqrt(std::max(0.0, 1.0 - z * z));
    return {std::cos(a) * r, std::sin(a) * r, z};
}

std::vector<Plate> generate_plates(const Params& params) {
    std::mt19937_64 rng(params.seed ^ 0xC0FFEEULL);
    std::uniform_real_distribution<double> uni(0.0, 1.0);
    std::vector<Plate> plates;
    plates.reserve(static_cast<std::size_t>(params.plate_count));
    const double tectonic_activity = clamp(params.internal_heat * std::sqrt(4.5 / std::max(0.05, params.geological_age_ga)), 0.25, 2.25);
    for (int i = 0; i < params.plate_count; ++i) {
        const double draw = uni(rng);
        int kind = 0;
        if (draw < params.continental_plate_fraction) {
            kind = 1;
        } else if (draw < params.continental_plate_fraction + 0.22) {
            kind = 2;
        }
        Plate plate;
        plate.id = i;
        plate.axis = random_unit_vector(rng);
        plate.angular_speed = (params.min_angular_speed +
            (params.max_angular_speed - params.min_angular_speed) * uni(rng)) * tectonic_activity;
        plate.kind = kind;
        plate.crust_density = kind == 0 ? 3.0 : (kind == 1 ? 2.72 : 2.84);
        plate.crust_thickness_km = kind == 0 ? 7.0 : (kind == 1 ? 34.0 : 22.0);
        plates.push_back(plate);
    }
    return plates;
}

std::vector<int> choose_plate_seeds(const Params& params, int cell_count) {
    std::mt19937_64 rng(params.seed ^ 0xBAD5EEDULL);
    std::uniform_int_distribution<int> pick(0, cell_count - 1);
    std::unordered_set<int> used;
    std::vector<int> seeds;
    while (static_cast<int>(seeds.size()) < params.plate_count) {
        const int candidate = pick(rng);
        if (used.insert(candidate).second) {
            seeds.push_back(candidate);
        }
    }
    return seeds;
}

void assign_plates(const std::vector<Vec3>& centers, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    std::vector<int> accelerated_plate_ids;
    if (try_accelerated_assign_plates(centers, cells, accelerated_plate_ids)) {
        if (accelerated_plate_ids.size() != cells.size()) {
            throw std::runtime_error("accelerated plate assignment result size mismatch");
        }
        for (int i = 0; i < n; ++i) {
            cells[static_cast<std::size_t>(i)].plate_id =
                accelerated_plate_ids[static_cast<std::size_t>(i)];
        }
    } else {
#pragma omp parallel for schedule(static)
        for (int i = 0; i < n; ++i) {
            double best = -2.0;
            int best_plate = 0;
            for (int p = 0; p < static_cast<int>(centers.size()); ++p) {
                const double score = dot(cells[i].p, centers[static_cast<std::size_t>(p)]);
                if (score > best) {
                    best = score;
                    best_plate = p;
                }
            }
            cells[i].plate_id = best_plate;
        }
    }
    std::vector<int> assigned_counts(centers.size(), 0);
    for (const Cell& cell : cells) {
        assigned_counts[static_cast<std::size_t>(cell.plate_id)]++;
    }
    for (std::size_t plate_id = 0; plate_id < assigned_counts.size(); ++plate_id) {
        if (assigned_counts[plate_id] == 0) {
            throw std::runtime_error(
                "nearest-center plate domain became empty; increase mesh.cell_count or reduce "
                "tectonics.plate_count/plate motion"
            );
        }
    }
}

Vec3 plate_velocity(const Plate& plate, Vec3 pos) {
    return cross(mul(plate.axis, plate.angular_speed), pos);
}

std::vector<double> smooth_field(const std::vector<Cell>& cells, const std::vector<double>& input, int steps, double self_weight) {
    if (steps <= 0) {
        return input;
    }
    std::vector<double> accelerated_output;
    if (try_accelerated_smooth_field(
            cells, input, steps, self_weight, accelerated_output
        )) {
        return accelerated_output;
    }
    std::vector<double> current = input;
    std::vector<double> next(input.size(), 0.0);
    for (int step = 0; step < steps; ++step) {
#pragma omp parallel for schedule(static)
        for (int i = 0; i < static_cast<int>(cells.size()); ++i) {
            double sum = 0.0;
            for (int j : cells[i].neighbors) {
                sum += current[j];
            }
            const double avg = cells[i].neighbors.empty() ? current[i] : sum / static_cast<double>(cells[i].neighbors.size());
            next[i] = self_weight * current[i] + (1.0 - self_weight) * avg;
        }
        current.swap(next);
    }
    return current;
}

void classify_boundaries(const Params& params, const std::vector<Plate>& plates, std::vector<Cell>& cells) {
    const int n = static_cast<int>(cells.size());
    std::vector<double> conv(n, 0.0), div(n, 0.0), trans(n, 0.0);
    for (int i = 0; i < n; ++i) {
        for (int j : cells[i].neighbors) {
            if (j <= i || cells[i].plate_id == cells[j].plate_id) {
                continue;
            }
            const Plate& a = plates[cells[i].plate_id];
            const Plate& b = plates[cells[j].plate_id];
            const Vec3 mid = normalize(add(cells[i].p, cells[j].p));
            const Vec3 delta = sub(cells[j].p, cells[i].p);
            const Vec3 across = normalize(sub(delta, mul(mid, dot(delta, mid))));
            const Vec3 tangent = normalize(cross(mid, across));
            const Vec3 vrel = sub(plate_velocity(b, mid), plate_velocity(a, mid));
            const double separation = dot(vrel, across);
            const double shear = std::abs(dot(vrel, tangent));
            const double c = clamp(-separation * 1.25, 0.0, 1.0);
            const double d = clamp(separation * 1.25, 0.0, 1.0);
            const double t = clamp((shear - std::abs(separation) * 0.35) * 1.05, 0.0, 1.0);
            conv[i] += c;
            conv[j] += c;
            div[i] += d;
            div[j] += d;
            trans[i] += t;
            trans[j] += t;
        }
    }
    for (int i = 0; i < n; ++i) {
        const double degree = std::max(1.0, static_cast<double>(cells[i].neighbors.size()));
        conv[i] = clamp(conv[i] / degree * 3.2, 0.0, 1.0);
        div[i] = clamp(div[i] / degree * 3.2, 0.0, 1.0);
        trans[i] = clamp(trans[i] / degree * 3.2, 0.0, 1.0);
    }
    std::vector<double> smoothed_conv;
    std::vector<double> smoothed_div;
    std::vector<double> smoothed_trans;
    if (try_accelerated_smooth_three_fields(
            cells,
            conv,
            div,
            trans,
            params.boundary_smoothing_steps,
            0.58,
            0.58,
            0.62,
            smoothed_conv,
            smoothed_div,
            smoothed_trans
        )) {
        conv = std::move(smoothed_conv);
        div = std::move(smoothed_div);
        trans = std::move(smoothed_trans);
    } else {
        conv = smooth_field(cells, conv, params.boundary_smoothing_steps, 0.58);
        div = smooth_field(cells, div, params.boundary_smoothing_steps, 0.58);
        trans = smooth_field(cells, trans, params.boundary_smoothing_steps, 0.62);
    }
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        cells[i].boundary_convergent = clamp(conv[i], 0.0, 1.0);
        cells[i].boundary_divergent = clamp(div[i], 0.0, 1.0);
        cells[i].boundary_transform = clamp(trans[i], 0.0, 1.0);
        const double m = std::max(cells[i].boundary_convergent, std::max(cells[i].boundary_divergent, cells[i].boundary_transform));
        if (m < 0.08) {
            cells[i].boundary_type = 0;
        } else if (cells[i].boundary_convergent == m && cells[i].boundary_divergent > 0.45 * m) {
            cells[i].boundary_type = 4;
        } else if (cells[i].boundary_convergent == m) {
            cells[i].boundary_type = 1;
        } else if (cells[i].boundary_divergent == m) {
            cells[i].boundary_type = 2;
        } else {
            cells[i].boundary_type = 3;
        }
    }
}

double lithology_resistance(int lithology) {
    switch (lithology) {
        case 0: return 0.85;
        case 1: return 1.25;
        case 2: return 0.75;
        case 3: return 0.82;
        case 4: return 0.62;
        case 5: return 0.95;
        case 6: return 1.35;
        default: return 1.0;
    }
}

namespace {

struct InitialCrustCategoryState {
    int crust_type = 0;
    int lithology = 0;
    double thickness_km = 0.0;
    double density_g_cm3 = 0.0;
};

InitialCrustCategoryState initial_crust_category_state(
    const Plate& plate,
    bool continental,
    bool continental_margin,
    double convergent,
    double divergent,
    double category_noise,
    double numeric_noise
) {
    InitialCrustCategoryState state;
    if (continental) {
        if (convergent > 0.40) {
            state.crust_type = 5;
            state.lithology = 6;
        } else if (divergent > 0.36) {
            state.crust_type = 6;
            state.lithology = 3;
        } else if (
            category_noise > 0.55 &&
            convergent < 0.16 &&
            divergent < 0.14
        ) {
            state.crust_type = 4;
            state.lithology = 1;
        } else if (category_noise < -0.45) {
            state.crust_type = 7;
            state.lithology = numeric_noise > 0.0 ? 2 : 4;
        } else {
            state.crust_type = 1;
            state.lithology = numeric_noise > 0.35 ? 1 : 3;
        }
        state.thickness_km = clamp(
            29.0 + 17.0 * convergent - 8.0 * divergent +
                5.0 * numeric_noise,
            18.0,
            72.0
        );
        return state;
    }

    if (convergent > 0.35 && plate.kind != 0) {
        state.crust_type = 3;
        state.lithology = 5;
    } else if (continental_margin) {
        state.crust_type = 2;
        state.lithology = 0;
    } else {
        state.crust_type = 0;
        state.lithology = 0;
    }
    state.thickness_km = clamp(
        6.5 + 3.0 * convergent + 1.5 * numeric_noise,
        4.5,
        14.0
    );
    state.density_g_cm3 = 3.00;
    return state;
}

}  // namespace

void derive_crust_and_topography(
    const Params& params,
    const std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    InitialOceanicCrustAgeDiagnostics* initial_oceanic_crust_age
) {
    const int n = static_cast<int>(cells.size());
    const double relief_scale = clamp(1.0 / std::sqrt(std::max(0.08, params.gravity_g)), 0.55, 1.60);
    const double tectonic_activity = clamp(params.internal_heat * std::sqrt(4.5 / std::max(0.05, params.geological_age_ga)), 0.25, 2.25);
    std::vector<double> continental_noise(static_cast<std::size_t>(n), 0.0);
    std::vector<double> relief_noise(static_cast<std::size_t>(n), 0.0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        continental_noise[static_cast<std::size_t>(i)] = signed_noise(
            params.seed, static_cast<std::uint64_t>(i), 17
        );
        relief_noise[static_cast<std::size_t>(i)] = signed_noise(
            params.seed, static_cast<std::uint64_t>(i), 31
        );
    }
    continental_noise = smooth_field(
        cells,
        continental_noise,
        INITIAL_CRUST_COHERENCE_SMOOTHING_STEPS,
        INITIAL_CRUST_COHERENCE_SELF_WEIGHT
    );
    relief_noise = smooth_field(
        cells,
        relief_noise,
        SECONDARY_RELIEF_SMOOTHING_STEPS,
        SECONDARY_RELIEF_SELF_WEIGHT
    );
    std::vector<double> continental_score(static_cast<std::size_t>(n), 0.0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        const Plate& plate = plates[static_cast<std::size_t>(cell.plate_id)];
        const double wave = 0.12 * std::sin(3.0 * cell.lon + 1.7 * std::sin(cell.lat * 2.0));
        const double plate_bias = plate.kind == 1 ? 0.72 : (plate.kind == 2 ? 0.48 : 0.17);
        continental_score[static_cast<std::size_t>(i)] = plate_bias +
            0.20 * continental_noise[static_cast<std::size_t>(i)] + wave +
            0.14 * cell.boundary_convergent;
    }
    std::vector<int> continental_rank(static_cast<std::size_t>(n), 0);
    std::iota(continental_rank.begin(), continental_rank.end(), 0);
    std::stable_sort(
        continental_rank.begin(),
        continental_rank.end(),
        [&continental_score](int a, int b) {
            const double score_a = continental_score[static_cast<std::size_t>(a)];
            const double score_b = continental_score[static_cast<std::size_t>(b)];
            return score_a == score_b ? a < b : score_a > score_b;
        }
    );
    const int continental_target_count = std::clamp(
        static_cast<int>(std::llround(params.continental_crust_fraction_target * static_cast<double>(n))),
        0,
        n
    );
    std::vector<int> continental_mask(static_cast<std::size_t>(n), 0);
    for (int rank = 0; rank < continental_target_count; ++rank) {
        const int cell_id = continental_rank[static_cast<std::size_t>(rank)];
        continental_mask[static_cast<std::size_t>(cell_id)] = 1;
    }
    std::vector<int> continental_margin(static_cast<std::size_t>(n), 0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        if (continental_mask[static_cast<std::size_t>(i)] != 0) {
            continue;
        }
        for (int neighbor_id : cells[static_cast<std::size_t>(i)].neighbors) {
            if (continental_mask[static_cast<std::size_t>(neighbor_id)] != 0) {
                continental_margin[static_cast<std::size_t>(i)] = 1;
                break;
            }
        }
    }
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[static_cast<std::size_t>(i)];
        const Plate& plate = plates[static_cast<std::size_t>(cell.plate_id)];
        const double category_noise = signed_noise(
            params.seed,
            static_cast<std::uint64_t>(i),
            23
        );
        const double numeric_noise = signed_noise(
            params.seed,
            static_cast<std::uint64_t>(i),
            31
        );
        const InitialCrustCategoryState state =
            initial_crust_category_state(
                plate,
                continental_mask[static_cast<std::size_t>(i)] != 0,
                continental_margin[static_cast<std::size_t>(i)] != 0,
                cell.boundary_convergent,
                cell.boundary_divergent,
                category_noise,
                numeric_noise
            );
        cell.crust_type = state.crust_type;
        cell.lithology = state.lithology;
        // The exact boundary geometry and oceanic predicate need a complete
        // provisional state before the ridge-distance age field is built.
        cell.crust_age_ma = 0.0;
        cell.crust_thickness_km = state.thickness_km;
        cell.crust_density = state.density_g_cm3 > 0.0
            ? state.density_g_cm3
            : 2.70 + 0.08 * hash01(params.seed, i, 43);
    }
    const CrustTransportPlan provisional_identity_transport =
        build_identity_crust_transport_plan(cells);
    int provisional_reciprocal_mesh_segment_count = 0;
    const std::vector<PlateBoundarySegment> provisional_boundary_segments =
        build_plate_boundary_segments(
            params,
            cells,
            plates,
            provisional_identity_transport,
            &provisional_reciprocal_mesh_segment_count
        );
    const std::vector<double> initial_oceanic_crust_age_ma =
        build_initial_oceanic_crust_age_field(
            params,
            cells,
            provisional_boundary_segments,
            initial_oceanic_crust_age
        );
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[i];
        const double n0 = continental_noise[static_cast<std::size_t>(i)];
        const double coherent_n2 = relief_noise[static_cast<std::size_t>(i)];
        const bool continental = continental_mask[static_cast<std::size_t>(i)] != 0;
        const double conv = cell.boundary_convergent;
        const double div = cell.boundary_divergent;
        const double trans = cell.boundary_transform;
        const bool oceanic = cell.crust_type == 0 || cell.crust_type == 2 || cell.crust_type == 3;
        const double initial_age_ceiling_ma = crust_age_ceiling_ma(
            params, 4200.0
        );
        cell.crust_age_ma = oceanic
            ? initial_oceanic_crust_age_ma[static_cast<std::size_t>(i)]
            : clamp(
                450.0 + 900.0 * params.geological_age_ga * hash01(params.seed, i, 41),
                std::min(120.0, initial_age_ceiling_ma),
                initial_age_ceiling_ma
            );
        const double isostatic = oceanic
            ? -OCEANIC_RIDGE_REFERENCE_DEPTH_M
            : CONTINENTAL_ISOSTATIC_FREEBOARD_M +
                CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM * (
                    cell.crust_thickness_km -
                    CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM
                ) -
                CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3 * (
                    cell.crust_density -
                    CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3
                );
        const bool oceanic_like = is_oceanic_crust_state(
            cell.crust_type,
            cell.lithology,
            cell.crust_age_ma,
            cell.crust_thickness_km,
            cell.crust_density
        );
        const double thermal = oceanic_age_depth_thermal_subsidence_m(
            cell.crust_age_ma,
            oceanic_like
        );
        // The published age-depth relation already includes the elevated
        // zero-age ridge intercept.  Adding a second oceanic ridge uplift
        // would double-count that bathymetry; the continental divergent term
        // remains a separate broad rift-shoulder proxy.
        const double ridge = div * (oceanic ? 0.0 : 880.0) * relief_scale;
        const double rift = div * (oceanic ? 0.0 : -820.0) * relief_scale;
        const double convergence_squared = conv * conv;
        const double orogen = (
            continental
                ? convergence_squared * CONTINENTAL_OROGEN_UPLIFT_SCALE_M
                : conv * 1350.0
        ) * relief_scale;
        const double oceanic_trench_scale = cell.crust_type == 3
            ? VOLCANIC_ARC_TRENCH_SUBSIDENCE_SCALE_M
            : OCEANIC_TRENCH_SUBSIDENCE_SCALE_M;
        const double trench = (
            oceanic
                ? -convergence_squared * oceanic_trench_scale
                : -conv * 350.0
        ) * relief_scale;
        const double volcanic = (
            (cell.crust_type == 3 ? VOLCANIC_ARC_UPLIFT_SCALE_M * convergence_squared : 0.0) +
            380.0 * div
        ) * relief_scale;
        const double fault = -320.0 * trans;
        const double rough = (continental ? 520.0 : 180.0) * coherent_n2 +
            (oceanic ? 260.0 : 620.0) * n0 +
            180.0 * std::sin(9.0 * cell.lon + 4.0 * cell.lat);
        cell.initial_isostatic_elevation_m = isostatic;
        cell.thermal_subsidence_target_m = thermal;
        cell.initial_ridge_uplift_m = ridge;
        cell.initial_orogenic_uplift_m = orogen;
        cell.initial_volcanic_uplift_m = volcanic;
        cell.initial_trench_subsidence_m = trench;
        cell.initial_rift_subsidence_m = rift;
        cell.initial_transform_fault_relief_m = fault;
        cell.initial_secondary_roughness_m = rough;
        cell.initial_elevation_m = isostatic + thermal + ridge + rift + orogen + trench + volcanic + fault + rough;
        cell.volcanic_potential_index = clamp(
            0.42 * div + 0.38 * conv * (cell.crust_type == 3 ? 1.0 : 0.35) +
            0.16 * (cell.lithology == 5 ? 1.0 : 0.0) + 0.04 * tectonic_activity,
            0.0,
            1.0
        );
        cell.uplift_rate = params.tectonic_uplift_scale * tectonic_activity *
            (1.5 * div + 8.5 * conv + (cell.crust_type == 3 ? 2.5 : 0.0)) *
            maturation_timestep_scale(params);
        cell.elevation_m = cell.initial_elevation_m;
        cell.initial_plate_id = cell.plate_id;
    }
    for (Cell& cell : cells) {
        initialize_sediment_interface(cell, "initial topography");
    }
}

bool is_oceanic_crust_state(
    int crust_type,
    int lithology,
    double age_ma,
    double thickness_km,
    double density
) {
    if (crust_type == 0) {
        return true;
    }
    if (crust_type == 2) {
        return lithology == 0;
    }
    if (crust_type != 3) {
        return false;
    }
    return age_ma <= 320.0 && thickness_km <= 18.0 && density >= 2.84;
}

namespace {

struct CrustRuleState {
    int crust_type = 0;
    int lithology = 0;
    double age_ma = 0.0;
    double thickness_km = 0.0;
    double density = 0.0;
};

struct CrustProcessCellDelta {
    bool triggered = false;
    bool changed = false;
    double crust_volume_km3 = 0.0;
    double density_weighted_crust_volume = 0.0;
    double crust_age_volume_moment_km3_ma = 0.0;
};

void record_crust_process_transition(
    double area_km2,
    bool triggered,
    const CrustRuleState& before,
    const CrustRuleState& after,
    CrustProcessCellDelta& delta
) {
    const double before_volume = area_km2 * before.thickness_km;
    const double after_volume = area_km2 * after.thickness_km;
    const bool changed =
        before.age_ma != after.age_ma ||
        before.thickness_km != after.thickness_km ||
        before.density != after.density;
    delta.triggered = delta.triggered || triggered;
    delta.changed = delta.changed || changed;
    delta.crust_volume_km3 += after_volume - before_volume;
    delta.density_weighted_crust_volume +=
        after_volume * after.density - before_volume * before.density;
    delta.crust_age_volume_moment_km3_ma +=
        after_volume * after.age_ma - before_volume * before.age_ma;
}

}  // namespace

double crust_equilibrium_elevation_m(double thickness_km, double density, bool oceanic) {
    if (oceanic) {
        return -OCEANIC_RIDGE_REFERENCE_DEPTH_M;
    }
    return CONTINENTAL_ISOSTATIC_FREEBOARD_M +
        CONTINENTAL_CRUST_THICKNESS_FREEBOARD_M_PER_KM * (
            thickness_km - CONTINENTAL_REFERENCE_CRUST_THICKNESS_KM
        ) -
        CONTINENTAL_CRUST_DENSITY_FREEBOARD_M_PER_G_CM3 * (
            density - CONTINENTAL_REFERENCE_CRUST_DENSITY_G_CM3
        );
}

PlateMotionStep summarize_plate_motion_step(
    const Params& params,
    const std::vector<Cell>& cells,
    const std::vector<Plate>& plates,
    int id,
    int erosion_iteration,
    const std::string& stage,
    const std::vector<int>& previous_plate_ids,
    const std::vector<double>& step_rotation_deg,
    const CrustMotionDiagnostics& crust_motion,
    const std::vector<double>& crust_age_change_ma,
    const std::vector<double>& crust_thickness_change_km,
    const std::vector<double>& crust_density_change,
    const std::vector<double>& tectonic_elevation_change_m,
    const std::vector<double>& previous_local_isostatic_equilibrium_m,
    const std::vector<double>& isostatic_equilibrium_change_m,
    const std::vector<double>& previous_local_thermal_subsidence_target_m,
    const std::vector<double>& thermal_equilibrium_change_m,
    const std::vector<double>& unbounded_dynamic_relief_change_m,
    const std::vector<double>& bounded_dynamic_relief_change_m
) {
    if (cells.size() > static_cast<std::size_t>(
            std::numeric_limits<int>::max())) {
        throw std::length_error(
            "plate-motion summary cell count exceeds native integer capacity"
        );
    }
    if (
        previous_local_isostatic_equilibrium_m.size() != cells.size() ||
        isostatic_equilibrium_change_m.size() != cells.size() ||
        previous_local_thermal_subsidence_target_m.size() != cells.size() ||
        thermal_equilibrium_change_m.size() != cells.size() ||
        unbounded_dynamic_relief_change_m.size() != cells.size() ||
        bounded_dynamic_relief_change_m.size() != cells.size()
    ) {
        throw std::invalid_argument(
            "plate-motion equilibrium checkpoint cardinality must equal cell count"
        );
    }
    PlateMotionStep step;
    step.id = id;
    step.erosion_iteration = erosion_iteration;
    step.stage = stage;
    step.cell_count = static_cast<int>(cells.size());
    step.plate_count = static_cast<int>(plates.size());
    step.cell_plate_ids.reserve(cells.size());
    step.crust_type_by_cell.reserve(cells.size());
    step.lithology_by_cell.reserve(cells.size());
    step.transport_plan = crust_motion.transport_plan;
    step.boundary_segments = build_plate_boundary_segments(
        params,
        cells,
        plates,
        step.transport_plan,
        &step.reciprocal_mesh_segment_count
    );
    step.boundary_segment_count = static_cast<int>(
        step.boundary_segments.size()
    );
    step.crust_overlap_candidate_fate_ledger =
        build_crust_overlap_candidate_fate_ledger(
            step.transport_plan,
            step.boundary_segments,
            step.id,
            step.cell_count,
            step.plate_count
        );
    std::unordered_set<int> boundary_incident_cell_ids;
    for (const PlateBoundarySegment& segment : step.boundary_segments) {
        boundary_incident_cell_ids.insert(segment.left_cell_id);
        boundary_incident_cell_ids.insert(segment.right_cell_id);
    }
    step.control_volume_boundary_incident_cell_count = static_cast<int>(
        boundary_incident_cell_ids.size()
    );
    step.crust_transport_distance_km_by_cell = crust_motion.transport_distance_km_by_cell;
    step.crust_age_transport_change_ma_by_cell = crust_motion.age_transport_change_ma_by_cell;
    step.crust_thickness_transport_change_km_by_cell = crust_motion.thickness_transport_change_km_by_cell;
    step.crust_density_transport_change_by_cell = crust_motion.density_transport_change_by_cell;
    step.crust_age_process_change_ma_by_cell = crust_motion.age_process_change_ma_by_cell;
    step.crust_thickness_process_change_km_by_cell = crust_motion.thickness_process_change_km_by_cell;
    step.crust_density_process_change_by_cell = crust_motion.density_process_change_by_cell;
    step.process_inventory_delta_by_reason =
        crust_motion.process_inventory_delta_by_reason;
    for (std::vector<double>* values : {
        &step.crust_transport_distance_km_by_cell,
        &step.crust_age_transport_change_ma_by_cell,
        &step.crust_thickness_transport_change_km_by_cell,
        &step.crust_density_transport_change_by_cell,
        &step.crust_age_process_change_ma_by_cell,
        &step.crust_thickness_process_change_km_by_cell,
        &step.crust_density_process_change_by_cell,
    }) {
        if (values->size() != cells.size()) {
            values->assign(cells.size(), 0.0);
        }
    }
    step.aged_oceanic_cell_ids = crust_motion.aged_oceanic_cell_ids;
    step.rejuvenated_oceanic_cell_ids = crust_motion.rejuvenated_oceanic_cell_ids;
    step.subducted_oceanic_cell_ids = crust_motion.subducted_oceanic_cell_ids;
    step.aged_oceanic_cell_count = static_cast<int>(step.aged_oceanic_cell_ids.size());
    step.rejuvenated_oceanic_cell_count = static_cast<int>(step.rejuvenated_oceanic_cell_ids.size());
    step.subducted_oceanic_cell_count = static_cast<int>(step.subducted_oceanic_cell_ids.size());
    step.crust_age_change_ma_by_cell = crust_age_change_ma;
    step.crust_thickness_change_km_by_cell = crust_thickness_change_km;
    step.crust_density_change_by_cell = crust_density_change;
    step.tectonic_elevation_change_m_by_cell = tectonic_elevation_change_m;
    step.previous_local_isostatic_equilibrium_m.reserve(cells.size());
    step.post_process_local_isostatic_equilibrium_m.reserve(cells.size());
    step.isostatic_equilibrium_change_m.reserve(cells.size());
    step.previous_local_thermal_subsidence_target_m.reserve(cells.size());
    step.post_process_local_thermal_subsidence_target_m.reserve(cells.size());
    step.thermal_equilibrium_change_m.reserve(cells.size());
    step.unbounded_dynamic_relief_change_m.reserve(cells.size());
    step.bounded_dynamic_relief_change_m.reserve(cells.size());
    step.boundary_convergent_by_cell.reserve(cells.size());
    step.boundary_divergent_by_cell.reserve(cells.size());
    step.boundary_transform_by_cell.reserve(cells.size());

    std::vector<int> plate_cell_counts(plates.size(), 0);
    std::vector<double> plate_areas(plates.size(), 0.0);
    for (std::size_t index = 0; index < cells.size(); ++index) {
        const Cell& cell = cells[index];
        step.cell_plate_ids.push_back(cell.plate_id);
        step.crust_type_by_cell.push_back(cell.crust_type);
        step.lithology_by_cell.push_back(cell.lithology);
        step.boundary_convergent_by_cell.push_back(cell.boundary_convergent);
        step.boundary_divergent_by_cell.push_back(cell.boundary_divergent);
        step.boundary_transform_by_cell.push_back(cell.boundary_transform);
        const double previous_isostatic_equilibrium_m =
            previous_local_isostatic_equilibrium_m[index];
        const bool post_process_oceanic_like = is_oceanic_crust_state(
            cell.crust_type,
            cell.lithology,
            cell.crust_age_ma,
            cell.crust_thickness_km,
            cell.crust_density
        );
        const double post_process_isostatic_equilibrium_m =
            crust_equilibrium_elevation_m(
                cell.crust_thickness_km,
                cell.crust_density,
                post_process_oceanic_like
            );
        const double expected_isostatic_equilibrium_change_m =
            TECTONIC_ISOSTATIC_TARGET_DIFFERENCE_GAIN * (
                post_process_isostatic_equilibrium_m -
                    previous_isostatic_equilibrium_m
            );
        if (
            !std::isfinite(previous_isostatic_equilibrium_m) ||
            !std::isfinite(post_process_isostatic_equilibrium_m) ||
            !std::isfinite(isostatic_equilibrium_change_m[index]) ||
            isostatic_equilibrium_change_m[index] !=
                expected_isostatic_equilibrium_change_m
        ) {
            throw std::runtime_error(
                "plate-motion isostatic equilibrium change is non-finite or stale"
            );
        }
        const double previous_thermal_subsidence_m =
            previous_local_thermal_subsidence_target_m[index];
        const double expected_post_process_thermal_subsidence_m =
            oceanic_age_depth_thermal_subsidence_m(
                cell.crust_age_ma,
                post_process_oceanic_like
            );
        if (!std::isfinite(previous_thermal_subsidence_m) ||
            !std::isfinite(cell.thermal_subsidence_target_m) ||
            cell.thermal_subsidence_target_m !=
                expected_post_process_thermal_subsidence_m) {
            throw std::runtime_error(
                "plate-motion thermal checkpoint is non-finite or stale"
            );
        }
        const double expected_thermal_equilibrium_change_m =
            OCEANIC_AGE_DEPTH_TARGET_DIFFERENCE_GAIN * (
                cell.thermal_subsidence_target_m -
                    previous_thermal_subsidence_m
            );
        const double recorded_thermal_equilibrium_change_m =
            thermal_equilibrium_change_m[index];
        if (!std::isfinite(recorded_thermal_equilibrium_change_m) ||
            recorded_thermal_equilibrium_change_m !=
                expected_thermal_equilibrium_change_m) {
            throw std::runtime_error(
                "plate-motion thermal equilibrium change is non-finite or stale"
            );
        }
        const double expected_bounded_dynamic_relief_change_m = clamp(
            unbounded_dynamic_relief_change_m[index],
            TECTONIC_DYNAMIC_RELIEF_MINIMUM_CHANGE_M,
            TECTONIC_DYNAMIC_RELIEF_MAXIMUM_CHANGE_M
        );
        if (
            !std::isfinite(unbounded_dynamic_relief_change_m[index]) ||
            !std::isfinite(bounded_dynamic_relief_change_m[index]) ||
            bounded_dynamic_relief_change_m[index] !=
                expected_bounded_dynamic_relief_change_m
        ) {
            throw std::runtime_error(
                "plate-motion bounded dynamic relief change is non-finite or stale"
            );
        }
        const double expected_tectonic_elevation_change_m =
            expected_isostatic_equilibrium_change_m +
            expected_thermal_equilibrium_change_m +
            expected_bounded_dynamic_relief_change_m;
        if (
            index >= tectonic_elevation_change_m.size() ||
            !std::isfinite(tectonic_elevation_change_m[index]) ||
            tectonic_elevation_change_m[index] !=
                expected_tectonic_elevation_change_m
        ) {
            throw std::runtime_error(
                "plate-motion tectonic elevation change does not replay"
            );
        }
        step.previous_local_isostatic_equilibrium_m.push_back(
            previous_isostatic_equilibrium_m
        );
        step.post_process_local_isostatic_equilibrium_m.push_back(
            post_process_isostatic_equilibrium_m
        );
        step.isostatic_equilibrium_change_m.push_back(
            isostatic_equilibrium_change_m[index]
        );
        step.previous_local_thermal_subsidence_target_m.push_back(
            previous_thermal_subsidence_m
        );
        step.post_process_local_thermal_subsidence_target_m.push_back(
            cell.thermal_subsidence_target_m
        );
        step.thermal_equilibrium_change_m.push_back(
            recorded_thermal_equilibrium_change_m
        );
        step.unbounded_dynamic_relief_change_m.push_back(
            unbounded_dynamic_relief_change_m[index]
        );
        step.bounded_dynamic_relief_change_m.push_back(
            bounded_dynamic_relief_change_m[index]
        );
        const double transport_distance_km = step.crust_transport_distance_km_by_cell[index];
        step.mean_crust_transport_distance_km += transport_distance_km;
        step.max_crust_transport_distance_km = std::max(
            step.max_crust_transport_distance_km, transport_distance_km
        );
        if (cell.plate_id >= 0 && cell.plate_id < static_cast<int>(plates.size())) {
            plate_cell_counts[static_cast<std::size_t>(cell.plate_id)]++;
            plate_areas[static_cast<std::size_t>(cell.plate_id)] += cell.area_km2;
        }
        if (cell.boundary_type != 0) {
            step.plate_boundary_cell_count++;
        }
        if (cell.crust_type == 8) {
            step.accreted_terrane_cell_count++;
        }
        if (index < previous_plate_ids.size() && cell.plate_id != previous_plate_ids[index]) {
            step.reassigned_cell_count++;
        }
        if (index < crust_age_change_ma.size()) {
            step.mean_abs_crust_age_change_ma += std::abs(crust_age_change_ma[index]);
        }
        if (index < crust_thickness_change_km.size()) {
            step.mean_abs_crust_thickness_change_km += std::abs(crust_thickness_change_km[index]);
        }
        if (index < crust_density_change.size()) {
            step.mean_abs_crust_density_change += std::abs(crust_density_change[index]);
        }
        step.mean_abs_crust_age_transport_change_ma += std::abs(
            step.crust_age_transport_change_ma_by_cell[index]
        );
        step.mean_abs_crust_thickness_transport_change_km += std::abs(
            step.crust_thickness_transport_change_km_by_cell[index]
        );
        step.mean_abs_crust_density_transport_change += std::abs(
            step.crust_density_transport_change_by_cell[index]
        );
        step.mean_abs_crust_age_process_change_ma += std::abs(
            step.crust_age_process_change_ma_by_cell[index]
        );
        step.mean_abs_crust_thickness_process_change_km += std::abs(
            step.crust_thickness_process_change_km_by_cell[index]
        );
        step.mean_abs_crust_density_process_change += std::abs(
            step.crust_density_process_change_by_cell[index]
        );
        if (index < tectonic_elevation_change_m.size()) {
            const double delta = tectonic_elevation_change_m[index];
            step.mean_tectonic_elevation_change_m += delta;
            step.mean_abs_tectonic_elevation_change_m += std::abs(delta);
            step.max_abs_tectonic_elevation_change_m = std::max(
                step.max_abs_tectonic_elevation_change_m,
                std::abs(delta)
            );
        }
        for (int neighbor : cell.neighbors) {
            if (neighbor > static_cast<int>(index) && cell.plate_id != cells[static_cast<std::size_t>(neighbor)].plate_id) {
                step.plate_boundary_edge_count++;
            }
        }
    }

    const double cell_divisor = cells.empty() ? 1.0 : static_cast<double>(cells.size());
    step.reassigned_cell_fraction = static_cast<double>(step.reassigned_cell_count) / cell_divisor;
    step.mean_crust_transport_distance_km /= cell_divisor;
    step.mean_abs_crust_age_change_ma /= cell_divisor;
    step.mean_abs_crust_thickness_change_km /= cell_divisor;
    step.mean_abs_crust_density_change /= cell_divisor;
    step.mean_abs_crust_age_transport_change_ma /= cell_divisor;
    step.mean_abs_crust_thickness_transport_change_km /= cell_divisor;
    step.mean_abs_crust_density_transport_change /= cell_divisor;
    step.mean_abs_crust_age_process_change_ma /= cell_divisor;
    step.mean_abs_crust_thickness_process_change_km /= cell_divisor;
    step.mean_abs_crust_density_process_change /= cell_divisor;
    step.mean_tectonic_elevation_change_m /= cell_divisor;
    step.mean_abs_tectonic_elevation_change_m /= cell_divisor;

    for (std::size_t plate_index = 0; plate_index < plates.size(); ++plate_index) {
        const Plate& plate = plates[plate_index];
        PlateKinematicSnapshot snapshot;
        snapshot.plate_id = plate.id;
        snapshot.center = plate.center;
        snapshot.rotation_axis = plate.axis;
        snapshot.intrinsic_angular_speed = plate.angular_speed;
        snapshot.step_rotation_deg = plate_index < step_rotation_deg.size() ? step_rotation_deg[plate_index] : 0.0;
        snapshot.cumulative_rotation_deg = plate.cumulative_rotation_deg;
        snapshot.cell_count = plate_cell_counts[plate_index];
        snapshot.area_km2 = plate_areas[plate_index];
        step.mean_plate_rotation_deg += std::abs(snapshot.step_rotation_deg);
        step.max_plate_rotation_deg = std::max(step.max_plate_rotation_deg, std::abs(snapshot.step_rotation_deg));
        step.plates.push_back(snapshot);
    }
    if (!plates.empty()) {
        step.mean_plate_rotation_deg /= static_cast<double>(plates.size());
    }
    for (const Cell& cell : cells) {
        const double volume = cell.area_km2 * cell.crust_thickness_km;
        step.post_process_crust_volume_km3 += volume;
        step.post_process_density_weighted_crust_volume +=
            volume * cell.crust_density;
        step.post_process_crust_age_volume_moment +=
            volume * cell.crust_age_ma;
    }
    // Validate rule completeness against per-cell transported-to-final state
    // changes.  This avoids using the ill-conditioned difference between two
    // large global inventories as the omission detector.
    std::array<long double, 3> direct_rule_delta{};
    std::array<long double, 3> direct_rule_absolute_delta{};
    for (std::size_t index = 0; index < cells.size(); ++index) {
        const Cell& cell = cells[index];
        const double transported_volume = cell.area_km2 *
            step.transport_plan.remapped_crust_thickness_km_by_cell[index];
        const double post_process_volume =
            cell.area_km2 * cell.crust_thickness_km;
        const std::array<double, 3> transported_state = {
            transported_volume,
            transported_volume *
                step.transport_plan.remapped_crust_density_by_cell[index],
            transported_volume *
                step.transport_plan.remapped_crust_age_ma_by_cell[index],
        };
        const std::array<double, 3> post_process_state = {
            post_process_volume,
            post_process_volume * cell.crust_density,
            post_process_volume * cell.crust_age_ma,
        };
        for (std::size_t component = 0;
             component < direct_rule_delta.size();
             ++component) {
            const double cell_delta =
                post_process_state[component] - transported_state[component];
            direct_rule_delta[component] += cell_delta;
            direct_rule_absolute_delta[component] += std::abs(cell_delta);
        }
    }
    std::array<long double, 3> attributed_process_delta{};
    std::array<long double, 3> attributed_absolute_delta{};
    for (const CrustProcessInventoryDelta& reason :
         step.process_inventory_delta_by_reason) {
        const std::array<double, 3> signed_from_positive_negative = {
            reason.positive_crust_volume_km3 -
                reason.negative_crust_volume_magnitude_km3,
            reason.positive_density_weighted_crust_volume -
                reason.negative_density_weighted_crust_volume_magnitude,
            reason.positive_crust_age_volume_moment_km3_ma -
                reason.negative_crust_age_volume_moment_magnitude_km3_ma,
        };
        const std::array<double, 3> recorded_net = {
            reason.crust_volume_km3,
            reason.density_weighted_crust_volume,
            reason.crust_age_volume_moment_km3_ma,
        };
        for (std::size_t component = 0;
             component < recorded_net.size();
             ++component) {
            if (recorded_net[component] !=
                signed_from_positive_negative[component]) {
                throw std::runtime_error(
                    "crust process positive/negative inventory did not reconcile"
                );
            }
        }
        attributed_process_delta[0] += reason.crust_volume_km3;
        attributed_process_delta[1] += reason.density_weighted_crust_volume;
        attributed_process_delta[2] +=
            reason.crust_age_volume_moment_km3_ma;
        attributed_absolute_delta[0] +=
            reason.positive_crust_volume_km3 +
            reason.negative_crust_volume_magnitude_km3;
        attributed_absolute_delta[1] +=
            reason.positive_density_weighted_crust_volume +
            reason.negative_density_weighted_crust_volume_magnitude;
        attributed_absolute_delta[2] +=
            reason.positive_crust_age_volume_moment_km3_ma +
            reason.negative_crust_age_volume_moment_magnitude_km3_ma;
    }
    const std::array<double, 3> serialized_process_delta = {
        step.post_process_crust_volume_km3 -
            step.transport_plan.transported_crust_volume_km3,
        step.post_process_density_weighted_crust_volume -
            step.transport_plan.transported_density_weighted_crust_volume,
        step.post_process_crust_age_volume_moment -
            step.transport_plan.transported_crust_age_volume_moment,
    };
    const std::array<long double, 3> inventory_subtraction_magnitude = {
        std::abs(step.post_process_crust_volume_km3) +
            std::abs(step.transport_plan.transported_crust_volume_km3),
        std::abs(step.post_process_density_weighted_crust_volume) +
            std::abs(
                step.transport_plan.transported_density_weighted_crust_volume
            ),
        std::abs(step.post_process_crust_age_volume_moment) +
            std::abs(step.transport_plan.transported_crust_age_volume_moment),
    };
    for (std::size_t index = 0; index < direct_rule_delta.size(); ++index) {
        const long double rule_forward_error_bound =
            128.0L * std::numeric_limits<double>::epsilon() *
            (1.0L + direct_rule_absolute_delta[index] +
                attributed_absolute_delta[index]);
        if (std::abs(
                direct_rule_delta[index] - attributed_process_delta[index]
            ) > rule_forward_error_bound) {
            throw std::runtime_error(
                "reason-resolved crust process inventory exceeded its rule-delta forward-error bound"
            );
        }
        const long double component_inventory_bound =
            16.0L * std::numeric_limits<double>::epsilon() *
            static_cast<long double>(std::max<std::size_t>(1, cells.size())) *
            (1.0L + inventory_subtraction_magnitude[index]);
        if (std::abs(
                static_cast<long double>(serialized_process_delta[index]) -
                direct_rule_delta[index]
            ) > component_inventory_bound) {
            throw std::runtime_error(
                "serialized crust process inventory exceeded its accumulation forward-error bound"
            );
        }
    }
    return step;
}

std::vector<double> advance_plate_motion_and_crust(
    const Params& params,
    int erosion_iteration,
    std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    std::vector<PlateMotionStep>& plate_motion_history,
    CrustMaterialShadowState& crust_material_shadow,
    CrustDryRockAccountingState& crust_dry_rock_accounting
) {
    if (cells.size() > static_cast<std::size_t>(
            std::numeric_limits<int>::max())) {
        throw std::length_error(
            "plate-motion cell count exceeds native integer capacity"
        );
    }
    const int n = static_cast<int>(cells.size());
    const double timestep_scale = maturation_timestep_scale(params);
    std::vector<int> previous_plate_ids(static_cast<std::size_t>(n));
    std::vector<int> previous_crust_types(static_cast<std::size_t>(n));
    std::vector<int> previous_lithologies(static_cast<std::size_t>(n));
    std::vector<double> previous_crust_age(static_cast<std::size_t>(n));
    std::vector<double> previous_crust_thickness(static_cast<std::size_t>(n));
    std::vector<double> previous_crust_density(static_cast<std::size_t>(n));
    std::vector<double> previous_local_isostatic_equilibrium_m(
        static_cast<std::size_t>(n)
    );
    std::vector<double> previous_local_thermal_subsidence_target_m(
        static_cast<std::size_t>(n)
    );
    std::vector<double> previous_convergent(static_cast<std::size_t>(n));
    std::vector<double> previous_divergent(static_cast<std::size_t>(n));
    std::vector<double> previous_transform(static_cast<std::size_t>(n));
    for (int i = 0; i < n; ++i) {
        const Cell& cell = cells[static_cast<std::size_t>(i)];
        previous_plate_ids[static_cast<std::size_t>(i)] = cell.plate_id;
        previous_crust_types[static_cast<std::size_t>(i)] = cell.crust_type;
        previous_lithologies[static_cast<std::size_t>(i)] = cell.lithology;
        previous_crust_age[static_cast<std::size_t>(i)] = cell.crust_age_ma;
        previous_crust_thickness[static_cast<std::size_t>(i)] = cell.crust_thickness_km;
        previous_crust_density[static_cast<std::size_t>(i)] = cell.crust_density;
        const bool previous_oceanic_like = is_oceanic_crust_state(
            cell.crust_type,
            cell.lithology,
            cell.crust_age_ma,
            cell.crust_thickness_km,
            cell.crust_density
        );
        const double expected_previous_thermal_subsidence_m =
            oceanic_age_depth_thermal_subsidence_m(
                cell.crust_age_ma,
                previous_oceanic_like
            );
        if (!std::isfinite(cell.thermal_subsidence_target_m) ||
            cell.thermal_subsidence_target_m !=
                expected_previous_thermal_subsidence_m) {
            throw std::runtime_error(
                "cell thermal subsidence is non-finite or stale before plate motion"
            );
        }
        previous_local_thermal_subsidence_target_m[static_cast<std::size_t>(i)] =
            cell.thermal_subsidence_target_m;
        previous_local_isostatic_equilibrium_m[static_cast<std::size_t>(i)] =
            crust_equilibrium_elevation_m(
                cell.crust_thickness_km,
                cell.crust_density,
                previous_oceanic_like
            );
        previous_convergent[static_cast<std::size_t>(i)] = cell.boundary_convergent;
        previous_divergent[static_cast<std::size_t>(i)] = cell.boundary_divergent;
        previous_transform[static_cast<std::size_t>(i)] = cell.boundary_transform;
    }

    std::vector<double> step_rotation_deg(plates.size(), 0.0);
    std::vector<Vec3> centers;
    centers.reserve(plates.size());
    for (std::size_t index = 0; index < plates.size(); ++index) {
        Plate& plate = plates[index];
        const double rotation_deg = plate.angular_speed *
            params.plate_motion_scale_deg_per_step * timestep_scale;
        const double rotation_rad = rotation_deg / DEG;
        plate.center = rotate_about_axis(plate.center, plate.axis, rotation_rad);
        plate.cumulative_rotation_deg += rotation_deg;
        step_rotation_deg[index] = rotation_deg;
        centers.push_back(plate.center);
    }
    assign_plates(centers, cells);
    classify_boundaries(params, plates, cells);

    CrustMotionDiagnostics crust_motion;
    crust_motion.transport_plan = build_forward_overlap_crust_transport_plan(
        params,
        plates,
        cells,
        previous_plate_ids,
        previous_crust_types,
        previous_lithologies,
        previous_crust_age,
        previous_crust_thickness,
        previous_crust_density,
        step_rotation_deg
    );
    reconcile_accelerated_crust_overlap_continuous_shadow(
        crust_motion.transport_plan,
        cells,
        previous_crust_thickness,
        previous_crust_density,
        previous_crust_age
    );
    begin_crust_material_shadow_step(
        cells,
        crust_motion.transport_plan,
        static_cast<int>(plate_motion_history.size()),
        erosion_iteration,
        "plate_motion_iteration",
        crust_material_shadow
    );
    record_cpu_conservative_crust_overlap_transition();
    crust_motion.transport_distance_km_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.age_transport_change_ma_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.thickness_transport_change_km_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.density_transport_change_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.age_process_change_ma_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.thickness_process_change_km_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.density_process_change_by_cell.assign(static_cast<std::size_t>(n), 0.0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        const std::size_t index = static_cast<std::size_t>(i);
        const int edge_begin =
            crust_motion.transport_plan.destination_offsets[index];
        const int edge_end =
            crust_motion.transport_plan.destination_offsets[index + 1];
        double distance_volume_sum = 0.0;
        double incoming_volume = 0.0;
        for (int edge_index = edge_begin; edge_index < edge_end; ++edge_index) {
            const int source_cell_id = crust_motion.transport_plan.source_cell_ids[
                static_cast<std::size_t>(edge_index)
            ];
            const double edge_volume =
                crust_motion.transport_plan.overlap_area_km2[
                    static_cast<std::size_t>(edge_index)
                ] * previous_crust_thickness[
                    static_cast<std::size_t>(source_cell_id)
                ];
            incoming_volume += edge_volume;
            distance_volume_sum += edge_volume *
                crust_motion.transport_plan.source_kinematic_distance_km[
                    static_cast<std::size_t>(source_cell_id)
                ];
        }
        crust_motion.transport_distance_km_by_cell[index] = incoming_volume > 0.0
            ? distance_volume_sum / incoming_volume
            : 0.0;
        crust_motion.age_transport_change_ma_by_cell[index] =
            crust_motion.transport_plan.remapped_crust_age_ma_by_cell[index] -
            previous_crust_age[index];
        crust_motion.thickness_transport_change_km_by_cell[index] =
            crust_motion.transport_plan.remapped_crust_thickness_km_by_cell[index] -
            previous_crust_thickness[index];
        crust_motion.density_transport_change_by_cell[index] =
            crust_motion.transport_plan.remapped_crust_density_by_cell[index] -
            previous_crust_density[index];
    }

    const double tectonic_activity = clamp(
        params.internal_heat * std::sqrt(4.5 / std::max(0.05, params.geological_age_ga)),
        0.25,
        2.25
    );
    std::vector<double> crust_age_change(static_cast<std::size_t>(n), 0.0);
    std::vector<double> crust_thickness_change(static_cast<std::size_t>(n), 0.0);
    std::vector<double> crust_density_change(static_cast<std::size_t>(n), 0.0);
    std::vector<double> tectonic_elevation_change(static_cast<std::size_t>(n), 0.0);
    std::vector<double> isostatic_equilibrium_change_m(
        static_cast<std::size_t>(n),
        0.0
    );
    std::vector<double> thermal_equilibrium_change_m(
        static_cast<std::size_t>(n),
        0.0
    );
    std::vector<double> unbounded_dynamic_relief_change_m(
        static_cast<std::size_t>(n),
        0.0
    );
    std::vector<double> bounded_dynamic_relief_change_m(
        static_cast<std::size_t>(n),
        0.0
    );
    std::vector<int> aged_oceanic_flags(static_cast<std::size_t>(n), 0);
    std::vector<int> rejuvenated_oceanic_flags(static_cast<std::size_t>(n), 0);
    std::vector<int> subducted_oceanic_flags(static_cast<std::size_t>(n), 0);
    std::vector<std::array<CrustProcessCellDelta, CRUST_PROCESS_REASON_COUNT>>
        process_delta_by_cell(static_cast<std::size_t>(n));
    // OpenMP cannot propagate exceptions across the parallel region. Each
    // worker records only its own cell's fail-closed shadow-accounting error;
    // the canonical serial pass below raises it after all workers join.
    std::vector<std::string> crust_material_errors(static_cast<std::size_t>(n));
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[static_cast<std::size_t>(i)];
        const std::size_t index = static_cast<std::size_t>(i);
        const int old_plate_id = previous_plate_ids[index];
        const bool plate_changed = cell.plate_id != old_plate_id;
        const bool local_old_oceanic = is_oceanic_crust_state(
            previous_crust_types[index],
            previous_lithologies[index],
            previous_crust_age[index],
            previous_crust_thickness[index],
            previous_crust_density[index]
        );
        const bool old_oceanic = is_oceanic_crust_state(
            crust_motion.transport_plan.remapped_crust_type_by_cell[index],
            crust_motion.transport_plan.remapped_lithology_by_cell[index],
            crust_motion.transport_plan.remapped_crust_age_ma_by_cell[index],
            crust_motion.transport_plan.remapped_crust_thickness_km_by_cell[index],
            crust_motion.transport_plan.remapped_crust_density_by_cell[index]
        );
        const double conv = cell.boundary_convergent;
        const double div = cell.boundary_divergent;
        const double trans = cell.boundary_transform;

        int crust_type =
            crust_motion.transport_plan.remapped_crust_type_by_cell[index];
        int lithology =
            crust_motion.transport_plan.remapped_lithology_by_cell[index];
        double crust_age =
            crust_motion.transport_plan.remapped_crust_age_ma_by_cell[index];
        double crust_thickness =
            crust_motion.transport_plan.remapped_crust_thickness_km_by_cell[index];
        double crust_density =
            crust_motion.transport_plan.remapped_crust_density_by_cell[index];

        const auto current_rule_state = [&]() {
            return CrustRuleState{
                crust_type,
                lithology,
                crust_age,
                crust_thickness,
                crust_density,
            };
        };
        const auto record_reason = [&](
            CrustProcessReason reason,
            bool triggered,
            const CrustRuleState& before
        ) {
            record_crust_process_transition(
                cell.area_km2,
                triggered,
                before,
                current_rule_state(),
                process_delta_by_cell[index][static_cast<std::size_t>(reason)]
            );
            if (crust_material_errors[index].empty()) {
                const CrustRuleState after = current_rule_state();
                try {
                    apply_crust_material_shadow_transition(
                        crust_material_shadow,
                        i,
                        cell.plate_id,
                        reason,
                        cell.area_km2,
                        before.thickness_km,
                        before.density,
                        after.thickness_km,
                        after.density
                    );
                } catch (const std::exception& error) {
                    crust_material_errors[index] = error.what();
                } catch (...) {
                    crust_material_errors[index] =
                        "unknown crust material shadow transition failure";
                }
            }
        };

        const CrustRuleState before_quiet_aging = current_rule_state();
        if (old_oceanic && div < 0.10 && conv < 0.10) {
            const double quiet_fraction = clamp(1.0 - std::max(div, conv) / 0.10, 0.0, 1.0);
            crust_age += params.oceanic_crust_aging_ma_per_step *
                timestep_scale * quiet_fraction;
        }
        record_reason(
            CRUST_PROCESS_QUIET_OCEANIC_AGING,
            old_oceanic && div < 0.10 && conv < 0.10,
            before_quiet_aging
        );

        if (plate_changed && std::max(conv, div) < 0.18) {
            crust_type = 2;
            lithology = old_oceanic ? 0 : 3;
        }
        if (div >= 0.10) {
            if (old_oceanic) {
                const CrustRuleState before_rejuvenation = current_rule_state();
                const double background_rejuvenation_reference =
                    clamp(div * 0.55, 0.0, 0.85);
                double rejuvenation = timestep_scale == 1.0 ?
                    clamp(div * (plate_changed ? 0.72 : 0.55), 0.0, 0.85) :
                    timestep_scaled_fraction(
                        background_rejuvenation_reference,
                        timestep_scale
                    );
                if (plate_changed && timestep_scale != 1.0) {
                    const double crossing_rejuvenation_reference =
                        clamp(div * 0.72, 0.0, 0.85);
                    const double crossing_impulse = clamp(
                        (crossing_rejuvenation_reference -
                            background_rejuvenation_reference) /
                            std::max(
                                1.0e-12,
                                1.0 - background_rejuvenation_reference
                            ),
                        0.0,
                        1.0
                    );
                    rejuvenation = 1.0 -
                        (1.0 - rejuvenation) *
                        (1.0 - crossing_impulse);
                }
                crust_age *= 1.0 - rejuvenation;
                record_reason(
                    CRUST_PROCESS_OCEANIC_RIDGE_REJUVENATION,
                    true,
                    before_rejuvenation
                );
                const CrustRuleState before_ridge_relaxation =
                    current_rule_state();
                if (timestep_scale == 1.0) {
                    crust_thickness += (7.0 - crust_thickness) * 0.34 * div;
                    crust_density += (3.0 - crust_density) * 0.24 * div;
                } else {
                    crust_thickness += (7.0 - crust_thickness) *
                        timestep_scaled_fraction(0.34 * div, timestep_scale);
                    crust_density += (3.0 - crust_density) *
                        timestep_scaled_fraction(0.24 * div, timestep_scale);
                }
                record_reason(
                    CRUST_PROCESS_OCEANIC_RIDGE_CREATION_RELAXATION,
                    true,
                    before_ridge_relaxation
                );
                if (div >= 0.28) {
                    crust_type = 0;
                    lithology = 0;
                }
            } else {
                const CrustRuleState before_continental_rifting =
                    current_rule_state();
                if (timestep_scale == 1.0) {
                    crust_thickness -= tectonic_activity *
                        (0.45 + (plate_changed ? 0.20 : 0.0)) * div;
                } else {
                    crust_thickness -= tectonic_activity * 0.45 * div *
                        timestep_scale;
                    if (plate_changed) {
                        crust_thickness -= tectonic_activity * 0.20 * div;
                    }
                }
                // A fully uncovered overlap row can start this ordered rule at
                // zero thickness. Divergent thinning may exhaust material but
                // must never manufacture a negative scalar crust reservoir;
                // the later thickness bound explicitly records any reseeding.
                crust_thickness = std::max(0.0, crust_thickness);
                crust_density += 0.004 * div * timestep_scale;
                record_reason(
                    CRUST_PROCESS_DIVERGENT_CONTINENTAL_RIFTING,
                    true,
                    before_continental_rifting
                );
                if (div >= 0.24) {
                    crust_type = 6;
                    lithology = 3;
                }
            }
        }
        if (conv >= 0.10) {
            if (old_oceanic) {
                const CrustRuleState before_oceanic_convergence =
                    current_rule_state();
                crust_thickness += tectonic_activity * 0.34 * conv *
                    timestep_scale;
                crust_age *= 1.0 - timestep_scaled_fraction(
                    0.12 * conv,
                    timestep_scale
                );
                record_reason(
                    CRUST_PROCESS_OCEANIC_CONVERGENCE_SUBDUCTION_PROXY,
                    true,
                    before_oceanic_convergence
                );
                if (conv >= 0.26) {
                    crust_type = 3;
                    lithology = 5;
                }
            } else {
                const CrustRuleState before_collision = current_rule_state();
                if (timestep_scale == 1.0) {
                    const double combined_thickness = crust_thickness +
                        tectonic_activity *
                        (0.72 + (plate_changed ? 0.38 : 0.0)) * conv;
                    crust_thickness += tectonic_activity * 0.72 * conv;
                    crust_density -= 0.006 * conv * timestep_scale;
                    record_reason(
                        CRUST_PROCESS_CONTINENTAL_COLLISION_OROGENY,
                        true,
                        before_collision
                    );
                    const CrustRuleState before_accretion = current_rule_state();
                    crust_thickness = combined_thickness;
                    record_reason(
                        CRUST_PROCESS_PLATE_CROSSING_ACCRETION_PROXY,
                        plate_changed,
                        before_accretion
                    );
                } else {
                    crust_thickness += tectonic_activity * 0.72 * conv *
                        timestep_scale;
                    crust_density -= 0.006 * conv * timestep_scale;
                    record_reason(
                        CRUST_PROCESS_CONTINENTAL_COLLISION_OROGENY,
                        true,
                        before_collision
                    );
                    const CrustRuleState before_accretion = current_rule_state();
                    if (plate_changed) {
                        crust_thickness += tectonic_activity * 0.38 * conv;
                    }
                    record_reason(
                        CRUST_PROCESS_PLATE_CROSSING_ACCRETION_PROXY,
                        plate_changed,
                        before_accretion
                    );
                }
                if (plate_changed && conv >= 0.18) {
                    crust_type = 8;
                    lithology = 6;
                } else if (conv >= 0.28) {
                    crust_type = 5;
                    lithology = 6;
                }
            }
        }

        const bool new_oceanic = is_oceanic_crust_state(
            crust_type,
            lithology,
            crust_age,
            crust_thickness,
            crust_density
        );
        const CrustRuleState before_age_bound = current_rule_state();
        const double age_upper_bound = crust_age_ceiling_ma(
            params,
            new_oceanic ? 320.0 : 4200.0
        );
        crust_age = clamp(
            crust_age,
            0.0,
            age_upper_bound
        );
        record_reason(
            CRUST_PROCESS_AGE_BOUND_ENFORCEMENT,
            before_age_bound.age_ma < 0.0 ||
                before_age_bound.age_ma > age_upper_bound,
            before_age_bound
        );
        const CrustRuleState before_thickness_bound = current_rule_state();
        const double minimum_thickness = new_oceanic ? 4.5 : 16.0;
        const double maximum_thickness = new_oceanic ? 18.0 : 76.0;
        crust_thickness = clamp(
            crust_thickness,
            minimum_thickness,
            maximum_thickness
        );
        record_reason(
            CRUST_PROCESS_THICKNESS_BOUND_ENFORCEMENT,
            before_thickness_bound.thickness_km < minimum_thickness ||
                before_thickness_bound.thickness_km > maximum_thickness,
            before_thickness_bound
        );
        const CrustRuleState before_density_bound = current_rule_state();
        crust_density = clamp(crust_density, 2.58, 3.08);
        record_reason(
            CRUST_PROCESS_DENSITY_BOUND_ENFORCEMENT,
            before_density_bound.density < 2.58 ||
                before_density_bound.density > 3.08,
            before_density_bound
        );

        crust_motion.age_process_change_ma_by_cell[index] = crust_age -
            crust_motion.transport_plan.remapped_crust_age_ma_by_cell[index];
        crust_motion.thickness_process_change_km_by_cell[index] =
            crust_thickness -
            crust_motion.transport_plan.remapped_crust_thickness_km_by_cell[index];
        crust_motion.density_process_change_by_cell[index] =
            crust_density -
            crust_motion.transport_plan.remapped_crust_density_by_cell[index];
        crust_age_change[index] = crust_age - previous_crust_age[index];
        crust_thickness_change[index] = crust_thickness - previous_crust_thickness[index];
        crust_density_change[index] = crust_density - previous_crust_density[index];
        cell.crust_type = crust_type;
        cell.lithology = lithology;
        cell.crust_age_ma = crust_age;
        cell.crust_thickness_km = crust_thickness;
        cell.crust_density = crust_density;
        cell.cumulative_crust_transport_distance_km += crust_motion.transport_distance_km_by_cell[index];
        if (crust_motion.age_process_change_ma_by_cell[index] > 1.0e-6 && old_oceanic) {
            aged_oceanic_flags[index] = 1;
            cell.oceanic_crust_aging_event_count++;
        }
        if (div >= 0.10 && crust_motion.age_process_change_ma_by_cell[index] < -1.0e-6 && old_oceanic) {
            rejuvenated_oceanic_flags[index] = 1;
            cell.oceanic_crust_rejuvenation_event_count++;
        }
        if (
            conv >= 0.18 &&
            ((plate_changed && local_old_oceanic) || (old_oceanic && conv >= 0.26))
        ) {
            subducted_oceanic_flags[index] = 1;
            cell.oceanic_crust_subduction_event_count++;
        }
        if (plate_changed) {
            cell.plate_assignment_change_count++;
            cell.last_plate_assignment_change_iteration = erosion_iteration;
        }

        const double old_isostatic_equilibrium_m = crust_equilibrium_elevation_m(
            previous_crust_thickness[index],
            previous_crust_density[index],
            local_old_oceanic
        );
        const double new_isostatic_equilibrium_m = crust_equilibrium_elevation_m(
            crust_thickness,
            crust_density,
            new_oceanic
        );
        const double old_thermal_subsidence_m =
            previous_local_thermal_subsidence_target_m[index];
        const double new_thermal_subsidence_m =
            oceanic_age_depth_thermal_subsidence_m(
                crust_age,
                new_oceanic
            );
        const double thermal_equilibrium_change =
            OCEANIC_AGE_DEPTH_TARGET_DIFFERENCE_GAIN * (
                new_thermal_subsidence_m - old_thermal_subsidence_m
            );
        if (!std::isfinite(thermal_equilibrium_change)) {
            crust_material_errors[index] =
                "non-finite oceanic age-depth equilibrium change";
        }
        thermal_equilibrium_change_m[index] =
            thermal_equilibrium_change;
        cell.thermal_subsidence_target_m = new_thermal_subsidence_m;
        cell.volcanic_potential_index = clamp(
            0.42 * div + 0.38 * conv * (crust_type == 3 ? 1.0 : 0.35) +
            0.16 * (lithology == 5 ? 1.0 : 0.0) + 0.04 * tectonic_activity,
            0.0,
            1.0
        );
        cell.uplift_rate = params.tectonic_uplift_scale * tectonic_activity *
            (1.5 * div + 8.5 * conv + (crust_type == 3 ? 2.5 : 0.0)) *
            timestep_scale;
        const double boundary_change =
            80.0 * (conv - previous_convergent[index]) +
            55.0 * (div - previous_divergent[index]) -
            30.0 * (trans - previous_transform[index]);
        const double isostatic_equilibrium_tendency_m =
            TECTONIC_ISOSTATIC_TARGET_DIFFERENCE_GAIN * (
                new_isostatic_equilibrium_m - old_isostatic_equilibrium_m
            );
        isostatic_equilibrium_change_m[index] =
            isostatic_equilibrium_tendency_m;
        // Isostatic relaxation is effectively complete on the nominal 5 Ma
        // maturation interval, so equilibrium target changes must not share
        // the empirical per-step relief clamp.  Clipping the combined term
        // used to leave kilometre-scale oceanic freeboard behind after a
        // crust-state transition, with no carried residual.  Only the
        // heuristic dynamic relief increment remains bounded here.
        const double equilibrium_change =
            isostatic_equilibrium_tendency_m + thermal_equilibrium_change;
        const double unbounded_dynamic_relief_change =
            cell.uplift_rate * TECTONIC_UPLIFT_RATE_RESPONSE_FRACTION +
            boundary_change;
        const double bounded_dynamic_relief_change = clamp(
            unbounded_dynamic_relief_change,
            TECTONIC_DYNAMIC_RELIEF_MINIMUM_CHANGE_M,
            TECTONIC_DYNAMIC_RELIEF_MAXIMUM_CHANGE_M
        );
        unbounded_dynamic_relief_change_m[index] =
            unbounded_dynamic_relief_change;
        bounded_dynamic_relief_change_m[index] =
            bounded_dynamic_relief_change;
        const double delta =
            equilibrium_change + bounded_dynamic_relief_change;
        tectonic_elevation_change[index] = delta;
        cell.cumulative_tectonic_elevation_change_m += delta;
    }

    for (int i = 0; i < n; ++i) {
        const std::string& error = crust_material_errors[
            static_cast<std::size_t>(i)
        ];
        if (!error.empty()) {
            throw std::runtime_error(
                "crust material shadow transition failed for cell " +
                std::to_string(i) + ": " + error
            );
        }
    }

    // Reduce in canonical cell order with wider accumulators.  Positive and
    // negative magnitudes are authoritative; the exported net is defined from
    // their rounded double values so the serialized identity is exact.
    std::array<std::array<long double, 3>, CRUST_PROCESS_REASON_COUNT>
        positive_process_delta{};
    std::array<std::array<long double, 3>, CRUST_PROCESS_REASON_COUNT>
        negative_process_delta{};
    std::array<std::array<long double, 3>, CRUST_PROCESS_REASON_COUNT>
        signed_process_delta{};
    for (int i = 0; i < n; ++i) {
        for (int reason_index = 0;
             reason_index < CRUST_PROCESS_REASON_COUNT;
             ++reason_index) {
            const CrustProcessCellDelta& cell_delta =
                process_delta_by_cell[static_cast<std::size_t>(i)][
                    static_cast<std::size_t>(reason_index)
                ];
            CrustProcessInventoryDelta& total =
                crust_motion.process_inventory_delta_by_reason[
                    static_cast<std::size_t>(reason_index)
                ];
            total.triggered_cell_count += cell_delta.triggered ? 1 : 0;
            total.changed_cell_count += cell_delta.changed ? 1 : 0;
            const std::array<double, 3> components = {
                cell_delta.crust_volume_km3,
                cell_delta.density_weighted_crust_volume,
                cell_delta.crust_age_volume_moment_km3_ma,
            };
            for (std::size_t component = 0;
                 component < components.size();
                 ++component) {
                positive_process_delta[static_cast<std::size_t>(reason_index)][
                    component
                ] += std::max(0.0, components[component]);
                negative_process_delta[static_cast<std::size_t>(reason_index)][
                    component
                ] += std::max(0.0, -components[component]);
                signed_process_delta[static_cast<std::size_t>(reason_index)][
                    component
                ] += components[component];
            }
        }
        if (aged_oceanic_flags[static_cast<std::size_t>(i)] != 0) {
            crust_motion.aged_oceanic_cell_ids.push_back(i);
        }
        if (rejuvenated_oceanic_flags[static_cast<std::size_t>(i)] != 0) {
            crust_motion.rejuvenated_oceanic_cell_ids.push_back(i);
        }
        if (subducted_oceanic_flags[static_cast<std::size_t>(i)] != 0) {
            crust_motion.subducted_oceanic_cell_ids.push_back(i);
        }
    }
    for (int reason_index = 0;
         reason_index < CRUST_PROCESS_REASON_COUNT;
         ++reason_index) {
        CrustProcessInventoryDelta& total =
            crust_motion.process_inventory_delta_by_reason[
                static_cast<std::size_t>(reason_index)
            ];
        const auto& positive = positive_process_delta[
            static_cast<std::size_t>(reason_index)
        ];
        const auto& negative = negative_process_delta[
            static_cast<std::size_t>(reason_index)
        ];
        const auto& signed_delta = signed_process_delta[
            static_cast<std::size_t>(reason_index)
        ];
        total.positive_crust_volume_km3 = static_cast<double>(positive[0]);
        total.negative_crust_volume_magnitude_km3 =
            static_cast<double>(negative[0]);
        total.positive_density_weighted_crust_volume =
            static_cast<double>(positive[1]);
        total.negative_density_weighted_crust_volume_magnitude =
            static_cast<double>(negative[1]);
        total.positive_crust_age_volume_moment_km3_ma =
            static_cast<double>(positive[2]);
        total.negative_crust_age_volume_moment_magnitude_km3_ma =
            static_cast<double>(negative[2]);
        total.crust_volume_km3 =
            total.positive_crust_volume_km3 -
            total.negative_crust_volume_magnitude_km3;
        total.density_weighted_crust_volume =
            total.positive_density_weighted_crust_volume -
            total.negative_density_weighted_crust_volume_magnitude;
        total.crust_age_volume_moment_km3_ma =
            total.positive_crust_age_volume_moment_km3_ma -
            total.negative_crust_age_volume_moment_magnitude_km3_ma;
        const std::array<double, 3> canonical_net = {
            total.crust_volume_km3,
            total.density_weighted_crust_volume,
            total.crust_age_volume_moment_km3_ma,
        };
        for (std::size_t component = 0;
             component < canonical_net.size();
             ++component) {
            const long double forward_error_bound =
                64.0L * std::numeric_limits<double>::epsilon() *
                (1.0L + positive[component] + negative[component]);
            if (std::abs(
                    signed_delta[component] -
                    static_cast<long double>(canonical_net[component])
                ) > forward_error_bound) {
                throw std::runtime_error(
                    "crust process signed inventory reduction exceeded its forward-error bound"
                );
            }
        }
    }

    finalize_crust_material_shadow_step(
        cells,
        crust_motion.transport_plan,
        crust_material_shadow
    );
    advance_crust_dry_rock_accounting_step(
        cells,
        static_cast<int>(plates.size()),
        crust_motion.transport_plan,
        crust_material_shadow.history.back(),
        crust_dry_rock_accounting
    );
    plate_motion_history.push_back(summarize_plate_motion_step(
        params,
        cells,
        plates,
        static_cast<int>(plate_motion_history.size()),
        erosion_iteration,
        "plate_motion_iteration",
        previous_plate_ids,
        step_rotation_deg,
        crust_motion,
        crust_age_change,
        crust_thickness_change,
        crust_density_change,
        tectonic_elevation_change,
        previous_local_isostatic_equilibrium_m,
        isostatic_equilibrium_change_m,
        previous_local_thermal_subsidence_target_m,
        thermal_equilibrium_change_m,
        unbounded_dynamic_relief_change_m,
        bounded_dynamic_relief_change_m
    ));
    return tectonic_elevation_change;
}

double approximate_heat_flow_mw_m2(const Params& params, const Cell& cell) {
    const bool oceanic = is_oceanic_crust_state(
        cell.crust_type,
        cell.lithology,
        cell.crust_age_ma,
        cell.crust_thickness_km,
        cell.crust_density
    );
    const double age = std::max(0.0, cell.crust_age_ma);
    const double age_heat = oceanic
        ? 45.0 + 95.0 * std::exp(-age / 60.0)
        : 38.0 + 34.0 * std::exp(-age / 1400.0);
    const double boundary_heat =
        55.0 * cell.boundary_divergent +
        30.0 * cell.boundary_convergent +
        18.0 * cell.boundary_transform +
        (cell.crust_type == 3 ? 24.0 : 0.0);
    return clamp(params.internal_heat * (age_heat + boundary_heat), 18.0, 240.0);
}

void summarize_plates(const Params& params, const std::vector<Cell>& cells, std::vector<Plate>& plates) {
    std::vector<std::array<double, 9>> crust_area(plates.size());
    std::vector<std::array<double, 7>> lithology_area(plates.size());
    for (auto& counts : crust_area) {
        counts.fill(0.0);
    }
    for (auto& counts : lithology_area) {
        counts.fill(0.0);
    }
    for (Plate& plate : plates) {
        plate.cell_count = 0;
        plate.area_km2 = 0.0;
        plate.mean_crust_age_ma = 0.0;
        plate.mean_crust_density = 0.0;
        plate.mean_crust_thickness_km = 0.0;
        plate.mean_boundary_activity = 0.0;
        plate.mean_heat_flow_mw_m2 = 0.0;
        plate.dominant_crust_type = plate.kind == 0 ? 0 : (plate.kind == 1 ? 1 : 2);
        plate.dominant_lithology = plate.kind == 0 ? 0 : 1;
    }
    for (const Cell& cell : cells) {
        if (cell.plate_id < 0 || cell.plate_id >= static_cast<int>(plates.size())) {
            continue;
        }
        Plate& plate = plates[static_cast<std::size_t>(cell.plate_id)];
        const double area = std::max(0.0, cell.area_km2);
        plate.cell_count += 1;
        plate.area_km2 += area;
        plate.mean_crust_age_ma += cell.crust_age_ma * area;
        plate.mean_crust_density += cell.crust_density * area;
        plate.mean_crust_thickness_km += cell.crust_thickness_km * area;
        plate.mean_boundary_activity += std::max(cell.boundary_convergent, std::max(cell.boundary_divergent, cell.boundary_transform)) * area;
        plate.mean_heat_flow_mw_m2 += approximate_heat_flow_mw_m2(params, cell) * area;
        if (cell.crust_type >= 0 && cell.crust_type < static_cast<int>(CRUST_NAMES.size())) {
            crust_area[static_cast<std::size_t>(cell.plate_id)][static_cast<std::size_t>(cell.crust_type)] += area;
        }
        if (cell.lithology >= 0 && cell.lithology < static_cast<int>(LITHOLOGY_NAMES.size())) {
            lithology_area[static_cast<std::size_t>(cell.plate_id)][static_cast<std::size_t>(cell.lithology)] += area;
        }
    }
    for (Plate& plate : plates) {
        const double divisor = plate.area_km2 > 0.0 ? plate.area_km2 : 1.0;
        plate.mean_crust_age_ma /= divisor;
        plate.mean_crust_density /= divisor;
        plate.mean_crust_thickness_km /= divisor;
        plate.mean_boundary_activity /= divisor;
        plate.mean_heat_flow_mw_m2 /= divisor;
        const std::size_t plate_index = static_cast<std::size_t>(plate.id);
        if (plate_index < crust_area.size()) {
            plate.dominant_crust_type = static_cast<int>(
                std::distance(crust_area[plate_index].begin(), std::max_element(crust_area[plate_index].begin(), crust_area[plate_index].end()))
            );
            plate.dominant_lithology = static_cast<int>(
                std::distance(lithology_area[plate_index].begin(), std::max_element(lithology_area[plate_index].begin(), lithology_area[plate_index].end()))
            );
        }
        if (plate.area_km2 <= 0.0) {
            plate.mean_crust_density = plate.crust_density;
            plate.mean_crust_thickness_km = plate.crust_thickness_km;
            plate.mean_crust_age_ma = crust_age_ceiling_ma(
                params, plate.kind == 0 ? 120.0 : 1600.0
            );
            plate.mean_heat_flow_mw_m2 = plate.kind == 0 ? 62.0 : 54.0;
        }
    }
}

}  // namespace magic_geo::detail
