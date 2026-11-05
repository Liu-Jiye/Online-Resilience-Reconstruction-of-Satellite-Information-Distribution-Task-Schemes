"""Integer bitset cross-check; does not import pilot diagnostic/search code."""
from collections import defaultdict
from .models import Item,ordered


def interval_bits(a,b):
    a=max(0,a)
    return ((1<<(b-a))-1)<<a if b>a else 0


def starts_in_free(free,duration):
    result=free
    for shift in range(1,duration):result &= free>>shift
    return result


class BitAudit:
    def __init__(self,instance,reference):
        self.instance=instance;self.reference=reference;self.contacts=defaultdict(list);self.busy=defaultdict(int)
        self.all_slots=(1<<instance.horizon)-1
        for c in instance.contacts:self.contacts[(c.sender,c.receiver)].append(c)
        for b in instance.calendar:self.busy[b.resource] |= interval_bits(b.start,b.end)

    def physical(self,task):
        mask=0
        for c in self.contacts[(task.sender,task.receiver)]:
            mask |= interval_bits(max(task.release,c.start),min(task.deadline,c.end)-task.duration+1)
        return mask

    def calendar_starts(self,task):
        free=self.all_slots & ~(self.busy[task.sender]|self.busy[task.receiver])
        return self.physical(task)&starts_in_free(free,task.duration)

    def inspect(self,task,frozen_count=0):
        physical=self.physical(task);legal=self.calendar_starts(task)
        relevant=[p for p in self.reference if p.task_id!=task.id and {p.sender,p.receiver}&{task.sender,task.receiver}]
        frozen={p.task_id for p in self.reference[:frozen_count]}
        candidates=set()
        for end in [0]+[p.end for p in relevant]:
            shifted=legal>>end
            if shifted:candidates.add(end+(shifted & -shifted).bit_length()-1)
        best=None;editable=None;witness=None
        for start in sorted(candidates):
            ids=sorted(p.task_id for p in relevant if p.start<start+task.duration and start<p.end)
            if best is None or len(ids)<best:best=len(ids);witness={'start':start,'blocker_ids':ids}
            if not frozen.intersection(ids):editable=len(ids) if editable is None else min(editable,len(ids))
        category=('no_physical' if not physical else 'calendar_blocked' if not legal else 'direct' if best==0 else 'frozen_blocked' if editable is None else 'editable_blocked')
        return {'physical_feasible':bool(physical),'calendar_feasible':bool(legal),'fixed_reference_min_blockers':best,
                'editable_min_blockers':editable,'category':category,'witness':witness}

    def reference_plan(self):
        occupied=self.busy.copy();plan=[]
        for t in sorted(self.instance.tasks,key=lambda t:t.density_key):
            free=self.all_slots & ~(occupied[t.sender]|occupied[t.receiver]);starts=self.physical(t)&starts_in_free(free,t.duration)
            if starts:
                start=(starts & -starts).bit_length()-1;p=Item(t.id,t.sender,t.receiver,start,start+t.duration)
                plan.append(p);mask=interval_bits(p.start,p.end);occupied[p.sender]|=mask;occupied[p.receiver]|=mask
        return ordered(plan)
