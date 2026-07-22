"""Synthetic geospatial fixtures: ESRI shapefile, DBF, and OPeNDAP ASCII grids.

The calibration readers parse these formats by hand, so the tests build the
smallest byte-exact files that exercise each reader instead of shipping
binary fixtures.
"""

from __future__ import annotations

import struct
from pathlib import Path


def write_vector_shapefile(path: Path, shape_type: int, points: list[tuple[float, float]]) -> None:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    record_content = bytearray()
    record_content += struct.pack("<i", shape_type)
    record_content += struct.pack("<4d", *bbox)
    record_content += struct.pack("<2i", 1, len(points))
    record_content += struct.pack("<i", 0)
    for x, y in points:
        record_content += struct.pack("<2d", x, y)

    file_length_words = (100 + 8 + len(record_content)) // 2
    header = bytearray(100)
    struct.pack_into(">i", header, 0, 9994)
    struct.pack_into(">i", header, 24, file_length_words)
    struct.pack_into("<i", header, 28, 1000)
    struct.pack_into("<i", header, 32, shape_type)
    struct.pack_into("<4d", header, 36, *bbox)

    record_header = struct.pack(">2i", 1, len(record_content) // 2)
    path.write_bytes(bytes(header) + record_header + bytes(record_content))


def write_polyline_shapefile(path: Path, points: list[tuple[float, float]] | None = None) -> None:
    write_vector_shapefile(path, 3, points or [(0.0, 0.0), (0.0, 1.0)])


def write_polygon_shapefile(path: Path, points: list[tuple[float, float]]) -> None:
    write_vector_shapefile(path, 5, points)


def write_dbf(path: Path, field_name: str, values: list[float]) -> None:
    field_length = 12
    decimal_count = 3
    header_length = 32 + 32 + 1
    record_length = 1 + field_length
    header = bytearray(header_length)
    header[0] = 0x03
    struct.pack_into("<I", header, 4, len(values))
    struct.pack_into("<H", header, 8, header_length)
    struct.pack_into("<H", header, 10, record_length)
    encoded_name = field_name.encode("ascii")[:10]
    field_offset = 32
    header[field_offset:field_offset + len(encoded_name)] = encoded_name
    header[field_offset + 11] = ord("N")
    header[field_offset + 16] = field_length
    header[field_offset + 17] = decimal_count
    header[-1] = 0x0D

    records = bytearray()
    for value in values:
        records += b" "
        records += f"{value:>{field_length}.{decimal_count}f}".encode("ascii")
    path.write_bytes(bytes(header) + bytes(records) + b"\x1A")


def write_dbf_table(path: Path, fields: dict[str, list[float | None]]) -> None:
    if not fields:
        raise ValueError("DBF test table requires fields")
    record_count = len(next(iter(fields.values())))
    if any(len(values) != record_count for values in fields.values()):
        raise ValueError("DBF test fields must have equal lengths")
    field_length = 14
    decimal_count = 3
    header_length = 32 + len(fields) * 32 + 1
    record_length = 1 + len(fields) * field_length
    header = bytearray(header_length)
    header[0] = 0x03
    struct.pack_into("<I", header, 4, record_count)
    struct.pack_into("<H", header, 8, header_length)
    struct.pack_into("<H", header, 10, record_length)
    for field_index, field_name in enumerate(fields):
        descriptor_offset = 32 + field_index * 32
        encoded_name = field_name.encode("ascii")[:10]
        header[descriptor_offset:descriptor_offset + len(encoded_name)] = encoded_name
        header[descriptor_offset + 11] = ord("N")
        header[descriptor_offset + 16] = field_length
        header[descriptor_offset + 17] = decimal_count
    header[-1] = 0x0D

    records = bytearray()
    field_values = list(fields.values())
    for record_index in range(record_count):
        records += b" "
        for values in field_values:
            value = values[record_index]
            records += (
                b" " * field_length
                if value is None
                else f"{value:>{field_length}.{decimal_count}f}".encode("ascii")
            )
    path.write_bytes(bytes(header) + bytes(records) + b"\x1A")


def write_opendap_ascii_grid(
    path: Path,
    grid: list[list[float]],
    latitudes: list[float],
    longitudes: list[float],
) -> None:
    rows = len(grid)
    columns = len(longitudes)
    lines = [
        "Dataset {",
        "    Grid {",
        "    } z;",
        "}",
        "---------------------------------------------",
        f"z.z[{rows}][{columns}]",
    ]
    for row_index, row in enumerate(grid):
        lines.append(f"[{row_index}], " + ", ".join(str(value) for value in row))
    lines.extend(
        [
            "",
            f"z.lat[{rows}]",
            ", ".join(str(value) for value in latitudes),
            "",
            f"z.lon[{columns}]",
            ", ".join(str(value) for value in longitudes),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
