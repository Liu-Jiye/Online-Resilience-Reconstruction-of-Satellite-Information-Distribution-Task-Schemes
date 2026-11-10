"""Full editable suffix PUCT and ALNS adaptations, with cumulative admission audit."""
from dataclasses import asdict,dataclass
from fractions import Fraction
from math import ceil,sqrt
from time import perf_counter_ns
import numpy as np
from ..models import ordered
from ..metrics import scored_metrics
from .indexed import IndexedInstance,Objective,earliest,opportunities
from .validation_indexed import validate
from .repair_runtime import DeadlineReached,center_and_region


class Engine:
    def __init__(self,case,B=5,budget_ms=50):
        self.start=perf_counter_ns(); self.end=self.start+int(budget_ms*1e6)
        self.case=case;self.B=B;self.trace=[];self.admissions=0;self.forced=[]
        self.plan=();self.initial=();self.verified=False;self.conflict=False
        self.instance=IndexedInstance(case.effective_instance())
        begin=perf_counter_ns();check=validate(case.base,case.reference)
        self.check_ns=max(100_000,perf_counter_ns()-begin)
        if not check.feasible: raise ValueError('invalid original reference')
        self.reserve=3*self.check_ns
        check=validate(self.instance,case.frozen,frozen=case.frozen,cancelled=case.event.cancelled)
        if not check.feasible:
            self.conflict=True;self.input_ns=perf_counter_ns()-self.start;return
        plan=tuple(p for p in case.reference if p.task_id not in case.event.cancelled)
        if not validate(self.instance,plan).feasible:
            plan=case.frozen
            for p in case.reference[case.frozen_count:]:
                self.guard()
                if p.task_id in case.event.cancelled:continue
                candidate=ordered(plan+(p,))
                if validate(self.instance,candidate).feasible:plan=candidate
                else:self.forced.append(p.task_id)
        self.initial=self.plan=plan
        self.original={p.task_id for p in case.reference}
        self.objective=Objective(case,self.instance,self.forced)
        self.verified=validate(self.instance,plan,frozen=case.frozen,cancelled=case.event.cancelled).feasible
        self.input_ns=perf_counter_ns()-self.start

    def guard(self):
        if perf_counter_ns()>=self.end-self.reserve:raise DeadlineReached

    def edit(self,candidate):
        before={p.task_id:p for p in self.plan};after={p.task_id:p for p in candidate}
        return dict(removed=sorted(t for t in before if before[t]!=after.get(t)),
                    added=[asdict(after[t]) for t in sorted(after) if before.get(t)!=after[t]])

    def cost(self,candidate):
        before={p.task_id:p for p in self.plan}
        return self.admissions+sum(p.task_id not in self.original and before.get(p.task_id)!=p for p in candidate)

    def accept(self,candidate):
        self.guard()
        if self.objective.key(candidate)>=self.objective.key(self.plan):return False
        step=self.edit(candidate);count=self.cost(candidate)
        if count>self.B:return False
        trace=self.trace+[step]
        self.reserve=max(self.reserve,(len(trace)+3)*self.check_ns)
        self.guard()
        check=validate(self.instance,candidate,frozen=self.case.frozen,cancelled=self.case.event.cancelled,
                       original_ids=self.original,budget=self.B,admissions=count,initial=self.initial,trace=trace)
        self.guard()
        assert check.feasible,check.errors
        self.plan=candidate;self.admissions=count;self.trace=trace
        return True

    def finish(self,method,stats,exhausted):
        before=perf_counter_ns();check=None
        if self.verified and not self.conflict:
            check=validate(self.instance.original,self.plan,frozen=self.case.frozen,cancelled=self.case.event.cancelled,
                original_ids=self.original,budget=self.B,admissions=self.admissions,initial=self.initial,trace=self.trace)
        end=perf_counter_ns();total=end-self.start;final_ns=end-before
        metrics=scored_metrics(self.case,self.plan,check,total,self.end-self.start,self.verified and not self.conflict,self.forced)
        return dict(method=method,version='P3-search-v1',eligibility_version='v2',event_id=self.case.event.id,
            instance_id=self.case.base.id,status='frozen_conflict' if self.conflict else 'timeout' if total>self.end-self.start or not self.verified else 'feasible',
            stop_reason='cooperative_deadline' if exhausted else 'search_limit_or_exhausted',budget_ms=50,w=None,B=self.B,
            initial_plan=[asdict(p) for p in self.initial],plan=[asdict(p) for p in self.plan],trace=self.trace,
            admissions_cumulative=self.admissions,forced_removed=self.forced,unchanged_outside_E=[],validated=check is not None and check.feasible,
            validation=check.to_dict() if check else None,total_ns=total,metrics=metrics,search_stats=stats,
            timings_ns=dict(input_and_baseline_ns=getattr(self,'input_ns',0),
                            search_ns=total-getattr(self,'input_ns',0)-final_ns,final_validation_ns=final_ns))


