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

void derive_crust_and_topography(const Params& params, const std::vector<Plate>& plates, std::vector<Cell>& cells) {
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
        Cell& cell = cells[i];
        const Plate& plate = plates[cell.plate_id];
        const double n0 = continental_noise[static_cast<std::size_t>(i)];
        const double n1 = signed_noise(params.seed, static_cast<std::uint64_t>(i), 23);
        const double n2 = signed_noise(params.seed, static_cast<std::uint64_t>(i), 31);
        const double coherent_n2 = relief_noise[static_cast<std::size_t>(i)];
        const bool continental = continental_mask[static_cast<std::size_t>(i)] != 0;
        const double conv = cell.boundary_convergent;
        const double div = cell.boundary_divergent;
        const double trans = cell.boundary_transform;
        if (continental) {
            if (conv > 0.40) {
                cell.crust_type = 5;
                cell.lithology = 6;
            } else if (div > 0.36) {
                cell.crust_type = 6;
                cell.lithology = 3;
            } else if (n1 > 0.55 && conv < 0.16 && div < 0.14) {
                cell.crust_type = 4;
                cell.lithology = 1;
            } else if (n1 < -0.45) {
                cell.crust_type = 7;
                cell.lithology = n2 > 0.0 ? 2 : 4;
            } else {
                cell.crust_type = 1;
                cell.lithology = n2 > 0.35 ? 1 : 3;
            }
        } else {
            if (conv > 0.35 && plate.kind != 0) {
                cell.crust_type = 3;
                cell.lithology = 5;
            } else if (continental_margin[static_cast<std::size_t>(i)] != 0) {
                cell.crust_type = 2;
                cell.lithology = 0;
            } else {
                cell.crust_type = 0;
                cell.lithology = 0;
            }
        }
        const bool oceanic = cell.crust_type == 0 || cell.crust_type == 2 || cell.crust_type == 3;
        const double initial_age_ceiling_ma = crust_age_ceiling_ma(
            params, oceanic ? 260.0 : 4200.0
        );
        cell.crust_age_ma = oceanic
            ? clamp(
                8.0 + 190.0 * (1.0 - div) + 25.0 * n1,
                0.0,
                initial_age_ceiling_ma
            )
            : clamp(
                450.0 + 900.0 * params.geological_age_ga * hash01(params.seed, i, 41),
                std::min(120.0, initial_age_ceiling_ma),
                initial_age_ceiling_ma
            );
        cell.crust_thickness_km = oceanic
            ? clamp(6.5 + 3.0 * conv + 1.5 * n2, 4.5, 14.0)
            : clamp(29.0 + 17.0 * conv - 8.0 * div + 5.0 * n2, 18.0, 72.0);
        cell.crust_density = oceanic ? 3.00 : 2.70 + 0.08 * hash01(params.seed, i, 43);
        const double isostatic = oceanic
            ? -3000.0
            : CONTINENTAL_ISOSTATIC_FREEBOARD_M +
                12.0 * (cell.crust_thickness_km - 30.0) -
                1800.0 * (cell.crust_density - 2.72);
        const double thermal = oceanic ? -1050.0 * std::sqrt(std::max(0.0, cell.crust_age_ma) / 190.0) : 0.0;
        const double ridge = div * (oceanic ? 2600.0 : 880.0) * relief_scale;
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
        cell.initial_thermal_subsidence_m = thermal;
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
            (1.5 * div + 8.5 * conv + (cell.crust_type == 3 ? 2.5 : 0.0));
        cell.elevation_m = cell.initial_elevation_m;
        cell.initial_plate_id = cell.plate_id;
        cell.last_crust_source_cell_id = cell.id;
        cell.initial_crust_age_ma = cell.crust_age_ma;
        cell.initial_crust_thickness_km = cell.crust_thickness_km;
        cell.initial_crust_density = cell.crust_density;
    }
}

bool is_oceanic_crust_state(int crust_type, double age_ma, double thickness_km, double density) {
    if (crust_type == 0) {
        return true;
    }
    if (crust_type != 2 && crust_type != 3) {
        return false;
    }
    return age_ma <= 320.0 && thickness_km <= 18.0 && density >= 2.84;
}

double crust_equilibrium_elevation_m(double thickness_km, double density, bool oceanic) {
    if (oceanic) {
        return -3000.0;
    }
    return CONTINENTAL_ISOSTATIC_FREEBOARD_M +
        12.0 * (thickness_km - 30.0) -
        1800.0 * (density - 2.72);
}

double oceanic_thermal_subsidence_m(double crust_age_ma, bool oceanic) {
    return oceanic ? -1050.0 * std::sqrt(std::max(0.0, crust_age_ma) / 190.0) : 0.0;
}

