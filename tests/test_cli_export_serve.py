"""CLI surface of ``export-debug``, ``export-debug-map``, ``export-rerun`` and ``serve``.

Everything here goes through :class:`typer.testing.CliRunner` against
``magic_geo.cli.app``; the commands' bodies are never imported directly. The
optional-dependency branches are reached by poisoning the *import site* in
``sys.modules`` (``None`` makes ``import`` raise :class:`ImportError`) rather
than by uninstalling anything, and ``serve`` never binds a port -- ``uvicorn``
and ``magic_geo.debug_server`` are replaced by stub modules whose recorded call
arguments are the assertion.

``tests/test_debug_cli.py`` already covers ``--help`` shapes, the happy ``serve``
starts and ``export-debug-map --no-image --no-prompt``; those are not repeated.
"""

from __future__ import annotations

import hashlib
import json
import struct
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import SkipTest, TestCase
from unittest.mock import Mock, patch
import sys

from typer.testing import CliRunner

from support import worlds

from magic_geo.cli import app
from magic_geo.io import write_json

from support.cli import assert_no_cli_crash

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

#: Rich draws Typer's parameter errors inside a box and hard-wraps the text, so
#: those messages are only matchable after the frame and line breaks are removed.
_BOX_CHARACTERS = frozenset("╭╮╯╰│─")


def _unboxed(output: str) -> str:
    """``output`` with Rich's panel frame dropped and whitespace collapsed."""
    without_frame = "".join(
        " " if character in _BOX_CHARACTERS else character for character in output
    )
    return " ".join(without_frame.split())


def _png_size(data: bytes) -> tuple[int, int]:
    """``(width, height)`` decoded from a PNG's leading IHDR chunk."""
    if data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise AssertionError("payload is not a PNG whose first chunk is IHDR")
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def _write_world(root: Path, *, name: str = "world.json", cells: bool = True) -> Path:
    """Write the 128-cell replay world (optionally stripped of cells) to ``root``."""
    payload = worlds.cached_world_readonly("replay_128")
    if not cells:
        # Shallow copy: the shared cached world must never be mutated.
        payload = dict(payload)
        payload["cells"] = []
    path = root / name
    write_json(path, payload)
    return path


def _fake_server_modules(create_app: Mock) -> dict[str, ModuleType]:
    """Stub ``uvicorn``/``magic_geo.debug_server`` so ``serve`` never binds a port."""
    uvicorn_module = ModuleType("uvicorn")
    uvicorn_module.run = Mock()
    debug_server_module = ModuleType("magic_geo.debug_server")
    debug_server_module.create_app = create_app
    return {"uvicorn": uvicorn_module, "magic_geo.debug_server": debug_server_module}