def candidate_tasks(engine,plan):
    ids={p.task_id for p in plan};frozen={p.task_id for p in engine.case.frozen}
    urgent=engine.case.event.urgent
    return sorted((t for t in engine.instance.tasks if t.id not in ids and t.id not in frozen and t.id not in engine.case.event.cancelled),
                  key=lambda t:(not (urgent and urgent.id==t.id),t.density_key))


def run_puct(case,temperature=1.,density_mean=0.,density_std=1.,seed=11):
    engine=Engine(case);rng=np.random.Generator(np.random.PCG64(seed));stats=dict(simulations=0,max_depth=0,expanded_nodes=0,temperature=temperature,seed=seed)
    exhausted=False
    # Node fields: plan, children, visits, value sum, prior. Tree values use known
    # event utility upper bound, never CP-SAT or future-event information.
    root=dict(plan=engine.plan,children=None,n=0,value=0.,prior=1.)
    utility_bound=max(1,sum(t.utility for t in engine.instance.tasks))

    def expand(node):
        plan=node['plan'];frozen_ids={p.task_id for p in case.frozen};children=[]
        ranked=candidate_tasks(engine,plan)
        removable=sorted((p for p in plan if p.task_id not in frozen_ids),key=lambda p:(engine.instance.task_map[p.task_id].utility/engine.instance.task_map[p.task_id].duration,p.task_id))
        for t in ranked:
            engine.guard()
            if t.id not in engine.original and engine.cost(plan)>=engine.B:continue
            choices=[None]+removable
            for removed in choices:
                engine.guard()
                reduced=plan if removed is None else tuple(p for p in plan if p!=removed)
                item=earliest(engine.instance,t,reduced,engine.guard)
                if item is None:continue
                candidate=ordered(reduced+(item,))
                if engine.cost(candidate)>engine.B:continue
                z=(t.utility/t.duration-density_mean)/max(density_std,1e-12)
                children.append(dict(plan=candidate,children=None,n=0,value=0.,log_prior=z/temperature))
                break
            if len(children)>=20:break
        if children:
            logits=np.asarray([n.pop('log_prior') for n in children]);p=np.exp(logits-logits.max());p/=p.sum()
            for n,prior in zip(children,p):n['prior']=float(prior)*.99
        children.append(dict(plan=plan,children=[],n=0,value=0.,prior=.01,stop=True))
        node['children']=children;stats['expanded_nodes']+=1

    try:
        if engine.verified and not engine.conflict and case.event.applicable:
            for simulation in range(40):
                engine.guard();node=root;path=[root]
                for depth in range(12):
                    engine.guard()
                    if node['children'] is None:expand(node)
                    if not node['children']:break
                    scores=[(n['value']/n['n'] if n['n'] else 0.)+1.5*n['prior']*sqrt(max(1,node['n']))/(1+n['n']) for n in node['children']]
                    best=max(scores);ties=[i for i,s in enumerate(scores) if s==best]
                    node=node['children'][int(rng.choice(ties))];path.append(node)
                    stats['max_depth']=max(stats['max_depth'],depth+1)
                    engine.accept(node['plan'])
                    if node.get('stop'):break
                key=engine.objective.key(node['plan'])
                reward=(2 if not key[0] else 0)+(-key[1])/utility_bound
                for n in path:n['n']+=1;n['value']+=reward
                stats['simulations']+=1
    except DeadlineReached:exhausted=True
    return engine.finish('PUCT-ISL',stats,exhausted)


