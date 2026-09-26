from __future__ import annotations

import ast
import re
from pathlib import Path
from unittest import SkipTest, TestCase

try:
    from magic_geo.debug_map_export import _CURATED_DESCRIPTIONS, _describe_layer
except ImportError as exc:  # pragma: no cover - exercised in minimal installs.
    raise SkipTest(f"debug map export parity tests require magic-geo[debug]: {exc}") from exc


LAYER_DOCS_PATH = Path("src/magic_geo/debug_ui/layer_docs.js")


def _curated_block() -> str:
    source = LAYER_DOCS_PATH.read_text(encoding="utf-8")
    return source.split("const CURATED = {", 1)[1].split("\n};", 1)[0]


def _curated_keys() -> set[str]:
    return set(
        re.findall(
            r"^\s*([A-Za-z_][A-Za-z0-9_]*):\s*.+,\s*$",
            _curated_block(),
            re.MULTILINE,
        )
    )


def _web_curated_value(name: str) -> str:
    match = re.search(
        rf"^\s*{re.escape(name)}:\s*(.+),\s*$",
        _curated_block(),
        re.MULTILINE,
    )
    if match is None:
        raise AssertionError(f"missing web CURATED entry {name}")
    value = ast.literal_eval(match.group(1))
    if not isinstance(value, str):
        raise AssertionError(f"web CURATED entry {name} is not a string")
    return value


class DebugMapExportDocumentationParityTests(TestCase):
    def test_cli_loads_every_web_curated_description(self) -> None:
        canonical_keys = _curated_keys()

        self.assertGreaterEqual(len(canonical_keys), 164)
        self.assertEqual(canonical_keys - _CURATED_DESCRIPTIONS.keys(), set())

    def test_representative_curated_prose_is_exactly_shared(self) -> None:
        for name, kind in (
            ("crust_age_ma", "numeric"),
            ("biome", "categorical"),
            ("cumulative_tectonic_elevation_change_m", "numeric"),
        ):
            with self.subTest(name=name):
                description = _describe_layer(
                    {
                        "id": f"cells/{name}",
                        "source": "cells",
                        "name": name,
                        "kind": kind,
                    }
                ).description
                self.assertEqual(description, _web_curated_value(name))

    def test_cli_roles_match_representative_web_naming_rules(self) -> None:
        cases = {
            "agricultural_zone_id": "identifier",
            "hillslope_sediment_incoming_edge_count": "diagnostic",
            "fluvial_sediment_routing_event_count": "diagnostic",
            "initial_elevation_m": "provenance",
            "cumulative_tectonic_elevation_change_m": "accumulator",
            "port_site_type": "classification",
            "agricultural_potential_index": "index",
            "advected_moisture_factor": "ratio",
            "dry_season_months": "seasonal",
            "elevation_m": "measurement",
        }

        for name, expected_role in cases.items():
            with self.subTest(name=name):
                kind = "categorical" if name == "port_site_type" else "numeric"
                layer_doc = _describe_layer(
                    {
                        "id": f"cells/{name}",
                        "source": "cells",
                        "name": name,
                        "kind": kind,
                    }
                )
                self.assertEqual(layer_doc.role, expected_role)

    def test_cli_family_context_keeps_the_web_semantics(self) -> None:
        layer_doc = _describe_layer(
            {
                "id": "cells/elevation_m",
                "source": "cells",
                "name": "elevation_m",
                "kind": "numeric",
            }
        )

        self.assertIn("one value per cell", layer_doc.family)
        self.assertIn("tectonics, climate, hydrology", layer_doc.family)


class CategoryPaletteParityTests(TestCase):
    """Browser and CLI exports must draw every class in the same guide color."""

    PALETTES_PATH = Path("src/magic_geo/debug_ui/palettes.js")

    def _web_tables(self) -> tuple[dict[str, str], list[str]]:
        source = self.PALETTES_PATH.read_text(encoding="utf-8")
        block = source.split("export const CATEGORY_COLORS = {", 1)[1].split("\n};", 1)[0]
        colors = dict(re.findall(r"^\s*'([^']+)': '(#[0-9a-f]{6})',\s*$", block, re.MULTILINE))
        palette_block = source.split("export const QUALITATIVE_PALETTE = [", 1)[1].split("];", 1)[0]
        return colors, re.findall(r"'(#[0-9a-f]{6})'", palette_block)

    def test_semantic_and_qualitative_tables_are_identical(self) -> None:
        from magic_geo.debug_map_export import _CATEGORY_COLORS, _QUALITATIVE_PALETTE

        colors, palette = self._web_tables()
        self.assertGreaterEqual(len(colors), 40)
        self.assertEqual(colors, _CATEGORY_COLORS)
        self.assertEqual(palette, list(_QUALITATIVE_PALETTE))

    def test_guide_colors_never_reuse_reserved_map_colors(self) -> None:
        from magic_geo.debug_map_export import MAP_BACKGROUND_HEX, MISSING_COLOR_HEX

        colors, palette = self._web_tables()
        reserved = {MAP_BACKGROUND_HEX.lower(), MISSING_COLOR_HEX.lower()}
        self.assertFalse(reserved & (set(colors.values()) | set(palette)))
        self.assertEqual(len(palette), len(set(palette)))

    def test_one_layer_never_assigns_two_classes_the_same_color(self) -> None:
        from magic_geo.debug_map_export import _category_palette

        for categories in (
            ["ocean", "open_ocean", "marine", "water"],
            ["desert", "hot_desert", "arid", "none", "False"],
            [f"class_{index}" for index in range(15)],
        ):
            with self.subTest(categories=categories):
                colors = _category_palette(categories)
                self.assertEqual(len(colors), len(set(colors)))


