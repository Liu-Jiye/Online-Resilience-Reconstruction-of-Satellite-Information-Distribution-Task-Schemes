"""Small D1 cases using unchanged P1 distributions; all failures are explicit."""
from dataclasses import asdict
import numpy as np
from .models import Case, Instance, case_to_dict, frozen_count
from .calendar import build_calendar
from .p1_generation import component_seeds, synthetic_contacts, generate_tasks
from .reference import create_reference
from .events import generate_event


def generate_base(ci, candidates, satellites, attempt, config):
    seed = config['instance_seed_start']+ci*config['instance_seed_stride']+attempt
    iid = f'P2-n{candidates}-s{satellites}-attempt-{attempt:03d}'
    seeds = component_seeds(seed)
    sats = tuple(f's{k:02d}' for k in range(satellites))
    rng = np.random.Generator(np.random.PCG64(seeds['contacts']))
    contacts, physical = synthetic_contacts(sats,rng)
    calendar, loads = build_calendar(sats,5400,seeds['calendar'],probability=.5,slot_s=60)
    common = {'instance_id':iid,'seed':seed,'combination_index':ci,'candidates':candidates,
              'satellites':satellites,'attempt':attempt,'component_seeds':seeds}
    try:
        tasks, task_meta = generate_tasks(sats,contacts,np.random.Generator(np.random.PCG64(seeds['tasks'])),count=candidates)
    except ValueError as error:
        return {**common,'status':'generation_failed','reason':str(error)}, None
    instance = Instance(iid,sats,tasks,contacts,calendar,5400)
    reference, reference_meta = create_reference(instance)
    if not reference:
        return {**common,'status':'generation_failed','reason':'empty_reference'}, None
    return {**common,'status':'valid','reference_count':len(reference)}, {
        'base':asdict(instance),'reference':[asdict(p) for p in reference],
        'metadata':{**common,'background_actual_load_by_terminal':loads,'task_sampling':task_meta,
                    'physical_contacts':physical,'reference_metadata':reference_meta}}


def select_events(valid_by_combination,config):
    rng = np.random.Generator(np.random.PCG64(config['event_selection_seed']))
    selected, kind_counts = [], {k:0 for k in config['event_kind_rotation']}
    for ci,valid in enumerate(valid_by_combination):
        indices = rng.permutation(len(valid)).tolist()[:config['event_counts_per_combination'][ci]]
        for index in indices:
            base = valid[index]
            ordinal = len(selected)
            kind = config['event_kind_rotation'][ordinal%3]
            ratio,q = config['event_scenarios_rotation'][kind_counts[kind]%4]
            kind_counts[kind] += 1
            selected.append({'event_ordinal':ordinal,'instance_id':base['instance_id'],
                             'combination_index':ci,'candidates':base['candidates'],'satellites':base['satellites'],
                             'instance_seed':base['seed'],'selection_index_in_valid_ids':index,
                             'kind':kind,'FR':ratio,'q':q,'event_seed':config['event_seed_start']+ordinal})
    return selected


def make_case(data,event_spec):
    from .models import case_from_dict
    skeleton = {k:data[k] for k in ('base','reference')}
    # Parse through the canonical P0 interchange rather than a new task parser.
    skeleton.update(event={'id':'placeholder','kind':'reward_update','seed':0,'intensity':0,
                           'cancelled':[],'rewards':[],'urgent':None,'applicable':True},frozen_count=0)
    parsed = case_from_dict(skeleton)
    spec = event_spec
    event = generate_event(parsed.base,parsed.reference,spec['kind'],spec['FR'],spec['q'],spec['event_seed'])
    return Case(parsed.base,parsed.reference,event,frozen_count(parsed.reference,spec['FR']))
