"""Error and option coverage for the `generate`, `render` and `render-raster` commands.

Everything here drives the public Typer application through ``CliRunner`` so the
tests keep working while the command package is reorganised: only exit codes and
printed text are asserted, never a private module path.
"""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

import yaml
from typer.testing import CliRunner

from magic_geo.cli import app
from magic_geo.io import write_world

from support import worlds
from support.nativestub import patch_generation_payload

from support.cli import assert_no_cli_crash


def flat(output: str) -> str:
    """Flatten Rich's boxed, terminal-width-wrapped error text for substring asserts."""
    return " ".join(output.replace("│", " ").split())


def ppm_geometry(data: bytes) -> tuple[str, int, int, int, int]:
    """Split a binary PPM into (magic, width, height, maxval, pixel byte count).

    The canvas size is read back out of the file itself rather than trusted from
    the requested options, so a render that ignores ``--width``/``--height``
    cannot pass.
    """
    magic, _comment, dimensions, maxval, pixels = data.split(b"\n", 4)
    width, height = (int(part) for part in dimensions.split())
    return magic.decode("ascii"), width, height, int(maxval), len(pixels)


class StaleNativeLibrary:
    """A V4 library whose current-default generation payload is a stale schema."""

    @staticmethod
    def magic_geo_generate_json_v4(*_args: object) -> int:
        return 1

    magic_geo_generate_geo_json_v4 = magic_geo_generate_json_v4
    magic_geo_generate_msgpack_v4 = magic_geo_generate_json_v4
    magic_geo_generate_geo_msgpack_v4 = magic_geo_generate_json_v4


