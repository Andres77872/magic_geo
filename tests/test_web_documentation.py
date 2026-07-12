from pathlib import Path
from unittest import TestCase

from magic_geo.config import WorldConfig


class WebDocumentationTests(TestCase):
    def test_configuration_reference_and_helper_guide_cover_public_surface(self) -> None:
        reference = Path("docs/configuration_reference.md").read_text(encoding="utf-8")
        helpers = Path("docs/configuration_helpers.md").read_text(encoding="utf-8")
        for section_name, section_field in WorldConfig.model_fields.items():
            self.assertIn(f"`{section_name}`", reference)
            section_model = section_field.annotation
            for field_name in section_model.model_fields:
                with self.subTest(section=section_name, field=field_name):
                    self.assertIn(f"`{field_name}`", reference)

        for helper_name in (
            "ConfigError",
            "apply_config_overrides",
            "config_schema",
            "create_config",
            "dump_config_yaml",
            "list_config_profiles",
            "load_config",
            "parse_config_overrides",
            "parse_config_yaml",
            "write_config",
            "generate_from_file",
            "generate_geo_from_file",
        ):
            self.assertIn(helper_name, helpers)

    def test_workbench_docs_cover_every_view_command_and_api_group(self) -> None:
        architecture = Path("docs/debugger.md").read_text(encoding="utf-8")
        guide = Path("docs/debug_ui_guide.md").read_text(encoding="utf-8")
        review = Path("docs/web_refactor_review.md").read_text(encoding="utf-8")
        combined = architecture + guide

        for view in ("Map", "Data", "Config", "Operations", "API"):
            self.assertIn(view, combined)
        for command in (
            "init-config",
            "backend",
            "generate",
            "validate-geo",
            "validate-geo-suite",
            "validate",
            "calibrate",
            "calibrate-ensemble",
            "derive-targets",
            "render",
            "render-raster",
            "export-debug",
            "export-rerun",
            "serve",
        ):
            self.assertIn(f"`{command}`", architecture)
        for endpoint in (
            "/api/status",
            "/api/config/schema",
            "/api/operations",
            "/api/jobs",
            "/api/catalog",
            "/api/family/{name}",
            "/api/section/{name}",
            "/api/docs",
        ):
            self.assertIn(endpoint, combined)

        self.assertIn("Remaining limitations", review)
        self.assertIn("Verification evidence", review)

