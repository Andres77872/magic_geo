from __future__ import annotations

import ctypes
import json
import struct
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from magic_geo import native as native_module
from magic_geo.config import config_to_native, load_config
from magic_geo.native import generate_geo_world, generate_world


class NativeMessagePackTests(TestCase):
    def test_native_messagepack_matches_the_preserved_json_boundary(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["run"]["name"] = "binary \"world\"\n🌍\u0001"
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        data["output"]["include_cells"] = True
        native = config_to_native(type(config).model_validate(data))

        json_world = generate_world(native, serialization="json")
        msgpack_world = generate_world(native, serialization="msgpack")
        json_geo_world = generate_geo_world(native, serialization="json")
        msgpack_geo_world = generate_geo_world(native, serialization="msgpack")

        self.assertEqual(msgpack_world, json_world)
        self.assertEqual(msgpack_geo_world, json_geo_world)
        self.assertEqual(msgpack_world["name"], data["run"]["name"])
        self.assertEqual(
            json.dumps(msgpack_world, sort_keys=True, separators=(",", ":")),
            json.dumps(json_world, sort_keys=True, separators=(",", ":")),
        )
        for msgpack_cell, json_cell in zip(
            msgpack_world["cells"],
            json_world["cells"],
            strict=True,
        ):
            for key in ("crust_age_ma", "crust_thickness_km", "crust_density"):
                self.assertEqual(
                    struct.pack(">d", msgpack_cell[key]),
                    struct.pack(">d", json_cell[key]),
                )

        invalid = deepcopy(native)
        invalid["mesh"]["cell_count"] = 64
        for serialization in ("json", "msgpack", "auto"):
            with self.subTest(error_serialization=serialization):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "cell_count must be between 128 and 200000",
                ):
                    generate_world(invalid, serialization=serialization)

        with self.assertRaisesRegex(ValueError, "auto, json, or msgpack"):
            generate_world(native, serialization="unknown")

    def test_auto_mode_falls_back_to_json_for_current_older_library(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        native = config_to_native(config)
        raw = ctypes.create_string_buffer(
            b'{"schema_version":1,"source":"json fallback"}'
        )

        class JsonOnlyLibrary:
            @staticmethod
            def magic_geo_generate_json_v3(_config: object) -> int:
                return ctypes.addressof(raw)

            @staticmethod
            def magic_geo_free_string(_pointer: object) -> None:
                return None

        with patch.object(
            native_module,
            "_load_library",
            return_value=JsonOnlyLibrary(),
        ):
            self.assertEqual(
                generate_world(native),
                {"schema_version": 1, "source": "json fallback"},
            )
            with self.assertRaisesRegex(RuntimeError, "does not support MessagePack"):
                generate_world(native, serialization="msgpack")

    def test_native_library_probe_prefers_the_host_format(self) -> None:
        expected = {
            "linux": "libmagic_geo_native.so",
            "darwin": "libmagic_geo_native.dylib",
            "win32": "magic_geo_native.dll",
        }
        for platform, filename in expected.items():
            with self.subTest(platform=platform), patch.object(
                native_module.sys,
                "platform",
                platform,
            ):
                names = native_module._native_library_names()
                self.assertEqual(names[0], filename)
                self.assertEqual(names, (filename,))
