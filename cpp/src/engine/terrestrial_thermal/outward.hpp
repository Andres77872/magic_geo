#pragma once
#include "phase_segment.hpp"
#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace phase_segment_prototype::bounds {
using I = Interval;
inline I checked(double lo, double hi) {
    if (!(std::isfinite(lo) && std::isfinite(hi) && lo <= hi))
        throw std::runtime_error("nonfinite or reversed outward interval");
    return {lo, hi};
}
inline I point(double x) { return checked(x, x); }
inline double down(double x) { return std::nextafter(x, -std::numeric_limits<double>::infinity()); }
inline double up(double x) { return std::nextafter(x, std::numeric_limits<double>::infinity()); }
inline bool zero(I x) { return x.lower == 0 && x.upper == 0; }
inline I add(I x, I y) {
    if (zero(x))
        return y;
    if (zero(y))
        return x;
    return checked(down(x.lower + y.lower), up(x.upper + y.upper));
}
inline I neg(I x) { return {-x.upper, -x.lower}; }
inline I sub(I x, I y) {
    if (x.lower == x.upper && y.lower == y.upper && x.lower == y.lower)
        return {0, 0};
    return add(x, neg(y));
}
inline I mul(I x, I y) {
    if (zero(x) || zero(y))
        return {0, 0};
    if (x.lower == 1 && x.upper == 1)
        return y;
    if (y.lower == 1 && y.upper == 1)
        return x;
    const double a = x.lower * y.lower, b = x.lower * y.upper, c = x.upper * y.lower,
                 d = x.upper * y.upper;
    if (!(std::isfinite(a) && std::isfinite(b) && std::isfinite(c) && std::isfinite(d)))
        throw std::runtime_error("interval product overflow");
    double lo = down(std::min({a, b, c, d})), hi = up(std::max({a, b, c, d}));
    if ((x.lower >= 0 && y.lower >= 0) || (x.upper <= 0 && y.upper <= 0))
        lo = std::max(0.0, lo);
    if ((x.lower >= 0 && y.upper <= 0) || (x.upper <= 0 && y.lower >= 0))
        hi = std::min(0.0, hi);
    return checked(lo, hi);
}
inline I div(I x, I y) {
    if (y.lower <= 0 && y.upper >= 0)
        throw std::runtime_error("interval divisor includes zero");
    if (zero(x))
        return {0, 0};
    if (y.lower == 1 && y.upper == 1)
        return x;
    return mul(x, checked(down(1 / y.upper), up(1 / y.lower)));
}
inline I fourth(I x) {
    if (x.lower < 0)
        throw std::runtime_error("negative temperature interval");
    const auto square = mul(x, x);
    // Products are nonnegative even if outward zero introduces a subnormal tail.
    const auto clipped = checked(std::max(0.0, square.lower), square.upper);
    const auto result = mul(clipped, clipped);
    return checked(std::max(0.0, result.lower), result.upper);
}
inline I hull(I x, I y) { return {std::min(x.lower, y.lower), std::max(x.upper, y.upper)}; }
inline I absolute(I x) {
    if (x.lower >= 0)
        return x;
    if (x.upper <= 0)
        return neg(x);
    return {0, std::max(-x.lower, x.upper)};
}
inline double absmax(I x) { return std::max(std::abs(x.lower), std::abs(x.upper)); }
inline bool inside(I x, I outer) { return x.lower >= outer.lower && x.upper <= outer.upper; }
inline bool strict_inside(I x, I outer) { return x.lower > outer.lower && x.upper < outer.upper; }
inline I gamma() {
    // Fixed adjacent binary64 bounds around sqrt(2), independently replayable.
    const I root{0x1.6a09e667f3bccp+0, 0x1.6a09e667f3bcdp+0};
    return sub(point(1), mul(root, point(.5)));
}
} // namespace phase_segment_prototype::bounds
