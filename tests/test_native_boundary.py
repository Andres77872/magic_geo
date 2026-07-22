"""Error paths at the ctypes/native boundary and in the ``.mgeo`` container.

Every case here drives a branch a healthy generated world cannot reach: a
library that cannot be resolved or is missing a symbol, a pointer that comes
back null or carries malformed MessagePack, a schema-2 payload with a broken
``planet_parameters`` snapshot, and containers whose header, length, or codec
has been corrupted. Each case is paired with an untampered control so a passing
assertion proves the failure came from the tamper.
"""

from __future__ import annotations

import ctypes
import errno
import json
import math
import os
import secrets
import stat
import zlib
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import msgpack

from magic_geo import native as native_module
from magic_geo import serialization as serialization_module
from magic_geo.config import config_to_native, load_config
from magic_geo.native import backend_info, generate_geo_world, generate_world
from magic_geo.planet_parameters import PLANET_PARAMETER_DEFAULTS
from magic_geo.serialization import (
    MGEO_HEADER,
    MGEO_HEADER_SIZE,
    MGEO_MAGIC,
    WorldSerializationError,
    dumps_world,
    loads_world,
    read_world,
    validate_world_payload,
    write_world,
)

from support.builders import sample_world
from support.nativestub import patch_loaded_library


_ABSENT = object()

_REQUIRED_NATIVE_SYMBOLS = (
    "magic_geo_backend_info_json",
    "magic_geo_generate_json_v3",
    "magic_geo_generate_geo_json_v3",
    "magic_geo_generate_msgpack_v3",
    "magic_geo_generate_geo_msgpack_v3",
    "magic_geo_free_string",
    "magic_geo_free_buffer",
)


class _ModuleProxy:
    """Stand in for a module inside one namespace, overriding or hiding names.

    ``patch.object(module_under_test, "os", _ModuleProxy(os, fchmod=_ABSENT))``
    reaches the ``hasattr``/``getattr`` fallbacks without mutating the real
    module for any other importer.
    """

    def __init__(self, module: object, **overrides: object) -> None:
        self.__dict__["_module"] = module
        self.__dict__["_overrides"] = overrides

    def __getattr__(self, name: str) -> object:
        overrides = self.__dict__["_overrides"]
        if name in overrides:
            value = overrides[name]
            if value is _ABSENT:
                raise AttributeError(name)
            return value
        return getattr(self.__dict__["_module"], name)


class _StubFunction:
    """A ctypes-function stand-in that records its calls."""

    def __init__(self, result: object = 0) -> None:
        self.result = result
        self.argtypes: object = None
        self.restype: object = None
        self.calls: list[tuple[object, ...]] = []

    def __call__(self, *args: object) -> object:
        self.calls.append(args)
        return self.result


class _StubLibrary:
    """A CDLL stand-in exposing exactly the symbols it was asked to expose."""

    def __init__(self, *, omit: tuple[str, ...] = ()) -> None:
        for name in _REQUIRED_NATIVE_SYMBOLS:
            if name not in omit:
                setattr(self, name, _StubFunction())


def _healthy_schema_payload() -> dict[str, object]:
    return {
        "schema_version": 2,
        "planet_parameters": dict(PLANET_PARAMETER_DEFAULTS),
    }


def _native_buffer(raw: bytes) -> tuple[ctypes.Array, int]:
    """Return a live ctypes buffer holding ``raw`` and its address."""
    buffer = (ctypes.c_ubyte * max(len(raw), 1)).from_buffer_copy(
        raw or b"\x00"
    )
    return buffer, ctypes.addressof(buffer)


