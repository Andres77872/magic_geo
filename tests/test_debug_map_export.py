from __future__ import annotations

import json
import re
import struct
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import SkipTest, TestCase
from unittest.mock import patch

from typer.testing import CliRunner

try:
    from magic_geo.cli import app
    from magic_geo.debug_export import export_debug_cache
    from magic_geo.debug_map_export import build_color_codex, export_map_reference
except ImportError as exc:  # pragma: no cover - exercised in minimal installs.
    raise SkipTest(f"debug map export tests require magic-geo[debug]: {exc}") from exc


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _make_map_cache(root: Path) -> tuple[Path, dict]:
    """Create a real two-cell Parquet cache with visible triangle fans."""

    world = {
        "name": "Tiny Semantic World",
        "schema_version": "test-v1",
        "mesh_backend": "test",
        "cells": [
            {
                "id": 0,
                "lat_deg": 0.0,
                "lon_deg": -45.0,
                "elevation_m": 120.0,
                "biome": "forest",
                "boundary_ring": [
                    [-40.0, -80.0],
                    [-40.0, -10.0],
                    [40.0, -10.0],
                    [40.0, -80.0],
                ],
            },
            {
                "id": 1,
                "lat_deg": 0.0,
                "lon_deg": 45.0,
                "elevation_m": 840.0,
                "biome": "ocean",
                "boundary_ring": [
                    [-40.0, 10.0],
                    [-40.0, 80.0],
                    [40.0, 80.0],
                    [40.0, 10.0],
                ],
            },
        ],
    }
    cache_dir = root / "debug"
    manifest = export_debug_cache(world, cache_dir, include_vtu=False)
    if manifest["mesh"]["triangle_count"] < 2:
        raise AssertionError("map fixture must contain real triangles")
    if not (cache_dir / "tables/cells.parquet").is_file():
        raise AssertionError("map fixture must contain a real Parquet cell table")
    return cache_dir, manifest


def _decode_rgb_png(payload: bytes) -> tuple[int, int, bytes]:
    """Decode the exporter's filter-0 RGB PNG without adding a Pillow dependency."""

    if not payload.startswith(PNG_SIGNATURE):
        raise AssertionError("not a PNG")
    cursor = len(PNG_SIGNATURE)
    width = height = 0
    compressed = bytearray()
    while cursor < len(payload):
        length = struct.unpack(">I", payload[cursor : cursor + 4])[0]
        chunk_type = payload[cursor + 4 : cursor + 8]
        chunk = payload[cursor + 8 : cursor + 8 + length]
        cursor += 12 + length
        if chunk_type == b"IHDR":
            width, height = struct.unpack(">II", chunk[:8])
            if chunk[8:13] != b"\x08\x02\x00\x00\x00":
                raise AssertionError("expected an 8-bit RGB PNG")
        elif chunk_type == b"IDAT":
            compressed.extend(chunk)
        elif chunk_type == b"IEND":
            break
    raw = zlib.decompress(bytes(compressed))
    stride = width * 3
    rows: list[bytes] = []
    for row in range(height):
        scanline = raw[row * (stride + 1) : (row + 1) * (stride + 1)]
        if not scanline or scanline[0] != 0:
            raise AssertionError("expected filter-0 PNG scanlines")
        rows.append(scanline[1:])
    return width, height, b"".join(rows)


