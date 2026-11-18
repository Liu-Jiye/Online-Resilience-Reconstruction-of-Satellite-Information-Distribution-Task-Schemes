"""Run any P5 step in a new output directory without touching frozen delivery."""
import argparse,importlib
from pathlib import Path
import p5_common

ACTIONS={'prepare':'prepare_p5','inputs':'prepare_p5_special','ablations':'run_p5_ablations',
    'searches':'run_p5_searches','special':'run_p5_special','references':'run_p5_references',
    'transfer':'run_p5_transfer','continuous':'run_p5_continuous_v2',
    'audit':'verify_stage5_evidence','summarize':'summarize_stage5','plot':'plot_stage5'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=ACTIONS);parser.add_argument('--out',required=True)
    args=parser.parse_args();output=(p5_common.ROOT/args.out).resolve();parent=(p5_common.ROOT/'reports/p5').resolve()
    assert output.is_relative_to(parent) and output!=p5_common.OUT.resolve(),'Use a new reports/p5/<run-id> directory; frozen delivery is protected'
    p5_common.OUT=output
    importlib.import_module(ACTIONS[args.action]).main()

if __name__=='__main__':main()
