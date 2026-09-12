# Layered calendar storage and lifetime review

The mapped layered owner now shares immutable forcing prefixes and snapshots, stores a lossless normalized journal, and accounts for returned candidates and rich diagnostics until their last retained reference is released. This removes quadratic forcing-value duplication and closes a gap where returned candidates could outlive their temporary reservation. These are internal prerequisites for a seasonal coordinator; full-year numerical and resource admission remain open.

## What changed

Previously, each accepted receipt copied the complete forcing history into both its initial and final snapshots. For T distinct windows with N forcing values each, those two histories retained N·T² double occurrences. At T=1080 and N=128, that is 149,299,200 occurrences, or 1,194,393,600 raw binary64 bytes, for only 138,240 unique values. Even one-character numeric tokens and their internal array commas require at least T²·(2N−1) = 297,432,000 JSON bytes, exceeding the 128 MiB journal cap before any other state or proof.

The new persistent tree stores each forcing vector once within the history and shares immutable entries between prefixes. Exact per-request operands remain separately retained. Appending copies only O(log T) small tree nodes. Accepted snapshots and receipt initial/final snapshots share ownership. The owner reserves its bounded record-index capacity at construction; a candidate retains one new record and its source snapshot instead of copied prior journals. A snapshot view no longer retains the complete journal.

Each normalized record references the preceding accepted snapshot and geographic mapping, records the forcing-prefix length and any newly appended forcing, and retains its full final physical graph. Exact replay operands, all material/remapping/absorption/topology receipts, complete SDIRK and BE witnesses, domain checks, error charges and ledgers remain present. Full standalone snapshot and receipt serializers still expand those references. The wire models are `lossless_layered_owner_journal_v1`, `lossless_layered_owner_journal_record_v1` and `mapped_atomic_layered_ice_owner_v5`.

Private reservations now follow the retained payload. Candidate and diagnostic aliases share one lease; a diagnostic alone keeps it alive. A successful commit transfers the exact normalized charge to committed history once. Stale candidates retain their private charge until released. Committed replay shares the original complete receipt and starts no new physical work, including when private slots are occupied.

The exposed storage counters distinguish committed journal bytes, prospective journal reservations, private receipt bytes, retained preparations and active computations. Seed and journal framing are charged. Rich refusals release prospective journal capacity but retain their own private charge; an oversized refusal falls back to fixed metadata preserving observed work. Fixed metadata is explicitly exempt if it cannot fit in the rich-payload budget.

## Meaning of the limits

The byte limits measure normalized JSON wire bytes. They do **not** bound peak resident memory. Structured receipts and encoded strings coexist, encoding and solver workspaces consume transient memory, and allocator overhead and caller-created copies need separate bounds. Event and outbox vectors still copy when a source-mutating snapshot is created; no general linear bound is claimed for arbitrary source histories. Sequential lifecycle qualification does not establish simultaneous-thread or allocation-failure behavior.

No complete accepted witness is truncated to fit. This is necessary but insufficient for full-calendar admission: the new representation still retains large thermal proofs for every accepted interval.

## Complete-horizon obstruction

Every accepted outer SDIRK receipt contains exactly three enthalpy coefficient intervals per thermal node per reconstruction leaf. Splitting preserves all three, including stationary curves. Each serialized interval object needs at least 21 bytes (`{"lower":0,"upper":0}`), and normalization retains the complete thermal serializer. Therefore a schedule with at least 128 thermal nodes, 1080 accepted thermal intervals and the default 32 outer leaves requires at least:

```text
3 × 21 × 128 × 1080 × 32 = 278,691,840 bytes
128 MiB history cap       = 134,217,728 bytes
```

The enthalpy coefficient objects alone exceed the cap by 144,474,112 bytes. This excludes both internal BE receipts, every other leaf field, states, requests, events and journal framing. More thermal nodes or accepted substeps increase the bound. For varying shapes the same bound is 63·Σ(Nj·Lj) bytes. This is source-backed integer arithmetic on the previously retained 1080-window count, with no new calendar or annual integration.

The bound applies to this representation and declared schedule. It neither rules out a different lossless store nor proves admission for a smaller leaf count. A complete horizon needs an explicit representation, retained and transient memory budget, work envelope and numerical qualification. Reducing proofs or changing the physical schedule merely to fit is not established by this work.

## First qualification outcomes

