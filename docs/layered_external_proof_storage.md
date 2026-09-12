# External layered proof codec and storage

Status: 2026-09-12. The complete thermal-proof codec and a generic Linux proof-byte store are implemented as internal components. The first fixed codec, store-control and 1,080-record storage qualifications and their independent retained-data audits passed. These components do not yet provide a stored layered owner or admit a complete physical solar year.

This increment follows the [full-horizon storage plan](layered_full_horizon_storage_plan.md). It preserves the existing numerical witnesses: both backward Euler (BE) stage receipts, all outer SDIRK2 leaves and polynomial coefficients, requests, fields, sweeps, partial results and work counters. No thermal equation, source policy, leaf count or numerical error budget changes here. The codec qualification used retained data and manufactured structures, with zero physical calls and zero historical numerical reruns. The installed `src/magic_geo/libmagic_geo_native.so` remains SHA-256 `fa17d36b6759b88b524ddcbd822eb025b6454d6356fe585f799fedd11b949731`; the new library and test builds are isolated.

The [codec interface](../cpp/src/engine/enthalpy_mesh_proof_codec.hpp) provides an exact checked size visitor, a complete maximum-shape bound, streaming encoding, bounded decoding and streamed legacy JSON expansion. Its 24-byte frame header binds magic, version, record kind and exact body length. Integers and binary64 representations have fixed little-endian encodings; vectors and strings retain explicit counts. Binary transport preserves signed zero, nonfinite representation bits, raw string bytes and every structured backing operand even when an availability flag hides that operand in legacy JSON. It is a representation codec, not a validator of the receipt's physics.

The decoder checks each count against the selected shape, remaining frame bytes, aggregate vector-element budget and decoded-payload budget before allocation. Unknown schemas, invalid boolean bytes, impossible lengths, truncation and trailing bytes refuse. Source and sink callbacks must transfer their entire supplied span or throw; callback spans are at most 65,536 bytes. Encoding and legacy expansion check the applicable output budget before invoking the sink. Expansion from a binary frame decodes one bounded complete receipt and then streams JSON. It avoids a complete expanded JSON string, but still retains that decoded structure. The decoded-payload counter covers the root object, requested vector elements and string storage including terminators; it excludes allocator overhead, excess capacities, other workspaces, caller copies and process RSS.

The retained codec outcomes are:

| Evidence | First retained result |
| --- | --- |
| Native data-only qualification | 324 checks, zero failures, 44 fixtures |
| Previously recorded JSON receipts | 40 exact original-byte expansions |
| Manufactured fixtures | Complete, empty, hidden/partial operands, and independent maximum shape |
| Structured fixture round trips | 44 binary bit-preserving round trips |
| Independent projection comparisons | 88 visible and deliberately promoted projections |
| Maximum source/sink callback span | 65,536 bytes each |
| Maximum-shape binary frame | 3,069,231 bytes |
| Maximum-shape decoded payload accounting | 3,448,430 bytes; not RSS |
| Maximum-shape expanded legacy JSON | 12,258,437 bytes |

The native controls also passed malformed magic/version/kind/boolean, truncation/trailing/count, decoded/frame/element/node cap, pre-sink output refusal and checked-overflow cases. The native process and independent audit each started once, exited zero, produced empty stderr, were reaped and left no process group. Their recorded elapsed times were approximately 2.309 and 2.254 seconds. This is a codec result, not a rerun of the numerical certificates stored inside the fixtures.

Historical JSON cannot disclose backing values that its original availability rules omitted. The retained-data fixture preparation supplies those missing fields explicitly as defaults; the audit does **not** claim to recover their historical C++ contents. The separate manufactured hidden/partial fixture exercises preservation of supplied nondefault backing values and nonfinite bits. Likewise, the promoted projections are diagnostic comparisons of recorded structures, not newly accepted physical results.

