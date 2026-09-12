#include "solar_calendar.hpp"
#include <iomanip>
#include <locale>
#include <sstream>

namespace magic_geo::detail {
std::string solar_calendar_json(const SolarCalendar& c) {
    std::ostringstream out;out.imbue(std::locale::classic());out<<std::setprecision(17);
    const auto quote=[&out](const std::string& s){
        out<<'"';for(char ch:s){if(ch=='"' || ch=='\\') out<<'\\';out<<ch;}out<<'"';
    };
    const auto interval=[&out](EnthalpyMeshInterval x){out<<"{\"lower\":"<<x.lower<<",\"upper\":"<<x.upper<<'}';};
    const auto& o=c.options();
    out<<"{\"schema\":\"prescribed_solar_calendar_v1\",\"calendar_origin_seconds\":0,"
          "\"original_orbital_accuracy_certified\":false,\"id\":";quote(o.id);
    out<<",\"axial_tilt_deg\":"<<o.axial_tilt_deg<<",\"orbital_eccentricity\":"<<o.orbital_eccentricity
       <<",\"stellar_luminosity\":"<<o.stellar_luminosity<<",\"year_duration_seconds\":"<<o.year_duration_seconds
       <<",\"top_of_atmosphere_albedo\":"<<o.top_of_atmosphere_albedo<<",\"thermal_error_budget_j\":"<<o.thermal_error_budget_j
       <<",\"forcing_refinement_level\":"<<o.forcing_refinement_level<<",\"maximum_windows\":"<<o.maximum_windows
       <<",\"maximum_stored_forcing_values\":"<<o.maximum_stored_forcing_values
       <<",\"clock_quantum_seconds\":"<<c.clock_quantum_seconds()<<",\"year_ticks\":"<<c.year_ticks()<<",\"latitudes_rad\":[";
    for(std::size_t i=0;i<c.latitudes_rad().size();++i){if(i)out<<',';out<<c.latitudes_rad()[i];}
    out<<"],\"windows\":[";
    for(std::size_t i=0;i<c.windows().size();++i){
        if(i)out<<',';
        const auto& w=c.windows()[i];const auto& a=w.orbital;
        out<<"{\"index\":"<<i<<",\"month_index\":"<<a.month_index
           <<",\"duration_fraction_of_year\":"<<a.duration_fraction_of_year<<",\"declination_rad\":"<<a.declination_rad
           <<",\"inverse_square_distance_factor\":"<<a.inverse_square_distance_factor
           <<",\"mean_anomaly_begin_rad\":"<<a.mean_anomaly_begin_rad<<",\"mean_anomaly_end_rad\":"<<a.mean_anomaly_end_rad
           <<",\"end_fraction_of_year\":"<<a.end_fraction_of_year<<",\"begin_tick\":"<<w.begin_tick<<",\"end_tick\":"<<w.end_tick
           <<",\"forcing_id\":";quote(w.forcing.id);
        out<<",\"begin_seconds\":"<<w.forcing.begin_seconds<<",\"end_seconds\":"<<w.forcing.end_seconds
           <<",\"duration_seconds\":"<<w.duration_seconds<<",\"thermal_error_allowance_j\":"<<w.thermal_error_allowance_j
           <<",\"endpoint_rounding_seconds\":";interval(w.endpoint_rounding_seconds);
        out<<",\"duration_change_seconds\":";interval(w.duration_change_seconds);
        out<<",\"absorbed_shortwave_w_m2\":[";
        for(std::size_t k=0;k<w.forcing.absorbed_shortwave_w_m2.size();++k){if(k)out<<',';out<<w.forcing.absorbed_shortwave_w_m2[k];}
        out<<"],\"signed_fluence_change_j_m2\":[";
        for(std::size_t k=0;k<w.fluence_change_j_m2.size();++k){if(k)out<<',';interval(w.fluence_change_j_m2[k]);}
        out<<"]}";
    }
    out<<"]}";return out.str();
}
} // namespace magic_geo::detail
