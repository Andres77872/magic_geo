#pragma once
#include "magic_geo/native.hpp"

inline magic_geo::Params geographic_foundation_case() {
    magic_geo::Params p;
    p.name="geographic_foundation_handoff";
    p.seed=424271;
    p.cell_count=128;
    p.plate_count=8;
    p.erosion_iterations=0;
    p.threads=1;
    p.float_precision=8;
    return p;
}
