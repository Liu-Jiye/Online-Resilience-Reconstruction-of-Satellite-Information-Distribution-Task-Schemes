"""Screen cached objects and register groups, no test-instance generation."""
from pathlib import Path
import json
import hashlib
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from isl.p1_orbits import screen, split_groups
from isl.p1_sources import save_json


def main():
    config = json.loads((ROOT / 'configs/p1.json').read_text(encoding='utf-8'))
    for name in ('starlink', 'oneweb'):
        destination = ROOT / f'data/processed/p1/{name}_eligible.json'
        if destination.exists():
            raise SystemExit('Prepared selection already exists; do not overwrite')
        payload = (ROOT / config['source_directory'] / f'{name}.json').read_bytes()
        fetched = json.loads((ROOT / config['source_directory'] / f'{name}.fetch.json').read_text())
        if hashlib.sha256(payload).hexdigest() != fetched['sha256']:
            raise ValueError('Original snapshot hash mismatch')
        records = json.loads(payload)
        eligible, origin, report = screen(records)
        save_json(ROOT / f'reports/p1/{name}_screening.json', report)
        if len(eligible) < 320:
            raise SystemExit('Too few eligible objects; request protocol decision')
        groups = split_groups(eligible, config['group_shuffle_seeds'][name])
        save_json(destination, {'t_ref_utc': origin.isoformat(), 'records': eligible})
        save_json(ROOT / f'reports/p1/{name}_groups.json', {'seed': config['group_shuffle_seeds'][name],
            'groups': groups, 'selected_objects': 320, 'unique_objects': 320,
            'split_intersections': {'train_validation': [], 'train_test': [], 'validation_test': []},
            'test_instance_generation': False})
        print(json.dumps({'constellation': name, **report['counts'], 't_ref': origin.isoformat()}), flush=True)


if __name__ == '__main__':
    main()
