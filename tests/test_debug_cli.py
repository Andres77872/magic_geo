from __future__ import annotations

import sys
from contextlib import chdir
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType
from unittest import TestCase
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from magic_geo.cli import app


class DebugCliTests(TestCase):
    @staticmethod
    def _fake_server_modules() -> tuple[ModuleType, ModuleType, Mock, Mock, object]:
        fake_app = object()
        uvicorn_run = Mock()
        create_app = Mock(return_value=fake_app)

        uvicorn_module = ModuleType("uvicorn")
        uvicorn_module.run = uvicorn_run
        debug_server_module = ModuleType("magic_geo.debug_server")
        debug_server_module.create_app = create_app
        return (
            uvicorn_module,
            debug_server_module,
            uvicorn_run,
            create_app,
            fake_app,
        )

    def test_serve_help_marks_debug_directory_optional(self) -> None:
        result = CliRunner().invoke(app, ["serve", "--help"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("--debug-dir", result.output)
        self.assertIn("default:", result.output)
        self.assertIn("<workspace>/debug", result.output)
        self.assertNotIn("[required]", result.output)

    def test_export_debug_map_help_exposes_all_native_export_controls(self) -> None:
        result = CliRunner().invoke(app, ["export-debug-map", "--help"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("without a browser", result.output)
        for option in (
            "--debug-dir",
            "--layer",
            "--output",
            "--projection",
            "--width",
            "--height",
            "--stage",
            "--month",
            "--center-lat",
            "--center-lon",
            "--camera-distance",
            "--camera-position",
            "--camera-target",
            "--camera-up",
            "--vertical-fov",
            "--cache-identity",
            "--wireframe",
            "--no-wireframe",
            "--plates",
            "--no-plates",
            "--graticule",
            "--no-graticule",
            "--image",
            "--no-image",
            "--prompt",
            "--no-prompt",
        ):
            with self.subTest(option=option):
                self.assertIn(option, result.output)

    def test_export_debug_map_rejects_disabling_both_outputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            result = CliRunner().invoke(
                app,
                [
                    "export-debug-map",
                    "--debug-dir",
                    temp_dir,
                    "--no-image",
                    "--no-prompt",
                ],
            )

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("at least one of PNG or Markdown output must be enabled", result.output)
        self.assertNotIn("Traceback", result.output)

    def test_serve_uses_runs_debug_when_directory_is_omitted(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            default_dir = Path("runs/debug")
            default_dir.mkdir(parents=True)
            (default_dir / "manifest.json").write_text("{}", encoding="utf-8")
            (
                uvicorn_module,
                debug_server_module,
                uvicorn_run,
                create_app,
                fake_app,
            ) = self._fake_server_modules()

            with patch.dict(
                sys.modules,
                {
                    "uvicorn": uvicorn_module,
                    "magic_geo.debug_server": debug_server_module,
                },
            ):
                result = runner.invoke(app, ["serve"])

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Serving web workbench debug cache runs/debug", result.output)
            create_app.assert_called_once_with(default_dir, workspace=Path("runs"))
            uvicorn_run.assert_called_once_with(
                fake_app,
                host="127.0.0.1",
                port=8642,
                log_level="warning",
            )

    def test_serve_honors_explicit_debug_directory(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            explicit_dir = Path("custom/cache")
            explicit_dir.mkdir(parents=True)
            (explicit_dir / "manifest.json").write_text("{}", encoding="utf-8")
            (
                uvicorn_module,
                debug_server_module,
                uvicorn_run,
                create_app,
                fake_app,
            ) = self._fake_server_modules()

            with patch.dict(
                sys.modules,
                {
                    "uvicorn": uvicorn_module,
                    "magic_geo.debug_server": debug_server_module,
                },
            ):
                result = runner.invoke(
                    app,
                    [
                        "serve",
                        "--debug-dir",
                        str(explicit_dir),
                        "--host",
                        "0.0.0.0",
                        "--port",
                        "9000",
                    ],
                )

            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Serving web workbench debug cache custom/cache", result.output)
            create_app.assert_called_once_with(explicit_dir, workspace=Path("runs"))
            uvicorn_run.assert_called_once_with(
                fake_app,
                host="0.0.0.0",
                port=9000,
                log_level="warning",
            )

    def test_serve_starts_cacheless_when_default_manifest_is_missing(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            (
                uvicorn_module,
                debug_server_module,
                uvicorn_run,
                create_app,
                fake_app,
            ) = self._fake_server_modules()
            with patch.dict(
                sys.modules,
                {
                    "uvicorn": uvicorn_module,
                    "magic_geo.debug_server": debug_server_module,
                },
            ):
                result = runner.invoke(app, ["serve"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("automatic workspace cache discovery", result.output)
        create_app.assert_called_once_with(None, workspace=Path("runs"))
        uvicorn_run.assert_called_once_with(
            fake_app,
            host="127.0.0.1",
            port=8642,
            log_level="warning",
        )

    def test_serve_reports_invalid_workspace_without_traceback(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            Path("workspace-file").write_text("not a directory", encoding="utf-8")
            (
                uvicorn_module,
                debug_server_module,
                uvicorn_run,
                create_app,
                _fake_app,
            ) = self._fake_server_modules()
            create_app.side_effect = FileExistsError("workspace is not a directory")
            with patch.dict(
                sys.modules,
                {
                    "uvicorn": uvicorn_module,
                    "magic_geo.debug_server": debug_server_module,
                },
            ):
                result = runner.invoke(
                    app,
                    ["serve", "--workspace", "workspace-file"],
                )

        self.assertEqual(result.exit_code, 2, result.output)
        self.assertIn("Unable to start web workbench", result.output)
        self.assertIn("not a directory", result.output)
        self.assertNotIn("Traceback", result.output)
        uvicorn_run.assert_not_called()
