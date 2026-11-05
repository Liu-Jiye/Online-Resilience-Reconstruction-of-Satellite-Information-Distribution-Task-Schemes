"""Acquire each constellation once; re-execution uses only verified cache."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from isl.p1_sources import download_once, save_json


def main():
    target = ROOT / 'data/raw/p1_snapshot_20261105'
    sources = [
        ('starlink', 'https://celestrak.org/NORAD/elements/gp.php?GROUP=starlink&FORMAT=json', True),
        ('oneweb', 'https://celestrak.org/NORAD/elements/gp.php?GROUP=oneweb&FORMAT=json', True),
        ('gp_formats', 'https://celestrak.org/NORAD/documentation/gp-data-formats.php', False),
        ('celestrak_home', 'https://celestrak.org/', False),
        ('celestrak_faq', 'https://celestrak.org/FAQs.php', False),
        ('usage_policy', 'https://celestrak.org/usage-policy.php', False),
    ]
    # Independent HTTP reads, one request per URL, no retry or cache bypass.
    def fetch(source):
        name, url, is_json = source
        try:
            return download_once(target, name, url, expect_json=is_json)
        except Exception as error:
            return {'name': name, 'status': 'failed', 'error': str(error)}
    with ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(fetch, sources))
    save_json(ROOT / 'reports/p1/acquisition.json', {'sources': records,
        'raw_directory': target.relative_to(ROOT).as_posix(), 'raw_redistributed': False})
    for record in records:
        print(json.dumps({k: record[k] for k in ('name', 'status', 'records', 'sha256', 'error') if k in record}))
    if any(r['status'] != 'downloaded' for r in records[:2]):
        raise SystemExit('Required GP snapshot unavailable; stop rather than substitute data.')


if __name__ == '__main__':
    main()
