"""Context managers for standing in for the native simulation library."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import patch

from magic_geo import native as native_module


@contextmanager
def patch_generation_payload(library: Any, payload: Any) -> Iterator[None]:
    """Make both transports return ``payload`` from ``library`` without the C++ core.

    Used to drive the schema-gating branches that a healthy native library can
    never produce.
    """
    with (
        patch.object(native_module, "_load_library", return_value=library),
        patch.object(native_module, "_consume_json_pointer", return_value=payload),
        patch.object(native_module, "_consume_msgpack_pointer", return_value=payload),
    ):
        yield


@contextmanager
def patch_loaded_library(
    library: Any,
    *,
    path: Path = Path("incomplete.so"),
) -> Iterator[None]:
    """Make ``native._load_library`` resolve ``path`` and load ``library`` via ctypes."""
    with (
        patch.object(native_module, "_library_path", return_value=path),
        patch.object(native_module.ctypes, "CDLL", return_value=library),
    ):
        yield
