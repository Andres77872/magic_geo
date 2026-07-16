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
DEBUG_UI_GUIDE_PATH = Path("docs/debug_ui_guide.md")


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
    def test_guide_scopes_camera_parity_and_numeric_lithology_codes(self) -> None:
        guide = DEBUG_UI_GUIDE_PATH.read_text(encoding="utf-8")
        normalized_guide = " ".join(guide.split())

        for contract in (
            "CLI independently reads the same debug cache",
            "canonical camera center/distance framing",
            "exact Three.js camera pose replay",
            "`--camera-position`, `--camera-target`, `--camera-up`, and `--vertical-fov`",
            "per-stage `lithology` layer is serialized as numeric codes 0–6",
            "does not contain an authoritative code-to-name table",
            "does not borrow the alphabetical category order",
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, normalized_guide)

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