The generic maximum-shape calculation uses independent caps, including every optional object present and every bounded vector full. Let `N` bound nodes, `E` edges, `K` sweep entries per BE stage, `B` leaves per BE stage, `L` outer leaves, `P` coefficients in each of the three polynomials, `M` bytes in each code/detail string and `G` bytes in each temperature-branch string. With all arithmetic checked:

```text
request      = 97 + 48N + 16E
BE_leaf      = 41 + 96N + 16E
BE_receipt   = 112 + 2M + request + 112N + 16E + 20K + B*BE_leaf
outer_leaf   = 33 + N*(24 + G + 48P)
framed_SDIRK = 24 + 140 + 2M + request + 48N + 2*BE_receipt + L*outer_leaf
```

The manufactured envelope `N=128, E=256, K=129, B=32, L=32, P=9, M=4096, G=11` gives exactly **3,069,231 bytes per framed receipt**. The retained maximum-shape fixture reaches those independent caps. This is broader than the current producer's three H coefficients, three T coefficients, nine residual coefficients and one leaf in each BE stage. It must not be confused with the narrower, producer-specific example in the earlier plan. The 128 thermal nodes in this storage fixture also do not establish a bound for a future 128-geographic-cell layered graph; multiple layers can make the actual thermal node count larger.

The [store interface](../cpp/src/engine/layered_proof_store.hpp) is deliberately generic. A sealed blob can contain accepted or refused evidence, or arbitrary caller-selected bytes. `begin()` reserves a single-use attempt; a move-only writer appends, seals or aborts it. A copyable immutable handle permits bounded readers, including after the store wrapper is destroyed. Reader and writer buffers stay charged while their leases are live. Aborted and indeterminate attempts consume their slots permanently. Successful sealing publishes a complete byte handle, without advancing an owner, physical state or commit revision.

Every store policy is explicit: provisioned bytes, attempt count, maximum payload, I/O operation allowance, reader/writer counts and buffer size. Structural ceilings are 1,048,576 attempts, 1 GiB payload per attempt, 2^40 I/O operations, 64 simultaneous readers and writers, and 1 MiB per buffer; the file extent must fit signed 64-bit offsets. Store and source identities are nonzero caller-supplied 32-byte values. Handle admission additionally requires the same live store state. The store supplies no identity authentication or physical source-binding policy on the caller's behalf.

The extent layout is a 256-byte header and, per attempt, a 128-byte begin frame, the full reserved payload capacity, a 128-byte seal/abort footer and a 128-byte commit marker. Thus a store for 1,080 maximum-shape blobs requires exactly:

```text
256 + 1080*(3,069,231 + 384) = 3,315,184,456 bytes
```

This is complete capacity for those 1,080 blob slots, with no compression assumption. It excludes a future owner's seed, calendar/source manifests, nonthermal metadata and additional source, refused or retry attempts. The qualified data-only horizon control provisions precisely this extent, one reader, one writer, a 65,536-byte I/O buffer and 500,000 I/O operations. It repeats one fixed manufactured blob, retaining one input blob and a handle index in RAM. Each slot is independently written, sealed, committed and fully read; the first and last are revisited before and after wrapper destruction. Repetition here exercises storage volume and lifecycle, without executing or representing 1,080 physical timesteps.

