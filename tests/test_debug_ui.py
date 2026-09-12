"""Run workbench request-order regressions against the actual JavaScript."""

import shutil
import subprocess
from pathlib import Path
from unittest import TestCase, skipUnless


@skipUnless(shutil.which("node"), "Node.js is required for frontend regressions")
class DebugUiTests(TestCase):
    def test_workbench_handlers(self) -> None:
        result = subprocess.run(
            ["node", str(Path(__file__).with_suffix(".mjs"))],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
