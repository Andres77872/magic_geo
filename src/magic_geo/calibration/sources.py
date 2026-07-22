"""Loading target and source manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ._helpers import _source_items, _target_items, _target_text


def load_calibration_targets(path: Path) -> list[dict[str, Any]]:
    return _target_items(json.loads(path.read_text(encoding="utf-8")))


def load_calibration_sources(path: Path) -> list[dict[str, Any]]:
    sources = _source_items(json.loads(path.read_text(encoding="utf-8")))
    resolved: list[dict[str, Any]] = []
    for source in sources:
        copied = dict(source)
        raw_path = _target_text(copied, "path")
        source_path = Path(raw_path)
        if not source_path.is_absolute():
            source_path = path.parent / source_path
        copied["path"] = str(source_path)
        if "dbf_path" in copied:
            raw_dbf_path = _target_text(copied, "dbf_path")
            dbf_path = Path(raw_dbf_path)
            if not dbf_path.is_absolute():
                dbf_path = path.parent / dbf_path
            copied["dbf_path"] = str(dbf_path)
        if "prj_path" in copied:
            raw_prj_path = _target_text(copied, "prj_path")
            prj_path = Path(raw_prj_path)
            if not prj_path.is_absolute():
                prj_path = path.parent / prj_path
            copied["prj_path"] = str(prj_path)
        resolved.append(copied)
    return resolved