def first_two(instance,task,plan):
    occupied=instance.occupied(plan,task.sender,task.receiver);starts=set()
    for left,latest in opportunities(instance,task):
        for lower in (left,):
            start=lower
            for a,b in occupied:
                if b<=start:continue
                if a>=start+task.duration:break
                start=b
            if start<=latest:
                starts.add(start)
                later=start+1
                for a,b in occupied:
                    if b<=later:continue
                    if a>=later+task.duration:break
                    later=b
                if later<=latest:starts.add(later)
    return sorted(starts)[:2]


def run_alns(case,seed=11):
    from alns import ALNS
    from alns.select import SegmentedRouletteWheel
    engine=Engine(case);rng=np.random.Generator(np.random.PCG64(seed));stats=dict(iterations=0,iterations_completed=0,seed=seed,framework='alns7.0.0',reaction=.8,package_decay=.2,operators=[])
    exhausted=False;frozen_ids={p.task_id for p in case.frozen}
    center,_,_=center_and_region(case,engine.instance,0)
    positions={p.task_id:i for i,p in enumerate(case.reference)}

    @dataclass
    class State:
        plan:tuple
        def objective(self):
            key=engine.objective.key(self.plan);n=len(engine.instance.tasks)+1
            # Exact integer packing preserves the full lexicographic order.
            value=int(key[0])*(sum(t.utility for t in engine.instance.tasks)+1)+key[1]
            value=value*n+key[2];value=value*n+key[3]
            return value*(engine.instance.horizon*n+1)+key[4]

    def destroy(kind):
        def operator(state,rng):
            engine.guard();items=[p for p in state.plan if p.task_id not in frozen_ids]
            count=min(10,max(1,ceil(.1*len(items))),len(items))
            if kind==0:
                order=list(rng.permutation(len(items)));chosen=[items[i] for i in order[:count]]
            elif kind==1:
                chosen=sorted(items,key=lambda p:(Fraction(engine.instance.task_map[p.task_id].utility,engine.instance.task_map[p.task_id].duration),p.task_id))[:count]
            else:chosen=sorted(items,key=lambda p:(abs(positions.get(p.task_id,center)-center),p.task_id))[:count]
            ids={p.task_id for p in chosen}
            stats['operators'].append(dict(destroy=kind,removed=sorted(ids)))
            return State(tuple(p for p in state.plan if p.task_id not in ids))
        return operator

    def repair(kind):
        def operator(state,rng):
            stats['operators'][-1]['repair']=kind
            plan=state.plan
            while True:
                engine.guard();pool=candidate_tasks(engine,plan);options=[]
                for t in pool:
                    engine.guard();item=earliest(engine.instance,t,plan,engine.guard)
                    if item is None:continue
                    candidate=ordered(plan+(item,))
                    if engine.cost(candidate)>engine.B:continue
                    urgent=not(case.event.urgent and t.id==case.event.urgent.id)
                    if kind==0:key=(urgent,t.density_key)
                    elif kind==1:key=(urgent,2*t.duration,item.start-t.release,t.density_key)
                    else:
                        two=first_two(engine.instance,t,plan)
                        regret=two[1]-two[0] if len(two)>1 else engine.instance.horizon
                        key=(urgent,-regret,t.density_key)
                    options.append((key,item))
                    if kind==0:break
                if not options:break
                item=min(options,key=lambda v:v[0])[1];plan=ordered(plan+(item,))
            assert validate(engine.instance,plan,frozen=case.frozen,cancelled=case.event.cancelled).feasible
            return State(plan)
        return operator

    def accept(rng,best,current,candidate):
        accepted=engine.accept(candidate.plan) if candidate.objective()<current.objective() else False
        stats['iterations_completed']+=1
        return accepted

    def stop(rng,best,current):
        if stats['iterations']>=200:return True
        engine.guard();stats['iterations']+=1;return False

    try:
        if engine.verified and not engine.conflict and case.event.applicable:
            alg=ALNS(rng)
            for i in range(3):alg.add_destroy_operator(destroy(i),name=('random','low_density','near_event')[i])
            for i in range(3):alg.add_repair_operator(repair(i),name=('density','least_increment','regret2')[i])
            selector=SegmentedRouletteWheel([5,2,0,0],decay=.2,seg_length=20,num_destroy=3,num_repair=3)
            alg.iterate(State(engine.plan),selector,accept,stop)
            stats['destroy_weights']=selector.destroy_weights.tolist();stats['repair_weights']=selector.repair_weights.tolist()
    except DeadlineReached:exhausted=True
    return engine.finish('ALNS-ISL',stats,exhausted)