PlateMotionStep summarize_plate_motion_step(
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
    const std::vector<double>& tectonic_elevation_change_m
) {
    PlateMotionStep step;
    step.id = id;
    step.erosion_iteration = erosion_iteration;
    step.stage = stage;
    step.cell_count = static_cast<int>(cells.size());
    step.plate_count = static_cast<int>(plates.size());
    step.cell_plate_ids.reserve(cells.size());
    step.crust_type_by_cell.reserve(cells.size());
    step.lithology_by_cell.reserve(cells.size());
    step.crust_source_cell_ids = crust_motion.source_cell_ids;
    if (step.crust_source_cell_ids.size() != cells.size()) {
        step.crust_source_cell_ids.resize(cells.size());
        std::iota(step.crust_source_cell_ids.begin(), step.crust_source_cell_ids.end(), 0);
    }
    step.crust_transport_distance_km_by_cell = crust_motion.transport_distance_km_by_cell;
    step.crust_age_transport_change_ma_by_cell = crust_motion.age_transport_change_ma_by_cell;
    step.crust_thickness_transport_change_km_by_cell = crust_motion.thickness_transport_change_km_by_cell;
    step.crust_density_transport_change_by_cell = crust_motion.density_transport_change_by_cell;
    step.crust_age_process_change_ma_by_cell = crust_motion.age_process_change_ma_by_cell;
    step.crust_thickness_process_change_km_by_cell = crust_motion.thickness_process_change_km_by_cell;
    step.crust_density_process_change_by_cell = crust_motion.density_process_change_by_cell;
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

    std::vector<int> plate_cell_counts(plates.size(), 0);
    std::vector<double> plate_areas(plates.size(), 0.0);
    std::unordered_set<int> unique_crust_sources;
    for (std::size_t index = 0; index < cells.size(); ++index) {
        const Cell& cell = cells[index];
        step.cell_plate_ids.push_back(cell.plate_id);
        step.crust_type_by_cell.push_back(cell.crust_type);
        step.lithology_by_cell.push_back(cell.lithology);
        const int source_cell_id = step.crust_source_cell_ids[index];
        if (source_cell_id != static_cast<int>(index)) {
            step.crust_source_remap_cell_count++;
        }
        unique_crust_sources.insert(source_cell_id);
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
    step.unique_crust_source_cell_count = static_cast<int>(unique_crust_sources.size());
    step.crust_source_reuse_count = static_cast<int>(cells.size()) - step.unique_crust_source_cell_count;
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
    return step;
}

std::vector<double> advance_plate_motion_and_crust(
    const Params& params,
    int erosion_iteration,
    std::vector<Plate>& plates,
    std::vector<Cell>& cells,
    std::vector<PlateMotionStep>& plate_motion_history
) {
    const int n = static_cast<int>(cells.size());
    std::vector<int> previous_plate_ids(static_cast<std::size_t>(n));
    std::vector<int> previous_crust_types(static_cast<std::size_t>(n));
    std::vector<int> previous_lithologies(static_cast<std::size_t>(n));
    std::vector<double> previous_crust_age(static_cast<std::size_t>(n));
    std::vector<double> previous_crust_thickness(static_cast<std::size_t>(n));
    std::vector<double> previous_crust_density(static_cast<std::size_t>(n));
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
        previous_convergent[static_cast<std::size_t>(i)] = cell.boundary_convergent;
        previous_divergent[static_cast<std::size_t>(i)] = cell.boundary_divergent;
        previous_transform[static_cast<std::size_t>(i)] = cell.boundary_transform;
    }

    std::vector<double> step_rotation_deg(plates.size(), 0.0);
    std::vector<Vec3> centers;
    centers.reserve(plates.size());
    for (std::size_t index = 0; index < plates.size(); ++index) {
        Plate& plate = plates[index];
        const double rotation_deg = plate.angular_speed * params.plate_motion_scale_deg_per_step;
        const double rotation_rad = rotation_deg / DEG;
        plate.center = rotate_about_axis(plate.center, plate.axis, rotation_rad);
        plate.cumulative_rotation_deg += rotation_deg;
        step_rotation_deg[index] = rotation_deg;
        centers.push_back(plate.center);
    }
    assign_plates(centers, cells);
    classify_boundaries(params, plates, cells);

    std::vector<std::vector<int>> previous_cells_by_plate(plates.size());
    for (int i = 0; i < n; ++i) {
        const int plate_id = previous_plate_ids[static_cast<std::size_t>(i)];
        if (plate_id >= 0 && plate_id < static_cast<int>(plates.size())) {
            previous_cells_by_plate[static_cast<std::size_t>(plate_id)].push_back(i);
        }
    }
    CrustMotionDiagnostics crust_motion;
    crust_motion.source_cell_ids.assign(static_cast<std::size_t>(n), -1);
    crust_motion.transport_distance_km_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.age_transport_change_ma_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.thickness_transport_change_km_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.density_transport_change_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.age_process_change_ma_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.thickness_process_change_km_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    crust_motion.density_process_change_by_cell.assign(static_cast<std::size_t>(n), 0.0);
    std::vector<Vec3> backtraced_positions(static_cast<std::size_t>(n));
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        const std::size_t index = static_cast<std::size_t>(i);
        const int plate_id = cells[index].plate_id;
        const Plate& plate = plates[static_cast<std::size_t>(plate_id)];
        const double rotation_rad = step_rotation_deg[static_cast<std::size_t>(plate_id)] / DEG;
        backtraced_positions[index] = rotate_about_axis(
            cells[index].p, plate.axis, -rotation_rad
        );
    }
    if (!try_accelerated_remap_crust_sources(
            cells,
            backtraced_positions,
            previous_cells_by_plate,
            crust_motion.source_cell_ids
        )) {
#pragma omp parallel for schedule(static)
        for (int i = 0; i < n; ++i) {
            const std::size_t index = static_cast<std::size_t>(i);
            const int plate_id = cells[index].plate_id;
            const Vec3 backtraced_position = backtraced_positions[index];
            int best_source = i;
            double best_score = -2.0;
            const std::vector<int>& candidates =
                previous_cells_by_plate[static_cast<std::size_t>(plate_id)];
            for (int candidate : candidates) {
                const double score = dot(
                    backtraced_position,
                    cells[static_cast<std::size_t>(candidate)].p
                );
                if (score > best_score) {
                    best_score = score;
                    best_source = candidate;
                }
            }
            crust_motion.source_cell_ids[index] = best_source;
        }
    }
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        const std::size_t index = static_cast<std::size_t>(i);
        const Vec3 backtraced_position = backtraced_positions[index];
        const std::size_t source_index = static_cast<std::size_t>(
            crust_motion.source_cell_ids[index]
        );
        crust_motion.transport_distance_km_by_cell[index] =
            angular_distance(backtraced_position, cells[index].p) * params.radius_km;
        crust_motion.age_transport_change_ma_by_cell[index] =
            previous_crust_age[source_index] - previous_crust_age[index];
        crust_motion.thickness_transport_change_km_by_cell[index] =
            previous_crust_thickness[source_index] - previous_crust_thickness[index];
        crust_motion.density_transport_change_by_cell[index] =
            previous_crust_density[source_index] - previous_crust_density[index];
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
    std::vector<int> aged_oceanic_flags(static_cast<std::size_t>(n), 0);
    std::vector<int> rejuvenated_oceanic_flags(static_cast<std::size_t>(n), 0);
    std::vector<int> subducted_oceanic_flags(static_cast<std::size_t>(n), 0);
