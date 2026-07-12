"""Lossless world persistence in JSON and the fast ``.mgeo`` container.

The binary container deliberately stores ordinary MessagePack rather than a
Python-specific object representation. Loading it cannot execute code, object
aliases are expanded just as they are by JSON, and other languages can decode
the payload using the published framing constants below.
"""

from __future__ import annotations

import json
import math
import mmap
import os
import secrets
import stat
import struct
import zlib
from pathlib import Path
from typing import Any, Literal

import msgpack


WorldFormat = Literal["auto", "json", "mgeo", "msgpack", "binary"]

MGEO_MAGIC = b"MGEO\r\n\x1a\n"
MGEO_VERSION_MAJOR = 1
MGEO_VERSION_MINOR = 0
MGEO_CODEC_MESSAGEPACK = 1
MGEO_FLAGS_NONE = 0
MGEO_HEADER = struct.Struct("<8sHHBBHQII")
MGEO_HEADER_SIZE = MGEO_HEADER.size
MGEO_SUFFIXES = frozenset({".mgeo", ".mgpack", ".msgpack", ".mpk"})

# The 4,096-cell reference artifact is roughly 193 MB as .mgeo. This is an
# encoded-input bound, not a promise about the larger decoded Python graph.
DEFAULT_MAX_WORLD_FILE_BYTES = 2 * 1024 * 1024 * 1024
DEFAULT_MAX_STRING_BYTES = 256 * 1024 * 1024
DEFAULT_MAX_ARRAY_LENGTH = 50_000_000
DEFAULT_MAX_MAP_LENGTH = 2_000_000
MAX_WORLD_NESTING_DEPTH = 64
MIN_MESSAGEPACK_INTEGER = -(2**63)
MAX_MESSAGEPACK_INTEGER = 2**64 - 1


class WorldSerializationError(ValueError):
    """A world file is malformed, unsupported, or exceeds configured limits."""


def _reject_extension(code: int, data: bytes) -> Any:
    del data
    raise WorldSerializationError(
        f"MessagePack extension type {code} is not valid in a world payload"
    )


def _world_schema(payload: dict[str, Any]) -> int:
    schema = payload.get("schema_version")
    if type(schema) is not int or not 0 <= schema <= 0xFFFFFFFF:
        raise WorldSerializationError(
            "binary worlds require an integer schema_version between 0 and 2^32-1"
        )
    return schema


def validate_world_payload(payload: dict[str, Any]) -> None:
    """Validate the finite, string-keyed JSON value model used by worlds."""

    if type(payload) is not dict:
        raise WorldSerializationError("world root must be an object")
    active_containers: set[int] = set()

    def validate_string(value: str) -> None:
        try:
            byte_length = len(value) if value.isascii() else len(value.encode("utf-8"))
        except UnicodeEncodeError as exc:
            raise WorldSerializationError(
                "world string is not valid UTF-8"
            ) from exc
        if byte_length > DEFAULT_MAX_STRING_BYTES:
            raise WorldSerializationError(
                f"world string exceeds the {DEFAULT_MAX_STRING_BYTES}-byte limit"
            )

    def visit(
        container: dict[Any, Any] | list[Any] | tuple[Any, ...],
        depth: int,
    ) -> None:
        identity = id(container)
        if depth > MAX_WORLD_NESTING_DEPTH:
            raise WorldSerializationError(
                f"world nesting exceeds {MAX_WORLD_NESTING_DEPTH} containers"
            )
        if identity in active_containers:
            raise WorldSerializationError("world contains a reference cycle")
        active_containers.add(identity)
        try:
            if type(container) is dict:
                if len(container) > DEFAULT_MAX_MAP_LENGTH:
                    raise WorldSerializationError(
                        "world object exceeds the "
                        f"{DEFAULT_MAX_MAP_LENGTH}-entry limit"
                    )
                for key in container:
                    if type(key) is not str:
                        raise WorldSerializationError(
                            "world object keys must be strings, not "
                            f"{type(key).__name__}"
                        )
                    validate_string(key)
                values = container.values()
            else:
                if len(container) > DEFAULT_MAX_ARRAY_LENGTH:
                    raise WorldSerializationError(
                        "world array exceeds the "
                        f"{DEFAULT_MAX_ARRAY_LENGTH}-item limit"
                    )
                values = container
            for value in values:
                value_type = type(value)
                if value_type is dict or value_type is list or value_type is tuple:
                    visit(value, depth + 1)
                elif value_type is str:
                    validate_string(value)
                elif value is None or value_type is bool:
                    continue
                elif value_type is int:
                    if not MIN_MESSAGEPACK_INTEGER <= value <= MAX_MESSAGEPACK_INTEGER:
                        raise WorldSerializationError(
                            "world integer is outside MessagePack's signed/unsigned "
                            "64-bit range"
                        )
                elif value_type is float:
                    if not math.isfinite(value):
                        raise WorldSerializationError(
                            "world contains a non-finite floating-point value"
                        )
                else:
                    raise WorldSerializationError(
                        "world contains a non-JSON value of type "
                        f"{value_type.__name__}"
                    )
        finally:
            active_containers.remove(identity)

    visit(payload, 0)


