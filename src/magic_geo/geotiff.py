from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass


class GeoTiffError(ValueError):
    """Raised when a GeoTIFF is malformed or uses an unsupported layout."""


_TYPE_SIZES = {
    1: 1,   # BYTE
    2: 1,   # ASCII
    3: 2,   # SHORT
    4: 4,   # LONG
    5: 8,   # RATIONAL
    6: 1,   # SBYTE
    7: 1,   # UNDEFINED
    8: 2,   # SSHORT
    9: 4,   # SLONG
    10: 8,  # SRATIONAL
    11: 4,  # FLOAT
    12: 8,  # DOUBLE
}


class _MsbBitReader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._bit_offset = 0

    def read(self, width: int) -> int | None:
        if self._bit_offset + width > len(self._data) * 8:
            return None
        value = 0
        for _ in range(width):
            byte = self._data[self._bit_offset // 8]
            bit = (byte >> (7 - self._bit_offset % 8)) & 1
            value = (value << 1) | bit
            self._bit_offset += 1
        return value


def decode_tiff_lzw(data: bytes, expected_size: int | None = None) -> bytes:
    reader = _MsbBitReader(data)
    output = bytearray()
    table: list[bytes] = []
    code_width = 9
    next_code = 258
    previous: bytes | None = None

    def reset() -> None:
        nonlocal table, code_width, next_code, previous
        table = [bytes((value,)) for value in range(256)] + [b"", b""]
        code_width = 9
        next_code = 258
        previous = None

    reset()
    while True:
        code = reader.read(code_width)
        if code is None:
            break
        if code == 256:
            reset()
            continue
        if code == 257:
            break
        if code < len(table) and table[code]:
            entry = table[code]
        elif code == next_code and previous is not None:
            entry = previous + previous[:1]
        else:
            raise GeoTiffError(f"invalid TIFF LZW code {code}")

        output.extend(entry)
        if previous is not None and next_code < 4096:
            new_entry = previous + entry[:1]
            if next_code == len(table):
                table.append(new_entry)
            else:
                table[next_code] = new_entry
            next_code += 1
            # TIFF LZW uses early code-width changes (EarlyChange=1).
            if code_width < 12 and next_code == (1 << code_width) - 1:
                code_width += 1
        previous = entry
        if expected_size is not None and len(output) > expected_size:
            raise GeoTiffError("TIFF LZW output exceeds expected strip size")

    if expected_size is not None and len(output) != expected_size:
        raise GeoTiffError(
            f"TIFF LZW output has {len(output)} bytes; expected {expected_size}"
        )
    return bytes(output)


@dataclass(frozen=True)
class GeoTiffMetadata:
    width: int
    height: int
    bits_per_sample: int
    sample_format: int
    compression: int
    rows_per_strip: int
    origin_x: float
    origin_y: float
    pixel_width: float
    pixel_height: float
    nodata: float | None


class GeoTiffRaster:
    def __init__(self, data: bytes) -> None:
        if len(data) < 8:
            raise GeoTiffError("TIFF data is too short")
        byte_order = data[:2]
        if byte_order == b"II":
            self._endian = "<"
        elif byte_order == b"MM":
            self._endian = ">"
        else:
            raise GeoTiffError("invalid TIFF byte order")
        if self._unpack_from("H", data, 2)[0] != 42:
            raise GeoTiffError("invalid TIFF magic number")
        ifd_offset = self._unpack_from("I", data, 4)[0]
        if ifd_offset + 2 > len(data):
            raise GeoTiffError("TIFF IFD offset exceeds file size")

        self._data = data
        self._tags = self._read_ifd(ifd_offset)
        width = self._required_int(256, "ImageWidth")
        height = self._required_int(257, "ImageLength")
        bits_per_sample = self._required_int(258, "BitsPerSample")
        compression = self._optional_int(259, 1)
        samples_per_pixel = self._optional_int(277, 1)
        rows_per_strip = self._optional_int(278, height)
        planar_configuration = self._optional_int(284, 1)
        predictor = self._optional_int(317, 1)
        sample_format = self._optional_int(339, 1)

        if width <= 0 or height <= 0:
            raise GeoTiffError("TIFF dimensions must be positive")
        if width * height > 100_000_000:
            raise GeoTiffError("TIFF raster dimensions are excessive")
        if samples_per_pixel != 1 or planar_configuration != 1:
            raise GeoTiffError("only scalar contiguous GeoTIFF rasters are supported")
        if bits_per_sample not in {8, 16, 32, 64}:
            raise GeoTiffError(f"unsupported TIFF BitsPerSample {bits_per_sample}")
        if sample_format not in {1, 2, 3}:
            raise GeoTiffError(f"unsupported TIFF SampleFormat {sample_format}")
        if sample_format == 3 and bits_per_sample not in {32, 64}:
            raise GeoTiffError("floating-point TIFF samples must use 32 or 64 bits")
        if compression not in {1, 5, 8, 32946}:
            raise GeoTiffError(f"unsupported TIFF compression {compression}")
        if rows_per_strip <= 0 or predictor not in {1, 2}:
            raise GeoTiffError(f"unsupported TIFF predictor/layout {predictor}")

        strip_offsets = tuple(int(value) for value in self._required_values(273, "StripOffsets"))
        strip_byte_counts = tuple(int(value) for value in self._required_values(279, "StripByteCounts"))
        expected_strip_count = math.ceil(height / rows_per_strip)
        if len(strip_offsets) != expected_strip_count or len(strip_byte_counts) != expected_strip_count:
            raise GeoTiffError("TIFF strip count does not match dimensions and RowsPerStrip")
        for offset, byte_count in zip(strip_offsets, strip_byte_counts, strict=True):
            if offset < 0 or byte_count < 0 or offset + byte_count > len(data):
                raise GeoTiffError("TIFF strip range exceeds file size")

        pixel_scale = self._required_values(33550, "ModelPixelScaleTag")
        tiepoints = self._required_values(33922, "ModelTiepointTag")
        if len(pixel_scale) < 2 or len(tiepoints) < 6:
            raise GeoTiffError("GeoTIFF georeferencing tags are incomplete")
        pixel_width = float(pixel_scale[0])
        pixel_height = float(pixel_scale[1])
        raster_x, raster_y = float(tiepoints[0]), float(tiepoints[1])
        model_x, model_y = float(tiepoints[3]), float(tiepoints[4])
        if pixel_width <= 0.0 or pixel_height <= 0.0:
            raise GeoTiffError("GeoTIFF pixel scales must be positive")
        origin_x = model_x - raster_x * pixel_width
        origin_y = model_y + raster_y * pixel_height

        nodata: float | None = None
        if 42113 in self._tags:
            raw_nodata = self._tags[42113]
            if not isinstance(raw_nodata, str):
                raise GeoTiffError("GDAL_NODATA must be ASCII")
            try:
                nodata = float(raw_nodata.strip("\x00 "))
            except ValueError as exc:
                raise GeoTiffError("GDAL_NODATA is not numeric") from exc

        self.metadata = GeoTiffMetadata(
            width=width,
            height=height,
            bits_per_sample=bits_per_sample,
            sample_format=sample_format,
            compression=compression,
            rows_per_strip=rows_per_strip,
            origin_x=origin_x,
            origin_y=origin_y,
            pixel_width=pixel_width,
            pixel_height=pixel_height,
            nodata=nodata,
        )
        self._predictor = predictor
        self._strip_offsets = strip_offsets
        self._strip_byte_counts = strip_byte_counts

    def _unpack_from(self, fmt: str, data: bytes, offset: int) -> tuple[object, ...]:
        try:
            return struct.unpack_from(self._endian + fmt, data, offset)
        except struct.error as exc:
            raise GeoTiffError("truncated TIFF structure") from exc

    def _read_ifd(self, offset: int) -> dict[int, object]:
        entry_count = int(self._unpack_from("H", self._data, offset)[0])
        entries_end = offset + 2 + entry_count * 12
        if entries_end + 4 > len(self._data):
            raise GeoTiffError("truncated TIFF IFD")
        tags: dict[int, object] = {}
        for entry_index in range(entry_count):
            entry_offset = offset + 2 + entry_index * 12
            tag, value_type, count = self._unpack_from("HHI", self._data, entry_offset)
            tag = int(tag)
            value_type = int(value_type)
            count = int(count)
            if value_type not in _TYPE_SIZES or count < 0:
                raise GeoTiffError(f"unsupported TIFF field type {value_type}")
            byte_count = _TYPE_SIZES[value_type] * count
            if byte_count <= 4:
                raw = self._data[entry_offset + 8:entry_offset + 8 + byte_count]
            else:
                value_offset = int(self._unpack_from("I", self._data, entry_offset + 8)[0])
                if value_offset < 0 or value_offset + byte_count > len(self._data):
                    raise GeoTiffError(f"TIFF tag {tag} value range exceeds file size")
                raw = self._data[value_offset:value_offset + byte_count]
            tags[tag] = self._decode_field(value_type, count, raw)
        return tags

    def _decode_field(self, value_type: int, count: int, raw: bytes) -> object:
        if value_type == 2:
            return raw.decode("ascii", errors="strict").rstrip("\x00")
        formats = {
            1: "B",
            3: "H",
            4: "I",
            6: "b",
            8: "h",
            9: "i",
            11: "f",
            12: "d",
        }
        if value_type in formats:
            values = struct.unpack(self._endian + formats[value_type] * count, raw)
            return values[0] if count == 1 else values
        if value_type in {5, 10}:
            integer_format = "I" if value_type == 5 else "i"
            integers = struct.unpack(self._endian + integer_format * count * 2, raw)
            values = []
            for index in range(count):
                numerator = integers[index * 2]
                denominator = integers[index * 2 + 1]
                if denominator == 0:
                    raise GeoTiffError("TIFF rational denominator is zero")
                values.append(numerator / denominator)
            return values[0] if count == 1 else tuple(values)
        if value_type == 7:
            return raw
        raise GeoTiffError(f"unsupported TIFF field type {value_type}")

    def _required_values(self, tag: int, name: str) -> tuple[object, ...]:
        if tag not in self._tags:
            raise GeoTiffError(f"TIFF is missing required {name} tag")
        value = self._tags[tag]
        return value if isinstance(value, tuple) else (value,)

    def _required_int(self, tag: int, name: str) -> int:
        values = self._required_values(tag, name)
        if len(values) != 1:
            raise GeoTiffError(f"TIFF {name} must be scalar")
        return int(values[0])

    def _optional_int(self, tag: int, default: int) -> int:
        if tag not in self._tags:
            return default
        return self._required_int(tag, str(tag))

    def grid_signature(self) -> tuple[object, ...]:
        metadata = self.metadata
        return (
            metadata.width,
            metadata.height,
            metadata.origin_x,
            metadata.origin_y,
            metadata.pixel_width,
            metadata.pixel_height,
        )

    def _decode_strip(self, strip_index: int) -> bytes:
        metadata = self.metadata
        first_row = strip_index * metadata.rows_per_strip
        rows = min(metadata.rows_per_strip, metadata.height - first_row)
        bytes_per_sample = metadata.bits_per_sample // 8
        expected_size = rows * metadata.width * bytes_per_sample
        offset = self._strip_offsets[strip_index]
        byte_count = self._strip_byte_counts[strip_index]
        compressed = self._data[offset:offset + byte_count]
        if metadata.compression == 1:
            decoded = compressed
        elif metadata.compression == 5:
            decoded = decode_tiff_lzw(compressed, expected_size)
        else:
            try:
                decoded = zlib.decompress(compressed)
            except zlib.error:
                try:
                    decoded = zlib.decompress(compressed, -zlib.MAX_WBITS)
                except zlib.error as exc:
                    raise GeoTiffError("invalid TIFF Deflate strip") from exc
        if len(decoded) != expected_size:
            raise GeoTiffError(
                f"decoded TIFF strip has {len(decoded)} bytes; expected {expected_size}"
            )
        if self._predictor == 2:
            decoded = self._undo_horizontal_predictor(decoded, rows)
        return decoded

    def _undo_horizontal_predictor(self, data: bytes, rows: int) -> bytes:
        metadata = self.metadata
        bytes_per_sample = metadata.bits_per_sample // 8
        row_size = metadata.width * bytes_per_sample
        modulus = 1 << metadata.bits_per_sample
        output = bytearray(data)
        for row in range(rows):
            row_offset = row * row_size
            previous = 0
            for column in range(metadata.width):
                offset = row_offset + column * bytes_per_sample
                current = int.from_bytes(
                    output[offset:offset + bytes_per_sample],
                    byteorder="little" if self._endian == "<" else "big",
                    signed=False,
                )
                current = (current + previous) % modulus
                output[offset:offset + bytes_per_sample] = current.to_bytes(
                    bytes_per_sample,
                    byteorder="little" if self._endian == "<" else "big",
                    signed=False,
                )
                previous = current
        return bytes(output)

    def _sample_value(self, row_data: bytes, row_in_strip: int, column: int) -> float:
        metadata = self.metadata
        bytes_per_sample = metadata.bits_per_sample // 8
        offset = (row_in_strip * metadata.width + column) * bytes_per_sample
        if metadata.sample_format == 3:
            fmt = "f" if metadata.bits_per_sample == 32 else "d"
        elif metadata.sample_format == 2:
            fmt = {8: "b", 16: "h", 32: "i", 64: "q"}[metadata.bits_per_sample]
        else:
            fmt = {8: "B", 16: "H", 32: "I", 64: "Q"}[metadata.bits_per_sample]
        return float(struct.unpack_from(self._endian + fmt, row_data, offset)[0])

    def sample_lon_lat(self, points: list[tuple[float, float]]) -> list[float | None]:
        metadata = self.metadata
        locations: list[tuple[int, int] | None] = []
        strips_needed: set[int] = set()
        for lon, lat in points:
            column = math.floor((lon - metadata.origin_x) / metadata.pixel_width)
            row = math.floor((metadata.origin_y - lat) / metadata.pixel_height)
            if row < 0 or row >= metadata.height or column < 0 or column >= metadata.width:
                locations.append(None)
                continue
            locations.append((row, column))
            strips_needed.add(row // metadata.rows_per_strip)

        decoded_strips = {strip: self._decode_strip(strip) for strip in strips_needed}
        values: list[float | None] = []
        for location in locations:
            if location is None:
                values.append(None)
                continue
            row, column = location
            strip = row // metadata.rows_per_strip
            row_in_strip = row - strip * metadata.rows_per_strip
            value = self._sample_value(decoded_strips[strip], row_in_strip, column)
            nodata = metadata.nodata
            if nodata is not None and (
                value == nodata
                or math.isclose(value, nodata, rel_tol=1.0e-6, abs_tol=1.0e-12)
            ):
                values.append(None)
            elif not math.isfinite(value):
                values.append(None)
            else:
                values.append(value)
        return values
