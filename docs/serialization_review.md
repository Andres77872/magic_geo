# Serialization deep review and optimized world format

## Outcome

JSON remains the default, stable interchange format. The project now also has:

- a safe, versioned `.mgeo` world container backed by MessagePack;
- additive native MessagePack generation functions using pointer-plus-length
  buffers;
- zero-copy decoding of those native buffers in Python;
- automatic `.json`/`.mgeo` loading in every CLI command that consumes a
  generated world; and
- a reproducible serialization benchmark.

World content now uses schema 2 after retiring schema-1 compatibility fields.
Both transports produce the same schema-2 Python dictionary after the native
serializer's established rounding rules have been applied.

## Audit findings

Generation previously crossed two expensive JSON boundaries:

```text
C++ simulation
  -> compact native JSON
  -> malloc + C ABI copy
  -> UTF-8 copy + Python json.loads
  -> ordered Python enrichment pipeline
  -> sorted, indented final JSON
```

The native boundary is implemented by `serialize_world` in
`cpp/src/engine/world_serialization.cpp`, copied in `cpp/src/c_api.cpp`, and
decoded in `src/magic_geo/native.py`. The final object is much larger because
`src/magic_geo/api.py` adds all Python-derived layers before
`src/magic_geo/io/json_writer.py` writes it.

The final 4,096-cell reference artifact contains only the portable value model
needed by MessagePack: string-keyed objects, arrays, UTF-8 strings, signed and
unsigned integers, binary64 floats, booleans, and null. It has a maximum
observed nesting depth of eight. Object identity is not part of the JSON
contract, so repeated references are encoded as repeated values rather than
Python aliases.

Important compatibility constraints found during the review:

- `schema_version` remains the world-content schema. Current generation emits
  version 2 after retiring schema-1 compatibility fields; it is independent of
  the `.mgeo` container version.
- Critical native numeric fields already use binary64 round-trip JSON text;
  other fields deliberately use configured decimal precision. The optimized
  native path transcodes that same JSON document, so downstream calculations
  do not silently receive different precision.
- Booleans must not become integers, negative sentinel IDs must remain signed,
  and the unsigned 64-bit range must remain available.
- Array order, empty collections, CSR offsets, and serializer key order remain
  unchanged.
- Existing `CConfig`, `CConfigV2`, and `CConfigV3` layouts and all JSON symbols
  remain untouched. Binary functions are additive.

The audit also found that native JSON string escaping omitted `\b`, `\f`, and
other U+0000–U+001F control characters. That path now emits valid JSON escapes;
ordinary generated JSON is byte-for-byte unaffected.

## Why MessagePack

MessagePack matches the existing JSON-shaped model without introducing a large
generated schema. Unlike pickle, it is language-neutral and decoding it cannot
execute arbitrary Python code. Unlike a columnar format, it can losslessly
carry the heterogeneous full world, including all histories and nested model
metadata.

A typed columnar result handle could eventually avoid building the intermediate
JSON document altogether. That would be a separate scientific-schema migration:
passing raw C++ doubles today would bypass intentional JSON quantization used by
some Python enrichers. The current native MessagePack path therefore prioritizes
compatibility: it streams over the canonical native JSON and changes only its
transport encoding.

Compression is not enabled in container version 1. Raw MessagePack is the
maximum-speed path, avoids decompression bombs, and already halves the
representative artifact. The decoded Python graph is still several times larger
than the encoded bytes. Readers therefore enforce encoded-byte, string,
collection-length, nesting, type, and finite-number limits; these reduce risk
but cannot promise a fixed decoded-RSS ceiling. A future compression flag can
be added in a new compatible container version after separately benchmarking
decompression and allocation limits.

## `.mgeo` version 1 framing

All header integers are little-endian. The MessagePack payload itself uses the
standard network-byte-order representation defined by MessagePack.

| Offset | Size | Field | Version 1 value |
|---:|---:|---|---|
| 0 | 8 | magic | `MGEO\r\n\x1a\n` |
| 8 | 2 | major | `1` |
| 10 | 2 | minor | `0` |
| 12 | 1 | codec | `1` (MessagePack) |
| 13 | 1 | flags | `0` |
| 14 | 2 | header size | `32` |
| 16 | 8 | payload byte count | exact remaining file size |
| 24 | 4 | payload CRC-32 | integrity check |
| 28 | 4 | world schema | must equal root `schema_version` |