class GenerateCliTests(TestCase):
    def _smoke_config(self, directory: Path, *overrides: str, name: str = "smoke.yaml") -> Path:
        """Write a 128-cell config with the CLI's own ``init-config`` command."""
        path = directory / name
        args = ["init-config", "--profile", "smoke", "--output", str(path)]
        for override in overrides:
            args += ["--set", override]
        result = CliRunner().invoke(app, args)
        self.assertEqual(result.exit_code, 0, result.output)
        return path

    def test_generate_rejects_unusable_config_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            valid = self._smoke_config(root)

            malformed = root / "malformed.yaml"
            malformed.write_text("run: [\n", encoding="utf-8")

            out_of_range = root / "out_of_range.yaml"
            data = yaml.safe_load(valid.read_text(encoding="utf-8"))
            data["mesh"]["cell_count"] = 4
            out_of_range.write_text(yaml.safe_dump(data), encoding="utf-8")

            cases = (
                ("missing", root / "absent.yaml", "does not exist"),
                ("directory", root, "Is a directory"),
                ("malformed_yaml", malformed, "invalid YAML"),
                (
                    "out_of_range",
                    out_of_range,
                    "mesh.cell_count: Input should be greater than or equal to 128",
                ),
            )
            for name, config, expected in cases:
                with self.subTest(config=name):
                    output = root / f"{name}.json"
                    result = CliRunner().invoke(
                        app,
                        ["generate", "--config", str(config), "--output", str(output)],
                    )

                    self.assertEqual(result.exit_code, 2, result.output)
                    self.assertIn(expected, flat(result.output))
                    assert_no_cli_crash(self, result)
                    self.assertFalse(output.exists())

    def test_generate_rejects_unknown_format_and_out_of_range_cells(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._smoke_config(root)

            cases = (
                ("xml", ["--format", "xml"], "--format must be auto, json, or mgeo"),
                ("uppercase", ["--format", "JSON"], "--format must be auto, json, or mgeo"),
                ("empty", ["--format", ""], "--format must be auto, json, or mgeo"),
                ("cells_below_minimum", ["--cells", "64"], "64 is not in the range x>=128"),
            )
            for name, extra, expected in cases:
                with self.subTest(case=name):
                    output = root / f"{name}.json"
                    result = CliRunner().invoke(
                        app,
                        [
                            "generate",
                            "--config",
                            str(config),
                            "--output",
                            str(output),
                            *extra,
                        ],
                    )

                    self.assertEqual(result.exit_code, 2, result.output)
                    self.assertIn(expected, flat(result.output))
                    assert_no_cli_crash(self, result)
                    self.assertFalse(output.exists())

    def test_generate_cell_override_revalidates_the_whole_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._smoke_config(
                root,
                "mesh.cell_count=512",
                "tectonics.plate_count=200",
            )

            rejected = root / "rejected.json"
            failure = CliRunner().invoke(
                app,
                [
                    "generate",
                    "--config",
                    str(config),
                    "--output",
                    str(rejected),
                    "--cells",
                    "128",
                ],
            )
            self.assertEqual(failure.exit_code, 2, failure.output)
            self.assertIn(
                "plate_count must be smaller than mesh.cell_count",
                flat(failure.output),
            )
            assert_no_cli_crash(self, failure)
            self.assertFalse(rejected.exists())

            accepted = root / "accepted.json"
            result = CliRunner().invoke(
                app,
                [
                    "generate",
                    "--config",
                    str(self._smoke_config(root, name="plain.yaml")),
                    "--output",
                    str(accepted),
                    "--cells",
                    "256",
                ],
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("cells=256", result.output)
            self.assertIn("scope=full_world", result.output)
            self.assertEqual(len(json.loads(accepted.read_text(encoding="utf-8"))["cells"]), 256)

    def test_generate_selects_the_serialization_from_suffix_then_flag(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._smoke_config(root)

            cases = (
                ("json_suffix", "world.json", [], b"{"),
                ("mgeo_suffix", "world.mgeo", [], b"MGEO"),
                ("unknown_suffix", "world.dat", [], b"{"),
                ("flag_overrides_json_suffix", "binary.json", ["--format", "mgeo"], b"MGEO"),
                ("flag_overrides_mgeo_suffix", "text.mgeo", ["--format", "json"], b"{"),
            )
            for name, filename, extra, expected_prefix in cases:
                with self.subTest(case=name):
                    output = root / filename
                    result = CliRunner().invoke(
                        app,
                        [
                            "generate",
                            "--config",
                            str(config),
                            "--output",
                            str(output),
                            *extra,
                        ],
                    )

                    self.assertEqual(result.exit_code, 0, result.output)
                    self.assertIn(f"Wrote {output} | scope=full_world cells=128", result.output)
                    self.assertEqual(
                        output.read_bytes()[: len(expected_prefix)],
                        expected_prefix,
                    )

    def test_generate_creates_missing_parent_directories_for_every_output(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._smoke_config(root)
            world = root / "deep" / "nested" / "world.json"
            summary = root / "reports" / "summary.md"
            cells_csv = root / "tables" / "cells.csv"

            result = CliRunner().invoke(
                app,
                [
                    "generate",
                    "--config",
                    str(config),
                    "--output",
                    str(world),
                    "--summary",
                    str(summary),
                    "--cells-csv",
                    str(cells_csv),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn(f"Wrote {world} | scope=full_world cells=128", result.output)
            world_payload = json.loads(world.read_text(encoding="utf-8"))
            self.assertEqual(len(world_payload["cells"]), 128)

            summary_text = summary.read_text(encoding="utf-8")
            self.assertTrue(summary_text.startswith("# "), summary_text[:80])
            self.assertIn("## Summary", summary_text)
            # The sidecar must describe the world that was just generated.
            self.assertIn("- `cell_count`: 128", summary_text)

            csv_lines = cells_csv.read_text(encoding="utf-8").splitlines()
            self.assertTrue(csv_lines[0].startswith("id,lat_deg,lon_deg,"))
            self.assertEqual(len(csv_lines), 129)
            self.assertEqual(
                [row.split(",", 1)[0] for row in csv_lines[1:]],
                [str(index) for index in range(128)],
            )

    def test_generate_geo_only_omits_the_civilization_layers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._smoke_config(root)
            output = root / "geo.json"

            result = CliRunner().invoke(
                app,
                [
                    "generate",
                    "--config",
                    str(config),
                    "--output",
                    str(output),
                    "--geo-only",
                ],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn(f"Wrote {output} | scope=geo_only cells=128", result.output)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["cells"]), 128)
            for omitted in ("settlements", "cultures", "historical_events"):
                with self.subTest(layer=omitted):
                    self.assertNotIn(omitted, payload)

    def test_generate_reports_a_native_generation_failure_without_a_traceback(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = self._smoke_config(root)

            for name, extra in (("full_world", []), ("geo_only", ["--geo-only"])):
                with self.subTest(scope=name):
                    output = root / f"{name}.json"
                    with patch_generation_payload(
                        StaleNativeLibrary(),
                        {"schema_version": 1},
                        model="seasonal",
                    ):
                        result = CliRunner().invoke(
                            app,
                            [
                                "generate",
                                "--config",
                                str(config),
                                "--output",
                                str(output),
                                *extra,
                            ],
                        )

                    self.assertEqual(result.exit_code, 2, result.output)
                    self.assertIn(
                        "unsupported world schema_version 1; expected 2",
                        flat(result.output),
                    )
                    assert_no_cli_crash(self, result)
                    self.assertFalse(output.exists())


class RenderCliTests(TestCase):
    """`render` and `render-raster` over the shared 256-cell smoke world."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._world_dir = TemporaryDirectory()
        root = Path(cls._world_dir.name)
        world = worlds.cached_world_readonly("small_smoke")
        cls.cell_count = len(world["cells"])
        cls.world_json = root / "world.json"
        cls.world_mgeo = root / "world.mgeo"
        write_world(cls.world_json, world, validate_model=False)
        write_world(cls.world_mgeo, world, validate_model=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._world_dir.cleanup()

    def test_render_commands_reject_missing_and_corrupt_world_files(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            empty = root / "empty.json"
            empty.write_bytes(b"")
            garbage = root / "garbage.json"
            garbage.write_text("this is not a world", encoding="utf-8")
            truncated = root / "truncated.mgeo"
            truncated.write_bytes(b"MGEO\r\n\x1a\n" + b"\x00" * 16)
            not_an_object = root / "list.json"
            not_an_object.write_text("[1, 2, 3]", encoding="utf-8")

            cases = (
                ("missing", root / "absent.json", "does not exist"),
                ("empty", empty, "Invalid world file: Expecting value"),
                ("garbage", garbage, "Invalid world file: Expecting value"),
                ("truncated_mgeo", truncated, "Invalid world file: truncated .mgeo header"),
                (
                    "json_array",
                    not_an_object,
                    "Invalid world file: decoded world root must be an object",
                ),
            )
            for command, suffix in (("render", "svg"), ("render-raster", "ppm")):
                for name, world, expected in cases:
                    with self.subTest(command=command, world=name):
                        output = root / f"{command}-{name}.{suffix}"
                        result = CliRunner().invoke(
                            app,
                            [command, "--world", str(world), "--output", str(output)],
                        )

                        self.assertEqual(result.exit_code, 2, result.output)
                        self.assertIn(expected, flat(result.output))
                        assert_no_cli_crash(self, result)
                        self.assertFalse(output.exists())

    def test_render_reads_both_world_serializations(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for command, suffix in (("render", "svg"), ("render-raster", "ppm")):
                for name, world in (("json", self.world_json), ("mgeo", self.world_mgeo)):
                    with self.subTest(command=command, serialization=name):
                        output = root / f"{command}-{name}.{suffix}"
                        result = CliRunner().invoke(
                            app,
                            [
                                command,
                                "--world",
                                str(world),
                                "--output",
                                str(output),
                                "--width",
                                "320",
                                "--height",
                                "160",
                            ],
                        )

                        self.assertEqual(result.exit_code, 0, result.output)
                        self.assertEqual(result.output.strip(), f"Wrote {output}")
                        if command == "render":
                            svg = output.read_text(encoding="utf-8")
                            self.assertIn('width="320" height="160"', svg)
                            self.assertTrue(svg.rstrip().endswith("</svg>"), svg[-80:])
                            self.assertEqual(
                                svg.count('class="terrain-cell"'), self.cell_count
                            )
                        else:
                            self.assertEqual(
                                ppm_geometry(output.read_bytes()),
                                ("P6", 320, 160, 255, 320 * 160 * 3),
                            )

    def test_render_supports_every_svg_projection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for requested, expected in (
                ("equirectangular", "equirectangular"),
                ("mollweide", "mollweide"),
                ("orthographic", "orthographic"),
                ("Mollweide", "mollweide"),
            ):
                with self.subTest(projection=requested):
                    output = root / f"{requested}.svg"
                    result = CliRunner().invoke(
                        app,
                        [
                            "render",
                            "--world",
                            str(self.world_mgeo),
                            "--output",
                            str(output),
                            "--projection",
                            requested,
                            "--width",
                            "640",
                            "--height",
                            "320",
                        ],
                    )

                    self.assertEqual(result.exit_code, 0, result.output)
                    self.assertEqual(result.output.strip(), f"Wrote {output}")
                    svg = output.read_text(encoding="utf-8")
                    self.assertIn(f'data-projection="{expected}"', svg)
                    self.assertIn('width="640" height="320"', svg)

    def test_render_commands_reject_an_unknown_projection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            for command, suffix in (("render", "svg"), ("render-raster", "ppm")):
                with self.subTest(command=command):
                    output = root / f"{command}.{suffix}"
                    result = CliRunner().invoke(
                        app,
                        [
                            command,
                            "--world",
                            str(self.world_mgeo),
                            "--output",
                            str(output),
                            "--projection",
                            "sinusoidal",
                        ],
                    )

                    self.assertEqual(result.exit_code, 2, result.output)
                    self.assertIn("unknown projection: sinusoidal", flat(result.output))
                    assert_no_cli_crash(self, result)
                    self.assertFalse(output.exists())

    def test_render_label_and_contour_toggles_change_the_svg_layers(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def render(name: str, *extra: str) -> str:
                output = root / f"{name}.svg"
                result = CliRunner().invoke(
                    app,
                    [
                        "render",
                        "--world",
                        str(self.world_mgeo),
                        "--output",
                        str(output),
                        "--width",
                        "640",
                        "--height",
                        "320",
                        *extra,
                    ],
                )
                self.assertEqual(result.exit_code, 0, result.output)
                return output.read_text(encoding="utf-8")

            default_svg = render("default")
            self.assertIn('data-contours="true"', default_svg)
            self.assertIn("terrain-contours", default_svg)
            self.assertNotIn("<text x=", default_svg)

            plain_svg = render("plain", "--no-contours", "--no-labels")
            self.assertIn('data-contours="false"', plain_svg)
            self.assertNotIn("terrain-contours", plain_svg)
            self.assertNotIn("<text x=", plain_svg)

            labelled_svg = render("labelled", "--labels")
            self.assertIn("<text x=", labelled_svg)

            wide_svg = render("wide", "--contour-interval", "1200")
            self.assertIn('data-contour-interval-m="1200"', wide_svg)

            narrow = root / "narrow.svg"
            rejected = CliRunner().invoke(
                app,
                [
                    "render",
                    "--world",
                    str(self.world_mgeo),
                    "--output",
                    str(narrow),
                    "--contour-interval",
                    "40",
                ],
            )
            self.assertEqual(rejected.exit_code, 2, rejected.output)
            self.assertIn("40.0 is not in the range x>=50.0", flat(rejected.output))
            self.assertFalse(narrow.exists())

    def test_render_max_cells_downsamples_the_svg_cell_layer(self) -> None:
        self.assertEqual(self.cell_count, 256)
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def cells_rendered(name: str, *extra: str) -> int:
                output = root / f"{name}.svg"
                result = CliRunner().invoke(
                    app,
                    [
                        "render",
                        "--world",
                        str(self.world_mgeo),
                        "--output",
                        str(output),
                        "--width",
                        "640",
                        "--height",
                        "320",
                        *extra,
                    ],
                )
                self.assertEqual(result.exit_code, 0, result.output)
                return output.read_text(encoding="utf-8").count('class="terrain-cell"')

            self.assertEqual(cells_rendered("full"), 256)
            self.assertEqual(cells_rendered("half", "--max-cells", "128"), 128)
            self.assertEqual(cells_rendered("above", "--max-cells", "1024"), 256)

            output = root / "tiny.svg"
            rejected = CliRunner().invoke(
                app,
                [
                    "render",
                    "--world",
                    str(self.world_mgeo),
                    "--output",
                    str(output),
                    "--max-cells",
                    "10",
                ],
            )
            self.assertEqual(rejected.exit_code, 2, rejected.output)
            self.assertIn("10 is not in the range x>=128", flat(rejected.output))
            self.assertFalse(output.exists())

    def test_render_raster_records_projection_and_texture_in_the_ppm_header(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            def raster(name: str, *extra: str) -> bytes:
                output = root / f"{name}.ppm"
                result = CliRunner().invoke(
                    app,
                    [
                        "render-raster",
                        "--world",
                        str(self.world_mgeo),
                        "--output",
                        str(output),
                        "--width",
                        "320",
                        "--height",
                        "160",
                        *extra,
                    ],
                )
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(result.output.strip(), f"Wrote {output}")
                data = output.read_bytes()
                # The requested canvas has to survive into the file itself.
                self.assertEqual(
                    ppm_geometry(data),
                    ("P6", 320, 160, 255, 320 * 160 * 3),
                )
                return data

            for projection in ("equirectangular", "mollweide", "orthographic"):
                with self.subTest(projection=projection):
                    data = raster(projection, "--projection", projection)
                    self.assertTrue(data.startswith(b"P6\n# magic-geo raster-terrain-v1 "))
                    self.assertIn(
                        f"projection={projection} texture=true".encode(),
                        data[:120],
                    )

            untextured = raster("untextured", "--no-texture")
            self.assertIn(b"texture=false", untextured[:120])

            full = raster("full")
            downsampled = raster("downsampled", "--max-cells", "128")
            self.assertEqual(len(full), len(downsampled))
            self.assertNotEqual(full, downsampled)

    def test_render_commands_reject_out_of_range_canvas_and_cell_limits(self) -> None:
        """Both commands declare the same numeric bounds; both must enforce them."""
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cases = (
                ("narrow", ["--width", "100"], "100 is not in the range 320<=x<=6400"),
                ("wide", ["--width", "9000"], "9000 is not in the range 320<=x<=6400"),
                ("short", ["--height", "80"], "80 is not in the range 160<=x<=3200"),
                ("tall", ["--height", "5000"], "5000 is not in the range 160<=x<=3200"),
                ("few_cells", ["--max-cells", "10"], "10 is not in the range x>=128"),
            )
            for command, suffix in (("render", "svg"), ("render-raster", "ppm")):
                for name, extra, expected in cases:
                    with self.subTest(command=command, case=name):
                        output = root / f"{command}-{name}.{suffix}"
                        result = CliRunner().invoke(
                            app,
                            [
                                command,
                                "--world",
                                str(self.world_mgeo),
                                "--output",
                                str(output),
                                *extra,
                            ],
                        )

                        self.assertEqual(result.exit_code, 2, result.output)
                        self.assertIn(expected, flat(result.output))
                        assert_no_cli_crash(self, result)
                        self.assertFalse(output.exists())
