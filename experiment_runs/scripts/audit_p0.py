"""Recheck P0 hashes and each saved output using the independent checker."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / 'src'))
from isl.models import Item, canonical_json, case_from_dict, case_to_dict
from isl.metrics import scored_metrics
from isl.validation import validate


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(directory):
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    for relative, expected in manifest['source_sha256'].items():
        if sha(REPO / relative) != expected:
            raise ValueError('Source hash mismatch: ' + relative)
    for name, expected in manifest['artifact_sha256'].items():
        if sha(directory / name) != expected:
            raise ValueError('Artifact hash mismatch: ' + name)
    raw_cases = json.loads((directory / 'cases.json').read_text(encoding='utf-8'))
    cases = {raw['event']['id']: case_from_dict(raw) for raw in raw_cases}
    rows = [json.loads(line) for line in (directory / 'results.jsonl').read_text(encoding='utf-8').splitlines()]
    identities = set()
    for row in rows:
        identity = (row['event_id'], row['method'])
        if identity in identities:
            raise ValueError('Duplicate event/method')
        identities.add(identity)
        case = cases[row['event_id']]
        if row['case_sha256'] != hashlib.sha256(canonical_json(case_to_dict(case)).encode()).hexdigest():
            raise ValueError('Case hash mismatch')
        plan = tuple(Item(**p) for p in row['plan'])
        check = validate(case.effective_instance(), plan, frozen=case.frozen, cancelled=case.event.cancelled,
                         original_ids={p.task_id for p in case.reference}, budget=row['B'],
                         admissions=row['admissions_cumulative'],
                         initial=tuple(Item(**p) for p in row['initial_plan']), trace=row['trace'],
                         unchanged=tuple(Item(**p) for p in row['unchanged_outside_E']))
        if not check.feasible:
            raise ValueError('Saved plan failed independent audit: ' + repr(check.errors))
        if canonical_json(check.to_dict()) != canonical_json(row['validation']):
            raise ValueError('Reported check differs from recomputed check')
        minimal_row = next(r for r in rows if r['event_id'] == row['event_id'] and r['method'] == 'Minimal-Repair')
        minimal_plan = tuple(Item(**p) for p in minimal_row['plan'])
        metrics = scored_metrics(case, plan, check, row['total_ns'], int(row['budget_ms'] * 1e6),
                                 row['validated'], row['forced_removed'], minimal_plan)
        if metrics != row['metrics']:
            raise ValueError('Reported metrics differ from recomputed metrics')
        if sum(row['timings_ns'].values()) != row['total_ns'] or min(row['timings_ns'].values()) < 0:
            raise ValueError('Invalid timing breakdown')
    if len(rows) != len(cases) * 3:
        raise ValueError('Missing event/method rows')
    replay = directory / 'single_case_replay.json'
    replay_agrees = None
    if replay.exists():
        one = json.loads(replay.read_text(encoding='utf-8'))
        previous = next(r for r in rows if (r['event_id'], r['method']) == (one['event_id'], one['method']))
        replay_agrees = all(previous[k] == one[k] for k in ('plan', 'trace', 'admissions_cumulative'))
        if not replay_agrees:
            raise ValueError('Single-case replay changed deterministic plan or trace')
    baseline = 'cd2d660ae1952783a39e53c221cdf0343faec050'
    changed = subprocess.check_output(['git', 'diff', '--name-only', baseline, '--'], cwd=REPO, text=True).splitlines()
    if any(not name.startswith('experiment_runs/') for name in changed):
        raise ValueError('Changes outside experiment_runs/')
    evidence = {
        'audited_at_utc': datetime.now(timezone.utc).isoformat(), 'stage': 'P0',
        'source_hashes_verified': len(manifest['source_sha256']),
        'artifact_hashes_verified': len(manifest['artifact_sha256']),
        'event_method_rows_independently_revalidated': len(rows),
        'metrics_and_timing_sums_recomputed': True,
        'deterministic_single_case_replay_agrees': replay_agrees,
        'single_case_replay_sha256': sha(replay) if replay.exists() else None,
        'original_files_outside_experiment_runs_changed': [],
        'audit_script_sha256': sha(Path(__file__)),
        'manifest_sha256': sha(directory / 'manifest.json'),
        'source_commit': manifest['source_commit'], 'passed': True,
    }
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run_directory', type=Path)
    parser.add_argument('--save', type=Path)
    args = parser.parse_args()
    result = audit(args.run_directory.resolve())
    if args.save:
        path = args.save.resolve()
        if not path.is_relative_to(ROOT) or path.exists():
            parser.error('save must be a new path inside experiment_runs/')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
