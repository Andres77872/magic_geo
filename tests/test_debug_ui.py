from pathlib import Path
from unittest import TestCase


class DebugUiContractTests(TestCase):
    def test_workbench_has_cacheless_and_complete_data_views(self) -> None:
        html = Path("src/magic_geo/debug_ui/index.html").read_text(encoding="utf-8")
        script = Path("src/magic_geo/debug_ui/app.js").read_text(encoding="utf-8")

        for view in ("map", "data", "config", "operations", "api"):
            self.assertIn(f'id="tab-{view}"', html)
            self.assertIn(f'id="view-{view}"', html)

        for data_kind in (
            "scalars",
            "skipped",
            "layers",
            "cells",
            "stages",
            "families",
            "sections",
        ):
            self.assertIn(f'value="{data_kind}"', html)

        for endpoint in (
            "/api/status",
            "/api/worlds",
            "/api/worlds/select",
            "/api/catalog",
            "/api/stage-summary/",
            "/api/family/",
            "/api/section/",
            "/api/config/schema",
            "/api/config/profiles",
            "/api/config/validate",
            "/api/config/save",
            "/api/operations",
            "/api/jobs",
            "/api/backend",
            "/api/docs",
        ):
            self.assertIn(endpoint, script if endpoint != "/api/docs" else html + script)

        self.assertIn("cache_available", script)
        self.assertIn('id="world-select"', html)
        self.assertIn("Full nested records", html)
        self.assertIn("Scalar columns", html)

    def test_ui_uses_semantic_controls_and_responsive_rules(self) -> None:
        html = Path("src/magic_geo/debug_ui/index.html").read_text(encoding="utf-8")
        style = Path("src/magic_geo/debug_ui/style.css").read_text(encoding="utf-8")
        self.assertIn('role="tablist"', html)
        self.assertIn('role="tabpanel"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('@media (max-width:', style)
        self.assertIn('.cacheless', style)

    def test_cache_reads_are_revision_pinned_and_reinitialize_in_place(self) -> None:
        script = Path("src/magic_geo/debug_ui/app.js").read_text(encoding="utf-8")

        for marker in (
            "cacheIdentityFor",
            "status?.cache_revision ?? null",
            "cacheEpoch",
            "statusRequest",
            "catalogRequest",
            "mapRequest",
            "cacheContextIsCurrent(context)",
            "cacheRevisionUrl",
            "params.set('revision', context.revision)",
            "resetCacheDerivedState",
            "disposeMapScene",
            "Status unavailable",
        ):
            self.assertIn(marker, script)
        self.assertNotIn("window.location.reload()", script)
        self.assertIn("encodeURIComponent(String(layer.id))", script)

    def test_async_ui_results_commit_only_when_the_request_is_current(self) -> None:
        script = Path("src/magic_geo/debug_ui/app.js").read_text(encoding="utf-8")

        data_guard = script.index(
            "if (requestId !== state.dataRequest || !cacheContextIsCurrent(context)) return;"
        )
        self.assertGreater(script.index("rawLink.href = rawUrl", data_guard), data_guard)
        self.assertGreater(script.index("state.dataTotal = dataTotal", data_guard), data_guard)
        self.assertIn("requestId !== state.configTemplateRequest", script)
        self.assertIn("state.configEditRevision !== editRevision", script)
        self.assertIn("Only the explicit Reset", script)
        self.assertIn("Your YAML edits were kept", script)
        self.assertIn("loadServerStatus(),\n    loadConfigWorkbench(),", script)
        self.assertIn("Retained stage extras", script)
