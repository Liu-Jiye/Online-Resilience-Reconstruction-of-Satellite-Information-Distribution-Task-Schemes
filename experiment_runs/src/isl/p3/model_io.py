"""Load individually hashed ET heads once, outside response timing."""
import json
import joblib


def load_model(folder):
    meta=json.loads((folder/'index.json').read_text())
    return dict(actions=meta['actions'],classifier=joblib.load(folder/'classifier.joblib'),
                heads=[joblib.load(folder/(name+'.joblib')) for name in meta['heads']])
