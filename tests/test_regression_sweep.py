"""Exercise durable runner diagnostics in a real, deliberately paused pytest."""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


RUNNER = Path(__file__).resolve().parents[1] / "scripts/research/regression_sweep.py"


def test_failure_subtest_and_cache_evidence_are_durable_before_blocked_teardown(tmp_path):
    output = tmp_path / "sweep"
    marker = tmp_path / "teardown-entered"
    release = tmp_path / "release-teardown"
    config = tmp_path / "pytest.ini"
    config.write_text("[pytest]\n", encoding="utf-8")
    support = tmp_path / "sweep_local_support"
    support.mkdir()
    (support / "__init__.py").write_text("COLLECTION_WITNESS = 731\n", encoding="utf-8")
    fixture_source = '''
from pathlib import Path
import sys
import time
import types
import pytest

class Config:
    def __init__(self, values): self.values = values
    def model_dump(self, *, mode):
        assert mode == "json"
        return self.values.copy()

worlds = types.ModuleType("support.worlds")
worlds.__file__ = __file__
worlds._cache = {}
worlds._legacy_cache = {}
worlds.LEGACY_CANONICAL = {"legacy": {"mesh.cell_count": 128}}
worlds.canonical_config = lambda key: Config({"kind": "canonical", "key": key})
worlds.build_legacy_config = lambda **kw: Config({"kind": "legacy", **kw})
worlds.build_config = lambda **kw: Config({"kind": "one_off", **kw})
def forbidden_generation(*args, **kwargs):
    raise AssertionError("the diagnostic runner must never generate a world")
worlds.generate_world = forbidden_generation
sys.modules["support.worlds"] = worlds
civilization = types.ModuleType("test_civilization_geography_validation")
civilization.__file__ = __file__
civilization.worlds = worlds
civilization._ONE_OFF_WORLDS = {}
sys.modules["test_civilization_geography_validation"] = civilization

@pytest.fixture
def blocked_teardown():
    yield
    Path(MARKER).write_text("entered")
    deadline = time.monotonic() + 15
    while not Path(RELEASE).exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert Path(RELEASE).exists(), "parent did not release teardown"
'''.replace("MARKER", repr(str(marker))).replace("RELEASE", repr(str(release)))
    (tmp_path / "conftest.py").write_text(fixture_source, encoding="utf-8")
    module = tmp_path / "test_tiny_sweep.py"
    module.write_text('''
import sys
from sweep_local_support import COLLECTION_WITNESS

assert COLLECTION_WITNESS == 731

RAW = {"cells": [{"id": 0, "temperature_c": -0.0, "raw": ["árbol", None, True]}], "summary": {"scope": "fake runner fixture"}}

def test_01_pass():
    worlds = sys.modules["support.worlds"]
    worlds._cache.update({"canonical": RAW, "same_object_alias": RAW})
    worlds._legacy_cache["legacy"] = {"cells": [{"id": 1, "raw": "legacy"}]}
    sys.modules["test_civilization_geography_validation"]._ONE_OFF_WORLDS[(1280, 3015)] = {"cells": [{"id": 2, "raw": "one-off"}]}
    assert True

def test_02_subtest_failure(subtests):
    assert sys.modules["support.worlds"]._cache["canonical"] == RAW
    assert set(RAW) == {"cells", "summary"}
    with subtests.test(msg="durable-subtest", seed=9, nonfinite=float("nan"),
                       infinity=float("inf"), opaque=object(), tuple_value=(1, object())):
        assert False, "subtest-failure-before-teardown"

def test_03_failure(blocked_teardown):
    world = {"cells": [{"id": 8, "raw": "local-before-failure"}], "summary": {},
             "planet_parameters": {"radius_km": 6371.0}}
    alias = world
    assert False, "ordinary-failure-before-teardown"
''', encoding="utf-8")
    argv = [sys.executable, str(RUNNER), "--output-dir", str(output),
            "--archive-failure-worlds",
            "--traceback-interval", "0.1", "--", "-c", str(config), str(module), "-q",
            "--import-mode=importlib"]
    environment = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    with (tmp_path / "child-output.txt").open("w", encoding="utf-8") as stdout:
        process = subprocess.Popen(argv, cwd=tmp_path, env=environment,
                                   stdout=stdout, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 20
            while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            assert marker.exists(), (tmp_path / "child-output.txt").read_text()
            assert process.poll() is None, "the paused teardown must still be running"
            failures = (output / "failures.txt").read_text()
            assert "ordinary-failure-before-teardown" in failures
            assert "subtest-failure-before-teardown" in failures
            assert "durable-subtest" in failures
            completed = [json.loads(line) for line in (output / "completed-nodeids.jsonl").read_text().splitlines()]
            assert len(completed) == 2
            assert completed[0].endswith("test_01_pass")
            assert completed[1].endswith("test_02_subtest_failure")
            events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
            subtest_report = next(event for event in events if event["event"] == "test_report"
                                  and event["outcome"] == "failed" and event["subtest"] is not None)
            context = subtest_report["subtest"]
            assert context["encoding"] == "bounded_repr_of_report_context"
            assert "durable-subtest" in context["message_repr"]
            assert "nan" in context["parameters_repr"]["nonfinite"]
            assert "inf" in context["parameters_repr"]["infinity"]
            assert "object" in context["parameters_repr"]["opaque"]
            assert "1" in context["parameters_repr"]["tuple_value"]
            assert all(isinstance(value, str) for value in context["parameters_repr"].values())
            assert any(event["event"] == "test_end" and event["outcome"] == "failed"
                       and event["nodeid"].endswith("test_02_subtest_failure") for event in events)
            assert not any(event["event"] == "test_end" and event["nodeid"].endswith("test_03_failure")
                           for event in events)

            records = [json.loads(line) for line in (output / "world-archives.jsonl").read_text().splitlines()]
            assert len(records) == 5, "four cache aliases and one failed local world are retained"
            assert len(list((output / "worlds").glob("*.json.gz"))) == 4, "the same world object is written once"
            for record in records:
                raw = gzip.decompress((output / record["world_file"]).read_bytes())
                assert hashlib.sha256(raw).hexdigest() == record["uncompressed_sha256"]
                assert len(raw) == record["uncompressed_bytes"]
                world = json.loads(raw)
                if record["cache"] == "failure_frame":
                    assert world == {"cells": [{"id": 8, "raw": "local-before-failure"}], "summary": {},
                                     "planet_parameters": {"radius_km": 6371.0}}
                    assert record["source_file"] == str(module)
                    assert record["local_name"] in {"world", "alias"}
                    assert record["config_file"] is None
                    assert record["world_provenance"] == "test_local_value_at_failure_may_include_test_mutations"
                    continue
                retained_config = json.loads((output / record["config_file"]).read_text())
                if record["cache"] == "_cache":
                    assert world == {"cells": [{"id": 0, "temperature_c": -0.0, "raw": ["árbol", None, True]}], "summary": {"scope": "fake runner fixture"}}
                    assert b'"temperature_c":-0.0' in raw
                    assert retained_config == {"kind": "canonical", "key": record["key"]}
                elif record["cache"] == "_legacy_cache":
                    assert world == {"cells": [{"id": 1, "raw": "legacy"}]}
                    assert retained_config == {"kind": "legacy", "mesh.cell_count": 128}
                else:
                    assert world == {"cells": [{"id": 2, "raw": "one-off"}]}
                    assert retained_config == {"kind": "one_off", "mesh.cell_count": 1280, "run.seed": 3015}
            trace_deadline = time.monotonic() + 5
            while "blocked_teardown" not in (output / "tracebacks.log").read_text() and time.monotonic() < trace_deadline:
                time.sleep(0.02)
            assert "blocked_teardown" in (output / "tracebacks.log").read_text()
            assert process.poll() is None, "periodic tracebacks must not abort the process"
        finally:
            release.write_text("continue", encoding="utf-8")
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                raise
    assert process.returncode == 1
    completed = [json.loads(line) for line in (output / "completed-nodeids.jsonl").read_text().splitlines()]
    assert len(completed) == 3
    events = [json.loads(line) for line in (output / "events.jsonl").read_text().splitlines()]
    assert events[-1]["event"] == "runner_exit"
    assert events[-1]["exit_status"] == 1
    assert events[-1]["archive_error_count"] == 0
    provenance = json.loads((output / "run.json").read_text())
    assert provenance["requested_pytest_args"] == argv[argv.index("--") + 1:]
    assert provenance["executable"] == sys.executable
    assert "scripts/research/regression_sweep.py" in provenance["source_sha256"]
    collected = json.loads((output / "collected-sources.json").read_text())
    assert collected[str(module)] == hashlib.sha256(module.read_bytes()).hexdigest()
