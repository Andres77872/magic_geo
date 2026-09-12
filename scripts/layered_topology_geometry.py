# Reused read-only geometry audit functions; historical runner intentionally omitted.
# Source replay.py SHA256 eb229ad6ebcdff15db07e07632f234fdecf627e274a7d2780b3491e6a9cf64fb
#!/usr/bin/env python3
"""Independent exact-rational layered geometry/mapping/inventory implementation."""
import copy,hashlib,json,math,sys
from fractions import Fraction as F
from pathlib import Path
checks=0
class Refusal(Exception): pass
def need(ok,why):
 global checks
 checks+=1
 if not ok:raise Refusal(why)
def q(x):return F(x)
def contains(x,v,why):need(q(x['lower'])<=v<=q(x['upper']),why)
def inventory_record(x,mass,energy,rawmass,rawenergy):
 need(x['represented_mass_kg']==rawmass and x['represented_enthalpy_j']==rawenergy,'represented extensive inventory')
 for key,v in [('exact_mass_kg',mass),('exact_enthalpy_j',energy),('mass_conversion_difference_kg',q(rawmass)-mass),('enthalpy_conversion_difference_j',q(rawenergy)-energy)]:contains(x[key],v,key)
def geometry(x,W,rho):
 exact=q(W)/q(rho);raw=W/rho if W else 0.0
 need(x['represented_thickness_m']==raw,'represented W/rho thickness')
 contains(x['exact_thickness_m'],exact,'original W/rho')
 contains(x['thickness_conversion_difference_m'],q(raw)-exact,'thickness conversion')
 contains(x['thickness_mass_reconstruction_difference_kg_m2'],q(rho)*q(raw)-q(W),'thickness mass bridge')
 return exact,raw

