# Native terrestrial water and enthalpy ownership

The internal terrestrial interval entry supplies a state owner that the existing annual ice diagnostic lacks. It accepts an explicitly prescribed initial-event precipitation source, optional withdrawals from initial liquid inventory, and heat over a real positive interval. It is a prerequisite for a seasonal coupled model. Ordinary generated climate, grounded ice, hydrology and public schemas retain their current authority.

The separate [independent W/H/Ea owner](terrestrial_coupled_ownership.md) now provides phase-aware surface/air evolution and common-time atomic publication. This page documents the preserved prescribed-heat W/H contract; ordinary generation still does not invoke either owner automatically.

The owner stores water W in kg/m² and enthalpy H in J/m² relative to solid water plus dry substrate at the declared freezing temperature. H includes the dry substrate; emptying the water reservoir cannot reset H to zero. The native calorimeter retains the reviewed A interval arithmetic and now shares its movement accounting with a separate instantaneous mass-event interface. The adapter enables it only on platforms with its required extended long-double significand and range. On other platforms the new interval mode refuses with a capability error; ordinary generation can still build. The existing receipt's `frozen_cryosphere_enthalpy_A_v1` identifier names the interval algorithm contract; current source revisions are recorded separately.

## Timing, domain and publication

`EarthSystemState` marks a surface ready only after generation and all existing descendants finish. `begin_terrestrial_water_epoch` lazily captures immutable canonical cells, geometry, wet flags, and the hydrology source operands. Normal generation allocates no second Cell snapshot. Failed initialization publishes no epoch, and the same generated surface cannot start another epoch implicitly.

Physical elapsed seconds and owner revisions are distinct from geological maturation Ma, periodic climate iterations and lake-stabilization retries. Each requested endpoint must be finite, strictly increasing and exactly representable from elapsed plus duration. Marine and lake slots require zero terrestrial W/H and capacity and cannot receive sources, withdrawals or heat. Both prepare and commit check the exact stored epoch identity and current surface operands. A changed terrain or wet domain cannot silently retain a terrestrial reservoir.

Preparation builds a private candidate from the accepted restart. It retains original source IDs, phases, masses and temperatures; the actual canonical kernel movements; the liquid outbox; and a private hydrology projection. Commit validates the unique owner and exact accepted bundle before one nonthrowing bundle swap. Rejected, stale or cross-owner candidates cannot debit water again. Unique source and withdrawal IDs remain consumed across accepted intervals and in supplied restarts.

All mass movements are initial events. Gross liquid withdrawals are certified against the initial liquid inventory. Newly imported water and liquid produced by interval heat cannot fund a withdrawal in that same interval. Melting changes phase while retaining W. A later explicit interval can withdraw available liquid. No imaginary positive-duration drain event or maximum withdrawal computed from rounded phase times area is inserted.

## Instantaneous mass events

The native `apply_mass_events` entry accepts imports, exports and unequal-area transfers without a duration or heat input. It returns the canonical post-event W/H, phase state, original carried-enthalpy movements and mass/energy ledgers. All withdrawals use initial donor inventories and enthalpies. A transfer carries one represented energy amount for both its debit and credit. A rejected batch leaves every input unchanged; an empty batch validates and preserves the input state bitwise. A coupled caller can carry its state directly when no mass event occurs.

This result publishes a new canonical thermal restart. Its representation residual must remain in the successor error history. In a synthetic rounding control, an event that adds 1 J/m² to an initial H of 2^53 J/m² publishes H=2^53 with a −1 J/m² energy residual. The existing combined `advance` entry retains its private unrounded event energy through the following heat sum, so a subsequent prescribed −2^53 J/m² leaves H=1. The two entries have different rounding contracts; replacing the existing interval with two rounded public operations would change its result. Neither residual is corrected with added heat.

The mass-event entry owns no atmospheric state, elapsed clock, source IDs or external delivery. Those remain responsibilities of the coupled owner. [Implementation and validation](../runs/seasonal-mass-event-integration-review/README.md)

## Hydrology boundary and numerical evidence

The shared native water partition has a separate supplied-liquid entry. The ordinary annual entry keeps the existing precipitation formula and operation order. The interval projection converts only actual exported liquid mass to depth with explicit area and reference density, then annualizes it using the declared year and interval duration. It applies the existing annual loss law and converts resulting AET, infiltration and runoff rates back to interval depths. Original precipitation remains separate provenance.

This is an annualized-rate loss approximation; it does not solve transient evaporation or downstream energy. The outbox carries the exact canonical export enthalpy returned by A, without recomputing it from a displayed temperature. The projected cells belong to the private receipt and never overwrite generated cells or their natural and social descendants. A committed owner projection is not an external hydrology delivery acknowledgement. Authoritative routing still needs a durable one-use sink and coordinated replacement of annual precipitation consumers.

Canonical kernel mass/energy closure does not certify original-source precision or hydrology conversion error. Receipts preserve inputs and canonical results for an independent rational replay and declare those additional errors uncertified by the native receipt. The known synthetic source cancellation has 1,025 J under the original constitutive expression and 1 J after canonical movement rounding; a closing canonical ledger cannot erase its 1,024 J discrepancy. The fixture uses synthetic properties and is not an Earth parameter set. Source representation, final state publication, mass/J aggregation, depth/rate conversion and partition closure must remain separate quantities.

The new projection refuses nonfinite derived hydrology values and positive rate-to-depth underflow or overflow. These guards apply to the new entry and leave historical annual behavior intact.

## Remaining coupled simulation work

The annual grounded-ice diagnostic still does not evolve a perennial water and energy reservoir. This internal owner does not derive snow timing from annual or monthly temperature, reuse diagnostic glacier thickness as W, or claim seasonal prediction accuracy. It contains no surface/air thermal coupling, snow reflectivity feedback, sea or lake ice, spatial energy exchange, or downstream evaporation energy budget.

The [reviewed phase-aware thermal component](../runs/seasonal-cryosphere-phase-segment-review/README.md) fits phase boundaries with a coupled implicit solve and separate physical first-hit/error certificates. The independent coupled owner now advances every applicable cell to one requested endpoint, transports event error to that common numerical clock, and carries inherited error through source events and thermal segments before one atomic commit. Its certified scope uses explicitly projected canonical W and recorded import joules; original-source trajectory accuracy remains unproved. A rounded upper latent boundary can still prevent certification of the outgoing branch and causes a retained refusal.

The closed fixed-partition experiments remain closed. Production source scheduling, original-source error propagation, hydrologic delivery and a monthly mass/energy certificate must still replace the affected annual consumers together. Internal atmospheric ownership alone does not establish a seasonal or perennial ice prediction.
