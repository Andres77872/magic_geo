# Complete-horizon layered proof storage: proposed contract

Date: 2026-09-12. Status: **owner integration proposed; codec and generic byte-store foundations implemented separately; no full year admitted**.

The later [external proof codec/store qualification](layered_external_proof_storage.md) implements the complete thermal binary representation and preallocated byte storage. Its generic maximum-shape bound is 3,069,231 bytes per receipt, with independent caps of 32 leaves in each BE stage and nine coefficients in each H/T/R polynomial. The narrower producer-specific example below retains its original scope. The new components do not yet implement this plan's stored owner, complete nonthermal metadata, live-memory admission or calendar integration. The remainder of this page is the original source-only plan; its archived version remains unchanged.

This is a read-only implementation plan. No model, serializer, calendar, numerical auditor, test or historical scientific run was executed. Only source reads, file hashes and elementary integer sizing were used. Exact observed sources are in [FULL_HORIZON_STORAGE_SOURCE_PINS.json](../runs/finalized-layered-state-review/work/FULL_HORIZON_STORAGE_SOURCE_PINS.json), SHA `89745228adeeadfae702272245b0732b9000cf469817be5fb54ba0ab4c7de3a2`.

## Decision

Add an explicitly selected **external retained-proof store**, with complete pre-work disk, live-memory and attempt reservations. Keep the current v5 in-memory JSON owner and its 128 MiB history limit unchanged. The smallest useful new representation is a schema-ordered binary thermal object plus streamed, lossless normalized owner metadata. It preserves every outer SDIRK coefficient and both complete BE receipts. It does not depend on compression, repeated values, stationary forcing, recomputing coefficients during decoding, fewer leaves, larger error budgets or fewer physical windows.

This is not admission of a year. A complete admission needs the finalized source/graph and calendar envelope, a reviewed size visitor, a live-allocation bound and provisioned external capacity. At least 128 nodes is a lower bound, not a resource upper bound. No numerical or work-completion claim follows from enough storage.

Even a simple binary interval costs 16 bytes. Thus outer enthalpy coefficients alone require

`3 × 16 × 128 × 1080 × 32 = 212,336,640 bytes = 202.5 MiB`.

This exceeds 128 MiB before outer temperatures/residuals, two BE stages, graphs, source histories or metadata. The existing JSON lower bound is 278,691,840 bytes. Merely changing JSON numbers to binary does not solve the current cap. A separate external-storage policy must be explicitly supplied and admitted; neither its capacity nor the meaning of the existing cap may change silently.

## Current seams that must change

The current [owner](../cpp/src/engine/layered_ice_owner.cpp) has three simultaneous retention mechanisms:

* `Record` owns the request key, complete normalized JSON string and a shared pointer to the complete structured receipt (lines 156–173).
* Each committed record remains in `Impl::records`; `history()` returns every complete receipt, and `journal_json()` concatenates every string (lines 273–289).
* `prepare()` serializes the full record only after all physical work, then checks its size. Commit retains the complete record and final snapshot (lines 519–575).

The existing lease fix correctly follows returned payload lifetime, but measures wire bytes, not these objects or temporary encodings. File-backing `Record::encoded` alone would retain the complete structured proof history in RAM. The new mode must keep lightweight record handles in its committed index, evict the completed rich receipt after sealing, and expose bounded read views rather than an unbounded `history()` or whole-journal string. Legacy APIs stay available only in the existing mode or as explicitly budgeted expansion operations.

The forcing tree already shares immutable vectors and prefix nodes. Keep its actual prefix identity semantics. Do not rebuild forcing values from a climate model during replay. Current normalized initial-snapshot/geographic references also remain valid. Event/outbox histories and component graph copies are not automatically deduplicated by these changes: their full remaining cost belongs in admission.

## Store format and losslessness

Proposed storage identities are `layered_external_proof_store_v1`, `layered_external_record_v1`, and `layered_thermal_binary_v1`. A separately declared owner storage successor is required; no old `lossless_layered_owner_journal_v1` document should secretly contain unresolved external thermal records.