#pragma omp parallel for schedule(static)
    for (int i = 0; i < n; ++i) {
        Cell& cell = cells[static_cast<std::size_t>(i)];
        const std::size_t index = static_cast<std::size_t>(i);
        const std::size_t source_index = static_cast<std::size_t>(crust_motion.source_cell_ids[index]);
        const int old_plate_id = previous_plate_ids[index];
        const bool plate_changed = cell.plate_id != old_plate_id;
        const bool local_old_oceanic = is_oceanic_crust_state(
            previous_crust_types[index],
            previous_crust_age[index],
            previous_crust_thickness[index],
            previous_crust_density[index]
        );
        const bool old_oceanic = is_oceanic_crust_state(
            previous_crust_types[source_index],
            previous_crust_age[source_index],
            previous_crust_thickness[source_index],
            previous_crust_density[source_index]
        );
        const double conv = cell.boundary_convergent;
        const double div = cell.boundary_divergent;
        const double trans = cell.boundary_transform;

        int crust_type = previous_crust_types[source_index];
        int lithology = previous_lithologies[source_index];
        double crust_age = previous_crust_age[source_index];
        double crust_thickness = previous_crust_thickness[source_index];
        double crust_density = previous_crust_density[source_index];

        if (old_oceanic && div < 0.10 && conv < 0.10) {
            const double quiet_fraction = clamp(1.0 - std::max(div, conv) / 0.10, 0.0, 1.0);
            crust_age += params.oceanic_crust_aging_ma_per_step * quiet_fraction;
        }

        if (plate_changed && std::max(conv, div) < 0.18) {
            crust_type = 2;
            lithology = old_oceanic ? 0 : 3;
        }
        if (div >= 0.10) {
            if (old_oceanic) {
                const double rejuvenation = clamp(div * (plate_changed ? 0.72 : 0.55), 0.0, 0.85);
                crust_age *= 1.0 - rejuvenation;
                crust_thickness += (7.0 - crust_thickness) * 0.34 * div;
                crust_density += (3.0 - crust_density) * 0.24 * div;
                if (div >= 0.28) {
                    crust_type = 0;
                    lithology = 0;
                }
            } else {
                crust_thickness -= tectonic_activity * (0.45 + (plate_changed ? 0.20 : 0.0)) * div;
                crust_density += 0.004 * div;
                if (div >= 0.24) {
                    crust_type = 6;
                    lithology = 3;
                }
            }
        }
        if (conv >= 0.10) {
            if (old_oceanic) {
                crust_thickness += tectonic_activity * 0.34 * conv;
                crust_age *= 1.0 - 0.12 * conv;
                if (conv >= 0.26) {
                    crust_type = 3;
                    lithology = 5;
                }
            } else {
                crust_thickness += tectonic_activity * (0.72 + (plate_changed ? 0.38 : 0.0)) * conv;
                crust_density -= 0.006 * conv;
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
            crust_type, crust_age, crust_thickness, crust_density
        );
        crust_age = clamp(
            crust_age,
            0.0,
            crust_age_ceiling_ma(params, new_oceanic ? 320.0 : 4200.0)
        );
        crust_thickness = clamp(crust_thickness, new_oceanic ? 4.5 : 16.0, new_oceanic ? 18.0 : 76.0);
        crust_density = clamp(crust_density, 2.58, 3.08);

        crust_motion.age_process_change_ma_by_cell[index] = crust_age - previous_crust_age[source_index];
        crust_motion.thickness_process_change_km_by_cell[index] =
            crust_thickness - previous_crust_thickness[source_index];
        crust_motion.density_process_change_by_cell[index] =
            crust_density - previous_crust_density[source_index];
        crust_age_change[index] = crust_age - previous_crust_age[index];
        crust_thickness_change[index] = crust_thickness - previous_crust_thickness[index];
        crust_density_change[index] = crust_density - previous_crust_density[index];
        cell.crust_type = crust_type;
        cell.lithology = lithology;
        cell.crust_age_ma = crust_age;
        cell.crust_thickness_km = crust_thickness;
        cell.crust_density = crust_density;
        cell.last_crust_source_cell_id = static_cast<int>(source_index);
        cell.cumulative_crust_transport_distance_km += crust_motion.transport_distance_km_by_cell[index];
        if (source_index != index) {
            cell.crust_source_remap_event_count++;
        }
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

        const double old_equilibrium = crust_equilibrium_elevation_m(
            previous_crust_thickness[index], previous_crust_density[index], local_old_oceanic
        ) + oceanic_thermal_subsidence_m(previous_crust_age[index], local_old_oceanic);
        const double new_equilibrium = crust_equilibrium_elevation_m(
            crust_thickness, crust_density, new_oceanic
        ) + oceanic_thermal_subsidence_m(crust_age, new_oceanic);
        cell.volcanic_potential_index = clamp(
            0.42 * div + 0.38 * conv * (crust_type == 3 ? 1.0 : 0.35) +
            0.16 * (lithology == 5 ? 1.0 : 0.0) + 0.04 * tectonic_activity,
            0.0,
            1.0
        );
        cell.uplift_rate = params.tectonic_uplift_scale * tectonic_activity *
            (1.5 * div + 8.5 * conv + (crust_type == 3 ? 2.5 : 0.0));
        const double boundary_change =
            80.0 * (conv - previous_convergent[index]) +
            55.0 * (div - previous_divergent[index]) -
            30.0 * (trans - previous_transform[index]);
        const double equilibrium_change = 0.18 * (new_equilibrium - old_equilibrium);
        const double delta = clamp(
            cell.uplift_rate * 0.42 + equilibrium_change + boundary_change,
            -180.0,
            220.0
        );
        tectonic_elevation_change[index] = delta;
        cell.cumulative_tectonic_elevation_change_m += delta;
    }

    for (int i = 0; i < n; ++i) {
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

    plate_motion_history.push_back(summarize_plate_motion_step(
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
        tectonic_elevation_change
    ));
    return tectonic_elevation_change;
}

double approximate_heat_flow_mw_m2(const Params& params, const Cell& cell) {
    const bool oceanic = is_oceanic_crust_state(
        cell.crust_type, cell.crust_age_ma, cell.crust_thickness_km, cell.crust_density
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
