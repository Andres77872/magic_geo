# Serialization and World Formats

[Wiki home](./README.md) > Serialization and World Formats

magic-geo persists a generated world in exactly two on-disk formats: pretty-printed JSON and the versioned binary `.mgeo` container, which wraps a standard MessagePack payload in a 32-byte checksummed header. Both carry the identical schema-2 value model, because the native engine emits one canonical JSON document and the MessagePack path *transcodes that document* rather than serializing C++ structs directly — which is what preserves every decimal-quantization boundary the Python enrichers depend on. This page documents format selection, the JSON key-order and precision contract, the `.mgeo` framing and its fail-closed limits, the strict bounded-depth C++ transcoder, the native binary transfer ABI, and how to reproduce the checked-in benchmark.

## On this page

- [Format selection](#format-selection)
- [The JSON contract](#the-json-contract)
- [The `.mgeo` container, version 1](#the-mgeo-container-version-1)
- [The native JSON-to-MessagePack transcoder](#the-native-json-to-messagepack-transcoder)
- [Safety limits and fail-closed checks](#safety-limits-and-fail-closed-checks)
- [Format comparison (measured)](#format-comparison-measured)
- [Round-trip guarantees](#round-trip-guarantees)
- [Native binary transfer APIs and free functions](#native-binary-transfer-apis-and-free-functions)
- [`float_precision` and the fields that ignore it](#float_precision-and-the-fields-that-ignore-it)
- [Compatibility and version-mismatch behavior](#compatibility-and-version-mismatch-behavior)
- [Benchmark it yourself](#benchmark-it-yourself)
- [Limitations and unresolved claims](#limitations-and-unresolved-claims)
- [See also](#see-also)

---

## Format selection

Everything in `src/magic_geo/serialization.py` funnels through two façade functions: `write_world` (`src/magic_geo/serialization.py:532`) and `read_world` (`src/magic_geo/serialization.py:557`). They are re-exported from `magic_geo.io` (`src/magic_geo/io/__init__.py:9`) because callers have always imported them from there.

### Accepted `format` values

`_normalize_format` (`src/magic_geo/serialization.py:619`) collapses the public `WorldFormat` alias (`src/magic_geo/serialization.py:25`) to three internal modes.

| Public value | Normalizes to | Meaning |
|---|---|---|
| `"auto"` | `auto` | Write: choose by path suffix. Read: choose by content magic. |
| `"json"` | `json` | Force JSON. |
| `"mgeo"` | `mgeo` | Force the binary container. |
| `"msgpack"` | `mgeo` | Alias for `mgeo`. |
| `"binary"` | `mgeo` | Alias for `mgeo`. |
| anything else | — | `ValueError("world format must be auto, json, or mgeo")` |

### Write-side selection is by suffix

When `format` normalizes to `auto`, `write_world` picks `mgeo` if `path.suffix.lower()` is in `MGEO_SUFFIXES`, otherwise JSON (`src/magic_geo/serialization.py:543-544`). An explicit `format="mgeo"` / `"msgpack"` / `"binary"` overrides the suffix entirely.

| Suffix | Format written | Constant |
|---|---|---|
| `.mgeo` | `.mgeo` binary | `MGEO_SUFFIXES` (`src/magic_geo/serialization.py:35`) |
| `.mgpack` | `.mgeo` binary | same |
| `.msgpack` | `.mgeo` binary | same |
| `.mpk` | `.mgeo` binary | same |
| `.json` | pretty JSON | default branch |
| any other / none | pretty JSON | default branch |

### Read-side selection is by content, not by name

`read_world` opens the file once, reads the first `len(MGEO_MAGIC)` = 8 bytes, and sets `normalized = "mgeo" if prefix == MGEO_MAGIC else "json"` (`src/magic_geo/serialization.py:576-578`). A JSON world stored at `world.mgeo` therefore still loads correctly; the test `test_read_auto_detection_uses_content_not_suffix` (`tests/test_serialization.py:374`) pins this.

| Situation | Behavior |
|---|---|
| `format="auto"`, file starts with magic | decoded as `.mgeo` |
| `format="auto"`, file does not start with magic | decoded as JSON |
| `format="json"`, file starts with magic | `WorldSerializationError("binary .mgeo file was requested as JSON")` (`:582`) |
| `format="mgeo"`, file is empty | `WorldSerializationError("empty .mgeo file")` (`:604`) |
| `format="mgeo"`, file does not start with magic | `WorldSerializationError("invalid .mgeo magic")` (`:606`) |

The binary path memory-maps the file (`mmap.mmap(..., access=mmap.ACCESS_READ)`, `src/magic_geo/serialization.py:607`) and decodes from a `memoryview` over the mapping — one file descriptor is used for both the size check and the decode.

### CLI surface

| Command / option | Behavior | Source |
|---|---|---|
| `magic-geo generate --output <path>` | default `runs/world.json` | `src/magic_geo/cli/commands/generate.py:23` |
| `magic-geo generate --format {auto,json,mgeo}` | default `auto`; any other value exits with code 2 and `--format must be auto, json, or mgeo` | `src/magic_geo/cli/commands/generate.py:38-59` |
| generate's save call | `write_world(output, world, format=world_format, validate_model=False)` — the generator owns the object, so the recursive preflight is skipped on the hot save path | `src/magic_geo/cli/commands/generate.py:78` |
| every world-consuming command | `_load_world_for_cli` calls `read_world(path)` with strict validation retained, because CLI paths are user-selected; `OSError`/`UnicodeError`/`ValueError` become `Invalid world file: …` and exit code 2 | `src/magic_geo/cli/_app.py:16-23` |
| web workbench job field | `world_format` choice `auto` / `json` / `mgeo`, flag `--format` | `src/magic_geo/web_jobs.py:121` |

```bash
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.json
magic-geo generate --config configs/earthlike_seed.yaml --output runs/world.mgeo
magic-geo validate --world runs/world.mgeo
magic-geo render  --world runs/world.mgeo --output runs/world.svg
```

---

## The JSON contract

### Two distinct JSON documents

There are two JSON texts in the system and they do **not** have the same key order.

| Document | Producer | Key order | Formatting |
|---|---|---|---|
| Native canonical JSON (in-process, never written to disk by the CLI) | `serialize_world` in `cpp/src/engine/world_serialization.cpp`, built with the `add_raw`/`add_str`/`add_int`/`add_u64`/`add_double` primitives in `cpp/src/engine/core.cpp:185-208` | fixed **emission order**, stable and treated as an invariant | compact, no whitespace |
| The `.json` file on disk | `write_json` (`src/magic_geo/io/json_writer.py:10-15`) | **sorted alphabetically** (`sort_keys=True`) | `indent=2`, `allow_nan=False`, `ensure_ascii` left at its default so non-ASCII is `\uXXXX`-escaped, written as UTF-8 |

The `.mgeo` payload, by contrast, is `msgpack.packb(payload, use_bin_type=True)` (`src/magic_geo/serialization.py:331`), and MessagePack maps are packed in Python-dict insertion order — i.e. native emission order followed by the order in which the Python enrichers added their keys. So:

- **JSON on disk is order-normalized (sorted).**
- **`.mgeo` on disk preserves insertion order.**

Both decode to dictionaries that compare `==` equal, since JSON object order is not part of the value model. Only byte-level digests and iteration order differ.

### Why key order matters anyway

- The engine treats it as a hard invariant: *"Preserve RNG consumption, OpenMP schedules, floating-point expression order, serializer key order, and precision unless a schema/behavior change is intended"* (`cpp/src/engine/README.md:339-340`).
- The serialization review lists *"Array order, empty collections, CSR offsets, and serializer key order remain unchanged"* among the compatibility constraints found during the audit (`docs/serialization_review.md:56-57`).
- The transcoder streams the source document, emitting map entries in source order (`cpp/src/engine/messagepack.cpp:176-196`). It never reorders and never builds a second object graph, so the native JSON and native MessagePack transports carry the same key order by construction.
- Because `msgpack.packb` is order-sensitive, `.mgeo` encoding is byte-deterministic for a given dict: `test_encoding_is_deterministic_and_does_not_preserve_aliases` (`tests/test_serialization.py:172`) asserts `dumps_world(world) == dumps_world(world)`.
- Many CSR-style ledgers in the schema (offset arrays paired with value arrays) are only interpretable if array order is preserved; see [World Document Schema](./10-world-schema.md).

### The permitted value model

`validate_world_payload` (`src/magic_geo/serialization.py:237`) defines the exact JSON value model a world may contain. It is a recursive, cycle-detecting pass.

| Rule | Enforcement | Source |
|---|---|---|
| Root must be a `dict` (exact type) | `WorldSerializationError("world root must be an object")` | `:240-241` |
| Object keys must be `str` | `"world object keys must be strings, not <type>"` | `:276-280` |
| Strings must be valid UTF-8 | `"world string is not valid UTF-8"` on `UnicodeEncodeError` | `:244-250` |
| Strings ≤ `DEFAULT_MAX_STRING_BYTES` | byte length measured, ASCII fast path | `:246-254` |
| Arrays ≤ `DEFAULT_MAX_ARRAY_LENGTH` items | applies to `list` and `tuple` | `:284-288` |
| Objects ≤ `DEFAULT_MAX_MAP_LENGTH` entries | | `:270-274` |
| Nesting ≤ `MAX_WORLD_NESTING_DEPTH` containers | `"world nesting exceeds 64 containers"` | `:261-264` |
| No reference cycles | live-container identity set | `:265-267` |
| `int` within MessagePack's signed/unsigned 64-bit range | `MIN_MESSAGEPACK_INTEGER` .. `MAX_MESSAGEPACK_INTEGER` | `:298-303` |
| `float` must be finite | `"world contains a non-finite floating-point value"` | `:304-308` |
| `None` and `bool` accepted unconditionally | | `:296-297` |
| Everything else rejected | `"world contains a non-JSON value of type <type>"` — covers `bytes`, `set`, `msgpack.Timestamp`, etc. | `:309-313` |

`validate_model=True` is the default for `dumps_world`, `loads_world`, `write_world`, `write_world_binary`, and `read_world`. `validate_model=False` skips only this recursive semantic pass; framing, checksum, decoder, and encoded-size checks always run (`docs/serialization_review.md:130-134`).

### Non-finite values cannot reach either format

Three independent gates:

| Gate | Where | Effect |
|---|---|---|
| `num(value, precision)` | `cpp/src/engine/core.cpp:168-177` | throws `std::runtime_error("attempted to serialize a non-finite simulation value")` |
| `roundtrip_num(value)` | `cpp/src/engine/numeric_serialization.cpp:5-16` | same throw |
| `json.dumps(..., allow_nan=False)` | `src/magic_geo/io/json_writer.py:13` | `ValueError` before any bytes are written |
| `validate_world_payload` | `src/magic_geo/serialization.py:304-308` | `WorldSerializationError` |

Reading a hand-edited `{"value": NaN}` JSON file is also rejected, because Python's `json.loads` accepts `NaN` but the model validator does not (`tests/test_serialization.py:380-390`).

### String escaping

`json_escape` (`cpp/src/engine/core.cpp:140-166`) escapes `"`, `\`, `\b`, `\f`, `\n`, `\r`, `\t`, and emits `\u00XX` for every other C0 control character. The review records that this path previously omitted `\b`, `\f`, and other U+0000–U+001F escapes, that it now emits valid JSON escapes, and that ordinary generated JSON is byte-for-byte unaffected by the fix (`docs/serialization_review.md:61-63`).

---

## The `.mgeo` container, version 1

`.mgeo` is a fixed 32-byte little-endian header followed by a raw MessagePack payload. The header layout is the `struct.Struct("<8sHHBBHQII")` at `src/magic_geo/serialization.py:33`; `<` suppresses alignment padding, so the size is exactly `8+2+2+1+1+2+8+4+4 = 32`.

| Offset | Size | Field | Struct code | Version-1 value | Constant |
|---:|---:|---|---|---|---|
| 0 | 8 | magic | `8s` | `MGEO\r\n\x1a\n` (`4d 47 45 4f 0d 0a 1a 0a`) | `MGEO_MAGIC` (`:28`) |
| 8 | 2 | version major | `H` | `1` | `MGEO_VERSION_MAJOR` (`:29`) |
| 10 | 2 | version minor | `H` | `0` | `MGEO_VERSION_MINOR` (`:30`) |
| 12 | 1 | codec | `B` | `1` = MessagePack | `MGEO_CODEC_MESSAGEPACK` (`:31`) |
| 13 | 1 | flags | `B` | `0` | `MGEO_FLAGS_NONE` (`:32`) |
| 14 | 2 | header size | `H` | `32` | `MGEO_HEADER_SIZE` (`:34`) |
| 16 | 8 | payload byte count | `Q` | exact remaining file size | — |
| 24 | 4 | payload CRC-32 | `I` | `zlib.crc32(payload)` | `_header` (`:338-349`) |
| 28 | 4 | world schema | `I` | must equal the payload's root `schema_version` | `_world_schema` (`:59-65`) |

All header integers are little-endian; the MessagePack payload itself uses MessagePack's own big-endian ("network byte order") field encoding (`docs/serialization_review.md:91-92`).

The magic is `MGEO` followed by `\r\n\x1a\n` (`MGEO_MAGIC`, `src/magic_geo/serialization.py:28`). The repository does not record a rationale for that trailing byte sequence, so treat any explanation of it as inference rather than a documented contract; what *is* enforced is only that the first eight bytes match exactly (`_decode_mgeo_view` check #4, and the `read_world` prefix test at `:605-606`).

### Worked example: reading the header by hand

```bash
xxd -l 32 runs/world.mgeo
```

```python
import struct, zlib
from pathlib import Path
from magic_geo.serialization import MGEO_HEADER, MGEO_HEADER_SIZE, MGEO_MAGIC

raw = Path("runs/world.mgeo").read_bytes()
(magic, major, minor, codec, flags,
 header_size, payload_size, crc32, world_schema) = MGEO_HEADER.unpack_from(raw)

assert magic == MGEO_MAGIC
assert (major, minor) == (1, 0)
assert codec == 1 and flags == 0 and header_size == MGEO_HEADER_SIZE == 32
assert payload_size == len(raw) - MGEO_HEADER_SIZE
assert crc32 == zlib.crc32(raw[MGEO_HEADER_SIZE:])
print(major, minor, codec, flags, payload_size, world_schema)
```

### Header and payload rejection matrix

`_decode_mgeo_view` (`src/magic_geo/serialization.py:363-453`) checks in this order:

| # | Condition | Error message |
|---:|---|---|
| 1 | `max_file_bytes < 0` | `ValueError("max_file_bytes must be nonnegative")` |
| 2 | `len(data) > max_file_bytes` | `world file is N bytes; limit is M bytes` |
| 3 | `len(data) < 32` | `truncated .mgeo header` |
| 4 | magic mismatch | `invalid .mgeo magic` |
| 5 | `(major, minor) != (1, 0)` | `unsupported .mgeo version {major}.{minor}; expected 1.0` |
| 6 | `codec != 1` | `unsupported .mgeo codec {codec}` |
| 7 | `flags != 0` | `unsupported .mgeo flags 0x{flags:02x}` |
| 8 | `header_size != 32` | `unsupported .mgeo header size {header_size}` |
| 9 | declared payload length ≠ actual | `.mgeo payload length mismatch: header declares X, file contains Y` |
| 10 | CRC-32 mismatch | `.mgeo checksum mismatch; the file is corrupt or incomplete` |
| 11 | MessagePack decode failure (`ExtraData`, `FormatError`, `StackError`, `UnicodeDecodeError`, `ValueError`) | `invalid MessagePack world payload: {exc}` |
| 12 | decoded root not a dict | `decoded world root must be an object` |
| 13 | root `schema_version` missing, non-`int`, or ≠ header value | `.mgeo world schema does not match its container header` |
| 14 | `validate_model=True` and the value model fails | any `validate_world_payload` message |

Trailing bytes after the payload are caught twice: by the declared-length check (#9) and by msgpack's `ExtraData` (#11). `tests/test_serialization.py:243-272` exercises all of empty input, a truncated header, a corrupted magic, wrong major, wrong minor, a bad codec, a nonzero flag, a wrong header size, a wrong payload length, a wrong schema field, a truncated payload, appended trailing bytes, and a single flipped payload bit.

### Atomic, permission-preserving writes

`write_world_binary` (`src/magic_geo/serialization.py:475-529`):

| Step | Detail |
|---|---|
| 1 | `path.parent.mkdir(parents=True, exist_ok=True)` |
| 2 | pack payload and build the header (schema is read from the payload) |
| 3 | record the existing file's mode via `stat.S_IMODE(path.stat().st_mode)` if the target already exists |
| 4 | create `.{name}.{16 hex chars}.tmp` beside the target with `O_WRONLY\|O_CREAT\|O_EXCL` (plus `O_BINARY` where it exists), retrying up to 128 times on `FileExistsError`; the suffix comes from `secrets.token_hex(8)` |
| 5 | if a prior mode was recorded, apply it with `os.fchmod` (or `os.chmod` where `fchmod` is unavailable) |
| 6 | write header then payload, `handle.flush()`, `os.fsync(handle.fileno())` |
| 7 | `os.replace(temporary_path, path)` — atomic on the same filesystem |
| 8 | `finally`: close a leaked descriptor and unlink a leftover temporary |

`tests/test_serialization.py:232-241` writes over an existing `0o640` file containing garbage and asserts the mode is preserved, the world reads back, and no `.tmp` sibling remains.

The JSON branch of `write_world` is *not* atomic: it delegates to `write_json`, which calls `Path.write_text` (`src/magic_geo/io/json_writer.py:12-15`).

### Compression

Container version 1 has no compression. The review states the reasoning explicitly: raw MessagePack is the maximum-speed path, it avoids decompression bombs, and it already halves the representative artifact; a compression flag can be added in a later compatible container version after separately benchmarking decompression and allocation limits (`docs/serialization_review.md:80-88`). `flags` is the reserved byte, and any nonzero value is rejected today.

---

## The native JSON-to-MessagePack transcoder

`cpp/src/engine/messagepack.cpp` implements `json_to_messagepack(std::string_view) -> std::vector<std::uint8_t>` (`:591`) as a single-pass `JsonToMessagePack` class (`:69`). It parses the canonical JSON text and emits MessagePack bytes directly; **no intermediate object graph is built**.

### Why it transcodes canonical JSON instead of serializing structs

This is a deliberate compatibility decision, stated in two places:

- `cpp/src/engine/README.md:27-29`: *"The MessagePack facade intentionally transcodes the canonical JSON document. This preserves every established decimal-quantization boundary consumed by the Python enrichers."*
- `docs/serialization_review.md:74-78`: a typed columnar result handle could eventually avoid building the intermediate JSON document, but that would be a separate scientific-schema migration, because *"passing raw C++ doubles today would bypass intentional JSON quantization used by some Python enrichers"*. The current path therefore *"streams over the canonical native JSON and changes only its transport encoding."*

In other words: many Python enrichers consume values that the C++ serializer has already rounded to `float_precision` decimal places. Handing them the unrounded binary64 would silently change downstream results. Transcoding the text guarantees byte-identical semantics between `serialization="json"` and `serialization="msgpack"`.

### Type mapping

| JSON input | MessagePack output | Source |
|---|---|---|
| `null` | `0xc0` nil | `:143-145` |
| `true` | `0xc3` | `:137-139` |
| `false` | `0xc2` | `:140-142` |
| object | `0xdf` **map32** with a back-patched `uint32` count — always the 32-bit form, never fixmap/map16 | `:164-197` |
| array | `0xdd` **array32** with a back-patched `uint32` count — always the 32-bit form | `:199-225` |
| string | minimal form: fixstr `0xa0\|len` (≤31), `0xd9` str8, `0xda` str16, `0xdb` str32 | `append_string` `:486-504` |
| number containing `.` or `e`/`E` | `0xcb` float64, from `std::from_chars(..., std::chars_format::general)`, bit-cast big-endian | `:452-467` |
| non-negative integer | minimal unsigned: positive fixint, `0xcc`, `0xcd`, `0xce`, `0xcf` | `append_unsigned` `:506-522` |
| negative integer | minimal signed: negative fixint (≥ −32), `0xd0`, `0xd1`, `0xd2`, `0xd3` | `append_signed` `:524-540` |

Because containers always use the 32-bit headers, the native transport buffer is **not** byte-identical to what Python's `msgpack.packb` would produce for the same value graph (the Python packer picks minimal container headers). The two are semantically equal, not byte-equal. Only string and integer encodings are minimal on the native side.

The output vector is pre-reserved at `input.size() / 2` for inputs over 128 bytes (`:71-76`), which matches the observed ~50% size reduction.

### Strictness: what the parser rejects

| Rejected input | Message fragment | Source |
|---|---|---|
| nesting depth > 256 (`MAX_JSON_NESTING_DEPTH`) | `nesting depth exceeds 256` | `:18`, `:120-123` |
| empty input / missing value | `expected a value`, `expected a JSON value` | `:124-152` |
| trailing content after the root | `trailing content after the root value` | `:82-84` |
| non-string object key | `object keys must be strings` | `:178-180` |
| missing `:` or `,` | `expected ':' after object key`, `expected ',' or '}' in object`, `expected ',' or ']' in array` | `:183`, `:194`, `:222` |
| trailing comma (`[1,]`, `{"a":1,}`) | falls out of the required-value parse | tested at `cpp/tests/serialization_roundtrip_test.cpp:151-152` |
| unescaped control character in a string | `unescaped control character in string` | `:251-253`, `:269-271` |
| unterminated string / escape | `unterminated string`, `unterminated string escape` | `:256`, `:276-278` |
| unknown escape | `unsupported string escape` | `:311-312` |
| truncated or non-hex `\uXXXX` | `truncated unicode escape`, `invalid unicode escape` | `:318-336` |
| lone high surrogate | `high surrogate is not followed by a low surrogate` | `:291-301` |
| lone low surrogate | `unpaired low surrogate` | `:305-306` |
| invalid UTF-8 (overlong, out-of-range, surrogate code point) | `string is not valid UTF-8` | `validate_utf8` `:357-397` |
| a number that ends at end-of-input before a digit | `truncated number` | `:403` |
| a literal that is not exactly `true`/`false`/`null` | `invalid literal` | `:158` |
| leading zero (`01`) | `leading zero in number` | `:405-409` |
| missing integer digits | `invalid integer component` | `:410-412` |
| `1.` with no fraction digits | `fraction has no digits` | `:428-430` |
| `1e` with no exponent digits | `exponent has no digits` | `:445-447` |
| float out of binary64 range or non-finite (`1e9999`) | `floating-point number is out of binary64 range` | `:460-463` |
| integer > `2^64-1` | `integer is out of unsigned 64-bit range` | `:479-480` |
| integer < `-2^63` | `negative integer is out of signed 64-bit range` | `:472-473` |
| container with > `2^32-1` entries | `object contains too many entries`, `array contains too many entries` | `:187-189`, `:215-217` |
| string > `2^32-1` bytes | `string exceeds MessagePack's 32-bit size limit` | `:487-489` |

Every failure raises `std::runtime_error` with the byte offset: `"invalid JSON for MessagePack at byte N: <message>"` (`:89-94`). At the C ABI boundary these become error envelopes, not crashes.

The string fast path (`:227-257`) scans for a closing quote first and copies the original UTF-8 span with no allocation when the string contains no backslash; only escaped strings take the decoding path (`:259-316`).

### `sanitize_utf8`

`sanitize_utf8` (`cpp/src/engine/messagepack.cpp:574-589`) preserves valid UTF-8 sequences and replaces each malformed byte with U+FFFD (`\xef\xbf\xbd`). It is used at FFI error boundaries where driver-owned diagnostics are not guaranteed to be well formed (`cpp/src/engine/messagepack.hpp:11-13`), specifically inside `error_json` in `cpp/src/c_api.cpp:104-131` (the `sanitize_utf8` call is at `:107`). It is applied to *error text*, not to world content.

### The `-0` case

`roundtrip_num(-0.0)` produces the lexical string `"-0"`, which Python's `json.loads` interprets as the **integer** `0`. The transcoder is required to do the same rather than silently changing downstream Python types, and the native test asserts both facts directly:

```cpp
CHECK(roundtrip_num(-0.0) == "-0");
CHECK(json_to_messagepack(roundtrip_num(-0.0)) ==
    std::vector<std::uint8_t>({0x00}));
```

(`cpp/tests/serialization_roundtrip_test.cpp:118-123`.) By contrast `num(-0.0, 4)` emits `"-0.0000"`, which is a JSON float and decodes to `-0.0` with the sign bit intact on both paths.

A related and important typing consequence: `roundtrip_num` uses `std::defaultfloat`, so integral values print without a decimal point (`0`, `5`, `6371`) and therefore decode as Python `int`, while non-integral values print in `%g`-style form and decode as `float`. Any consumer of a round-trip field must accept both `int` and `float`.

---

## Safety limits and fail-closed checks

Four distinct limit sets exist, at four different boundaries.

### 1. Python persistence limits (`src/magic_geo/serialization.py`)

| Constant | Value | Applies to | Line |
|---|---:|---|---|
| `DEFAULT_MAX_WORLD_FILE_BYTES` | `2 * 1024**3` = 2,147,483,648 | encoded input bytes for `read_world` / `loads_world` | `:39` |
| `DEFAULT_MAX_STRING_BYTES` | `256 * 1024**2` = 268,435,456 | one string, in UTF-8 bytes | `:40` |
| `DEFAULT_MAX_ARRAY_LENGTH` | 50,000,000 | one array | `:41` |
| `DEFAULT_MAX_MAP_LENGTH` | 2,000,000 | one object | `:42` |
| `MAX_WORLD_NESTING_DEPTH` | 64 | container nesting during model validation | `:43` |
| `MIN_MESSAGEPACK_INTEGER` | `-(2**63)` | integer lower bound | `:44` |
| `MAX_MESSAGEPACK_INTEGER` | `2**64 - 1` | integer upper bound | `:45` |

`max_file_bytes` is a per-call keyword on both `loads_world` and `read_world`; a negative value raises `ValueError`. Note the code comment at `:37-38`: the 4,096-cell reference artifact is roughly 193 MB as `.mgeo`, and this is an **encoded-input bound, not a promise about the larger decoded Python graph**.

### 2. `.mgeo` decoder limits passed to `msgpack.unpackb` (`src/magic_geo/serialization.py:418-430`)

| Option | Value | Effect |
|---|---|---|
| `raw=False` | — | strings decode as `str`, not `bytes` |
| `use_list=True` | — | arrays decode as `list` |
| `strict_map_key=True` | — | only `str`/`bytes` map keys accepted |
| `ext_hook=_reject_extension` | `:52-56` | `MessagePack extension type {code} is not valid in a world payload` |
| `max_str_len` | `min(payload_size, DEFAULT_MAX_STRING_BYTES)` | |
| `max_bin_len` | `0` | **bin type forbidden entirely** |
| `max_array_len` | `min(payload_size, DEFAULT_MAX_ARRAY_LENGTH)` | |
| `max_map_len` | `min(payload_size, DEFAULT_MAX_MAP_LENGTH)` | |
| `max_ext_len` | `0` | **ext type forbidden entirely** |

### 3. Native transport decoder limits (`src/magic_geo/native.py:201-212`)

The zero-copy path over the C-allocated buffer uses the same hardening, bounded by the buffer size rather than by the persistence constants:

| Option | Value |
|---|---|
| `raw=False`, `use_list=True`, `strict_map_key=True` | as above |
| `ext_hook` | `_reject_msgpack_extension` (`src/magic_geo/native.py:40-44`) → `MessagePack extension type {code} is not valid in a native world` |
| `max_str_len`, `max_array_len`, `max_map_len` | `size` (the returned byte count) |
| `max_bin_len`, `max_ext_len` | `0` |

`_consume_msgpack_pointer` (`src/magic_geo/native.py:184-231`) wraps the malloc'd block as `(ctypes.c_ubyte * size).from_address(ptr)` → `memoryview(...).cast("B")` and unpacks from the view with no intermediate `bytes` copy. Its `finally` releases the memoryview **before** calling `magic_geo_free_buffer`, which is mandatory because the view aliases the allocation. A null pointer raises `native library returned a null MessagePack pointer`; `size <= 0` frees the buffer then raises `native library returned an empty MessagePack buffer`; a non-dict root raises `native MessagePack root is not an object`; an `"error"` key raises `RuntimeError` with the native message.

### 4. C++ transcoder limit

`MAX_JSON_NESTING_DEPTH = 256` (`cpp/src/engine/messagepack.cpp:18`). This is far above the maximum observed nesting depth of eight recorded for the reference artifact (`docs/serialization_review.md:38-41`).

### What is *not* promised

The review is explicit: encoded-byte, string, collection-length, nesting, type, and finite-number limits *"reduce risk but cannot promise a fixed decoded-RSS ceiling"*, because the decoded Python graph is still several times larger than the encoded bytes (`docs/serialization_review.md:82-87`).

---

## Format comparison (measured)

**Artifact and environment.** All numbers below come from `docs/serialization_review.md:165-192` and describe a **single warm-cache run** on a **local, git-ignored** `runs/earthlike/world.json` artifact with SHA-256 `bd06e7b6691abf5b5b020132ec1b79d12a12542f5312c2c3c575c577d7b247d6`, produced from `configs/earthlike_seed.yaml` (a 4,096-cell earthlike world), on an Intel Core i5-14400F with Python 3.13.14 and msgpack 1.2.1. The review states plainly: *"These timings are evidence for this machine, not CI thresholds or a claim that the artifact is tracked."* Timing assertions are deliberately absent from the normal test suite (`docs/serialization_review.md:208-209`).

### Trusted generated-world path (`validate_model=False`)

| Operation | JSON | `.mgeo` | Improvement |
|---|---:|---:|---:|
| File size | 387,454,418 B | 192,978,786 B | 50.2% smaller |
| Save time | 2.503 s | 0.639 s | 3.92x faster |
| Load time | 2.068 s | 0.796 s | 2.60x faster |

### Strict path (recursive JSON-model preflight enabled on both sides)

| Operation | JSON | `.mgeo` | Improvement |
|---|---:|---:|---:|
| Load (JSON figure is an estimate: decode + validation) | 3.656 s | 2.408 s | 1.52x faster |
| Save | 2.503 s | 2.297 s | 1.09x faster |

The review notes this split *"separates codec performance from the optional full-graph semantic pass instead of hiding that cost."*

### Other measurements from the same run

| Measurement | Value |
|---|---|
| Peak process RSS for the full comparison plus semantic digest | ≈ 1.353 GB |
| Semantic equality check | re-encoding both decoded worlds to MessagePack produced equal SHA-256 digests, covering the complete value graph rather than a sample |
| 4,096-cell native snapshot, zero erosion iterations, end-to-end simulation + transfer + decode via JSON | 0.857 s |
| Same, via MessagePack | 0.759 s (1.13x faster) |
| Decoded objects from the two transports | deeply equal |

The end-to-end figure **includes simulation work**, so the review notes it *understates* the isolated transport improvement.

The README repeats the headline result as *"50.2% smaller, 3.92x faster to save, and 2.60x faster to load in a single benchmark"* (`README.md:177-179`).

---

## Round-trip guarantees

### What `.mgeo` preserves exactly

| Property | Guarantee | Evidence |
|---|---|---|
| binary64 bit pattern | preserved bit-for-bit; MessagePack floats are 8-byte IEEE-754 `0xcb` values | `tests/test_serialization.py:163-170` compares `struct.pack(">d", v)` for every value |
| `bool` vs `int` | `True`/`False` stay `bool`, never become `1`/`0` | `tests/test_serialization.py:159-160` |
| unsigned 64-bit maximum | `2**64 - 1` survives | `:161` |
| signed 64-bit minimum | `-(2**63)` survives | `:162` |
| negative sentinel IDs | remain signed integers, never coerced to unsigned | `docs/serialization_review.md:54-55` |
| `None` | stays `None` (nil) | value model |
| string content | UTF-8, including astral-plane code points and escaped control characters | `docs/serialization_review.md:210`; exercised at `tests/test_native_messagepack.py:22` |
| object key order | preserved (dict insertion order) | `msgpack.packb` semantics |
| array order, empty collections, CSR offsets | unchanged | `docs/serialization_review.md:56-57` |
| encoding determinism | `dumps_world(w) == dumps_world(w)` | `tests/test_serialization.py:176-180` |

### What is deliberately *not* preserved

| Property | Behavior | Evidence |
|---|---|---|
| Object identity / aliasing | shared references are expanded into independent copies; `decoded["left"] == decoded["right"]` but `is not` | `tests/test_serialization.py:172-182`; `docs/serialization_review.md:41-43` |
| `tuple` | encodes as an array and decodes as `list` | `tests/test_serialization.py:184-185` |
| JSON on-disk key order | normalized by `sort_keys=True` | `src/magic_geo/io/json_writer.py:13` |
| Byte-identity between the native transcoder and `msgpack.packb` | native always uses map32/array32 headers | `cpp/src/engine/messagepack.cpp:167`, `:202` |

### What the *native* round trip guarantees

The engine's precision policy splits fields into two classes (`cpp/src/engine/README.md`, precision discussion; `docs/serialization_review.md:50-53`):

| Class | Primitive | Guarantee |
|---|---|---|
| Replay-critical state | `roundtrip_num` / `roundtrip_double_array_json` (`cpp/src/engine/numeric_serialization.cpp`) | `std::defaultfloat` at `std::numeric_limits<double>::max_digits10` (= 17 significant digits) — parsing recovers the **original binary64 bit pattern** |
| Presentation / diagnostic state | `num(value, precision)` (`cpp/src/engine/core.cpp:168`) | `std::fixed` at `precision` **decimal places** — value is decimally quantized at write time, in C++, identically for both transports |

The C++ test `strictly_positive_area_arrays_round_trip_binary64` (`cpp/tests/serialization_roundtrip_test.cpp:27-62`) checks `std::bit_cast<std::uint64_t>` equality after `strtod` for `denorm_min()`, `4.0e-18`, `min()`, `1.0e-7`, `1.0e-9`, `2.0322308988775575e-7`, `123456.78901234567`, and `max()`, and additionally asserts each decoded value stays strictly positive (so a positive area can never round to zero).

Consequently the important claim is narrow and worth stating precisely: **`.mgeo` preserves the Python value graph bit-for-bit, and the native transcoder preserves the canonical JSON text's semantics exactly — but neither undoes the decimal quantization that the C++ serializer already applied to `float_precision`-class fields.** Those fields are quantized before either format sees them.

---

## Native binary transfer APIs and free functions

### C++ symbols (`cpp/include/magic_geo/native.hpp`)

| Symbol | Signature | Line |
|---|---|---|
| `magic_geo::generate_world_msgpack` | `std::vector<std::uint8_t>(const Params&, const ComputeOptions&)` | `:151-154` |
| `magic_geo::generate_geo_world_msgpack` | `std::vector<std::uint8_t>(const Params&, const ComputeOptions&)` | `:155-158` |

Both are implemented in `cpp/src/engine.cpp:38-62` and share the identical prologue with the JSON entry points — `validate_compute_options` → `validate_params` → `ScopedThreadConfiguration` → `ComputeSession` → `simulate_world` / `simulate_geo_world` → `serialize_world` — then wrap the result in `detail::json_to_messagepack(...)` (`cpp/src/engine.cpp:46`, `:59`). There is **no** one-argument (CPU-only) MessagePack overload; MessagePack is v3-only.

### C ABI symbols (`extern "C"`)

| Symbol | Signature | Header line | Definition |
|---|---|---|---|
| `magic_geo_generate_msgpack_v3` | `const std::uint8_t*(const magic_geo::CConfigV3* cfg, std::size_t* size)` | `:179-182` | `cpp/src/c_api.cpp:244` |
| `magic_geo_generate_geo_msgpack_v3` | `const std::uint8_t*(const magic_geo::CConfigV3* cfg, std::size_t* size)` | `:183-186` | `cpp/src/c_api.cpp:267` |
| `magic_geo_free_buffer` | `void(const std::uint8_t* ptr)` | `:188` | `cpp/src/c_api.cpp:297` |
| `magic_geo_free_string` | `void(const char* ptr)` | `:187` | `cpp/src/c_api.cpp:293` |

The header comments the contract directly: *"Binary results can contain NUL bytes and therefore always use an explicit byte count. The returned allocation belongs to the caller and must be released with `magic_geo_free_buffer`."* (`cpp/include/magic_geo/native.hpp:176-178`).

### Buffer ownership and error behavior

| Situation | Behavior | Source |
|---|---|---|
| `size == nullptr` | return `nullptr` immediately, no allocation | `cpp/src/c_api.cpp:247-249`, `:270-272` |
| normal entry | `*size` is zeroed first, then set on success | same |
| `cfg == nullptr` | `copy_error_msgpack_noexcept("null config pointer", size)` | `:253-255`, `:276-278` |
| `std::exception` thrown | `copy_error_msgpack_noexcept(exc.what(), size)` | `:260-262`, `:283-285` |
| unknown throw | `"unknown generation failure"` / `"unknown geo generation failure"` | `:262-263`, `:286-289` |
| error envelope construction fails | `copy_error_msgpack_noexcept` is `noexcept` and degrades to `nullptr` with `*size = 0` | `:137-149` |
| empty result vector | `copy_buffer` mallocs 1 byte so the pointer is never null on success | `:85-101` |
| freeing | `magic_geo_free_buffer` / `magic_geo_free_string` are `std::free` with a `const_cast`; `nullptr` is safe | `:293-299` |

Error payloads are built as `error_json(message)` — the message is `sanitize_utf8`'d then JSON-escaped with `\u00XX` for control characters (`cpp/src/c_api.cpp:104-131`) — and then transcoded to MessagePack by `error_msgpack` (`:133-135`). So a MessagePack error return is a valid one-key map `{"error": "..."}`.

### Python binding

`src/magic_geo/native.py` uses **only** the v3 entry points. Both public generators take a keyword-only `serialization` argument:

```python
from pathlib import Path
from magic_geo.config import config_to_native, load_config
from magic_geo.native import generate_geo_world, generate_world

native = config_to_native(load_config(Path("configs/earthlike_seed.yaml")))

world_auto    = generate_world(native)                          # "auto" -> MessagePack
world_msgpack = generate_world(native, serialization="msgpack") # forced binary transport
world_json    = generate_world(native, serialization="json")    # forced text transport
geo_world     = generate_geo_world(native, serialization="msgpack")
```

| `serialization` value | Entry point used (full world / geo-only) | Source |
|---|---|---|
| `"auto"` (default) | `magic_geo_generate_msgpack_v3` / `magic_geo_generate_geo_msgpack_v3` | `src/magic_geo/native.py:358-366`, `:384-392` |
| `"msgpack"` | same as `auto` | same |
| `"json"` | `magic_geo_generate_json_v3` / `magic_geo_generate_geo_json_v3` | `:367-372`, `:393-398` |
| anything else | `ValueError("serialization must be auto, json, or msgpack")` | `:356-357`, `:382-383` |

`magic_geo.api.generate_world` and `generate_geo_world` call the native generators without passing `serialization`, so the production pipeline takes the MessagePack transport by default (`src/magic_geo/api.py:196-198`, `:294-302`).

All pointer returns declare `restype = ctypes.c_void_p` (not `c_char_p`), specifically so ctypes does not copy-and-discard the pointer before it can be freed. Loading resolves seven symbols; a missing one is re-raised as `RuntimeError("native library does not expose the current V3 JSON and MessagePack ABI; rebuild magic_geo_native from the current source tree")`.

### Python persistence API

```python
from pathlib import Path
from magic_geo.serialization import (
    dumps_world, loads_world, read_world, write_world, write_world_binary,
)

write_world(Path("runs/world.mgeo"), world)                  # suffix selects .mgeo
write_world(Path("runs/world.json"), world)                  # suffix selects JSON
write_world(Path("runs/world.data"), world, format="mgeo")   # explicit override
write_world_binary(Path("runs/world.mgeo"), world)           # bypass the façade

loaded = read_world(Path("runs/world.mgeo"))                 # magic-based detection
fast   = read_world(Path("runs/world.mgeo"), validate_model=False)
capped = read_world(Path("runs/world.mgeo"), max_file_bytes=512 * 1024 * 1024)

blob   = dumps_world(world)                                  # bytes, header + payload
again  = loads_world(blob)
```

| Function | Signature | Line |
|---|---|---|
| `dumps_world` | `(payload, *, validate_model=True) -> bytes` | `:352` |
| `loads_world` | `(data, *, max_file_bytes=DEFAULT_MAX_WORLD_FILE_BYTES, validate_model=True) -> dict` | `:456` |
| `write_world_binary` | `(path, payload, *, validate_model=True) -> None` | `:475` |
| `write_world` | `(path, payload, *, format="auto", validate_model=True) -> None` | `:532` |
| `read_world` | `(path, *, format="auto", max_file_bytes=…, validate_model=True) -> dict` | `:557` |
| `validate_world_payload` | `(payload) -> None` | `:237` |
| `retired_world_schema_fields` | `(payload) -> tuple[str, ...]` | `:68` |
| `WorldSerializationError` | subclass of `ValueError` | `:48` |

---

## `float_precision` and the fields that ignore it

`output.float_precision` (`src/magic_geo/config.py:450-455`) defaults to **4**, is constrained `ge=0, le=8` by Pydantic, and is re-validated natively: `float_precision must be between 0 and 8` (`cpp/src/engine/core.cpp:430-431`). Its documented role is *"General JSON decimal precision; replay-critical fields use higher fixed floors."* Its configured value is echoed into the document as `summary.output_float_precision` (`cpp/src/engine/summary.cpp:1323`) so consumers can reconstruct the quantization grid.

### The two primitives

| Primitive | Formatting | Meaning of the number |
|---|---|---|
| `num(value, precision)` (`cpp/src/engine/core.cpp:168`) | `std::fixed << std::setprecision(precision)` | **decimal places** |
| `roundtrip_num(value)` (`cpp/src/engine/numeric_serialization.cpp:5`) | `std::defaultfloat << std::setprecision(max_digits10)` | **significant digits** (17) |

### Precision floors observed in the serializers

| Effective precision | Where it is applied | Source |
|---|---|---|
| `roundtrip_num` (full binary64 round trip) | per-cell `crust_age_ma`, `crust_thickness_km`, `crust_density`, `thermal_subsidence_target_m`, `elevation_m`, `water_depth_m` | `cpp/src/engine/entity_serialization.cpp:145-186` |
| `geometry_precision = max(max_digits10, float_precision)` | per-cell `position_3d`, `normal_3d`, `lat_deg`, `lon_deg`, `area_km2`, `control_volume_vertices_3d` | `cpp/src/engine/entity_serialization.cpp:112-131` |
| `surface_precision = max(10, float_precision)` | the elevation/sediment-depth family of cell fields (`cumulative_tectonic_elevation_change_m`, `initial_*_m`, `bedrock_surface_elevation_m`, …) | `cpp/src/engine/entity_serialization.cpp:117`, applied from `:156` onward |
| `MASS_PRECISION = max_digits10` | every `*_mass_kg`, residual, and packet-table mass array in the crust dry-rock accounting and material-shadow serializers | `cpp/src/engine/crust_reservoir_serialization.cpp:7` |
| `max_digits10` | the shared nominal-time block injected into seven process ledgers | `cpp/src/engine/process_serialization.cpp:141` |
| various fixed floors (`max(6, p)`, `max(8, p)`, `max(12, p)`, literals `6` and `12`) | history/model fragments in `cpp/src/engine/process_serialization.cpp` and `cpp/src/engine/summary.cpp` | e.g. `process_serialization.cpp:655`, `:845`, `:917`, `:1236` |
| plain `float_precision` | the bulk of cell climate/hydrology/ice/soil fields and the society/natural entity arrays | `cpp/src/engine/entity_serialization.cpp` throughout |

For the field-by-field precision mapping across all 155 cell fields and the full summary, see [World Document Schema](./10-world-schema.md). The rule of thumb — and it is only that, because the floors are per-serializer literals, not a declared policy: **fields that a replay or conservation audit consumes as operands are written either at full binary64 round-trip or at a fixed floor that exceeds the default `float_precision` of 4.** The floors actually observed in the serializers are `max(6, p)`, `max(8, p)`, `max(10, p)`, and `max(12, p)` (`cpp/src/engine/process_serialization.cpp:3472`, `:845`, `:455`, `:556`), so "higher than the configured precision" is the guarantee you can rely on; "at least ten decimal places" is not. Verify the specific field in the schema table before assuming a floor.

### Comment recorded in the source for `elevation_m` / `water_depth_m`

> These two fields jointly determine the discrete ocean mask. Fixed fractional formatting can collapse a one-ULP-below-sea-level water cell to signed zero and make the serialized mask unreplayable.

(`cpp/src/engine/entity_serialization.cpp:182-184`; the two fields themselves are at `:185-186`.)

### `float_precision` is not purely cosmetic

One verified case where the configured precision changes a **value**, not just its formatting: `conflict_intensity_scale = 10^clamp(float_precision, 0, 8)` is used to round each conflict's intensity onto the emitted grid *before* the `>= 0.65` test that produces `summary.high_intensity_conflict_count` (`cpp/src/engine/summary.cpp:712-723`). Changing `float_precision` can therefore change that counter.

### Consumer caution

`plate_boundary_segment_model` carries five self-describing contract keys — `intrinsic_angular_speed_serialized_significant_digits`, `rotation_axis_serialized_significant_digits`, `assignment_center_serialized_significant_digits`, `top_level_plate_center_serialized_significant_digits` (`cpp/src/engine/process_serialization.cpp:3041-3048`, `:3063-3064`) and `serialized_float_decimal_significant_digits` (`:3126-3127`). All five are emitted through `add_int`, so each is a plain JSON integer holding `precision`, which in that serializer is `constexpr int precision = std::numeric_limits<double>::max_digits10` (`:2949`) — i.e. the literal `17`.

The caution is about what that `17` means for the fields the keys describe, not about the keys' own formatting. Those fields — the per-step plate `center`, `rotation_axis`, and `intrinsic_angular_speed` — are written with `transport_precision = max_digits10` (`:3530`) through `vec3_json` / `add_double` (`:4395-4401`), and `add_double` routes to `num(value, precision)`, which is `std::fixed` at that many **decimal places**. So a key named `…_significant_digits` describes a value formatted with 17 decimal places. Read the key as a declaration about a sibling field's write precision, and read `num`'s own contract (decimal places) for what the number actually is.

---

## Compatibility and version-mismatch behavior

There are **two independent version numbers**. Confusing them is the most common serialization mistake.

| Version | Current value | Scope | Constant |
|---|---:|---|---|
| World content schema (`schema_version`, a document root key) | `2` | the set and meaning of world keys | `CURRENT_WORLD_SCHEMA_VERSION` (`src/magic_geo/serialization.py:27`) |
| `.mgeo` container version (header bytes 8–11) | `1.0` | the framing around the payload | `MGEO_VERSION_MAJOR` / `MGEO_VERSION_MINOR` (`:29-30`) |

The review states this explicitly: *"`schema_version` remains the world-content schema. Current generation emits version 2 after retiring schema-1 compatibility fields; it is independent of the `.mgeo` container version."* (`docs/serialization_review.md:47-50`).

### Container-version mismatch

| Header state | Result |
|---|---|
| `(major, minor) == (1, 0)` | accepted |
| anything else | `unsupported .mgeo version {major}.{minor}; expected 1.0` |
| `codec != 1` | `unsupported .mgeo codec {codec}` |
| `flags != 0` | `unsupported .mgeo flags 0x{flags:02x}` |

There is no forward-compatibility or "ignore unknown flags" path. The container fails closed on every unknown value, which is what reserves the flags byte for a future compression codec.

### World-schema mismatch

`_world_schema` (`src/magic_geo/serialization.py:59-65`) requires `type(schema) is int` (so `True` is rejected, since `bool` is a subclass) and `0 <= schema <= 0xFFFFFFFF`. **It does not require the value to be 2** — the container can carry any 32-bit schema number, and the header must simply agree with the payload. Note the asymmetry: `dumps_world` and `write_world_binary` always run this check, while the JSON branch of `write_world` does not, so a JSON world may be written without a `schema_version` key at all.

Enforcement of "must be 2" lives in three places above the container:

| Gate | Behavior | Source |
|---|---|---|
| `native._require_current_world_schema` | non-`int` or `!= 2` → `native library returned unsupported world schema_version {actual!r}; expected 2; rebuild magic_geo_native from the current source tree` | `src/magic_geo/native.py:234-241` |
| `magic-geo validate` | `FAIL world schema_version must be 2, got <n>`, exit code 1 | `src/magic_geo/cli/commands/validate.py:100-113` |
| geo validation suite | contract check `world_schema_version`, message *"natural-world validation requires the current world schema"* | `src/magic_geo/geo_validation.py:828-839` |

### Retired schema-1 fields

`retired_world_schema_fields(payload)` (`src/magic_geo/serialization.py:68-234`) returns the list of retired keys and container aliases actually present in a payload. Their reappearance is treated as a fatal schema regression by `native._require_current_world_schema`, by `magic-geo validate` (`world schema contains retired fields: …`), and by the geo validation contract check `retired_world_schema_fields` (*"schema-1 compatibility fields must not reappear in current worlds"*).

| Container | Retired names | Count |
|---|---|---:|
| `simulation_clock` | `legacy_mean_erosion_rate_field_semantics` | 1 |
| `plate_kinematic_model` | `accelerator_crust_source_remap_kernel_used`, `legacy_crust_source_cell_id_semantics`, `legacy_crust_source_remap_event_semantics`, `legacy_crust_source_reuse_count_semantics` | 4 |
| `plate_boundary_segment_model` | `unavailable_opening_crust_fallback_semantics`, `legacy_smoothed_cell_boundary_forcing_retained`, `boundary_segments_drive_legacy_smoothed_forcing` | 3 |
| `crust_dry_rock_accounting_model` | `legacy_proxy_compensations_exposed` | 1 |
| `backend` | `accelerator_crust_source_remap_kernel_production_active`, `accelerator_crust_source_remap_kernel_role`, `legacy_nearest_source_remap_world_pipeline_enabled`, `legacy_crust_source_remap_dispatch_counters_deprecated`, `opencl_crust_source_remap_dispatch_count`, `cuda_crust_source_remap_dispatch_count` | 6 |
| `climate_model` | `positive_precipitation_pre_thermal_annual_floor_mm`, `positive_precipitation_effective_annual_floor_mm`, `positive_precipitation_floor_application` | 3 |
| `oceanic_age_depth_model` | `thermal_target_difference_tendency_formula`, `…_application`, `…_compatibility_alias`, `…_application_replayed` | 4 |
| `initial_oceanic_crust_age_model` | `compatibility_cell_alias_location`, `compatibility_history_alias_location`, `compatibility_alias_scope` | 3 |
| `summary` | `total_crust_source_remap_event_count`, `total_crust_source_reuse_count`, `numeric_depression_fill_max_pass_count`, `numeric_depression_fill_pass_count`, `numeric_depression_fill_event_count`, `numeric_depression_fill_cell_application_count`, `numeric_depression_filled_unique_cell_count`, `numeric_depression_fill_geologic_source_event_count`, `numeric_depression_fill_area_km2`, `numeric_depression_fill_volume_km3`, `mean_numeric_depression_fill_depth_m`, `max_numeric_depression_fill_depth_m`, `cumulative_numeric_depression_fill_sum_m`, `max_cumulative_numeric_depression_fill_m`, `numeric_depression_unbalanced_fill_event_count` | 15 |
| document root | `numeric_depression_fill_history` | 1 |
| `cells[i]` | `last_crust_source_cell_id`, `crust_source_remap_event_count`, `initial_crust_age_ma`, `initial_crust_thickness_km`, `initial_crust_density`, `initial_thermal_subsidence_m`, `sediment_production_m`, `cumulative_numeric_depression_fill_m`, `numeric_depression_fill_event_count` | 9 |
| `earth_system_feedback_history[i]` | `mean_erosion_rate_m_per_step`, `numeric_depression_fill_pass_count`, `numeric_depression_fill_event_count`, `numeric_depression_fill_cell_application_count`, `numeric_depression_filled_unique_cell_count`, `numeric_depression_fill_area_km2`, `numeric_depression_fill_volume_km3`, `max_numeric_depression_fill_depth_m` | 8 |
| `numeric_depression_correction_history[i]` | `applied_fill_volume_km3` | 1 |
| `plate_motion_history[i]` | `crust_source_remap_cell_count`, `unique_crust_source_cell_count`, `crust_source_reuse_count`, `crust_source_cell_ids`, `thermal_target_difference_tendency_m` | 5 |
| **Total distinct names** | | **64** |

`tests/test_serialization.py:30-151` builds a payload containing every one of them and asserts `len(retired) == 64` with no duplicates, so this inventory is pinned by a test.

### ABI stability rules that bear on serialization

| Rule | Source |
|---|---|
| `CConfig` (v1) and `CConfigV2` field order, types, and 64-bit sizes stay stable; the binary MessagePack functions are purely **additive** | `docs/serialization_review.md:58-59`; `cpp/src/engine/README.md` invariants |
| MessagePack is exposed only on the v3 config; v1/v2 callers get the historical JSON entry points | `cpp/include/magic_geo/native.hpp:166-186` |
| The Python package requires the current V3 JSON **and** MessagePack symbols at load time | `docs/serialization_review.md:149-151`; `src/magic_geo/native.py` symbol resolution |
| All existing JSON symbols remain untouched | `docs/serialization_review.md:58-59` |

### Additional native-boundary gate

Beyond the schema number and the retired-field scan, `_require_current_world_schema` also requires a well-formed `planet_parameters` object: it must be a dict, must cover every key of `PLANET_PARAMETER_DEFAULTS` (missing keys are listed sorted), every value must be a non-`bool` `int`/`float` convertible to `float` without `OverflowError` and finite, and `radius_km`, `gravity_g`, `geological_age_ga` must be strictly `> 0.0` (`src/magic_geo/native.py:248-278`).

---

## Benchmark it yourself

`scripts/benchmark_serialization.py` is checked in and reproduces the persistence measurement.

```bash
# 1. Produce a comparable input if no local run exists.
magic-geo generate \
  --config configs/earthlike_seed.yaml \
  --output runs/earthlike/world.json

# 2. Benchmark.
.venv/bin/python scripts/benchmark_serialization.py runs/earthlike/world.json

# Skip the memory-intensive pretty JSON write (uses the source file's size instead).
.venv/bin/python scripts/benchmark_serialization.py runs/earthlike/world.json --skip-json-write
```

### Arguments

| Argument | Type | Meaning | Source |
|---|---|---|---|
| `world` (positional) | `Path` | Existing generated **JSON** world; it is resolved and read with `format="json"` | `scripts/benchmark_serialization.py:43`, `:51`, `:58-60` |
| `--skip-json-write` | flag | Skip the pretty JSON write comparison; `json_bytes` then reports the source file's size and both save speedups become `null` | `:44-48`, `:74-78`, `:121-130` |

### What the script does, in order

| Step | Action | Line |
|---|---|---|
| 1 | create a `magic-geo-serialization-` temporary directory for all outputs | `:52` |
| 2 | time `read_world(source, format="json", validate_model=False)` | `:58-60` |
| 3 | time `validate_world_payload(world)` separately | `:61` |
| 4 | compute `expected_digest = sha256(msgpack.packb(world, use_bin_type=True))` | `:36-38`, `:62` |
| 5 | unless skipped, time `write_json(json_target, world)` | `:64-66` |
| 6 | time `write_world(binary_target, world, validate_model=False)` | `:67-69` |
| 7 | time `write_world(strict_binary_target, world, validate_model=True)` | `:70-72` |
| 8 | `del world; gc.collect()`, then time `read_world(binary_target, validate_model=False)` and digest it | `:80-84` |
| 9 | `del loaded; gc.collect()`, then time `read_world(binary_target, validate_model=True)` and digest it | `:86-91` |
| 10 | read peak RSS from `resource.getrusage(RUSAGE_SELF).ru_maxrss` (bytes on darwin, KiB elsewhere; `None` on Windows where `resource` is unavailable) | `:21-24`, `:93-96` |
| 11 | print one JSON object with `indent=2, sort_keys=True` | `:133` |

### Reported keys

| Key | Meaning |
|---|---|
| `source` | resolved input path |
| `semantic_sha256_equal` | `True` when the JSON-loaded, `.mgeo`-loaded, and strict-`.mgeo`-loaded digests all match — a whole-graph equality check, not a sample |
| `json_bytes` / `mgeo_bytes` / `mgeo_to_json_size_ratio` | sizes and their ratio |
| `json_load_seconds` | JSON decode without the model pass |
| `json_model_validation_seconds` | the recursive `validate_world_payload` pass alone |
| `json_strict_load_estimate_seconds` | the sum of the two above (an **estimate**, not a measured single operation) |
| `json_save_seconds` | pretty JSON write, or `null` with `--skip-json-write` |
| `mgeo_load_seconds` / `mgeo_save_seconds` | trusted (`validate_model=False`) binary timings |
| `mgeo_strict_load_seconds` / `mgeo_strict_save_seconds` | validated binary timings |
| `load_speedup` / `strict_load_speedup` | JSON ÷ `.mgeo` |
| `save_speedup` / `strict_save_speedup` | JSON ÷ `.mgeo`, or `null` with `--skip-json-write` |
| `peak_rss_bytes` | peak process RSS, or `null` on platforms without `resource` |

### Correctness tests (no timing assertions)

| Suite | Coverage |
|---|---|
| `tests/test_serialization.py` | retired-field inventory (64 names), binary64 bit patterns, uint64/int64 edges, bool-vs-int, determinism, alias expansion, tuple flattening, suffix selection, JSON-writer byte equality, permission preservation, atomic replacement, malformed headers, truncation, corruption, trailing bytes, schema/header mismatch, size limits, cycle and depth rejection, ext/bin rejection, non-finite rejection, CLI acceptance of `.mgeo`, CLI rejection of schema 1 and of retired fields |
| `tests/test_native_messagepack.py` | JSON vs MessagePack transport parity for both `generate_world` and `generate_geo_world`, including a run name containing `"`, a newline, an astral emoji and U+0001; per-cell `struct.pack(">d", …)` equality for `crust_age_ma` / `crust_thickness_km` / `crust_density`; identical error text across all three `serialization` values; stale-schema and retired-field rejection |
| `cpp/tests/serialization_roundtrip_test.cpp` (CTest name `magic_geo_serialization_roundtrip`, registered at `CMakeLists.txt:334-335`) | binary64 round trip for arrays and scalars including denormals and `DBL_MAX`, non-finite fail-closed, exact MessagePack byte encodings for nil/bool/ints/float64/strings/containers, the `-0` integer rule, surrogate-pair decoding, malformed-JSON rejection, the 256-depth limit, and `sanitize_utf8` behavior |

The review states directly: *"Timing assertions are intentionally absent from normal tests."* (`docs/serialization_review.md:208`).

---

## Limitations and unresolved claims

- **The published timings are one machine, one warm-cache run.** `docs/serialization_review.md:170-172` says so explicitly: *"These timings are evidence for this machine, not CI thresholds or a claim that the artifact is tracked."* The `runs/earthlike/world.json` artifact they were measured on is local and git-ignored; it is not in the repository, and nothing in the test suite reproduces or gates these numbers. Treat 50.2% / 3.92x / 2.60x as a single observation, not a specification.
- **`json_strict_load_estimate_seconds` is an estimate.** It is the arithmetic sum of a decode timing and a separate validation timing (`scripts/benchmark_serialization.py:108-111`), not a measured single strict-load operation. The 1.52x strict-load figure inherits that.
- **The end-to-end 1.13x transport figure includes simulation work** and therefore understates the isolated transport improvement (`docs/serialization_review.md:189-192`).
- **No decoded-memory ceiling is promised.** The encoded-byte, string, collection-length, nesting, type, and finite-number limits *"reduce risk but cannot promise a fixed decoded-RSS ceiling"* (`docs/serialization_review.md:82-87`). The decoded Python graph is several times larger than the encoded bytes.
- **`.mgeo` files are not signed or authenticated.** CRC-32 detects accidental corruption and truncation; it is not a cryptographic integrity check and provides no protection against a deliberately crafted file. The decoder's defense is its limit set, not the checksum.
- **The two on-disk formats are not byte-comparable.** JSON is written with sorted keys; `.mgeo` preserves insertion order. Any workflow that diffs or digests world files must normalize first (the benchmark does this by re-packing both decoded graphs with the same packer).
- **The native transcoder output is not canonical MessagePack.** It always emits map32/array32 container headers (`cpp/src/engine/messagepack.cpp:167`, `:202`), so its bytes differ from `msgpack.packb` output for the same value graph even though the decoded values are identical. Do not compare native transport bytes against Python-packed bytes.
- **`float_precision` quantization is applied in C++, before either format exists.** Neither JSON nor `.mgeo` can recover the pre-quantization binary64 for fields written through `num(value, precision)`. Only `roundtrip_num`-class fields carry the original bit pattern.
- **Round-trip fields decode with a variable Python type.** `roundtrip_num` prints integral values without a decimal point, so a replay-critical field such as `crust_age_ma` may arrive as `int` on one cell and `float` on another. Consumers must handle both.
- **Serializers are read-only over `GeneratedWorld` and carry the model's explicit false-authority flags forward verbatim.** Nothing on this page upgrades those claims. The crust material shadow and the three-reservoir dry-rock accounting are non-authoritative counter-models with `physical_basis_resolved = false`; subduction polarity is emitted as an explicit *candidate* pair with physical sides `unknown`; mass provenance, physical time, process-rate calibration, and whole-coupling timestep convergence remain `false` in the document. A high-precision serialization of an unresolved quantity is still an unresolved quantity — `MASS_PRECISION = max_digits10` guarantees numerical fidelity of the counter-model's bookkeeping, not physical validity.
- **Accelerator parity is not a serialization property.** The document's `backend` object carries dispatch telemetry, but CPU remains authoritative for the exact overlap geometry; the serialization layer neither validates nor asserts backend agreement.
- **A columnar / typed result handle is explicitly deferred.** `docs/serialization_review.md:74-78` describes it as a separate scientific-schema migration that would bypass the intentional JSON quantization the Python enrichers rely on. It is not implemented.
- **Compression is not implemented in container version 1** and the `flags` byte must be `0`. A future compression flag is described as possible in a new compatible container version only after separately benchmarking decompression and allocation limits (`docs/serialization_review.md:86-88`).
- **The JSON write path is not atomic** and does not check `schema_version`. Only `write_world_binary` performs the temp-file / fsync / `os.replace` sequence and the schema/header agreement check.
- **`numeric_serialization.cpp` is not listed in the engine README's source-responsibility table** — a documentation gap noted during recon, not a behavior gap. The file itself is authoritative for `roundtrip_num` / `roundtrip_double_array_json`.

---

## See also

- [World Document Schema](./10-world-schema.md) — the full key inventory, per-field precision classes, and the geo-only divergence
- [Native Engine (C++ Core)](./08-native-engine.md) — `serialize_world`, the C ABI, and the engine invariants
- [Python API](./07-python-api.md) — `magic_geo.api`, `magic_geo.native`, and the enrichment pipeline
- [CLI Reference](./06-cli-reference.md) — `generate --format`, and the shared world loader used by every consuming command
- [Configuration Reference](./05-configuration-reference.md) — `output.float_precision` and `output.include_cells`
- [Validation](./12-validation.md) — the schema-version and retired-field gates in `magic-geo validate`
- [Geo Validation Suite](./13-geo-validation-suite.md) — the `world_schema_version` and `retired_world_schema_fields` contract checks
- [Testing and Quality Gates](./18-testing.md) — `tests/test_serialization.py`, `tests/test_native_messagepack.py`, and the `magic_geo_serialization_roundtrip` CTest
- [Compute Backends (CPU, OpenCL, CUDA)](./09-compute-backends.md) — the `backend` telemetry object embedded in every world
- [Architecture](./04-architecture.md) — where serialization sits in the generation pipeline
- [Troubleshooting and FAQ](./22-troubleshooting.md) — `.mgeo` decode errors and schema-mismatch messages
- [Glossary](./21-glossary.md) — canonical JSON, round-trip precision, replay operand
