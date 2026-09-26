"""The progress channel is optional, framed and independent of generation data."""

import io
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from magic_geo.generation_progress import emit_progress


@pytest.mark.parametrize("enabled", [None, "0", "true"])
def test_progress_is_silent_unless_explicitly_enabled(monkeypatch, capsys, enabled):
    if enabled is None:
        monkeypatch.delenv("MAGIC_GEO_PROGRESS", raising=False)
    else:
        monkeypatch.setenv("MAGIC_GEO_PROGRESS", enabled)
    emit_progress("mesh", "Building cells", current=1, total=12)
    assert capsys.readouterr() == ("", "")


def test_progress_records_escape_text_and_only_count_known_work(monkeypatch, capsys):
    monkeypatch.setenv("MAGIC_GEO_PROGRESS", "1")
    emit_progress("climate", 'A "seasonal" cycle', "Month\n🌎", current=3, total=12)
    emit_progress("geometry", "Assembling world", current=100)
    output = capsys.readouterr()
    assert output.out == ""
    lines = output.err.splitlines()
    assert len(lines) == 2
    records = [json.loads(line.removeprefix("MAGIC_GEO_PROGRESS ")) for line in lines]
    assert records == [
        {"phase": "climate", "label": 'A "seasonal" cycle', "detail": "Month\n🌎", "current": 3, "total": 12},
        {"phase": "geometry", "label": "Assembling world", "detail": ""},
    ]


def test_concurrent_progress_remains_one_record_per_line(monkeypatch, capsys):
    monkeypatch.setenv("MAGIC_GEO_PROGRESS", "1")
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda index: emit_progress("stage", f"Record {index}"), range(24)))
    lines = capsys.readouterr().err.splitlines()
    assert len(lines) == 24
    records = [json.loads(line.removeprefix("MAGIC_GEO_PROGRESS ")) for line in lines]
    assert {event["label"] for event in records} == {f"Record {index}" for index in range(24)}


def test_closed_diagnostic_stream_does_not_fail_generation(monkeypatch):
    monkeypatch.setenv("MAGIC_GEO_PROGRESS", "1")
    closed_stream = io.StringIO()
    closed_stream.close()
    monkeypatch.setattr("magic_geo.generation_progress.sys.stderr", closed_stream)
    emit_progress("stage", "Working")
