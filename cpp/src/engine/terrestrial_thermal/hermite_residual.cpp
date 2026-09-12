#include "hermite_residual.hpp"
#include "outward.hpp"

#include <algorithm>
#include <array>
#include <cfenv>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <utility>

namespace phase_segment_prototype {
namespace {
namespace b = bounds;
namespace t = higher_order_thermal_prototype;
using I = Interval;
constexpr int maximum_degree = 12;
constexpr int maximum_leaves = 64;

void need(bool condition, const char *message) {
  if (!condition)
    throw std::runtime_error(message);
}

void arithmetic_capability() {
  need(std::numeric_limits<double>::is_iec559 &&
           std::numeric_limits<double>::digits == 53 &&
           std::fegetround() == FE_TONEAREST,
       "Hermite certificate requires nearest binary64 arithmetic");
  volatile double normal = std::numeric_limits<double>::min();
  volatile double subnormal = std::numeric_limits<double>::denorm_min();
  volatile double tenth = 0.1;
  volatile double one = 1.0;
  volatile double underflowed = normal * tenth;
  volatile double preserved = subnormal * one;
  need(underflowed > 0 && preserved > 0,
       "Hermite certificate requires gradual arithmetic without FTZ/DAZ");
}

struct Polynomial {
  int degree = 0;
  std::array<I, maximum_degree + 1> coefficient{};
};

Polynomial constant(I value) {
  Polynomial result;
  result.coefficient[0] = b::checked(value.lower, value.upper);
  return result;
}

// All arguments are <=12. These exact integers and their products fit well
// inside binary64's exact integer range; their ratios are enclosed outward.
constexpr std::uint64_t choose(int n, int k) {
  if (k < 0 || k > n)
    return 0;
  k = std::min(k, n - k);
  std::uint64_t value = 1;
  for (int j = 1; j <= k; ++j)
    value = value * static_cast<std::uint64_t>(n - k + j) /
            static_cast<std::uint64_t>(j);
  return value;
}

I ratio(std::uint64_t numerator, std::uint64_t denominator) {
  need(denominator > 0, "zero Bernstein combinatorial denominator");
  return b::div(b::point(static_cast<double>(numerator)),
                b::point(static_cast<double>(denominator)));
}

Polynomial elevate(const Polynomial &value, int degree) {
  need(value.degree >= 0 && value.degree <= degree && degree <= maximum_degree,
       "Bernstein elevation degree cap");
  if (value.degree == degree)
    return value;
  Polynomial result;
  result.degree = degree;
  for (int k = 0; k <= degree; ++k) {
    I sum{0, 0};
    const int begin = std::max(0, k - (degree - value.degree));
    const int end = std::min(value.degree, k);
    for (int i = begin; i <= end; ++i) {
      const auto numerator =
          choose(value.degree, i) * choose(degree - value.degree, k - i);
      const I weight = ratio(numerator, choose(degree, k));
      sum = b::add(sum, b::mul(weight, value.coefficient[i]));
    }
    result.coefficient[k] = sum;
  }
  return result;
}

Polynomial add(const Polynomial &left, const Polynomial &right) {
  const int degree = std::max(left.degree, right.degree);
  const Polynomial a = elevate(left, degree), c = elevate(right, degree);
  Polynomial result;
  result.degree = degree;
  for (int i = 0; i <= degree; ++i)
    result.coefficient[i] = b::add(a.coefficient[i], c.coefficient[i]);
  return result;
}

Polynomial scale(const Polynomial &value, I factor) {
  Polynomial result;
  result.degree = value.degree;
  for (int i = 0; i <= result.degree; ++i)
    result.coefficient[i] = b::mul(value.coefficient[i], factor);
  return result;
}

Polynomial subtract(const Polynomial &left, const Polynomial &right) {
  return add(left, scale(right, b::point(-1)));
}

Polynomial product(const Polynomial &left, const Polynomial &right) {
  const int degree = left.degree + right.degree;
  need(left.degree >= 0 && right.degree >= 0 && degree <= maximum_degree,
       "Bernstein product degree cap");
  Polynomial result;
  result.degree = degree;
  for (int k = 0; k <= degree; ++k) {
    I sum{0, 0};
    const int begin = std::max(0, k - right.degree);
    const int end = std::min(left.degree, k);
    for (int i = begin; i <= end; ++i) {
      const int j = k - i;
      const auto numerator = choose(left.degree, i) * choose(right.degree, j);
      const I weight = ratio(numerator, choose(degree, k));
      const I term =
          b::mul(b::mul(left.coefficient[i], right.coefficient[j]), weight);
      sum = b::add(sum, term);
    }
    result.coefficient[k] = sum;
  }
  return result;
}

Polynomial fourth(const Polynomial &value) {
  // These are signed polynomial coefficients, not pointwise temperatures.
  // No coefficient is clipped merely because the represented function's
  // fourth power is nonnegative on its already proved physical domain.
  const Polynomial square = product(value, value);
  return product(square, square);
}

Polynomial derivative(const Polynomial &value) {
  if (value.degree == 0)
    return constant({0, 0});
  Polynomial result;
  result.degree = value.degree - 1;
  for (int i = 0; i <= result.degree; ++i)
    result.coefficient[i] =
        b::mul(b::point(static_cast<double>(value.degree)),
               b::sub(value.coefficient[i + 1], value.coefficient[i]));
  return result;
}

I range(const Polynomial &value) {
  I result = value.coefficient[0];
  for (int i = 1; i <= value.degree; ++i)
    result = b::hull(result, value.coefficient[i]);
  return b::checked(result.lower, result.upper);
}

I absolute_integral(const Polynomial &value) {
  I sum{0, 0};
  for (int i = 0; i <= value.degree; ++i)
    sum = b::add(sum, b::point(b::absmax(value.coefficient[i])));
  const I mean = b::div(sum, b::point(static_cast<double>(value.degree + 1)));
  return b::checked(0, mean.upper);
}

struct Curve {
  Polynomial surface;
  Polynomial air;
};

std::pair<Polynomial, Polynomial> split(const Polynomial &value) {
  need(value.degree == 3, "only cubic Hermite subdivision is supported");
  Polynomial left, right;
  left.degree = right.degree = 3;
  auto temporary = value.coefficient;
  left.coefficient[0] = temporary[0];
  right.coefficient[3] = temporary[3];
  for (int level = 1; level <= 3; ++level) {
    for (int i = 0; i <= 3 - level; ++i)
      temporary[i] =
          b::mul(b::add(temporary[i], temporary[i + 1]), b::point(0.5));
    left.coefficient[level] = temporary[0];
    right.coefficient[3 - level] = temporary[3 - level];
  }
  return {left, right};
}

struct Parameters {
  I tf, cb, ca, a, k, absorbed_shortwave, boundary, solid_capacity,
      liquid_capacity;
  bool dry = false;
  bool air = false;
};

Parameters parameters(const Input &in, Energy endpoint, double duration) {
  arithmetic_capability();
  need(in.goal == Goal::fixed_duration &&
           in.endpoint_certificate == EndpointCertificate::hermite_residual,
       "Hermite certificate requires opt-in fixed-duration mode");
  const int leaves = in.reconstruction_leaves;
  need(leaves > 0 && leaves <= maximum_leaves && (leaves & (leaves - 1)) == 0,
       "Hermite leaf count must be a power of two from 1 through 64");
  need(!in.is_water && !in.is_lake, "Hermite terrestrial column cannot be wet");
  for (double value :
       {in.water.freezing_temperature_k, in.water.solid_heat_capacity_j_kg_k,
        in.water.liquid_heat_capacity_j_kg_k, in.water.latent_heat_j_kg,
        in.column.area_m2, in.column.dry_heat_capacity_j_m2_k, duration})
    need(std::isfinite(value) && value > 0,
         "nonpositive or nonfinite Hermite physical input");
  for (double value : {in.water_mass_kg_m2, in.incident_shortwave_w_m2,
                       in.column.atmospheric_heat_capacity_j_m2_k,
                       in.column.sensible_exchange_w_m2_k})
    need(std::isfinite(value) && value >= 0,
         "negative or nonfinite Hermite physical input");
  for (double value : {in.column.atmospheric_longwave_absorptivity,
                       in.column.surface_shortwave_albedo})
    need(std::isfinite(value) && value >= 0 && value <= 1,
         "Hermite optical coefficient outside physical range");
  for (double value :
       {in.initial.surface_enthalpy_j_m2, in.initial.atmospheric_energy_j_m2,
        endpoint.surface_enthalpy_j_m2, endpoint.atmospheric_energy_j_m2})
    need(std::isfinite(value), "nonfinite Hermite endpoint");
  need(duration == in.maximum_duration_seconds,
       "Hermite fixed duration differs from request");
  Parameters p;
  p.tf = b::point(in.water.freezing_temperature_k);
  p.cb = b::point(in.column.dry_heat_capacity_j_m2_k);
  p.ca = b::point(in.column.atmospheric_heat_capacity_j_m2_k);
  p.a = b::point(in.column.atmospheric_longwave_absorptivity);
  p.k = b::point(in.column.sensible_exchange_w_m2_k);
  p.absorbed_shortwave =
      b::mul(b::sub(b::point(1), b::point(in.column.surface_shortwave_albedo)),
             b::point(in.incident_shortwave_w_m2));
  p.dry = in.water_mass_kg_m2 == 0;
  p.air = in.column.atmospheric_heat_capacity_j_m2_k > 0;
  need(p.air || (in.initial.atmospheric_energy_j_m2 == 0 &&
                 endpoint.atmospheric_energy_j_m2 == 0 && b::zero(p.a) &&
                 b::zero(p.k)),
       "Hermite airless state and coefficients must be zero");
  const I water = b::point(in.water_mass_kg_m2);
  p.boundary = b::mul(water, b::point(in.water.latent_heat_j_kg));
  p.solid_capacity = b::add(
      p.cb, b::mul(water, b::point(in.water.solid_heat_capacity_j_kg_k)));
  p.liquid_capacity = b::add(
      p.cb, b::mul(water, b::point(in.water.liquid_heat_capacity_j_kg_k)));
  need(p.solid_capacity.lower > 0 && p.liquid_capacity.lower > 0,
       "Hermite capacity positivity unproved");
  return p;
}

I surface_temperature(const Parameters &p, I enthalpy) {
  if (p.dry)
    return b::add(p.tf, b::div(enthalpy, p.cb));
  // This continuous global identity encloses both phase thresholds without
  // comparing a raw value against a rounded W*Lf or changing the state.
  const I cold{std::min(enthalpy.lower, 0.0), std::min(enthalpy.upper, 0.0)};
  const I above = b::sub(enthalpy, p.boundary);
  const I warm{std::max(above.lower, 0.0), std::max(above.upper, 0.0)};
  return b::add(p.tf, b::add(b::div(cold, p.solid_capacity),
                             b::div(warm, p.liquid_capacity)));
}

I air_temperature(const Parameters &p, I energy) {
  if (!p.air) {
    need(b::zero(energy), "nonzero airless Hermite curve");
    return {0, 0};
  }
  return b::add(p.tf, b::div(energy, p.ca));
}

void physical_range(const Parameters &p, StateBox box) {
  need(surface_temperature(p, box.surface_enthalpy_j_m2).lower >= 0 &&
           air_temperature(p, box.atmospheric_energy_j_m2).lower >= 0,
       "Hermite whole-curve physical temperature domain unproved");
}

FluxBox ideal_flux(const Parameters &p, I enthalpy, I energy) {
  const I ts = surface_temperature(p, enthalpy),
          ta = air_temperature(p, energy);
  need(ts.lower >= 0 && ta.lower >= 0,
       "Hermite ideal flux physical domain unproved");
  const I sigma = b::point(t::sigma_w_m2_k4);
  const I surface_longwave = b::mul(sigma, b::fourth(ts));
  const I air_longwave = b::mul(p.a, b::mul(sigma, b::fourth(ta)));
  const I sensible = b::mul(p.k, b::sub(ts, ta));
  return {b::sub(b::sub(b::add(p.absorbed_shortwave, air_longwave),
                        surface_longwave),
                 sensible),
          p.air ? b::add(b::sub(b::mul(p.a, surface_longwave),
                                b::mul(b::point(2), air_longwave)),
                         sensible)
                : I{0, 0}};
}

FluxBox global_field(const Parameters &p, StateBox box) {
  // The global positive-temperature law is monotone in these opposite
  // corners: Fs decreases with H/increases with Ea; Fa does the converse.
  const auto lower = ideal_flux(p, b::point(box.surface_enthalpy_j_m2.upper),
                                b::point(box.atmospheric_energy_j_m2.lower));
  const auto upper = ideal_flux(p, b::point(box.surface_enthalpy_j_m2.lower),
                                b::point(box.atmospheric_energy_j_m2.upper));
  return {
      b::checked(lower.surface_net_w_m2.lower, upper.surface_net_w_m2.upper),
      b::checked(upper.atmospheric_net_w_m2.lower,
                 lower.atmospheric_net_w_m2.upper)};
}

Polynomial hermite(double initial, double endpoint, I first_flux, I final_flux,
                   double duration) {
  Polynomial result;
  result.degree = 3;
  result.coefficient[0] = b::point(initial);
  result.coefficient[1] =
      b::add(b::point(initial),
             b::div(b::mul(b::point(duration), first_flux), b::point(3)));
  result.coefficient[2] =
      b::sub(b::point(endpoint),
             b::div(b::mul(b::point(duration), final_flux), b::point(3)));
  result.coefficient[3] = b::point(endpoint);
  return result;
}

enum class LeafBranch { dry, solid, mixed, liquid, global };

LeafBranch branch(const Parameters &p, I enthalpy) {
  if (p.dry)
    return LeafBranch::dry;
  if (enthalpy.upper <= 0)
    return LeafBranch::solid;
  if (enthalpy.lower >= 0 && enthalpy.upper <= p.boundary.lower)
    return LeafBranch::mixed;
  if (enthalpy.lower >= p.boundary.upper)
    return LeafBranch::liquid;
  return LeafBranch::global;
}

Polynomial branch_temperature(const Parameters &p, const Polynomial &enthalpy,
                              LeafBranch phase) {
  switch (phase) {
  case LeafBranch::dry:
    return add(constant(p.tf), scale(enthalpy, b::div(b::point(1), p.cb)));
  case LeafBranch::solid:
    return add(constant(p.tf),
               scale(enthalpy, b::div(b::point(1), p.solid_capacity)));
  case LeafBranch::mixed:
    return constant(p.tf);
  case LeafBranch::liquid:
    return add(constant(p.tf), scale(subtract(enthalpy, constant(p.boundary)),
                                     b::div(b::point(1), p.liquid_capacity)));
  case LeafBranch::global:
    break;
  }
  throw std::runtime_error("unproved Hermite polynomial phase branch");
}

std::pair<Polynomial, Polynomial>
polynomial_field(const Parameters &p, const Curve &curve, LeafBranch phase) {
  const Polynomial ts = branch_temperature(p, curve.surface, phase);
  const Polynomial ta =
      p.air ? add(constant(p.tf), scale(curve.air, b::div(b::point(1), p.ca)))
            : constant({0, 0});
  const Polynomial surface_longwave =
      scale(fourth(ts), b::point(t::sigma_w_m2_k4));
  const Polynomial air_longwave =
      scale(fourth(ta), b::mul(p.a, b::point(t::sigma_w_m2_k4)));
  const Polynomial sensible = scale(subtract(ts, ta), p.k);
  const Polynomial surface =
      subtract(subtract(add(constant(p.absorbed_shortwave), air_longwave),
                        surface_longwave),
               sensible);
  const Polynomial air = p.air ? add(subtract(scale(surface_longwave, p.a),
                                              scale(air_longwave, b::point(2))),
                                     sensible)
                               : constant({0, 0});
  return {surface, air};
}

ResidualLeaf residual_leaf(const Parameters &p, const Curve &curve, int index,
                           I leaf_duration) {
  ResidualLeaf result;
  result.index = index;
  result.trace_range = {range(curve.surface), range(curve.air)};
  physical_range(p, result.trace_range);
  const auto phase = branch(p, result.trace_range.surface_enthalpy_j_m2);
  const Polynomial ds = derivative(curve.surface), da = derivative(curve.air);
  if (phase != LeafBranch::global) {
    const auto field = polynomial_field(p, curve, phase);
    result.polynomial = true;
    result.surface_residual_integral_j_m2 =
        absolute_integral(subtract(ds, scale(field.first, leaf_duration)));
    result.air_residual_integral_j_m2 =
        absolute_integral(subtract(da, scale(field.second, leaf_duration)));
  } else {
    const auto field = global_field(p, result.trace_range);
    const I surface =
        b::sub(range(ds), b::mul(leaf_duration, field.surface_net_w_m2));
    const I air =
        b::sub(range(da), b::mul(leaf_duration, field.atmospheric_net_w_m2));
    result.surface_residual_integral_j_m2 = b::checked(0, b::absmax(surface));
    result.air_residual_integral_j_m2 = b::checked(0, b::absmax(air));
  }
  return result;
}
} // namespace

void build_hermite_residual(const Input &in, Energy endpoint, double duration,
                            ResidualCertificate &out) {
  out = ResidualCertificate{};
  out.started = true;
  const Parameters p = parameters(in, endpoint, duration);
  const auto first = ideal_flux(p, b::point(in.initial.surface_enthalpy_j_m2),
                                b::point(in.initial.atmospheric_energy_j_m2));
  const auto last = ideal_flux(p, b::point(endpoint.surface_enthalpy_j_m2),
                               b::point(endpoint.atmospheric_energy_j_m2));
  std::array<Curve, maximum_leaves> curves;
  curves[0] = {
      hermite(in.initial.surface_enthalpy_j_m2, endpoint.surface_enthalpy_j_m2,
              first.surface_net_w_m2, last.surface_net_w_m2, duration),
      hermite(in.initial.atmospheric_energy_j_m2,
              endpoint.atmospheric_energy_j_m2, first.atmospheric_net_w_m2,
              last.atmospheric_net_w_m2, duration)};
  // A fixed dyadic subdivision, not an adaptive phase partition or a root
  // search. Its mathematical leaf endpoints need not be physical clock ticks.
  for (int count = 1; count < in.reconstruction_leaves; count *= 2) {
    for (int i = count - 1; i >= 0; --i) {
      const auto surface = split(curves[i].surface), air = split(curves[i].air);
      curves[2 * i] = {surface.first, air.first};
      curves[2 * i + 1] = {surface.second, air.second};
    }
  }
  const I leaf_duration =
      b::div(b::point(duration),
             b::point(static_cast<double>(in.reconstruction_leaves)));
  out.leaves.reserve(static_cast<std::size_t>(in.reconstruction_leaves));
  for (int i = 0; i < in.reconstruction_leaves; ++i) {
    ++out.leaves_started;
    const auto leaf = residual_leaf(p, curves[i], i, leaf_duration);
    // Publish only completed leaf diagnostics. A failed leaf may be
    // counted as started without a misleading default-zero leaf record.
    out.leaves.push_back(leaf);
    out.surface_residual_integral_j_m2 =
        b::add(out.surface_residual_integral_j_m2,
               leaf.surface_residual_integral_j_m2);
    out.air_residual_integral_j_m2 =
        b::add(out.air_residual_integral_j_m2, leaf.air_residual_integral_j_m2);
  }
  out.endpoint_l1_error_j_m2 = b::add(out.surface_residual_integral_j_m2,
                                      out.air_residual_integral_j_m2);
  out.available = true;
}

} // namespace phase_segment_prototype
