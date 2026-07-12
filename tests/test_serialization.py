from __future__ import annotations

import math
import stat
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import msgpack
from typer.testing import CliRunner

from magic_geo import serialization as serialization_module
from magic_geo.cli import app
from magic_geo.io import read_world, write_json, write_world
from magic_geo.serialization import (
    MGEO_HEADER,
    MGEO_HEADER_SIZE,
    MGEO_MAGIC,
    WorldSerializationError,
    dumps_world,
    loads_world,
)


def sample_world() -> dict[str, object]:
    return {
        "schema_version": 1,
        "name": "Tierra \"rápida\"\n🌍\u0001",
        "none": None,
        "truth": True,
        "integer": 1,
        "uint64": 2**64 - 1,
        "int64": -(2**63),
        "values": [
            -0.0,
            0.0,
            math.nextafter(0.0, 1.0),
            1.2345678901234567,
            1.7976931348623157e308,
        ],
        "empty_object": {},
        "empty_array": [],
        "nested": {"records": [{"id": 0}, {"id": 1}]},
    }


class WorldSerializationTests(TestCase):
    def test_binary_round_trip_preserves_json_value_semantics(self) -> None:
        world = sample_world()
        encoded = dumps_world(world)
        decoded = loads_world(encoded)

        self.assertEqual(decoded, world)
        self.assertIs(type(decoded["truth"]), bool)
        self.assertIs(type(decoded["integer"]), int)
        self.assertEqual(decoded["uint64"], 2**64 - 1)
        self.assertEqual(decoded["int64"], -(2**63))
        original_values = world["values"]
        decoded_values = decoded["values"]
        assert isinstance(original_values, list)
        assert isinstance(decoded_values, list)
        self.assertEqual(
            [struct.pack(">d", value) for value in decoded_values],
            [struct.pack(">d", value) for value in original_values],
        )

    def test_encoding_is_deterministic_and_does_not_preserve_aliases(self) -> None:
        shared = [1, 2, 3]
        world = {"schema_version": 1, "left": shared, "right": shared}

        first = dumps_world(world)
        second = dumps_world(world)
        decoded = loads_world(first)

        self.assertEqual(first, second)
        self.assertEqual(decoded["left"], decoded["right"])
        self.assertIsNot(decoded["left"], decoded["right"])

        tuple_world = {"schema_version": 1, "sequence": (1, 2, 3)}
        self.assertEqual(loads_world(dumps_world(tuple_world))["sequence"], [1, 2, 3])

    def test_file_facade_keeps_json_and_selects_mgeo_by_suffix(self) -> None:
        world = sample_world()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            json_path = root / "world.json"
            direct_json_path = root / "direct.json"
            binary_path = root / "world.mgeo"
            disguised_binary_path = root / "world.data"

            write_world(json_path, world)
            write_json(direct_json_path, world)
            write_world(binary_path, world)
            disguised_binary_path.write_bytes(binary_path.read_bytes())

            self.assertEqual(json_path.read_bytes(), direct_json_path.read_bytes())
            self.assertEqual(binary_path.read_bytes()[:8], MGEO_MAGIC)
            self.assertEqual(
                stat.S_IMODE(binary_path.stat().st_mode),
                stat.S_IMODE(json_path.stat().st_mode),
            )
            self.assertEqual(read_world(json_path), world)
            self.assertEqual(read_world(binary_path), world)
            self.assertEqual(read_world(disguised_binary_path), world)
            with self.assertRaisesRegex(WorldSerializationError, "limit"):
                read_world(
                    json_path,
                    max_file_bytes=json_path.stat().st_size - 1,
                )
            small_json_path = root / "small.json"
            small_json_path.write_bytes(b'{"schema_version":1}')
            self.assertEqual(
                read_world(
                    small_json_path,
                    max_file_bytes=small_json_path.stat().st_size,
                ),
                {"schema_version": 1},
            )
            deeply_nested_path = root / "deep.json"
            deeply_nested_path.write_bytes(
                b'{"schema_version":1,"deep":' +
                b"[" * 10_000 + b"0" + b"]" * 10_000 + b"}"
            )
            with self.assertRaisesRegex(WorldSerializationError, "nesting"):
                read_world(deeply_nested_path)

    def test_binary_write_atomically_replaces_existing_file(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            path.write_bytes(b"old incomplete data")
            path.chmod(0o640)
            write_world(path, sample_world())

            self.assertEqual(read_world(path), sample_world())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o640)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_corrupt_headers_payloads_and_limits_fail_closed(self) -> None:
        encoded = dumps_world(sample_world())

        def with_header_field(index: int, value: int | bytes) -> bytes:
            fields = list(MGEO_HEADER.unpack_from(encoded))
            fields[index] = value
            return MGEO_HEADER.pack(*fields) + encoded[MGEO_HEADER_SIZE:]

        malformed = [
            b"",
            encoded[: MGEO_HEADER_SIZE - 1],
            b"BROKEN!!" + encoded[8:],
            with_header_field(1, 2),
            with_header_field(2, 1),
            with_header_field(3, 99),
            with_header_field(4, 1),
            with_header_field(5, MGEO_HEADER_SIZE + 1),
            with_header_field(6, len(encoded)),
            with_header_field(8, 2),
            encoded[:-1],
            encoded + b"trailing",
            encoded[:-1] + bytes([encoded[-1] ^ 0x01]),
        ]
        for data in malformed:
            with self.subTest(length=len(data), prefix=data[:8]):
                with self.assertRaises(WorldSerializationError):
                    loads_world(data)

        with self.assertRaises(WorldSerializationError):
            loads_world(encoded, max_file_bytes=len(encoded) - 1)

    def test_invalid_roots_schema_and_values_are_rejected(self) -> None:
        with self.assertRaisesRegex(WorldSerializationError, "schema_version"):
            dumps_world({"name": "missing schema"})
        with self.assertRaisesRegex(WorldSerializationError, "world root"):
            dumps_world([])  # type: ignore[arg-type]
        with self.assertRaisesRegex(WorldSerializationError, "non-JSON"):
            dumps_world({"schema_version": 1, "bad": {1, 2, 3}})
        invalid_values = [
            math.nan,
            math.inf,
            b"binary",
            msgpack.Timestamp(0, 0),
            2**64,
            -(2**63) - 1,
            "\ud800",
        ]
        for value in invalid_values:
            with self.subTest(invalid_value=repr(value)):
                with self.assertRaises(WorldSerializationError):
                    dumps_world({"schema_version": 1, "bad": value})
        with self.assertRaisesRegex(WorldSerializationError, "keys must be strings"):
            dumps_world({"schema_version": 1, "bad": {1: "integer key"}})

        cyclic: dict[str, object] = {"schema_version": 1}
        cyclic["cycle"] = cyclic
        with self.assertRaisesRegex(WorldSerializationError, "reference cycle"):
            dumps_world(cyclic)

        too_deep: dict[str, object] = {"schema_version": 1}
        cursor = too_deep
        for _ in range(66):
            child: dict[str, object] = {}
            cursor["child"] = child
            cursor = child
        with self.assertRaisesRegex(WorldSerializationError, "nesting"):
            dumps_world(too_deep)

        with patch.object(serialization_module, "DEFAULT_MAX_ARRAY_LENGTH", 2):
            with self.assertRaisesRegex(WorldSerializationError, "array"):
                dumps_world({"schema_version": 1, "bad": [1, 2, 3]})
        with patch.object(serialization_module, "DEFAULT_MAX_MAP_LENGTH", 2):
            with self.assertRaisesRegex(WorldSerializationError, "object"):
                dumps_world(
                    {
                        "schema_version": 1,
                        "bad": {"a": 1, "b": 2, "c": 3},
                    }
                )
        with patch.object(serialization_module, "DEFAULT_MAX_STRING_BYTES", 14):
            with self.assertRaisesRegex(WorldSerializationError, "string"):
                dumps_world({"schema_version": 1, "bad": "x" * 15})

        with TemporaryDirectory() as directory:
            strict_json = Path(directory) / "strict.json"
            with self.assertRaises(WorldSerializationError):
                write_world(
                    strict_json,
                    {"schema_version": 1, "bad": 2**64},
                    format="json",
                )

        packed_list = msgpack.packb([1, 2, 3], use_bin_type=True)
        fields = list(MGEO_HEADER.unpack_from(dumps_world(sample_world())))
        fields[6] = len(packed_list)
        import zlib

        fields[7] = zlib.crc32(packed_list)
        fields[8] = 1
        non_object = MGEO_HEADER.pack(*fields) + packed_list
        with self.assertRaisesRegex(WorldSerializationError, "root"):
            loads_world(non_object)

        extension_payload = msgpack.packb(
            {"schema_version": 1, "extension": msgpack.ExtType(1, b"bad")},
            use_bin_type=True,
        )
        fields[6] = len(extension_payload)
        fields[7] = zlib.crc32(extension_payload)
        extension_world = MGEO_HEADER.pack(*fields) + extension_payload
        with self.assertRaisesRegex(WorldSerializationError, "extension|max_ext_len"):
            loads_world(extension_world)

        invalid_decoded_values = [
            math.nan,
            math.inf,
            b"binary",
            msgpack.Timestamp(0, 0),
        ]
        for value in invalid_decoded_values:
            packed = msgpack.packb(
                {"schema_version": 1, "bad": value},
                use_bin_type=True,
            )
            fields[6] = len(packed)
            fields[7] = zlib.crc32(packed)
            invalid_world = MGEO_HEADER.pack(*fields) + packed
            with self.subTest(invalid_decoded_value=repr(value)):
                with self.assertRaises(WorldSerializationError):
                    loads_world(invalid_world)

    def test_read_auto_detection_uses_content_not_suffix(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            write_world(path, sample_world(), format="json")
            self.assertEqual(read_world(path), sample_world())

    def test_json_writer_rejects_nonfinite_values(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            with self.assertRaises(ValueError):
                write_json(path, {"value": math.nan})
            path.write_text('{"value": NaN}', encoding="utf-8")
            with self.assertRaisesRegex(WorldSerializationError, "non-finite"):
                read_world(path)
            path.write_text('{"value": "\\ud800"}', encoding="utf-8")
            with self.assertRaisesRegex(WorldSerializationError, "UTF-8"):
                read_world(path)

    def test_cli_world_consumer_accepts_mgeo(self) -> None:
        world = {
            "schema_version": 1,
            "mesh_backend": "fibonacci_sphere",
            "summary": {
                "cell_count": 0,
                "ocean_fraction": 0.5,
                "river_downhill_fraction": 1.0,
            },
            "cells": [],
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            write_world(path, world)
            result = CliRunner().invoke(app, ["validate", "--world", str(path)])

        # The deliberately incomplete fixture fails domain validation, proving
        # that the command got past binary decoding and into normal validation.
        self.assertEqual(result.exit_code, 1)
        self.assertIn("FAIL sea level model", result.output)
        self.assertNotIn("Invalid world file", result.output)
