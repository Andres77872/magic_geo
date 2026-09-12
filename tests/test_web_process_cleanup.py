"""Real-child regressions for failures while consuming workbench output.

The subprocess commands are replaced with tiny Python controls: these tests do
not invoke the CLI, load a native backend, or generate a world.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from magic_geo.web_jobs import JobManager, WebJob


@skipUnless(os.name == "posix", "requires POSIX process groups and signals")
class WebProcessOutputCleanupTests(TestCase):
    def _assert_output_failure_reaps_child(self, *, invalid_utf8: bool) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            workspace = root / "runs"
            workspace.mkdir()
            world = workspace / "world.json"
            other_world = workspace / "other-world.json"
            world.write_text("{}", encoding="utf-8")
            other_world.write_text("{}", encoding="utf-8")
            children: list[subprocess.Popen[str]] = []
            spawned = threading.Event()
            release_spawn = threading.Event()
            first_complete = threading.Event()
            first_id: list[str] = []
            terminal_observations: list[tuple[str, int | None, int | None]] = []
            log_failures: list[str] = []
            real_popen = subprocess.Popen

            def completed(job: WebJob) -> None:
                if first_id and job.id == first_id[0]:
                    # Inspect without poll()/wait(): the worker must already
                    # have reaped the child before publishing terminal state.
                    terminal_observations.append(
                        (job.status, job.exit_code, children[0].returncode)
                    )
                    first_complete.set()

            manager = JobManager(root, workspace, on_complete=completed)
            original_append_log = manager._append_log

            def append_log(job: WebJob, text: str) -> None:
                if not invalid_utf8 and text == "raise-in-log-handler\n":
                    log_failures.append(text)
                    raise RuntimeError("synthetic child log failure")
                original_append_log(job, text)

            def controlled_popen(command, **kwargs):
                first = not children
                if first:
                    payload = "b'\\xff\\n'" if invalid_utf8 else "b'raise-in-log-handler\\n'"
                    script = (
                        "import os, signal, sys, time\n"
                        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                        "os.write(1, b'ready\\n')\n"
                        "sys.stdin.buffer.read(1)\n"
                        f"os.write(1, {payload})\n"
                        "time.sleep(60)\n"
                    )
                    kwargs["stdin"] = subprocess.PIPE
                else:
                    script = "print('next-job-finished', flush=True)\n"
                # Pin decoding independently of locale and Python defaults.
                kwargs["encoding"] = "utf-8"
                kwargs["errors"] = "strict"
                process = real_popen([sys.executable, "-c", script], **kwargs)
                children.append(process)
                if first:
                    assert process.stdout is not None
                    self.assertEqual(process.stdout.readline(), "ready\n")
                    spawned.set()
                    if not release_spawn.wait(5.0):
                        raise AssertionError("test did not release Popen")
                    assert process.stdin is not None
                    process.stdin.write("x")
                    process.stdin.flush()
                    process.stdin.close()
                return process

            def finished(job_id: str) -> dict:
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    result = manager.get(job_id)
                    if result["status"] not in {"queued", "running"}:
                        return result
                    time.sleep(0.005)
                self.fail(f"job did not finish: {manager.get(job_id)}")

            try:
                with patch("magic_geo.web_jobs.subprocess.Popen", side_effect=controlled_popen), patch.object(
                    manager, "_append_log", side_effect=append_log
                ):
                    first = manager.submit("validate", {"world": str(world)})
                    first_id.append(first["id"])
                    self.assertTrue(spawned.wait(5.0), "child did not install its TERM handler")
                    successor = manager.submit("validate", {"world": str(other_world)})
                    self.assertEqual(successor["status"], "queued")
                    release_spawn.set()
                    self.assertTrue(first_complete.wait(5.0), "failed job did not complete")
                    failed = finished(first["id"])
                    next_finished = finished(successor["id"])
                    self.assertEqual(failed["status"], "failed")
                    self.assertEqual(failed["exit_code"], -1)
                    self.assertFalse(manager._jobs[first["id"]]._cancel_requested)
                    if invalid_utf8:
                        self.assertIn("UnicodeDecodeError", failed["log"])
                        self.assertIn("invalid start byte", failed["log"])
                        self.assertEqual(log_failures, [])
                    else:
                        self.assertIn("RuntimeError: synthetic child log failure", failed["log"])
                        self.assertEqual(log_failures, ["raise-in-log-handler\n"])
                    self.assertEqual(next_finished["status"], "succeeded")
                    self.assertEqual(next_finished["exit_code"], 0)
                    self.assertIn("next-job-finished", next_finished["log"])
                    self.assertEqual(len(children), 2)
                    self.assertIsNone(manager._jobs[first["id"]]._process)
                    self.assertEqual(
                        terminal_observations,
                        [("failed", -1, -signal.SIGKILL)],
                        "the child must be killed and reaped before failure is published",
                    )
                    with self.assertRaises(ChildProcessError):
                        os.waitpid(children[0].pid, os.WNOHANG)
            finally:
                release_spawn.set()
                # Expected failures against the old implementation must not
                # leave its TERM-ignoring child or its executor behind.
                for process in children:
                    if process.poll() is None:
                        JobManager._terminate_process(process, force=True)
                    process.wait(timeout=3.0)
                    for stream in (process.stdin, process.stdout):
                        if stream is not None and not stream.closed:
                            stream.close()
                manager.close()

    def test_invalid_utf8_reaps_child_before_failed_job_and_queue_progress(self) -> None:
        self._assert_output_failure_reaps_child(invalid_utf8=True)

    def test_log_handler_exception_reaps_child_before_failed_job_and_queue_progress(self) -> None:
        self._assert_output_failure_reaps_child(invalid_utf8=False)
