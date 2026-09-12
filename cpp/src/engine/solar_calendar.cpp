#include "solar_calendar.hpp"
#include "finalized_enthalpy_context.hpp"
#include "terrestrial_thermal/outward.hpp"

#include <bit>
#include <cfenv>
#include <cmath>
#include <limits>

namespace magic_geo::detail {
namespace {
namespace b = phase_segment_prototype::bounds;
void need(bool ok,const char* detail) {
    if(!ok) throw TerrestrialWaterError("solar_calendar_refusal",detail);
}
struct Product {
    std::uint64_t lo=0,hi=0;
    bool bit(unsigned n) const {return n<64 ? ((lo>>n)&1) : n<128 ? ((hi>>(n-64))&1) : false;}
    bool below(unsigned n) const {
        if(n>=128) return hi || lo;
        if(n>=64) return lo || (n>64 && (hi & ((std::uint64_t{1}<<(n-64))-1)));
        return n && (lo & ((std::uint64_t{1}<<n)-1));
    }
};
Product multiply(std::uint64_t x,std::uint64_t y) {
    Product p;
    for(unsigned i=0;i<53;++i) if((y>>i)&1) {
        const auto old=p.lo;p.lo+=x<<i;p.hi+=(i ? x>>(64-i) : 0)+(p.lo<old);
    }
    return p;
}
}

std::uint64_t round_solar_calendar_tick(double fraction,std::uint64_t count) {
    need(std::isfinite(fraction) && fraction>=0 && fraction<=1 && count>0 && count<=9007199254740992ULL,
         "fraction/tick count outside canonical calendar domain");
    if(fraction==0) return 0;
    const auto bits=std::bit_cast<std::uint64_t>(fraction);
    const unsigned exponent=(bits>>52)&2047;
    const auto mantissa=(bits&0xfffffffffffffULL)|(exponent ? 0x10000000000000ULL : 0);
    const unsigned shift=exponent ? 1075-exponent : 1074;
    const auto p=multiply(count,mantissa);
    std::uint64_t q=shift<64 ? (p.lo>>shift)|(p.hi<<(64-shift)) : shift<128 ? p.hi>>(shift-64) : 0;
    if(p.bit(shift-1) && (p.below(shift-1) || (q&1))) ++q;
    need(q<=count,"rounded calendar tick exceeds year");
    return q;
}

struct SolarCalendar::Data {
    SolarCalendarOptions options;
    std::vector<double> latitudes;
    std::vector<SolarCalendarWindow> windows;
    double quantum=0;
    std::uint64_t ticks=0;
};
SolarCalendar::SolarCalendar(std::shared_ptr<const Data> d):data_(std::move(d)){}
const SolarCalendarOptions& SolarCalendar::options()const{return data_->options;}
const std::vector<double>& SolarCalendar::latitudes_rad()const{return data_->latitudes;}
const std::vector<SolarCalendarWindow>& SolarCalendar::windows()const{return data_->windows;}
double SolarCalendar::clock_quantum_seconds()const{return data_->quantum;}
std::uint64_t SolarCalendar::year_ticks()const{return data_->ticks;}
void SolarCalendar::require_owner_capacity(const EnthalpyMeshOwnerLimits& limits)const {
    need(windows().size()<=limits.max_committed_intervals && windows().size()<=limits.max_prepare_attempts &&
         latitudes_rad().size()<=limits.max_cells &&
         windows().size()<=limits.max_stored_forcing_values/latitudes_rad().size(),
         "owner cannot retain or prepare the complete forcing calendar");
    for(const auto& w:windows())
        need(w.forcing.id.size()<=limits.max_identifier_bytes,"owner forcing identifier capacity");
}
SolarCalendar build_solar_calendar(const std::vector<double>& latitudes,SolarCalendarOptions o) {
    need(std::numeric_limits<double>::is_iec559 && std::numeric_limits<double>::digits==53 &&
         std::fegetround()==FE_TONEAREST,"binary64 round-to-nearest arithmetic required");
    volatile double tiny=std::numeric_limits<double>::denorm_min(),one=1;
    need(tiny*one>0,"gradual underflow required");
    need(!latitudes.empty() && latitudes.size()<=4096,"bounded complete latitude coverage required");
    for(double lat:latitudes) need(std::isfinite(lat) && std::abs(lat)<=std::numbers::pi/2,"invalid latitude");
    need(!o.id.empty() && o.id.size()<=72,"calendar ID length");
    for(unsigned char c:o.id) need(c>=33 && c<=126,"calendar ID must be visible ASCII");
    need(std::isfinite(o.year_duration_seconds) && o.year_duration_seconds>0 &&
         std::isfinite(o.top_of_atmosphere_albedo) && o.top_of_atmosphere_albedo>=0 && o.top_of_atmosphere_albedo<=1 &&
         std::isfinite(o.thermal_error_budget_j) && o.thermal_error_budget_j>0,"invalid year, albedo or whole-year thermal budget");
    need(o.maximum_windows>0 && o.maximum_windows<=2048 && o.maximum_stored_forcing_values>0 &&
         o.maximum_stored_forcing_values<=2097152 && o.forcing_refinement_level>=0 &&
         o.forcing_refinement_level<=SolarOrbitForcing::maximum_integration_refinement_level,"calendar work policy");
    // Sum ceil(angular span / limit) <= angular samples + time subdivisions.
    // Conservative reservation precedes the orbital object's allocations.
    const auto reserved=(SolarOrbitForcing::minimum_samples_per_orbit+360)*(std::size_t{1}<<o.forcing_refinement_level);
    need(reserved<=o.maximum_windows && reserved<=o.maximum_stored_forcing_values/latitudes.size(),
         "complete orbital reservation exceeds calendar limits");
    auto d=std::make_shared<SolarCalendar::Data>();d->options=o;d->latitudes=latitudes;
    d->quantum=std::nextafter(o.year_duration_seconds,std::numeric_limits<double>::infinity())-o.year_duration_seconds;
    const double ticks=o.year_duration_seconds/d->quantum;
    need(std::isfinite(d->quantum) && d->quantum>0 && std::isfinite(ticks) && ticks>=1 &&
         ticks<=9007199254740992.0 && ticks==std::floor(ticks),"year is not representable on a finite binary64 endpoint lattice");
    d->ticks=static_cast<std::uint64_t>(ticks);
    need(static_cast<double>(d->ticks)*d->quantum==o.year_duration_seconds,"year endpoint mismatch");
    const SolarOrbitForcing orbit(o.axial_tilt_deg,o.orbital_eccentricity,o.stellar_luminosity,o.forcing_refinement_level);
    need(orbit.integration_intervals().size()<=reserved,"orbital interval reservation exceeded");
    d->windows.reserve(orbit.integration_intervals().size());
    std::uint64_t previous_tick=0;double previous_fraction=0;
    for(std::size_t i=0;i<orbit.integration_intervals().size();++i) {
        SolarCalendarWindow w;w.orbital=orbit.integration_intervals()[i];
        need(w.orbital.end_fraction_of_year>previous_fraction,"nonincreasing original orbital endpoint coordinate");
        w.begin_tick=previous_tick;w.end_tick=round_solar_calendar_tick(w.orbital.end_fraction_of_year,d->ticks);
        need(w.end_tick>w.begin_tick,"orbital window collapses on the year endpoint lattice");
        w.forcing.id=o.id+":"+std::to_string(i);
        w.forcing.begin_seconds=static_cast<double>(w.begin_tick)*d->quantum;
        w.forcing.end_seconds=static_cast<double>(w.end_tick)*d->quantum;
        w.duration_seconds=static_cast<double>(w.end_tick-w.begin_tick)*d->quantum;
        need(w.forcing.end_seconds-w.forcing.begin_seconds==w.duration_seconds &&
             w.forcing.begin_seconds+w.duration_seconds==w.forcing.end_seconds,"calendar duration does not close");
        w.endpoint_rounding_seconds=b::sub(b::point(w.forcing.end_seconds),b::mul(b::point(o.year_duration_seconds),b::point(w.orbital.end_fraction_of_year)));
        w.duration_change_seconds=b::sub(b::point(w.duration_seconds),b::mul(b::point(o.year_duration_seconds),b::point(w.orbital.duration_fraction_of_year)));
        w.thermal_error_allowance_j=b::mul(b::point(o.thermal_error_budget_j),
            b::div(b::point(static_cast<double>(w.end_tick-w.begin_tick)),b::point(static_cast<double>(d->ticks)))).lower;
        need(std::isfinite(w.thermal_error_allowance_j) && w.thermal_error_allowance_j>0,"thermal share is not positive and representable");
        w.forcing.absorbed_shortwave_w_m2.reserve(latitudes.size());
        w.fluence_change_j_m2.reserve(latitudes.size());
        for(double lat:latitudes) {
            const double incident=orbit.interval_mean_insolation_w_m2(lat,i);
            const double flux=(1-o.top_of_atmosphere_albedo)*incident;
            need(std::isfinite(flux) && flux>=0,"absorbed shortwave is not representable");
            need(!(incident>0 && o.top_of_atmosphere_albedo<1 && flux==0),"positive absorbed shortwave underflows to zero");
            w.fluence_change_j_m2.push_back(b::mul(b::point(flux),w.duration_change_seconds));
            w.forcing.absorbed_shortwave_w_m2.push_back(flux);
        }
        previous_tick=w.end_tick;previous_fraction=w.orbital.end_fraction_of_year;d->windows.push_back(std::move(w));
    }
    need(previous_tick==d->ticks && previous_fraction==1,"calendar does not cover the exact declared year");
    return SolarCalendar(std::move(d));
}
SolarCalendar build_finalized_solar_calendar(const FinalizedEnthalpyContext& context,SolarCalendarOptions options) {
    need(std::bit_cast<std::uint64_t>(options.year_duration_seconds)==
         std::bit_cast<std::uint64_t>(context.properties().year_duration_seconds),"calendar/context year mismatch");
    std::vector<double> latitudes;latitudes.reserve(context.surface().cells().size());
    for(const auto& cell:context.surface().cells()) latitudes.push_back(cell.lat);
    return build_solar_calendar(latitudes,std::move(options));
}
} // namespace magic_geo::detail
