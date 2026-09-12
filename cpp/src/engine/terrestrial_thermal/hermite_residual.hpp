#pragma once

#include "phase_segment.hpp"

namespace phase_segment_prototype {

// Bound the same-time L1 residual of the exact mathematical Hermite curve
// through the actual initial state and endpoint. No thermal/ODE/root calls.
// The curve may cross either phase threshold. The wrapper separately owns
// the physical flow tube, selected-candidate identity and acceptance budget.
// On failure, available stays false; leaves contains only completed leaves,
// while leaves_started may include one incomplete attempted leaf.
void build_hermite_residual(const Input &, Energy endpoint, double duration,
                            ResidualCertificate &out);

} // namespace phase_segment_prototype
