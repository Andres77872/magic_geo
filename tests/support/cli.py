"""Assertions for Typer/click CLI invocations.

``CliRunner`` turns an uncaught exception into ``exit_code == 1`` with an *empty*
``output`` and no traceback text anywhere, so ``assertNotIn("Traceback",
result.output)`` can never fail and is not a crash guard. Only
``result.exception`` distinguishes the two: a reported failure leaves the
``SystemExit`` that ``typer.Exit`` raises, while a crash leaves the original
exception.
"""

from __future__ import annotations

import traceback
from typing import Any
from unittest import TestCase


def assert_no_cli_crash(testcase: TestCase, result: Any, *, command: str = "command") -> None:
    """Require that the CLI reported a failure rather than raising."""
    exception = result.exception
    if exception is not None and not isinstance(exception, SystemExit):
        formatted = "".join(traceback.format_exception(*result.exc_info))
        testcase.fail(f"{command} raised instead of reporting:\n{formatted}")
