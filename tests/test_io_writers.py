"""Rendering-tail coverage for :mod:`magic_geo.io` map writers.

``tests/test_serialization.py`` covers ``write_json``/``read_world``/``write_world``
and ``tests/test_smoke_exports.py`` covers the CSV/markdown field inventory plus a
single mollweide SVG/PPM smoke render. This file exercises the parts those leave
alone: every projection, every rendering option, and the degenerate worlds that
drive the skip branches of ``write_svg_map`` and ``write_raster_map``.

Assertions parse the emitted SVG as XML and the emitted PPM header/pixels, so a
regression in geometry, element counts or palette shows up as a failure rather
than as a silently different picture.
"""

from __future__ import annotations

import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from xml.etree import ElementTree

from magic_geo.io import write_raster_map, write_summary_markdown, write_svg_map

from support import worlds

SVG = "{http://www.w3.org/2000/svg}"

#: Background fill of an untouched raster pixel, and the out-of-globe fill.
SPACE_RGB = (12, 25, 37)
BACKDROP_RGB = (23, 59, 86)


def _cell(cell_id: int | None, lat: float, lon: float, **overrides: object) -> dict[str, object]:
    """A minimal cell carrying every field the map writers read."""
    cell: dict[str, object] = {
        "lat_deg": lat,
        "lon_deg": lon,
        "elevation_m": 300.0,
        "is_water": False,
        "neighbors": [],
        "biome": "temperate_grassland",
        "landform": "plain",
        "temperature_c": 15.0,
        "precipitation_mm_y": 800.0,
    }
    if cell_id is not None:
        cell["id"] = cell_id
    cell.update(overrides)
    return cell


def _world(cells: list[dict[str, object]], **overrides: object) -> dict[str, object]:
    world: dict[str, object] = {
        "name": "writer probe",
        "cells": cells,
        "settlements": [],
        "routes": [],
        "sacred_areas": [],
        "ruins": [],
    }
    world.update(overrides)
    return world


def _parse(path: Path) -> ElementTree.Element:
    return ElementTree.parse(path).getroot()


