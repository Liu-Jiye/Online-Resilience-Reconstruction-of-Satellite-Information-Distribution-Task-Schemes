"""Run only P0 correctness acceptance and save small, versioned evidence.

From repository root:
  experiment_runs/.venv/Scripts/python.exe experiment_runs/scripts/run_p0.py
No orbit downloads, dataset pilots, solver studies, tuning or main tests.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(ROOT / 'src'))

from isl import __version__
from isl.models import Busy, Case, Contact, Instance, Item, Task, case_to_dict, canonical_json, frozen_count
from isl.events import generate_event
from isl.metrics import aggregate, raw_metrics
from isl.reference import create_reference
from isl.repair import run_method


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def command(args):
    return subprocess.check_output(args, cwd=REPO, text=True, encoding='utf-8').strip()


def hashes(paths):
    return {p.relative_to(REPO).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def fixture():
    # Hand-authored correctness fixture: not sampled from a research dataset.
    pairs = [('A', 'B'), ('C', 'B'), ('A', 'D'), ('C', 'D')]
    tasks = tuple(Task(f't{i:02d}', a, b, (i % 4) * 20, 120 + (i % 3) * 40,
                       (i % 3 + 1) * 500_000_000, 100_000_000, 20 + 7 * i)
                  for i, (a, b) in enumerate(pairs * 3))
    contacts = tuple(Contact(f'c{i}', a, b, 0, 240) for i, (a, b) in enumerate(pairs))
    return Instance('P0-hand-authored-001', ('A', 'B', 'C', 'D'), tasks, contacts,
                    (Busy('A', 30, 60), Busy('B', 90, 120)), 5400)


def environment():
    freeze = command([sys.executable, '-m', 'pip', 'freeze'])
    info = {
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'python_version': platform.python_version(), 'python_executable': sys.executable,
        'os': platform.platform(), 'machine': platform.machine(),
        'processor': platform.processor(), 'logical_cpu_count': os.cpu_count(),
        'python_implementation': platform.python_implementation(),
        'clock': {'name': 'perf_counter_ns', 'resolution_s': __import__('time').get_clock_info('perf_counter').resolution},
        'pip_freeze': freeze.splitlines(), 'method_worker_threads': 1,
        'threading_note': 'No parallel repair workers; OS process/native library thread counts are not pinned.',
        'affinity_pinned': False, 'frequency_policy': 'not_controlled',
        'container_image_digest': None, 'gpu_used': False,
        'target_main_environment_met': False,
        'scope': 'P0 correctness acceptance only; Windows/Python3.14 timings are not main-evaluation evidence',
    }
    if os.name == 'nt':
        script = "$cpu = @(Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors); $computer = Get-CimInstance Win32_ComputerSystem; @{cpu=$cpu; total_physical_memory_bytes=$computer.TotalPhysicalMemory} | ConvertTo-Json -Depth 4 -Compress"
        result = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True)
        info['hardware_query_exit_code'] = result.returncode
        if result.returncode == 0:
            info['hardware'] = json.loads(result.stdout)
        else:
            info['hardware_query_error'] = result.stderr.strip()
    return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-id', default=datetime.now(timezone.utc).strftime('P0-%Y%m%dT%H%M%SZ'))
    args = parser.parse_args()
    if not args.run_id.startswith('P0-') or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.run_id):
        raise SystemExit('run-id must be a safe P0-prefixed basename')
    destination = ROOT / 'reports' / 'p0' / args.run_id
    destination.mkdir(parents=True, exist_ok=False)
    config = json.loads((ROOT / 'configs/p0.json').read_text(encoding='utf-8'))
    dump(destination / 'config.json', config)
    source_paths = list((ROOT / 'src').rglob('*.py')) + list((ROOT / 'tests').rglob('*.py'))
    source_paths += list((ROOT / 'scripts').glob('*.py'))
    source_paths += [ROOT / 'configs/p0.json', ROOT / 'environment/requirements-p0.lock.txt',
                     ROOT / 'protocol/P0_IMPLEMENTATION_CONTRACT.md']
    source_hashes = hashes(source_paths)
    dump(destination / 'environment.json', environment())
    junit_path = destination / 'pytest.xml'
    completed = subprocess.run([sys.executable, '-m', 'pytest', str(ROOT / 'tests'), '-q',
                                '-p', 'no:cacheprovider', '--junitxml', str(junit_path)],
                               cwd=REPO, capture_output=True, text=True, encoding='utf-8')
    (destination / 'pytest.txt').write_text(completed.stdout + completed.stderr, encoding='utf-8')
    if completed.returncode != 0:
        raise SystemExit(f'P0 acceptance tests failed; evidence saved to {destination}')
    suite = ET.parse(junit_path).getroot()
    tests = sum(int(s.attrib.get('tests', 0)) for s in suite.findall('testsuite'))
    instance = fixture()
    reference, reference_info = create_reference(instance)
    dump(destination / 'reference.json', {'instance': asdict(instance), 'reference': [asdict(p) for p in reference],
                                        'construction': reference_info})
    cases = []
    counter = config['event_seed_start']
    for kind in ('cancellation', 'urgent_insertion', 'reward_update'):
        for ratio in config['frozen_ratios']:
            for q in config['intensities']:
                event = generate_event(instance, reference, kind, ratio, q, counter)
                cases.append(Case(instance, reference, event, frozen_count(reference, ratio)))
                counter += 1
    dump(destination / 'cases.json', [case_to_dict(case) for case in cases])
    # Preheat correctness fixture only; it has no train/validation/test meaning.
    for i in range(config['warmup_calls']):
        run_method(cases[i % len(cases)], config['methods'][i % len(config['methods'])])
    rows = []
    for i, case in enumerate(cases):
        by_method = {}
        # Deterministic rotation avoids always executing a method first; no
        # statistical latency comparison is made on this micro fixture.
        methods = config['methods'][i % 3:] + config['methods'][:i % 3]
        for method in methods:
            result = run_method(case, method, budget_ms=config['response_budget_ms'])
            result['case_sha256'] = hashlib.sha256(canonical_json(case_to_dict(case)).encode()).hexdigest()
            if result['validation'] is not None and not result['validation']['feasible']:
                raise AssertionError(result['validation'])
            by_method[method] = result
        minimal = tuple(Item(**p) for p in by_method['Minimal-Repair']['plan'])
        baseline = raw_metrics(case, minimal, by_method['Minimal-Repair']['forced_removed'])['U_raw']
        for result in by_method.values():
            metrics = result['metrics']
            delta = metrics['U'] - baseline if metrics['U'] is not None else None
            metrics.update({'U_min': baseline, 'delta_U': delta,
                            'normalized_delta_U': delta / max(1, baseline) if delta is not None else None})
            rows.append(result)
    (destination / 'results.jsonl').write_text(''.join(canonical_json(r) + '\n' for r in rows), encoding='utf-8')
    dump(destination / 'summary.json', {
        'stage': 'P0', 'unit_tests_passed': tests, 'cases': len(cases), 'method_calls': len(rows),
        'scope': 'correctness_smoke_only_not_research_performance',
        'by_method': {method: aggregate([r for r in rows if r['method'] == method]) for method in config['methods']},
        'statuses': {status: sum(r['status'] == status for r in rows) for status in sorted({r['status'] for r in rows})},
        'next_stages_executed': [],
    })
    manifest = {
        'stage': 'P0', 'implementation_version': __version__, 'protocol_version': '1.0',
        'run_id': args.run_id, 'finished_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_commit': command(['git', 'rev-parse', 'HEAD']),
        'git_status_at_capture': command(['git', 'status', '--porcelain']),
        'source_sha256': source_hashes,
        'command': [sys.executable, *sys.argv],
        'artifact_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted(destination.iterdir()) if p.is_file()},
        'all_acceptance_tests_passed': True,
        'scientific_results_available': False,
        'instance_seed': None,
        'instance_seed_reason': 'Hand-authored deterministic micro fixture; no random instance generator was run.',
        'event_seed_interval': [config['event_seed_start'], counter - 1],
        'search_seed': None,
        'search_seed_reason': 'All three P0 methods are deterministic; no stochastic search is implemented here.',
    }
    dump(destination / 'manifest.json', manifest)
    print(json.dumps({'run_directory': str(destination), 'unit_tests_passed': tests,
                      'cases': len(cases), 'method_calls': len(rows)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
