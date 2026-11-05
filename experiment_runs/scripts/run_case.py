"""Run a saved P0 ISL case without entering later experimental stages."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import platform

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from isl.models import case_from_dict, case_to_dict, canonical_json
from isl.repair import run_method


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', required=True, type=Path)
    parser.add_argument('--index', type=int, default=0, help='Index if input is a case list')
    parser.add_argument('--method', choices=['Fixed-PALR', 'Minimal-Repair', 'Frozen-Greedy'], default='Fixed-PALR')
    parser.add_argument('--w', type=int, default=5)
    parser.add_argument('--B', type=int)
    parser.add_argument('--budget-ms', type=float, default=50)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    target = args.output.resolve()
    if not target.is_relative_to(ROOT):
        parser.error('output must remain inside experiment_runs/')
    if target.exists():
        parser.error('output already exists; preserve prior evidence')
    raw = json.loads(args.case.read_text(encoding='utf-8'))
    case = case_from_dict(raw[args.index] if isinstance(raw, list) else raw)
    result = run_method(case, args.method, w=args.w, B=args.B, budget_ms=args.budget_ms)
    result['case'] = case_to_dict(case)
    result['case_sha256'] = hashlib.sha256(canonical_json(result['case']).encode()).hexdigest()
    result['source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    result['python_version'] = platform.python_version()
    result['platform'] = platform.platform()
    result['source_sha256'] = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted((ROOT / 'src').rglob('*.py'))}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({'status': result['status'], 'online_success': result['metrics']['online_success'],
                      'output': str(target)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