`.mgeo` readers reject unknown versions/codecs/flags, bad header or payload
lengths, checksum mismatches, trailing bytes, invalid UTF-8/MessagePack,
extension values, non-empty binary values, and header/content schema
mismatches. Both decoders enforce the configured input-byte limit and an object
root with string keys. Public strict reads additionally reject non-finite
numbers, other non-JSON values, excessive nesting, and reference cycles.
Auto-detection uses content magic rather than trusting a filename suffix. Reads
use one opened file descriptor for size checking and decoding. Writes use a
temporary file in the destination directory, preserve normal/new or existing
file permissions, flush and sync it, then atomically replace the target.

## APIs and CLI behavior

Python persistence:

```python
from pathlib import Path
from magic_geo.serialization import read_world, write_world

write_world(Path("runs/world.mgeo"), world)
loaded = read_world(Path("runs/world.mgeo"))
```

Public calls recursively validate the JSON value model by default. Code that
already owns and has validated a generated world can select the maximum-speed
path with `validate_model=False`. The CLI does this only at its
generator-owned save boundary. Standalone CLI loads are user-selected and
therefore retain strict validation; framing, checksum, decoder, and encoded-size
checks always run.

`write_world` selects `.mgeo` for `.mgeo`, `.mgpack`, `.msgpack`, and `.mpk`
suffixes; all other suffixes retain the existing pretty JSON writer. `read_world`
detects binary content by magic, so renamed files still load correctly.

Native C++ and C ABI additions:

- `generate_world_msgpack` / `generate_geo_world_msgpack`;
- `magic_geo_generate_msgpack_v3` /
  `magic_geo_generate_geo_msgpack_v3`; and
- `magic_geo_free_buffer`.

The C ABI returns a byte pointer and explicit `size_t`; it never treats binary
data as a NUL-terminated string. Python uses a `memoryview` over that allocation,
decodes it without an intermediate bytes copy, and frees it afterward. The
Python package requires the current V3 JSON and MessagePack symbols when loading
the native library. Callers can request `serialization="json"` or
`serialization="msgpack"` explicitly for transport parity testing.

The generation command remains JSON by default, based on its default filename:

```bash
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.mgeo
magic-geo validate --world runs/world.mgeo
```

Validation, calibration, SVG/raster rendering, debug export, and Rerun export
all use the shared loader.

## Measured result

One warm-cache run on 2026-07-11 used the local, ignored
`runs/earthlike/world.json` artifact (SHA-256
`bd06e7b6691abf5b5b020132ec1b79d12a12542f5312c2c3c575c577d7b247d6`),
an Intel Core i5-14400F, Python 3.13.14, and msgpack 1.2.1. These timings are
evidence for this machine, not CI thresholds or a claim that the artifact is
tracked.

| Trusted generated-world operation | JSON | `.mgeo` | Improvement |
|---|---:|---:|---:|
| File size | 387,454,418 B | 192,978,786 B | 50.2% smaller |
| Save | 2.503 s | 0.639 s | 3.92x faster |
| Load | 2.068 s | 0.796 s | 2.60x faster |

With recursive JSON-model preflight enabled on both sides, estimated JSON load
was 3.656 s versus 2.408 s for `.mgeo` (1.52x), while strict `.mgeo` save was
2.297 s (1.09x faster than JSON). This separates codec performance from the
optional full-graph semantic pass instead of hiding that cost.

Peak process RSS for the full comparison and semantic digest was about
1.353 GB. Re-encoding both decoded worlds to MessagePack produced equal
SHA-256 digests, covering the complete value graph rather than a small sample.

For the 4,096-cell native snapshot with zero erosion iterations, end-to-end
simulation plus transfer/decode took 0.857 s through JSON and 0.759 s through
MessagePack (1.13x faster), and the decoded objects were deeply equal. Simulation
work is included, so this understates the isolated transport improvement.

Reproduce the persistence measurement with:

```bash
.venv/bin/python scripts/benchmark_serialization.py runs/earthlike/world.json
```

Create a comparable input when no local run exists:

```bash
magic-geo generate \
  --config configs/earthlike_seed.yaml \
  --output runs/earthlike/world.json
```

Timing assertions are intentionally absent from normal tests. Correctness tests
cover exact JSON/MessagePack equivalence, binary64 bit patterns, uint64/int64
edges, Unicode and control characters, deterministic output, alias expansion,
atomic replacement, malformed headers, truncation, corruption, schema mismatch,
and size limits.
