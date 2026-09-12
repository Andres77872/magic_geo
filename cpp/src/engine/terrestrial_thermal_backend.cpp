#include <cfloat>
#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 && LDBL_MAX_EXP >= 16384
#include "terrestrial_thermal/thermal_stage.cpp"
#else
#include "terrestrial_thermal/thermal_stage.hpp"
namespace higher_order_thermal_prototype {
Receipt solve_stage(const StageInput &) {
    Receipt r;
    r.failure_code = "capability_unavailable";
    r.detail = "extended long-double calorimeter backend unavailable";
    return r;
}
} // namespace higher_order_thermal_prototype
#endif
