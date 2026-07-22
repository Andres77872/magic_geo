"""Pytest fixtures over :mod:`tests.support`.

The suite is unittest-based, and ``unittest.TestCase`` methods cannot receive
pytest fixtures. Those files therefore call the ``support`` helpers directly;
these fixtures exist for plain-pytest test functions.

Imports stay inside the fixture bodies so that collection never pulls in the
optional ``[debug]`` stack, which would defeat the module-level skips in
``test_debug_server.py``.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture
def small_smoke_world() -> dict[str, Any]:
    """A private deep copy of the 256-cell smoke world."""
    from support import worlds

    return worlds.cached_world("small_smoke")


@pytest.fixture
def mid_512_world() -> dict[str, Any]:
    """A private deep copy of the 512-cell causal-replay world."""
    from support import worlds

    return worlds.cached_world("mid_512")


@pytest.fixture
def routed_512_world() -> dict[str, Any]:
    """A private deep copy of the 512-cell sediment-routing world."""
    from support import worlds

    return worlds.cached_world("routed_512")


@pytest.fixture
def coupled_128_world() -> dict[str, Any]:
    """A private deep copy of the 128-cell coupled-maturation world."""
    from support import worlds

    return worlds.cached_world("coupled_128")


@pytest.fixture
def replay_128_world() -> dict[str, Any]:
    """A private deep copy of the 128-cell world the replay validators run on."""
    from support import worlds

    return worlds.cached_world("replay_128")


@pytest.fixture
def sample_world() -> dict[str, object]:
    """The hand-built serialization edge-case payload."""
    from support.builders import sample_world as build

    return build()


@pytest.fixture
def cli_runner():
    """A Typer ``CliRunner`` for invoking commands in-process."""
    from typer.testing import CliRunner

    return CliRunner()
