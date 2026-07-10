import hashlib
import struct
import zlib
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from zipfile import ZIP_DEFLATED, ZipFile

from magic_geo.calibration import derive_calibration_targets, evaluate_calibration_targets
from magic_geo.geotiff import GeoTiffRaster, decode_tiff_lzw


def _pack_lzw_literals(payload: bytes) -> bytes:
    codes = [256, *payload, 257]
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


def _build_geotiff(
    values: list[float | int],
    width: int,
    height: int,
    *,
    bits_per_sample: int,
    sample_format: int,
    compression: int,
    nodata: float | int,
) -> bytes:
    if sample_format == 3:
        value_format = "f" if bits_per_sample == 32 else "d"
    elif sample_format == 2:
        value_format = {8: "b", 16: "h", 32: "i", 64: "q"}[bits_per_sample]
    else:
        value_format = {8: "B", 16: "H", 32: "I", 64: "Q"}[bits_per_sample]
    raw_pixels = struct.pack("<" + value_format * len(values), *values)
    if compression == 1:
        pixel_data = raw_pixels
    elif compression == 5:
        pixel_data = _pack_lzw_literals(raw_pixels)
    elif compression == 8:
        pixel_data = zlib.compress(raw_pixels)
    else:
        raise ValueError("unsupported test compression")

    def short(value: int) -> bytes:
        return struct.pack("<H", value)

    def long(value: int) -> bytes:
        return struct.pack("<I", value)

    tags: list[tuple[int, int, int, bytes]] = [
        (256, 3, 1, short(width)),
        (257, 3, 1, short(height)),
        (258, 3, 1, short(bits_per_sample)),
        (259, 3, 1, short(compression)),
        (262, 3, 1, short(1)),
        (273, 4, 1, b"\x00\x00\x00\x00"),
        (277, 3, 1, short(1)),
        (278, 4, 1, long(height)),
        (279, 4, 1, long(len(pixel_data))),
        (284, 3, 1, short(1)),
        (339, 3, 1, short(sample_format)),
        (33550, 12, 3, struct.pack("<3d", 360.0 / width, 180.0 / height, 0.0)),
        (33922, 12, 6, struct.pack("<6d", 0.0, 0.0, 0.0, -180.0, 90.0, 0.0)),
        (42113, 2, len(f"{nodata}\x00"), f"{nodata}\x00".encode("ascii")),
    ]
    tags.sort(key=lambda item: item[0])
    ifd_size = 2 + len(tags) * 12 + 4
    extra_offset = 8 + ifd_size
    extra_chunks: list[bytes] = []
    value_offsets: dict[int, int] = {}
    for tag, _value_type, _count, raw in tags:
        if len(raw) > 4:
            value_offsets[tag] = extra_offset
            extra_chunks.append(raw)
            extra_offset += len(raw)
    pixel_offset = extra_offset

    output = bytearray(struct.pack("<2sHI", b"II", 42, 8))
    output += struct.pack("<H", len(tags))
    for tag, value_type, count, raw in tags:
        if tag == 273:
            raw = long(pixel_offset)
        output += struct.pack("<HHI", tag, value_type, count)
        if len(raw) <= 4:
            output += raw.ljust(4, b"\x00")
        else:
            output += long(value_offsets[tag])
    output += long(0)
    output += b"".join(extra_chunks)
    output += pixel_data
    return bytes(output)


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
            raster = _build_geotiff(
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
        encoded = _pack_lzw_literals(payload)
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