Use append-only framed records, a bounded index and an immutable header binding the complete schema, native source identity, owner/epoch identity, seed, geographic mapping and predeclared calendar/policy digest. Each frame carries a version, record kind, attempt number, request identity, base/target revisions, payload lengths and digest. State-order links are explicit and distinct from physical file order. Accepted, refused, replay and indeterminate-I/O outcomes are distinct record kinds. References resolve only within the admitted store; no arbitrary external path dereference is permitted.

The thermal binary payload has an explicit field order, no C++ padding or native-endian struct dump:

* binary64: exactly eight little-endian representation bytes; preserve signed zero and all diagnostic nonfinite sign/payload bits without evaluating them;
* signed integer: fixed-width signed 32-bit; counters: unsigned 64-bit; checked conversions, never native `size_t`;
* bool: one byte, strictly 0 or 1; optional: one presence byte followed by the value if present;
* vector: unsigned 32-bit count followed by all elements in original order; byte string: unsigned 32-bit length and exact original bytes;
* interval: two binary64 operands, 16 bytes, including signed zero/slack; polynomial: its actual coefficient count and every interval, without degree trimming;
* every availability flag, partial prefix, work count, stage request, raw candidate, defect and final-state presence from the current SDIRK and BE structures is retained. Static model strings are determined by the exact schema/model ID, including pure-water dispatch, rather than guessed by a decoder.

The owner metadata writer preserves the existing normalized information: exact request/replay-key operands, initial snapshot reference, final graph, appended forcing, material/remap/absorption/topology receipts, domains, quotas, ledger, outbox and work. Only `thermal` becomes an explicit typed binary-object reference. Initially keep the remaining metadata lossless JSON to avoid simultaneously redesigning every material codec. All of its references, lengths and bytes count. Content sharing is an optional later optimization: the capacity proof assumes no favorable equality or compression.

The proof reader decodes recorded values; it does not call the SDIRK/BE solver, graph builder, calorimeter, remapper or forcing/calendar producer. Old expanded JSON can be emitted as a bounded stream using the frozen ordering, byte-string escaping, finite-number formatting and nonfinite tags. Exact JSON-byte equivalence is a separate required qualification on retained receipts. It is not established by this design. Hashes bind content/integrity, not authenticity against a hostile writer; exact request identity checks must retain bytes, not trust hash equality alone.

## Explicit byte algebra

All additions and products use checked unsigned arithmetic. Overflow, an unknown shape or a missing string bound causes **pre-work admission refusal**. A schema size/count visitor and the actual bounded writer must share field coverage, but independently tested expected sizes must detect omissions. The visitor traverses declared shapes and operands, never a numerical producer or a serializer that constructs the full output string.

For the binary field encoding above:

`B(f64)=8`, `B(i32)=4`, `B(u64)=8`, `B(bool)=1`, `B(interval)=16`,

`B(string_s)=4+s`, `B(vector_n(T))=4+Σ B(Ti)`,

`B(optional(T))≤1+B(T)`, `B(struct)=Σ B(fields)`.

This counts all stored operands, even values whose normal JSON representation is unavailable/null. Their flags still govern public availability. A nullable-vector representation can be smaller but is not needed for the bound.

Let N bound every thermal node vector, E bound every thermal edge vector, S bound sweeps for either BE stage, and L=32 be the declared outer leaves. Partial/refused numerical records obey the same shape bounds. The current source gives:

| Object | Conservative binary payload bound in bytes |
| --- | ---: |
| Full mesh request | `97 + 48N + 16E` |
| Mesh field | `20 + 64N + 16E` |
| One complete BE leaf | `41 + 96N + 16E` |
| One BE receipt, including request, one leaf and at most S+1 sweep entries | `512 + D_BE + 256N + 48E + 20(S+1)` |
| One complete outer SDIRK leaf | `33 + 275N` |
| Full SDIRK receipt including both BE receipts | `1377 + 608N + 112E + 40(S+1) + L(33+275N) + D_outer + D_BE1 + D_BE2` |

