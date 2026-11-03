#!/usr/bin/env python3
"""Summarise GB_TRACE iteration traces (benchmarks/cilk_util.h): one line per trace file.

For every <name>-rep<k>.csv (idx,worker,t0,t1; seconds since the start of the kernel):
  span      makespan = last iteration end
  work      sum of iteration durations (CPU time spent in the loop body)
  util      work / (workers * span): 1 = no idle time
  ramp      time at which 95% of the workers have started their first iteration
  tail      span - the time at which 90% of the workers have finished their last iteration (idle tail)
  idle%     share of the idle worker time (workers * span - work) that falls into the ramp and the tail
  mean/p99  mean and 99th percentile iteration duration [ms]

    python3 analyze-trace.py dir/chain-rep*.csv
"""
import sys

import numpy as np
import pandas as pd


def summarize(path, nworkers=None):
    t = pd.read_csv(path)
    dur = t["t1"] - t["t0"]
    p = nworkers or t["worker"].nunique()
    span = t["t1"].max()
    work = dur.sum()
    first = t.groupby("worker")["t0"].min().sort_values().to_numpy()
    last = t.groupby("worker")["t1"].max().sort_values().to_numpy()
    k = max(int(np.ceil(0.95 * len(first))) - 1, 0)
    ramp = first[k]
    tail = span - last[int(0.10 * len(last))] if len(last) > 1 else 0.0
    idle = p * span - work
    # idle time before a worker's first iteration or after its last one
    edge = first.sum() + (span - last).sum()
    return dict(file=path.split("/")[-1], workers=len(first), span=span, work=work, util=work / (p * span),
                ramp=ramp, tail=tail, edge_idle=edge / idle if idle > 0 else 0.0,
                mean_ms=dur.mean() * 1e3, p99_ms=dur.quantile(0.99) * 1e3, n=len(t))


def main(paths):
    rows = [summarize(p) for p in paths]
    df = pd.DataFrame(rows)
    pd.set_option("display.width", 200)
    print(df.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


if __name__ == "__main__":
    main(sys.argv[1:])
