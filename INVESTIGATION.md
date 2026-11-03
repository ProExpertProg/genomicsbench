# Where is LF slower than DC? (GenomicsBench, Chameleon node)

Data: the full-dataset sweep `~/logs/261103-genomicsbench` (`results.csv`: 8 benchmarks x {dc, lf} x workers {32, 64, 128} x
G {1,...,64}, 10 trials each, `GB_REPEAT` with one warm-up repetition), plus the experiments below. The node is 2x64-core EPYC
7763 (SMT off, boost off), runtimes are cheetah `dcfa06b` built as `lf` and `dc`. Plots: `scripts/plot-lfdc.py`.

## Short answer

LF is within ~1-2% of DC wherever the comparison is fair. The places where LF *looked* slower are explained by

1. **chunk granularity**: DC's leaves are smaller than G, LF's chunks are exactly G (most same-G slowdowns, up to +65%);
2. **automatic NUMA balancing** noise (bsw +10%, fmi +23%, pileup, parts of chain);
3. a small **steal-policy** effect on heavy-tailed loops (chain: 2-5% at equal chunk size).

There is no sign of per-iteration or scheduler overhead in LF: the total body work of a loop is identical under both runtimes
and the extra time is idle tail at the end of the loop.

## 1. Same-G slowdowns are mostly a granularity artifact

DC (`cilk_for_root`) halves the range until it is <= G, so its leaves have `n / 2^k` iterations, with k the smallest value that
makes this <= G: between G/2 and G, e.g. chain (n = 10001): G = 4/8/16/32/64 -> 2.4/4.9/9.8/19.5/39.1. LF takes chunks of exactly G
iterations (`count / G` chunks). So "LF at G" has up to 1.6x coarser chunks than "DC at G", which matters when the loop has few
iterations per worker (pileup: 645 iterations for 128 workers; G = 8 gives LF 81 chunks, DC 128 leaves of ~5) or heavy-tailed
iteration costs (chain).

Comparing LF at the *equal effective chunk size* (log-log interpolation of LF's curve at DC's leaf size), geometric mean over all
(workers, G) points of the sweep:

| bench | LF/DC at the same G | LF/DC at equal chunk size |
|---|---|---|
| phmm | 1.169 | 0.958 |
| pileup | 1.247 | 1.017 |
| chain | 1.077 | 1.043 |
| bsw | 1.038 | 1.015 |
| fmi | 1.043 | 1.030 (inflated by the NUMA events of section 3) |
| poa | 1.017 | 1.005 |
| dbg | 1.003 | 0.993 |

(`results/lfdc-equal-chunk.csv`.) The sweep convention "LF at G and G/2 against DC at G" brackets this, but DC's effective chunk is
n/2^k, i.e. anywhere between 0.5 G and G depending on n, so a bracket is not an equal-chunk comparison.

## 2. chain: idle tail, reproduced by a work-stealing model, partly granularity, partly steal policy

chain (10001 iterations, costs: mean 5 ms, max 235 ms, the top 10% of the iterations hold 39% of the work) at 64 workers.
Per-iteration traces (`GB_TRACE`, `scripts/analyze-trace.py`):

* total body work is the same in all configurations (50.7 core-s), ramp-up is ~0.2 ms, **all extra time is an idle tail**:
  utilisation 0.92 (G = 1) -> LF 0.78 / DC 0.90 (G = 8) -> LF 0.66-0.74 / DC 0.78 (G = 64).
* `scripts/sim-cilk-for.py` replays the measured per-iteration costs through an idealised work-stealing model (free steals):
  DC = recursive halving, owner runs the left child, thieves steal the oldest continuation; LF = owner takes chunks in ascending order,
  thief takes the upper half of the victim's remaining chunks (`runtime/loop-frames.c`). It reproduces the measurements without any
  overhead: LF/DC 1.05 / 1.06 / 1.13 at G = 4 / 8 / 64 (measured 1.00-1.11 / 1.04-1.12 / 1.12-1.19), spans within a few percent.
* Giving LF the exact chunk boundaries of DC's leaves cuts the model's gap to 1.02-1.04: granularity is most of it at large G, the
  rest is the steal policy (what a thief takes).
* What-if (model only): a thief that takes 2/3 or 4/5 of the victim's remaining chunks instead of half makes LF 3-7% *faster* than
  DC on this loop. See section 5 for the check on the real runtime.

## 3. The remaining anomalies are automatic NUMA balancing

`kernel.numa_balancing = 1` on the node. Slow repetitions were found to be caused by it:

* bsw 128 workers, per-iteration traces: slow repetitions (+10%) have *identical* scheduling (utilisation, ramp) but ~10% more body time,
  concentrated on ~1/3 of the workers (their iterations 1.2x-6x longer), in LF and DC alike (with tracing on).
* `/proc/vmstat` sampled during 21 repetitions: slow repetitions coincide with **~25,000 NUMA hint faults, ~26,000 PTE updates and ~7,200
  page migrations** per repetition, fast ones with ~900 hint faults and none of the others.
