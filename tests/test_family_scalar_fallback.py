"""Scalar views of retained JSONL-only caches; no generation or re-export."""

from contextlib import contextmanager
from copy import deepcopy
import json

import pytest
from fastapi import HTTPException

from magic_geo.debug_server import _DebugCache
from test_debug_server import _make_cache, _mutate_manifest


@contextmanager
def jsonl_cache(root, records):
    cache_dir = _make_cache(root)
    path = cache_dir / "events/scalar-control.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")
    _mutate_manifest(cache_dir, lambda manifest: manifest["families"].update({
        "scalar_control": {"kind": "jsonl", "jsonl": "events/scalar-control.jsonl", "row_count": len(records)},
        "empty_control": {"kind": "empty", "row_count": 0,
                          "availability": {"complete": True, "field": "test_selection_complete", "scope": "complete_source_domain"}},
    }))
    before = path.read_bytes()
    cache = _DebugCache(cache_dir)
    try:
        yield cache
    finally:
        cache.close()
        assert path.read_bytes() == before


def test_one_region_scalar_view_omits_cell_ids_but_keeps_null_mean_and_known_zero(tmp_path):
    record = {
        "id": 0, "cell_count": 128, "cell_ids": list(range(128)),
        "region_class": "no_marine_source", "mean_distance_to_marine_water_km": None,
        "marine_distance_defined_cell_count": 0, "no_marine_source_cell_count": 128,
        "mean_oceanic_humidity_availability_index": 0.0, "has_marine_source": False,
    }
    with jsonl_cache(tmp_path, [record]) as cache:
        result = cache.family_rows("scalar_control", 10, 0, "scalars")
        assert result["detail"] == "scalars"
        assert result["rows"] == [{key: value for key, value in record.items() if key != "cell_ids"}]
        assert result["total"] == 1 and result["next_offset"] is None
        assert cache.family_rows("scalar_control", 10, 0, "full")["rows"] == [record]


def test_few_scalar_columns_preserve_jsonl_pagination_and_full_rows(tmp_path):
    records = [{"id": index, "payload": {"step": index}} for index in range(3)]
    with jsonl_cache(tmp_path, records) as cache:
        middle = cache.family_rows("scalar_control", 1, 1, "scalars")
        assert middle["rows"] == [{"id": 1}]
        assert (middle["detail"], middle["total"], middle["offset"], middle["limit"], middle["next_offset"]) == ("scalars", 3, 1, 1, 2)
        last = cache.family_rows("scalar_control", 1, 2, "scalars")
        assert last["rows"] == [{"id": 2}] and last["next_offset"] is None
        beyond = cache.family_rows("scalar_control", 1, 3, "scalars")
        assert beyond["rows"] == [] and beyond["next_offset"] is None
        assert cache.family_rows("scalar_control", 3, 0, "full")["rows"] == records


def test_nested_only_rows_remain_empty_records_in_scalar_page(tmp_path):
    records = [{"payload": {"a": 1}}, {"steps": [1, 2]}]
    with jsonl_cache(tmp_path, records) as cache:
        first = cache.family_rows("scalar_control", 1, 0, "scalars")
        assert first["rows"] == [{}] and first["next_offset"] == 1
        last = cache.family_rows("scalar_control", 1, 1, "scalars")
        assert last["rows"] == [{}] and last["next_offset"] is None
        assert cache.family_rows("scalar_control", 2, 0, "full")["rows"] == records


def test_boolean_availability_flags_survive_with_page_column_backfill(tmp_path):
    records = [
        {"id": 0, "score": None, "estimate_availability": {"score": False, "other": "undeclared"}, "payload": [1]},
        {"id": 1, "score": 0.0, "estimate_availability": {"score": True}, "source_availability": {"temperature": False}},
    ]
    original = deepcopy(records)
    with jsonl_cache(tmp_path, records) as cache:
        result = cache.family_rows("scalar_control", 2, 0, "scalars")
        assert result["rows"] == [
            {"id": 0, "score": None, "estimate_availability.score": False, "source_availability.temperature": None},
            {"id": 1, "score": 0.0, "estimate_availability.score": True, "source_availability.temperature": False},
        ]
        assert cache.family_rows("scalar_control", 2, 0, "full")["rows"] == original
    assert records == original


@pytest.mark.parametrize("collision", ["same_row", "other_row", "derived_name"])
def test_scalar_availability_name_collisions_refuse_without_changing_full_records(tmp_path, collision):
    records = [{"id": 0, "estimate_availability": {"score": False}}]
    if collision == "same_row":
        records[0]["estimate_availability.score"] = True
    elif collision == "other_row":
        records.append({"id": 1, "estimate_availability.score": True})
    else:
        records[0] = {
            "estimate_availability": {"source_availability.score": False},
            "estimate_availability.source_availability": {"score": True},
        }
    with jsonl_cache(tmp_path, records) as cache:
        with pytest.raises(HTTPException, match="scalar availability") as caught:
            cache.family_rows("scalar_control", 10, 0, "scalars")
        assert caught.value.status_code == 500
        assert cache.family_rows("scalar_control", 10, 0, "full")["rows"] == records


def test_flat_parquet_and_empty_families_keep_existing_detail_semantics(tmp_path):
    with jsonl_cache(tmp_path, []) as cache:
        for name in ("flat", "empty_control"):
            full = cache.family_rows(name, 10, 0, "full")
            scalars = cache.family_rows(name, 10, 0, "scalars")
            assert scalars == full
            assert scalars["detail"] == "full"