class ExportDebugCommandTests(TestCase):
    """``export-debug``: world loading, the VTU toggle and both failure exits."""

    world_dir: TemporaryDirectory
    world: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.world_dir = TemporaryDirectory()
        cls.world = _write_world(Path(cls.world_dir.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls.world_dir.cleanup()

    def test_rejects_a_world_path_that_does_not_exist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "absent.json"
            result = CliRunner().invoke(app, ["export-debug", "--world", str(missing)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(
            f"Invalid value for '--world' / '-w': Path '{missing}' does not exist.",
            _unboxed(result.output),
        )
        assert_no_cli_crash(self, result)

    def test_reports_a_friendly_message_when_the_debug_extra_is_unavailable(self) -> None:
        with patch.dict(sys.modules, {"magic_geo.debug_export": None}):
            result = CliRunner().invoke(app, ["export-debug", "--world", str(self.world)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Debug export requires the optional debug dependencies", result.output)
        self.assertIn("pip install 'magic-geo[debug]'", result.output)
        assert_no_cli_crash(self, result)

    def test_no_vtu_writes_the_cache_into_an_already_populated_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            out_dir = Path(temp_dir) / "cache"
            out_dir.mkdir()
            (out_dir / "manifest.json").write_text("{stale}", encoding="utf-8")
            (out_dir / "leftover.txt").write_text("from an older run", encoding="utf-8")

            result = CliRunner().invoke(
                app,
                [
                    "export-debug",
                    "--world",
                    str(self.world),
                    "--output",
                    str(out_dir),
                    "--no-vtu",
                ],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            mesh = manifest["mesh"]
            self.assertEqual(manifest["world"]["cell_count"], 128)
            # --world is recorded verbatim: path, size and digest of the file on disk.
            world_bytes = self.world.read_bytes()
            self.assertEqual(
                manifest["source"],
                {
                    "path": str(self.world),
                    "bytes": len(world_bytes),
                    "sha256": hashlib.sha256(world_bytes).hexdigest(),
                },
            )
            self.assertIn(
                f"Wrote {out_dir} | layers={len(manifest['layers'])} "
                f"stage_histories={len(manifest['stage_histories'])} "
                f"families={len(manifest['families'])} "
                f"mesh_vertices={mesh['vertex_count']} mesh_triangles={mesh['triangle_count']}",
                result.output,
            )
            # --no-vtu suppresses the ParaView side-car entirely.
            self.assertEqual(list(out_dir.rglob("*.vtu")), [])
            self.assertFalse((out_dir / "world.pvd").exists())
            # An already-populated directory is refreshed, not rejected.
            self.assertEqual(
                (out_dir / "leftover.txt").read_text(encoding="utf-8"), "from an older run"
            )

    def test_vtu_default_writes_paraview_stage_files_beside_the_world(self) -> None:
        with TemporaryDirectory() as temp_dir:
            world = _write_world(Path(temp_dir))

            result = CliRunner().invoke(
                app,
                [
                    "export-debug",
                    "--world",
                    str(world),
                    "--elevation-exaggeration",
                    "5.0",
                ],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            # No --output: the cache defaults to <world dir>/debug.
            out_dir = Path(temp_dir) / "debug"
            self.assertIn(f"Wrote {out_dir} | layers=", result.output)
            self.assertTrue((out_dir / "world.pvd").is_file())
            stage_files = sorted(path.name for path in out_dir.rglob("*.vtu"))
            self.assertIn("stage_0000.vtu", stage_files)
            manifest = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
            paraview = manifest["paraview"]
            # --elevation-exaggeration reaches the exporter instead of the 30.0 default.
            self.assertEqual(paraview["elevation_exaggeration"], 5.0)
            self.assertEqual(paraview["pvd"], "world.pvd")
            # One contiguously numbered .vtu per stage, each listed by the collection.
            self.assertEqual(
                stage_files,
                [f"stage_{index:04d}.vtu" for index in range(paraview["stage_count"])],
            )
            pvd = (out_dir / "world.pvd").read_text(encoding="utf-8")
            for index, name in enumerate(stage_files):
                self.assertIn(f'timestep="{index}" group="" part="0" file="vtu/{name}"', pvd)

    def test_rejects_a_world_payload_without_cells(self) -> None:
        with TemporaryDirectory() as temp_dir:
            world = _write_world(Path(temp_dir), name="empty.json", cells=False)

            result = CliRunner().invoke(app, ["export-debug", "--world", str(world)])

            self.assertEqual(result.exit_code, 2, result.output)
            self.assertIn(
                "world payload has no cells; generate with output.include_cells enabled",
                result.output,
            )
            assert_no_cli_crash(self, result)
            self.assertFalse((Path(temp_dir) / "debug").exists())


class ExportRerunCommandTests(TestCase):
    """``export-rerun``: the rerun-sdk guard, the default target and the stats line."""

    def test_rejects_a_world_path_that_does_not_exist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "absent.mgeo"
            result = CliRunner().invoke(app, ["export-rerun", "--world", str(missing)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(
            f"Invalid value for '--world' / '-w': Path '{missing}' does not exist.",
            _unboxed(result.output),
        )
        assert_no_cli_crash(self, result)

    def test_reports_a_friendly_message_when_rerun_sdk_is_absent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            world = _write_world(Path(temp_dir))
            with patch.dict(sys.modules, {"magic_geo.debug_rerun": None}):
                result = CliRunner().invoke(app, ["export-rerun", "--world", str(world)])

            self.assertEqual(result.exit_code, 2, result.output)
            self.assertIn("Rerun export requires the rerun-sdk package", result.output)
            self.assertIn("pip install rerun-sdk", result.output)
            assert_no_cli_crash(self, result)
            self.assertFalse((Path(temp_dir) / "world.rrd").exists())

    def test_writes_the_recording_next_to_the_world_and_reports_stats(self) -> None:
        stats = {
            "stages": 8,
            "vertices": 884,
            "feedback_scalars": 896,
            "plate_boundary_segments": 219,
        }
        recorder = Mock(return_value=stats)
        fake_module = ModuleType("magic_geo.debug_rerun")
        fake_module.export_rerun_recording = recorder

        with TemporaryDirectory() as temp_dir:
            world = _write_world(Path(temp_dir))
            with patch.dict(sys.modules, {"magic_geo.debug_rerun": fake_module}):
                result = CliRunner().invoke(app, ["export-rerun", "--world", str(world)])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(recorder.call_count, 1)
            payload, target = recorder.call_args.args
            # The default target sits beside the world file, not in the cwd.
            self.assertEqual(target, Path(temp_dir) / "world.rrd")
            self.assertEqual(len(payload["cells"]), 128)
            self.assertIn(
                f"Wrote {Path(temp_dir) / 'world.rrd'} | stages=8 vertices=884 "
                "feedback_scalars=896 plate_segments=219",
                result.output,
            )

    def test_honors_an_explicit_output_and_surfaces_export_failures(self) -> None:
        recorder = Mock(side_effect=ValueError("world payload has no cells"))
        fake_module = ModuleType("magic_geo.debug_rerun")
        fake_module.export_rerun_recording = recorder

        with TemporaryDirectory() as temp_dir:
            world = _write_world(Path(temp_dir))
            target = Path(temp_dir) / "nested" / "custom.rrd"
            with patch.dict(sys.modules, {"magic_geo.debug_rerun": fake_module}):
                result = CliRunner().invoke(
                    app,
                    ["export-rerun", "--world", str(world), "--output", str(target)],
                )

            self.assertEqual(result.exit_code, 2, result.output)
            self.assertEqual(recorder.call_args.args[1], target)
            self.assertIn("world payload has no cells", result.output)
            assert_no_cli_crash(self, result)


class ExportDebugMapCommandTests(TestCase):
    """``export-debug-map`` against a real cache built through ``export-debug``."""

    temp: TemporaryDirectory
    cache: Path

    @classmethod
    def setUpClass(cls) -> None:
        cls.temp = TemporaryDirectory()
        root = Path(cls.temp.name)
        world = _write_world(root)
        cls.cache = root / "cache"
        result = CliRunner().invoke(
            app,
            [
                "export-debug",
                "--world",
                str(world),
                "--output",
                str(cls.cache),
                "--no-vtu",
            ],
        )
        if result.exit_code != 0:
            cls.temp.cleanup()
            if "requires the optional debug dependencies" in result.output:  # pragma: no cover
                raise SkipTest("the [debug] extra is not installed")
            # Any other failure is a real regression, not a reason to skip.
            raise AssertionError(f"export-debug could not build the cache: {result.output}")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temp.cleanup()

    def test_rejects_a_debug_directory_that_does_not_exist(self) -> None:
        with TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "no-such-cache"
            result = CliRunner().invoke(
                app, ["export-debug-map", "--debug-dir", str(missing)]
            )

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(
            f"Invalid value for '--debug-dir' / '-d': Directory '{missing}' does not exist.",
            _unboxed(result.output),
        )
        assert_no_cli_crash(self, result)

    def test_reports_a_friendly_message_when_the_debug_extra_is_unavailable(self) -> None:
        with patch.dict(sys.modules, {"magic_geo.debug_map_export": None}):
            result = CliRunner().invoke(
                app, ["export-debug-map", "--debug-dir", str(self.cache)]
            )

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Debug map export requires the optional debug dependencies", result.output)
        self.assertIn("pip install 'magic-geo[debug]'", result.output)
        assert_no_cli_crash(self, result)

    def test_rejects_an_unknown_layer_id(self) -> None:
        with TemporaryDirectory() as temp_dir:
            result = CliRunner().invoke(
                app,
                [
                    "export-debug-map",
                    "--debug-dir",
                    str(self.cache),
                    "--layer",
                    "cells/not_a_real_layer",
                    "--output",
                    str(Path(temp_dir) / "map"),
                ],
            )

            self.assertEqual(result.exit_code, 2, result.output)
            self.assertIn("Unable to export debug map:", result.output)
            self.assertIn("unknown or unavailable layer 'cells/not_a_real_layer'", result.output)
            assert_no_cli_crash(self, result)
            self.assertEqual(sorted(Path(temp_dir).iterdir()), [])

    def test_rejects_an_unknown_projection(self) -> None:
        with TemporaryDirectory() as temp_dir:
            result = CliRunner().invoke(
                app,
                [
                    "export-debug-map",
                    "--debug-dir",
                    str(self.cache),
                    "--projection",
                    "gall-peters",
                    "--output",
                    str(Path(temp_dir) / "map"),
                ],
            )

            self.assertEqual(result.exit_code, 2, result.output)
            self.assertIn(
                "Unable to export debug map: projection must be globe, equirect, or mollweide",
                result.output,
            )
            assert_no_cli_crash(self, result)

    def test_writes_paired_png_and_prompt_for_every_projection(self) -> None:
        rasters: dict[str, bytes] = {}
        for projection in ("globe", "equirect", "mollweide"):
            with self.subTest(projection=projection), TemporaryDirectory() as temp_dir:
                base = Path(temp_dir) / projection
                result = CliRunner().invoke(
                    app,
                    [
                        "export-debug-map",
                        "--debug-dir",
                        str(self.cache),
                        "--projection",
                        projection,
                        "--output",
                        str(base),
                        "--width",
                        "320",
                        "--height",
                        "160",
                    ],
                )

                self.assertEqual(result.exit_code, 0, result.output)
                image = base.with_suffix(".png")
                prompt = Path(f"{base}.gpt-image-prompt.md")
                self.assertIn(
                    f"Wrote {image}, {prompt} | layer=cells/elevation_m "
                    f"projection={projection} stage=0 month=1",
                    result.output,
                )
                raster = image.read_bytes()
                self.assertEqual(raster[:8], PNG_SIGNATURE)
                # --width/--height reach the rasteriser in that order.
                self.assertEqual(_png_size(raster), (320, 160))
                self.assertIn("cells/elevation_m", prompt.read_text(encoding="utf-8"))
                rasters[projection] = raster

        # Each projection draws the same layer differently; identical bytes would
        # mean --projection only reached the echoed summary.
        self.assertEqual(len(set(rasters.values())), 3, sorted(rasters))

    def test_month_option_is_one_based_and_selects_the_monthly_slice(self) -> None:
        rasters: dict[int, bytes] = {}
        for month in (1, 12):
            with self.subTest(month=month), TemporaryDirectory() as temp_dir:
                base = Path(temp_dir) / f"month-{month}"
                result = CliRunner().invoke(
                    app,
                    [
                        "export-debug-map",
                        "--debug-dir",
                        str(self.cache),
                        "--layer",
                        "monthly/temperature_monthly_c",
                        "--output",
                        str(base),
                        "--width",
                        "320",
                        "--height",
                        "160",
                        "--projection",
                        "equirect",
                        "--month",
                        str(month),
                        "--no-prompt",
                    ],
                )

                # December is month 12 on the CLI and index 11 in the cache; a
                # command that forwarded 12 would be rejected by the exporter.
                self.assertEqual(result.exit_code, 0, result.output)
                image = base.with_suffix(".png")
                self.assertIn(
                    f"Wrote {image} | layer=monthly/temperature_monthly_c "
                    f"projection=equirect stage=0 month={month}",
                    result.output,
                )
                rasters[month] = image.read_bytes()

        self.assertNotEqual(rasters[1], rasters[12])

    def test_stage_option_selects_the_stage_history_row(self) -> None:
        layer = "hydrologic_water_budget_history/elevation_m"
        manifest = json.loads((self.cache / "manifest.json").read_text(encoding="utf-8"))
        history = manifest["stage_histories"]["hydrologic_water_budget_history"]
        stage_count = history["stage_count"]
        # One row per cell per stage, so the history really is stage-indexed.
        self.assertEqual(history["row_count"], stage_count * manifest["world"]["cell_count"])
        self.assertGreater(stage_count, 1)
        last_stage = stage_count - 1

        rasters: dict[int, bytes] = {}
        for stage in (0, last_stage):
            with self.subTest(stage=stage), TemporaryDirectory() as temp_dir:
                base = Path(temp_dir) / f"stage-{stage}"
                result = CliRunner().invoke(
                    app,
                    [
                        "export-debug-map",
                        "--debug-dir",
                        str(self.cache),
                        "--layer",
                        layer,
                        "--output",
                        str(base),
                        "--width",
                        "320",
                        "--height",
                        "160",
                        "--projection",
                        "equirect",
                        "--stage",
                        str(stage),
                        "--no-prompt",
                    ],
                )

                self.assertEqual(result.exit_code, 0, result.output)
                image = base.with_suffix(".png")
                self.assertIn(
                    f"Wrote {image} | layer={layer} projection=equirect "
                    f"stage={stage} month=1",
                    result.output,
                )
                rasters[stage] = image.read_bytes()

        # The terrain evolves across the recorded stages, so the first and the
        # last snapshot cannot raster to the same bytes.
        self.assertNotEqual(rasters[0], rasters[last_stage])

        with TemporaryDirectory() as temp_dir:
            result = CliRunner().invoke(
                app,
                [
                    "export-debug-map",
                    "--debug-dir",
                    str(self.cache),
                    "--layer",
                    layer,
                    "--output",
                    str(Path(temp_dir) / f"stage-{stage_count}"),
                    "--stage",
                    str(stage_count),
                    "--no-prompt",
                ],
            )

            # Stage indices are zero-based, so stage_count is one past the end.
            self.assertEqual(result.exit_code, 2, result.output)
            self.assertIn(
                f"Unable to export debug map: stage {stage_count} out of range", result.output
            )
            assert_no_cli_crash(self, result)
            self.assertEqual(sorted(Path(temp_dir).iterdir()), [])

    def test_no_prompt_writes_only_the_png(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "image-only"
            result = CliRunner().invoke(
                app,
                [
                    "export-debug-map",
                    "--debug-dir",
                    str(self.cache),
                    "--output",
                    str(base),
                    "--width",
                    "320",
                    "--height",
                    "160",
                    "--no-prompt",
                ],
            )

            image = base.with_suffix(".png")
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn(f"Wrote {image} | layer=cells/elevation_m", result.output)
            self.assertEqual(image.read_bytes()[:8], PNG_SIGNATURE)
            self.assertEqual([path.name for path in Path(temp_dir).iterdir()], ["image-only.png"])

    def test_no_image_writes_only_the_gpt_image_prompt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            base = Path(temp_dir) / "prompt-only"
            result = CliRunner().invoke(
                app,
                [
                    "export-debug-map",
                    "--debug-dir",
                    str(self.cache),
                    "--output",
                    str(base),
                    "--no-image",
                ],
            )

            prompt = Path(f"{base}.gpt-image-prompt.md")
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn(f"Wrote {prompt} | layer=cells/elevation_m", result.output)
            self.assertEqual(
                [path.name for path in Path(temp_dir).iterdir()],
                ["prompt-only.gpt-image-prompt.md"],
            )


class ServeCommandTests(TestCase):
    """``serve`` guards: workspace containment, cache selection and startup failures."""

    def test_relative_external_workspace_is_forwarded_to_the_server(self) -> None:
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            create_app = Mock(return_value=object())
            with patch.dict(sys.modules, _fake_server_modules(create_app)):
                result = CliRunner().invoke(app, ["serve", "--workspace", "../sibling/runs"])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(create_app.call_args.kwargs["workspace"], (Path(temp_dir) / "../sibling/runs").resolve())
            assert_no_cli_crash(self, result)

    def test_absolute_external_workspace_is_forwarded_to_the_server(self) -> None:
        with TemporaryDirectory() as outside, TemporaryDirectory() as temp_dir, chdir(temp_dir):
            create_app = Mock(return_value=object())
            with patch.dict(sys.modules, _fake_server_modules(create_app)):
                result = CliRunner().invoke(app, ["serve", "--workspace", outside])
            self.assertEqual(result.exit_code, 0, result.output)
            create_app.assert_called_once_with(None, workspace=Path(outside))
            assert_no_cli_crash(self, result)

    def test_rejects_a_debug_directory_that_does_not_exist(self) -> None:
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            result = CliRunner().invoke(app, ["serve", "--debug-dir", "no-such-cache"])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(
            "Invalid value for '--debug-dir' / '-d': Directory 'no-such-cache' does not exist.",
            _unboxed(result.output),
        )
        assert_no_cli_crash(self, result)

    def test_rejects_an_explicit_debug_directory_without_a_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            empty = Path("not-a-cache")
            empty.mkdir()

            result = CliRunner().invoke(app, ["serve", "--debug-dir", str(empty)])

            self.assertEqual(result.exit_code, 2, result.output)
            self.assertIn(
                "No manifest.json in not-a-cache; choose an export-debug cache or omit -d",
                result.output,
            )
            assert_no_cli_crash(self, result)

    def test_reports_a_friendly_message_when_the_debug_extra_is_unavailable(self) -> None:
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            # Poison the import site rather than uninstalling uvicorn.
            with patch.dict(sys.modules, {"uvicorn": None}):
                result = CliRunner().invoke(app, ["serve"])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Serving requires the optional debug dependencies", result.output)
        self.assertIn("pip install 'magic-geo[debug]'", result.output)
        assert_no_cli_crash(self, result)

    def test_falls_back_to_cacheless_when_the_automatic_cache_is_invalid(self) -> None:
        fake_app = object()
        create_app = Mock(side_effect=[ValueError("manifest format is not magic-geo-debug"), fake_app])
        modules = _fake_server_modules(create_app)

        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            cache = Path("runs/debug")
            cache.mkdir(parents=True)
            (cache / "manifest.json").write_text("{}", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                result = CliRunner().invoke(app, ["serve"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn(
            "Ignoring invalid automatic cache runs/debug: manifest format is not magic-geo-debug",
            result.output,
        )
        self.assertIn(
            "Serving web workbench with automatic workspace cache discovery", result.output
        )
        self.assertEqual(
            [(call.args, call.kwargs) for call in create_app.call_args_list],
            [
                ((Path("runs/debug"),), {"workspace": Path("runs")}),
                ((None,), {"workspace": Path("runs")}),
            ],
        )
        modules["uvicorn"].run.assert_called_once_with(
            fake_app, host="127.0.0.1", port=8642, log_level="warning"
        )

    def test_forwards_a_custom_workspace_host_and_port(self) -> None:
        fake_app = object()
        create_app = Mock(return_value=fake_app)
        modules = _fake_server_modules(create_app)

        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            cache = Path("sandbox/debug")
            cache.mkdir(parents=True)
            (cache / "manifest.json").write_text("{}", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                result = CliRunner().invoke(
                    app,
                    [
                        "serve",
                        "--workspace",
                        "sandbox",
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "9100",
                    ],
                )

        self.assertEqual(result.exit_code, 0, result.output)
        # The automatic cache is <workspace>/debug, not the hard-coded runs/debug.
        create_app.assert_called_once_with(Path("sandbox/debug"), workspace=Path("sandbox"))
        self.assertIn(
            "Serving web workbench debug cache sandbox/debug at http://0.0.0.0:9100",
            result.output,
        )
        modules["uvicorn"].run.assert_called_once_with(
            fake_app, host="0.0.0.0", port=9100, log_level="warning"
        )

    def test_reports_failure_when_the_cacheless_fallback_also_fails(self) -> None:
        create_app = Mock(
            side_effect=[ValueError("manifest is not a mapping"), OSError("workspace is read-only")]
        )
        modules = _fake_server_modules(create_app)

        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            cache = Path("sandbox/debug")
            cache.mkdir(parents=True)
            (cache / "manifest.json").write_text("{}", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                result = CliRunner().invoke(app, ["serve", "--workspace", "sandbox"])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Ignoring invalid automatic cache sandbox/debug", result.output)
        self.assertIn("Unable to start web workbench: workspace is read-only", result.output)
        self.assertNotIn("Serving web workbench", result.output)
        assert_no_cli_crash(self, result)
        # The retry keeps the chosen workspace and only drops the cache.
        self.assertEqual(
            [(call.args, call.kwargs) for call in create_app.call_args_list],
            [
                ((Path("sandbox/debug"),), {"workspace": Path("sandbox")}),
                ((None,), {"workspace": Path("sandbox")}),
            ],
        )
        modules["uvicorn"].run.assert_not_called()

    def test_does_not_retry_when_an_explicitly_chosen_cache_is_invalid(self) -> None:
        create_app = Mock(side_effect=ValueError("manifest version 99 is unsupported"))
        modules = _fake_server_modules(create_app)

        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            cache = Path("runs/debug")
            cache.mkdir(parents=True)
            (cache / "manifest.json").write_text("{}", encoding="utf-8")

            with patch.dict(sys.modules, modules):
                result = CliRunner().invoke(app, ["serve", "--debug-dir", str(cache)])

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn(
            "Unable to start web workbench: manifest version 99 is unsupported", result.output
        )
        self.assertNotIn("Ignoring invalid automatic cache", result.output)
        self.assertEqual(create_app.call_count, 1)
        modules["uvicorn"].run.assert_not_called()
