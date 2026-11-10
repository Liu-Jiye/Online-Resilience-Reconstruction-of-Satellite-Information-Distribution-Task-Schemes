"""Verify P3 frozen inputs without executing a repair method or reading test performance."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import zipfile
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from isl.models import case_from_dict, canonical_json, frozen_count
from isl.events import generate_event
from isl.validation import validate


def main():
    out=ROOT/'reports/p3/P3-20261110/data'
    manifest=json.loads((out/'manifest.json').read_text())
    assert manifest['complete'] and len(manifest['instances'])==5000
    assert manifest['test_scenes_generated']==0
    for name, expected in manifest['source_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected,name
    counts=Counter(); total_events=0
    for row in manifest['instances']:
        counts[(row['split'],row['layer'])]+=1
        assert row['split'] in ('train','validation')
        seed=row['seed']
        assert (190000<=seed<194000) if row['split']=='train' else (290000<=seed<291000)
        path=out/(row['id']+'.zip')
        assert hashlib.sha256(path.read_bytes()).hexdigest()==row['archive_sha256']
        with zipfile.ZipFile(path) as z:
            for name,expected in row['entries_sha256'].items():
                encoded=z.read(name)
                assert hashlib.sha256(encoded).hexdigest()==expected
                d=json.loads(encoded)
                assert len(d['events'])==12
                assert len(d['instance']['tasks'])==(100 if name=='default.json' else 500)
                geometry=row['geometry']
                assert len(d['instance']['satellites'])==32
                if geometry['type']!='synthetic':
                    groups=json.loads((ROOT/f"reports/p1/{geometry['type']}_groups.json").read_text())['groups']
                    group=next(g for g in groups if g['group_id']==geometry['group'])
                    assert group['split']==row['split']
                    assert set(d['instance']['satellites'])=={str(n) for n in group['norad_ids']}
                first=d['events'][0]
                original=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=first['event'],frozen_count=0))
                assert validate(original.base,original.reference).feasible
                for e in d['events']:
                    c=case_from_dict(dict(base=d['instance'],reference=d['reference'],event=e['event'],
                                         frozen_count=frozen_count(d['reference'],e['FR'])))
                    # Events do not alter contacts or calendar in this protocol.
                    event=generate_event(c.base,c.reference,c.event.kind,e['FR'],e['q'],c.event.seed)
                    from dataclasses import asdict
                    assert canonical_json(asdict(event))==canonical_json(e['event'])
                    total_events+=1
    assert dict(counts)=={('train','D1'):1600,('train','D2-S'):1200,('train','D2-O'):1200,
                         ('validation','D1'):400,('validation','D2-S'):300,('validation','D2-O'):300}
    print(json.dumps({'passed':True,'base_scenes':5000,'paired_variants':10000,'events_reproduced':total_events,
                      'test_scenes':0,'repair_calls':0}))


if __name__=='__main__':
    main()
