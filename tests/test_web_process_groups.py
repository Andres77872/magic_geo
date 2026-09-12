"""Cancellation retains group ownership after the direct child exits."""
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from magic_geo.web_jobs import JobManager
from test_web_jobs import wait_for_job, wait_until


def process_state(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return None


@pytest.mark.skipif(sys.platform != "linux", reason="non-reaping process-state observation uses Linux /proc")
@pytest.mark.parametrize("cancel_before_exit", [False, True], ids=["leader-already-exited", "leader-exits-on-term"])
def test_cancel_kills_descendant_holding_stdout_after_leader_exit(tmp_path, cancel_before_exit):
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs/world.json").write_text("{}")
    manager = JobManager(tmp_path, Path("runs"))
    real_popen = subprocess.Popen
    real_timer = threading.Timer
    handles = []
    timers = []
    timer_scheduled = threading.Event()
    fire_timer = threading.Event()
    # The child and its descendant share the new process group and stdout.
    # A private pipe orders handler installation before the parent announces it.
    program = (
        "import os, signal, time\n"
        "r, w = os.pipe()\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    os.close(r)\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    os.write(w, b'r')\n"
        "    os.close(w)\n"
        "    time.sleep(30)\n"
        "    os._exit(0)\n"
        "os.close(w)\n"
        "os.read(r, 1)\n"
        "os.close(r)\n"
        "print('descendant=' + str(pid), flush=True)\n"
        + ("time.sleep(30)\n" if cancel_before_exit else "os._exit(0)\n")
    )

    def start(command, **kwargs):
        process = real_popen([sys.executable, "-c", program], **kwargs)
        handles.append(process)
        return process

    def short_timer(interval, callback):
        assert interval == 5.0

        def fire():
            if fire_timer.wait(5.0):
                callback()

        timer = real_timer(0.05, fire)
        timers.append(timer)
        timer_scheduled.set()
        return timer

    descendant = None
    try:
        with patch("magic_geo.web_jobs.subprocess.Popen", side_effect=start), patch(
            "magic_geo.web_jobs.threading.Timer", side_effect=short_timer
        ):
            submitted = manager.submit("validate", {"world": "runs/world.json"})
            job_id = submitted["id"]
            assert wait_until(lambda: "descendant=" in manager.get(job_id)["log"], timeout=3.0)
            line = next(line for line in manager.get(job_id)["log"].splitlines() if line.startswith("descendant="))
            descendant = int(line.partition("=")[2])
            leader = handles[0]
            if not cancel_before_exit:
                # Observe exit without poll()/wait(), which would release the
                # leader PID before the production cancellation path sees it.
                assert wait_until(lambda: process_state(leader.pid) == "Z", timeout=3.0)
            assert process_state(descendant) not in (None, "Z")
            manager.cancel(job_id)
            assert timer_scheduled.wait(1.0), "group escalation missing after leader exit"
            assert wait_until(lambda: process_state(leader.pid) in (None, "Z"), timeout=3.0)
            fire_timer.set()
            finished = wait_for_job(manager, job_id, timeout=2.0)
            assert finished["status"] == "cancelled"
            assert finished["exit_code"] == (-signal.SIGTERM if cancel_before_exit else 0)
            assert leader.returncode == finished["exit_code"]
            assert manager._jobs[job_id]._process is None
            assert wait_until(lambda: process_state(descendant) in (None, "Z"), timeout=2.0)
    finally:
        fire_timer.set()
        # Also clean the deliberately failing original implementation. The
        # grandchild cannot be waited by this parent; EOF and /proc prove exit.
        for process in handles:
            JobManager._terminate_process(process, force=True)
        for timer in timers:
            timer.join(timeout=2.0)
        manager.close()
        for process in handles:
            process.wait(timeout=2.0)


@pytest.mark.skipif(os.name != "posix", reason="POSIX signals and descriptor closure")
def test_cancel_still_escalates_after_stdout_closes_before_child_exit(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs/world.json").write_text("{}")
    manager = JobManager(tmp_path, Path("runs"))
    real_popen, real_timer = subprocess.Popen, threading.Timer
    handles, timers = [], []

    def start(command, **kwargs):
        process = real_popen([
            sys.executable, "-c",
            "import os, signal, time\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "print('closing-output', flush=True)\n"
            "os.close(1)\nos.close(2)\ntime.sleep(30)\n",
        ], **kwargs)
        handles.append(process)
        return process

    def short_timer(interval, callback):
        assert interval == 5.0
        timer = real_timer(0.05, callback)
        timers.append(timer)
        return timer

    try:
        with patch("magic_geo.web_jobs.subprocess.Popen", side_effect=start), patch(
            "magic_geo.web_jobs.threading.Timer", side_effect=short_timer
        ):
            job = manager.submit("validate", {"world": "runs/world.json"})
            assert wait_until(lambda: "closing-output" in manager.get(job["id"])["log"], timeout=3.0)
            assert wait_until(lambda: handles[0].stdout.closed, timeout=3.0)
            manager.cancel(job["id"])
            final = wait_for_job(manager, job["id"], timeout=2.0)
            assert final["status"] == "cancelled"
            assert final["exit_code"] == -signal.SIGKILL
            assert handles[0].returncode == -signal.SIGKILL
    finally:
        for process in handles:
            if process.poll() is None:
                JobManager._terminate_process(process, force=True)
        for timer in timers:
            timer.join(timeout=2.0)
        manager.close()
        for process in handles:
            process.wait(timeout=2.0)
