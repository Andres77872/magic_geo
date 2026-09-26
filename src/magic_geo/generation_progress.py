"""Opt-in generation activity for the worker's stderr event stream.

Counts describe work inside the named stage; they are never an overall
percentage or a prediction of the amount of solver work still required.
"""

from __future__ import annotations

import json
import os
import sys
import threading

_LOCK = threading.Lock()


def emit_progress(
    phase: str,
    label: str,
    detail: str = "",
    *,
    current: int | None = None,
    total: int | None = None,
) -> None:
    if os.environ.get("MAGIC_GEO_PROGRESS") != "1":
        return
    event: dict[str, str | int] = {"phase": phase, "label": label, "detail": detail}
    if current is not None and total is not None:
        event.update(current=current, total=total)
    try:
        line = "MAGIC_GEO_PROGRESS " + json.dumps(event, separators=(",", ":")) + "\n"
        with _LOCK:
            sys.stderr.write(line)
            sys.stderr.flush()
    except (OSError, ValueError):
        # A closed diagnostic stream must not change generation results.
        pass
