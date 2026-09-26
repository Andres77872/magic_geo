#!/usr/bin/env python3
"""Regenerate the numeric colour tables shared by the web map and the CLI export.

The browser (``debug_ui/colormaps.js``) and ``magic_geo.debug_map_export`` must
draw a value in exactly the same colour, so both read the 256-entry lookup
tables stored in ``colormaps.js``.  This script is the only thing that writes
those tables; run it after changing a definition below and commit the result.

    python scripts/generate_colormaps.py          # rewrite the tables
    python scripts/generate_colormaps.py --check  # exit 1 if they are stale

Definitions
-----------
viridis
    Sequential.  The 6th-order polynomial fit of matplotlib's viridis that the
    map has always used (van der Walt & Smith, 2015), sampled at i/255 and
    truncated to bytes exactly as the WebGL texture upload does.
coolwarm
    Diverging.  Kenneth Moreland's "cool to warm" map (Moreland 2009, "Diverging
    Color Maps for Scientific Visualization"): endpoints sRGB (59, 76, 192) and
    (180, 4, 38) interpolated through a neutral white point in the Msh space
    defined in that paper, which keeps lightness symmetric about the centre.
terrain
    Hypsometric, split at sea level.  The lower half (indices 0-127) is a blue
    bathymetric ramp and the upper half (128-255) a land ramp; both increase
    monotonically in CIELAB lightness away from deep water, so the ordering
    survives greyscale printing and common colour-vision deficiencies.  The
    sharp lightness step at index 128 marks the 0 m contour (Crameri et al.
    2020 recommend this split design for topography).  Control points are
    interpolated linearly in CIELAB.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "src" / "magic_geo" / "debug_ui" / "colormaps.js"
BEGIN = "// BEGIN GENERATED LUTS (scripts/generate_colormaps.py)"
END = "// END GENERATED LUTS"
SIZE = 256

_WHITE = (0.95047, 1.0, 1.08883)  # D65


def _viridis(t: float) -> tuple[float, float, float]:
    coefficients = (
        (0.2777273272234177, 0.005407344544966578, 0.3340998053353061),
        (0.1050930431085774, 1.404613529898575, 1.384590162594685),
        (-0.3308618287255563, 0.214847559468213, 0.09509516302823659),
        (-4.634230498983486, -5.799100973351585, -19.33244095627987),
        (6.228269936347081, 14.17993336680509, 56.69055260068105),
        (4.776384997670288, -13.74514537774601, -65.35303263337234),
        (-5.435455855934631, 4.645852612178535, 26.3124352495832),
    )
    channels = []
    for channel in range(3):
        value = coefficients[6][channel]
        for index in range(5, -1, -1):
            value = value * t + coefficients[index][channel]
        channels.append(max(0.0, min(1.0, value)))
    return channels[0], channels[1], channels[2]


def _to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _to_srgb(channel: float) -> float:
    channel = max(0.0, min(1.0, channel))
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def _rgb_to_lab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_to_linear(c) for c in rgb)
    xyz = (
        0.4124564 * r + 0.3575761 * g + 0.1804375 * b,
        0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
        0.0193339 * r + 0.1191920 * g + 0.9503041 * b,
    )

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = (f(value / white) for value, white in zip(xyz, _WHITE))
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _lab_to_rgb(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    lightness, a, b = lab
    fy = (lightness + 16) / 116
    fx = fy + a / 500
    fz = fy - b / 200

    def finv(t: float) -> float:
        return t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116) / 7.787

    x, y, z = (finv(value) * white for value, white in zip((fx, fy, fz), _WHITE))
    linear = (
        3.2404542 * x - 1.5371385 * y - 0.4985314 * z,
        -0.9692660 * x + 1.8760108 * y + 0.0415560 * z,
        0.0556434 * x - 0.2040259 * y + 1.0572252 * z,
    )
    return tuple(_to_srgb(channel) for channel in linear)  # type: ignore[return-value]


def _hex_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


# -- Moreland (2009) Msh interpolation ---------------------------------------


def _lab_to_msh(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    lightness, a, b = lab
    magnitude = math.sqrt(lightness * lightness + a * a + b * b)
    saturation = math.acos(max(-1.0, min(1.0, lightness / magnitude))) if magnitude > 1e-3 else 0.0
    hue = math.atan2(b, a) if saturation > 1e-3 else 0.0
    return magnitude, saturation, hue


def _msh_to_lab(msh: tuple[float, float, float]) -> tuple[float, float, float]:
    magnitude, saturation, hue = msh
    return (
        magnitude * math.cos(saturation),
        magnitude * math.sin(saturation) * math.cos(hue),
        magnitude * math.sin(saturation) * math.sin(hue),
    )


def _adjust_hue(msh: tuple[float, float, float], unsaturated_magnitude: float) -> float:
    magnitude, saturation, hue = msh
    if magnitude >= unsaturated_magnitude:
        return hue
    spin = saturation * math.sqrt(unsaturated_magnitude ** 2 - magnitude ** 2) / (magnitude * math.sin(saturation))
    return hue + spin if hue > -math.pi / 3 else hue - spin


def _moreland(rgb1, rgb2, t: float) -> tuple[float, float, float]:
    m1, s1, h1 = _lab_to_msh(_rgb_to_lab(rgb1))
    m2, s2, h2 = _lab_to_msh(_rgb_to_lab(rgb2))
    hue_gap = abs(math.atan2(math.sin(h1 - h2), math.cos(h1 - h2)))
    if s1 > 0.05 and s2 > 0.05 and hue_gap > math.pi / 3:
        middle = max(m1, m2, 88.0)
        if t < 0.5:
            m2, s2, h2 = middle, 0.0, 0.0
            t = 2 * t
        else:
            m1, s1, h1 = middle, 0.0, 0.0
            t = 2 * t - 1
    if s1 < 0.05 and s2 > 0.05:
        h1 = _adjust_hue((m2, s2, h2), m1)
    elif s2 < 0.05 and s1 > 0.05:
        h2 = _adjust_hue((m1, s1, h1), m2)
    msh = ((1 - t) * m1 + t * m2, (1 - t) * s1 + t * s2, (1 - t) * h1 + t * h2)
    return _lab_to_rgb(_msh_to_lab(msh))


# -- CIELAB piecewise-linear ramps -------------------------------------------


def _lab_ramp(stops: list[tuple[float, str]], t: float) -> tuple[float, float, float]:
    labs = [(position, _rgb_to_lab(_hex_rgb(color))) for position, color in stops]
    if t <= labs[0][0]:
        return _lab_to_rgb(labs[0][1])
    for (p0, c0), (p1, c1) in zip(labs, labs[1:]):
        if t <= p1:
            f = (t - p0) / (p1 - p0) if p1 > p0 else 0.0
            return _lab_to_rgb(tuple(a + (b - a) * f for a, b in zip(c0, c1)))  # type: ignore[arg-type]
    return _lab_to_rgb(labs[-1][1])


# Bathymetry: deep abyssal navy to bright shelf blue (lightness 13 -> 80).
TERRAIN_OCEAN = [
    (0.0, "#0a1a3c"),
    (0.35, "#173f7a"),
    (0.7, "#2f74b5"),
    (0.9, "#6aaee0"),
    (1.0, "#a9d6f2"),
]
# Land: coastal green to bare rock and snow (lightness 38 -> 96).
TERRAIN_LAND = [
    (0.0, "#2c6a3a"),
    (0.2, "#5b9142"),
    (0.42, "#a6b85e"),
    (0.62, "#d7c98a"),
    (0.82, "#e4d6bf"),
    (1.0, "#f8f6f2"),
]


def _bytes_truncated(rgb: tuple[float, float, float]) -> tuple[int, int, int]:
    return tuple(max(0, min(255, math.floor(channel * 255))) for channel in rgb)  # type: ignore[return-value]


def _bytes_rounded(rgb: tuple[float, float, float]) -> tuple[int, int, int]:
    return tuple(max(0, min(255, math.floor(channel * 255 + 0.5))) for channel in rgb)  # type: ignore[return-value]


def build_luts() -> dict[str, list[tuple[int, int, int]]]:
    blue = (59 / 255, 76 / 255, 192 / 255)
    red = (180 / 255, 4 / 255, 38 / 255)
    half = SIZE // 2
    return {
        # Byte truncation matches the historical Uint8Array texture upload, so
        # existing viridis renders stay byte-identical.
        "viridis": [_bytes_truncated(_viridis(i / (SIZE - 1))) for i in range(SIZE)],
        "coolwarm": [_bytes_rounded(_moreland(blue, red, i / (SIZE - 1))) for i in range(SIZE)],
        "terrain": (
            [_bytes_rounded(_lab_ramp(TERRAIN_OCEAN, i / (half - 1))) for i in range(half)]
            + [_bytes_rounded(_lab_ramp(TERRAIN_LAND, i / (half - 1))) for i in range(half)]
        ),
    }


def render_block(luts: dict[str, list[tuple[int, int, int]]]) -> str:
    lines = [BEGIN, "export const COLORMAP_LUTS = {"]
    for name, entries in luts.items():
        data = "".join(f"{r:02x}{g:02x}{b:02x}" for r, g, b in entries)
        lines.append(f"  {name}: '{data}',")
    lines += ["};", END]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="fail if colormaps.js is out of date")
    args = parser.parse_args()
    source = TARGET.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
    if not pattern.search(source):
        print(f"{TARGET}: generated block markers not found", file=sys.stderr)
        return 2
    updated = pattern.sub(lambda _: render_block(build_luts()), source)
    if args.check:
        if updated != source:
            print(f"{TARGET} is stale; run scripts/generate_colormaps.py", file=sys.stderr)
            return 1
        return 0
    if updated != source:
        TARGET.write_text(updated, encoding="utf-8")
        print(f"updated {TARGET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
