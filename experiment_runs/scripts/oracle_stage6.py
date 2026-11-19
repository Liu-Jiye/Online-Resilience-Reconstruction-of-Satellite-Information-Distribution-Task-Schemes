"""A9 descriptive offline per-base grid selection, separately from deployable methods."""
import numpy as np
import pandas as pd
from p6_common import *
from analyze_stage6 import bootstrap,infer_view

def main():
    o=pd.read_csv(P5/'tables/A9_per_base_oracle_events.csv.gz',keep_default_na=False)
    for field in ['N_sym','M_edit']:
        o['accepted_'+field]=o[field]*o.valid_output
    o['urgent']=o.kind.eq('urgent_insertion').astype(float)
    o['online_urgent']=o.online_success*o.urgent;o['applicable_urgent']=o.applicable*o.urgent
    original=pd.read_csv(OUT/'tables/ablations_events.csv.gz',keep_default_na=False)
    original=original[original.label.isin(['Rule-PALR','Grid-w5-B2','Grid-w5-B1'])]
    e=pd.concat([original,o],ignore_index=True)
    b=bootstrap(e.root_id.unique());s,d=infer_view(e,b,'A9_offline','all','overall','all')
    csv('A9_offline_statistics.csv',pd.DataFrame(s))
    csv('A9_offline_effects.csv',pd.DataFrame(d))
    save(OUT/'A9_offline_scope.json',dict(scope='Observed per-base choice among25 grid calls using all12 event outcomes, optimistic post-selection descriptive envelope; bootstrap freezes selected actions and does not correct selection optimism; not an online50ms policy or general optimum',
        base_clusters=e.root_id.nunique(),selection_source_sha256=sha(P5/'tables/A9_per_base_oracle_events.csv.gz')))

if __name__=='__main__':main()
