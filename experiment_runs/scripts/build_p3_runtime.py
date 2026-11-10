"""Produce an auditable, additive fork using exact checked replacements."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
source=ROOT/'src/isl/repair_v2.py'
text=source.read_text(encoding='utf-8')
changes=[]

# Same full checker, with local resource indexes; independent original checker
# is still used for original-reference validation and final response validation.
checker_source=ROOT/'src/isl/validation.py'
checker=checker_source.read_text(encoding='utf-8').replace('from .models import Item','from ..models import Item')
checker=checker.replace('    tasks = instance.task_map', '''    tasks = instance.task_map
    contacts_by_pair = {}
    calendar_by_resource = {}
    for contact in instance.contacts:
        contacts_by_pair.setdefault((contact.sender, contact.receiver), []).append(contact)
    for calendar_index, busy in enumerate(instance.calendar):
        calendar_by_resource.setdefault(busy.resource, []).append((calendar_index, busy))''')
checker=checker.replace('for c in instance.contacts):','for c in contacts_by_pair.get((t.sender, t.receiver), ())):')
checker=checker.replace('        for b in instance.calendar:', '''        relevant_calendar = sorted(dict(calendar_by_resource.get(p.sender, []) + calendar_by_resource.get(p.receiver, [])).items())
        for _, b in relevant_calendar:''')
checker_target=ROOT/'src/isl/p3/validation_indexed.py'
checker_target.write_text(checker,encoding='utf-8',newline='\n')


def change(old,new,count=1):
    global text
    assert text.count(old)==count,old
    text=text.replace(old,new)
    changes.append({'old':old,'new':new,'count':count})


for module in ('models','placement','validation','metrics'):
    change(f'from .{module} import', f'from ..{module} import')
change('from ..placement import earliest, opportunities','from .indexed import IndexedInstance, Objective, earliest, opportunities')
change('from ..validation import validate','from .validation_indexed import validate as independent_validate\nfrom .validation_indexed import validate')
change('        self.end = self.start + self.budget_ns','        self.end = self.start + self.budget_ns\n        self.reserve_ns = 0')
change('        if self.clock() >= self.end:', '        if self.clock() >= self.end - self.reserve_ns:')
change('        base_check = validate(case.base, case.reference)',
       '        base_check_begin = clock()\n        base_check = independent_validate(case.base, case.reference)\n        base_check_ns = clock() - base_check_begin')
change("    instance = None\n", "    instance = None\n    objective = None\n\n    def selection_key(case_unused, candidate, forced_unused=()):\n        return objective.key(candidate)\n")
change('        instance = case.effective_instance()', '        instance = IndexedInstance(case.effective_instance())')
old='''            baseline = list(case.frozen)
            for p in case.reference[case.frozen_count:]:
                timer.guard()
                if p.task_id in case.event.cancelled:
                    continue
                check = validate(instance, ordered(tuple(baseline) + (p,)))
                if check.feasible:
                    baseline.append(p)
                else:
                    forced.append(p.task_id)
                    forced_reasons[p.task_id] = list(check.errors)
'''
new='''            complete_baseline = tuple(p for p in case.reference if p.task_id not in case.event.cancelled)
            bulk_check = validate(instance, complete_baseline)
            timer.guard()
            if bulk_check.feasible:
                baseline = list(complete_baseline)
            else:
                baseline = list(case.frozen)
                for p in case.reference[case.frozen_count:]:
                    timer.guard()
                    if p.task_id in case.event.cancelled:
                        continue
                    check = validate(instance, ordered(tuple(baseline) + (p,)))
                    if check.feasible:
                        baseline.append(p)
                    else:
                        forced.append(p.task_id)
                        forced_reasons[p.task_id] = list(check.errors)
'''
change(old,new)
change('            plan, verified = initial, True', '            plan, verified = initial, True\n            objective = Objective(case, instance, forced)\n            timer.reserve_ns = max(1_000_000, 3 * base_check_ns) if base_check_ns else 0')
change('        candidate_trace = trace + [step]',
       '        candidate_trace = trace + [step]\n        timer.reserve_ns = max(timer.reserve_ns, int(2 * reserve_probe_ns * (len(candidate_trace)+2) / 2)) if reserve_probe_ns else timer.reserve_ns')
change('    objective = None\n','    objective = None\n    reserve_probe_ns = 0\n')
change('            cancelled = set(case.event.cancelled)', '''            probe_begin = clock()
            probe_check = validate(instance, plan, frozen=case.frozen, cancelled=case.event.cancelled,
                original_ids=original_ids, budget=B, admissions=admissions, initial=initial, trace=trace, unchanged=unchanged)
            reserve_probe_ns = clock() - probe_begin
            if not probe_check.feasible:
                raise AssertionError(probe_check.errors)
            timer.reserve_ns = max(timer.reserve_ns, 2 * reserve_probe_ns)
            cancelled = set(case.event.cancelled)''')
change('        final_check = validate(instance, plan, frozen=case.frozen, cancelled=case.event.cancelled,',
       '        final_check = independent_validate(instance.original, plan, frozen=case.frozen, cancelled=case.event.cancelled,')
change('                    best, best_key = None, selection_key(case, plan, forced)',
       '                    incumbent_key = selection_key(case, plan, forced)\n                    best, best_key = None, incumbent_key')
change('                            key = selection_key(case, candidate, forced)',
       '                            key = objective.edit_key(incumbent_key, removed, item)')
change("'version': '0.2.0-urgent-eligibility-v2'", "'version': '0.3.3-p3-indexed-v2'")
text='"""P3 additive equivalent runtime fork. Generated by build_p3_runtime.py; see transformation receipt."""\n'+text
target=ROOT/'src/isl/p3/repair_runtime.py'
target.write_text(text,encoding='utf-8',newline='\n')
receipt={'source':str(source.relative_to(ROOT)),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
         'output':str(target.relative_to(ROOT)),'output_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
         'changes':changes,'checker_source_sha256':hashlib.sha256(checker_source.read_bytes()).hexdigest(),
         'indexed_checker_sha256':hashlib.sha256(checker_target.read_bytes()).hexdigest(),
         'deadline_semantics':'50ms total unchanged; timed full current-state audit probe reserves2x audit time, scaled by trace length+2 over2 before acceptance; late output still timeout'}
(ROOT/'reports/p3/P3-20261110/runtime_transformation.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