def _terrain_cells(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [node for node in root.iter(SVG + "circle") if node.get("class") == "terrain-cell"]


def _settlement_circles(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [node for node in root.iter(SVG + "circle") if node.get("stroke") == "#2b1f17"]


def _globe_circles(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [node for node in root.iter(SVG + "circle") if node.get("stroke") == "#8fb6c6"]


def _contour_group(root: ElementTree.Element) -> ElementTree.Element | None:
    for node in root.iter(SVG + "g"):
        if node.get("class") == "terrain-contours":
            return node
    return None


def _contour_lines(root: ElementTree.Element) -> list[ElementTree.Element]:
    return [
        node
        for node in root.iter(SVG + "line")
        if (node.get("class") or "").startswith("terrain-contour")
    ]


def _all_lines(root: ElementTree.Element) -> list[ElementTree.Element]:
    return list(root.iter(SVG + "line"))


def _points(nodes: list[ElementTree.Element]) -> list[tuple[str, str]]:
    return [(node.get("cx", ""), node.get("cy", "")) for node in nodes]


def _mollweide_theta(lat_deg: float) -> float:
    """Solve ``2*theta + sin(2*theta) == pi * sin(lat)`` by bisection.

    This is the defining equation of the Mollweide auxiliary angle. Solving it
    here (rather than reusing the writer's Newton iteration) means the expected
    anchor points are derived from the projection, not from the implementation.
    """
    target = math.pi * math.sin(math.radians(lat_deg))
    low, high = -math.pi / 2.0, math.pi / 2.0
    for _ in range(200):
        middle = (low + high) / 2.0
        if 2.0 * middle + math.sin(2.0 * middle) < target:
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def _mollweide_point(
    lat_deg: float, lon_deg: float, width: float, height: float
) -> tuple[str, str]:
    theta = _mollweide_theta(lat_deg)
    x = width * (0.5 + math.radians(lon_deg) * math.cos(theta) / (2.0 * math.pi))
    y = height * (0.5 - math.sin(theta) / 2.0)
    return (f"{x:.2f}", f"{y:.2f}")


def _read_ppm(path: Path) -> tuple[bytes, int, int, bytes]:
    """Split a binary PPM into ``(comment, width, height, pixel_bytes)``."""
    magic, comment, dimensions, maxval, body = path.read_bytes().split(b"\n", 4)
    if magic != b"P6" or maxval != b"255":
        raise AssertionError(f"unexpected PPM header: {magic!r} {maxval!r}")
    width_text, height_text = dimensions.split(b" ")
    return comment, int(width_text), int(height_text), body


def _pixel(body: bytes, width: int, x: int, y: int) -> tuple[int, int, int]:
    index = (y * width + x) * 3
    red, green, blue = body[index : index + 3]
    return (red, green, blue)


class SvgProjectionTests(TestCase):
    """Projection geometry and document-level attributes of ``write_svg_map``."""

    def test_projection_matrix_document_attributes_and_cell_counts(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        self.assertEqual(len(world["cells"]), 256)
        # The orthographic hemisphere test is |lon| <= 90 for any |lat| < 90.
        front_hemisphere = [cell for cell in world["cells"] if abs(float(cell["lon_deg"])) <= 90.0]
        self.assertGreater(len(front_hemisphere), 0)
        self.assertLess(len(front_hemisphere), 256)

        expected_counts = {
            "equirectangular": 256,
            "mollweide": 256,
            "orthographic": len(front_hemisphere),
        }
        with TemporaryDirectory() as tmpdir:
            for projection, expected in expected_counts.items():
                with self.subTest(projection=projection):
                    output = Path(tmpdir) / f"{projection}.svg"
                    write_svg_map(
                        output,
                        world,
                        width=480,
                        height=240,
                        projection=projection,
                        contours=False,
                    )
                    root = _parse(output)
                    self.assertEqual(root.get("viewBox"), "0 0 480 240")
                    self.assertEqual(root.get("width"), "480")
                    self.assertEqual(root.get("height"), "240")
                    self.assertEqual(root.get("data-projection"), projection)
                    self.assertEqual(root.get("data-renderer"), "terrain-v1")
                    self.assertEqual(root.get("data-contours"), "false")
                    self.assertEqual(
                        root.findtext(SVG + "title"),
                        f"earthlike_mvp {projection} causal terrain map",
                    )
                    self.assertIsNone(_contour_group(root))

                    filters = list(root.iter(SVG + "filter"))
                    self.assertEqual([node.get("id") for node in filters], ["terrain-soften"])
                    blur = filters[0].find(SVG + "feGaussianBlur")
                    self.assertIsNotNone(blur)
                    assert blur is not None
                    self.assertEqual(blur.get("stdDeviation"), "0.08")

                    rendered = _terrain_cells(root)
                    self.assertEqual(len(rendered), expected)
                    for node in rendered:
                        self.assertEqual(node.get("filter"), "url(#terrain-soften)")
                        x = float(node.get("cx", "nan"))
                        y = float(node.get("cy", "nan"))
                        self.assertTrue(0.0 <= x <= 480.0, f"cx out of viewport: {x}")
                        self.assertTrue(0.0 <= y <= 240.0, f"cy out of viewport: {y}")

                    globes = _globe_circles(root)
                    if projection == "orthographic":
                        self.assertEqual(len(globes), 1)
                        self.assertEqual(globes[0].get("cx"), "240.00")
                        self.assertEqual(globes[0].get("cy"), "120.00")
                        self.assertEqual(globes[0].get("r"), "112.80")
                        for node in rendered:
                            dx = float(node.get("cx", "nan")) - 240.0
                            dy = float(node.get("cy", "nan")) - 120.0
                            self.assertLessEqual(math.hypot(dx, dy), 112.81)
                    else:
                        self.assertEqual(globes, [])

    def test_projection_anchor_points_are_exact(self) -> None:
        cells = [
            _cell(0, 0.0, 0.0),
            _cell(1, 90.0, 0.0),
            _cell(2, -90.0, 0.0),
            _cell(3, 0.0, 90.0),
            _cell(4, 0.0, -90.0),
            _cell(5, 0.0, 180.0),
            _cell(6, 90.0, 90.0),
        ]
        world = _world(cells)
        # width=400, height=200 -> orthographic globe radius = 200 * 0.47 = 94.0
        expected = {
            "equirectangular": [
                ("200.00", "100.00"),
                ("200.00", "0.00"),
                ("200.00", "200.00"),
                ("300.00", "100.00"),
                ("100.00", "100.00"),
                ("400.00", "100.00"),
                ("300.00", "0.00"),
            ],
            # Mollweide agrees with equirectangular on the equator and the
            # central meridian, but collapses every longitude at the pole.
            "mollweide": [
                ("200.00", "100.00"),
                ("200.00", "0.00"),
                ("200.00", "200.00"),
                ("300.00", "100.00"),
                ("100.00", "100.00"),
                ("400.00", "100.00"),
                ("200.00", "0.00"),
            ],
            # lon=180 is on the far side of the globe and is dropped entirely.
            "orthographic": [
                ("200.00", "100.00"),
                ("200.00", "6.00"),
                ("200.00", "194.00"),
                ("294.00", "100.00"),
                ("106.00", "100.00"),
                ("200.00", "6.00"),
            ],
        }
        with TemporaryDirectory() as tmpdir:
            for projection, points in expected.items():
                with self.subTest(projection=projection):
                    output = Path(tmpdir) / f"anchors_{projection}.svg"
                    write_svg_map(
                        output,
                        world,
                        width=400,
                        height=200,
                        projection=projection,
                        contours=False,
                    )
                    self.assertEqual(_points(_terrain_cells(_parse(output))), points)

    def test_mollweide_matches_the_closed_form_at_mid_latitudes(self) -> None:
        """The equator, the poles and the central meridian are fixed points of the
        auxiliary-angle iteration: they project correctly even if the solver never
        runs. These mid-latitude anchors are the ones that actually pin it."""
        anchors = [(45.0, 90.0), (45.0, 0.0), (-60.0, 180.0), (30.0, -120.0), (60.0, 45.0)]
        cells = [_cell(index, lat, lon) for index, (lat, lon) in enumerate(anchors)]
        expected = [_mollweide_point(lat, lon, 400.0, 200.0) for lat, lon in anchors]
        # Cross-check the bisection helper itself against hand-solved values.
        self.assertEqual(expected[0], ("280.59", "40.80"))
        self.assertEqual(expected[2], ("329.42", "176.24"))
        # Latitude 45 is compressed towards the pole: equirectangular would put it
        # at y = 50.00 and lon 90 at x = 300.00.
        self.assertEqual(expected[1], ("200.00", "40.80"))
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "mollweide_mid.svg"
            write_svg_map(
                output, _world(cells), width=400, height=200, projection="mollweide", contours=False
            )
            self.assertEqual(_points(_terrain_cells(_parse(output))), expected)

    def test_mollweide_raster_disc_sits_at_the_closed_form_centre(self) -> None:
        # A lone cell at lat 60, lon 150 is drawn as an 18 px disc. Mollweide puts
        # its centre at (110.83, 8.55); equirectangular would put it at (132, 12).
        self.assertEqual(_mollweide_point(60.0, 150.0, 144.0, 72.0), ("110.83", "8.55"))
        world = _world([_cell(0, 60.0, 150.0)])
        with TemporaryDirectory() as tmpdir:
            # Also covers the raster writer creating missing parent directories.
            mollweide = Path(tmpdir) / "nested" / "deep" / "moll.ppm"
            equirectangular = Path(tmpdir) / "equi.ppm"
            write_raster_map(
                mollweide, world, width=144, height=72, projection="mollweide", texture=False
            )
            write_raster_map(equirectangular, world, width=144, height=72, texture=False)
            _, width, _, mollweide_body = _read_ppm(mollweide)
            _, _, _, equirectangular_body = _read_ppm(equirectangular)
            # Painted iff within 18 px of the centre, so these probes bracket it to
            # better than a pixel in x and in y.
            cases = [
                ((128, 8), True, True),
                ((92, 8), False, False),
                ((110, 25), True, False),
                ((110, 27), False, False),
                ((132, 12), False, True),
                ((110, 8), True, False),
            ]
            for probe, in_mollweide, in_equirectangular in cases:
                with self.subTest(probe=probe):
                    self.assertEqual(
                        _pixel(mollweide_body, width, *probe) != BACKDROP_RGB, in_mollweide
                    )
                    self.assertEqual(
                        _pixel(equirectangular_body, width, *probe) != BACKDROP_RGB,
                        in_equirectangular,
                    )

    def test_projection_name_is_normalised_case_insensitively(self) -> None:
        world = _world([_cell(0, 10.0, 20.0)])
        with TemporaryDirectory() as tmpdir:
            for requested, normalised in (
                ("MOLLWEIDE", "mollweide"),
                ("Orthographic", "orthographic"),
                ("EquiRectangular", "equirectangular"),
            ):
                with self.subTest(projection=requested):
                    svg_path = Path(tmpdir) / f"{normalised}.svg"
                    write_svg_map(svg_path, world, width=80, height=40, projection=requested)
                    self.assertEqual(_parse(svg_path).get("data-projection"), normalised)

                    ppm_path = Path(tmpdir) / f"{normalised}.ppm"
                    write_raster_map(ppm_path, world, width=40, height=20, projection=requested)
                    comment, _, _, _ = _read_ppm(ppm_path)
                    self.assertEqual(
                        comment,
                        f"# magic-geo raster-terrain-v1 projection={normalised} texture=true".encode(),
                    )

    def test_unknown_projection_is_rejected_by_both_writers(self) -> None:
        world = _world([_cell(0, 0.0, 0.0)])
        with TemporaryDirectory() as tmpdir:
            svg_path = Path(tmpdir) / "bad.svg"
            ppm_path = Path(tmpdir) / "bad.ppm"
            with self.assertRaisesRegex(ValueError, r"^unknown projection: sinusoidal$"):
                write_svg_map(svg_path, world, projection="Sinusoidal")
            with self.assertRaisesRegex(ValueError, r"^unknown projection: robinson$"):
                write_raster_map(ppm_path, world, projection="Robinson")
            self.assertFalse(svg_path.exists())
            self.assertFalse(ppm_path.exists())


class SvgOptionTests(TestCase):
    """``max_cells``, ``labels`` and ``contours`` option handling."""

    def test_max_cells_downsamples_with_a_stride(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        cells = world["cells"]
        self.assertEqual(len(cells), 256)
        cases = [
            (None, 256, 1),
            (0, 256, 1),
            (-4, 256, 1),
            (256, 256, 1),
            (400, 256, 1),
            (128, 128, 2),
            (100, 86, 3),
            (64, 64, 4),
        ]
        with TemporaryDirectory() as tmpdir:
            for max_cells, expected_count, stride in cases:
                with self.subTest(max_cells=max_cells):
                    output = Path(tmpdir) / f"stride_{max_cells}.svg"
                    write_svg_map(
                        output,
                        world,
                        width=360,
                        height=180,
                        max_cells=max_cells,
                        contours=False,
                    )
                    rendered = _terrain_cells(_parse(output))
                    self.assertEqual(len(rendered), expected_count)
                    # The kept cells are cells[::stride], in order.
                    for index, node in list(enumerate(rendered))[:6]:
                        source = cells[index * stride]
                        self.assertEqual(
                            (node.get("cx"), node.get("cy")),
                            (
                                f"{(float(source['lon_deg']) + 180.0) / 360.0 * 360.0:.2f}",
                                f"{(90.0 - float(source['lat_deg'])) / 180.0 * 180.0:.2f}",
                            ),
                        )

    def test_cell_radius_is_clamped_between_0_7_and_3_2_px(self) -> None:
        # radius = sqrt(viewport area / rendered cells) * 0.23, clamped to [0.7, 3.2].
        cases = [
            (1, 400, 200, "3.20"),  # raw 65.05 -> upper clamp
            (10, 40, 20, "2.06"),  # raw 2.0572 -> unclamped
            (30, 20, 10, "0.70"),  # raw 0.5939 -> lower clamp
        ]
        with TemporaryDirectory() as tmpdir:
            for count, width, height, expected in cases:
                with self.subTest(count=count):
                    raw = (width * height / count) ** 0.5 * 0.23
                    self.assertAlmostEqual(float(expected), max(0.7, min(3.2, raw)), places=2)
                    cells = [_cell(index, 0.0, float(index)) for index in range(count)]
                    output = Path(tmpdir) / f"radius_{count}.svg"
                    write_svg_map(
                        output, _world(cells), width=width, height=height, contours=False
                    )
                    rendered = _terrain_cells(_parse(output))
                    self.assertEqual(len(rendered), count)
                    self.assertEqual({node.get("r") for node in rendered}, {expected})

    def test_labels_render_the_top_settlements_only(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        ranked = sorted(
            world["settlements"], key=lambda item: float(item.get("score", 0.0)), reverse=True
        )
        expected_texts = [
            f"{str(item['type']).replace('_', ' ').title()} {item['id']}" for item in ranked
        ]
        self.assertEqual(expected_texts[0], "River City 0")
        with TemporaryDirectory() as tmpdir:
            labelled = Path(tmpdir) / "labelled.svg"
            write_svg_map(labelled, world, width=480, height=240, labels=True, contours=False)
            root = _parse(labelled)
            self.assertEqual([node.text for node in root.iter(SVG + "text")], expected_texts)

            unlabelled = Path(tmpdir) / "unlabelled.svg"
            write_svg_map(unlabelled, world, width=480, height=240, labels=False, contours=False)
            self.assertEqual(list(_parse(unlabelled).iter(SVG + "text")), [])

    def test_labels_are_capped_at_twenty_four_entries(self) -> None:
        cells = [_cell(index, 0.0, float(index)) for index in range(30)]
        settlements = [
            {"id": index, "cell_id": index, "type": "port", "score": index / 100.0}
            for index in range(30)
        ]
        world = _world(cells, settlements=settlements)
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "capped.svg"
            write_svg_map(output, world, width=400, height=200, labels=True, contours=False)
            root = _parse(output)
            texts = [node.text for node in root.iter(SVG + "text")]
            self.assertEqual(len(texts), 24)
            self.assertEqual(texts[0], "Port 29")
            self.assertEqual(texts[-1], "Port 6")
            # Every settlement still gets a marker; only the labels are capped.
            self.assertEqual(len(_settlement_circles(root)), 30)

    def test_contour_interval_is_clamped_and_levels_are_multiples(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        with TemporaryDirectory() as tmpdir:
            for requested, effective in ((10.0, 50.0), (500.0, 500.0), (2000.0, 2000.0)):
                with self.subTest(contour_interval_m=requested):
                    output = Path(tmpdir) / f"contours_{requested:.0f}.svg"
                    write_svg_map(
                        output,
                        world,
                        width=480,
                        height=240,
                        max_cells=120,
                        contour_interval_m=requested,
                    )
                    root = _parse(output)
                    self.assertEqual(root.get("data-contours"), "true")
                    group = _contour_group(root)
                    self.assertIsNotNone(group)
                    assert group is not None
                    self.assertEqual(group.get("data-contour-interval-m"), f"{effective:.0f}")
                    lines = _contour_lines(root)
                    self.assertGreater(len(lines), 0)
                    for node in lines:
                        level = float(node.get("data-elevation-m", "nan"))
                        self.assertEqual(level % effective, 0.0)
                        major = int(round(level / effective)) % 2 == 0
                        self.assertEqual(
                            node.get("class"),
                            "terrain-contour terrain-contour-major"
                            if major
                            else "terrain-contour terrain-contour-minor",
                        )
                        self.assertEqual(node.get("stroke"), "#f4e7b8" if major else "#c9b77e")
                        self.assertEqual(
                            node.get("stroke-width"), "0.62" if major else "0.38"
                        )
                        self.assertEqual(
                            node.get("stroke-opacity"), "0.54" if major else "0.34"
                        )
                        self.assertEqual(node.get("stroke-linecap"), "round")


class SvgDegenerateWorldTests(TestCase):
    """Single-cell, empty, all-water and all-land worlds."""

    def test_empty_world_renders_only_the_background(self) -> None:
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "empty.svg"
            write_svg_map(output, _world([]), width=120, height=60)
            root = _parse(output)
            self.assertEqual(root.get("viewBox"), "0 0 120 60")
            self.assertEqual(_terrain_cells(root), [])
            self.assertIsNone(_contour_group(root))
            rects = list(root.iter(SVG + "rect"))
            self.assertEqual(len(rects), 1)
            self.assertEqual(rects[0].get("fill"), "#173b56")

    def test_single_cell_world_has_no_relief_and_no_contours(self) -> None:
        # elevation 60 m exercises the lowest elevation-ramp branch, and the
        # cell has no neighbours so its relief shading falls back to zero.
        world = _world([_cell(0, 12.5, -30.0, elevation_m=60.0)])
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "nested" / "deep" / "one.svg"
            write_svg_map(output, world, width=400, height=200)
            self.assertTrue(output.parent.is_dir())
            root = _parse(output)
            rendered = _terrain_cells(root)
            self.assertEqual(len(rendered), 1)
            self.assertEqual(rendered[0].get("cx"), "166.67")
            self.assertEqual(rendered[0].get("cy"), "86.11")
            # radius is clamped to its 3.2 px maximum for a one-cell world.
            self.assertEqual(rendered[0].get("r"), "3.20")
            self.assertEqual(rendered[0].get("fill"), "#8d985c")
            self.assertEqual(rendered[0].get("stroke-width"), "0.08")
            self.assertEqual(rendered[0].get("opacity"), "0.96")
            self.assertIsNone(_contour_group(root))
            self.assertEqual(_all_lines(root), [])

    def test_all_water_world_paints_water_body_variants(self) -> None:
        cells = [
            _cell(0, 0.0, -60.0, is_water=True, water_depth_m=4200.0, biome="ocean"),
            _cell(
                1,
                0.0,
                -30.0,
                is_water=True,
                water_depth_m=120.0,
                water_body_type="continental_shelf",
            ),
            _cell(2, 0.0, 0.0, is_water=True, water_depth_m=400.0, water_body_type="inland_sea"),
            _cell(3, 0.0, 30.0, is_water=True, water_depth_m=400.0, reef_system_id=7),
            _cell(4, 0.0, 60.0, is_water=True, water_depth_m=400.0, reef_growth_index=0.9),
            _cell(5, 0.0, 90.0, is_water=True, water_depth_m=400.0, landform="fjord"),
        ]
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "water.svg"
            write_svg_map(output, _world(cells), width=400, height=200)
            root = _parse(output)
            rendered = _terrain_cells(root)
            self.assertEqual(len(rendered), 6)
            # No land at all: the contour pass produces no group.
            self.assertIsNone(_contour_group(root))
            for node in rendered:
                self.assertEqual(node.get("stroke-width"), "0.18")
                self.assertEqual(node.get("opacity"), "0.94")
            fills = [node.get("fill") for node in rendered]
            self.assertEqual(
                fills,
                ["#153f67", "#71bcc6", "#60abbe", "#75c4c6", "#80d8cc", "#68adc0"],
            )
            self.assertEqual(len(set(fills)), 6)
            # Only the fjord cell gets a contrasting outline.
            strokes = [node.get("stroke") for node in rendered]
            self.assertEqual(strokes[:5], fills[:5])
            self.assertEqual(strokes[5], "#82d0d2")

    def test_all_land_world_contour_levels_and_style_classes(self) -> None:
        cells = [
            _cell(0, 0.0, 0.0, elevation_m=900.0, neighbors=[1, 4]),
            _cell(1, 0.0, 2.0, elevation_m=1400.0, neighbors=[0, 2]),
            _cell(2, 0.0, 4.0, elevation_m=1400.0, neighbors=[1, 3]),
            _cell(3, 0.0, 6.0, elevation_m=2600.0, neighbors=[2]),
            # 500 m is not above the contour interval, so it never becomes a level,
            # and its edge with cell 0 crosses no level at all.
            _cell(4, 0.0, 8.0, elevation_m=500.0, neighbors=[0]),
        ]
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "land.svg"
            write_svg_map(
                output, _world(cells), width=400, height=200, contour_interval_m=500.0
            )
            root = _parse(output)
            self.assertEqual(len(_terrain_cells(root)), 5)
            group = _contour_group(root)
            self.assertIsNotNone(group)
            assert group is not None
            self.assertEqual(group.get("data-contour-interval-m"), "500")
            lines = _contour_lines(root)
            self.assertEqual(
                [(node.get("data-elevation-m"), node.get("class")) for node in lines],
                [
                    ("1000", "terrain-contour terrain-contour-major"),
                    ("1500", "terrain-contour terrain-contour-minor"),
                    ("2000", "terrain-contour terrain-contour-major"),
                    ("2500", "terrain-contour terrain-contour-minor"),
                ],
            )
            # The 1000 m contour belongs to the 0-1 edge, the rest to the 2-3 edge.
            self.assertEqual((lines[0].get("x1"), lines[0].get("x2")), ("200.00", "202.22"))
            self.assertEqual((lines[3].get("x1"), lines[3].get("x2")), ("204.44", "206.67"))

    def test_contour_edges_skip_water_flat_and_self_pairs(self) -> None:
        cells = [
            # land -> water neighbour: the 1000..2600 m span must not be contoured.
            _cell(0, 0.0, 0.0, elevation_m=1000.0, neighbors=[1]),
            # water -> land neighbour with a higher id: skipped from the water side.
            _cell(1, 0.0, 10.0, elevation_m=2600.0, is_water=True, neighbors=[2]),
            _cell(2, 0.0, 20.0, elevation_m=1000.0, neighbors=[]),
            # equal elevations on a level, plus a self-referencing neighbour id.
            _cell(3, 0.0, 30.0, elevation_m=1500.0, neighbors=[4, 3]),
            _cell(4, 0.0, 40.0, elevation_m=1500.0, neighbors=[3]),
        ]
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "guards.svg"
            write_svg_map(
                output, _world(cells), width=400, height=200, contour_interval_m=500.0
            )
            root = _parse(output)
            self.assertEqual(len(_terrain_cells(root)), 5)
            group = _contour_group(root)
            self.assertIsNotNone(group)
            assert group is not None
            self.assertEqual(len(group), 0)
            self.assertEqual(_all_lines(root), [])

            # Control: flipping only ``is_water`` on cell 1 makes both of its edges
            # contour, which proves the empty result above is the water guard and
            # not an inert world.
            wet = [dict(cell) for cell in cells]
            wet[1] = dict(wet[1], is_water=False)
            flipped = Path(tmpdir) / "guards_land.svg"
            write_svg_map(
                flipped, _world(wet), width=400, height=200, contour_interval_m=500.0
            )
            lines = _contour_lines(_parse(flipped))
            self.assertEqual(
                [(node.get("data-elevation-m"), node.get("x1"), node.get("x2")) for node in lines],
                [
                    ("1000", "200.00", "211.11"),
                    ("1500", "200.00", "211.11"),
                    ("2000", "200.00", "211.11"),
                    ("2500", "200.00", "211.11"),
                    ("1000", "211.11", "222.22"),
                    ("1500", "211.11", "222.22"),
                    ("2000", "211.11", "222.22"),
                    ("2500", "211.11", "222.22"),
                ],
            )

    def test_contours_only_link_pairs_that_are_both_rendered(self) -> None:
        cells = [
            _cell(0, 0.0, 0.0, elevation_m=1000.0, neighbors=[1]),
            _cell(1, 0.0, 10.0, elevation_m=2000.0, neighbors=[0, 2]),
            _cell(2, 0.0, 20.0, elevation_m=1000.0, neighbors=[1, 3]),
            _cell(3, 0.0, 30.0, elevation_m=2000.0, neighbors=[2]),
        ]
        with TemporaryDirectory() as tmpdir:
            full = Path(tmpdir) / "chain.svg"
            write_svg_map(
                full, _world(cells), width=400, height=200, contour_interval_m=500.0
            )
            lines = _contour_lines(_parse(full))
            # Each of the three chain edges crosses 1000/1500/2000 m exactly once,
            # and each pair is emitted once, from the lower id.
            self.assertEqual(
                [(node.get("data-elevation-m"), node.get("x1"), node.get("x2")) for node in lines],
                [
                    ("1000", "200.00", "211.11"),
                    ("1500", "200.00", "211.11"),
                    ("2000", "200.00", "211.11"),
                    ("1000", "211.11", "222.22"),
                    ("1500", "211.11", "222.22"),
                    ("2000", "211.11", "222.22"),
                    ("1000", "222.22", "233.33"),
                    ("1500", "222.22", "233.33"),
                    ("2000", "222.22", "233.33"),
                ],
            )

            thinned = Path(tmpdir) / "chain_thinned.svg"
            write_svg_map(
                thinned,
                _world(cells),
                width=400,
                height=200,
                max_cells=2,
                contour_interval_m=500.0,
            )
            root = _parse(thinned)
            # Stride 2 keeps cells 0 and 2, so every edge now has one endpoint that
            # was dropped: the group is emitted but stays empty.
            self.assertEqual(_points(_terrain_cells(root)), [("200.00", "100.00"), ("222.22", "100.00")])
            group = _contour_group(root)
            self.assertIsNotNone(group)
            assert group is not None
            self.assertEqual(len(group), 0)

    def test_relief_shading_uses_the_neighbour_mean(self) -> None:
        cells = [
            # relief = 2000 - mean(200, 400) = 1700 -> shade factor 1.0678.
            _cell(0, 0.0, 0.0, elevation_m=2000.0, neighbors=[1, 2]),
            _cell(1, 0.0, 20.0, elevation_m=200.0, neighbors=[0]),
            _cell(2, 0.0, 40.0, elevation_m=400.0, neighbors=[0]),
            # relief = 2000 - 200 = 1800 -> shade factor 1.08 (the clamp).
            _cell(3, 0.0, 60.0, elevation_m=2000.0, neighbors=[4]),
            # A basin: elevation below the neighbour mean floors relief at 0.
            _cell(4, 0.0, 80.0, elevation_m=200.0, neighbors=[3]),
        ]
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "relief.svg"
            write_svg_map(output, _world(cells), width=400, height=200, contours=False)
            fills = [node.get("fill") for node in _terrain_cells(_parse(output))]
            self.assertEqual(fills, ["#999e72", "#999b5f", "#94965b", "#9b9f74", "#999b5f"])
            # Mean-vs-min matters: cell 0 would take cell 3's brighter fill if the
            # relief used the lowest neighbour instead of the average.
            self.assertNotEqual(fills[0], fills[3])
            # The basin cell is shaded exactly like the flat 200 m cell, so relief
            # is floored at zero rather than taken as an absolute difference.
            self.assertEqual(fills[4], fills[1])

    def test_aridity_branches_repaint_land_fills(self) -> None:
        # Potential evapotranspiration is (temperature_c + 8) * 31, so at 15 C the
        # aridity index is precipitation / 713.
        cells = [
            _cell(0, 0.0, 0.0, elevation_m=600.0, biome="hot_desert", precipitation_mm_y=300.0),
            _cell(1, 0.0, 20.0, elevation_m=600.0, biome="hot_desert", precipitation_mm_y=340.0),
            _cell(2, 0.0, 40.0, elevation_m=600.0, biome="hot_desert", precipitation_mm_y=850.0),
            _cell(3, 0.0, 60.0, elevation_m=600.0, biome="hot_desert", precipitation_mm_y=800.0),
            _cell(
                4,
                0.0,
                80.0,
                elevation_m=600.0,
                biome="hot_desert",
                precipitation_mm_y=2600.0,
                temperature_c=5.0,
            ),
        ]
        # The four warm cells bracket both cuts from each side, so neither the
        # thresholds nor the +8 C offset in the PET term can move without a fill
        # changing.
        self.assertAlmostEqual(300.0 / 713.0, 0.4208, places=4)  # below the 0.45 cut
        self.assertAlmostEqual(340.0 / 713.0, 0.4769, places=4)  # just above it
        self.assertAlmostEqual(850.0 / 713.0, 1.1921, places=4)  # just above the 1.15 cut
        self.assertAlmostEqual(800.0 / 713.0, 1.1220, places=4)  # just below it
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "aridity.svg"
            write_svg_map(output, _world(cells), width=400, height=200, contours=False)
            fills = [node.get("fill") for node in _terrain_cells(_parse(output))]
            self.assertEqual(
                fills, ["#b09b63", "#aa955f", "#8b8a59", "#aa955f", "#aa955f"]
            )
            # The wet blend also needs warmth: the 6.45-aridity cell at 5 C keeps
            # the untouched fill of the in-between cells.
            self.assertEqual(fills[4], fills[3])
            self.assertEqual(fills[1], fills[3])

    def test_terrain_style_classes_by_landform_and_river_flag(self) -> None:
        cells = [
            _cell(0, 0.0, 0.0),
            _cell(1, 0.0, 2.0, is_river=True),
            _cell(2, 0.0, 4.0, elevation_m=1000.0),
            _cell(3, 0.0, 6.0, landform="delta"),
            _cell(4, 0.0, 8.0, landform="mountain_belt", elevation_m=3100.0),
            _cell(5, 0.0, 10.0, landform="salt_flat"),
            _cell(6, 0.0, 12.0, landform="moraine"),
            _cell(7, 0.0, 14.0, biome="ice_cap"),
            # The white blend has a second trigger: > 80 m of ice on any biome.
            _cell(8, 0.0, 16.0, ice_thickness_m=400.0),
        ]
        expected = [
            ("0.08", "0.96"),
            ("0.42", "0.98"),
            ("0.36", "0.97"),
            ("0.30", "0.97"),
            ("0.08", "0.96"),
            ("0.08", "0.96"),
            ("0.30", "0.97"),
            ("0.08", "0.96"),
            ("0.08", "0.96"),
        ]
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "styles.svg"
            write_svg_map(output, _world(cells), width=400, height=200, contours=False)
            rendered = _terrain_cells(_parse(output))
            self.assertEqual(
                [(node.get("stroke-width"), node.get("opacity")) for node in rendered], expected
            )
            fills = [node.get("fill") for node in rendered]
            self.assertEqual(
                fills,
                [
                    "#96985d",
                    "#96985d",
                    "#848653",
                    "#7e956a",
                    "#808560",
                    "#b7b591",
                    "#898a67",
                    "#cecec2",
                    "#c5c7b4",
                ],
            )
            # The river flag changes only the outline, never the fill.
            self.assertEqual(fills[0], fills[1])
            self.assertEqual(rendered[1].get("stroke"), "#9bd3df")
            self.assertNotEqual(rendered[0].get("stroke"), "#9bd3df")
            # Every landform variant repaints the base grassland fill, and the two
            # ice triggers land on different whites because the biome differs.
            self.assertEqual(len(set(fills)), 8)
            self.assertNotEqual(fills[7], fills[8])

    def test_cells_without_an_id_are_drawn_but_skipped_by_relief_and_contours(self) -> None:
        cells = [
            _cell(0, 0.0, 0.0, elevation_m=1000.0, neighbors=[1]),
            _cell(1, 0.0, 2.0, elevation_m=2000.0, neighbors=[0]),
            _cell(None, 0.0, 4.0, elevation_m=1800.0, neighbors=[0, 1]),
        ]
        world = _world(
            cells,
            # -1 is the sentinel a missing ``cell_id`` falls back to; it must not
            # resolve to the id-less cell.
            settlements=[{"id": 0, "cell_id": -1, "type": "port", "score": 0.5}],
            ruins=[{"type": "nameless", "significance": 0.5}],
        )
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "no_id.svg"
            write_svg_map(
                output, world, width=400, height=200, labels=True, contour_interval_m=500.0
            )
            root = _parse(output)
            rendered = _terrain_cells(root)
            self.assertEqual(len(rendered), 3)
            self.assertEqual(_points(rendered)[2], ("204.44", "100.00"))
            self.assertEqual(_settlement_circles(root), [])
            self.assertEqual(list(root.iter(SVG + "text")), [])
            self.assertEqual(
                [node for node in root.iter(SVG + "rect") if node.get("fill") == "#8b6d5c"], []
            )
            # Only the 0-1 edge contributes contours; the id-less cell is skipped.
            lines = _contour_lines(root)
            self.assertEqual(
                [node.get("data-elevation-m") for node in lines], ["1000", "1500", "2000"]
            )
            for node in lines:
                self.assertEqual((node.get("x1"), node.get("x2")), ("200.00", "202.22"))


class SvgOverlayTests(TestCase):
    """Settlement, route, sacred-area and ruin overlays."""

    def _overlay_world(self, *, cell_id: int) -> dict[str, object]:
        cells = [
            _cell(0, 0.0, 0.0, elevation_m=1000.0),
            _cell(1, 0.0, 20.0, elevation_m=1000.0),
        ]
        return _world(
            cells,
            settlements=[
                {"id": 0, "cell_id": cell_id, "type": "port", "score": 0.5},
                {"id": 1, "cell_id": cell_id, "type": "mining_town", "score": 0.25},
            ],
            routes=[{"from": 0, "to": 1, "type": "coastal_sea"}],
            sacred_areas=[{"cell_id": cell_id, "type": "sky burial <site>", "significance": 0.5}],
            ruins=[{"cell_id": cell_id, "type": "sunken hall", "significance": 0.5}],
        )

    def test_overlays_render_for_resolvable_cells(self) -> None:
        world = self._overlay_world(cell_id=0)
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "overlays.svg"
            write_svg_map(
                output, world, width=400, height=200, labels=True, contours=False
            )
            root = _parse(output)
            polygons = list(root.iter(SVG + "polygon"))
            self.assertEqual(len(polygons), 1)
            self.assertEqual(polygons[0].get("fill"), "#fff0a6")
            self.assertEqual(polygons[0].findtext(SVG + "title"), "sky burial <site>")
            # Half-size 4.0 + 3.0 * significance = 5.5 about the cell at (200, 100).
            self.assertEqual(
                polygons[0].get("points"), "200.00,94.50 194.50,105.50 205.50,105.50"
            )
            rects = [node for node in root.iter(SVG + "rect") if node.get("fill") == "#8b6d5c"]
            self.assertEqual(len(rects), 1)
            self.assertEqual(rects[0].findtext(SVG + "title"), "sunken hall")
            # Side 3.6 + 2.8 * significance = 5.0, centred on the same cell.
            self.assertEqual(
                (
                    rects[0].get("x"),
                    rects[0].get("y"),
                    rects[0].get("width"),
                    rects[0].get("height"),
                    rects[0].get("transform"),
                ),
                ("197.50", "97.50", "5.00", "5.00", "rotate(45 200.00 100.00)"),
            )
            self.assertEqual(len(_settlement_circles(root)), 2)
            self.assertEqual(
                [node.get("fill") for node in _settlement_circles(root)],
                ["#f6c65b", "#d98559"],
            )
            # Marker radius 2.7 + 4.2 * score.
            self.assertEqual(
                [node.get("r") for node in _settlement_circles(root)], ["4.80", "3.75"]
            )
            self.assertEqual([node.text for node in root.iter(SVG + "text")], ["Port 0", "Mining Town 1"])
            # Labels are offset by (+7, -7) from their cell.
            self.assertEqual(
                [(node.get("x"), node.get("y")) for node in root.iter(SVG + "text")],
                [("207.00", "93.00"), ("207.00", "93.00")],
            )
            routes = [node for node in _all_lines(root) if node.get("stroke") == "#9bd3df"]
            self.assertEqual(len(routes), 1)
            self.assertEqual(
                (routes[0].get("x1"), routes[0].get("x2")), ("200.00", "200.00")
            )

    def test_markup_from_world_text_is_escaped_and_trimmed(self) -> None:
        """Every string that reaches the SVG comes from world data, so the document
        has to stay well-formed for names carrying ``&`` or angle brackets."""
        world = _world(
            [_cell(0, 0.0, 0.0)],
            name="Tierra & <probe>",
            settlements=[
                {"id": "A&B", "cell_id": 0, "type": "river_city", "score": 0.9},
                {"cell_id": 0, "type": "port", "score": 0.5},  # no id key at all
            ],
            ruins=[{"cell_id": 0, "type": "hall of <bones> & dust", "significance": 0.5}],
            sacred_areas=[{"cell_id": 0, "type": "grove of R&R", "significance": 0.2}],
        )
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "escaped.svg"
            write_svg_map(output, world, width=400, height=200, labels=True, contours=False)
            # _parse would raise ParseError on any unescaped marker.
            root = _parse(output)
            self.assertEqual(
                root.findtext(SVG + "title"),
                "Tierra & <probe> equirectangular causal terrain map",
            )
            # The id-less settlement label has no trailing space.
            self.assertEqual(
                [node.text for node in root.iter(SVG + "text")], ["River City A&B", "Port"]
            )
            rects = [node for node in root.iter(SVG + "rect") if node.get("fill") == "#8b6d5c"]
            self.assertEqual(len(rects), 1)
            self.assertEqual(rects[0].findtext(SVG + "title"), "hall of <bones> & dust")
            polygons = list(root.iter(SVG + "polygon"))
            self.assertEqual(len(polygons), 1)
            self.assertEqual(polygons[0].findtext(SVG + "title"), "grove of R&R")

    def test_overlays_pointing_at_unknown_cells_are_dropped(self) -> None:
        world = self._overlay_world(cell_id=999)
        world["routes"] = [
            {"from": 0, "to": 1, "type": "coastal_sea"},  # settlements resolve, cells do not
            {"from": 9, "to": 0, "type": "land"},  # settlement index out of range
            {"from": 0, "to": -3, "type": "land"},
        ]
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "dangling.svg"
            write_svg_map(
                output, world, width=400, height=200, labels=True, contours=False
            )
            root = _parse(output)
            self.assertEqual(list(root.iter(SVG + "polygon")), [])
            self.assertEqual(
                [node for node in root.iter(SVG + "rect") if node.get("fill") == "#8b6d5c"], []
            )
            self.assertEqual(_settlement_circles(root), [])
            self.assertEqual(list(root.iter(SVG + "text")), [])
            self.assertEqual(_all_lines(root), [])
            # The terrain itself is unaffected.
            self.assertEqual(len(_terrain_cells(root)), 2)

    def test_orthographic_drops_far_side_cells_and_overlays(self) -> None:
        cells = [
            _cell(0, 0.0, 0.0, elevation_m=1000.0, neighbors=[1]),
            _cell(1, 0.0, 179.0, elevation_m=2600.0, neighbors=[0]),
        ]
        world = _world(
            cells,
            settlements=[
                {"id": 0, "cell_id": 1, "type": "port", "score": 0.9},
                {"id": 1, "cell_id": 0, "type": "oasis", "score": 0.4},
            ],
            routes=[{"from": 0, "to": 1, "type": "land"}],
            sacred_areas=[{"cell_id": 1, "type": "hidden shrine", "significance": 1.0}],
            ruins=[{"cell_id": 1, "type": "far tower", "significance": 1.0}],
        )
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "ortho_overlays.svg"
            write_svg_map(
                output,
                world,
                width=400,
                height=200,
                projection="orthographic",
                labels=True,
                contour_interval_m=500.0,
            )
            root = _parse(output)
            self.assertEqual(_points(_terrain_cells(root)), [("200.00", "100.00")])
            # Both cells feed the contour level list, but no edge can be drawn.
            group = _contour_group(root)
            self.assertIsNotNone(group)
            assert group is not None
            self.assertEqual(len(group), 0)
            self.assertEqual(_contour_lines(root), [])
            self.assertEqual(_all_lines(root), [])
            self.assertEqual(list(root.iter(SVG + "polygon")), [])
            self.assertEqual(
                [node for node in root.iter(SVG + "rect") if node.get("fill") == "#8b6d5c"], []
            )
            self.assertEqual(_points(_settlement_circles(root)), [("200.00", "100.00")])
            self.assertEqual([node.text for node in root.iter(SVG + "text")], ["Oasis 1"])

    def test_equirectangular_suppresses_antimeridian_spans(self) -> None:
        cells = [
            _cell(0, 0.0, -179.0, elevation_m=1000.0, neighbors=[1]),
            _cell(1, 0.0, 179.0, elevation_m=2600.0, neighbors=[0]),
        ]
        world = _world(
            cells,
            settlements=[
                {"id": 0, "cell_id": 0, "type": "port", "score": 0.5},
                {"id": 1, "cell_id": 1, "type": "port", "score": 0.5},
            ],
            routes=[{"from": 0, "to": 1, "type": "land"}],
        )
        with TemporaryDirectory() as tmpdir:
            wrapped = Path(tmpdir) / "wrapped.svg"
            write_svg_map(
                wrapped, world, width=400, height=200, contour_interval_m=500.0
            )
            root = _parse(wrapped)
            self.assertEqual(len(_terrain_cells(root)), 2)
            group = _contour_group(root)
            self.assertIsNotNone(group)
            assert group is not None
            self.assertEqual(len(group), 0)
            self.assertEqual(_all_lines(root), [])

            # Mollweide has no antimeridian guard, so the same edges are drawn.
            unwrapped = Path(tmpdir) / "unwrapped.svg"
            write_svg_map(
                unwrapped,
                world,
                width=400,
                height=200,
                projection="mollweide",
                contour_interval_m=500.0,
            )
            other = _parse(unwrapped)
            self.assertEqual(
                [node.get("data-elevation-m") for node in _contour_lines(other)],
                ["1000", "1500", "2000", "2500"],
            )
            self.assertEqual(
                len([node for node in _all_lines(other) if node.get("stroke") == "#f0d38a"]), 1
            )


class RasterMapTests(TestCase):
    """``write_raster_map`` header, backdrop and pixel content."""

    def test_header_and_payload_size_for_every_projection(self) -> None:
        world = worlds.cached_world_readonly("small_smoke")
        with TemporaryDirectory() as tmpdir:
            for projection in ("equirectangular", "mollweide", "orthographic"):
                for texture in (True, False):
                    with self.subTest(projection=projection, texture=texture):
                        output = Path(tmpdir) / f"{projection}_{texture}.ppm"
                        write_raster_map(
                            output,
                            world,
                            width=64,
                            height=32,
                            projection=projection,
                            max_cells=80,
                            texture=texture,
                        )
                        comment, width, height, body = _read_ppm(output)
                        self.assertEqual(
                            comment,
                            (
                                "# magic-geo raster-terrain-v1 "
                                f"projection={projection} texture={str(texture).lower()}"
                            ).encode(),
                        )
                        self.assertEqual((width, height), (64, 32))
                        self.assertEqual(len(body), 64 * 32 * 3)

    def test_orthographic_backdrop_separates_globe_from_space(self) -> None:
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "space.ppm"
            write_raster_map(
                output, _world([]), width=64, height=32, projection="orthographic"
            )
            _, width, _, body = _read_ppm(output)
            # radius = min(64, 32) * 0.47 = 15.04 px about (32.0, 16.0)
            self.assertEqual(_pixel(body, width, 0, 0), SPACE_RGB)
            self.assertEqual(_pixel(body, width, 63, 31), SPACE_RGB)
            self.assertEqual(_pixel(body, width, 32, 16), BACKDROP_RGB)
            self.assertEqual(_pixel(body, width, 46, 16), BACKDROP_RGB)
            self.assertEqual(_pixel(body, width, 48, 16), SPACE_RGB)
            space_pixels = sum(
                1
                for index in range(0, len(body), 3)
                if (body[index], body[index + 1], body[index + 2]) == SPACE_RGB
            )
            # 64 * 32 pixels minus the ~pi * 15.04 ** 2 = 711 px globe disc.
            self.assertEqual(space_pixels, 1332)
            self.assertEqual(len(body) // 3 - space_pixels, 716)

    def test_equirectangular_single_cell_disc(self) -> None:
        world = _world([_cell(0, 0.0, 0.0, elevation_m=60.0)])
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "single.ppm"
            write_raster_map(output, world, width=80, height=40, texture=False)
            _, width, _, body = _read_ppm(output)
            # radius clamps to 18 px about (40.0, 20.0); corners stay background.
            self.assertEqual(_pixel(body, width, 40, 20), (159, 172, 106))
            self.assertEqual(_pixel(body, width, 0, 0), BACKDROP_RGB)
            self.assertEqual(_pixel(body, width, 79, 39), BACKDROP_RGB)
            # The disc edge falls between y=1 and y=2 on the central column.
            self.assertEqual(_pixel(body, width, 40, 1), BACKDROP_RGB)
            self.assertEqual(_pixel(body, width, 40, 2), (121, 140, 100))

    def test_mollweide_raster_collapses_the_pole_onto_the_central_meridian(self) -> None:
        cells = [_cell(0, 90.0, 90.0), _cell(1, 0.0, 90.0)]
        world = _world(cells)
        with TemporaryDirectory() as tmpdir:
            mollweide = Path(tmpdir) / "mollweide.ppm"
            equirectangular = Path(tmpdir) / "equirectangular.ppm"
            write_raster_map(
                mollweide, world, width=144, height=72, projection="mollweide", texture=False
            )
            write_raster_map(equirectangular, world, width=144, height=72, texture=False)
            _, width, _, mollweide_body = _read_ppm(mollweide)
            _, _, _, equirectangular_body = _read_ppm(equirectangular)
            # The 18 px discs sit 36 px apart, so each anchor is unambiguous.
            self.assertNotEqual(_pixel(mollweide_body, width, 72, 0), BACKDROP_RGB)
            self.assertEqual(_pixel(mollweide_body, width, 108, 0), BACKDROP_RGB)
            self.assertNotEqual(_pixel(equirectangular_body, width, 108, 0), BACKDROP_RGB)
            self.assertEqual(_pixel(equirectangular_body, width, 72, 0), BACKDROP_RGB)
            # Both projections keep the equatorial cell at lon 90 in the same place.
            self.assertNotEqual(_pixel(mollweide_body, width, 108, 36), BACKDROP_RGB)
            self.assertNotEqual(_pixel(equirectangular_body, width, 108, 36), BACKDROP_RGB)

    def test_elevation_ramp_and_water_bodies_use_distinct_colours(self) -> None:
        cells = [
            _cell(0, 0.0, -135.0, elevation_m=60.0),
            _cell(1, 0.0, -45.0, elevation_m=500.0),
            _cell(2, 0.0, 45.0, elevation_m=1400.0),
            _cell(3, 0.0, 135.0, elevation_m=3000.0),
            # Depths span the 0..4200 m ramp so the depth term is observable and
            # not saturated at either end.
            _cell(4, 45.0, -135.0, is_water=True, water_depth_m=4200.0),
            _cell(
                5,
                45.0,
                -45.0,
                is_water=True,
                water_depth_m=120.0,
                water_body_type="continental_shelf",
            ),
            _cell(
                6, 45.0, 45.0, is_water=True, water_depth_m=400.0, water_body_type="inland_sea"
            ),
            _cell(
                7, 45.0, 135.0, is_water=True, water_depth_m=60.0, water_body_type="fresh_lake"
            ),
            _cell(8, -45.0, -135.0, is_water=True, water_depth_m=30.0, reef_system_id=2),
            _cell(9, -45.0, -45.0, is_water=True, water_depth_m=30.0, reef_growth_index=0.8),
            # No "id" key at all: still drawn, but skipped by the relief pass.
            _cell(None, -45.0, 45.0, elevation_m=2200.0),
        ]
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "palette.ppm"
            write_raster_map(output, _world(cells), width=72, height=36, texture=False)
            _, width, _, body = _read_ppm(output)
            samples = [
                _pixel(body, width, 9, 18),
                _pixel(body, width, 27, 18),
                _pixel(body, width, 45, 18),
                _pixel(body, width, 63, 18),
                _pixel(body, width, 9, 9),
                _pixel(body, width, 27, 9),
                _pixel(body, width, 45, 9),
                _pixel(body, width, 63, 9),
                _pixel(body, width, 9, 27),
                _pixel(body, width, 27, 27),
                _pixel(body, width, 45, 27),
            ]
            # Each probe is the centre pixel of its own 7.37 px disc, composited
            # over the (23, 59, 86) backdrop at alpha 0.96 * (0.70 + 0.30 * edge)
            # = 0.9573. The colours below were recomputed from the documented
            # palette anchors and blend weights (see the module docstring) rather
            # than read back off a rendering.
            self.assertEqual(
                samples,
                [
                    (159, 172, 106),  # 60 m: grassland over the low elevation ramp
                    (163, 165, 103),  # 500 m
                    (144, 147, 97),  # 1400 m
                    (169, 176, 130),  # 3000 m, ramping to the snow tint
                    (20, 60, 98),  # 4200 m deep ocean, full depth blend
                    (104, 176, 186),  # 120 m continental shelf
                    (89, 159, 178),  # 400 m inland sea
                    (101, 171, 188),  # 60 m fresh lake
                    (113, 189, 190),  # 30 m reef by system id
                    (121, 203, 193),  # 30 m reef by growth index 0.8
                    (146, 152, 109),  # 2200 m, id-less so relief never applies
                ],
            )
            self.assertEqual(len(set(samples)), 11)
            # Deep ocean is darker than the shelf; the reef tints toward green.
            self.assertLess(samples[4][2], samples[5][2])
            self.assertGreater(samples[8][1], samples[4][1])

    def test_raster_land_modifier_pixels_are_exact(self) -> None:
        """Every climate/landform branch of the raster land palette, on the same
        11-slot grid as the ramp test so each probe is its own disc centre."""
        cells = [
            # aridity 300 / 713 = 0.42 -> the dry blend.
            _cell(0, 0.0, -135.0, elevation_m=600.0, biome="hot_desert", precipitation_mm_y=300.0),
            # aridity 850 / 713 = 1.19 at 15 C -> just past the humid cut.
            _cell(
                1,
                0.0,
                -45.0,
                elevation_m=600.0,
                biome="tropical_rainforest",
                precipitation_mm_y=850.0,
            ),
            # aridity 6.45 but only 5 C, so neither blend applies.
            _cell(
                2, 0.0, 45.0, elevation_m=600.0, precipitation_mm_y=2600.0, temperature_c=5.0
            ),
            # sediment 6 / 8 = 0.75 -> sediment blend, then the delta wash.
            _cell(3, 0.0, 135.0, elevation_m=600.0, landform="delta", sediment_thickness_m=6.0),
            # sediment 0.5 / 8 = 0.06 is below the 0.10 cut: floodplain wash only.
            _cell(
                4,
                45.0,
                -135.0,
                elevation_m=600.0,
                landform="floodplain",
                sediment_thickness_m=0.5,
            ),
            # alluvial fans take the sediment blend but not the wash.
            _cell(
                5,
                45.0,
                -45.0,
                elevation_m=600.0,
                landform="alluvial_fan",
                sediment_thickness_m=6.0,
            ),
            _cell(6, 45.0, 45.0, elevation_m=600.0, biome="ice_cap"),
            _cell(7, 45.0, 135.0, elevation_m=600.0, ice_thickness_m=400.0),
            _cell(8, -45.0, -135.0, elevation_m=2400.0, landform="mountain_belt"),
            _cell(9, -45.0, -45.0, elevation_m=600.0, landform="salt_flat"),
            _cell(10, -45.0, 45.0, elevation_m=600.0, landform="moraine"),
        ]
        probes = [
            (9, 18),
            (27, 18),
            (45, 18),
            (63, 18),
            (9, 9),
            (27, 9),
            (45, 9),
            (63, 9),
            (9, 27),
            (27, 27),
            (45, 27),
        ]
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "modifiers.ppm"
            write_raster_map(output, _world(cells), width=72, height=36, texture=False)
            _, width, _, body = _read_ppm(output)
            samples = [_pixel(body, width, x, y) for x, y in probes]
            self.assertEqual(
                samples,
                [
                    (197, 175, 114),  # dry blend over hot desert
                    (81, 125, 82),  # humid blend over rainforest
                    (160, 161, 101),  # cold and wet: untouched grassland
                    (128, 160, 119),  # sediment blend + delta wash
                    (138, 161, 118),  # floodplain wash without the sediment blend
                    (144, 159, 102),  # sediment blend without a wash
                    (228, 229, 218),  # ice-cap biome
                    (218, 221, 202),  # 400 m of ice over grassland
                    (124, 131, 94),  # mountain belt, shaded to 0.82
                    (201, 200, 164),  # salt flat
                    (148, 152, 117),  # moraine
                ],
            )
            # The ice-cap biome and a thick ice sheet reach the same white blend
            # from different fields, but the underlying biome still shows through.
            self.assertNotEqual(samples[6], samples[7])
            # A mountain belt is darker than the plain it is cut from.
            self.assertLess(samples[8][0], samples[2][0])

    def test_texture_only_perturbs_land_pixels(self) -> None:
        cells = [
            _cell(0, 0.0, -60.0, elevation_m=1200.0, neighbors=[1], erosion_rate=9.0),
            _cell(1, 0.0, 60.0, is_water=True, water_depth_m=1000.0, neighbors=[0]),
        ]
        world = _world(cells)
        with TemporaryDirectory() as tmpdir:
            textured = Path(tmpdir) / "textured.ppm"
            flat = Path(tmpdir) / "flat.ppm"
            write_raster_map(textured, world, width=72, height=36, texture=True)
            write_raster_map(flat, world, width=72, height=36, texture=False)
            _, width, _, textured_body = _read_ppm(textured)
            _, _, _, flat_body = _read_ppm(flat)
            self.assertNotEqual(textured_body, flat_body)
            land = (24, 18)
            water = (48, 18)
            self.assertNotEqual(
                _pixel(textured_body, width, *land), _pixel(flat_body, width, *land)
            )
            self.assertEqual(
                _pixel(textured_body, width, *water), _pixel(flat_body, width, *water)
            )

    def test_texture_shade_tracks_relief_erosion_and_cell_id(self) -> None:
        """The textured shade factor is 0.88 + 0.20 * relief/1800 + 0.08 *
        erosion/18 + 0.10 * (noise - 0.5); the pixels below lock all three terms
        (the noise term is a deterministic function of the cell id)."""
        pair = [
            _cell(0, 0.0, -90.0, elevation_m=1200.0, neighbors=[1]),
            _cell(1, 0.0, 90.0, elevation_m=1200.0, neighbors=[0]),
        ]
        with TemporaryDirectory() as tmpdir:
            dry = Path(tmpdir) / "erosion_0.ppm"
            eroded = Path(tmpdir) / "erosion_18.ppm"
            write_raster_map(dry, _world(pair), width=72, height=36, texture=True)
            write_raster_map(
                eroded,
                _world([dict(pair[0], erosion_rate=18.0), pair[1]]),
                width=72,
                height=36,
                texture=True,
            )
            _, width, _, dry_body = _read_ppm(dry)
            _, _, _, eroded_body = _read_ppm(eroded)
            self.assertEqual(_pixel(dry_body, width, 18, 18), (124, 127, 82))
            self.assertEqual(_pixel(eroded_body, width, 18, 18), (135, 139, 90))
            # Erosion only brightens the cell it is set on.
            self.assertEqual(
                _pixel(dry_body, width, 54, 18), _pixel(eroded_body, width, 54, 18)
            )
            # Cell 1 carries identical fields and differs only by id, so the noise
            # term alone separates the two discs.
            self.assertEqual(_pixel(dry_body, width, 54, 18), (125, 128, 83))

            # Relief is the drop to the neighbour mean, not to the lowest neighbour.
            lowered = Path(tmpdir) / "relief_1200.ppm"
            write_raster_map(
                lowered,
                _world([pair[0], dict(pair[1], elevation_m=0.0)]),
                width=72,
                height=36,
                texture=True,
            )
            _, _, _, lowered_body = _read_ppm(lowered)
            self.assertEqual(_pixel(lowered_body, width, 18, 18), (143, 146, 95))

            averaged = Path(tmpdir) / "relief_600.ppm"
            write_raster_map(
                averaged,
                _world(
                    [
                        dict(pair[0], neighbors=[1, 2]),
                        dict(pair[1], elevation_m=0.0),
                        _cell(2, 0.0, 150.0, elevation_m=1200.0),
                    ]
                ),
                width=72,
                height=36,
                texture=True,
            )
            _, _, _, averaged_body = _read_ppm(averaged)
            # mean(0, 1200) = 600 -> relief 600. Taking the lowest neighbour would
            # give relief 1200 and the pixel (143, 146, 95) instead.
            self.assertEqual(_pixel(averaged_body, width, 18, 18), (133, 137, 89))

    def test_max_cells_limits_the_discs_that_are_drawn(self) -> None:
        cells = [
            _cell(0, 0.0, -135.0),
            _cell(1, 0.0, -45.0),
            _cell(2, 0.0, 45.0),
            _cell(3, 0.0, 135.0),
        ]
        world = _world(cells)
        with TemporaryDirectory() as tmpdir:
            thinned = Path(tmpdir) / "thinned.ppm"
            full = Path(tmpdir) / "full.ppm"
            paired = Path(tmpdir) / "paired.ppm"
            write_raster_map(thinned, world, width=72, height=36, max_cells=1, texture=False)
            write_raster_map(paired, world, width=72, height=36, max_cells=2, texture=False)
            write_raster_map(full, world, width=72, height=36, texture=False)
            _, width, _, thinned_body = _read_ppm(thinned)
            _, _, _, paired_body = _read_ppm(paired)
            _, _, _, full_body = _read_ppm(full)
            self.assertNotEqual(_pixel(thinned_body, width, 9, 18), BACKDROP_RGB)
            for x in (27, 45, 63):
                with self.subTest(x=x):
                    self.assertEqual(_pixel(thinned_body, width, x, 18), BACKDROP_RGB)
                    self.assertNotEqual(_pixel(full_body, width, x, 18), BACKDROP_RGB)
            # max_cells=2 of 4 keeps cells[::2] -- the first and third cell, not the
            # first two.
            for x, kept in ((9, True), (27, False), (45, True), (63, False)):
                with self.subTest(max_cells=2, x=x):
                    self.assertEqual(
                        _pixel(paired_body, width, x, 18) != BACKDROP_RGB, kept
                    )

    def test_raster_overlays_pointing_at_unknown_cells_are_dropped(self) -> None:
        cells = [_cell(0, 0.0, -60.0), _cell(1, 0.0, 60.0)]
        bare = _world(cells)
        dangling = _world(
            cells,
            settlements=[
                {"id": 0, "cell_id": 404, "type": "port", "score": 0.9},
                {"id": 1, "cell_id": 405, "type": "port", "score": 0.9},
            ],
            routes=[
                {"from": 0, "to": 1, "type": "land"},
                {"from": 12, "to": 0, "type": "land"},
                {"from": 0, "to": -2, "type": "land"},
            ],
        )
        with TemporaryDirectory() as tmpdir:
            bare_path = Path(tmpdir) / "bare.ppm"
            dangling_path = Path(tmpdir) / "dangling.ppm"
            write_raster_map(bare_path, bare, width=72, height=36, texture=False)
            write_raster_map(dangling_path, dangling, width=72, height=36, texture=False)
            self.assertEqual(bare_path.read_bytes(), dangling_path.read_bytes())

    def test_raster_far_side_and_antimeridian_overlays_are_dropped(self) -> None:
        cells = [_cell(0, 0.0, -179.0), _cell(1, 0.0, 179.0)]
        settlements = [
            {"id": 0, "cell_id": 0, "type": "port", "score": 0.9},
            {"id": 1, "cell_id": 1, "type": "port", "score": 0.9},
        ]
        routed = _world(cells, settlements=settlements, routes=[{"from": 0, "to": 1}])
        unrouted = _world(cells, settlements=settlements)
        with TemporaryDirectory() as tmpdir:
            wrapped = Path(tmpdir) / "wrapped.ppm"
            plain = Path(tmpdir) / "plain.ppm"
            write_raster_map(wrapped, routed, width=72, height=36, texture=False)
            write_raster_map(plain, unrouted, width=72, height=36, texture=False)
            # The route spans the antimeridian and is skipped entirely.
            self.assertEqual(wrapped.read_bytes(), plain.read_bytes())

            # A negative endpoint index must be rejected outright rather than
            # wrapping around to the last settlement: these two cells are 120 deg
            # apart, so a route between them would be drawn if -1 resolved.
            near = [_cell(0, 0.0, -60.0), _cell(1, 0.0, 60.0)]
            negative = Path(tmpdir) / "negative.ppm"
            bare = Path(tmpdir) / "bare.ppm"
            write_raster_map(
                negative,
                _world(near, settlements=settlements, routes=[{"from": 0, "to": -1}]),
                width=72,
                height=36,
                texture=False,
            )
            write_raster_map(
                bare, _world(near, settlements=settlements), width=72, height=36, texture=False
            )
            self.assertEqual(negative.read_bytes(), bare.read_bytes())
            # Control: the same pair with a valid index does draw a route.
            drawn = Path(tmpdir) / "drawn.ppm"
            write_raster_map(
                drawn,
                _world(near, settlements=settlements, routes=[{"from": 0, "to": 1}]),
                width=72,
                height=36,
                texture=False,
            )
            self.assertNotEqual(drawn.read_bytes(), bare.read_bytes())

            hidden = Path(tmpdir) / "hidden.ppm"
            empty = Path(tmpdir) / "empty.ppm"
            write_raster_map(
                hidden,
                routed,
                width=64,
                height=32,
                projection="orthographic",
                texture=False,
            )
            write_raster_map(
                empty,
                _world([]),
                width=64,
                height=32,
                projection="orthographic",
                texture=False,
            )
            # Both cells sit on the far hemisphere, so nothing at all is drawn.
            self.assertEqual(hidden.read_bytes(), empty.read_bytes())

    def test_raster_draws_settlement_and_route_markers(self) -> None:
        cells = [_cell(0, 0.0, -60.0), _cell(1, 0.0, 60.0)]
        world = _world(
            cells,
            settlements=[
                {"id": 0, "cell_id": 0, "type": "port", "score": 1.0},
                {"id": 1, "cell_id": 1, "type": "port", "score": 1.0},
            ],
            routes=[{"from": 0, "to": 1, "type": "land"}],
        )
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "markers.ppm"
            write_raster_map(output, world, width=72, height=36, texture=False)
            _, width, _, body = _read_ppm(output)
            # Settlement cores at lon -60/+60 land on x=24 and x=48.
            self.assertEqual(_pixel(body, width, 24, 18), (232, 212, 152))
            self.assertEqual(_pixel(body, width, 48, 18), (232, 212, 152))
            # The route runs along the equator between them.
            self.assertEqual(_pixel(body, width, 36, 18), (240, 211, 138))
            self.assertEqual(_pixel(body, width, 36, 17), (240, 211, 138))
            # ...and it is a hairline: the route disc radius is max(0.8, 17.28 *
            # 0.17) = 2.94, so three rows out is untouched terrain.
            plain = Path(tmpdir) / "plain.ppm"
            write_raster_map(
                plain,
                _world(cells, settlements=world["settlements"]),
                width=72,
                height=36,
                texture=False,
            )
            _, _, _, plain_body = _read_ppm(plain)
            for dy in (3, 4):
                with self.subTest(dy=dy):
                    self.assertEqual(
                        _pixel(body, width, 36, 18 + dy),
                        _pixel(plain_body, width, 36, 18 + dy),
                    )
            self.assertNotEqual(
                _pixel(body, width, 36, 20), _pixel(plain_body, width, 36, 20)
            )

    def test_raster_settlement_marker_grows_with_score(self) -> None:
        # A lone cell on a 36x18 canvas gets a 12.2188 px disc, so the marker
        # half-size 12.2188 * (0.28 + 0.50 * score) stays below the 8 px cap and
        # the score term is observable.
        world = _world([_cell(0, 0.0, 0.0)])
        footprints: dict[float, int] = {}
        with TemporaryDirectory() as tmpdir:
            plain = Path(tmpdir) / "plain.ppm"
            write_raster_map(plain, world, width=36, height=18, texture=False)
            _, width, height, plain_body = _read_ppm(plain)
            for score, expected_size, expected_pixels in ((0.5, 6.4760, 172), (0.1, 4.0322, 80)):
                with self.subTest(score=score):
                    self.assertAlmostEqual(
                        expected_size, 12.2188 * (0.28 + 0.50 * score), places=3
                    )
                    marked = Path(tmpdir) / f"marked_{score}.ppm"
                    write_raster_map(
                        marked,
                        _world(
                            [_cell(0, 0.0, 0.0)],
                            settlements=[
                                {"id": 0, "cell_id": 0, "type": "port", "score": score}
                            ],
                        ),
                        width=36,
                        height=18,
                        texture=False,
                    )
                    _, _, _, marked_body = _read_ppm(marked)
                    changed = [
                        (x, y)
                        for y in range(height)
                        for x in range(width)
                        if _pixel(marked_body, width, x, y) != _pixel(plain_body, width, x, y)
                    ]
                    # The halo disc has radius size + 1 about (18.0, 9.0); a pixel
                    # is touched when its centre falls inside that radius.
                    inside = [
                        (x, y)
                        for y in range(height)
                        for x in range(width)
                        if (x + 0.5 - 18.0) ** 2 + (y + 0.5 - 9.0) ** 2
                        <= (expected_size + 1.0) ** 2
                    ]
                    self.assertEqual(len(inside), expected_pixels)
                    self.assertEqual(changed, inside)
                    footprints[score] = len(changed)
            self.assertGreater(footprints[0.5], footprints[0.1])

            _, _, _, marked_body = _read_ppm(Path(tmpdir) / "marked_0.5.ppm")
            # Core, then the dark halo ring, then untouched terrain. The ring pixel
            # sits 6.52 px out: outside the 6.476 core, inside the 7.476 halo, where
            # (35, 31, 23) is composited at 0.92 * (0.70 + 0.30 * 0.2399) = 0.710
            # over the (157, 163, 106) terrain.
            self.assertEqual(_pixel(marked_body, width, 18, 9), (232, 211, 152))
            self.assertEqual(_pixel(marked_body, width, 24, 9), (70, 69, 47))
            self.assertEqual(_pixel(marked_body, width, 25, 9), _pixel(plain_body, width, 25, 9))

    def test_raster_route_is_drawn_as_a_hairline(self) -> None:
        # Two cells on a 36x18 canvas get 8.64 px discs, so the route stroke radius
        # is max(0.8, 8.64 * 0.17) = 1.469 px about the y = 9.0 equator: the rows
        # whose centres are 0.5 px away are painted and the ones 1.5 px away are not.
        cells = [_cell(0, 0.0, -60.0), _cell(1, 0.0, 60.0)]
        settlements = [
            {"id": 0, "cell_id": 0, "type": "port", "score": 0.0},
            {"id": 1, "cell_id": 1, "type": "port", "score": 0.0},
        ]
        with TemporaryDirectory() as tmpdir:
            routed = Path(tmpdir) / "routed.ppm"
            plain = Path(tmpdir) / "plain.ppm"
            write_raster_map(
                routed,
                _world(cells, settlements=settlements, routes=[{"from": 0, "to": 1}]),
                width=36,
                height=18,
                texture=False,
            )
            write_raster_map(
                plain, _world(cells, settlements=settlements), width=36, height=18, texture=False
            )
            _, width, _, routed_body = _read_ppm(routed)
            _, _, _, plain_body = _read_ppm(plain)
            for row, painted in ((7, False), (8, True), (9, True), (10, False), (11, False)):
                with self.subTest(row=row):
                    self.assertEqual(
                        _pixel(routed_body, width, 18, row) != _pixel(plain_body, width, 18, row),
                        painted,
                    )
            self.assertEqual(_pixel(routed_body, width, 18, 9), (232, 206, 135))


class SummaryMarkdownSectionTests(TestCase):
    """The count-section and backend tail of ``write_summary_markdown``."""

    def test_count_sections_and_backend_block_are_rendered(self) -> None:
        world = {
            "name": "section probe",
            "summary": {
                "cell_count": 3,
                "biome_counts": {"tundra": 2, "ocean": 1},
                "resource_counts": {},
            },
            "backend": {"mode": "native", "threads": 4},
        }
        with TemporaryDirectory() as tmpdir:
            output = Path(tmpdir) / "summary.md"
            write_summary_markdown(output, world)
            text = output.read_text(encoding="utf-8")
            lines = text.splitlines()
            self.assertEqual(lines[0], "# section probe")
            self.assertIn("- `cell_count`: 3", lines)
            self.assertIn("## biome_counts", lines)
            index = lines.index("## biome_counts")
            self.assertEqual(lines[index + 1 : index + 4], ["", "- `ocean`: 1", "- `tundra`: 2"])
            # Empty count maps are omitted entirely.
            self.assertNotIn("## resource_counts", lines)
            backend_index = lines.index("## Backend")
            self.assertEqual(
                lines[backend_index + 1 : backend_index + 4],
                ["", "- `mode`: native", "- `threads`: 4"],
            )