def audit(g):
 need(g['model']=='fixed_geometry_layered_ice_thermal_graph_v1','graph model')
 need(g['mass_area_scope']=='full_horizontal_footprint_coverage_fraction_one_v1','footprint area scope')
 for flag in ['original_source_accuracy_certified','geometry_conversion_error_in_thermal_certificate','source_operations_supported','deep_reservoir_thermally_coupled','geothermal_flux_resolved','water_percolation_resolved','material_remapping_supported','ordinary_generation_changed','world_horizontal_coverage_authenticated']:need(g[flag] is False,'scope '+flag)
 for key,value in {'geometry_scope':'prescribed_fixed_mass_density_conductivity_v1','conductance_scope':'equal_area_center_to_center_series_resistance_v1','conversion_scope':'canonical_binary64_operands_outward_bounds_v1','active_enthalpy_scope':'thermal_nodes_including_declared_top_nonwater_capacity_v1','deep_enthalpy_scope':'pure_water_relative_to_solid_at_freezing_temperature_v1','combined_enthalpy_scope':'active_thermal_nodes_plus_isolated_deep_water_not_ice_only_v1'}.items():need(g[key]==value,'scope '+key)
 inp=g['input'];need(inp['complete_horizontal_coverage_declared'] is True and inp['bottom_boundary']=='insulated','explicit input/boundary')
 expected={'water':inp['water'],'columns':[],'edges':[],'water_mass_kg_m2':[],'initial_enthalpy_j_m2':[],'absorbed_shortwave_w_m2':[]}
 active=[F(0),F(0),0.0,0.0];deep=[F(0),F(0),0.0,0.0];tops=[];vindex=0;dindex=0;flat=0
 for i,c in enumerate(inp['columns']):
  need(c['cell_id']==i and c['area_m2']>0 and c['layers'],'horizontal column identity/area')
  C=c['top_nonwater_heat_capacity_j_m2_k'];closure=c['top_closure']
  need((closure=='prescribed_top_energy' and C==0) or (closure in ('prescribed_nonwater_top_capacity','coarse_combined_surface_atmosphere') and C>0),'declared top closure')
  tops.append(flat);depth=F(0);rawdepth=0.0
  for j,l in enumerate(c['layers']):
   need(l['layer_id']==j and l['water_mass_kg_m2']>=0 and l['density_kg_m3']>0 and l['conductivity_w_m_k']>0,'material layer identity')
   node=g['nodes'][flat];need((node['thermal_node_id'],node['cell_id'],node['layer_id'])==(flat,i,j),'geographic to thermal mapping')
   W,H=l['water_mass_kg_m2'],l['enthalpy_j_m2'];A=c['area_m2'];base=C if j==0 else 0
   need(W>0 or (j==0 and len(c['layers'])==1 and base>0),'nonempty layer/dry shape')
   Cs=q(base)+q(W)*q(inp['water']['solid_heat_capacity_j_kg_k']);Cl=q(base)+q(W)*q(inp['water']['liquid_heat_capacity_j_kg_k'])
   need(Cs>0 and Cl>0 and q(H)>=-Cs*q(inp['water']['freezing_temperature_k']),'initial physical layer')
   dz,rawdz=geometry(node['geometry'],W,l['density_kg_m3'])
   inventory_record(node['inventory'],q(A)*q(W),q(A)*q(H),A*W,A*H)
   need(node['represented_depth_begin_m']==rawdepth,'raw depth begin');contains(node['exact_depth_begin_m'],depth,'exact depth begin');contains(node['depth_begin_difference_m'],q(rawdepth)-depth,'depth begin bridge')
   depth+=dz;rawdepth+=rawdz
   need(node['represented_depth_end_m']==rawdepth,'raw depth end');contains(node['exact_depth_end_m'],depth,'exact depth end');contains(node['depth_end_difference_m'],q(rawdepth)-depth,'depth end bridge')
   active[0]+=q(A)*q(W);active[1]+=q(A)*q(H);active[2]+=A*W;active[3]+=A*H
   expected['columns'].append({'area_m2':A,'heat_capacity_j_m2_k':base,'longwave_emissivity':c['top_longwave_emissivity'] if j==0 else 0})
   expected['water_mass_kg_m2'].append(W);expected['initial_enthalpy_j_m2'].append(H);expected['absorbed_shortwave_w_m2'].append(c['top_absorbed_shortwave_w_m2'] if j==0 else 0)
   if j:
    e=g['vertical_edges'][vindex];vindex+=1;prior=c['layers'][j-1];pdz=q(prior['water_mass_kg_m2'])/q(prior['density_kg_m3']);prawdz=prior['water_mass_kg_m2']/prior['density_kg_m3']
    R1=pdz/(2*q(prior['conductivity_w_m_k']));R2=dz/(2*q(l['conductivity_w_m_k']));R=R1+R2;K=q(A)/R
    raw1=(prawdz/2)/prior['conductivity_w_m_k'];raw2=(rawdz/2)/l['conductivity_w_m_k'];rawR=raw1+raw2;rawK=A/rawR
    need((e['first_thermal_node'],e['second_thermal_node'])==(flat-1,flat),'vertical adjacency')
    for key,value in [('area_m2',A),('first_thickness_m',prawdz),('second_thickness_m',rawdz),('first_conductivity_w_m_k',prior['conductivity_w_m_k']),('second_conductivity_w_m_k',l['conductivity_w_m_k'])]:need(e[key]==value,'edge operand '+key)
    for stem,exact,raw in [('first_half_resistance_m2_k_w',R1,raw1),('second_half_resistance_m2_k_w',R2,raw2),('total_resistance_m2_k_w',R,rawR),('conductance_w_k',K,rawK)]:
     need(e['represented_'+stem]==raw,'raw edge '+stem);contains(e['exact_'+stem],exact,'exact edge '+stem)
     parts=stem.rsplit('_m2_k_w',1) if stem.endswith('_m2_k_w') else stem.rsplit('_w_k',1);suffix='m2_k_w' if stem.endswith('_m2_k_w') else 'w_k'
     contains(e[parts[0]+'_difference_'+suffix],q(raw)-exact,'edge conversion '+stem)
    expected['edges'].append({'first_cell':flat-1,'second_cell':flat,'conductance_w_k':rawK})
   flat+=1
  d=c['deep_inventory']
  if d is not None:
   x=g['deep_inventories'][dindex];dindex+=1;need(x['cell_id']==i,'deep identity')
   W,H=d['water_mass_kg_m2'],d['enthalpy_j_m2'];need(W>=0 and d['density_kg_m3']>0 and (W>0 or H==0),'deep nonempty energy')
   need(c['layers'][0]['water_mass_kg_m2']>0 or W==0,'no hidden deep under dry zero surface')
   if W:
    need(q(W)*q(inp['water']['solid_heat_capacity_j_kg_k'])>0 and q(W)*q(inp['water']['liquid_heat_capacity_j_kg_k'])>0,'deep positive sensible capacities')
    need(q(H)>=-q(W)*q(inp['water']['solid_heat_capacity_j_kg_k'])*q(inp['water']['freezing_temperature_k']),'deep physical floor')
   geometry(x['geometry'],W,d['density_kg_m3']);inventory_record(x['inventory'],q(c['area_m2'])*q(W),q(c['area_m2'])*q(H),c['area_m2']*W,c['area_m2']*H)
   deep[0]+=q(c['area_m2'])*q(W);deep[1]+=q(c['area_m2'])*q(H);deep[2]+=c['area_m2']*W;deep[3]+=c['area_m2']*H
 need(len(g['nodes'])==flat and len(g['vertical_edges'])==vindex and len(g['deep_inventories'])==dindex,'complete node/edge/deep tables')
 need(g['top_thermal_node_ids']==tops,'top-only node map')
 seen=set()
 for e in inp['horizontal_climate_edges']:
  a,b=e['first_cell'],e['second_cell'];need(0<=a<b<len(tops) and (a,b) not in seen and e['conductance_w_k']>0,'horizontal graph');seen.add((a,b))
  expected['edges'].append({'first_cell':tops[a],'second_cell':tops[b],'conductance_w_k':e['conductance_w_k']})
 expected['edges'].sort(key=lambda e:(e['first_cell'],e['second_cell']))
 for key,value in expected.items():need(g['mesh'][key]==value,'actual thermal graph '+key)
 need(g['mesh']['options']['allow_pure_water_columns'] is True,'explicit generalized mode')
 inventory_record(g['inventories']['active'],*active);inventory_record(g['inventories']['deep'],*deep)
 inventory_record(g['inventories']['combined'],*(a+b for a,b in zip(active,deep)))
 return {'thermal_nodes':flat,'vertical_edges':vindex,'deep_stores':dindex,'exact_active_mass_kg':str(active[0]),'exact_deep_mass_kg':str(deep[0])}
