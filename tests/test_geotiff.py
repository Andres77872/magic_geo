from __future__ import annotations

import hashlib
import math
import re
import struct
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zipfile import ZIP_DEFLATED, ZipFile

from magic_geo.calibration import derive_calibration_targets, evaluate_calibration_targets
from magic_geo.geotiff import GeoTiffError, GeoTiffRaster, decode_tiff_lzw

from support.builders import build_geotiff, pack_lzw_literals

GRID_VALUES = [float(10 * row + column) for row in range(4) for column in range(4)]
# The 4x4 rasters built below span the whole globe: 90 deg wide, 45 deg tall cells
# anchored at (-180, 90), so these points hit the centre of every pixel in order.
CELL_CENTRES = [
    (-180.0 + 90.0 * column + 45.0, 90.0 - 45.0 * row - 22.5)
    for row in range(4)
    for column in range(4)
]


def _short(value: int, endian: str = "<") -> bytes:
    return struct.pack(endian + "H", value)


def _long(value: int, endian: str = "<") -> bytes:
    return struct.pack(endian + "I", value)


def _pack_lzw_codes(codes: list[int]) -> bytes:
    """Pack an arbitrary TIFF LZW code stream, mirroring the EarlyChange=1 widths."""
    packed_bits: list[int] = []
    code_width = 9
    next_code = 258
    previous = False
    for code in codes:
        packed_bits.extend((code >> shift) & 1 for shift in range(code_width - 1, -1, -1))
        if code == 256:
            code_width = 9
            next_code = 258
            previous = False
        elif code == 257:
            break
        else:
            if previous and next_code < 4096:
                next_code += 1
                if code_width < 12 and next_code == (1 << code_width) - 1:
                    code_width += 1
            previous = True
    while len(packed_bits) % 8:
        packed_bits.append(0)
    return bytes(
        sum(packed_bits[offset + bit] << (7 - bit) for bit in range(8))
        for offset in range(0, len(packed_bits), 8)
    )


def _float32_raster(**overrides: object) -> bytes:
    """A 4x4 float32 raster over the whole globe, with ``build_geotiff`` deviations."""
    options: dict[str, object] = {
        "bits_per_sample": 32,
        "sample_format": 3,
        "compression": 1,
        "nodata": None,
    }
    options.update(overrides)
    values = options.pop("values", GRID_VALUES)
    return build_geotiff(list(values), 4, 4, **options)  # type: ignore[arg-type]


def _multi_strip_raster(rows_per_strip: int) -> bytes:
    """The 4x4 float32 grid split into ceil(4 / ``rows_per_strip``) strips.

    ``build_geotiff`` only writes single-strip files, so StripOffsets and
    StripByteCounts are replaced by arrays here. The pixel block is always the
    tail of the file, which is what makes the offsets computable: the first
    build only exists to measure the file, and the second one repeats it with
    real offsets (identical field widths, hence an identical layout).
    """
    strip_rows = [min(rows_per_strip, 4 - first) for first in range(0, 4, rows_per_strip)]
    byte_counts = [rows * 4 * 4 for rows in strip_rows]
    overrides: dict[int, tuple[int, int, bytes]] = {
        278: (4, 1, _long(rows_per_strip)),
        273: (4, len(byte_counts), b"".join(_long(0) for _ in byte_counts)),
        279: (4, len(byte_counts), b"".join(_long(count) for count in byte_counts)),
    }
    draft = _float32_raster(tag_overrides=overrides)
    offsets: list[int] = []
    next_offset = len(draft) - 4 * 4 * 4
    for byte_count in byte_counts:
        offsets.append(next_offset)
        next_offset += byte_count
    overrides[273] = (4, len(byte_counts), b"".join(_long(offset) for offset in offsets))
    payload = _float32_raster(tag_overrides=overrides)
    assert len(payload) == len(draft)
    return payload


def _hide_tag(payload: bytes, tag: int, value_type: int, count: int, raw: bytes) -> bytes:
    """Rename one IFD entry so the parser no longer sees ``tag``.

    ``build_geotiff`` can override or add tags but never drop one. Rewriting just
    the 2-byte tag id leaves every offset in the file intact, so the parser has to
    cope with the tag being absent rather than with a corrupt layout. 65000 is a
    private tag id the module ignores.
    """
    entry = _short(tag) + _short(value_type) + _long(count) + raw.ljust(4, b"\x00")
    assert payload.count(entry) == 1, f"tag {tag} entry is not unique in the file"
    return payload.replace(entry, _short(65000) + entry[2:])


