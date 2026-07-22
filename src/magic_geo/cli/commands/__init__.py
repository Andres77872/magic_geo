"""Command modules; importing each one registers its Typer commands.

Import order fixes the order `magic-geo --help` lists commands in.
"""

from __future__ import annotations

from . import config  # noqa: F401
from . import generate  # noqa: F401
from . import validate_geo  # noqa: F401
from . import validate  # noqa: F401
from . import calibrate  # noqa: F401
from . import render  # noqa: F401
from . import export  # noqa: F401
from . import serve  # noqa: F401
