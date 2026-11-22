"""Paired timing experiment for early verified urgent insertion in the P5 PALR."""
import argparse
import collections
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import random
from statistics import mean
import subprocess
import sys
from time import perf_counter_ns
import zipfile

import numpy as np


BUDGETS = (5, 10, 20)


def load_cases(p5, data_directory, limit):
    subset = json.loads((p5 / "subsets.json").read_text(encoding="utf-8"))
    bases = tuple(subset["ablation_300"])
    assert len(set(bases)) == len(bases) == 300
    for base in bases[:limit]:
        archive = p5 / "ablations" / (base + ".json.gz")
        with gzip.open(archive, "rt", encoding="utf-8") as records:
            expected = {}
            for line in records:
                row = json.loads(line)
                expected[row["scenario"]] = row["input_sha256"]
        with zipfile.ZipFile(data_directory / (base + ".zip")) as data_file:
            data = json.loads(data_file.read("default.json"))
        scenarios = cases(data)
        assert len(expected) == len(scenarios) == 12
        for scenario, (_, case) in enumerate(scenarios):
            digest = hashlib.sha256(canonical_json(case_to_dict(case)).encode()).hexdigest()
            assert digest == expected[scenario], (base, scenario, digest, expected[scenario])
            yield base, subset["layers"][base], scenario, case


def timed(kernel, case, budget):
    start = perf_counter_ns()
    result = kernel(case, w=5, B=2, budget_ms=budget)
    return rescore(case, result, perf_counter_ns() - start, budget)


def audited_metrics(case, result):
    metrics = result["metrics"]
    if metrics["valid_output"]:
        assert result["validated"] and metrics["within_budget"]
        check = validate(
            case.effective_instance(), tuple(Item(**p) for p in result["plan"]),
            frozen=case.frozen, cancelled=case.event.cancelled,
            original_ids={p.task_id for p in case.reference}, budget=result["B"],
            admissions=result["admissions_cumulative"],
            initial=tuple(Item(**p) for p in result["initial_plan"]),
            trace=result["trace"],
            unchanged=tuple(Item(**p) for p in result["unchanged_outside_E"]),
        )
        assert check.feasible, check.errors
    else:
        assert not metrics["online_success"] and metrics["U_exec"] == 0
    selected = ("online_success", "valid_output", "within_budget", "U_exec",
                "N_drop", "N_add", "M_all", "L_total_ms")
    return {key: metrics[key] for key in selected}


def summarize(observations):
    summary = []
    for budget in BUDGETS:
        for kind in ("all", "urgent_insertion", "cancellation", "reward_update"):
            rows = [r for r in observations if r["budget_ms"] == budget and r["applicable"]
                    and (kind == "all" or r["kind"] == kind)]
            if not rows:
                continue
            clusters = collections.defaultdict(list)
            for row in rows:
                clusters[row["base"]].append(row)
            cluster_stats = np.asarray([
                (len(group),
                 sum(int(r["early"]["online_success"]) - int(r["fixed"]["online_success"]) for r in group),
                 sum(r["early"]["U_exec"] - r["fixed"]["U_exec"] for r in group))
                for group in clusters.values()
            ])
            rng = np.random.default_rng(9738)
            draws = rng.integers(0, len(clusters), size=(10000, len(clusters)))
            counts, successes, utility = cluster_stats[draws].sum(axis=1).T
            paired = [r for r in rows if r["fixed"]["valid_output"] and r["early"]["valid_output"]]
            entry = dict(budget_ms=budget, kind=kind, calls_per_arm=len(rows),
                         unique_events=len({(r["base"], r["scenario"]) for r in rows}),
                         success_delta_pp_ci=np.quantile(100 * successes / counts, [.025, .975]).tolist(),
                         utility_delta_ci=np.quantile(utility / counts, [.025, .975]).tolist(),
                         gains=sum(r["early"]["online_success"] and not r["fixed"]["online_success"] for r in rows),
                         losses=sum(r["fixed"]["online_success"] and not r["early"]["online_success"] for r in rows),
                         both_valid=len(paired))
            for arm in ("fixed", "early"):
                entry[arm] = dict(
                    success=sum(r[arm]["online_success"] for r in rows),
                    timeouts=sum(not r[arm]["within_budget"] for r in rows),
                    valid=sum(r[arm]["valid_output"] for r in rows),
                    U_exec=mean(r[arm]["U_exec"] for r in rows),
                    p95_ms=float(np.quantile([r[arm]["L_total_ms"] for r in rows], .95)),
                    paired_drops=mean(r[arm]["N_drop"] for r in paired) if paired else None,
                    paired_adds=mean(r[arm]["N_add"] for r in paired) if paired else None,
                    paired_movement=mean(r[arm]["M_all"] for r in paired) if paired else None,
                )
            summary.append(entry)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--replicates", type=int, default=2)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    if not 1 <= args.limit <= 300 or args.replicates < 1:
        parser.error("limit must be 1–300 and replicates must be positive")
    repo = args.repo.resolve()
    run_directory = repo / "experiment_runs"
    sys.path.insert(0, str(run_directory / "src"))
    global repair, rescore, validate, Item, cases, case_to_dict, canonical_json
    from isl.p5 import repair
    from isl.p5 import repair_short_budget
    from isl.p5.online import rescore
    from isl.validation import validate
    from isl.models import Item, case_to_dict, canonical_json
    from isl.p5.data import cases

    p5 = run_directory / "reports" / "p5" / "P5-20261118"
    p4_data = run_directory / "reports" / "p4" / "P4-20261117" / "data"
    inputs = list(load_cases(p5, p4_data, args.limit))
    assert len(inputs) == args.limit * 12
    kernels = {"fixed": repair.run_method, "early": repair_short_budget.run_method}
    for _, _, _, case in inputs[:24]:
        for kernel in kernels.values():
            timed(kernel, case, 10)
    rng = random.Random(73519)
    observations = []
    for replicate in range(args.replicates):
        order = list(range(len(inputs)))
        rng.shuffle(order)
        for number, index in enumerate(order, start=1):
            base, layer, scenario, case = inputs[index]
            for budget in rng.sample(BUDGETS, len(BUDGETS)):
                arms = rng.sample(tuple(kernels), len(kernels))
                raw = {arm: timed(kernels[arm], case, budget) for arm in arms}
                observations.append(dict(
                    base=base, layer=layer, scenario=scenario, kind=case.event.kind,
                    applicable=case.event.applicable, replicate=replicate,
                    budget_ms=budget, first=arms[0],
                    **{arm: audited_metrics(case, raw[arm]) for arm in arms},
                ))
            if number % 300 == 0:
                print(f"Repeat {replicate + 1}/{args.replicates}, {number}/{len(inputs)} events", flush=True)
    result = dict(repo_commit=subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        kernel_sha256=hashlib.sha256(Path(repair.__file__).read_bytes()).hexdigest(),
        early_kernel_sha256=hashlib.sha256(Path(repair_short_budget.__file__).read_bytes()).hexdigest(),
        timing="Full kernel call including final validation and result construction, with common outer scoring",
        python=sys.version, platform=platform.platform(), numpy=np.__version__,
        cpu_count=os.cpu_count(), events=len(inputs), repetitions=args.replicates,
        summary=summarize(observations),
        by_replicate=[summarize([r for r in observations if r["replicate"] == i])
                      for i in range(args.replicates)],
        rows=observations)
    with gzip.open(args.output, "wt", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, allow_nan=False)
    for entry in result["summary"]:
        print(json.dumps(entry), flush=True)


if __name__ == "__main__":
    main()
