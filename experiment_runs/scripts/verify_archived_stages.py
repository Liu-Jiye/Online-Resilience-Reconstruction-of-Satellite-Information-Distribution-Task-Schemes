"""Read-only byte checks of P3/P3-R/P4; no new plan replay or timing."""
import json
from pathlib import Path
from verify_delivery import digest, checked_path

ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def verify():
    results = {}
    for stage, folder, key, repo_relative in [
        ('P3', 'p3/P3-20261110', 'file_sha256', True),
        ('P3-R', 'p3r/P3R-20261112', 'files', False),
        ('P4', 'p4/P4-20261117', 'files', False),
    ]:
        run = ROOT / 'reports' / folder
        entries = load(run / 'acceptance_manifest.json')[key]
        for name, value in entries.items():
            if repo_relative:
                if not name.startswith('experiment_runs/'):
                    raise ValueError(f'Unexpected evidence path: {name}')
                name = name.removeprefix('experiment_runs/')
            path = checked_path(name)
            expected = value['sha256'] if isinstance(value, dict) else value
            if digest(path) != expected:
                raise ValueError(f'{stage} hash mismatch: {name}')
            if isinstance(value, dict) and path.stat().st_size != value['bytes']:
                raise ValueError(f'{stage} byte count mismatch: {name}')
        if load(run / 'final_audit.json').get('passed') is not True:
            raise ValueError(f'{stage} archived audit did not pass')
        freeze_name = {'P3': None, 'P3-R': 'validation_freeze.json', 'P4': 'test_freeze.json'}[stage]
        frozen_count = 0
        if freeze_name:
            frozen = load(run / freeze_name)['sha256']
            for name, value in frozen.items():
                if digest(checked_path(name)) != value:
                    raise ValueError(f'{stage} frozen source mismatch: {name}')
            frozen_count = len(frozen)
        results[stage] = dict(passed=True, acceptance_files=len(entries), source_freeze_files=frozen_count,
                              archived_independent_audit_passed=True)
        print(json.dumps({stage: results[stage]}), flush=True)
    return dict(passed=True, stages=results,
                verification_scope='Byte integrity and preserved audit certificates; no new semantic replay or timing.')


if __name__ == '__main__':
    print(json.dumps(verify(), indent=2))
