from __future__ import annotations

from contextlib import chdir
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import runpy
import sys
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from typer.testing import CliRunner

from magic_geo import create_config, load_config
from magic_geo.cli import app

from support.cli import assert_no_cli_crash


class ConfigCliTests(TestCase):
    def test_module_entrypoint_routes_to_the_cli(self) -> None:
        output = StringIO()
        with (
            patch.object(sys, "argv", ["magic_geo", "--help"]),
            redirect_stdout(output),
            redirect_stderr(output),
            self.assertRaises(SystemExit) as exited,
        ):
            runpy.run_module("magic_geo", run_name="__main__")

        self.assertEqual(exited.exception.code, 0)
        self.assertIn("Usage", output.getvalue())
        self.assertIn("generate", output.getvalue())

    def test_init_config_uses_safe_local_target_and_earthlike_profile(self) -> None:
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            result = CliRunner().invoke(app, ["init-config"])

            self.assertEqual(result.exit_code, 0, result.output)
            target = Path("magic-geo.yaml")
            self.assertTrue(target.is_file())
            self.assertEqual(load_config(target), create_config("earthlike"))
            self.assertIn("profile=earthlike", result.output)

            generate_help = CliRunner().invoke(app, ["generate", "--help"])
            self.assertEqual(generate_help.exit_code, 0, generate_help.output)
            self.assertIn("magic-geo.yaml", generate_help.output)

    def test_init_config_profile_and_repeatable_typed_overrides(self) -> None:
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            result = CliRunner().invoke(
                app,
                [
                    "init-config",
                    "--profile",
                    "smoke",
                    "--set",
                    "run.name=browser smoke",
                    "--set",
                    "hydrology.preserve_geologic_depressions=false",
                    "--set",
                    "mesh.cell_count=256",
                    "--output",
                    "configs/custom.yaml",
                ],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            config = load_config(Path("configs/custom.yaml"))
            self.assertEqual(config.run.name, "browser smoke")
            self.assertFalse(config.hydrology.preserve_geologic_depressions)
            self.assertEqual(config.mesh.cell_count, 256)

    def test_init_config_rejects_unknown_profile_override_and_overwrite(self) -> None:
        runner = CliRunner()
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            invalid_profile = runner.invoke(app, ["init-config", "--profile", "unknown"])
            self.assertEqual(invalid_profile.exit_code, 2, invalid_profile.output)
            self.assertIn("unknown configuration profile", invalid_profile.output)

            invalid_override = runner.invoke(app, ["init-config", "--set", "mesh.missing=1"])
            self.assertEqual(invalid_override.exit_code, 2, invalid_override.output)
            self.assertIn("unknown configuration override", invalid_override.output)

            first = runner.invoke(app, ["init-config"])
            self.assertEqual(first.exit_code, 0, first.output)
            second = runner.invoke(app, ["init-config"])
            self.assertEqual(second.exit_code, 2, second.output)
            self.assertIn("--force", second.output)

    def test_generate_reports_malformed_yaml_without_traceback(self) -> None:
        with TemporaryDirectory() as temp_dir, chdir(temp_dir):
            path = Path("broken.yaml")
            path.write_text("run: [\n", encoding="utf-8")
            result = CliRunner().invoke(app, ["generate", "--config", str(path)])

            self.assertEqual(result.exit_code, 2, result.output)
            self.assertIn("invalid YAML", result.output)
            assert_no_cli_crash(self, result)

    def test_init_config_normalizes_complex_yaml_and_write_errors(self) -> None:
        deeply_nested = "[" * 80 + "0" + "]" * 80
        complex_result = CliRunner().invoke(
            app,
            ["init-config", "--set", f"run.name={deeply_nested}"],
        )
        self.assertEqual(complex_result.exit_code, 2, complex_result.output)
        self.assertIn("nesting exceeds", complex_result.output)
        assert_no_cli_crash(self, complex_result)

        for assignment in (
            "run.seed=" + "1" * 4301,
            "run.name=2020-02-30",
        ):
            with self.subTest(assignment=assignment[:40]):
                result = CliRunner().invoke(app, ["init-config", "--set", assignment])
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn("invalid", result.output.lower())
                assert_no_cli_crash(self, result)

        with patch("magic_geo.cli.write_config", side_effect=PermissionError("read-only")):
            write_result = CliRunner().invoke(app, ["init-config"])
        self.assertEqual(write_result.exit_code, 2, write_result.output)
        self.assertIn("read-only", write_result.output)
        assert_no_cli_crash(self, write_result)
