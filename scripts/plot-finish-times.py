#!/usr/bin/env python3
"""Per-worker finish times of the chain loop: when does each worker run out of work? Workers are sorted by finish time
(rank on x); the loop ends when the last one finishes. The gap between a worker's finish time and the span is idle time.

  measured   GB_TRACE traces (traces/chain/chain-<cfg>-w<P>-g<G>-1/chain-rep<k>.csv): median over repetitions, band = min..max
  model      scripts/sim-cilk-for.py on the measured per-iteration costs: median over random steal orders, band = 10..90%

    python3 plot-finish-times.py traces/ --out finish-times.pdf
"""
import argparse
import glob
import importlib.util
import os
import random

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e2e1dd"
LF_C, DC_C = "#f0913f", "#2a78d6"      # validated pair (validate_palette.py); LF G=8 as in plot-chain-cost.py

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("traces", help="directory with chain-cost.npy and chain/ (GB_TRACE runs)")
ap.add_argument("--out", default="finish-times.pdf")
ap.add_argument("--trials", type=int, default=30, help="random steal orders per model curve")
a = ap.parse_args()

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sim", os.path.join(here, "sim-cilk-for.py"))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)

cost = np.load(os.path.join(a.traces, "chain-cost.npy"))
n = len(cost)
ideal = lambda P: cost.sum() / P


def measured(cfg, P, G):
    runs = []
    files = sorted(glob.glob(os.path.join(a.traces, "chain", f"chain-{cfg}-w{P}-g{G}-1", "chain-rep*.csv")),
                   key=lambda f: int(f.split("rep")[1][:-4]))[1:]          # drop the warm-up repetition
    for f in files:
        t = pd.read_csv(f)
        runs.append(np.sort(t.groupby("worker").t1.max().to_numpy()))
    return np.array(runs)


def modelled(cfg, P, G, trials):
    rng = random.Random(1)
    runs = []
    for _ in range(trials):
        if cfg == "dc":
            span, fin = sim.sim_dc(cost, P, G, rng, return_finish=True)
        else:
            span, fin = sim.sim_lf(cost, P, G, rng, return_finish=True)
        runs.append(np.sort(fin))
    return np.array(runs)


def stats(runs):
    span = runs[:, -1]
    idle = (span[:, None] - runs).sum(1)               # core-seconds between a worker's finish and the end
    return np.median(span), np.median(idle), np.median(runs, 0)


plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                     "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": GRID, "font.size": 8})

fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.9), gridspec_kw=dict(wspace=0.2, left=0.05, right=0.99, top=0.76, bottom=0.12))
fig.suptitle("chain: when does each worker finish? (workers sorted by finish time)", x=0.012, y=0.985, ha="left",
             fontsize=12, fontweight="semibold")
fig.text(0.012, 0.935, ("Median over repetitions (measured) or random steal orders (model); band = min..max resp. 10..90%. "
                       "Idle tail = sum over workers of (span - finish time), in core-seconds. Dotted: ideal finish time total work / P.\n"
                       "No DC G=16 trace was taken, and traces exist for 64 workers only: the pair LF G=8 / DC G=16 is shown in the model."),
         ha="left", va="top", fontsize=7.5, color=INK2, linespacing=1.5)

panels = [
    ("measured, 64 workers (GB_TRACE)", 64, [("lf", 8, "-", True), ("dc", 8, "-", True)], measured),
    ("model, 64 workers", 64, [("lf", 8, "-", False), ("dc", 8, "--", False), ("dc", 16, "-", False)], modelled),
    ("model, 128 workers", 128, [("lf", 8, "-", False), ("dc", 8, "--", False), ("dc", 16, "-", False)], modelled),
]
lims = []
for ax, (title, P, curves, fn) in zip(axes, panels):
    handles = []
    lo_all, hi_all = [], []
    for cfg, G, ls, _ in curves:
        runs = fn(cfg, P, G) if fn is measured else fn(cfg, P, G, a.trials)
        col = LF_C if cfg == "lf" else DC_C
        span, idle, med = stats(runs)
        x = np.arange(1, P + 1)
        if fn is measured:
            lo, hi = runs.min(0), runs.max(0)
        else:
            lo, hi = np.quantile(runs, 0.1, 0), np.quantile(runs, 0.9, 0)
        ax.fill_between(x, lo, hi, color=col, alpha=0.18, lw=0)
        ax.plot(x, med, color=col, lw=1.8, ls=ls)
        lo_all.append(lo.min())
        hi_all.append(hi.max())
        handles.append(Line2D([], [], color=col, lw=1.8, ls=ls,
                              label=f"{cfg.upper()} G={G}: span {span:.3f} s, idle tail {idle:.1f} core-s"))
    ax.axhline(ideal(P), color=INK, lw=0.8, ls=(0, (1, 2)))
    ax.text(P * 0.01, ideal(P), f"ideal {ideal(P):.3f} s", fontsize=7, color=INK, va="bottom")
    ax.set_xlim(1, P)
    ax.set_title(title, fontsize=8.5, loc="left", pad=4)
    ax.set_xlabel("worker rank (by finish time)")
    ax.legend(handles=handles, loc="lower right", frameon=False, fontsize=7, labelcolor=INK)
    ax.grid(color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    lims.append((min(lo_all) * 0.9, max(hi_all) * 1.03))
lo64, hi64 = min(lims[0][0], lims[1][0]), max(lims[0][1], lims[1][1])      # same scale for the two 64-worker panels
axes[0].set_ylim(lo64, hi64)
axes[1].set_ylim(lo64, hi64)
axes[2].set_ylim(*lims[2])
axes[0].set_ylabel("finish time [s]")

fig.savefig(a.out)
print("wrote", a.out)