class DebugMapExportTests(TestCase):
    def test_numeric_codex_records_robust_clipping_and_missing_data(self) -> None:
        codex = build_color_codex(
            {
                "id": "cells/elevation_m",
                "name": "elevation_m",
                "source": "cells",
                "kind": "numeric",
                "stats": {"min": -1000.0, "p2": -100.0, "p98": 900.0, "max": 2000.0},
            },
            [-1000.0, -100.0, 400.0, 900.0, 2000.0, float("nan")],
        )

        self.assertIn("Viridis normalized over -100 m to 900 m", codex)
        self.assertIn("Values outside that display range are clamped", codex)
        self.assertEqual(len(re.findall(r"^\| #[0-9a-f]{6} \|", codex, re.MULTILINE)), 11)
        self.assertIn("Missing or unavailable cell; do not invent content | 1 | 16.67%", codex)
        self.assertIn("Complete layer/time-axis raw range: -1000 m to 2000 m", codex)
        self.assertIn("Robust display range (2nd–98th percentile): -100 m to 900 m", codex)

    def test_cli_writes_paired_png_and_semantic_prompt(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir, manifest = _make_map_cache(root)
            output = root / "exports" / "reference.png"

            result = CliRunner().invoke(
                app,
                [
                    "export-debug-map",
                    "--debug-dir",
                    str(cache_dir),
                    "--layer",
                    "cells/biome",
                    "--output",
                    str(output),
                    "--projection",
                    "equirect",
                    "--width",
                    "320",
                    "--height",
                    "160",
                ],
            )

            self.assertEqual(result.exit_code, 0, result.output)
            image_path = output
            prompt_path = output.with_name("reference.gpt-image-prompt.md")
            self.assertTrue(image_path.is_file())
            self.assertTrue(prompt_path.is_file())
            self.assertIn(str(image_path), result.output)
            self.assertIn(str(prompt_path), result.output)
            self.assertGreater(manifest["mesh"]["triangle_count"], 0)

            payload = image_path.read_bytes()
            self.assertEqual(payload[:8], PNG_SIGNATURE)
            self.assertEqual(payload[12:16], b"IHDR")
            self.assertEqual(struct.unpack(">II", payload[16:24]), (320, 160))
            width, height, pixels = _decode_rgb_png(payload)
            self.assertEqual((width, height, len(pixels)), (320, 160, 320 * 160 * 3))

            prompt = prompt_path.read_text(encoding="utf-8")
            self.assertIn("Attach `reference.png` as Image 1", prompt)
            for section in (
                "## Goal",
                "## Priority order",
                "## Reference geometry",
                "## Mapped field",
                "## Color codex",
                "## Output",
            ):
                self.assertIn(section, prompt)
            self.assertIn("- Layer: `cells/biome`", prompt)
            self.assertIn("- Reference raster: 320 × 160 pixels", prompt)
            self.assertIn("| Guide color | Code | Category meaning | Cells | Share of slice |", prompt)

            category_rows = {
                label: (color, int(count), share)
                for color, _code, label, count, share in re.findall(
                    r"\| (#[0-9a-f]{6}) \| (\d+) \| ([^|]+?) \| (\d+) \| ([0-9.]+%) \|",
                    prompt,
                )
            }
            self.assertEqual(set(category_rows), {"forest", "ocean"})
            for color, count, share in category_rows.values():
                self.assertEqual((count, share), (1, "50.00%"))
                rgb = bytes.fromhex(color.removeprefix("#"))
                self.assertTrue(
                    any(pixels[offset : offset + 3] == rgb for offset in range(0, len(pixels), 3)),
                    f"codex color {color} was not rendered into the PNG",
                )

    def test_exporter_supports_image_only_prompt_only_and_rejects_neither(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir, _manifest = _make_map_cache(root)

            image_only = export_map_reference(
                cache_dir,
                layer_id="cells/biome",
                output=root / "image-only",
                projection="equirect",
                width=64,
                height=32,
                write_image=True,
                write_prompt=False,
            )
            self.assertEqual(image_only.image_path, root / "image-only.png")
            self.assertIsNone(image_only.prompt_path)
            self.assertTrue(image_only.image_path.is_file())
            self.assertFalse((root / "image-only.gpt-image-prompt.md").exists())

            prompt_only = export_map_reference(
                cache_dir,
                layer_id="cells/biome",
                output=root / "prompt-only.md",
                projection="mollweide",
                width=64,
                height=32,
                write_image=False,
                write_prompt=True,
            )
            self.assertIsNone(prompt_only.image_path)
            self.assertEqual(
                prompt_only.prompt_path,
                root / "prompt-only.gpt-image-prompt.md",
            )
            self.assertFalse((root / "prompt-only.png").exists())
            prompt = prompt_only.prompt_path.read_text(encoding="utf-8")
            self.assertIn("Attach `prompt-only.png` as Image 1", prompt)
            self.assertIn("forest", prompt)
            self.assertIn("ocean", prompt)

            with self.assertRaisesRegex(ValueError, "at least one of PNG or Markdown"):
                export_map_reference(
                    cache_dir,
                    layer_id="cells/biome",
                    output=root / "neither",
                    write_image=False,
                    write_prompt=False,
                )
            self.assertFalse((root / "neither.png").exists())
            self.assertFalse((root / "neither.gpt-image-prompt.md").exists())

    def test_exact_web_camera_pose_is_available_to_cli_export(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir, _manifest = _make_map_cache(root)

            result = export_map_reference(
                cache_dir,
                layer_id="cells/biome",
                output=root / "camera-replay",
                projection="equirect",
                width=96,
                height=48,
                camera_position="0.25,0.1,3.4",
                camera_target="0.25,0.1,0",
                camera_up="0,1,0",
                vertical_fov=55.0,
            )

            self.assertTrue(result.image_path.is_file())
            prompt = result.prompt_path.read_text(encoding="utf-8")
            self.assertIn("Camera position (Three.js world): `0.25, 0.1, 3.4`", prompt)
            self.assertIn("OrbitControls target (Three.js world): `0.25, 0.1, 0`", prompt)
            self.assertIn("Camera up vector (Three.js world): `0, 1, 0`", prompt)
            self.assertIn("Vertical field of view: 55°", prompt)
            self.assertRegex(prompt, r"View fingerprint: `[0-9a-f]{16}`")

            _width, _height, pixels = _decode_rgb_png(result.image_path.read_bytes())
            background = bytes.fromhex("10141a")
            self.assertTrue(
                any(pixels[offset : offset + 3] != background for offset in range(0, len(pixels), 3)),
                "explicit camera replay produced a blank map",
            )

    def test_prompt_only_validates_camera_and_incomplete_mesh(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir, _manifest = _make_map_cache(root)

            with self.assertRaisesRegex(ValueError, "camera distance must be a finite number"):
                export_map_reference(
                    cache_dir,
                    layer_id="cells/biome",
                    output=root / "bad-camera",
                    camera_distance=float("nan"),
                    write_image=False,
                    write_prompt=True,
                )

            manifest_path = cache_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["mesh"]["cells_without_ring"] = 1
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "debug mesh is incomplete"):
                export_map_reference(
                    cache_dir,
                    layer_id="cells/biome",
                    output=root / "incomplete",
                    write_image=False,
                    write_prompt=True,
                )
            self.assertFalse((root / "incomplete.gpt-image-prompt.md").exists())

    def test_cache_change_does_not_publish_mixed_or_partial_outputs(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            cache_dir, _manifest = _make_map_cache(root)
            image_path = root / "stable.png"
            prompt_path = root / "stable.gpt-image-prompt.md"
            image_path.write_bytes(b"previous image")
            prompt_path.write_text("previous prompt", encoding="utf-8")

            with patch(
                "magic_geo.debug_map_export._require_unchanged_snapshot",
                side_effect=[None, ValueError("debug cache changed during map export; retry")],
            ):
                with self.assertRaisesRegex(ValueError, "debug cache changed during map export"):
                    export_map_reference(
                        cache_dir,
                        layer_id="cells/biome",
                        output=root / "stable",
                        projection="equirect",
                        width=64,
                        height=32,
                    )

            self.assertEqual(image_path.read_bytes(), b"previous image")
            self.assertEqual(prompt_path.read_text(encoding="utf-8"), "previous prompt")
            self.assertEqual(list(root.glob(".stable.*.tmp")), [])
