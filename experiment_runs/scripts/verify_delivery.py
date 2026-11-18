"""Verify historical deliverables; optionally restore the byte-identical ZIPs.

Standard library only. This never reruns an experiment or changes frozen files.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def checked_path(relative):
    path = (ROOT / relative).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f'Path outside experiment_runs: {relative}')
    return path


def verify(restore_dir=None):
    catalog = json.loads((ROOT / 'deliveries/catalog.json').read_text(encoding='utf8'))
    count = split_count = 0
    for entry in catalog['files']:
        if entry['storage'] == 'file':
            path = checked_path(entry['path'])
            if path.stat().st_size != entry['bytes'] or digest(path) != entry['sha256']:
                raise ValueError(f"Deliverable mismatch: {entry['path']}")
        else:
            combined = hashlib.sha256()
            size = 0
            for part in entry['parts']:
                path = checked_path(part['path'])
                if path.stat().st_size != part['bytes'] or digest(path) != part['sha256']:
                    raise ValueError(f"Part mismatch: {part['path']}")
                with path.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        size += len(block)
                        combined.update(block)
            if size != entry['bytes'] or combined.hexdigest() != entry['sha256']:
                raise ValueError(f"Combined ZIP mismatch: {entry['original_name']}")
            if restore_dir is not None:
                dest = restore_dir / entry['source_date'] / entry['original_name']
                if dest.exists():
                    if dest.stat().st_size != size or digest(dest) != entry['sha256']:
                        raise FileExistsError(f'Refusing to replace a different file: {dest}')
                else:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with dest.open('xb') as stream:
                        for part in entry['parts']:
                            with checked_path(part['path']).open('rb') as source:
                                for block in iter(lambda: source.read(1024 * 1024), b''):
                                    stream.write(block)
                    if digest(dest) != entry['sha256']:
                        raise ValueError(f'Restored ZIP mismatch: {dest}')
            split_count += 1
        count += 1
    return dict(passed=True, deliverables=count, split_archives=split_count,
                original_bytes=sum(e['bytes'] for e in catalog['files']),
                restore_dir=str(restore_dir) if restore_dir else None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore-dir', type=Path, help='Restore the two split ZIPs here; existing different files are never overwritten.')
    args = parser.parse_args()
    print(json.dumps(verify(args.restore_dir), ensure_ascii=False, indent=2))
