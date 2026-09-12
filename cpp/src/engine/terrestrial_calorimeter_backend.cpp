#include <cfloat>
// The production copy adds a clock-free mass-event entry while preserving the
// archived combined advance contract. Platforms without the required arithmetic
// build ordinary native generation and expose an unavailable interval capability.
#if !defined(MAGIC_GEO_TERRESTRIAL_DISABLE_CALORIMETER) && LDBL_MANT_DIG >= 64 && LDBL_MAX_EXP >= 16384
#include "terrestrial_calorimeter/cryosphere_enthalpy.cpp"
#endif
