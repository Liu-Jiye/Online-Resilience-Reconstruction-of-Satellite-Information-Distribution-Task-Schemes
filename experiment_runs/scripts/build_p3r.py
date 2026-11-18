"""Initial additive fork only; later audited P3-R refinements live in source."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
dst=ROOT/'src/isl/p3r'
if dst.exists():raise SystemExit('P3-R already exists; refusing to overwrite its developed/frozen runtime')
dst.mkdir()
(dst/'__init__.py').write_text('"""P3-R additive runtime and sparse controller experiment."""\n')
sources={}
for name in ('indexed.py','repair_runtime.py','control.py','control_timed.py','search.py','model_io.py','validation_indexed.py'):
    p=ROOT/'src/isl/p3'/name;text=p.read_text();sources[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    if name=='repair_runtime.py':text=text.replace('0.3.3-p3-indexed-v2','0.4.0-p3r-resource-check')
    if name=='validation_indexed.py':
        text=text.replace('from dataclasses import asdict, dataclass','from dataclasses import asdict, dataclass\nfrom collections import defaultdict')
        text=text.replace('    ids = [p.task_id for p in plan]','    by_resource = defaultdict(set)\n    exact_items = defaultdict(list)\n    for j, item in enumerate(plan):\n        exact_items[item.task_id].append(item)\n        by_resource[item.sender].add(j)\n        by_resource[item.receiver].add(j)\n    ids = [p.task_id for p in plan]')
        text=text.replace('        for j in range(i):','        # Include unknown prior items too: the original checks them against later items.\n        for j in sorted(by_resource[p.sender] | by_resource[p.receiver]):\n            if j >= i: break')
        text=text.replace('    for p in frozen:\n        if sum(q == p for q in plan) != 1:', '    for p in frozen:\n        if sum(q == p for q in exact_items[p.task_id]) != 1:')
        text=text.replace('any(sum(q == p for q in plan) != 1 for p in unchanged)','any(sum(q == p for q in exact_items[p.task_id]) != 1 for p in unchanged)')
    (dst/name).write_text(text,encoding='utf-8')
(dst/'fork_sources.json').write_text(json.dumps(sources,indent=2)+'\n')
print('P3-R fork created')
