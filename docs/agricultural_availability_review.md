# Agricultural availability and surface mining

Fresh full worlds declare `causal_soil_climate_resource_connected_land_use_zones_v2`.
The original weighted agriculture formula can exceed its 0.58 candidate threshold
when its own temperature response is zero. V2 makes that unavailable estimate
explicit and excludes standing water from terrestrial agriculture and surface
mining. Exact declared v1 archives retain their historical equations and replay.

| Cell field | Meaning |
|---|---|
| `agricultural_habitat_applicable` | Exposed land: neither water/lake boolean nor ocean, shelf, inland-sea or fresh-lake category |
| `agricultural_climate_supported` | Finite nonboolean annual air temperature strictly between -9 and 43°C; independent of habitat |
| `agricultural_potential_supported` | Applicable habitat, supported own temperature response, and available typed soil/climate/water descriptors |
| `mining_surface_applicable` | Exposed land only; no claim of complete mining inputs, economic access or mine capacity |

Unsupported agriculture is stored as zero with support=false, zone ID -1 and no
zone membership. A supported zero remains a valid visible value. Aquatic surface
mining is zero/inapplicable with no mining zone; geological resource labels and
deposit records remain intact. Dry saline terrain is not standing water solely
because of its category. The historical fresh-lake bonus is not transferred to
nearby land or interpreted as irrigation.

The temperature interval is the positive domain of the existing annual proxy,
not a crop-survival limit or a yield calibration. Agriculture reads its own
native/soil/biome/water descriptors; it does not consume ecosystem primary
productivity. Native population's regional `agricultural_capacity_index` and the
economy's use of that separate quantity are unchanged and still need their own
applicability review.

V2 requires explicit reciprocal neighbour lists, valid unique IDs and source
links, a primary-resource category on every cell, and explicit deposit,
settlement and route collections. Empty collections and resource `none` are
legitimate; missing collections are rejected. In reviewed complete-world
witnesses, omitted adjacency split a three-cell agricultural component, and a
missing resource label silently erased a positive mining candidate. The strict
preflight now rejects both before publishing any owned field. Re-enrichment is
atomic as well.

All coefficients, raw candidate thresholds (0.58 agriculture, 0.52 mining),
component ordering, links, rounding and legacy means are retained. Four flag
counts, supported agricultural area and unsupported terrestrial agricultural
count accompany the existing all-cell means, which include unavailable zero
sentinels. The CLI independently replays the declared v2 stage before eager
numeric checks, after earlier native/ecology/water errors. The three-family
human-geography validator keeps its existing message order. Geography-only
worlds legitimately omit this human stage.

CSV appends the four flags. The debug map and inspector mask agriculture with
its potential-support flag and mining with its surface-applicability flag.
Supported zero stays visible; historical absent flags remain undeclared. Layer
help and Markdown summaries explain these distinctions and the means' scope.

The [adoption evidence](../runs/agricultural-main-adoption/README.md) records the
28-path patch (12 production, 16 tests/fixtures), original/result hashes, independent
review, full combined test result, export QA and main checks. Prepared maps were
visually inspected; live browser inspector and legend verification remains
unavailable, as documented in the QA evidence. One actual fresh
128-cell full generation took 16.721 seconds, declared both land-use and
worldbuilding v2, and passed full CLI/native/human/water audits. Every unowned
root, cell and summary value exactly matches the retained full-world baseline.
Twelve independent missing-input probes reject without mutation; four complete
valid archives retain exactly equal outputs after the stricter input checks.

The separate [activity audit](../runs/settlement-activity-dependency-review/README.md)
records remaining suitability inputs in natural disturbance/fire and human
accessibility. This agricultural change does not resolve those, native
population/settlement applicability, or seasonal ice/enthalpy coupling.
