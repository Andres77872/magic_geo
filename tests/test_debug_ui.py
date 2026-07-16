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

    def test_status_refresh_requires_the_workbench_status_api(self) -> None:
        script = Path("src/magic_geo/debug_ui/app.js").read_text(encoding="utf-8")
        status_loader = script[
            script.index("async function loadServerStatus") : script.index(
                "async function initializeMap"
            )
        ]

        self.assertIn("await fetchJson('/api/status')", status_loader)
        self.assertIn("showStatusRefreshFailure(error);", status_loader)
        self.assertNotIn("optionalJson('/api/manifest')", status_loader)
        self.assertNotIn("legacyManifest", status_loader)
        self.assertNotIn("legacy debug cache", status_loader)

    def test_map_exports_png_and_copy_paste_image_prompt(self) -> None:
        html = Path("src/magic_geo/debug_ui/index.html").read_text(encoding="utf-8")
        script = Path("src/magic_geo/debug_ui/app.js").read_text(encoding="utf-8")
        cli = Path("src/magic_geo/cli.py").read_text(encoding="utf-8")
        web_jobs = Path("src/magic_geo/web_jobs.py").read_text(encoding="utf-8")
        guide = Path("docs/debug_ui_guide.md").read_text(encoding="utf-8")

        for control_id in ("export-map-image", "export-image-prompt"):
            self.assertIn(f'id="{control_id}"', html)
            self.assertIn(f"#{control_id}", script)

        for helper in (
            "mapExportBaseName",
            "mapViewFingerprint",
            "buildColorCodex",
            "buildImagePromptMarkdown",
            "downloadMapImage",
            "downloadImagePrompt",
        ):
            self.assertIn(helper, script)

        self.assertIn("toBlob", script)
        self.assertIn("image/png", script)
        self.assertIn("text/markdown", script)
        self.assertIn(".png", script)
        self.assertIn(".md", script)
        self.assertNotIn("api.openai.com", script)
        self.assertNotIn("/v1/images", script)
        self.assertIn('@app.command("export-debug-map")', cli)
        self.assertIn('"id": "export-debug-map"', web_jobs)
        self.assertIn('"equivalent_view": "map"', web_jobs)

        for documented_contract in (
            "final selected projection",
            "current camera framing",
            "currently visible map overlay",
            "copy/paste-ready GPT Image prompt",
            "color codex",
            "does **not** call OpenAI or any other image-generation API",
        ):
            self.assertIn(documented_contract, guide)

    def test_map_export_guards_pairing_plate_loads_and_stale_async_results(self) -> None:
        script = Path("src/magic_geo/debug_ui/app.js").read_text(encoding="utf-8")

        plate_loader = script[
            script.index("function cancelPlateLinesLoad") : script.index("function buildGraticule")
        ]
        self.assertIn("if (three.plateLinesLoading) return three.plateLinesLoading;", plate_loader)
        self.assertIn("{ signal: controller.signal }", plate_loader)
        self.assertIn("three.scene !== scene", plate_loader)
        self.assertIn("scene.add(lines);", plate_loader)
        self.assertEqual(plate_loader.count("scene.add(lines);"), 1)
        self.assertNotIn("three.scene.add(three.plateLines)", plate_loader)
        self.assertIn("three.plateLinesLoading = null;", plate_loader)
        self.assertIn("controller.abort();", plate_loader)

        disposal = script[
            script.index("function disposeMapScene") : script.index("function resetCacheDerivedState")
        ]
        self.assertIn("cancelPlateLinesLoad();", disposal)
        plate_toggle = script[
            script.index("bind($('#toggle-plates')") : script.index("bind($('#toggle-graticule')")
        ]
        self.assertIn("cancelPlateLinesLoad();", plate_toggle)

        naming = script[
            script.index("function exactViewNumber") : script.index("function rgbBytes")
        ]
        self.assertIn("function fnv1a64", naming)
        self.assertIn("magic-geo-map-view-v1", naming)
        self.assertIn("view-${filenameSlug(viewFingerprint, 'view')}", naming)
        self.assertIn("view.overlays.wireframe ? 1 : 0", naming)
        self.assertIn("exactViewNumber(pose.verticalFovDegrees)", naming)
        snapshot_view = script[
            script.index("function snapshotView") : script.index("function lastImageViewFor")
        ]
        self.assertIn("cameraPose: cameraPoseSnapshot()", snapshot_view)
        self.assertIn("mapViewFingerprint(snapshot, view)", snapshot_view)
        self.assertIn("mapExportFileNames(snapshot, projection, view.viewFingerprint)", snapshot_view)

        paired_view = script[
            script.index("function lastImageViewFor") : script.index("function downloadBlob")
        ]
        self.assertNotIn("snapshotView(snapshot)", paired_view)
        for snapshot_field in ("cacheIdentity", "layer", "stage", "month", "values"):
            self.assertIn(f"view.{snapshot_field} === snapshot.{snapshot_field}", paired_view)

        prompt_download = script[
            script.index("function downloadImagePrompt") : script.index("// ---------------------------------------------------------------------------\n// Layer docs card")
        ]
        self.assertIn("lastImageViewFor(snapshot) || snapshotView(snapshot)", prompt_download)

        prompt = script[
            script.index("function buildImagePromptMarkdown") : script.index("async function downloadMapImage")
        ]
        for camera_field in (
            "Deterministic view fingerprint",
            "Camera position (world x, y, z)",
            "OrbitControls target (world x, y, z)",
            "Camera up vector (world x, y, z)",
            "Vertical field of view",
        ):
            self.assertIn(camera_field, prompt)

        export_flow = script[
            script.index("async function downloadMapImage") : script.index("function downloadImagePrompt")
        ]
        generation_assignment = export_flow.index("state.exportGeneration = generation;")
        capture_await = export_flow.index("await captureMapCanvas")
        self.assertLess(generation_assignment, capture_await)
        self.assertIn("exportOperationMatchesState(generation, snapshot)", export_flow)
        self.assertIn(
            "if (generation !== null && !exportGenerationIsCurrent(generation)) return;",
            export_flow,
        )
        self.assertIn(
            "if (generation !== null && exportGenerationIsCurrent(generation))",
            export_flow,
        )
        reset = script[
            script.index("function resetCacheDerivedState") : script.index("function showStatusRefreshFailure")
        ]
        self.assertIn("state.exportGeneration += 1;", reset)

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