D is the maximum combined raw byte length of failure-code and detail strings for that receipt; their length prefixes are already counted. These bounds assume no nested per-object frame header. Add the chosen outer frame overhead separately. The BE bound deliberately permits S+1 entries in each stage, although the actual two stages share a stricter sweep allowance. Scalar evaluations do not each add a retained scalar record; the stored sweep history and counters still count.

The outer leaf bound follows directly from at most 3 H, 3 T and 9 residual coefficient intervals per node, three polynomial length fields, the temperature-branch string (at most 11 bytes for `phase_range`), one absolute residual bound and the leaf/vector framing. H keeps three coefficients even for a stationary curve. The two BE stages each keep one linear reconstruction leaf. These witnesses are additional to the outer leaves, not a replacement for them.

For illustration of the formula only, Nmax=128, Emax=1024, Smax=128, L=32 and each Dmax=4096 give at most **1,338,793 thermal bytes per attempt**, or **1,445,896,440 bytes for 1080 such attempts**. These N/E/D bounds are manufactured resource operands, not the actual forthcoming graph, a promise that the year takes one attempt per window, or a complete owner-store requirement. Owner metadata and every extra attempt still add capacity.

For the remaining JSON metadata, a conservative shape visitor uses:

* a raw string of at most s bytes: `2+6s` encoded bytes;
* finite or nonfinite numeric token: at most 64 bytes under the explicitly pinned number codec; integer token at most 20, boolean at most 5, null 4;
* array: `2+Σ(1+B(element))`, including a safe extra comma allowance;
* object: `2+Σ(B(quoted_key)+2+B(value))`.

Every metadata field in `receipt_json`, the normalized snapshot writer and each nested component writer must appear in this shape visitor. Its input bounds include columns, active and deep inventories, edges, geometry conversion intervals, donors, allocations, selected parcels, domains, event-ID bytes and all copies of initial/final component graphs. It must include the escaped replay-key string, which can itself contain a full request encoding. Do not silently assume all metadata is O(N), or that current event/outbox copying disappeared. Exact source requests can be sized before work; future graph/receipt fields require declared maxima. Undefined/unbounded exception `what()` text is a remaining bound obligation, not permission to truncate it: accepted-proof capacity must be proved, and unexpected unbounded diagnostics must fence the run as retention-incomplete.

For each permitted attempt slot a, let Ma be the resulting metadata upper bound, Qa the thermal bound (zero for source-only work), and Ha the fixed framing/hash/index allowance. Then

`Ra = Ha + Ma + Qa`.

If the selected frame format adds chunk headers, include `chunk_header_bytes × ceil((Ma+Qa)/chunk_payload_bytes)` explicitly. A first implementation may use one frame with incremental hashing and a fixed 64 KiB I/O buffer, avoiding per-chunk headers. The writer checks remaining frame capacity before each write and records actual bytes separately from reservations.

The complete retained-store reservation is

`B_required = B_header + B_seed + B_calendar_manifest + B_index`

`             + Σa∈all_permitted_attempt_slots Ra + B_commit_markers + B_emergency`.

Both accepted and refused attempts are included. Aliases/replays reference an existing proof and add only their bounded observation/commit marker, never an invented new thermal receipt. Do not add C extra receipt extents if all simultaneously in-flight attempts already have slots in this sum; add such extents explicitly if the slot policy otherwise omits them. A shared coarse maximum `Amax × Rmax` is safe when an exact per-window shape envelope is unavailable, but its real capacity cost must be published.

## Full-calendar admission

Before any builder/material/thermal call, require one immutable manifest with all 1080 forcing-window boundaries and original forcing/source identities; the actual fixed tolerance/error shares; L=32; finite Nmax/Emax after every permitted topology operation; source-only transaction slots; maximum accepted substeps per window; maximum attempts/refusals; maximum simultaneous preparations and retained read views; and all source, outbox, string and work caps.

Admission proves complete-window coverage is representable and the resource envelope fits; it does not prove that any solver step will be accepted. Every shortened attempt and rejected prefix uses its own reserved slot. No failed attempt consumes physical time or sources. Successful substeps must retain actual carry and cover each original source window; no window may be dropped to satisfy storage. A later actual shape exceeding the predeclared envelope refuses before its physical work, preserving the last accepted state and labeling the horizon incomplete.

