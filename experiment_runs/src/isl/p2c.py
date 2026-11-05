"""Controlled mechanism fixtures, explicitly distinct from natural samples."""
import numpy as np
from .models import Task, Contact, Busy, Instance, Event, Case
from .reference import create_reference

GROUPS = [('direct',25),('single',50),('double',25),('triple',25),('outside',50),('hard',25)]


def construct(index, group, ordinal):
    rng=np.random.Generator(np.random.PCG64(210000+index))
    s=[f'S{x}' for x in rng.permutation(8)]
    a=int(rng.integers(40,201));d=int(rng.integers(96,121));rate=int(rng.choice([1000,2000]))
    tasks=[];contacts=[]
    def task(tid,pair,start,duration):
        t=Task(tid,*pair,start,start+duration,(duration-1)*rate,rate,int(rng.integers(10,51)))
        tasks.append(t);contacts.append(Contact('C-'+tid,*pair,start,start+duration))
    hard_type=('physical','calendar','frozen')[ordinal%3] if group=='hard' else None
    k={'direct':0,'single':1,'double':2,'triple':3,'outside':1,'hard':1 if hard_type=='frozen' else 0}[group]
    for j in range(k):
        left=a+(d*j)//k;right=a+(d*(j+1))//k
        if group=='outside':left=a-40
        task(f'block-{j}',(s[0],s[2]) if j%2==0 else (s[2],s[1]),left,right-left)
    if group=='outside':
        for j in range(14):task(f'fill-{j}',(s[3],s[4]),a-35+2*j,2)
    step=int(rng.integers(5,10))
    while len(tasks)<20:
        j=len(tasks);task(f'tail-{j}',(s[5],s[6]),a+d+10+step*j,3)
    if hard_type!='physical':contacts.append(Contact('C-urgent',s[0],s[1],a,a+d))
    calendar=[Busy(s[7],500,520)]
    if hard_type=='calendar':calendar.append(Busy(s[1],a,a+d))
    base=Instance(f'P2C-{index:03d}',tuple(s),tuple(tasks),tuple(contacts),tuple(calendar),5400)
    reference,_=create_reference(base)
    assert len(reference)==20
    urgent=Task('urgent',s[0],s[1],0,a+d,(d-1)*rate,rate,1000)
    event=Event(f'P2C-event-{index:03d}','urgent_insertion',210000+index,.8,urgent=urgent)
    case=Case(base,reference,event,1 if hard_type=='frozen' else 0)
    return case,{'index':index,'group':group,'ordinal':ordinal,'seed':210000+index,'hard_type':hard_type,
                 'urgent_start':a,'urgent_duration':d,'expected_min_drops':k if group!='hard' else None}
