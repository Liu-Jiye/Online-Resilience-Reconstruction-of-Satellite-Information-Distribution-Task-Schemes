"""Once-only public snapshot acquisition; original bytes remain local."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def download_once(directory, name, url, *, expect_json=False):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    record_path = directory / (name + '.fetch.json')
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding='utf-8'))
        if record['status'] != 'downloaded':
            raise RuntimeError('Previous fetch failed; explicit new acquisition required: ' + name)
        payload = (directory / record['filename']).read_bytes()
        if hashlib.sha256(payload).hexdigest() != record['sha256']:
            raise ValueError('Snapshot hash mismatch')
        return record
    record = {'requested_url': url, 'requested_at_utc': datetime.now(timezone.utc).isoformat(),
              'request_count': 1, 'name': name}
    try:
        request = Request(url, headers={'User-Agent': 'ISL-Research-Pilot/0.1 (single snapshot acquisition)',
                                        'Accept': 'application/json' if expect_json else 'text/html'})
        with urlopen(request, timeout=60) as response:
            payload = response.read()
            record.update({'final_url': response.url, 'http_status': response.status,
                           'response_headers': dict(response.headers.items())})
        if expect_json:
            parsed = json.loads(payload)
            if not isinstance(parsed, list) or not parsed or not all(isinstance(r, dict) for r in parsed):
                raise ValueError('Expected nonempty GP object array')
            record['records'] = len(parsed)
            record['field_names'] = sorted({k for row in parsed for k in row})
        filename = name + ('.json' if expect_json else '.html')
        (directory / filename).write_bytes(payload)
        record.update({'status': 'downloaded', 'filename': filename, 'size_bytes': len(payload),
                       'sha256': hashlib.sha256(payload).hexdigest(),
                       'received_at_utc': datetime.now(timezone.utc).isoformat()})
    except (HTTPError, URLError, ValueError, TimeoutError) as error:
        record.update({'status': 'failed', 'error': str(error), 'http_status': getattr(error, 'code', None)})
        save_json(record_path, record)
        raise
    save_json(record_path, record)
    return record
