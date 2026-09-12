#include "seasonal_liquid_routing.hpp"

#include <algorithm>
#include <bit>
#include <cfenv>
#include <cmath>
#include <functional>
#include <iomanip>
#include <limits>
#include <locale>
#include <queue>
#include <set>
#include <sstream>
#include <utility>

namespace magic_geo::detail {
namespace {
using I = SeasonalLiquidInterval;
void need(bool ok, const char* code, const std::string& detail) {
    if (!ok) throw SeasonalLiquidRoutingError(code, detail);
}
bool finite(double x) { return std::isfinite(x); }
bool same(double a, double b) {
    return std::bit_cast<std::uint64_t>(a) == std::bit_cast<std::uint64_t>(b);
}
I checked(double lo, double hi) {
    need(finite(lo) && finite(hi) && lo <= hi, "arithmetic_refusal", "unrepresentable outward bound");
    return {lo, hi};
}
I point(double x) { return checked(x, x); }
double down(double x) { return std::nextafter(x, -std::numeric_limits<double>::infinity()); }
double up(double x) { return std::nextafter(x, std::numeric_limits<double>::infinity()); }
bool zero(I x) { return x.lower == 0 && x.upper == 0; }
I add(I x, I y) {
    if (zero(x)) return y;
    if (zero(y)) return x;
    return checked(down(x.lower+y.lower), up(x.upper+y.upper));
}
I difference(I x, I y) {
    if (x.lower==x.upper && y.lower==y.upper && x.lower==y.lower) return {};
    return add(x, {-y.upper,-y.lower});
}
// These operations are used only with nonnegative operands.
I multiply(I x, I y) {
    need(x.lower>=0 && y.lower>=0,"arithmetic_refusal","negative product operand");
    if (zero(x) || zero(y)) return {};
    if (x.lower==1 && x.upper==1) return y;
    if (y.lower==1 && y.upper==1) return x;
    const double lo=x.lower*y.lower, hi=x.upper*y.upper;
    need(finite(lo) && finite(hi),"arithmetic_refusal","product overflow");
    return checked(std::max(0.0,down(lo)),up(hi));
}
I divide(I x, double positive) {
    need(x.lower>=0 && finite(positive) && positive>0,"arithmetic_refusal","invalid ratio operand");
    if (zero(x)) return {};
    if (positive==1) return x;
    const double lo=x.lower/positive, hi=x.upper/positive;
    need(finite(lo) && finite(hi),"arithmetic_refusal","ratio overflow");
    return checked(std::max(0.0,down(lo)),up(hi));
}
double sum(double x, double y) {
    const double value=x+y;
    need(finite(value),"arithmetic_refusal","represented mass sum overflow");
    return value;
}
double positive_result(double x) {
    need(finite(x) && x>0,"arithmetic_refusal","positive conversion overflow or underflow");
    return x;
}
void limits_ok(const SeasonalLiquidRoutingLimits& l) {
    need(l.max_cells>0 && l.max_cells<=200000 && l.max_neighbor_entries<=1600000 &&
         l.max_sources<=262144 && l.max_identifier_bytes>0 && l.max_identifier_bytes<=96 &&
         l.max_arithmetic_groups>0 && l.max_arithmetic_groups<=2097152,
         "invalid_limits","routing limits exceed fixed component bounds");
}
void identifier(const std::string& id, std::size_t cap) {
    need(!id.empty() && id.size()<=cap,"invalid_input","identifier length");
    for (unsigned char c:id) need(c>=33 && c<=126,"invalid_input","identifier must be visible ASCII");
}
SeasonalLiquidRoutingNode node(const Cell& c) {
    SeasonalLiquidRoutingNode n;
    n.cell_id=c.id; n.original_receiver=c.flow_to;
    n.effective_receiver=(c.is_water || c.is_lake)?-1:c.flow_to;
    n.neighbors=c.neighbors; n.is_water=c.is_water; n.is_lake=c.is_lake;
    n.water_body=c.water_body; n.is_closed_basin=c.is_closed_basin; n.lake_overflows=c.lake_overflows;
    n.hydrologic_surface_conditioned=c.hydrologic_surface_conditioned;
    n.depression_component_id=c.depression_component_id; n.depression_sink_cell_id=c.depression_sink_cell_id;
    n.area_km2=c.area_km2; n.elevation_m=c.elevation_m; n.filled_elevation_m=c.filled_elevation_m;
    n.hydrologic_surface_elevation_m=c.hydrologic_surface_elevation_m;
    n.hydrologic_flow_slope=c.hydrologic_flow_slope; n.water_depth_m=c.water_depth_m;
    n.lake_fill_fraction=c.lake_fill_fraction;
    n.terminal=c.is_water?SeasonalLiquidTerminal::marine:c.is_lake?SeasonalLiquidTerminal::lake:
        c.flow_to<0?SeasonalLiquidTerminal::dry:SeasonalLiquidTerminal::none;
    return n;
}
bool node_matches(const SeasonalLiquidRoutingNode& n,const Cell& c) {
    return n.cell_id==c.id && n.original_receiver==c.flow_to && n.neighbors==c.neighbors &&
        n.is_water==c.is_water && n.is_lake==c.is_lake && n.water_body==c.water_body &&
        n.is_closed_basin==c.is_closed_basin && n.lake_overflows==c.lake_overflows &&
        n.hydrologic_surface_conditioned==c.hydrologic_surface_conditioned &&
        n.depression_component_id==c.depression_component_id && n.depression_sink_cell_id==c.depression_sink_cell_id &&
        same(n.area_km2,c.area_km2) && same(n.elevation_m,c.elevation_m) &&
        same(n.filled_elevation_m,c.filled_elevation_m) &&
        same(n.hydrologic_surface_elevation_m,c.hydrologic_surface_elevation_m) &&
        same(n.hydrologic_flow_slope,c.hydrologic_flow_slope) && same(n.water_depth_m,c.water_depth_m) &&
        same(n.lake_fill_fraction,c.lake_fill_fraction);
}
std::string quote(const std::string& s) {
    std::ostringstream o; o.imbue(std::locale::classic()); o << '"';
    for (unsigned char c:s) {
        if(c=='"' || c=='\\') o << '\\' << static_cast<char>(c);
        else if(c<32 || c>=127) o << "\\u00" << std::hex << std::setw(2) << std::setfill('0') << static_cast<int>(c);
        else o << static_cast<char>(c);
    }
    o << '"'; return o.str();
}
std::string number(double x) {
    std::ostringstream o; o.imbue(std::locale::classic());
    if(!finite(x)) {
        o << "{\"nonfinite_binary64_bits\":\"" << std::hex << std::setw(16) << std::setfill('0')
          << std::bit_cast<std::uint64_t>(x) << "\"}";
    } else o << std::setprecision(17) << x;
    return o.str();
}
std::string interval(I x) { return "{\"lower\":"+number(x.lower)+",\"upper\":"+number(x.upper)+'}'; }
std::string boolean(bool b) { return b?"true":"false"; }
template<class T,class F> std::string array(const std::vector<T>& xs,F f) {
    std::string out="["; bool first=true;
    for(const auto& x:xs) {if(!first)out+=',';first=false;out+=f(x);} return out+']';
}
struct Object {
    std::string text="{"; bool first=true;
    void add(const std::string& k,const std::string& v) {if(!first)text+=',';first=false;text+=quote(k)+':'+v;}
    void value(const std::string& k,double v) {add(k,number(v));}
    std::string finish() {return text+'}';}
};
std::string terminal(SeasonalLiquidTerminal t) {
    switch(t) {
        case SeasonalLiquidTerminal::dry:return "dry";
        case SeasonalLiquidTerminal::lake:return "lake";
        case SeasonalLiquidTerminal::marine:return "marine";
        case SeasonalLiquidTerminal::none:return "none";
    }
    throw SeasonalLiquidRoutingError("invalid_input","unknown terminal type");
}
std::string limits_json(const SeasonalLiquidRoutingLimits& l) {
    Object o;
#define V(k) o.add(#k,std::to_string(l.k))
    V(max_cells);V(max_neighbor_entries);V(max_sources);V(max_identifier_bytes);V(max_arithmetic_groups);
#undef V
    return o.finish();
}
std::string node_json(const SeasonalLiquidRoutingNode& n,bool derived) {
    Object o; o.add("cell_id",std::to_string(n.cell_id));o.add("original_receiver",std::to_string(n.original_receiver));
    o.add("neighbors",array(n.neighbors,[](int x){return std::to_string(x);}));
#define B(k) o.add(#k,boolean(n.k))
    B(is_water);B(is_lake);B(is_closed_basin);B(lake_overflows);B(hydrologic_surface_conditioned);
#undef B
#define Z(k) o.add(#k,std::to_string(n.k))
    Z(water_body);Z(depression_component_id);Z(depression_sink_cell_id);
#undef Z
#define V(k) o.value(#k,n.k)
    V(area_km2);V(elevation_m);V(filled_elevation_m);V(hydrologic_surface_elevation_m);
    V(hydrologic_flow_slope);V(water_depth_m);V(lake_fill_fraction);
#undef V
    if(derived) {
        o.add("effective_receiver",std::to_string(n.effective_receiver));o.add("terminal",quote(terminal(n.terminal)));
        o.value("area_m2",n.area_m2);o.add("area_conversion_difference_m2",interval(n.area_conversion_difference_m2));
    }
    return o.finish();
}
void identity(Object& o) {
    o.add("model",quote("fixed_terrain_finite_liquid_mass_routing_v1"));
    o.add("terminal_policy",quote("first_wet_or_dry_terminal_v1"));
    o.add("mass_scope",quote("canonical_represented_source_kg_outward_rounding_bounds_v1"));
    o.add("depth_scope",quote("equivalent_throughput_depth_not_water_storage_v1"));
    o.add("original_source_accuracy_certified","false");o.add("owner_commit_authenticated","false");
    o.add("external_delivery_acknowledged","false");o.add("downstream_energy_certified","false");
    o.add("physical_travel_time_resolved","false");o.add("ordinary_generation_changed","false");
}
} // namespace

SeasonalLiquidRoutingError::SeasonalLiquidRoutingError(std::string c,std::string detail)
    :std::runtime_error(c+": "+detail),code(std::move(c)) {}
SeasonalLiquidRoutingCapability seasonal_liquid_routing_capability() {
#if defined(__FAST_MATH__)
    return {false,"fast_math_unsupported"};
#else
    if(!(std::numeric_limits<double>::is_iec559 && std::numeric_limits<double>::radix==2 &&
         std::numeric_limits<double>::digits==53 && sizeof(double)==8 && std::fegetround()==FE_TONEAREST))
        return {false,"requires_binary64_round_to_nearest"};
    volatile double normal=std::numeric_limits<double>::min();
    volatile double tiny=std::numeric_limits<double>::denorm_min();
    volatile double half=.5, one=1;
    const double subnormal=normal*half, retained=tiny*one;
    if(!(subnormal>0 && subnormal<normal && same(retained,std::numeric_limits<double>::denorm_min())))
        return {false,"requires_gradual_underflow"};
    return {true,"binary64_nearest_gradual_underflow"};
#endif
}
struct SeasonalLiquidRoutingGraph::Data {
    std::uint64_t revision;
    SeasonalLiquidRoutingLimits limits;
    std::vector<SeasonalLiquidRoutingNode> nodes;
    std::vector<int> order;
};
SeasonalLiquidRoutingGraph::SeasonalLiquidRoutingGraph(std::shared_ptr<const Data> p):data_(std::move(p)) {}
const std::vector<SeasonalLiquidRoutingNode>& SeasonalLiquidRoutingGraph::nodes() const{return data_->nodes;}
const std::vector<int>& SeasonalLiquidRoutingGraph::topological_order() const{return data_->order;}
const SeasonalLiquidRoutingLimits& SeasonalLiquidRoutingGraph::limits() const{return data_->limits;}
std::uint64_t SeasonalLiquidRoutingGraph::revision() const{return data_->revision;}
bool SeasonalLiquidRoutingGraph::matches(const std::vector<Cell>& cells) const {
    if(cells.size()!=nodes().size())return false;
    for(std::size_t i=0;i<cells.size();++i)if(!node_matches(nodes()[i],cells[i]))return false;
    return true;
}
SeasonalLiquidRoutingGraph capture_seasonal_liquid_routing_graph(
    const std::vector<Cell>& cells,std::uint64_t revision,SeasonalLiquidRoutingLimits limits) {
    limits_ok(limits);
    need(!cells.empty() && cells.size()<=limits.max_cells,"invalid_graph","cell count outside admitted bound");
    std::size_t incidence=0;
    for(const auto& c:cells) {
        need(c.neighbors.size()<=limits.max_neighbor_entries-incidence,"invalid_graph","neighbor incidence cap");
        incidence+=c.neighbors.size();
    }
    const auto capability=seasonal_liquid_routing_capability();
    need(capability.available,"capability_unavailable",capability.reason);
    const auto n=cells.size();
    std::vector<std::size_t> incoming(n,0);
    for(std::size_t i=0;i<n;++i) {
        const auto& c=cells[i];
        need(c.id==static_cast<int>(i),"invalid_graph","noncanonical cell ID");
        need(finite(c.area_km2) && c.area_km2>0,"invalid_graph","invalid cell area");
        need(!(c.is_water && c.is_lake),"invalid_graph","contradictory wet applicability");
        need((c.is_water && c.water_body>=1 && c.water_body<=3) ||
             (c.is_lake && (c.water_body==4 || c.water_body==5)) ||
             (!c.is_water && !c.is_lake && (c.water_body==0 || c.water_body==5)),
             "invalid_graph","inconsistent water class");
        for(double v:{c.elevation_m,c.filled_elevation_m,c.hydrologic_surface_elevation_m,
                      c.hydrologic_flow_slope,c.water_depth_m,c.lake_fill_fraction})
            need(finite(v),"invalid_graph","nonfinite routing metadata");
        need(c.water_depth_m>=0 && c.hydrologic_flow_slope>=0 && c.lake_fill_fraction>=0 &&
             c.lake_fill_fraction<=1.5,"invalid_graph","invalid routing metadata range");
        need(c.depression_component_id>=-1 && c.depression_sink_cell_id>=-1 &&
             c.depression_sink_cell_id<static_cast<int>(n),"invalid_graph","invalid depression identity");
        std::set<int> neighbors;
        for(int j:c.neighbors)
            need(j>=0 && j<static_cast<int>(n) && j!=c.id && neighbors.insert(j).second,
                 "invalid_graph","invalid or duplicate neighbor");
        need(c.flow_to>=-1 && c.flow_to<static_cast<int>(n) && c.flow_to!=c.id,
             "invalid_graph","invalid receiver");
        if(c.flow_to>=0) {
            need(neighbors.count(c.flow_to)!=0,"invalid_graph","receiver is not adjacent");
            ++incoming[static_cast<std::size_t>(c.flow_to)];
        }
    }
    // Validate the ORIGINAL whole graph, including edges later cut at wet nodes.
    std::priority_queue<int,std::vector<int>,std::greater<int>> ready;
    for(std::size_t i=0;i<n;++i)if(incoming[i]==0)ready.push(static_cast<int>(i));
    std::vector<int> order;order.reserve(n);
    while(!ready.empty()) {
        const int i=ready.top();ready.pop();order.push_back(i);
        const int to=cells[static_cast<std::size_t>(i)].flow_to;
        if(to>=0 && --incoming[static_cast<std::size_t>(to)]==0)ready.push(to);
    }
    need(order.size()==n,"invalid_graph","receiver graph has a cycle");
    auto data=std::make_shared<SeasonalLiquidRoutingGraph::Data>();
    data->revision=revision;data->limits=limits;data->order=std::move(order);data->nodes.reserve(n);
    for(const auto& c:cells) {
        auto x=node(c);x.area_m2=positive_result(c.area_km2*1e6);
        x.area_conversion_difference_m2=difference(point(x.area_m2),multiply(point(c.area_km2),point(1e6)));
        data->nodes.push_back(std::move(x));
    }
    return SeasonalLiquidRoutingGraph(std::move(data));
}

SeasonalLiquidRoutingReceipt route_seasonal_liquid_mass(
    const SeasonalLiquidRoutingGraph& graph,const SeasonalLiquidMassRequest& request) {
    SeasonalLiquidRoutingReceipt r;r.graph_revision=graph.revision();
    try {
        const auto capability=seasonal_liquid_routing_capability();
        need(capability.available,"capability_unavailable",capability.reason);
        const auto& limits=graph.limits();const auto& ns=graph.nodes();
        need(request.sources.size()<=limits.max_sources,"invalid_input","source count exceeds admitted cap");
        identifier(request.id,limits.max_identifier_bytes);
        for(const auto& s:request.sources)identifier(s.id,limits.max_identifier_bytes);
        r.request=request;
        need(request.complete_source_list,"invalid_input","finite source list must be declared complete");
        need(finite(request.reference_water_density_kg_m3) && request.reference_water_density_kg_m3>0,
             "invalid_input","invalid reference liquid density");
        std::set<std::string> ids;
        for(const auto& s:request.sources) {
            need(ids.insert(s.id).second,"invalid_input","duplicate finite source identifier");
            need(s.cell_id>=0 && static_cast<std::size_t>(s.cell_id)<ns.size(),"invalid_input","unknown source cell");
            need(!ns[s.cell_id].is_water && !ns[s.cell_id].is_lake,"invalid_input","source must be exposed land");
            need(finite(s.mass_kg) && s.mass_kg>=0,"invalid_input","invalid finite source mass");
        }
        SeasonalLiquidRoutingResult result;
        std::vector<double> masses(ns.size(),0);std::vector<I> exact(ns.size());
        const auto group=[&]() {
            need(r.work.arithmetic_groups_started<limits.max_arithmetic_groups,"work_cap","arithmetic group cap");
            ++r.work.arithmetic_groups_started;
        };
        for(const auto& s:request.sources) {
            group();masses[s.cell_id]=sum(masses[s.cell_id],s.mass_kg);
            exact[s.cell_id]=add(exact[s.cell_id],point(s.mass_kg));
            result.represented_source_total_kg=sum(result.represented_source_total_kg,s.mass_kg);
            result.exact_source_total_kg=add(result.exact_source_total_kg,point(s.mass_kg));
            ++r.work.sources_completed;
        }
        for(int id:graph.topological_order()) {
            const auto i=static_cast<std::size_t>(id);const int to=ns[i].effective_receiver;
            if(to>=0) {
                group();const auto j=static_cast<std::size_t>(to);
                masses[j]=sum(masses[j],masses[i]);exact[j]=add(exact[j],exact[i]);
                ++r.work.edges_completed;
            }
        }
        result.cells.reserve(ns.size());
        for(std::size_t i=0;i<ns.size();++i) {
            group();SeasonalLiquidCellReceipt c;c.cell_id=static_cast<int>(i);
            c.effective_receiver=ns[i].effective_receiver;c.terminal=ns[i].terminal;
            c.represented_throughput_mass_kg=masses[i];c.exact_source_mass_kg=exact[i];
            c.representation_difference_kg=difference(point(masses[i]),exact[i]);
            if(masses[i]>0) {
                double depth=positive_result(masses[i]/ns[i].area_m2);
                depth=positive_result(depth/request.reference_water_density_kg_m3);
                c.represented_depth_mm=positive_result(depth*1000);
            }
            // Exact depth concerns the ideal routed source mass and canonical
            // area/density. Original area conversion is a separate graph field.
            c.exact_depth_mm=multiply(divide(divide(exact[i],ns[i].area_m2),
                request.reference_water_density_kg_m3),point(1000));
            c.represented_mass_exact_depth_mm=multiply(divide(divide(point(masses[i]),ns[i].area_m2),
                request.reference_water_density_kg_m3),point(1000));
            c.depth_conversion_difference_mm=difference(point(c.represented_depth_mm),c.represented_mass_exact_depth_mm);
            c.depth_total_difference_mm=difference(point(c.represented_depth_mm),c.exact_depth_mm);
            ++r.work.conversions_completed;
            if(c.terminal!=SeasonalLiquidTerminal::none) {
                group();result.terminal_cell_ids.push_back(c.cell_id);
                result.represented_terminal_total_kg=sum(result.represented_terminal_total_kg,masses[i]);
                result.exact_terminal_total_kg=add(result.exact_terminal_total_kg,exact[i]);
                result.exact_represented_terminal_sum_kg=add(result.exact_represented_terminal_sum_kg,point(masses[i]));
                ++r.work.terminals_completed;
            }
            result.cells.push_back(std::move(c));
        }
        group();result.source_sum_difference_kg=difference(point(result.represented_source_total_kg),result.exact_source_total_kg);
        result.terminal_sum_difference_kg=difference(point(result.represented_terminal_total_kg),result.exact_represented_terminal_sum_kg);
        result.terminal_total_minus_source_mass_kg=difference(point(result.represented_terminal_total_kg),result.exact_source_total_kg);
        r.final=std::move(result);r.accepted=true;
    } catch(const std::bad_alloc&) {throw;
    } catch(const SeasonalLiquidRoutingError& e) {r.failure_code=e.code;r.detail=e.what();}
    return r;
}

std::string seasonal_liquid_routing_input_json(const std::vector<Cell>& cells,
    std::uint64_t revision,const SeasonalLiquidRoutingLimits& limits) {
    Object o;o.add("revision",std::to_string(revision));o.add("limits",limits_json(limits));
    o.add("cells",array(cells,[](const Cell& c){return node_json(node(c),false);}));return o.finish();
}
std::string seasonal_liquid_routing_graph_json(const SeasonalLiquidRoutingGraph& graph) {
    Object o;identity(o);o.add("revision",std::to_string(graph.revision()));o.add("limits",limits_json(graph.limits()));
    o.add("nodes",array(graph.nodes(),[](const auto& n){return node_json(n,true);}));
    o.add("topological_order",array(graph.topological_order(),[](int i){return std::to_string(i);}));return o.finish();
}
std::string seasonal_liquid_mass_request_json(const SeasonalLiquidMassRequest& r) {
    Object o;o.add("id",quote(r.id));o.add("complete_source_list",boolean(r.complete_source_list));
    o.value("reference_water_density_kg_m3",r.reference_water_density_kg_m3);
    o.add("sources",array(r.sources,[](const auto& s){Object z;z.add("id",quote(s.id));z.add("cell_id",std::to_string(s.cell_id));z.value("mass_kg",s.mass_kg);return z.finish();}));
    return o.finish();
}
std::string seasonal_liquid_routing_receipt_json(const SeasonalLiquidRoutingReceipt& r) {
    Object o;identity(o);o.add("accepted",boolean(r.accepted));o.add("failure_code",quote(r.failure_code));
    o.add("detail",quote(r.detail));o.add("graph_revision",std::to_string(r.graph_revision));
    o.add("request",r.request?seasonal_liquid_mass_request_json(*r.request):"null");Object w;
#define W(k) w.add(#k,std::to_string(r.work.k))
    W(arithmetic_groups_started);W(sources_completed);W(edges_completed);W(conversions_completed);W(terminals_completed);
#undef W
    o.add("work",w.finish());
    if(!r.final) o.add("final","null");
    else {
        const auto& f=*r.final;Object z;
        z.add("cells",array(f.cells,[](const SeasonalLiquidCellReceipt& c){
            Object v;v.add("cell_id",std::to_string(c.cell_id));v.add("effective_receiver",std::to_string(c.effective_receiver));v.add("terminal",quote(terminal(c.terminal)));
            v.value("represented_throughput_mass_kg",c.represented_throughput_mass_kg);v.add("exact_source_mass_kg",interval(c.exact_source_mass_kg));
            v.add("representation_difference_kg",interval(c.representation_difference_kg));v.value("represented_depth_mm",c.represented_depth_mm);
            v.add("exact_depth_mm",interval(c.exact_depth_mm));v.add("represented_mass_exact_depth_mm",interval(c.represented_mass_exact_depth_mm));
            v.add("depth_conversion_difference_mm",interval(c.depth_conversion_difference_mm));v.add("depth_total_difference_mm",interval(c.depth_total_difference_mm));return v.finish();}));
        z.add("terminal_cell_ids",array(f.terminal_cell_ids,[](int i){return std::to_string(i);}));
        z.value("represented_source_total_kg",f.represented_source_total_kg);z.value("represented_terminal_total_kg",f.represented_terminal_total_kg);
#define V(k) z.add(#k,interval(f.k))
        V(exact_source_total_kg);V(exact_terminal_total_kg);V(exact_represented_terminal_sum_kg);
        V(source_sum_difference_kg);V(terminal_sum_difference_kg);V(terminal_total_minus_source_mass_kg);
#undef V
        o.add("final",z.finish());
    }
    return o.finish();
}
} // namespace magic_geo::detail
