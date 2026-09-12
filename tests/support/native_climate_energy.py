"""Fresh decoded copies of genuine, checked-in C++ climate certificates."""
from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any


_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/native_climate_energy"


def native_climate_world() -> dict[str, Any]:
    """128-cell native public-generation witness, including linked fields."""
    return json.loads(gzip.decompress((_FIXTURES / "world_128.json.gz").read_bytes()))


def native_climate_certificate(method: str = "tr_bdf2") -> dict[str, Any]:
    """12-cell standalone witness; explicitly lacks full-world linkage."""
    if method not in {"tr_bdf2", "backward_euler"}:
        raise ValueError("unsupported fixture time method")
    return json.loads(gzip.decompress((_FIXTURES / f"certificate_12_{method}.json.gz").read_bytes()))