All three fixed drivers pass on their first execution. Their inventories, source files, executable hashes and journal reader were pinned beforehand. The full native library builds in a new directory with an explicit library-output override; the installed library remains `fa17d36b6759b88b524ddcbd822eb025b6454d6356fe585f799fedd11b949731`. The isolated library is `acc73c9118f1dd842b41419ca8ed62076281135c50c6a32877648b53a9a8bae4`.

| Qualification | Observed scope |
|---|---|
| Immutable forcing container | Retains 1081 prefixes for 1080 manufactured 128-value windows, with exactly 1080 shared vector objects and 1,105,920 bytes of unique main vector payload. All 726,319 repeated value/address/cap/lifetime assertions pass. No owner, graph, thermal or calendar execution. |
| Owner lifetime | All 72 checks pass: 14 prepares, six commit calls (three fresh, two replays, one stale), 16 builders, seven material calls, six calorimeter calls, one new one-second SDIRK interval, two internal BE calls and 64 scalar evaluations. |
| Byte budgets | All 31 checks pass: five prepares, three constructors (two accepted, one history-cap refusal), two material calls and zero calorimeter/thermal calls. Four builders are observed through returned owners; one additional failed-constructor builder is inferred from its source route. |
| Independent journal expansion | First reader passes 118,745 structural/value/byte assertions. It reconstructs three journal captures, comparing six complete receipt occurrences with both full histories and their original prepare receipts, plus final snapshots, fixed inventory operands, replay identities and exact journal byte counts. |

The byte fixture determines its limits by literal serialization before any owner or material call: source input 19,719 bytes; whole private slot 4096 bytes; tight request/receipt cap 365 bytes. With seven free retained-count slots, an existing 2378-byte diagnostic still correctly prevents another whole-slot reservation. Oversized source diagnostics preserve their observed work in either a retained 1942-byte normalized metadata record or explicitly exempt 1841-byte expanded metadata under the tight cap. All private and prospective journal reservations release at the tested final-reference boundaries.

The lifetime fixture's constructed journal is 5301 bytes. Its three committed records produce a 57,271-byte journal, unchanged by replay and a later uncommitted candidate. The independent reader checks complete nested thermal and material data for lossless preservation; it does not re-prove those components' numerical error bounds. Repeated container checks and JSON parser checks are not distinct physical-validation cases and should not be added to historical test totals.

All first driver and decoder processes exit zero with empty stderr, are reaped and leave no process group. The 191 C++/CMake source files remain pinned after execution. Two earlier syntax-only failures are retained: an older test serializer helper required a vector, and the new budget size witness attempted to default-construct a snapshot whose graph has no default constructor. The helper now accepts a range, and the size witness substitutes a literal normalized reference without constructing a graph. Corrected strict compilation passes before producer execution. No historical scientific suite, world generation or annual integration is rerun.

The [evidence package](../runs/layered-calendar-storage-review/README.md) retains the fixed protocols, sources, preimages, first outcomes, executable identities, independent reader and source-backed full-horizon bound.

## Remaining production work

The [geographic handoff](geographic_foundation_calendar_research.md) supplies an owned stabilized source. Physical layer W/H initialization, complete-calendar request and event planning, source/drainage ownership, general mass export, conservative liquid delivery, annual error qualification and versioned rebuilding of downstream products remain open. Generated ice still uses the existing annual diagnostic. The installed native library and API/viewer behavior are unchanged by this isolated storage qualification.

## Subsequent initialization and storage design

The [supplied-state initializer](finalized_layered_state_research.md) now provides explicit canonical W/H or tagged equilibrium T/liquid profiles on that foundation. Its first controls and one fresh foundation integration pass, with independent exact conversion/binding checks; it performs no thermal evolution or full-calendar admission. Physical profile derivation and spin-up remain separate work.

The [complete-horizon storage plan](layered_full_horizon_storage_plan.md) preserves the fixed full-year requirement and proposes external complete-proof retention with separate disk, live-memory and work reservations. A binary interval does not remove the capacity problem: mandatory outer H coefficients alone still require 202.5 MiB for 128 nodes, 1080 intervals and 32 leaves. The plan identifies the codec, complete schema sizing, streaming owner APIs, lifetime accounting and durable I/O failure controls needed. None of those new storage mechanisms is implemented or qualified by this plan; the v5 evidence above remains frozen.
