import csv
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]


def main():
    errors = []
    with (ROOT / 'archive/manifest.csv').open(encoding='utf-8-sig', newline='') as stream:
        records = list(csv.DictReader(stream))
    if len(records) != 7 or len({record['source_id'] for record in records}) != 7:
        errors.append('Expected seven uniquely identified original files')
    for record in records:
        source = ROOT / record['repository_path']
        if not source.is_file():
            errors.append(f'Missing source: {source}')
            continue
        payload = source.read_bytes()
        if len(payload) != int(record['size_bytes']):
            errors.append(f'Size mismatch: {source}')
        if hashlib.sha256(payload).hexdigest() != record['sha256']:
            errors.append(f'Hash mismatch: {source}')
        index = ROOT / record['text_index']
        if not index.is_file() or not index.stat().st_size:
            errors.append(f'Missing or empty index: {index}')
    for path in ROOT.rglob('*.json'):
        if '.git' not in path.parts:
            try:
                json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, UnicodeError) as exception:
                errors.append(f'Invalid JSON {path}: {exception}')
    for path in ROOT.rglob('*.md'):
        if '.git' in path.parts:
            continue
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if target.startswith(('https://', 'http://', '#', 'mailto:')):
                continue
            destination = (path.parent / unquote(target.split('#')[0])).resolve()
            if not destination.exists():
                errors.append(f'Broken local link in {path.relative_to(ROOT)}: {target}')
    if errors:
        raise SystemExit('\n'.join(errors))
    print(f'PASS: {len(records)} source hashes, indexes, JSON syntax and local Markdown links')
    print('This validates repository integrity only; no algorithm experiments were run.')


if __name__ == '__main__':
    main()