* A/B with `kernel.numa_balancing=0` (restored afterwards): slow repetitions 12% -> **0%**, trial-to-trial CV 3.3-4.3% -> **0.4-0.7%**,
  worst repetition 0.336 s -> 0.288 s, LF and DC medians identical (0.279 vs 0.280 s).
* Targeted rerun of the cases that looked slower, balancing off (`results/lfdc-numa-off.csv`, same binaries):

| case | LF/DC, balancing on | LF/DC, balancing off | CV on -> off |
|---|---|---|---|
| bsw, 128 workers, G = 8 | 1.10 | 1.009 | 0.051 -> 0.011 |
| bsw, 128 workers, G = 16 | 1.08 | 1.014 | |
| fmi, 128 workers, G = 2 | 1.23 | 1.025 | 0.025 -> 0.004 |
| fmi, 128 workers, G = 8 | 1.21 | 1.016 | |
| chain, 64 workers, G = 4 | 1.11 | 0.996 | 0.049 -> 0.052 |
| chain, 64 workers, G = 8 | 1.12 | 1.039 | |
| chain, 64 workers, G = 64 | 1.19 | 1.128 (granularity) | |
| pileup, 32 workers, G = 16 | 1.52 | 1.059 | 0.14 -> 0.17 |

* **fmi** is *faster* with balancing on (5.5 s vs a steady 6.7 s with it off): the kernel migrates the shared index and per-worker
  arrays closer to their users. In the sweep's two "LF is 23% slower" processes (G = 2 and G = 8) the migration simply happened late
  (6.8 s for 8 repetitions, then 5.4 s); the same configuration in three fresh processes did not reproduce it. Such level shifts hit
  6 of 136 LF processes and 1 of 136 DC processes in the sweep (pileup and fmi, the memory-heavy ones), too few to call it LF-specific.
* **pileup** frees and reallocates its ~51 GB of results every repetition and is multimodal repetition by repetition (3.2-3.6 s vs
  3.9-4.65 s, lag-1 autocorrelation of the mode -0.25, in both runtimes); with 645 iterations the outcome depends on which worker gets
  the heavy chunks and on page placement. LF's share of slow-mode repetitions was 65% vs 47% for DC at G = 2 (8 processes each).

## 4. Recommendations

* Decide on `kernel.numa_balancing` deliberately for these runs (record it in the log). It changes bsw/chain by ~1-10% noise and fmi
  by 20%. Setting it to 0 in `bench_prepare_amd.sh` makes timings reproducible; keep in mind that it is then the placement of the
  default first-touch allocation that is measured (fmi gets slower).
* Compare LF and DC at equal effective chunk size (LF at G' = DC's leaf size `n / 2^ceil(log2(n/G))`), or at least report both.
* For loops with few, heavy-tailed iterations (chain, pileup) prefer small G; the runtime default of 2048 serialises all of these loops.

## 5. Check of the steal-share what-if on the real runtime

Two private copies of the LF runtime (`~/gb/cl/cheetah-lf67`, `cheetah-lf80`; the installed builds are untouched) with one changed
line in `split_loop_frame` (`runtime/loop-frames.c:21`): `mid = start + (end - start) / 3` (the thief takes 2/3 of the victim's
remaining chunks, `lf67`) or `/ 5` (4/5, `lf80`) instead of `(start + end) / 2`. chain, 64 workers, NUMA balancing off, 10 trials
(`results/lfvar-chain.csv`), median kernel seconds and the model's prediction:

| G | dc | lf (stock) | lf67 | lf80 |
|---|---|---|---|---|
| 4 | 0.909 (model 0.897) | 0.931 (0.940) | 0.871 (0.894) | 0.852 (0.854) |
| 8 | 0.873 (0.891) | 0.949 (0.943) | 0.927 (0.924) | 0.895 (0.868) |
| 64 | 1.002 (0.991) | 1.126 (1.122) | 1.116 (1.042) | 1.024 (1.014) |

The model predicts the stock runtimes within ~1-2%, and lf80 within ~3% (LF/DC: 0.94 / 1.03 / 1.02 at G = 4 / 8 / 64, model 0.95 /
0.97 / 1.02). lf67 at G = 64 is the one clear miss (1.116 measured, 1.042 modelled; CV 0.07). So for this loop the whole stock-LF gap
to DC is a consequence of how many chunks a thief takes plus the coarser chunks, not of runtime overhead; a larger steal share
removes it. This is one heavy-tailed loop and a model without steal costs: a larger share leaves the victim less work and could cost
more steals on loops with uniform iterations, so this is a lead for the LF steal policy, not a recommendation.

## Files

* `scripts/sweep-lfdc.sh`, `scripts/plot-lfdc.py` (+ `pbbsbench_plots.py`), `scripts/analyze-trace.py`, `scripts/sim-cilk-for.py`.
* `benchmarks/cilk_util.h`: `GB_REPEAT`, `GB_TRACE`.
* Raw data: `.auxtmpdir/chameleon-cloud/logs/261103-genomicsbench*` (sweep logs, traces, NUMA probes).