Creation exclusively opens a new file and preallocates the entire admitted range before returning an attempt writer. It retains failed files and never replaces an existing path. The implementation checks the direct error return from `posix_fallocate`; preallocation reserves file space rather than merely setting a sparse length. Later non-capacity I/O failures still require handling. [Linux `posix_fallocate(3)`](https://man7.org/linux/man-pages/man3/posix_fallocate.3.html)

Buffered appends count copied logical bytes separately from positive `pwrite` return bytes. A failing partial write retains its observed prefix and fences the store; it does not create a sealed proof. Oversized appends reject that entire new append and terminate the prior admitted prefix with an abort when its I/O succeeds. Bounded hooks can reduce real syscall sizes or inject errors, including `EINTR`; retries consume the unchanged I/O allowance. Positional short reads/writes are handled explicitly, and the file is not opened with `O_APPEND`. [Linux `pread(2)` / `pwrite(2)`](https://man7.org/linux/man-pages/man2/pread.2.html)

Header/frame and full payload integrity use CRC64-ECMA-182, an accidental-corruption check rather than hostile-writer authentication. A reader verifies the immutable header, begin and seal frames; payload verification completes only at EOF. Earlier delivered bytes cannot authorize physical publication. `commit(handle, previous_sequence/base/final)` separately writes and flushes a marker before advancing the store's in-memory head. Exact replay of the same committed handle and linkage returns its original sequence, including after later commits, without another write. Changed linkage and stale siblings refuse. Ambiguous commit-marker write/flush failures leave the in-memory head unchanged, set `commit_indeterminate` and fence further use. That state is not a safely retryable physical refusal.

The implementation performs file and parent-directory `fsync` at creation and file `fsync` at its subsequent boundaries. Directory synchronization matters separately from file synchronization. The claim is this declared protocol, with reported filesystem identity; there is no open-existing-file recovery API or crash-recovery qualification. A tmpfs result cannot establish persistence across unmount or reboot. [Linux `fsync(2)`](https://man7.org/linux/man-pages/man2/fsync.2.html), [Linux `tmpfs(5)`](https://man7.org/linux/man-pages/man5/tmpfs.5.html)

**Store-control result: PASS on the first fixed run.** All 128 checks passed, with 39 creation attempts, 61 typed-error observations and 33 statistics records. The actual direct API counts were one size query, 38 begins, 28 appends, 22 seals, one explicit abort, 15 commits, 20 reader opens and 17 reads. Codec, owner and model calls were zero. The independently frozen reader passed 7,247 assertions and verified all 23 retained files, including the unchanged existing sentinel and incomplete or intentionally damaged files. Its separate byte/header self-test passed 868 assertions and rejected 22 mutations. Source and fixed fixtures were unchanged after execution began.

These controls covered exact/short capacity and identity admission, unchanged existing files, real short I/O, the standard CRC vector, lease/abort/replay/lifetime behavior, corruption, partial failure, marker ambiguity and bounded interruption. The positive-prefix failure retained three successfully written payload bytes while reporting eight logical appended bytes. The independent audit binds file bytes, counters and native check outcomes; it is not a separate process-lifetime observer. Native controls and the file audit each started once, exited zero, produced empty stderr, were reaped and left no process group. The tested filesystem was reported as volatile tmpfs, so the result does not establish persistence across reboot.

**1,080-record storage result: PASS on the first fixed run.** All 1,087 native checks passed and all 1,080 distinct slots were committed. The first independent audit passed 221,679 assertions, verified every payload's SHA-256 and all header/frame/commit links, and streamed the entire 3,315,184,456-byte file with read spans no larger than 65,536 bytes. Native execution took approximately 16.883 seconds and the audit 4.323 seconds. Each process started once, exited zero with empty stderr, was reaped and left no process group. Neither executed a codec, owner or physical model.

| Retained horizon measurement | Value |
| --- | ---: |
| Actual preallocated file extent and positive written bytes | 3,315,184,456 bytes |
| Complete payload bytes across 1,080 slots | 3,314,769,480 bytes |
| Store I/O operations before wrapper destruction | 111,343 |
| Final hook operation number after the two surviving-handle reads | 111,443 |
| Final read bytes, including frame rereads, derived from the bound counters | 3,327,601,412 bytes |
| Peak live store I/O buffer payload | 65,536 bytes |
| Store slot-index payload | 69,120 bytes |
| Retained handle-vector payload | 43,200 bytes |
| One retained input blob | 3,069,231 bytes |
| Driver verification buffer | 65,536 bytes |
| Observed native process `ru_maxrss` | 10,728 KiB |

The final complete statistics snapshot precedes destruction of the final store wrapper; subsequent reads and the hook's final operation number are recorded separately. Buffer/index counts are payload measurements and `ru_maxrss` is an observed process high-water mark. The 3.315 GB tmpfs backing store and kernel memory are outside that process-RSS comparison. These figures therefore do not prove a total-memory limit, a full-owner live budget or durable storage. The retained file SHA-256 is `195700a7b6cd59d60c2fa8459e93c582895cb163d25782fe6bfca027a296c92b`.

The independent stored-owner design review remains a required integration guide, not an implemented successor. The following gates are still open:

1. A separate stored-owner API must replace retained rich thermal receipts with opaque proof handles and bounded decode/read views. Retaining `Record::receipt` while also writing it externally would keep the existing RAM growth. Candidate base/final snapshots, diagnostic aliases and readers need explicit lifetime accounting.
2. Complete nonthermal metadata needs a lossless schema, streaming writer and checked maximum-size visitor. This includes exact request/replay-key bytes, graph/source/epoch references, forcing, clock, mass/enthalpy/error state, all material/remap/absorption/topology receipts, domains, quotas, ledger, outboxes, consumed IDs and work. A codec frame is not a complete owner transaction. Arbitrarily long exception messages and allocation-failure diagnostics need an explicit bounded failure policy.
3. Store commit and physical publication must form one owner-visible accepted bundle. Owner/base/geographic/source identity, exact replay, stale siblings and preallocated index/state replacement must be rechecked before the marker, followed only by nonthrowing publication. Store ambiguity must fence the owner too. Codec callback errors normalize underlying exceptions, so integration must preserve the store's separate fencing/ambiguity state. Recovery remains a separate unimplemented contract.
4. Complete live-memory admission must cover current and privately retained graphs, forcing/event/index state, simultaneous component and solver workspaces, both BE receipts, decoded views, buffers, temporary copies and failure metadata. Wire size and requested decoded-payload counts do not prove allocator capacity or peak RSS. The current 128 MiB normalized in-memory history contract remains a different storage mode.
5. Full-calendar admission needs the actual complete source/forcing schedule, graph and metadata bounds, source-only operations, accepted substeps, retries/refusals, diagnostic and I/O budgets, and all existing owner work/cardinality limits. Hard limits of 4,096 prepares and 2,048 commits, forcing storage, consumed IDs, pending parcels and thermal node-leaf work still apply. More external bytes neither changes these limits nor supplies missing physical source/publication policy. Only after those gates and a new short stored-owner integration qualification can a complete physical-calendar experiment be admitted.

The [portable evidence archive](../runs/layered-external-proof-review/README.md) catalogs `CODEC_IMPLEMENTATION.md`, `STORE_IMPLEMENTATION.md`, `STORED_OWNER_SOURCE_DESIGN.md`, frozen protocols/fixtures, native and independent-reader outputs, process records and the full retained store file. Original staging evidence under `/tmp/layered-external-proof-review` and all earlier frozen packages remain intact. Codec stdout SHA-256 is `d4eab41318a0618b8ef05b18d1c49daa5da1c1f12e92ba697f8b49dc0b184ea3`; codec audit stdout is `734e72dbda08b029bf721440b636dae330a4b4573b3c534383c7b0522fe44fb1`; store-control stdout is `debc226794bc7cd0ec68770f1df637b86f2ec222fb76b2e9eb05ea15b7877143`; store-control audit stdout is `2398fdf21498a6029e5de80865ba682dedb26c4b223f16a3e4f3199d3f55e4e6`. Horizon stdout is `29c10ef9b326eb660f3390adc4ee63284cafa2b424d3cf47891b846405f3d496` and its independent audit stdout is `63261981c43f5b6e33e9566b4fc761b7ed1c1dc577843635074ef65ac611758b`. The source-only stored-owner design note is `8ed826010da804c94141ffb29c5dc36b6215e112433713f6898a12f46e91b40b`.
