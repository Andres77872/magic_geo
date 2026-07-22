"""Hand-built payload fixtures shared by more than one test module."""

from __future__ import annotations

import math
import struct
import zlib


def sample_world() -> dict[str, object]:
    """A world payload covering the serialization edge cases worth pinning."""
    return {
        "schema_version": 1,
        "name": "Tierra \"rápida\"\n🌍\u0001",
        "none": None,
        "truth": True,
        "integer": 1,
        "uint64": 2**64 - 1,
        "int64": -(2**63),
        "values": [
            -0.0,
            0.0,
            math.nextafter(0.0, 1.0),
            1.2345678901234567,
            1.7976931348623157e308,
        ],
        "empty_object": {},
        "empty_array": [],
        "nested": {"records": [{"id": 0}, {"id": 1}]},
    }


def pack_lzw_literals(payload: bytes) -> bytes:
    """Encode ``payload`` as TIFF LZW using literal codes only."""
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


def apply_horizontal_predictor(
    raw_pixels: bytes,
    width: int,
    height: int,
    bits_per_sample: int,
    *,
    big_endian: bool = False,
) -> bytes:
    """Forward horizontal differencing (TIFF Predictor=2) over packed samples."""
    bytes_per_sample = bits_per_sample // 8
    order = "big" if big_endian else "little"
    modulus = 1 << bits_per_sample
    row_size = width * bytes_per_sample
    output = bytearray(raw_pixels)
    for row in range(height):
        base = row * row_size
        originals = [
            int.from_bytes(
                raw_pixels[base + column * bytes_per_sample : base + (column + 1) * bytes_per_sample],
                order,
            )
            for column in range(width)
        ]
        for column in range(width - 1, 0, -1):
            difference = (originals[column] - originals[column - 1]) % modulus
            output[base + column * bytes_per_sample : base + (column + 1) * bytes_per_sample] = (
                difference.to_bytes(bytes_per_sample, order)
            )
    return bytes(output)


def build_geotiff(
    values: list[float | int],
    width: int,
    height: int,
    *,
    bits_per_sample: int,
    sample_format: int,
    compression: int,
    nodata: float | int | str | None,
    big_endian: bool = False,
    predictor: int = 1,
    raw_deflate: bool = False,
    tiepoint: tuple[float, float, float, float, float, float] = (
        0.0,
        0.0,
        0.0,
        -180.0,
        90.0,
        0.0,
    ),
    tag_overrides: dict[int, tuple[int, int, bytes]] | None = None,
    truncate_bytes: int = 0,
) -> bytes:
    """A single-strip, single-band GeoTIFF covering the whole globe.

    Every keyword past ``nodata`` is a deliberate deviation used by the GeoTIFF
    tests; the defaults reproduce the original little-endian, unpredicted,
    zlib-wrapped layout byte for byte.
    """
    endian = ">" if big_endian else "<"
    if sample_format == 3:
        value_format = "f" if bits_per_sample == 32 else "d"
    elif sample_format == 2:
        value_format = {8: "b", 16: "h", 32: "i", 64: "q"}[bits_per_sample]
    else:
        value_format = {8: "B", 16: "H", 32: "I", 64: "Q"}[bits_per_sample]
    raw_pixels = struct.pack(endian + value_format * len(values), *values)
    if predictor == 2:
        raw_pixels = apply_horizontal_predictor(
            raw_pixels, width, height, bits_per_sample, big_endian=big_endian
        )
    if compression == 1:
        pixel_data = raw_pixels
    elif compression == 5:
        pixel_data = pack_lzw_literals(raw_pixels)
    elif compression == 8:
        if raw_deflate:
            compressor = zlib.compressobj(wbits=-15)
            pixel_data = compressor.compress(raw_pixels) + compressor.flush()
        else:
            pixel_data = zlib.compress(raw_pixels)
    else:
        raise ValueError("unsupported test compression")

    def short(value: int) -> bytes:
        return struct.pack(endian + "H", value)

    def long(value: int) -> bytes:
        return struct.pack(endian + "I", value)

    entries: dict[int, tuple[int, int, bytes]] = {
        256: (3, 1, short(width)),
        257: (3, 1, short(height)),
        258: (3, 1, short(bits_per_sample)),
        259: (3, 1, short(compression)),
        262: (3, 1, short(1)),
        273: (4, 1, b"\x00\x00\x00\x00"),
        277: (3, 1, short(1)),
        278: (4, 1, long(height)),
        279: (4, 1, long(len(pixel_data))),
        284: (3, 1, short(1)),
        339: (3, 1, short(sample_format)),
        33550: (12, 3, struct.pack(endian + "3d", 360.0 / width, 180.0 / height, 0.0)),
        33922: (12, 6, struct.pack(endian + "6d", *tiepoint)),
    }
    if predictor != 1:
        entries[317] = (3, 1, short(predictor))
    if nodata is not None:
        entries[42113] = (2, len(f"{nodata}\x00"), f"{nodata}\x00".encode("ascii"))
    if tag_overrides:
        entries.update(tag_overrides)

    tags: list[tuple[int, int, int, bytes]] = [
        (tag, value_type, count, raw)
        for tag, (value_type, count, raw) in sorted(entries.items())
    ]
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

    magic = b"MM" if big_endian else b"II"
    output = bytearray(struct.pack(endian + "2sHI", magic, 42, 8))
    output += struct.pack(endian + "H", len(tags))
    for tag, value_type, count, raw in tags:
        if tag == 273 and not (tag_overrides and 273 in tag_overrides):
            raw = long(pixel_offset)
        output += struct.pack(endian + "HHI", tag, value_type, count)
        if len(raw) <= 4:
            output += raw.ljust(4, b"\x00")
        else:
            output += long(value_offsets[tag])
    output += long(0)
    output += b"".join(extra_chunks)
    output += pixel_data
    if truncate_bytes:
        return bytes(output[: len(output) - truncate_bytes])
    return bytes(output)