def _write_worldclim_archive(path: Path, variable: str, *, temperature: bool) -> None:
    with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
        for month in range(1, 13):
            nodata = -9999.0 if temperature else -32768
            monthly_value = float(month) if temperature else 10
            values = [
                monthly_value if column < 2 else nodata
                for _row in range(4)
                for column in range(4)
            ]
            raster = build_geotiff(
                values,
                4,
                4,
                bits_per_sample=32 if temperature else 16,
                sample_format=3 if temperature else 2,
                compression=5 if temperature else 8,
                nodata=nodata,
            )
            archive.writestr(f"wc2.1_10m_{variable}_{month:02}.tif", raster)


class GeoTiffTests(TestCase):
    def test_tiff_lzw_handles_early_width_changes(self) -> None:
        payload = bytes(range(256)) * 3
        encoded = pack_lzw_literals(payload)
        self.assertEqual(decode_tiff_lzw(encoded, len(payload)), payload)

    def test_worldclim_geotiff_archives_and_land_metrics(self) -> None:
        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            temperature_archive = root / "wc2.1_10m_tavg.zip"
            precipitation_archive = root / "wc2.1_10m_prec.zip"
            _write_worldclim_archive(temperature_archive, "tavg", temperature=True)
            _write_worldclim_archive(precipitation_archive, "prec", temperature=False)
            temperature_sha256 = hashlib.sha256(temperature_archive.read_bytes()).hexdigest()

            raster_bytes: bytes
            with ZipFile(temperature_archive) as archive:
                raster_bytes = archive.read("wc2.1_10m_tavg_01.tif")
            raster = GeoTiffRaster(raster_bytes)
            self.assertEqual(raster.metadata.compression, 5)
            self.assertEqual(raster.sample_lon_lat([(-90.0, 45.0), (90.0, 45.0)]), [1.0, None])

            common = {
                "dataset": "test_worldclim",
                "sample_cell_count": 128,
                "format": "worldclim_geotiff_zip",
                "tolerance_abs": 0.0,
            }
            sources = [
                {
                    **common,
                    "layer": "temperature",
                    "metric": "fibonacci_mean_land_annual_temperature_c",
                    "world_metric": "mean_land_annual_temperature_c",
                    "path": str(temperature_archive),
                    "statistic": "fibonacci_mean_land_annual_temperature_c",
                    "variable": "tavg",
                },
                {
                    **common,
                    "layer": "temperature",
                    "metric": "fibonacci_mean_land_annual_temperature_range_c",
                    "world_metric": "mean_land_annual_temperature_range_c",
                    "path": str(temperature_archive),
                    "statistic": "fibonacci_mean_land_annual_temperature_range_c",
                    "variable": "tavg",
                },
                {
                    **common,
                    "layer": "precipitation",
                    "metric": "fibonacci_mean_land_annual_precipitation_mm",
                    "world_metric": "mean_land_precipitation_mm_y",
                    "path": str(precipitation_archive),
                    "statistic": "fibonacci_mean_land_annual_precipitation_mm",
                    "variable": "prec",
                },
            ]
            report = derive_calibration_targets(sources)

        targets = {target["metric"]: target for target in report["targets"]}
        self.assertEqual(targets["mean_land_annual_temperature_c"]["source_value"], 6.5)
        self.assertEqual(targets["mean_land_annual_temperature_range_c"]["source_value"], 11.0)
        self.assertEqual(targets["mean_land_precipitation_mm_y"]["source_value"], 120.0)
        self.assertEqual(
            targets["mean_land_annual_temperature_c"]["source_sha256"],
            temperature_sha256,
        )
        self.assertEqual(targets["mean_land_precipitation_mm_y"]["source_grid_width"], 4)

        world = {
            "calibration_checks": [{"metric": "mean_land_precipitation_mm_y", "value": 120.0}],
            "cells": [
                {
                    "is_water": False,
                    "temperature_monthly_c": [float(month) for month in range(1, 13)],
                    "precipitation_mm_y": 120.0,
                },
                {
                    "is_water": True,
                    "temperature_monthly_c": [0.0] * 12,
                    "precipitation_mm_y": 0.0,
                },
            ],
        }
        evaluation = evaluate_calibration_targets(world, report["targets"])
        self.assertEqual(evaluation["summary"]["external_calibration_pass_count"], 3)
        self.assertIn("mean_land_annual_temperature_c", evaluation["available_world_metrics"])
        self.assertIn("mean_land_annual_temperature_range_c", evaluation["available_world_metrics"])

    # ------------------------------------------------------------------
    # header parsing
    # ------------------------------------------------------------------

    def test_malformed_headers_are_rejected(self) -> None:
        valid = _float32_raster()
        cases = [
            ("bad byte order", b"XX" + valid[2:], "invalid TIFF byte order"),
            (
                "bad magic",
                b"II" + _short(43) + valid[4:],
                "invalid TIFF magic number",
            ),
            ("seven bytes", valid[:7], "TIFF data is too short"),
            ("empty", b"", "TIFF data is too short"),
        ]
        for label, payload, message in cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(GeoTiffError, re.escape(message)):
                    GeoTiffRaster(payload)
        # The untampered header parses, so the mutations above are what fail.
        self.assertEqual(GeoTiffRaster(valid).metadata.width, 4)

    def test_ifd_offset_past_end_of_file_is_rejected(self) -> None:
        valid = _float32_raster()
        tampered = valid[:4] + _long(len(valid)) + valid[8:]
        with self.assertRaisesRegex(
            GeoTiffError, re.escape("TIFF IFD offset exceeds file size")
        ):
            GeoTiffRaster(tampered)

    def test_ifd_structure_defects_are_rejected(self) -> None:
        valid = _float32_raster()
        cases = [
            (
                # Two extra bytes at the end read as an entry count of 1000, so the
                # 12-byte entries the IFD claims to hold run far past the file.
                "entry array runs past end of file",
                valid[:4] + _long(len(valid)) + valid[8:] + _short(1000),
                "truncated TIFF IFD",
            ),
            (
                # 64 of the file's bytes are pixels, so chopping 72 also eats the
                # tail of the last out-of-line tag value (ModelTiepointTag, 48
                # bytes) while leaving the IFD entries themselves intact.
                "tag value range runs past end of file",
                _float32_raster(truncate_bytes=72),
                "TIFF tag 33922 value range exceeds file size",
            ),
            (
                "unknown field type",
                _float32_raster(tag_overrides={700: (13, 1, b"\x00\x00\x00\x00")}),
                "unsupported TIFF field type 13",
            ),
        ]
        for label, payload, message in cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(GeoTiffError, re.escape(message)):
                    GeoTiffRaster(payload)
        # An IFD offset that points at the real IFD, with the same trailing bytes
        # appended, parses: only the redirected offset above is fatal.
        self.assertEqual(GeoTiffRaster(valid + _short(1000)).metadata.width, 4)

    def test_undefined_field_type_is_carried_as_raw_bytes(self) -> None:
        raster = GeoTiffRaster(_float32_raster(tag_overrides={700: (7, 4, b"abcd")}))
        self.assertEqual(raster._tags[700], b"abcd")
        self.assertEqual(raster.sample_lon_lat(CELL_CENTRES), GRID_VALUES)

    def test_required_tag_defects_are_rejected(self) -> None:
        cases = [
            (
                "ImageWidth missing",
                _hide_tag(_float32_raster(), 256, 3, 1, _short(4)),
                "TIFF is missing required ImageWidth tag",
            ),
            (
                "ImageWidth holds two values",
                _float32_raster(tag_overrides={256: (3, 2, _short(4) + _short(4))}),
                "TIFF ImageWidth must be scalar",
            ),
        ]
        for label, payload, message in cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(GeoTiffError, re.escape(message)):
                    GeoTiffRaster(payload)

    def test_big_endian_raster_matches_little_endian_twin(self) -> None:
        little = _float32_raster(compression=5)
        big = _float32_raster(compression=5, big_endian=True)
        self.assertEqual(little[:2], b"II")
        self.assertEqual(big[:2], b"MM")
        self.assertNotEqual(little, big)

        little_raster = GeoTiffRaster(little)
        big_raster = GeoTiffRaster(big)
        # 4x4 cells anchored at (-180, 90), 360/4 by 180/4 degrees each.
        self.assertEqual(little_raster.grid_signature(), (4, 4, -180.0, 90.0, 90.0, 45.0))
        self.assertEqual(big_raster.grid_signature(), little_raster.grid_signature())
        self.assertEqual(
            big_raster.sample_lon_lat(CELL_CENTRES),
            little_raster.sample_lon_lat(CELL_CENTRES),
        )
        self.assertEqual(big_raster.sample_lon_lat(CELL_CENTRES), GRID_VALUES)

    # ------------------------------------------------------------------
    # unsupported layouts
    # ------------------------------------------------------------------

    def test_unsupported_layouts_are_rejected(self) -> None:
        cases: list[tuple[str, dict[str, object], str]] = [
            (
                "samples_per_pixel=2",
                {"tag_overrides": {277: (3, 1, _short(2))}},
                "only scalar contiguous GeoTIFF rasters are supported",
            ),
            (
                "planar_configuration=2",
                {"tag_overrides": {284: (3, 1, _short(2))}},
                "only scalar contiguous GeoTIFF rasters are supported",
            ),
            (
                "bits_per_sample=24",
                {"tag_overrides": {258: (3, 1, _short(24))}},
                "unsupported TIFF BitsPerSample 24",
            ),
            (
                "sample_format=4",
                {"tag_overrides": {339: (3, 1, _short(4))}},
                "unsupported TIFF SampleFormat 4",
            ),
            (
                "sample_format=3 with 16 bits",
                {
                    "bits_per_sample": 16,
                    "sample_format": 1,
                    "values": [int(value) for value in GRID_VALUES],
                    "tag_overrides": {339: (3, 1, _short(3))},
                },
                "floating-point TIFF samples must use 32 or 64 bits",
            ),
            (
                "compression=2",
                {"tag_overrides": {259: (3, 1, _short(2))}},
                "unsupported TIFF compression 2",
            ),
            (
                "zero width",
                {"tag_overrides": {256: (3, 1, _short(0))}},
                "TIFF dimensions must be positive",
            ),
            (
                "negative width",
                {"tag_overrides": {256: (8, 1, struct.pack("<h", -4))}},
                "TIFF dimensions must be positive",
            ),
            (
                "predictor=3",
                {"tag_overrides": {317: (3, 1, _short(3))}},
                "unsupported TIFF predictor/layout 3",
            ),
            (
                "strip count disagrees with rows_per_strip",
                {"tag_overrides": {278: (4, 1, _long(1))}},
                "TIFF strip count does not match dimensions and RowsPerStrip",
            ),
            (
                "strip range past end of file",
                {"truncate_bytes": 4},
                "TIFF strip range exceeds file size",
            ),
            (
                "dimensions above the 100M sample cap",
                {
                    "tag_overrides": {
                        256: (4, 1, _long(50_000)),
                        257: (4, 1, _long(50_000)),
                    }
                },
                "TIFF raster dimensions are excessive",
            ),
        ]
        for label, overrides, message in cases:
            with self.subTest(case=label):
                payload = _float32_raster(**overrides)
                with self.assertRaisesRegex(GeoTiffError, re.escape(message)):
                    GeoTiffRaster(payload)
        # Same builder without any mutation: parses and samples cleanly.
        self.assertEqual(GeoTiffRaster(_float32_raster()).sample_lon_lat(CELL_CENTRES), GRID_VALUES)

    def test_rational_tag_with_zero_denominator_is_rejected(self) -> None:
        payload = _float32_raster(tag_overrides={282: (5, 1, struct.pack("<II", 72, 0))})
        with self.assertRaisesRegex(
            GeoTiffError, re.escape("TIFF rational denominator is zero")
        ):
            GeoTiffRaster(payload)
        # The very same tag with a non-zero denominator is accepted.
        raster = GeoTiffRaster(
            _float32_raster(tag_overrides={282: (5, 1, struct.pack("<II", 72, 1))})
        )
        self.assertEqual(raster.metadata.width, 4)

    # ------------------------------------------------------------------
    # LZW
    # ------------------------------------------------------------------

    def test_lzw_rejects_code_outside_the_table(self) -> None:
        stream = _pack_lzw_codes([256, 65, 500, 257])
        with self.assertRaisesRegex(GeoTiffError, re.escape("invalid TIFF LZW code 500")):
            decode_tiff_lzw(stream)
        # 258 (== next_code) is the highest code this stream may legally use.
        self.assertEqual(decode_tiff_lzw(_pack_lzw_codes([256, 65, 258, 257])), b"AA" + b"A")

    def test_lzw_enforces_expected_output_size(self) -> None:
        stream = _pack_lzw_codes([256, 65, 66, 67, 68, 257])
        self.assertEqual(decode_tiff_lzw(stream, 4), b"ABCD")
        cases = [
            ("expected smaller than output", 2, "TIFF LZW output exceeds expected strip size"),
            ("expected larger than output", 10, "TIFF LZW output has 4 bytes; expected 10"),
        ]
        for label, expected_size, message in cases:
            with self.subTest(case=label):
                with self.assertRaisesRegex(GeoTiffError, re.escape(message)):
                    decode_tiff_lzw(stream, expected_size)

    def test_lzw_clear_code_resets_the_table_mid_stream(self) -> None:
        # 65, 66 create table[258] = b"AB"; the second clear code discards it, so the
        # trailing 258 is instead the self-referencing entry built from b"C".
        self.assertEqual(
            decode_tiff_lzw(_pack_lzw_codes([256, 65, 66, 256, 67, 258, 257])),
            b"ABCCC",
        )
        # Without the mid-stream clear the same trailing code resolves to b"AB".
        self.assertEqual(
            decode_tiff_lzw(_pack_lzw_codes([256, 65, 66, 67, 258, 257])),
            b"ABCAB",
        )

    def test_lzw_stops_at_the_end_of_the_code_stream_without_eoi(self) -> None:
        # Three 9-bit codes fill 27 of the 32 bits, so the five padding bits are
        # too few for a fourth code: the decoder has to stop on a short read
        # rather than invent a code or run off the end of the buffer.
        stream = _pack_lzw_codes([256, 65, 66])
        self.assertEqual(len(stream), 4)
        self.assertEqual(decode_tiff_lzw(stream), b"AB")
        self.assertEqual(decode_tiff_lzw(stream, 2), b"AB")
        with self.assertRaisesRegex(
            GeoTiffError, re.escape("TIFF LZW output has 2 bytes; expected 3")
        ):
            decode_tiff_lzw(stream, 3)

    def test_lzw_decodes_self_referencing_code(self) -> None:
        # KwKwK: code == next_code decodes to previous + previous[:1].
        self.assertEqual(decode_tiff_lzw(_pack_lzw_codes([256, 65, 258, 257])), b"AAA")
        self.assertEqual(decode_tiff_lzw(_pack_lzw_codes([256, 66, 67, 259, 257])), b"BCCC")

    # ------------------------------------------------------------------
    # Deflate
    # ------------------------------------------------------------------

    def test_deflate_accepts_raw_stream_via_negative_window_retry(self) -> None:
        payload = _float32_raster(compression=8, raw_deflate=True)
        raster = GeoTiffRaster(payload)
        offset = raster._strip_offsets[0]
        byte_count = raster._strip_byte_counts[0]
        stream = payload[offset : offset + byte_count]
        # No zlib wrapper: the first decompress attempt has to fail for the
        # -MAX_WBITS retry to be what decodes this raster.
        with self.assertRaises(zlib.error):
            zlib.decompress(stream)
        self.assertEqual(
            zlib.decompress(stream, -zlib.MAX_WBITS),
            struct.pack("<16f", *GRID_VALUES),
        )
        self.assertEqual(raster.sample_lon_lat(CELL_CENTRES), GRID_VALUES)

    def test_deflate_rejects_corrupt_stream(self) -> None:
        payload = _float32_raster(compression=8)
        raster = GeoTiffRaster(payload)
        offset = raster._strip_offsets[0]
        byte_count = raster._strip_byte_counts[0]
        self.assertEqual(raster.sample_lon_lat([CELL_CENTRES[0]]), [0.0])

        corrupt = payload[:offset] + b"\xff" * byte_count + payload[offset + byte_count :]
        self.assertEqual(len(corrupt), len(payload))
        corrupt_raster = GeoTiffRaster(corrupt)
        with self.assertRaisesRegex(GeoTiffError, re.escape("invalid TIFF Deflate strip")):
            corrupt_raster.sample_lon_lat([CELL_CENTRES[0]])

    # ------------------------------------------------------------------
    # predictor
    # ------------------------------------------------------------------

    def test_horizontal_predictor_round_trips(self) -> None:
        base_values = [3, 9, 250, 255, 0, 128, 200, 7, 10, 20, 30, 40, 255, 0, 255, 0]
        for bits_per_sample in (8, 16):
            # 251*v + 3 keeps every 16-bit sample under 65536 while giving it two
            # different bytes, so a byte-order slip cannot cancel itself out.
            values = [
                value * 251 + 3 if bits_per_sample == 16 else value for value in base_values
            ]
            if bits_per_sample == 16:
                self.assertTrue(
                    all(value >> 8 != value & 0xFF for value in values),
                    "16-bit predictor samples must not be byte-symmetric",
                )
            for compression in (1, 5, 8):
                for big_endian in (False, True):
                    with self.subTest(
                        bits=bits_per_sample, compression=compression, big_endian=big_endian
                    ):
                        payload = build_geotiff(
                            values,
                            4,
                            4,
                            bits_per_sample=bits_per_sample,
                            sample_format=1,
                            compression=compression,
                            nodata=None,
                            predictor=2,
                            big_endian=big_endian,
                        )
                        raster = GeoTiffRaster(payload)
                        self.assertEqual(
                            raster.sample_lon_lat(CELL_CENTRES),
                            [float(value) for value in values],
                        )
                        # The stored samples really are differenced: reading the same
                        # bytes without the predictor tag yields the deltas instead.
                        unpredicted = build_geotiff(
                            values,
                            4,
                            4,
                            bits_per_sample=bits_per_sample,
                            sample_format=1,
                            compression=compression,
                            nodata=None,
                            predictor=2,
                            big_endian=big_endian,
                            tag_overrides={317: (3, 1, _short(1, ">" if big_endian else "<"))},
                        )
                        self.assertNotEqual(
                            GeoTiffRaster(unpredicted).sample_lon_lat(CELL_CENTRES),
                            [float(value) for value in values],
                        )

    # ------------------------------------------------------------------
    # nodata and sampling
    # ------------------------------------------------------------------

    def test_nodata_tag_must_be_numeric_ascii(self) -> None:
        cases = [
            ("non-numeric text", {"nodata": "not-a-number"}, "GDAL_NODATA is not numeric"),
            (
                "non-ascii field type",
                {"tag_overrides": {42113: (3, 1, _short(5))}},
                "GDAL_NODATA must be ASCII",
            ),
        ]
        for label, overrides, message in cases:
            with self.subTest(case=label):
                payload = _float32_raster(**overrides)
                with self.assertRaisesRegex(GeoTiffError, re.escape(message)):
                    GeoTiffRaster(payload)
        # A numeric string parses into the metadata unharmed.
        self.assertEqual(GeoTiffRaster(_float32_raster(nodata="-9999.0")).metadata.nodata, -9999.0)

    def test_numeric_nodata_masks_matching_samples(self) -> None:
        values = [-9999.0, 1.0, 2.0, 3.0] + [4.0] * 12
        masked = GeoTiffRaster(_float32_raster(values=values, nodata=-9999.0))
        self.assertEqual(masked.metadata.nodata, -9999.0)
        self.assertEqual(masked.sample_lon_lat(CELL_CENTRES[:4]), [None, 1.0, 2.0, 3.0])
        # Without the tag the very same sample comes back as a number.
        unmasked = GeoTiffRaster(_float32_raster(values=values, nodata=None))
        self.assertIsNone(unmasked.metadata.nodata)
        self.assertEqual(unmasked.sample_lon_lat(CELL_CENTRES[:4]), [-9999.0, 1.0, 2.0, 3.0])

    def test_non_finite_samples_are_masked(self) -> None:
        values = [math.nan, math.inf, -math.inf, 3.0] + [4.0] * 12
        raster = GeoTiffRaster(_float32_raster(values=values, nodata=None))
        self.assertEqual(raster.sample_lon_lat(CELL_CENTRES[:4]), [None, None, None, 3.0])

    def test_out_of_grid_points_skip_strip_decoding(self) -> None:
        raster = GeoTiffRaster(_float32_raster())
        decoded_strips: list[int] = []
        original_decode_strip = raster._decode_strip

        def counting_decode_strip(strip_index: int) -> bytes:
            decoded_strips.append(strip_index)
            return original_decode_strip(strip_index)

        raster._decode_strip = counting_decode_strip  # type: ignore[method-assign]
        outside = [(200.0, 0.0), (-200.0, 0.0), (0.0, 100.0), (0.0, -100.0)]
        self.assertEqual(raster.sample_lon_lat(outside), [None, None, None, None])
        self.assertEqual(decoded_strips, [])
        # An in-grid point on the same raster does decode the strip.
        self.assertEqual(raster.sample_lon_lat([CELL_CENTRES[5]]), [11.0])
        self.assertEqual(decoded_strips, [0])

    def test_multi_strip_raster_maps_rows_onto_the_right_strip(self) -> None:
        # rows_per_strip=3 over 4 rows: strip 0 holds rows 0-2, strip 1 holds the
        # single trailing row, so the short final strip and the row-within-strip
        # offset both have to be handled.
        raster = GeoTiffRaster(_multi_strip_raster(3))
        self.assertEqual(raster.metadata.rows_per_strip, 3)
        self.assertEqual(raster._strip_byte_counts, (48, 16))
        self.assertEqual(raster.sample_lon_lat(CELL_CENTRES), GRID_VALUES)

        decoded_strips: list[int] = []
        original_decode_strip = raster._decode_strip

        def counting_decode_strip(strip_index: int) -> bytes:
            decoded_strips.append(strip_index)
            return original_decode_strip(strip_index)

        raster._decode_strip = counting_decode_strip  # type: ignore[method-assign]
        # Row 0 lives in strip 0 and row 3 in strip 1; each sample touches one strip.
        self.assertEqual(raster.sample_lon_lat([CELL_CENTRES[1]]), [1.0])
        self.assertEqual(decoded_strips, [0])
        self.assertEqual(raster.sample_lon_lat([CELL_CENTRES[13]]), [31.0])
        self.assertEqual(decoded_strips, [0, 1])

    def test_rows_per_strip_defaults_to_the_image_height(self) -> None:
        raster = GeoTiffRaster(_hide_tag(_float32_raster(), 278, 4, 1, _long(4)))
        # The tag really is gone; the value below is the default, not the tag.
        self.assertNotIn(278, raster._tags)
        self.assertIn(65000, raster._tags)
        self.assertEqual(raster.metadata.rows_per_strip, 4)
        self.assertEqual(raster.metadata.height, 4)
        self.assertEqual(raster.sample_lon_lat(CELL_CENTRES), GRID_VALUES)

    def test_one_row_per_strip_raster_samples_every_row(self) -> None:
        raster = GeoTiffRaster(_multi_strip_raster(1))
        self.assertEqual(raster.metadata.rows_per_strip, 1)
        self.assertEqual(raster._strip_byte_counts, (16, 16, 16, 16))
        self.assertEqual(raster.sample_lon_lat(CELL_CENTRES), GRID_VALUES)

    def test_strip_byte_count_shorter_than_the_strip_is_rejected(self) -> None:
        # 4x4 float32 needs 64 bytes; claim 60 and the strip decodes short.
        raster = GeoTiffRaster(_float32_raster(tag_overrides={279: (4, 1, _long(60))}))
        with self.assertRaisesRegex(
            GeoTiffError, re.escape("decoded TIFF strip has 60 bytes; expected 64")
        ):
            raster.sample_lon_lat([CELL_CENTRES[0]])
        # The untouched byte count decodes the full strip.
        self.assertEqual(
            GeoTiffRaster(_float32_raster()).sample_lon_lat([CELL_CENTRES[0]]), [0.0]
        )

    def test_nodata_matches_within_float32_rounding_tolerance(self) -> None:
        # GDAL writes the sentinel as decimal text, so the float64 tag value and the
        # float32 sample never compare equal; masking has to be tolerant.
        stored_sentinel = struct.unpack("<f", struct.pack("<f", -3.4e38))[0]
        self.assertNotEqual(stored_sentinel, -3.4e38)
        stored_other = struct.unpack("<f", struct.pack("<f", -3.39e38))[0]
        # 0.29% away from the sentinel: far outside the 1e-6 relative tolerance.
        self.assertGreater(abs(stored_other - stored_sentinel) / abs(stored_sentinel), 1.0e-6)

        values = [-3.4e38, -3.39e38, 1.0] + [2.0] * 13
        raster = GeoTiffRaster(_float32_raster(values=values, nodata="-3.4e+38"))
        self.assertEqual(raster.metadata.nodata, -3.4e38)
        self.assertEqual(
            raster.sample_lon_lat(CELL_CENTRES[:3]), [None, stored_other, 1.0]
        )

    def test_padded_nodata_field_is_parsed(self) -> None:
        raster = GeoTiffRaster(
            _float32_raster(tag_overrides={42113: (2, 10, b"-9999.0\x00 \x00")})
        )
        self.assertEqual(raster.metadata.nodata, -9999.0)

    def test_origin_uses_raster_tiepoint_offsets(self) -> None:
        raster_x, raster_y = 1.5, 2.0
        model_x, model_y = -170.0, 80.0
        raster = GeoTiffRaster(
            _float32_raster(tiepoint=(raster_x, raster_y, 0.0, model_x, model_y, 0.0))
        )
        metadata = raster.metadata
        self.assertEqual(metadata.pixel_width, 90.0)
        self.assertEqual(metadata.pixel_height, 45.0)
        self.assertAlmostEqual(metadata.origin_x, model_x - raster_x * metadata.pixel_width, places=12)
        self.assertAlmostEqual(metadata.origin_y, model_y + raster_y * metadata.pixel_height, places=12)
        self.assertAlmostEqual(metadata.origin_x, -305.0, places=12)
        self.assertAlmostEqual(metadata.origin_y, 170.0, places=12)
        # The shifted origin moves the sampling window with it: the first pixel now
        # sits at the shifted origin, and a point the default grid covers falls out.
        self.assertEqual(raster.sample_lon_lat([(-305.0 + 45.0, 170.0 - 22.5)]), [0.0])
        self.assertEqual(raster.sample_lon_lat([CELL_CENTRES[3]]), [None])
        self.assertEqual(GeoTiffRaster(_float32_raster()).sample_lon_lat([CELL_CENTRES[3]]), [3.0])

    def test_non_positive_pixel_scales_are_rejected(self) -> None:
        cases = [
            ("zero width", 0.0, 45.0),
            ("zero height", 90.0, 0.0),
            ("negative width", -90.0, 45.0),
            ("negative height", 90.0, -45.0),
        ]
        for label, pixel_width, pixel_height in cases:
            with self.subTest(case=label):
                payload = _float32_raster(
                    tag_overrides={
                        33550: (12, 3, struct.pack("<3d", pixel_width, pixel_height, 0.0))
                    }
                )
                with self.assertRaisesRegex(
                    GeoTiffError, re.escape("GeoTIFF pixel scales must be positive")
                ):
                    GeoTiffRaster(payload)
        # The same tag rewritten with the builder's own positive scales is accepted.
        raster = GeoTiffRaster(
            _float32_raster(tag_overrides={33550: (12, 3, struct.pack("<3d", 90.0, 45.0, 0.0))})
        )
        self.assertEqual((raster.metadata.pixel_width, raster.metadata.pixel_height), (90.0, 45.0))

    def test_incomplete_georeferencing_tags_are_rejected(self) -> None:
        cases = [
            (
                "pixel scale holds one value",
                {33550: (12, 1, struct.pack("<d", 90.0))},
            ),
            (
                "tiepoint holds three values",
                {33922: (12, 3, struct.pack("<3d", 0.0, 0.0, 0.0))},
            ),
        ]
        for label, overrides in cases:
            with self.subTest(case=label):
                payload = _float32_raster(tag_overrides=overrides)
                with self.assertRaisesRegex(
                    GeoTiffError, re.escape("GeoTIFF georeferencing tags are incomplete")
                ):
                    GeoTiffRaster(payload)