Existing count gates remain relevant even after external storage exists:

* owner hard limits permit at most 4096 prepares and 2048 commits. At least 1080 accepted thermal intervals plus source-only/remap/topology commits must fit. Internal BE stages are not owner commits;
* forcing storage counts geographic vectors, not layered thermal nodes. 1080×128 values fit the current default 524,288-value allowance; this does not bound a potentially larger thermal graph;
* the current consumed-event cap is 8192 and pending-outbox cap is 1024. If a future schedule has one distinct import per geographic cell per window, 138,240 events would exceed the former. This is a conditional cardinality warning, not a claim about an as-yet-unprovided physical event plan;
* max node-leaves, sweeps, scalar work, record size and retained private views must also fit. More disk does not relax them.

External bytes, retained decoded bytes and total peak-live bytes are separately named policy inputs. The admission receipt publishes each requested limit, each computed requirement, all shape operands, source hashes and failure reason. No new large capacity is selected automatically. The present 128 MiB JSON-history contract cannot be reinterpreted as a disk limit or a resident-memory limit.

## Ownership and API seam

Suggested new internal interfaces, names provisional:

```cpp
struct LayeredCalendarStorageEnvelope;  // complete windows/slots/shapes/work
struct LayeredExternalStorePolicy;     // explicit file/live/view/I/O limits
struct LayeredStorageAdmission;        // checked requirements + typed refusal
class LayeredProofStore;               // unique store/epoch identity, no copies
class LayeredProofReservation;         // opaque bounded attempt extent
class LayeredProofHandle;              // immutable location/length/digest lease
class LayeredProofReadView;            // bounded scoped decoder lease

LayeredStorageAdmission admit_layered_calendar_storage(
    const LayeredCalendarStorageEnvelope&, const LayeredExternalStorePolicy&);
// Open/provision only after admission; reserve all required extents/index slots.
// begin_attempt -> bounded writer -> seal -> immutable ProofHandle.
// Stored preparation returns ProofHandle + optional opaque candidate.
// read(handle, decode_budget) -> bounded view; stream_legacy_json(handle, sink).
```

Prefer a separate stored-owner mode/API rather than changing the meaning of `LayeredIceOwnerCandidate::receipt()` or `history()`. A stored candidate holds owner/base identity, its sealed proof handle and the private final snapshot needed for commit. It does not pin every thermal vector. Successful commit changes the accepted state/source/outbox bundle and a lightweight proof index together. The resident index is reserved before work. Exact replay resolves the retained request/record without executing physical components; a conflicting ID remains a conflict.

Source IDs, raw forcing, exact clock operands, retries, work observations and partial failure receipts are append-only evidence. Full rejected numerical diagnostics remain retained even when their candidate is not accepted. Unused reserved capacity may be released only without weakening the already admitted remaining-horizon envelope. An outbox delivery acknowledgement is a distinct future physical transaction, not an I/O record being flushed.

## Durable commit and I/O failure

Prepare writes and seals a complete immutable proof before returning a candidate. No source/state is published merely because a partial file exists. Short writes, checksum failure, exhaustion or lost storage ownership refuse and leave accepted state untouched; observed work and bounded fatal metadata remain available. Never silently fall back to uncharged RAM or retry a physical step after storage failure.

A durable mode needs an explicit commit protocol: under the owner lock revalidate owner/base/geography, persist a commit marker referencing the sealed proof and prior committed head, flush under the declared filesystem policy, then perform an allocation-free in-memory publication. Crash recovery follows only complete verified markers and their immutable proof objects. An I/O error after a commit marker may have reached storage is **indeterminate**, not a safely retryable refusal. Fence the owner and require recovery to determine the accepted head before any further source consumption.