def _pack_payload(
    payload: dict[str, Any],
    *,
    validate_model: bool,
) -> bytes:
    if type(payload) is not dict:
        raise WorldSerializationError("world root must be an object")
    _world_schema(payload)
    if validate_model:
        validate_world_payload(payload)
    try:
        return msgpack.packb(payload, use_bin_type=True)
    except (OverflowError, TypeError, ValueError) as exc:
        raise WorldSerializationError(
            f"world contains a value unsupported by MessagePack: {exc}"
        ) from exc


def _header(payload: bytes, world_schema: int) -> bytes:
    return MGEO_HEADER.pack(
        MGEO_MAGIC,
        MGEO_VERSION_MAJOR,
        MGEO_VERSION_MINOR,
        MGEO_CODEC_MESSAGEPACK,
        MGEO_FLAGS_NONE,
        MGEO_HEADER_SIZE,
        len(payload),
        zlib.crc32(payload),
        world_schema,
    )


def dumps_world(
    payload: dict[str, Any],
    *,
    validate_model: bool = True,
) -> bytes:
    """Encode one world as versioned ``.mgeo``; validate its model by default."""

    packed = _pack_payload(payload, validate_model=validate_model)
    return _header(packed, _world_schema(payload)) + packed


def _decode_mgeo_view(
    data: memoryview,
    *,
    max_file_bytes: int,
    validate_model: bool,
) -> dict[str, Any]:
    if max_file_bytes < 0:
        raise ValueError("max_file_bytes must be nonnegative")
    if len(data) > max_file_bytes:
        raise WorldSerializationError(
            f"world file is {len(data)} bytes; limit is {max_file_bytes} bytes"
        )
    if len(data) < MGEO_HEADER_SIZE:
        raise WorldSerializationError("truncated .mgeo header")

    (
        magic,
        major,
        minor,
        codec,
        flags,
        header_size,
        payload_size,
        expected_crc32,
        expected_world_schema,
    ) = MGEO_HEADER.unpack_from(data)
    if magic != MGEO_MAGIC:
        raise WorldSerializationError("invalid .mgeo magic")
    if (major, minor) != (MGEO_VERSION_MAJOR, MGEO_VERSION_MINOR):
        raise WorldSerializationError(
            f"unsupported .mgeo version {major}.{minor}; "
            f"expected {MGEO_VERSION_MAJOR}.{MGEO_VERSION_MINOR}"
        )
    if codec != MGEO_CODEC_MESSAGEPACK:
        raise WorldSerializationError(f"unsupported .mgeo codec {codec}")
    if flags != MGEO_FLAGS_NONE:
        raise WorldSerializationError(f"unsupported .mgeo flags 0x{flags:02x}")
    if header_size != MGEO_HEADER_SIZE:
        raise WorldSerializationError(
            f"unsupported .mgeo header size {header_size}"
        )
    actual_payload_size = len(data) - MGEO_HEADER_SIZE
    if payload_size != actual_payload_size:
        raise WorldSerializationError(
            ".mgeo payload length mismatch: "
            f"header declares {payload_size}, file contains {actual_payload_size}"
        )

    packed = data[MGEO_HEADER_SIZE:]
    try:
        actual_crc32 = zlib.crc32(packed)
        if actual_crc32 != expected_crc32:
            raise WorldSerializationError(
                ".mgeo checksum mismatch; the file is corrupt or incomplete"
            )
        try:
            decoded = msgpack.unpackb(
                packed,
                raw=False,
                use_list=True,
                strict_map_key=True,
                ext_hook=_reject_extension,
                max_str_len=min(payload_size, DEFAULT_MAX_STRING_BYTES),
                max_bin_len=0,
                max_array_len=min(payload_size, DEFAULT_MAX_ARRAY_LENGTH),
                max_map_len=min(payload_size, DEFAULT_MAX_MAP_LENGTH),
                max_ext_len=0,
            )
        except (
            msgpack.ExtraData,
            msgpack.FormatError,
            msgpack.StackError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            raise WorldSerializationError(
                f"invalid MessagePack world payload: {exc}"
            ) from exc
    finally:
        packed.release()

    if not isinstance(decoded, dict):
        raise WorldSerializationError("decoded world root must be an object")
    schema = decoded.get("schema_version")
    if type(schema) is not int or schema != expected_world_schema:
        raise WorldSerializationError(
            ".mgeo world schema does not match its container header"
        )
    if validate_model:
        validate_world_payload(decoded)
    return decoded


def loads_world(
    data: bytes | bytearray | memoryview,
    *,
    max_file_bytes: int = DEFAULT_MAX_WORLD_FILE_BYTES,
    validate_model: bool = True,
) -> dict[str, Any]:
    """Decode a complete versioned ``.mgeo`` byte string."""

    view = memoryview(data).cast("B")
    try:
        return _decode_mgeo_view(
            view,
            max_file_bytes=max_file_bytes,
            validate_model=validate_model,
        )
    finally:
        view.release()


def write_world_binary(
    path: Path,
    payload: dict[str, Any],
    *,
    validate_model: bool = True,
) -> None:
    """Atomically write checksummed ``.mgeo``; validate its model by default."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    packed = _pack_payload(payload, validate_model=validate_model)
    header = _header(packed, _world_schema(payload))

    existing_mode: int | None = None
    try:
        existing_mode = stat.S_IMODE(path.stat().st_mode)
    except FileNotFoundError:
        pass

    temporary_path: Path | None = None
    descriptor: int | None = None
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        flags |= getattr(os, "O_BINARY", 0)
        for _ in range(128):
            temporary_path = path.parent / (
                f".{path.name}.{secrets.token_hex(8)}.tmp"
            )
            try:
                descriptor = os.open(temporary_path, flags, 0o666)
                break
            except FileExistsError:
                temporary_path = None
        if descriptor is None or temporary_path is None:
            raise FileExistsError(
                f"could not allocate a temporary file beside {path}"
            )
        if existing_mode is not None:
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, existing_mode)
            else:
                os.chmod(temporary_path, existing_mode)
        with os.fdopen(descriptor, mode="wb") as handle:
            descriptor = None
            handle.write(header)
            handle.write(packed)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def write_world(
    path: Path,
    payload: dict[str, Any],
    *,
    format: WorldFormat = "auto",
    validate_model: bool = True,
) -> None:
    """Write JSON or ``.mgeo``, selecting by suffix when format is ``auto``."""

    path = Path(path)
    normalized = _normalize_format(format)
    if normalized == "auto":
        normalized = "mgeo" if path.suffix.lower() in MGEO_SUFFIXES else "json"
    if normalized == "mgeo":
        write_world_binary(path, payload, validate_model=validate_model)
        return

    # Import lazily to avoid a module cycle: io re-exports this façade.
    from .io import write_json

    if validate_model:
        validate_world_payload(payload)
    write_json(path, payload)


def read_world(
    path: Path,
    *,
    format: WorldFormat = "auto",
    max_file_bytes: int = DEFAULT_MAX_WORLD_FILE_BYTES,
    validate_model: bool = True,
) -> dict[str, Any]:
    """Load JSON or ``.mgeo`` by content, validating its value model by default."""

    path = Path(path)
    normalized = _normalize_format(format)
    if max_file_bytes < 0:
        raise ValueError("max_file_bytes must be nonnegative")
    with path.open("rb") as handle:
        file_size = os.fstat(handle.fileno()).st_size
        if file_size > max_file_bytes:
            raise WorldSerializationError(
                f"world file is {file_size} bytes; limit is {max_file_bytes} bytes"
            )
        prefix = handle.read(len(MGEO_MAGIC))
        if normalized == "auto":
            normalized = "mgeo" if prefix == MGEO_MAGIC else "json"

        if normalized == "json":
            if prefix == MGEO_MAGIC:
                raise WorldSerializationError(
                    "binary .mgeo file was requested as JSON"
                )
            handle.seek(0)
            raw_json = handle.read(max_file_bytes + 1)
            if len(raw_json) > max_file_bytes:
                raise WorldSerializationError(
                    f"world file exceeds the {max_file_bytes}-byte limit"
                )
            try:
                decoded = json.loads(raw_json)
            except RecursionError as exc:
                raise WorldSerializationError(
                    "JSON world nesting exceeds the decoder limit"
                ) from exc
            if type(decoded) is not dict:
                raise WorldSerializationError("decoded world root must be an object")
            if validate_model:
                validate_world_payload(decoded)
            return decoded

        if file_size == 0:
            raise WorldSerializationError("empty .mgeo file")
        if prefix != MGEO_MAGIC:
            raise WorldSerializationError("invalid .mgeo magic")
        with mmap.mmap(handle.fileno(), length=0, access=mmap.ACCESS_READ) as mapped:
            view = memoryview(mapped)
            try:
                return _decode_mgeo_view(
                    view,
                    max_file_bytes=max_file_bytes,
                    validate_model=validate_model,
                )
            finally:
                view.release()


def _normalize_format(format: WorldFormat) -> Literal["auto", "json", "mgeo"]:
    if format == "auto":
        return "auto"
    if format == "json":
        return "json"
    if format in {"mgeo", "msgpack", "binary"}:
        return "mgeo"
    raise ValueError("world format must be auto, json, or mgeo")
