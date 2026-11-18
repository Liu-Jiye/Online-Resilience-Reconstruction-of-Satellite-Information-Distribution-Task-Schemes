"""Search-only diagnostic relaxations. Final checks use full original physics."""
from collections import defaultdict
from ..models import Contact
from ..p3r.indexed import IndexedInstance as FullIndex, Objective, earliest, opportunities

class IndexedInstance(FullIndex):
    def __init__(self,instance,ignore_window=False,ignore_receiver=False):
        super().__init__(instance)
        self.ignore_receiver=ignore_receiver
        if ignore_window:
            self.by_pair=defaultdict(list)
            for t in instance.tasks:
                if not self.by_pair[t.sender,t.receiver]:
                    self.by_pair[t.sender,t.receiver]=[Contact('diagnostic:'+t.sender+':'+t.receiver,t.sender,t.receiver,0,instance.horizon)]

    def occupied(self,plan,sender,receiver):
        if not self.ignore_receiver:return super().occupied(plan,sender,receiver)
        return sorted(set([(p.start,p.end) for p in plan if p.sender==sender]+self.by_resource[sender]))