class NumericScaleParityTests(TestCase):
    """The CLI export colours numeric layers exactly as the web map does.

    Both read the same generated lookup tables and resolve the same scale
    rules; ``tests/fixtures/colormap_scale_cases.json`` is also asserted by
    ``tests/test_debug_ui.mjs`` against ``debug_ui/colormaps.js``.
    """

    COLORMAPS_PATH = Path("src/magic_geo/debug_ui/colormaps.js")
    CASES_PATH = Path("tests/fixtures/colormap_scale_cases.json")

    def test_generated_tables_are_current(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("generate_colormaps", Path("scripts/generate_colormaps.py"))
        generator = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(generator)
        from magic_geo.debug_map_export import _COLORMAP_LUTS

        expected = generator.build_luts()
        self.assertEqual(set(_COLORMAP_LUTS), set(expected))
        for name, entries in expected.items():
            with self.subTest(colormap=name):
                self.assertEqual(list(_COLORMAP_LUTS[name]), [tuple(entry) for entry in entries])

    def test_viridis_table_is_byte_identical_to_the_historical_polynomial(self) -> None:
        from magic_geo.debug_map_export import _COLORMAP_LUTS, _VIRIDIS_LUT

        self.assertEqual(_COLORMAP_LUTS["viridis"], _VIRIDIS_LUT)

    def test_perceptual_ordering_of_the_tables(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("generate_colormaps", Path("scripts/generate_colormaps.py"))
        generator = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(generator)
        from magic_geo.debug_map_export import _COLORMAP_LUTS

        lightness = {
            name: [generator._rgb_to_lab(tuple(channel / 255 for channel in rgb))[0] for rgb in lut]
            for name, lut in _COLORMAP_LUTS.items()
        }
        # Sequential: lightness never falls by more than rounding noise.
        self.assertTrue(all(b >= a - 0.3 for a, b in zip(lightness["viridis"], lightness["viridis"][1:])))
        # Terrain: each half gets lighter away from deep water, with a dark
        # step at sea level (index 128) that marks the 0 m contour.
        ocean, land = lightness["terrain"][:128], lightness["terrain"][128:]
        self.assertTrue(all(b >= a - 0.3 for a, b in zip(ocean, ocean[1:])))
        self.assertTrue(all(b >= a - 0.3 for a, b in zip(land, land[1:])))
        self.assertGreater(ocean[-1] - land[0], 30)
        # Diverging (Moreland): lightest at the centre, symmetric ends.
        cool = lightness["coolwarm"]
        self.assertEqual(max(range(256), key=cool.__getitem__) in (127, 128), True)
        self.assertAlmostEqual(cool[0], cool[255], delta=3.0)

    def test_shared_cases_resolve_to_the_same_scale_and_colours(self) -> None:
        import json

        from magic_geo.debug_map_export import _numeric_scale, _rgb_hex, _value_rgb

        cases = json.loads(self.CASES_PATH.read_text(encoding="utf-8"))["cases"]
        self.assertGreaterEqual(len(cases), 8)
        for case in cases:
            with self.subTest(layer=case["layer"]["name"], why=case["why"]):
                scale = _numeric_scale(case["layer"])
                self.assertEqual(scale.mode, case["scale"]["mode"])
                self.assertEqual(scale.colormap, case["scale"]["colormap"])
                self.assertAlmostEqual(scale.low, case["scale"]["lo"], places=9)
                self.assertAlmostEqual(scale.high, case["scale"]["hi"], places=9)
                for value, color in case["samples"]:
                    self.assertEqual(_rgb_hex(_value_rgb(case["layer"], float(value), scale)), color, f"value {value}")

    def test_identifier_colours_follow_the_documented_identifier_role(self) -> None:
        from magic_geo.debug_map_export import _is_identifier_layer

        names = ["id", "plate_id", "basin_id", "flow_to", "spill_to", "glacier_flow_to", "depression_sink_cell_id",
                 "river_capture_target_basin_id", "elevation_m", "healpix_like_lon_bin", "cell_edge_count", "idle_index"]
        for name in names:
            with self.subTest(name=name):
                role = _describe_layer({"name": name, "source": "cells", "kind": "numeric"}).role
                self.assertEqual(_is_identifier_layer({"name": name, "kind": "numeric"}), role == "identifier")

    def test_web_rules_are_the_same_rules(self) -> None:
        source = self.COLORMAPS_PATH.read_text(encoding="utf-8")
        from magic_geo import debug_map_export as export

        self.assertIn(f"const ELEVATION_NAME = /{export._ELEVATION_NAME.pattern}/;", source)
        self.assertIn(f"const CHANGE_NAME = /{export._CHANGE_NAME.pattern}/;", source)
        pointers = re.search(r"IDENTIFIER_POINTERS = new Set\(\[([^\]]*)\]\)", source)
        self.assertIsNotNone(pointers)
        self.assertEqual(set(re.findall(r"'([a-z_]+)'", pointers.group(1))), set(export._IDENTIFIER_POINTERS))
