# Example seed gallery

The repository ships nine complete, original world seeds in
[`configs/seeds`](../configs/seeds). They are standalone `WorldConfig` YAML
files, not fragments: every example explicitly sets all 44 generation
properties across all nine sections. This makes each premise inspectable and
keeps future schema drift visible in tests.

These are exploratory worldbuilding presets, not calibrated replicas of
fictional properties or predictions of real exoplanets. A seed biases the
causal generator; it cannot request a named continent, exact coastline, city,
faction, landmark, or story outcome.

## Run an example

Generate the declared-resolution world:

```bash
magic-geo generate \
  --config configs/seeds/continental_realm.yaml \
  --output runs/continental_realm/world.json \
  --summary runs/continental_realm/summary.md
```

Use the CLI override for a faster first look. The geodesic example rounds a
requested 512 cells to the realizable 642-cell mesh.

```bash
magic-geo generate \
  --geo-only \
  --config configs/seeds/continental_realm.yaml \
  --cells 512 \
  --output runs/continental_realm/geo-world-512.json
```

All examples use `compute.backend: cpu` and `compute.threads: 1` because the
current engine is bit-stable only for a fixed thread count. Change those values
when throughput matters more than exact replay.

## Catalog

| Seed | Intended use | Dominant controls | What to inspect |
| --- | --- | --- | --- |
| [`continental_realm.yaml`](../configs/seeds/continental_realm.yaml) | Temperate, land-rich epic-fantasy or campaign world | Lower ocean inventory, high continental-crust target, 12 broad plates, geodesic mesh | Major watersheds, inland basins, mountain passes, long routes, ports, and natural frontiers |
| [`glasswind_desert.yaml`](../configs/seeds/glasswind_desert.yaml) | Water-scarcity desert planet | Zero ocean inventory, `0.08` precipitation scale, strong subtropical drying, warm climate | Desert coverage, dry basins, rare water nodes, sparse settlement, and route dependence |
| [`pelagic_archipelago.yaml`](../configs/seeds/pelagic_archipelago.yaml) | Stormy maritime and island world | Large ocean inventory, low continental-crust target, 24 plates, strong rain | Island count, protected bays, straits, reefs, short rivers, ports, and maritime routes |
| [`cryogenic_slushball.yaml`](../configs/seeds/cryogenic_slushball.yaml) | Ice-dominated survival setting | `0.55` stellar luminosity, weak greenhouse trapping, cold temperature anchor | Ice extent, liquid refugia, tundra, glacial landforms, meltwater, and cold-water ports |
| [`young_volcanic.yaml`](../configs/seeds/young_volcanic.yaml) | Small, hot, geologically active frontier | Young age, high internal heat, 28 plates, rapid motion, strong uplift | Boundary density, relief, volcanic proxies, arc resources, hazards, and constrained routes |
| [`verdant_hothouse.yaml`](../configs/seeds/verdant_hothouse.yaml) | Hot, wet jungle, wetland, and river world | Dense atmosphere, strong greenhouse forcing, high precipitation, filled depressions | Forest and wetland coverage, connected drainage, large rivers, floodplains, and river ports |
| [`solstice_extreme.yaml`](../configs/seeds/solstice_extreme.yaml) | Severe but regular seasonal world | `75°` axial tilt, moderate eccentricity, 30-hour day | Monthly temperature range, shifting ice, seasonal water stress, and biome ecotones |
| [`ironroot_super_earth.yaml`](../configs/seeds/ironroot_super_earth.yaml) | High-gravity large-planet experiment | 9,500 km radius, `1.6 g`, 3.02-billion km³ ocean inventory, dense atmosphere | Area/distance scaling, relief response, transport distances, hydrology, and high-gravity diagnostics |
| [`oldstone_stagnant.yaml`](../configs/seeds/oldstone_stagnant.yaml) | Ancient, eroded, tectonically quiet world | Zero plate motion, low internal heat, 9.5 Ga age, broad crust, refined erosion steps | Worn relief, mature drainage, closed basins, old interiors, sedimentary resources, and sparse young mountains |

## Declared-resolution audit

Each exact checked-in seed was generated with `generate_geo_world` at its
declared resolution and then passed through the `generic` geo validator. All
nine complete all 14 layer-contract families with zero validation errors.
Warnings below are nonfatal realism observations that are useful for the stated
extreme regimes. Values are reference observations, not stable acceptance bands
for edited parameters or future engine versions.

| Seed | Cells | Ocean | Mean °C | Land precipitation mm/y | Defining generated evidence | Generic result |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| `continental_realm` | 2,562 | 0.340 | 14.0 | 932 | 6 landmasses; 33.0% forest land; 19.0°C seasonal land range | 14/14 layers, 0 warnings |
| `glasswind_desert` | 2,048 | 0.000 | 31.9 | 108 | 87.5% desert land; no rivers; one landmass | 14/14 layers, 2 warnings |
| `pelagic_archipelago` | 2,048 | 0.916 | 20.1 | 3,317 | 10 landmasses in the remaining 8.4% land area | 14/14 layers, 1 warning |
| `cryogenic_slushball` | 2,048 | 0.616 | −21.2 | 268 | 24.4% ice cells; no forest/desert land | 14/14 layers, 2 warnings |
| `young_volcanic` | 2,048 | 0.240 | 42.0 | 1,174 | 326 volcanic-arc cells; 286 high-seismic-hazard cells; 7 landmasses | 14/14 layers, 2 warnings |
| `verdant_hothouse` | 2,048 | 0.655 | 40.9 | 7,338 | 81.0% forest land; no desert land; 4.9% river cells | 14/14 layers, 0 warnings |
| `solstice_extreme` | 2,048 | 0.468 | 12.2 | 1,071 | 43.7°C mean seasonal land-temperature range | 14/14 layers, 0 warnings |
| `ironroot_super_earth` | 2,048 | 0.578 | 17.2 | 1,612 | 10 landmasses; 42.0% forest land | 14/14 layers, 0 warnings |
| `oldstone_stagnant` | 2,048 | 0.257 | 4.4 | 358 | 40.3% desert land; 10.4% ice cells; zero configured plate motion | 14/14 layers, 2 warnings |

