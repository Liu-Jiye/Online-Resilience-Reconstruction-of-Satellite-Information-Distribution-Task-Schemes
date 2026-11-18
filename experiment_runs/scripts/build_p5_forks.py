"""Transparent additive forks. Original P3/P3R source bytes stay untouched."""
from p5_common import *

def replace_once(text,old,new):
    assert text.count(old)==1,(old,text.count(old))
    return text.replace(old,new)

def main():
    dest=ROOT/'src/isl/p5';dest.mkdir(exist_ok=True)
    text=(ROOT/'src/isl/p3r/repair_runtime.py').read_text(encoding='utf-8')
    text=text.replace('from .indexed import','from .indexed import').replace('from .validation_indexed import validate as independent_validate','from ..p3r.validation_indexed import validate as independent_validate').replace('from .validation_indexed import validate','from .validation_relaxed import validate')
    text=replace_once(text,'def run_method(case, method=\'Fixed-PALR\', *, w=5, B=None, budget_ms=50, clock=perf_counter_ns):',
        'def run_method(case, method=\'Fixed-PALR\', *, w=5, B=None, budget_ms=50, clock=perf_counter_ns, ignore_window=False, ignore_receiver=False, insertion_only=False, random_ties=False, seed=11):')
    text=replace_once(text,'    timer = Timer(budget_ms, clock)',
        '    import numpy as np\n    from functools import partial\n    checker = validate\n    validate = partial(checker, ignore_window=ignore_window, ignore_receiver=ignore_receiver)\n    rng = np.random.Generator(np.random.PCG64(seed))\n    timer = Timer(budget_ms, clock)')
    # local assignment requires read from alias, not a local name before binding.
    text=text.replace('    checker = validate','    from .validation_relaxed import validate as checker')
    text=replace_once(text,'        instance = IndexedInstance(case.effective_instance())','        instance = IndexedInstance(case.effective_instance(), ignore_window=ignore_window, ignore_receiver=ignore_receiver)')
    text=replace_once(text,"                    removals = sorted((p for p in plan if p.task_id in editable_ids), key=lambda p: p.task_id)",
        "                    removals = [] if insertion_only else sorted((p for p in plan if p.task_id in editable_ids), key=lambda p: p.task_id)")
    text=replace_once(text,'                    best, best_key = None, incumbent_key',
        '                    best, best_key = None, (incumbent_key[:2]+(1.,) if random_ties else incumbent_key)')
    text=replace_once(text,'                            key = objective.edit_key(incumbent_key, removed, item)',
        '                            key = objective.edit_key(incumbent_key, removed, item)\n                            if random_ties:\n                                if key[:2] >= incumbent_key[:2]:continue\n                                key = key[:2]+(float(rng.random()),)')
    text=text.replace("'version': '0.4.0-p3r-resource-check'","'version': 'P5-additive-ablation-v1'")
    text=text.replace("'validated': verified and final_check is not None,","'validated': verified and final_check is not None and final_check.feasible,\n        'ablation_flags':dict(ignore_window=ignore_window,ignore_receiver=ignore_receiver,insertion_only=insertion_only,random_ties=random_ties,seed=seed),")
    (dest/'repair.py').write_text(text,encoding='utf-8')
    v=(ROOT/'src/isl/p3r/validation_indexed.py').read_text(encoding='utf-8')
    v=replace_once(v,'             budget=None, admissions=None, initial=None, trace=None, unchanged=()):',
        '             budget=None, admissions=None, initial=None, trace=None, unchanged=(), ignore_window=False, ignore_receiver=False):')
    v=replace_once(v,'        by_resource[item.receiver].add(j)','        if not ignore_receiver:by_resource[item.receiver].add(j)')
    v=replace_once(v,'        if not any(c.sender == t.sender and c.receiver == t.receiver',
        '        if not ignore_window and not any(c.sender == t.sender and c.receiver == t.receiver')
    v=replace_once(v,'            if b.resource in (p.sender, p.receiver) and p.start < b.end and b.start < p.end:',
        '            if b.resource in ((p.sender,) if ignore_receiver else (p.sender,p.receiver)) and p.start < b.end and b.start < p.end:')
    v=replace_once(v,'        for j in sorted(by_resource[p.sender] | by_resource[p.receiver]):',
        '        for j in sorted(by_resource[p.sender] if ignore_receiver else by_resource[p.sender] | by_resource[p.receiver]):')
    v=replace_once(v,'                for resource in sorted({p.sender, p.receiver} & {q.sender, q.receiver}):',
        '                for resource in sorted(({p.sender} & {q.sender}) if ignore_receiver else {p.sender, p.receiver} & {q.sender, q.receiver}):')
    v=v.replace('unchanged=unchanged).feasible:', 'unchanged=unchanged,ignore_window=ignore_window,ignore_receiver=ignore_receiver).feasible:')
    (dest/'validation_relaxed.py').write_text(v,encoding='utf-8')
    (dest/'__init__.py').write_text('"""P5 additive experimental implementations; frozen historical modules untouched."""\n',encoding='utf-8')
    save(OUT/'fork_provenance.json',dict(inputs={str(p.relative_to(ROOT)):sha(p) for p in [ROOT/'src/isl/p3r/repair_runtime.py',ROOT/'src/isl/p3r/validation_indexed.py']},outputs={str(p.relative_to(ROOT)):sha(p) for p in [dest/'repair.py',dest/'validation_relaxed.py']},generator_sha256=sha(Path(__file__))))

if __name__=='__main__':main()
