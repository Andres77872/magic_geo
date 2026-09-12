#!/usr/bin/env python3
"""Extract native certificates without recomputing any physical value.

Input is the JSON emitted by a C++ seasonal climate test executable. Output is
deterministic gzip JSON and a SHA256 manifest. Full-world extraction retains
only fields consumed by independent native-energy linkage; standalone BE/TR
certificate inputs retain their four native objects and need explicit
certificate-only auditing. Tests read the checked-in output, never build/runs.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path


CERTIFICATE_FIELDS = (
    "climate_energy_model", "climate_energy_forcing_intervals",
    "climate_energy_transport_edges", "climate_energy_balance_records",
)
WORLD_FIELDS = ("climate_model", "planet_parameters")
CELL_FIELDS = (
    "id", "position_3d", "area_km2", "lat_deg", "temperature_c",
    "temperature_monthly_c", "is_water", "is_lake", "water_depth_m", "elevation_m",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    raw_source = args.source.read_bytes()
    payload = json.loads(raw_source)
    retained = {field: payload[field] for field in CERTIFICATE_FIELDS}
    if "cells" in payload:
        retained.update({field: payload[field] for field in WORLD_FIELDS})
        retained["cells"] = [{field: cell[field] for field in CELL_FIELDS} for cell in payload["cells"]]
    encoded = (json.dumps(retained, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()
    compressed = gzip.compress(encoded, mtime=0)
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_bytes(compressed)
    manifest = {
        "source_filename": args.source.name,
        "source_sha256": hashlib.sha256(raw_source).hexdigest(),
        "retained_json_sha256": hashlib.sha256(encoded).hexdigest(),
        "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
        "retained_json_bytes": len(encoded), "gzip_bytes": len(compressed),
        "certificate_fields": list(CERTIFICATE_FIELDS),
        "additional_world_fields": [*WORLD_FIELDS, "cells"] if "cells" in retained else [],
        "cell_fields": list(CELL_FIELDS) if "cells" in retained else [],
        "cell_count": len(retained["climate_energy_balance_records"]),
        "time_method": retained["climate_energy_model"]["time_method"],
        "physical_values_recomputed": False,
    }
    args.destination.with_suffix(args.destination.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({"fixture": str(args.destination), "bytes": len(compressed)}))


if __name__ == "__main__":
    main()