The audit also exposed two important nonlinear boundaries:

- Connected-ocean flooding has topology jumps. The Super-Earth, solstice, and
  oldstone inventories use nearby round values that reconstruct exactly at the
  declared mesh; several superficially similar volumes generated a world but
  failed ocean-inventory closure.
- Schema validity is weaker than simulation validity. The exact desert preset
  passes with eight plates, but nearby plate counts and seeds can fail current
  crust-transport replay. The volcanic preset passes at six refined maturation
  steps; seven generates but fails a material-shadow replay, and eight exceeds
  the current accounting envelope. Re-run generic validation after changing
  these coupled controls.

## Research translated into presets

Popular fictional planets often make one environmental premise immediately
legible and then let it constrain travel, settlement, resources, and conflict.
Official descriptions of
[Tatooine](https://www.starwars.com/databank/tatooine),
[Kamino](https://www.starwars.com/databank/kamino),
[Hoth](https://www.starwars.com/databank/hoth), and
[Mustafar](https://www.starwars.com/databank/mustafar) are clear examples of the
desert, ocean, ice, and volcanic premises. The examples here use those broad
archetypes but have original names, seeds, and parameter combinations; they do
not reproduce franchise geography or lore.

The presets also follow two more general research lessons:

- The Science Fiction and Fantasy Writers Association recommends extrapolating
  a small number of changes through geography, livelihood, economy, culture,
  law, and conflict rather than adding isolated novelties
  ([worldbuilding through extrapolation](https://sfwa.org/2019/05/03/from-the-inside-out-worldbuilding-through-extrapolation/)).
- Kevin Lynch's paths, edges, districts, nodes, and landmarks provide a useful
  test of whether generated geography will remain readable at story scale
  ([MIT, *Images of the City*](https://betterworld.mit.edu/images-of-the-city/)).

That produces the review chain used for this gallery:

```text
planet premise
  -> climate, relief, and water regime
  -> traversable paths and hard edges
  -> resource and hazard asymmetry
  -> settlement nodes and political districts
  -> memorable generated landmarks
```

The cold and high-obliquity examples deliberately remain more nuanced than
their names. NASA climate studies describe both partially open-ocean
"slushball" outcomes and the strong climate swings possible above roughly
55 degrees of obliquity
([NASA GISS snowball research](https://www.giss.nasa.gov/research/features/201508_slushball/),
[NASA Astrobiology on axial tilt](https://astrobiology.nasa.gov/news/how-tidally-locked-planets-could-avoid-a-snowball-earth-fate/)).

## How to interpret the controls

- `planet.ocean_water_inventory_km3`, not `ocean_fraction_target`, controls the
  sea-level flood solve. The target is a diagnostic comparison value, so the
  realized fraction will differ and can change with mesh resolution.
- `run.seed` chooses a deterministic realization of the configured regime. It
  does not guarantee that a desired archipelago, inland sea, or supercontinent
  appears. Generate several seed values and select from measured output when a
  story needs a specific layout.
- `tectonics` and `erosion.maturation_timestep_ma` are procedural controls with
  nominal time labels, not calibrated plate velocities or geological clocks.
- `output.include_cells: true` is intentional. Natural and human geography
  enrichers need cells, and the detailed output is what lets you audit whether
  the generated world supports the preset's premise.
- `mesh.neighbor_count` affects the Fibonacci process stencil. A geodesic mesh
  derives its stencil from triangle edges, so the field remains explicit in the
  complete YAML but does not tune that backend in the same way.
- Non-Earth planets are schema-valid but only lightly calibrated. In particular,
  the volcanic example uses heat, motion, uplift, and resource proxies; it does
  not simulate exposed lava. The seasonal example always has twelve months and
  cannot reproduce irregular multi-year seasons. The desert example has one
  star in the current energy model and no explicit deep-aquifer inventory.

## Selecting a story-ready realization

Treat the YAML as a regime, then review generated evidence before naming the
world in a campaign or novel:

1. Generate a 512-cell geo-only preview for several `run.seed` values.
2. Compare ocean/land fraction, biome coverage, ice, river and lake networks,
   landmass count, relief, and climate seasonality.
3. Inspect paths and edges: navigable rivers, coasts, passes, deserts, glaciers,
   and chokepoints.
4. Generate the best candidates at the declared resolution. Coastlines, narrow
   straits, island counts, and even realized ocean fraction are resolution
   sensitive.
5. Run `magic-geo validate-geo --profile generic` on exotic worlds. The
   `earthlike` profile is intentionally inappropriate for most gallery presets.
6. Only then select settlements, factions, hazards, and landmarks from the
   generated causal evidence.

## Schema defaults versus curated seeds

Omitted YAML values use `WorldConfig` defaults. The packaged `init-config`
template and canonical Earth reference are the curated `earthlike` profile,
not plain serializations of the neutral `default` profile: Earth-like sets
`tectonics.plate_motion_scale_deg_per_step: 4.0` and
`climate.precipitation_scale: 0.8`, while the neutral defaults are `2.0` and
`1.0`. Keep fields explicit when reproducibility or reviewability matters.
