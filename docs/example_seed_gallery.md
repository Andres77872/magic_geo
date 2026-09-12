# Example seed gallery

The repository ships nine complete, original world seeds in
[`configs/seeds`](../configs/seeds). They are standalone `WorldConfig` YAML
files, not fragments: every example declares `config_version: 2` and
explicitly sets all 43 generation properties across all nine sections. This makes each premise inspectable and
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
| [`cryogenic_slushball.yaml`](../configs/seeds/cryogenic_slushball.yaml) | Ice-dominated survival setting | `0.55` stellar luminosity, weak greenhouse trapping, low obliquity | Ice extent, liquid refugia, tundra, glacial landforms, meltwater, and cold-water ports |
| [`young_volcanic.yaml`](../configs/seeds/young_volcanic.yaml) | Small, hot, geologically active frontier | Young age, high internal heat, 28 plates, rapid motion, strong uplift | Boundary density, relief, volcanic proxies, arc resources, hazards, and constrained routes |
| [`verdant_hothouse.yaml`](../configs/seeds/verdant_hothouse.yaml) | Hot, wet jungle, wetland, and river world | Dense atmosphere, strong greenhouse forcing, high precipitation, filled depressions | Forest and wetland coverage, connected drainage, large rivers, floodplains, and river ports |
| [`solstice_extreme.yaml`](../configs/seeds/solstice_extreme.yaml) | Severe but regular seasonal world | `75°` axial tilt, moderate eccentricity, 30-hour day | Monthly temperature range, shifting ice, seasonal water stress, and biome ecotones |
| [`ironroot_super_earth.yaml`](../configs/seeds/ironroot_super_earth.yaml) | High-gravity large-planet experiment | 9,500 km radius, `1.6 g`, 3.02-billion km³ ocean inventory, dense atmosphere | Area/distance scaling, relief response, transport distances, hydrology, and high-gravity diagnostics |
| [`oldstone_stagnant.yaml`](../configs/seeds/oldstone_stagnant.yaml) | Ancient, eroded, tectonically quiet world | Zero plate motion, low internal heat, 9.5 Ga age, broad crust, refined erosion steps | Worn relief, mature drainage, closed basins, old interiors, sedimentary resources, and sparse young mountains |

## Seasonal migration evidence

All presets now use the native seasonal energy model with a declared reference
infrared optical depth of 1.0. This is the same baseline coefficient for every
preset; pressure, greenhouse factor, gravity, luminosity and orbital differences
are preserved. The previous Celsius mean and lapse controls were removed,
without fitting opacity to the old means. The [migration report](seasonal_scenario_migration.md)
records every retired control, paired V3 comparison, numerical gate and runtime.

The current audit requests 128 cells and zero erosion iterations while retaining
each preset's plate count and mesh backend. Continental realm resolves to 162
geodesic cells. All nine native energy budgets pass independent replay. Eight
presets pass generic coherence; the dry desert exposes a terminal/basin
validation failure documented in the report. These observations supersede the
old legacy-model declared-resolution table. The migrated full-resolution worlds
and full erosion histories have not been certified by this bounded audit.

| Seed | Seasonal mean °C | Ocean area fraction | Land precipitation mm/y | Interpretation |
| --- | ---: | ---: | ---: | --- |
| `continental_realm` | 18.4 | 0.452 | 1,651 | Land-rich at this mesh; no Earth calibration claim |
| `glasswind_desert` | 21.0 | 0.000 | 60 | 94.5% desert land; zero runoff; dry-terminal validation issue |
| `pelagic_archipelago` | 32.7 | 0.742 | 5,077 | Hot and wet; island geometry remains resolution sensitive |
| `cryogenic_slushball` | −37.7 | 0.648 | 349 | Cold surface; marine labels do not certify liquid refugia |
| `young_volcanic` | 69.6 | 0.125 | 1,381 | Extreme heat; geological proxies do not establish habitability |
| `verdant_hothouse` | 76.4 | 0.664 | 9,015 | Original jungle premise is unverified at this temperature |
| `solstice_extreme` | 19.4 | 0.523 | 2,058 | 44.6°C mean seasonal land range; hottest monthly cell 78.0°C |
| `ironroot_super_earth` | 22.4 | 0.562 | 3,032 | Pressure/gravity/radius scaling retained |
| `oldstone_stagnant` | 3.3 | 0.305 | 546 | Cold, quiet initial world; long erosion history not probed here |

The seasonal solve uses prescribed surface coefficients without closed
lake/ice/cloud feedback. Rain, wind and biomes retain empirical rules. In
particular, forest labels in the very hot presets are not evidence that
terrestrial forests can survive there. Review the actual temperature and
available habitat support before adopting a biological or settlement premise.
Do not infer full simulation validity from YAML validity or a green energy
budget alone.

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

- `climate.reference_infrared_optical_depth` is the gray infrared depth at one
  bar and Earth gravity before local pressure, gravity and greenhouse-factor
  scaling. It is not a prescribed mean temperature; all ten shipped complete
  world files use the declared baseline 1.0.
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

Version 2 YAML documents use seasonal `WorldConfig` defaults for omitted
values. Keep `config_version: 2` explicit; version 1 is the separately selected
legacy model. The packaged `init-config`
template and canonical Earth reference are the curated `earthlike` profile,
not plain serializations of the neutral `default` profile: Earth-like sets
`tectonics.plate_motion_scale_deg_per_step: 4.0` and
`climate.precipitation_scale: 0.8`, while the neutral defaults are `2.0` and
`1.0`. Keep fields explicit when reproducibility or reviewability matters.
