"""Record the actual Linux execution boundary, before any P3 measurements."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[1]
out = root / 'reports/p3/P3-20261110'
out.mkdir(parents=True, exist_ok=True)
affinity = sorted(os.sched_getaffinity(0))
assert platform.system() == 'Linux' and sys.version_info[:2] == (3, 11)
assert affinity == [0], affinity
threads = {k: os.environ.get(k) for k in
           ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')}
assert set(threads.values()) == {'1'}
freeze = subprocess.check_output([sys.executable, '-m', 'pip', 'freeze'], text=True)
subprocess.run([sys.executable, '-m', 'pip', 'check'], check=True)
(root / 'environment/p3/requirements.lock.txt').write_text(freeze, encoding='utf-8')
record = dict(at_utc=datetime.now(timezone.utc).isoformat(), python=sys.version,
              platform=platform.platform(), affinity=affinity, thread_environment=threads,
              os_release=Path('/etc/os-release').read_text(),
              meminfo=Path('/proc/meminfo').read_text(),
              cpuinfo=Path('/proc/cpuinfo').read_text(),
              dpkg_packages=subprocess.check_output(['dpkg-query', '-W'], text=True).splitlines(),
              note='Debian Bookworm Linux container; actual VM memory recorded, not host RAM; no P3 results yet')
(out / 'environment.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: record[k] for k in ('python', 'platform', 'affinity', 'thread_environment')}))
