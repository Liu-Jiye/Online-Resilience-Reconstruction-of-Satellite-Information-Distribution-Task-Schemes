"""Add explicit local domain, shared deadline and warm incumbent to search fork."""
from p5_common import *
from build_p5_forks import replace_once

def main():
    t=(ROOT/'src/isl/p3r/search.py').read_text(encoding='utf-8')
    t=t.replace('from .indexed import','from ..p3r.indexed import').replace('from .validation_indexed import','from ..p3r.validation_indexed import').replace('from .repair_runtime import','from ..p3r.repair_runtime import')
    t=replace_once(t,'def __init__(self,case,B=5,budget_ms=50):','def __init__(self,case,B=5,budget_ms=50,local_w=None,warm=None):')
    t=replace_once(t,'        self.verified=validate(self.instance,plan,frozen=case.frozen,cancelled=case.event.cancelled).feasible',
        '''        self.unchanged=();self.allowed={t.id for t in self.instance.tasks}
        if local_w is not None:
            _,indices,spans=center_and_region(case,self.instance,local_w)
            editable={case.reference[i].task_id for i in indices}
            self.unchanged=tuple(p for p in plan if p.task_id not in editable)
            self.allowed={t.id for t in self.instance.tasks if t.id in self.original or
                (case.event.urgent and t.id==case.event.urgent.id) or any(t.release<b and a<t.deadline for a,b in spans)}
        if warm is not None and warm['validated']:
            from ..models import Item
            self.initial=tuple(Item(**p) for p in warm['initial_plan'])
            self.plan=tuple(Item(**p) for p in warm['plan'])
            self.trace=list(warm['trace']);self.admissions=warm['admissions_cumulative']
            self.forced=list(warm['forced_removed']);self.objective=Objective(case,self.instance,self.forced)
        self.fixed_ids={p.task_id for p in case.frozen+self.unchanged}
        self.verified=validate(self.instance,self.plan,frozen=case.frozen,cancelled=case.event.cancelled,
            unchanged=self.unchanged,original_ids=self.original,budget=B,admissions=self.admissions,initial=self.initial,trace=self.trace).feasible''')
    t=t.replace('initial=self.initial,trace=trace)','initial=self.initial,trace=trace,unchanged=self.unchanged)')
    t=t.replace('initial=self.initial,trace=self.trace)','initial=self.initial,trace=self.trace,unchanged=self.unchanged)')
    t=t.replace('unchanged=self.unchanged,original_ids=self.original,budget=B,','original_ids=self.original,budget=B,')
    t=t.replace('budget_ms=50,w=None,B=self.B,','budget_ms=(self.end-self.start)/1e6,w=None,B=self.B,')
    t=t.replace('unchanged_outside_E=[],','unchanged_outside_E=[asdict(p) for p in self.unchanged],')
    t=t.replace("frozen={p.task_id for p in engine.case.frozen}","frozen=engine.fixed_ids")
    t=t.replace("t.id not in ids and t.id not in frozen and t.id not in engine.case.event.cancelled", "t.id in engine.allowed and t.id not in ids and t.id not in frozen and t.id not in engine.case.event.cancelled")
    t=replace_once(t,'def run_puct(case,temperature=1.,density_mean=0.,density_std=1.,seed=11):',
        'def run_puct(case,temperature=1.,density_mean=0.,density_std=1.,seed=11,budget_ms=50,B=5,local_w=None,warm=None,simulations=40):')
    t=replace_once(t,'    engine=Engine(case);rng=np.random.Generator(np.random.PCG64(seed));stats=dict(simulations=0',
        '    engine=Engine(case,B,budget_ms,local_w,warm);rng=np.random.Generator(np.random.PCG64(seed));stats=dict(simulations=0')
    t=t.replace("frozen_ids={p.task_id for p in case.frozen};children=[]","frozen_ids=engine.fixed_ids;children=[]")
    t=t.replace('for simulation in range(40):','for simulation in range(simulations):')
    t=replace_once(t,'def run_alns(case,seed=11):','def run_alns(case,seed=11,budget_ms=50,B=5,local_w=None,warm=None):')
    t=replace_once(t,'    engine=Engine(case);rng=np.random.Generator(np.random.PCG64(seed));stats=dict(iterations=0',
        '    engine=Engine(case,B,budget_ms,local_w,warm);rng=np.random.Generator(np.random.PCG64(seed));stats=dict(iterations=0')
    t=t.replace('exhausted=False;frozen_ids={p.task_id for p in case.frozen}', 'exhausted=False;frozen_ids=engine.fixed_ids')
    (ROOT/'src/isl/p5/search.py').write_text(t,encoding='utf-8')
    save(OUT/'search_fork_provenance.json',dict(input_sha256=sha(ROOT/'src/isl/p3r/search.py'),output_sha256=sha(ROOT/'src/isl/p5/search.py'),generator_sha256=sha(Path(__file__))))

if __name__=='__main__':main()
