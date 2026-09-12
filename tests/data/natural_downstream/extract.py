"""Re-extract complete projections only from the exact archived source hashes."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--public-directory',type=Path,required=True)
    parser.add_argument('--scenario-directory',type=Path,required=True)
    args=parser.parse_args()
    directory=Path(__file__).resolve().parent
    manifest=json.loads((directory/'manifest.json').read_text())
    for name,item in manifest['fixtures'].items():
        source=args.public_directory/(name+'.json') if name in ('full_world','geo_only') else args.scenario_directory/(name+'.world.json.gz')
        raw=source.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['source_sha256']:
            raise ValueError(name+': source hash differs')
        world=json.loads(gzip.decompress(raw) if source.suffix=='.gz' else raw)
        projection={k:world[k] for k in manifest['retained_top_fields'] if k in world}
        projection['cells']=[{k:c[k] for k in manifest['retained_cell_fields'] if k in c} for c in world['cells']]
        projection['summary']={k:world['summary'][k] for k in manifest['retained_summary_fields'] if k in world['summary']}
        encoded=(json.dumps(projection,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
        if hashlib.sha256(encoded).hexdigest()!=item['projection_sha256']:
            raise ValueError(name+': projection hash differs')
        (directory/(name+'.json')).write_bytes(encoded)
        print(name+': exact source and projection verified')


if __name__=='__main__':
    main()
