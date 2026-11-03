#!/usr/bin/env python3
"""Idealised work-stealing simulation of cilk_for chunking under the DC and LF runtimes of cheetah.

Input: the cost [s] of every loop iteration (e.g. measured with GB_TRACE). Steals are free and instantaneous, victims are
chosen uniformly among the workers that have something to steal, so any difference between the two policies comes from
the structure of the chunks and from which work a thief takes, not from overhead.

  dc  recursive halving (runtime/cilk_abi_cilk_for_dc.c): a task [lo,hi) with hi-lo > G spawns the left half, which the
      worker runs right away (work first), leaving the continuation (the right part) on its deque; leaves are runs of
      between G/2 and G iterations. The owner resumes its newest continuation (the smallest), a thief steals the oldest
      (the largest, the upper half of what is left).
  lf  a loop frame of count/G chunks (runtime/cilk_abi_cilk_for_lf.c, loop-frames.c): the owner takes the chunks in
      ascending order; a thief takes the upper half of the victim's remaining chunks ((start+end)/2 .. end).

    python3 sim-cilk-for.py costs.npy -P 64 -G 1,2,4,8,16,32,64 --trials 40
"""
import argparse
import heapq
import random

import numpy as np


def sim_dc(cost, P, G, rng):
    pre = np.concatenate([[0.0], np.cumsum(cost)])
    n = len(cost)
    dq = [[] for _ in range(P)]          # (lo, hi); index 0 = oldest
    ev = []                              # (time, worker): worker becomes free
    idle = set(range(P))
    span = 0.0

    def start_task(w, t, lo, hi):
        nonlocal span
        while hi - lo > G:               # cilk_for_root: cilk_spawn the left half (the worker runs it right away)
            mid = lo + (hi - lo) // 2    # and leave the continuation, the right part, on the deque
            dq[w].append((mid, hi))
            hi = mid
        f = t + pre[hi] - pre[lo]
        span = max(span, f)
        heapq.heappush(ev, (f, w))
        idle.discard(w)

    def feed(t):                         # idle workers try to steal until nothing is left to steal
        progress = True
        while progress and idle:
            progress = False
            for w in sorted(idle):
                if dq[w]:
                    lo, hi = dq[w].pop()
                    start_task(w, t, lo, hi)
                    progress = True
                    continue
                victims = [v for v in range(P) if dq[v]]
                if victims:
                    v = rng.choice(victims)
                    lo, hi = dq[v].pop(0)
                    start_task(w, t, lo, hi)
                    progress = True

    start_task(0, 0.0, 0, n)
    feed(0.0)
    while ev:
        t, w = heapq.heappop(ev)
        idle.add(w)
        feed(t)
    return span


def dc_leaves(n, G):
    """Boundaries of the leaves cilk_for_root produces for [0, n): runs of between G/2 and G iterations."""
    out, stack = [], [(0, n)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo > G:
            mid = lo + (hi - lo) // 2
            stack.append((mid, hi))
            stack.append((lo, mid))
        else:
            out.append((lo, hi))
    return out


def sim_lf(cost, P, G, rng, dc_chunks=False, steal_frac=0.5):
    n = len(cost)
    pre = np.concatenate([[0.0], np.cumsum(cost)])
    if dc_chunks:       # same chunks as DC's leaves instead of chunks of G iterations
        chunks = dc_leaves(n, G)
    else:
        chunks = [(k * G, min((k + 1) * G, n)) for k in range(-(-n // G))]
    nch = len(chunks)
    ccost = np.array([pre[hi] - pre[lo] for lo, hi in chunks])
    rng_s = [0] * P
    rng_e = [0] * P
    rng_e[0] = nch
    ev = []
    idle = set(range(P))
    span = 0.0

    def run_next(w, t):
        nonlocal span
        k = rng_s[w]
        rng_s[w] += 1
        f = t + ccost[k]
        span = max(span, f)
        heapq.heappush(ev, (f, w))
        idle.discard(w)

    def feed(t):
        progress = True
        while progress and idle:
            progress = False
            for w in sorted(idle):
                if rng_s[w] < rng_e[w]:
                    run_next(w, t)
                    progress = True
                    continue
                victims = [v for v in range(P) if rng_s[v] < rng_e[v]]
                if victims:
                    v = rng.choice(victims)
                    # the runtime takes the upper half; steal_frac != 0.5 is a what-if
                    mid = rng_s[v] + int(np.floor((rng_e[v] - rng_s[v]) * (1.0 - steal_frac)))
                    rng_s[w], rng_e[w] = mid, rng_e[v]
                    rng_e[v] = mid
                    run_next(w, t)
                    progress = True

    # worker 0 starts the loop frame: it executes the first chunk, the others steal from it
    run_next(0, 0.0)
    feed(0.0)
    while ev:
        t, w = heapq.heappop(ev)
        idle.add(w)
        feed(t)
    return span


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("costs", help=".npy file with the cost of every iteration [s]")
    ap.add_argument("-P", type=int, default=64)
    ap.add_argument("-G", default="1,2,4,8,16,32,64")
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--lf-steal-frac", type=float, default=0.5, help="what-if: fraction of the victim's remaining chunks an LF thief takes")
    ap.add_argument("--lf-dc-chunks", action="store_true", help="LF on exactly the chunks of DC's leaves")
    a = ap.parse_args()
    cost = np.load(a.costs)
    ideal = cost.sum() / a.P
    print(f"{len(cost)} iterations, total {cost.sum():.2f} s, P={a.P}: ideal span {ideal:.3f} s, longest iteration {cost.max():.3f} s")
    print(f"{'G':>4} {'dc span':>9} {'lf span':>9} {'lf/dc':>7}   (median of {a.trials} random steal orders; spans / ideal in brackets)")
    for G in [int(x) for x in a.G.split(",")]:
        rng = random.Random(a.seed)
        dc = np.median([sim_dc(cost, a.P, G, rng) for _ in range(a.trials)])
        lf = np.median([sim_lf(cost, a.P, G, rng, a.lf_dc_chunks, a.lf_steal_frac) for _ in range(a.trials)])
        print(f"{G:>4} {dc:9.3f} {lf:9.3f} {lf / dc:7.3f}   ({dc / ideal:.3f}, {lf / ideal:.3f})")


if __name__ == "__main__":
    main()
