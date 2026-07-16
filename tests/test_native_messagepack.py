from __future__ import annotations

import json
import struct
from copy import deepcopy
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from magic_geo import native as native_module
from magic_geo.config import config_to_native, load_config
from magic_geo.native import generate_geo_world, generate_world
from magic_geo.planet_parameters import planet_parameter_snapshot


class NativeMessagePackTests(TestCase):
    def test_native_messagepack_matches_the_preserved_json_boundary(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        data = config.model_dump(mode="python")
        data["run"]["name"] = "binary \"world\"\n🌍\u0001"
        data["planet"]["radius_km"] = 6200.123456789
        data["planet"]["gravity_g"] = 0.987654321
        data["mesh"]["cell_count"] = 128
        data["tectonics"]["plate_count"] = 8
        data["erosion"]["iterations"] = 0
        data["output"]["include_cells"] = True
        configured = type(config).model_validate(data)
        native = config_to_native(configured)

        json_world = generate_world(native, serialization="json")
        msgpack_world = generate_world(native, serialization="msgpack")
        json_geo_world = generate_geo_world(native, serialization="json")
        msgpack_geo_world = generate_geo_world(native, serialization="msgpack")

        self.assertEqual(msgpack_world, json_world)
        self.assertEqual(msgpack_geo_world, json_geo_world)
        expected_planet = planet_parameter_snapshot(configured.planet)
        self.assertEqual(json_world["planet_parameters"], expected_planet)
        self.assertEqual(json_geo_world["planet_parameters"], expected_planet)
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

    def test_generation_rejects_a_symbol_complete_stale_world_schema(self) -> None:
        config = load_config(Path("configs/earthlike_seed.yaml"))
        native = config_to_native(config)

        class StaleLibrary:
            @staticmethod
            def magic_geo_generate_json_v3(*_args: object) -> int:
                return 1

            magic_geo_generate_geo_json_v3 = magic_geo_generate_json_v3
            magic_geo_generate_msgpack_v3 = magic_geo_generate_json_v3
            magic_geo_generate_geo_msgpack_v3 = magic_geo_generate_json_v3

        stale_payload = {"schema_version": 1}
        with (
            patch.object(native_module, "_load_library", return_value=StaleLibrary()),
            patch.object(
                native_module,
                "_consume_json_pointer",
                return_value=stale_payload,
            ),
            patch.object(
                native_module,
                "_consume_msgpack_pointer",
                return_value=stale_payload,
            ),
        ):
            for generator in (generate_world, generate_geo_world):
                for serialization in ("json", "msgpack"):
                    with self.subTest(
                        generator=generator.__name__,
                        serialization=serialization,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "unsupported world schema_version 1; expected 2",
                        ):
                            generator(native, serialization=serialization)

        for stale_payload in ({"schema_version": 2.0}, {"schema_version": True}, {}):
            with self.subTest(stale_payload=stale_payload):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "unsupported world schema_version",
                ):
                    native_module._require_current_world_schema(stale_payload)

        with self.assertRaisesRegex(
            RuntimeError,
            "retired fields",
        ):
            native_module._require_current_world_schema(
                {
                    "schema_version": 2,
                    "plate_kinematic_model": {
                        "accelerator_crust_source_remap_kernel_used": False,
                    },
                }
            )
        with self.assertRaisesRegex(
            RuntimeError,
            "without explicit planet_parameters",
        ):
            native_module._require_current_world_schema({"schema_version": 2})

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