class NativeLibraryResolutionTests(TestCase):
    def test_untampered_resolution_finds_the_packaged_library(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MAGIC_GEO_NATIVE_LIBRARY", None)
            resolved = native_module._library_path()

        self.assertTrue(resolved.is_file())
        self.assertEqual(resolved.name, native_module._native_library_names()[0])
        self.assertEqual(
            resolved.parent,
            Path(native_module.__file__).resolve().parent,
        )

    def test_missing_packaged_library_names_the_build_command(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MAGIC_GEO_NATIVE_LIBRARY", None)
            with patch.object(
                native_module,
                "_native_library_names",
                return_value=("libmagic_geo_native_absent.so",),
            ):
                with self.assertRaises(RuntimeError) as caught:
                    native_module._library_path()

        message = str(caught.exception)
        self.assertIn("native library was not found", message)
        self.assertIn("cmake -S . -B build", message)

    def test_env_override_must_name_an_existing_file(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "not-built.so"
            cases = {
                "missing_path": missing,
                "directory_instead_of_file": root,
            }
            for label, candidate in cases.items():
                with self.subTest(override=label):
                    with patch.dict(
                        os.environ,
                        {"MAGIC_GEO_NATIVE_LIBRARY": str(candidate)},
                    ):
                        with self.assertRaises(RuntimeError) as caught:
                            native_module._library_path()
                    message = str(caught.exception)
                    self.assertIn(
                        "MAGIC_GEO_NATIVE_LIBRARY does not name a file",
                        message,
                    )
                    self.assertIn(str(candidate.resolve()), message)

    def test_env_override_selects_the_named_file(self) -> None:
        with TemporaryDirectory() as directory:
            override = Path(directory) / "stand-in.so"
            override.write_bytes(b"not a real ELF, but it is a file")
            with patch.dict(
                os.environ,
                {"MAGIC_GEO_NATIVE_LIBRARY": str(override)},
            ):
                resolved = native_module._library_path()

            self.assertEqual(resolved, override.resolve())
            self.assertNotEqual(resolved.name, "libmagic_geo_native.so")

    def test_env_override_is_honoured_end_to_end_by_backend_info(self) -> None:
        # The override points at a copy under a name the packaged search would
        # never produce, so loading it proves the override was honoured rather
        # than merely tolerated.
        packaged = Path(native_module.__file__).resolve().parent / (
            native_module._native_library_names()[0]
        )
        with TemporaryDirectory() as directory:
            relocated = Path(directory) / "relocated_magic_geo_native.so"
            relocated.write_bytes(packaged.read_bytes())
            self.assertNotEqual(
                relocated.name,
                native_module._native_library_names()[0],
            )

            with patch.dict(
                os.environ,
                {"MAGIC_GEO_NATIVE_LIBRARY": str(relocated)},
            ):
                self.assertEqual(native_module._library_path(), relocated)
                overridden = backend_info()

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("MAGIC_GEO_NATIVE_LIBRARY", None)
                self.assertEqual(native_module._library_path(), packaged)
                default = backend_info()

        self.assertIsInstance(overridden, dict)
        self.assertIn("active_backend", overridden)
        self.assertEqual(overridden, default)

    def test_empty_env_override_falls_through_to_the_packaged_library(self) -> None:
        with patch.dict(os.environ, {"MAGIC_GEO_NATIVE_LIBRARY": ""}):
            resolved = native_module._library_path()

        self.assertEqual(resolved.name, native_module._native_library_names()[0])


class NativeLibrarySymbolTests(TestCase):
    def test_complete_library_binds_every_v3_signature(self) -> None:
        stub = _StubLibrary()
        with patch_loaded_library(stub):
            loaded = native_module._load_library()

        self.assertIs(loaded, stub)
        self.assertEqual(stub.magic_geo_backend_info_json.argtypes, [])
        self.assertIs(stub.magic_geo_backend_info_json.restype, ctypes.c_void_p)
        self.assertIs(stub.magic_geo_generate_json_v3.restype, ctypes.c_void_p)
        self.assertIs(stub.magic_geo_generate_geo_json_v3.restype, ctypes.c_void_p)
        self.assertIs(stub.magic_geo_generate_msgpack_v3.restype, ctypes.c_void_p)
        self.assertIs(
            stub.magic_geo_generate_geo_msgpack_v3.restype,
            ctypes.c_void_p,
        )
        self.assertIsNone(stub.magic_geo_free_string.restype)
        self.assertIsNone(stub.magic_geo_free_buffer.restype)

        config_pointer = ctypes.POINTER(native_module.NativeConfigV3)
        size_pointer = ctypes.POINTER(ctypes.c_size_t)
        self.assertEqual(stub.magic_geo_generate_json_v3.argtypes, [config_pointer])
        self.assertEqual(
            stub.magic_geo_generate_geo_json_v3.argtypes,
            [config_pointer],
        )
        self.assertEqual(
            stub.magic_geo_generate_msgpack_v3.argtypes,
            [config_pointer, size_pointer],
        )
        self.assertEqual(
            stub.magic_geo_generate_geo_msgpack_v3.argtypes,
            [config_pointer, size_pointer],
        )
        self.assertEqual(stub.magic_geo_free_string.argtypes, [ctypes.c_void_p])
        self.assertEqual(stub.magic_geo_free_buffer.argtypes, [ctypes.c_void_p])

    def test_any_missing_symbol_demands_a_rebuild(self) -> None:
        for symbol in _REQUIRED_NATIVE_SYMBOLS:
            with self.subTest(missing_symbol=symbol):
                stub = _StubLibrary(omit=(symbol,))
                self.assertFalse(hasattr(stub, symbol))
                with patch_loaded_library(stub):
                    with self.assertRaises(RuntimeError) as caught:
                        native_module._load_library()
                message = str(caught.exception)
                self.assertIn(
                    "native library does not expose the current V3 JSON and "
                    "MessagePack ABI",
                    message,
                )
                self.assertIn("rebuild magic_geo_native", message)
                self.assertIsInstance(caught.exception.__cause__, AttributeError)


class NativeJsonPointerTests(TestCase):
    def test_untampered_pointer_decodes_and_is_freed(self) -> None:
        library = _StubLibrary()
        buffer = ctypes.create_string_buffer(b'{"schema_version": 2}')
        pointer = ctypes.cast(buffer, ctypes.c_void_p).value
        assert pointer is not None

        payload = native_module._consume_json_pointer(library, pointer)

        self.assertEqual(payload, {"schema_version": 2})
        self.assertEqual(library.magic_geo_free_string.calls, [(pointer,)])

    def test_null_pointer_is_reported_without_a_free(self) -> None:
        library = _StubLibrary()

        with self.assertRaises(RuntimeError) as caught:
            native_module._consume_json_pointer(library, 0)

        self.assertIn("null JSON pointer", str(caught.exception))
        self.assertEqual(library.magic_geo_free_string.calls, [])

    def test_non_null_pointer_with_no_bytes_still_frees(self) -> None:
        # The address is a live buffer rather than a literal so that a failure
        # of the ``cast`` override surfaces as an assertion rather than as a
        # segmentation fault that would take the whole suite down with it.
        library = _StubLibrary()
        buffer, pointer = _native_buffer(b'{"schema_version": 2}\x00')
        proxy = _ModuleProxy(ctypes, cast=lambda *args: ctypes.c_char_p(None))

        with patch.object(native_module, "ctypes", proxy):
            with self.assertRaises(RuntimeError) as caught:
                native_module._consume_json_pointer(library, pointer)

        self.assertIn("empty JSON pointer", str(caught.exception))
        self.assertEqual(library.magic_geo_free_string.calls, [(pointer,)])
        del buffer

    def test_malformed_json_frees_before_it_propagates(self) -> None:
        library = _StubLibrary()
        buffer = ctypes.create_string_buffer(b"{not json")
        pointer = ctypes.cast(buffer, ctypes.c_void_p).value
        assert pointer is not None

        with self.assertRaises(json.JSONDecodeError):
            native_module._consume_json_pointer(library, pointer)

        self.assertEqual(library.magic_geo_free_string.calls, [(pointer,)])

    def test_error_object_is_raised_as_the_native_message(self) -> None:
        library = _StubLibrary()
        buffer = ctypes.create_string_buffer(b'{"error": "plate_count too small"}')
        pointer = ctypes.cast(buffer, ctypes.c_void_p).value
        assert pointer is not None

        with self.assertRaises(RuntimeError) as caught:
            native_module._consume_json_pointer(library, pointer)

        self.assertEqual(str(caught.exception), "plate_count too small")


class NativeMessagePackPointerTests(TestCase):
    def test_untampered_buffer_decodes_and_is_freed(self) -> None:
        library = _StubLibrary()
        raw = msgpack.packb({"schema_version": 2}, use_bin_type=True)
        buffer, pointer = _native_buffer(raw)

        payload = native_module._consume_msgpack_pointer(library, pointer, len(raw))

        self.assertEqual(payload, {"schema_version": 2})
        self.assertEqual(library.magic_geo_free_buffer.calls, [(pointer,)])
        del buffer

    def test_null_pointer_is_reported_without_a_free(self) -> None:
        library = _StubLibrary()

        with self.assertRaises(RuntimeError) as caught:
            native_module._consume_msgpack_pointer(library, 0, 16)

        self.assertIn("null MessagePack pointer", str(caught.exception))
        self.assertEqual(library.magic_geo_free_buffer.calls, [])

    def test_non_positive_size_is_reported_and_still_freed(self) -> None:
        for size in (0, -1):
            with self.subTest(size=size):
                library = _StubLibrary()
                buffer, pointer = _native_buffer(b"\x90")
                with self.assertRaises(RuntimeError) as caught:
                    native_module._consume_msgpack_pointer(library, pointer, size)
                self.assertIn("empty MessagePack buffer", str(caught.exception))
                self.assertEqual(library.magic_geo_free_buffer.calls, [(pointer,)])
                del buffer

    def test_malformed_buffers_are_wrapped_and_freed(self) -> None:
        # The wrapper text is shared by every rejection, so each case also pins
        # the ``__cause__`` msgpack raises: that is what proves, for instance,
        # that ``max_bin_len=0`` and ``strict_map_key=True`` are the settings
        # doing the rejecting rather than some incidental decode failure.
        cases = {
            "never_used_byte": (b"\xc1", msgpack.FormatError, ""),
            "trailing_extra_object": (
                msgpack.packb(1) + msgpack.packb(2),
                msgpack.ExtraData,
                "extra data",
            ),
            "truncated_map": (b"\x81\xa1", ValueError, "incomplete input"),
            "binary_value_over_max_bin_len": (
                msgpack.packb({"a": b"x"}, use_bin_type=True),
                ValueError,
                "exceeds max_bin_len(0)",
            ),
            "integer_map_key": (
                msgpack.packb({1: "a"}),
                ValueError,
                "int is not allowed for map key when strict_map_key=True",
            ),
            "invalid_utf8_string": (
                b"\xa2\xff\xfe",
                UnicodeDecodeError,
                "'utf-8' codec can't decode byte 0xff",
            ),
        }
        for label, (raw, cause_type, cause_fragment) in cases.items():
            with self.subTest(malformed=label):
                library = _StubLibrary()
                buffer, pointer = _native_buffer(raw)
                with self.assertRaises(RuntimeError) as caught:
                    native_module._consume_msgpack_pointer(
                        library,
                        pointer,
                        len(raw),
                    )
                cause = caught.exception.__cause__
                self.assertIsInstance(cause, cause_type)
                self.assertIn(cause_fragment, str(cause))
                self.assertEqual(
                    str(caught.exception),
                    f"native library returned invalid MessagePack: {cause}",
                )
                self.assertEqual(
                    library.magic_geo_free_buffer.calls,
                    [(pointer,)],
                )
                del buffer

    def test_an_unmappable_size_still_frees_the_buffer(self) -> None:
        # A size the host cannot even describe as an array aborts before the
        # memoryview exists; the buffer must still be handed back.
        library = _StubLibrary()
        buffer, pointer = _native_buffer(b"\x90")

        with self.assertRaises(OverflowError):
            native_module._consume_msgpack_pointer(library, pointer, 2**63)

        self.assertEqual(library.magic_geo_free_buffer.calls, [(pointer,)])
        del buffer

    def test_non_object_root_is_rejected(self) -> None:
        library = _StubLibrary()
        raw = msgpack.packb([1, 2, 3], use_bin_type=True)
        buffer, pointer = _native_buffer(raw)

        with self.assertRaises(RuntimeError) as caught:
            native_module._consume_msgpack_pointer(library, pointer, len(raw))

        self.assertEqual(
            str(caught.exception),
            "native MessagePack root is not an object",
        )
        self.assertEqual(library.magic_geo_free_buffer.calls, [(pointer,)])
        del buffer

    def test_error_object_is_raised_as_the_native_message(self) -> None:
        library = _StubLibrary()
        raw = msgpack.packb({"error": "cell_count out of range"}, use_bin_type=True)
        buffer, pointer = _native_buffer(raw)

        with self.assertRaises(RuntimeError) as caught:
            native_module._consume_msgpack_pointer(library, pointer, len(raw))

        self.assertEqual(str(caught.exception), "cell_count out of range")
        del buffer

    def test_extension_hook_names_the_offending_extension_code(self) -> None:
        # ``max_ext_len=0`` makes msgpack reject extension frames before the
        # hook runs, so the hook is only reachable directly. It stays as the
        # belt-and-braces guard if that limit is ever relaxed.
        with self.assertRaises(ValueError) as caught:
            native_module._reject_msgpack_extension(7, b"payload")

        self.assertEqual(
            str(caught.exception),
            "MessagePack extension type 7 is not valid in a native world",
        )


class NativeSchemaGateTests(TestCase):
    def test_untampered_schema_2_payload_passes_through(self) -> None:
        payload = _healthy_schema_payload()

        self.assertIs(native_module._require_current_world_schema(payload), payload)

    def test_incomplete_planet_parameters_names_every_missing_key(self) -> None:
        payload = _healthy_schema_payload()
        removed = ("gravity_g", "axial_tilt_deg")
        for key in removed:
            self.assertIn(key, payload["planet_parameters"])
            del payload["planet_parameters"][key]

        with self.assertRaises(RuntimeError) as caught:
            native_module._require_current_world_schema(payload)

        message = str(caught.exception)
        self.assertIn("incomplete planet_parameters snapshot", message)
        self.assertIn("axial_tilt_deg, gravity_g", message)

    def test_non_dict_planet_parameters_is_rejected(self) -> None:
        for replacement in ([], "6371", None, 0):
            with self.subTest(planet_parameters=repr(replacement)):
                payload = _healthy_schema_payload()
                payload["planet_parameters"] = replacement
                with self.assertRaises(RuntimeError) as caught:
                    native_module._require_current_world_schema(payload)
                self.assertIn(
                    "without explicit planet_parameters",
                    str(caught.exception),
                )

    def test_each_invalid_planet_parameter_value_is_named(self) -> None:
        cases = {
            "boolean": ("gravity_g", True),
            "string": ("day_length_hours", "24.0"),
            "none": ("greenhouse_factor", None),
            "list": ("internal_heat", [1.0]),
            "nan": ("axial_tilt_deg", math.nan),
            "positive_infinity": ("stellar_luminosity", math.inf),
            "negative_infinity": ("orbital_eccentricity", -math.inf),
            "overflowing_integer": ("atmosphere_pressure_bar", 10**400),
            "zero_radius": ("radius_km", 0.0),
            "negative_radius": ("radius_km", -6371.0),
            "zero_gravity": ("gravity_g", 0.0),
            "negative_age": ("geological_age_ga", -4.5),
        }
        for label, (key, value) in cases.items():
            with self.subTest(invalid=label):
                payload = _healthy_schema_payload()
                self.assertNotEqual(
                    repr(payload["planet_parameters"][key]),
                    repr(value),
                    "tamper must change the value it overwrites",
                )
                payload["planet_parameters"][key] = value
                with self.assertRaises(RuntimeError) as caught:
                    native_module._require_current_world_schema(payload)
                self.assertEqual(
                    str(caught.exception),
                    f"native library returned invalid planet_parameters.{key}",
                )

    def test_a_negative_non_dimension_parameter_is_accepted(self) -> None:
        # Only radius, gravity, and age carry a positivity rule; pinning that
        # keeps the previous case honest about which branch it exercised.
        payload = _healthy_schema_payload()
        payload["planet_parameters"]["internal_heat"] = -1.0

        self.assertIs(native_module._require_current_world_schema(payload), payload)


class NativeGenerationArgumentTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        cls.native_config = config_to_native(type(config).model_validate(data))

    def test_every_generator_rejects_an_unknown_serialization(self) -> None:
        for generator in (generate_world, generate_geo_world):
            for serialization in ("", "unknown", "JSON", "MessagePack", "yaml"):
                with self.subTest(
                    generator=generator.__name__,
                    serialization=serialization,
                ):
                    with self.assertRaises(ValueError) as caught:
                        generator(
                            deepcopy(self.native_config),
                            serialization=serialization,
                        )
                    self.assertEqual(
                        str(caught.exception),
                        "serialization must be auto, json, or msgpack",
                    )

    def test_the_accepted_serialization_arguments_agree(self) -> None:
        worlds = {
            name: generate_world(
                deepcopy(self.native_config),
                serialization=name,
            )
            for name in ("auto", "json", "msgpack")
        }

        self.assertEqual(worlds["auto"], worlds["msgpack"])
        self.assertEqual(worlds["auto"], worlds["json"])
        self.assertEqual(worlds["json"]["schema_version"], 2)


class SerializationRetiredFieldScanTests(TestCase):
    def test_non_object_history_entries_are_skipped_not_crashed(self) -> None:
        payload = {
            "schema_version": 2,
            "cells": [
                None,
                42,
                "not a cell",
                {"initial_crust_age_ma": 0.0},
            ],
            "earth_system_feedback_history": [
                [],
                {"mean_erosion_rate_m_per_step": 0.0},
            ],
            "numeric_depression_correction_history": [
                "not an event",
                {"applied_fill_volume_km3": 0.0},
            ],
            "plate_motion_history": [
                None,
                {"crust_source_reuse_count": 0},
            ],
        }

        retired = serialization_module.retired_world_schema_fields(payload)

        self.assertEqual(
            retired,
            (
                "cells[3].initial_crust_age_ma",
                "earth_system_feedback_history[1].mean_erosion_rate_m_per_step",
                "numeric_depression_correction_history[1]"
                ".applied_fill_volume_km3",
                "plate_motion_history[1].crust_source_reuse_count",
            ),
        )

    def test_non_list_containers_are_ignored_entirely(self) -> None:
        payload = {
            "schema_version": 2,
            "cells": {"0": {"initial_crust_age_ma": 0.0}},
            "earth_system_feedback_history": "none",
            "numeric_depression_correction_history": 0,
            "plate_motion_history": None,
            "summary": "not an object",
        }

        self.assertEqual(
            serialization_module.retired_world_schema_fields(payload),
            (),
        )


class SerializationValueModelTests(TestCase):
    def test_a_non_object_root_is_rejected_by_the_validator(self) -> None:
        for root in ([], (), "world", 0, None):
            with self.subTest(root=repr(root)):
                with self.assertRaises(WorldSerializationError) as caught:
                    validate_world_payload(root)  # type: ignore[arg-type]
                self.assertEqual(
                    str(caught.exception),
                    "world root must be an object",
                )

        self.assertIsNone(validate_world_payload({"schema_version": 1}))

    def test_unpackable_values_survive_a_skipped_model_validation(self) -> None:
        # ``validate_model=False`` is the only way to reach msgpack's own
        # rejection: the value model catches these first when it runs.
        control = dumps_world(
            {"schema_version": 1, "fine": [1, 2, 3]},
            validate_model=False,
        )
        self.assertEqual(loads_world(control)["fine"], [1, 2, 3])

        for label, value in {
            "set": {1, 2, 3},
            "complex": complex(1, 2),
            "object": object(),
            "oversized_integer": 2**64,
        }.items():
            with self.subTest(unpackable=label):
                with self.assertRaises(WorldSerializationError) as caught:
                    dumps_world(
                        {"schema_version": 1, "bad": value},
                        validate_model=False,
                    )
                self.assertIn(
                    "world contains a value unsupported by MessagePack",
                    str(caught.exception),
                )

    def test_extension_hook_names_the_offending_extension_code(self) -> None:
        # Same story as the native hook: ``max_ext_len=0`` rejects extension
        # frames before ``ext_hook`` can run, so it is reachable only directly.
        with self.assertRaises(WorldSerializationError) as caught:
            serialization_module._reject_extension(3, b"payload")

        self.assertEqual(
            str(caught.exception),
            "MessagePack extension type 3 is not valid in a world payload",
        )


class MgeoContainerBoundaryTests(TestCase):
    def test_negative_byte_limits_are_a_plain_value_error(self) -> None:
        encoded = dumps_world(sample_world())
        self.assertEqual(loads_world(encoded, max_file_bytes=len(encoded)), sample_world())

        with self.assertRaises(ValueError) as caught:
            loads_world(encoded, max_file_bytes=-1)
        self.assertIs(type(caught.exception), ValueError)
        self.assertEqual(str(caught.exception), "max_file_bytes must be nonnegative")

        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            path.write_bytes(encoded)
            self.assertEqual(read_world(path), sample_world())
            with self.assertRaises(ValueError) as caught:
                read_world(path, max_file_bytes=-1)
            self.assertIs(type(caught.exception), ValueError)
            self.assertEqual(
                str(caught.exception),
                "max_file_bytes must be nonnegative",
            )

    def test_each_corrupted_header_field_names_its_own_defect(self) -> None:
        encoded = dumps_world(sample_world())
        fields = list(MGEO_HEADER.unpack_from(encoded))
        body = encoded[MGEO_HEADER_SIZE:]

        def tampered(index: int, value: object) -> bytes:
            mutated = list(fields)
            self.assertNotEqual(
                mutated[index],
                value,
                "tamper must change the header field it overwrites",
            )
            mutated[index] = value
            return MGEO_HEADER.pack(*mutated) + body

        broken_magic = b"NOTMGEO\n"
        self.assertEqual(len(broken_magic), len(MGEO_MAGIC))
        self.assertNotEqual(broken_magic, MGEO_MAGIC)

        cases = {
            "magic": (
                broken_magic + encoded[len(MGEO_MAGIC):],
                "invalid .mgeo magic",
            ),
            "major_version": (
                tampered(1, 2),
                "unsupported .mgeo version 2.0; expected 1.0",
            ),
            "minor_version": (
                tampered(2, 7),
                "unsupported .mgeo version 1.7; expected 1.0",
            ),
            "codec": (tampered(3, 4), "unsupported .mgeo codec 4"),
            "flags": (tampered(4, 0x20), "unsupported .mgeo flags 0x20"),
            "header_size": (
                tampered(5, MGEO_HEADER_SIZE + 8),
                f"unsupported .mgeo header size {MGEO_HEADER_SIZE + 8}",
            ),
            "payload_size": (
                tampered(6, len(body) + 3),
                ".mgeo payload length mismatch: header declares "
                f"{len(body) + 3}, file contains {len(body)}",
            ),
            "crc32": (
                tampered(7, (fields[7] ^ 0xFFFF) & 0xFFFFFFFF),
                ".mgeo checksum mismatch; the file is corrupt or incomplete",
            ),
            "world_schema": (
                tampered(8, 9),
                ".mgeo world schema does not match its container header",
            ),
        }
        for label, (data, message) in cases.items():
            with self.subTest(corrupted=label):
                with self.assertRaises(WorldSerializationError) as caught:
                    loads_world(data)
                self.assertEqual(str(caught.exception), message)

        self.assertEqual(loads_world(encoded), sample_world())

    def test_truncation_below_the_header_is_named_as_truncation(self) -> None:
        encoded = dumps_world(sample_world())
        for length in (0, 1, 8, MGEO_HEADER_SIZE - 1):
            with self.subTest(length=length):
                with self.assertRaises(WorldSerializationError) as caught:
                    loads_world(encoded[:length])
                self.assertEqual(str(caught.exception), "truncated .mgeo header")

    def test_a_file_limit_below_the_encoded_size_fails_closed(self) -> None:
        encoded = dumps_world(sample_world())

        with self.assertRaises(WorldSerializationError) as caught:
            loads_world(encoded, max_file_bytes=len(encoded) - 1)

        self.assertEqual(
            str(caught.exception),
            f"world file is {len(encoded)} bytes; limit is {len(encoded) - 1} bytes",
        )


class MgeoFileReaderTests(TestCase):
    def test_an_mgeo_file_requested_as_json_is_refused(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            write_world(path, sample_world())
            self.assertEqual(read_world(path, format="mgeo"), sample_world())

            with self.assertRaises(WorldSerializationError) as caught:
                read_world(path, format="json")

        self.assertEqual(
            str(caught.exception),
            "binary .mgeo file was requested as JSON",
        )

    def test_an_empty_file_requested_as_mgeo_is_named_empty(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "empty.mgeo"
            path.write_bytes(b"")

            with self.assertRaises(WorldSerializationError) as caught:
                read_world(path, format="mgeo")

        self.assertEqual(str(caught.exception), "empty .mgeo file")

    def test_a_json_file_requested_as_mgeo_is_rejected_by_magic(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            write_world(path, sample_world(), format="json")
            self.assertEqual(read_world(path), sample_world())

            with self.assertRaises(WorldSerializationError) as caught:
                read_world(path, format="mgeo")

        self.assertEqual(str(caught.exception), "invalid .mgeo magic")

    def test_a_short_prefix_file_requested_as_mgeo_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "stub.mgeo"
            path.write_bytes(b"MG")

            with self.assertRaises(WorldSerializationError) as caught:
                read_world(path, format="mgeo")

        self.assertEqual(str(caught.exception), "invalid .mgeo magic")

    def test_a_json_root_that_is_not_an_object_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            control = root / "object.json"
            control.write_bytes(b'{"schema_version": 1}')
            self.assertEqual(read_world(control), {"schema_version": 1})

            for label, raw in {
                "array": b"[1, 2, 3]",
                "string": b'"world"',
                "number": b"12",
                "null": b"null",
            }.items():
                with self.subTest(json_root=label):
                    path = root / f"{label}.json"
                    path.write_bytes(raw)
                    with self.assertRaises(WorldSerializationError) as caught:
                        read_world(path)
                    self.assertEqual(
                        str(caught.exception),
                        "decoded world root must be an object",
                    )

    def test_a_json_file_that_grew_after_its_stat_is_still_bounded(self) -> None:
        # ``fstat`` is taken before the read, so a file that grows in between
        # would slip past the first check; the post-read length guard is what
        # actually bounds the decoder. Shrinking the reported size simulates
        # exactly that race.
        real_fstat = os.fstat

        def understating_fstat(descriptor: int) -> os.stat_result:
            fields = list(real_fstat(descriptor))
            fields[6] = 0
            return os.stat_result(fields)

        with TemporaryDirectory() as directory:
            path = Path(directory) / "grew.json"
            path.write_bytes(b'{"schema_version": 1, "padding": "xxxxxxxxxx"}')

            self.assertEqual(
                read_world(path, max_file_bytes=path.stat().st_size),
                {"schema_version": 1, "padding": "xxxxxxxxxx"},
            )

            proxy = _ModuleProxy(os, fstat=understating_fstat)
            with patch.object(serialization_module, "os", proxy):
                with self.assertRaises(WorldSerializationError) as caught:
                    read_world(path, max_file_bytes=16)

        self.assertEqual(
            str(caught.exception),
            "world file exceeds the 16-byte limit",
        )


class MgeoAtomicWriteTests(TestCase):
    def test_a_colliding_temporary_name_is_retried(self) -> None:
        # ``handed_out`` is what proves the retry happened: a writer that never
        # collided would ask for exactly one name, and one that gave up on the
        # first collision would never reach the second.
        names = ("a" * 16, "b" * 16)
        handed_out: list[str] = []

        def token_hex(length: int) -> str:
            self.assertEqual(length, 8)
            value = names[len(handed_out)]
            handed_out.append(value)
            return value

        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            collision = path.parent / f".{path.name}.{names[0]}.tmp"
            collision.write_bytes(b"someone else got here first")

            proxy = _ModuleProxy(secrets, token_hex=token_hex)
            with patch.object(serialization_module, "secrets", proxy):
                write_world(path, sample_world())

            self.assertEqual(handed_out, list(names))
            self.assertEqual(read_world(path), sample_world())
            self.assertEqual(
                collision.read_bytes(),
                b"someone else got here first",
            )
            self.assertEqual(
                sorted(p.name for p in path.parent.glob(f".{path.name}.*.tmp")),
                [collision.name],
            )

    def test_exhausting_every_temporary_name_fails_closed(self) -> None:
        attempts: list[int] = []

        def token_hex(length: int) -> str:
            attempts.append(length)
            return "c" * 16

        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            collision = path.parent / f".{path.name}.{'c' * 16}.tmp"
            collision.write_bytes(b"occupied")

            proxy = _ModuleProxy(secrets, token_hex=token_hex)
            with patch.object(serialization_module, "secrets", proxy):
                with self.assertRaises(FileExistsError) as caught:
                    write_world(path, sample_world())

            # The writer must exhaust its whole budget before giving up.
            self.assertEqual(len(attempts), 128)
            self.assertEqual(
                str(caught.exception),
                f"could not allocate a temporary file beside {path}",
            )
            self.assertFalse(path.exists())
            self.assertEqual(collision.read_bytes(), b"occupied")

    def test_a_failure_after_open_closes_and_removes_the_temporary(self) -> None:
        opened: list[int] = []

        def recording_open(*args: object, **kwargs: object) -> int:
            descriptor = os.open(*args, **kwargs)  # type: ignore[arg-type]
            opened.append(descriptor)
            return descriptor

        def failing_fchmod(descriptor: int, mode: int) -> None:
            raise OSError(1, "fchmod is not permitted here")

        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            path.write_bytes(b"previous contents")
            path.chmod(0o640)

            proxy = _ModuleProxy(os, open=recording_open, fchmod=failing_fchmod)
            with patch.object(serialization_module, "os", proxy):
                with self.assertRaises(OSError) as caught:
                    write_world(path, sample_world())

            self.assertIn("fchmod is not permitted here", str(caught.exception))
            self.assertEqual(path.read_bytes(), b"previous contents")
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

            # The descriptor was opened before the failure, so the writer owes
            # us a close: the fd must be dead by the time the error surfaces.
            self.assertEqual(len(opened), 1)
            with self.assertRaises(OSError) as leaked:
                os.fstat(opened[0])
            self.assertEqual(leaked.exception.errno, errno.EBADF)

    def test_a_failure_before_replace_leaves_no_temporary_behind(self) -> None:
        def failing_fsync(descriptor: int) -> None:
            raise OSError(5, "simulated I/O error")

        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            path.write_bytes(b"previous contents")

            proxy = _ModuleProxy(os, fsync=failing_fsync)
            with patch.object(serialization_module, "os", proxy):
                with self.assertRaises(OSError) as caught:
                    write_world(path, sample_world())

            self.assertIn("simulated I/O error", str(caught.exception))
            self.assertEqual(path.read_bytes(), b"previous contents")
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])

    def test_mode_is_preserved_on_hosts_without_fchmod(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            path.write_bytes(b"previous contents")
            path.chmod(0o604)

            proxy = _ModuleProxy(os, fchmod=_ABSENT)
            self.assertFalse(hasattr(proxy, "fchmod"))
            with patch.object(serialization_module, "os", proxy):
                write_world(path, sample_world())

            self.assertEqual(read_world(path), sample_world())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o604)
            self.assertEqual(list(path.parent.glob(f".{path.name}.*.tmp")), [])


class WorldFormatSelectionTests(TestCase):
    def test_every_binary_format_alias_writes_the_same_container(self) -> None:
        world = sample_world()
        with TemporaryDirectory() as directory:
            root = Path(directory)
            written: dict[str, bytes] = {}
            for alias in ("mgeo", "msgpack", "binary"):
                path = root / f"{alias}.dat"
                write_world(path, world, format=alias)
                written[alias] = path.read_bytes()
                self.assertEqual(written[alias][:8], MGEO_MAGIC)
                self.assertEqual(read_world(path), world)

            json_path = root / "explicit.json"
            write_world(json_path, world, format="json")
            json_bytes = json_path.read_bytes()

            # ``format="json"`` must not produce a container, whatever the
            # suffix says, and must still round-trip.
            self.assertNotEqual(json_bytes[: len(MGEO_MAGIC)], MGEO_MAGIC)
            self.assertEqual(json_bytes[:1], b"{")
            self.assertEqual(read_world(json_path), world)
            self.assertNotIn(json_bytes, set(written.values()))

        self.assertEqual(len(set(written.values())), 1)
        self.assertEqual(written["mgeo"], dumps_world(world))

    def test_model_validation_can_be_skipped_on_both_json_facades(self) -> None:
        # 2**64 is one past MessagePack's unsigned range but perfectly ordinary
        # JSON, so it survives both writers once the value model is switched off.
        world = {"schema_version": 1, "bad": 2**64}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"

            with self.assertRaisesRegex(WorldSerializationError, "64-bit range"):
                write_world(path, world, format="json")
            self.assertFalse(path.exists())

            write_world(path, world, format="json", validate_model=False)
            self.assertIn(b"18446744073709551616", path.read_bytes())
            with self.assertRaisesRegex(WorldSerializationError, "64-bit range"):
                read_world(path, format="json")
            decoded = read_world(path, format="json", validate_model=False)

        self.assertEqual(decoded, world)

    def test_an_unknown_format_is_rejected_by_every_facade(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "world.mgeo"
            write_world(path, sample_world())

            for alias in ("MGEO", "yaml", "cbor", "", "auto "):
                with self.subTest(format=alias):
                    with self.assertRaises(ValueError) as caught:
                        read_world(path, format=alias)  # type: ignore[arg-type]
                    self.assertIs(type(caught.exception), ValueError)
                    self.assertEqual(
                        str(caught.exception),
                        "world format must be auto, json, or mgeo",
                    )
                    with self.assertRaises(ValueError) as written:
                        write_world(
                            path,
                            sample_world(),
                            format=alias,  # type: ignore[arg-type]
                        )
                    self.assertIs(type(written.exception), ValueError)
                    self.assertEqual(
                        str(written.exception),
                        "world format must be auto, json, or mgeo",
                    )


class MgeoPayloadDecodeTests(TestCase):
    @staticmethod
    def _container(packed: bytes, world_schema: int = 1) -> bytes:
        return (
            MGEO_HEADER.pack(
                MGEO_MAGIC,
                serialization_module.MGEO_VERSION_MAJOR,
                serialization_module.MGEO_VERSION_MINOR,
                serialization_module.MGEO_CODEC_MESSAGEPACK,
                serialization_module.MGEO_FLAGS_NONE,
                MGEO_HEADER_SIZE,
                len(packed),
                zlib.crc32(packed),
                world_schema,
            )
            + packed
        )

    def test_a_well_formed_container_round_trips(self) -> None:
        packed = msgpack.packb({"schema_version": 1, "ok": True}, use_bin_type=True)

        self.assertEqual(
            loads_world(self._container(packed)),
            {"schema_version": 1, "ok": True},
        )

    def test_malformed_payloads_are_wrapped_with_their_cause(self) -> None:
        # As on the native side, the wrapper text is shared, so each case pins
        # the msgpack rejection that produced it.
        cases = {
            "never_used_byte": (b"\xc1", msgpack.FormatError, ""),
            "truncated_map": (b"\x81\xa1", ValueError, "incomplete input"),
            "trailing_extra_object": (
                msgpack.packb({"schema_version": 1}) + msgpack.packb(1),
                msgpack.ExtraData,
                "extra data",
            ),
            "integer_map_key": (
                msgpack.packb({1: "a"}),
                ValueError,
                "int is not allowed for map key when strict_map_key=True",
            ),
            "invalid_utf8_string": (
                b"\x81\xa1a\xa2\xff\xfe",
                UnicodeDecodeError,
                "'utf-8' codec can't decode byte 0xff",
            ),
        }
        for label, (packed, cause_type, cause_fragment) in cases.items():
            with self.subTest(malformed=label):
                with self.assertRaises(WorldSerializationError) as caught:
                    loads_world(self._container(packed))
                cause = caught.exception.__cause__
                self.assertIsInstance(cause, cause_type)
                self.assertIn(cause_fragment, str(cause))
                self.assertEqual(
                    str(caught.exception),
                    f"invalid MessagePack world payload: {cause}",
                )

    def test_a_missing_or_mistyped_schema_version_mismatches_the_header(self) -> None:
        for label, payload in {
            "absent": {"name": "no schema"},
            "float": {"schema_version": 1.0},
            "boolean": {"schema_version": True},
            "string": {"schema_version": "1"},
        }.items():
            with self.subTest(schema_version=label):
                packed = msgpack.packb(payload, use_bin_type=True)
                with self.assertRaises(WorldSerializationError) as caught:
                    loads_world(self._container(packed))
                self.assertEqual(
                    str(caught.exception),
                    ".mgeo world schema does not match its container header",
                )

    def test_model_validation_can_be_skipped_on_decode(self) -> None:
        packed = msgpack.packb(
            {"schema_version": 1, "bad": math.nan},
            use_bin_type=True,
        )
        container = self._container(packed)

        with self.assertRaisesRegex(WorldSerializationError, "non-finite"):
            loads_world(container)

        decoded = loads_world(container, validate_model=False)
        self.assertTrue(math.isnan(decoded["bad"]))
