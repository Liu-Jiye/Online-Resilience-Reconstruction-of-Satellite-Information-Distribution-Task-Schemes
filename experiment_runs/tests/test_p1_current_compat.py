from pathlib import Path
import sys
import tempfile
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from p1_current_compat import PROGRESS_PATHS,check_paths,digest


@pytest.fixture
def work_path():
    work=Path(__file__).resolve().parents[2].parent
    with tempfile.TemporaryDirectory(prefix='p1-compat-test-',dir=work) as temp:
        path=Path(temp).resolve()
        assert path.parent==work.resolve() and path.name.startswith('p1-compat-test-')
        yield path


def fixture_data(work_path):
    old={name:b'P1 historical '+name.encode() for name in PROGRESS_PATHS}
    current={name:b'P2 current '+name.encode() for name in PROGRESS_PATHS}
    old['experiment_runs/scientific.json']=b'unchanged scientific evidence'
    current['experiment_runs/scientific.json']=old['experiment_runs/scientific.json']
    for name,data in current.items():
        p=work_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
    return old,current,{k:digest(v) for k,v in old.items()},{k:digest(v) for k,v in current.items()}


def test_only_verified_P2_progress_transition_is_accepted(work_path):
    old,current,p1,p2=fixture_data(work_path)
    receipt=check_paths(work_path,p1,p2,lambda stage,name:(old if stage=='P1' else current)[name])
    assert receipt['immutable_P1_acceptance_files_verified']==1
    assert receipt['progress_files_verified']==3
    assert all(x['changed_since_P1'] for x in receipt['progress_transitions'])


@pytest.mark.parametrize('target',['experiment_runs/scientific.json','experiment_runs/README.md','experiment_runs/status.json','experiment_runs/STAGES.md'])
def test_unregistered_edits_never_pass(work_path,target):
    old,current,p1,p2=fixture_data(work_path)
    (work_path/target).write_bytes(b'changed after approved P2')
    with pytest.raises(AssertionError):check_paths(work_path,p1,p2,lambda stage,name:(old if stage=='P1' else current)[name])


@pytest.mark.parametrize('stage',['P1','P2'])
def test_wrong_historical_blob_is_rejected(work_path,stage):
    old,current,p1,p2=fixture_data(work_path)
    with pytest.raises(AssertionError,match='historical blob mismatch'):
        check_paths(work_path,p1,p2,lambda s,name:b'wrong Git blob' if s==stage else (old if s=='P1' else current)[name])


def test_missing_progress_file_in_acceptance_is_rejected(work_path):
    old,current,p1,p2=fixture_data(work_path);del p1['experiment_runs/status.json']
    with pytest.raises(AssertionError,match='Missing required progress'):
        check_paths(work_path,p1,p2,lambda stage,name:(old if stage=='P1' else current)[name])
