"""Re-extract the portable stage projections from the exact retained raw worlds.

Usage: python extract.py --source-directory /path/to/exact/full-and-geo-json
This performs no native generation and refuses a different source hash.
"""
import argparse
import hashlib
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-directory", type=Path, required=True)
    args = parser.parse_args()
    output = Path(__file__).resolve().parent
    manifest = json.loads((output / "manifest.json").read_text())
    for name, source in manifest["fixtures"].items():
        raw = (args.source_directory / (name + ".json")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != source["uncompressed_sha256"]:
            raise ValueError(name + ": original world hash differs")
        world = json.loads(raw)
        projection = {key: world[key] for key in manifest["retained_top_fields"] if key in world}
        projection["cells"] = [
            {key: cell[key] for key in manifest["retained_cell_fields"] if key in cell}
            for cell in world["cells"]
        ]
        projection["summary"] = {
            key: world["summary"][key]
            for key in manifest["retained_summary_fields"]
            if key in world["summary"]
        }
        encoded = (json.dumps(projection, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
        if hashlib.sha256(encoded).hexdigest() != source["projection_sha256"]:
            raise ValueError(name + ": projection differs from the recorded extraction")
        (output / (name + ".json")).write_bytes(encoded)
        print(name + ": verified and extracted")


if __name__ == "__main__":
    main()
