FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39
ENV OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONHASHSEED=20261020 PYTHONUNBUFFERED=1 MPLBACKEND=Agg
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY requirements.lock.txt /tmp/requirements.lock.txt
RUN python -m pip install --no-cache-dir -r /tmp/requirements.lock.txt && python -m pip check
WORKDIR /workspace
ENV PYTHONPATH=/workspace/experiment_runs/src