This protocol is a missing implementation/qualification obligation. A process-atomic but non-crash-recoverable first variant is possible only if explicitly declared; it cannot claim durable transaction recovery. Free-space observation alone does not guarantee capacity. Provision a dedicated file/volume reservation with checked preallocation where supported, retain its identity, and still handle runtime I/O failure. A sparse file or a hopeful compression ratio is not reserved physical storage.

## Peak live memory and witness

The live-memory contract must remove retention proportional to completed thermal intervals. Keep only the current accepted graph/state, bounded in-flight work, bounded candidate final snapshots, small record/event/forcing indexes and bounded read views. Full older proof objects live in the external store. Reading all receipts into a caller vector is outside this mode and must refuse without a separate complete reservation.

Define source-backed maxima: G for one graph/snapshot including event/outbox storage; I for immutable source/forcing/index storage; W for one solver/component workspace; R for one decoded rich receipt; P for one candidate final snapshot; C for concurrent computations; K for retained candidate snapshots; V for decoded read views; Q for bounded I/O buffers. Then a conservative payload/allocation target is

`M_live_required = M_fixed + I + G + C(W+R+Q) + K(P+handle) + V(R+Q) + M_emergency`.

Every alias shares its lease until the last reference is released. Caller-created copies are either prevented by the new views or charged to an explicit allocator; arbitrary user copies cannot be included in a library-only memory guarantee. Current structured vectors and `std::string` temporaries are not all routed through a limiting allocator, so **this source currently does not prove M_live_required**.

The SDIRK workspace must count both complete BE receipts, the copied second-stage request, retained outer leaves, node/edge fields, graph reconstruction inputs and allocator/vector overhead. During dyadic splitting, old and new curve levels coexist: the last split can retain L+L/2 H curves; each has N vectors of three intervals. During certification, one current heating-polynomial workspace coexists with completed T/residual leaves. JSON/codec expansion must be streamed; retaining both a full rich receipt and a complete expanded string in addition to these objects defeats the proposed peak bound.

Use a bounded allocation resource for all new store/decoder allocations and a reviewed allocator/shape model for unchanged solver workspaces, or explicitly keep the latter as an unresolved qualification gate. The live witness must record allocated/capacity high-water marks per category and process peak RSS separately. RSS includes libraries, stacks, allocator metadata and other runtime effects; the codec payload formula is not an RSS theorem. OS address-space/process limits provide a final refusal barrier, not a success guarantee. No memory compression/cache-eviction promise substitutes for this accounting.

## Smallest decisive qualification before any horizon run

All proposed controls below are future work, not executed here. Freeze schemas, limits and expected outcomes before any new physical run.

1. Pure codec tests on already retained accepted/refused SDIRK/BE/owner receipts: byte/bit exact decoding and streamed legacy expansion, every coefficient/flag, signed zero, nonfinite payloads, empty/partial arrays, source IDs and invalid-byte identifiers. No solver rerun.
2. Manufactured maximum-shape objects and adversarial incompressible bits: writer bytes never exceed the independent formula. These are storage objects, not simulated climates. Count overflow, missing shape/string caps and one-byte-short capacity refuse before any physical callback.
3. A 1080-slot manufactured store at N≥128/L32, including explicitly reserved source/retry slots: sequential seal/read/release shows bounded live high-water marks and complete evidence retention. This is a storage stress witness only; no calendar/model execution or annual accuracy label.
4. Deterministic short-write/disk-full/truncated/checksum/flush-failure controls across prepare/seal/commit boundaries. Verify owner/source/outbox state, indeterminate-commit fencing, recovery scope and last-reference lease release. Concurrent aliases/views obey the declared bounds.
5. One small newly authorized owner integration, only after codec/resource controls and independent review, must exercise actual numerical receipt capture, failed attempt, commit and replay through the store. Old complete proof bytes remain available to the independent reader; no historical scientific suite needs rerunning.

The necessary production edits are consequently a bounded store/codec module, a complete schema size visitor, streaming metadata/legacy writers, stored-owner candidate/history interfaces and commit/recovery/error handling. No thermal equation, source, time partition, leaf count or tolerance needs to change for this storage increment. Full-horizon numerical admission and measured practical completion remain separate and open.
