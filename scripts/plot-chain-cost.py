#!/usr/bin/env python3
"""Iteration cost of chain against the iteration index (G=1), with the cost of the schedulable units of one grainsize G:
LF chunks (exactly G iterations) and DC leaves (between G/2 and G iterations, see runtime/cilk_abi_cilk_for_dc.c).

  top     cost of every unit [ms] along the index: G=1 iterations (grey stems), LF chunks and DC leaves (faded steps),
          the ideal span with P workers, and a rug of the units above a threshold
  bottom  left: zoom on the heaviest iteration (the unit that contains it, and the work that shares the unit)
          right: share of the total work held by units larger than x

    python3 plot-chain-cost.py chain-cost.npy --G 16 -P 128 --out chain-cost-g16.pdf
"""
import argparse
import importlib.util
import os

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e2e1dd"
LF_C, DC_C = "#e0782a", "#2a78d6"          # as in pbbsbench_plots.py (validated pair)

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("costs", help=".npy with the cost [s] of every iteration (GB_TRACE of chain, DC G=1)")
ap.add_argument("--G", type=int, default=16)
ap.add_argument("-P", type=int, default=128, help="workers for the ideal-span line")
ap.add_argument("--threshold", type=float, default=100.0, help="ms; units above it are marked")
ap.add_argument("--out", default="chain-cost.pdf")
a = ap.parse_args()

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sim", os.path.join(here, "sim-cilk-for.py"))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)

c = np.load(a.costs) * 1e3                      # ms
n, G = len(c), a.G
pre = np.concatenate([[0.0], np.cumsum(c)])
lf = [(k * G, min((k + 1) * G, n)) for k in range(-(-n // G))]
dc = sorted(sim.dc_leaves(n, G))
cost = lambda units: np.array([pre[h] - pre[l] for l, h in units])
lc, dcc = cost(lf), cost(dc)
ideal = c.sum() / a.P
T = a.threshold

plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                     "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": GRID, "font.size": 8})


def step(ax, units, vals, color, **kw):
    xs = np.array([[l, h] for l, h in units]).ravel()
    ys = np.repeat(vals, 2)
    ax.plot(xs, ys, color=color, lw=kw.pop("lw", 0.8), **kw)


def style(ax):
    ax.grid(color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


fig = plt.figure(figsize=(12.5, 9.2))
gs = fig.add_gridspec(3, 2, height_ratios=[3.0, 0.55, 2.4], hspace=0.38, wspace=0.30, left=0.165, right=0.925,
                      top=0.855, bottom=0.07)
fig.suptitle(f"chain: cost of the schedulable units, iteration (G=1) vs chunk/leaf at G={G}", x=0.012, y=0.985,
             ha="left", fontsize=12, fontweight="semibold")
fig.text(0.012, 0.953, (f"one iteration = one chain_dp call (GB_TRACE, DC G=1, 64 workers, mean of 10 reps; total {c.sum() / 1e3:.1f} core-s, "
                       f"mean {c.mean():.1f} ms, max {c.max():.0f} ms). The span of the loop is at least the cost of its largest unit.\n"
                       f"LF G={G}: {len(lf)} chunks of {G} iterations. DC G={G}: {len(dc)} leaves of {min(h - l for l, h in dc)}-{max(h - l for l, h in dc)} "
                       f"iterations. Dashed line: ideal span with {a.P} workers ({ideal:.0f} ms); dotted: {T:.0f} ms."),
         ha="left", va="top", fontsize=7.5, color=INK2, linespacing=1.5)

# ---- top: cost along the index
ax = fig.add_subplot(gs[0, 0:2])
ax.vlines(np.arange(n), 0, c, color=INK2, lw=0.45, alpha=0.85, zorder=2)
step(ax, lf, lc, LF_C, alpha=0.55, zorder=3)
step(ax, dc, dcc, DC_C, alpha=0.55, zorder=3)
ax.axhline(ideal, color=INK, lw=0.8, ls=(0, (5, 3)), zorder=4)
ax.axhline(T, color=INK2, lw=0.7, ls=(0, (1, 2)), zorder=4)
ax.text(n * 1.003, ideal, f"ideal span\n{a.P} workers\n{ideal:.0f} ms", va="center", ha="left", fontsize=7, color=INK)
ax.text(n * 1.003, T, f"{T:.0f} ms", va="center", ha="left", fontsize=7, color=INK2)
top = np.argsort(c)[::-1][:5]
for i in top:
    ax.annotate(f"#{i}: {c[i]:.0f} ms", (i, c[i]), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=6.5,
                color=INK)
ax.set_xlim(0, n)
ax.set_ylim(0, max(lc.max(), c.max(), ideal) * 1.12)
ax.set_ylabel("cost of one unit [ms]")
ax.set_xticklabels([])
style(ax)
handles = [Line2D([], [], color=INK2, lw=1.2, label="iteration (G=1)"),
           Line2D([], [], color=LF_C, lw=1.6, alpha=0.7, label=f"LF chunk, G={G}: cost of {G} iterations"),
           Line2D([], [], color=DC_C, lw=1.6, alpha=0.7, label=f"DC leaf, G={G}: cost of ~{n / len(dc):.0f} iterations")]
fig.legend(handles=handles, loc="upper right", ncol=3, frameon=False, fontsize=7.5, labelcolor=INK2, bbox_to_anchor=(0.925, 0.905))

# ---- rug: where the units exceed the threshold
rg = fig.add_subplot(gs[1, 0:2], sharex=ax)
for y, units, vals, col, lab in ((1, lf, lc, LF_C, "LF"), (0, dc, dcc, DC_C, "DC")):
    big = [(l + h) / 2 for (l, h), v in zip(units, vals) if v > T]
    rg.vlines(big, y - 0.35, y + 0.35, color=col, lw=0.9)
    rg.text(-n * 0.012, y, f"{lab} units > {T:.0f} ms\n{len(big)} of {len(vals)}, {vals[vals > T].sum() / c.sum() * 100:.0f}% of the work",
            ha="right", va="center", fontsize=7, color=INK)
rg.set_ylim(-0.6, 1.6)
rg.set_yticks([])
rg.set_xlabel("iteration index")
for sp in ("top", "right", "left"):
    rg.spines[sp].set_visible(False)
rg.grid(color=GRID, lw=0.5, axis="x")

# ---- bottom left: zoom on the heaviest iteration
zb = fig.add_subplot(gs[2, 0])
i0 = int(np.argmax(c))
lo, hi = max(i0 - 60, 0), min(i0 + 61, n)
k = i0 // G
l, h = lf[k]
j = [m for m, (x, y) in enumerate(dc) if x <= i0 < y][0]
dl, dh = dc[j]
zb.axvspan(l, h, ymin=0, ymax=1, color=LF_C, alpha=0.10, lw=0)
zb.axvspan(dl, dh, ymin=0, ymax=1, color=DC_C, alpha=0.10, lw=0)
zb.vlines(np.arange(lo, hi), 0, c[lo:hi], color=INK2, lw=1.4, alpha=0.9)
step(zb, [u for u in lf if u[1] > lo and u[0] < hi], np.array([lc[m] for m, u in enumerate(lf) if u[1] > lo and u[0] < hi]), LF_C, alpha=0.75, lw=1.1)
step(zb, [u for u in dc if u[1] > lo and u[0] < hi], np.array([dcc[m] for m, u in enumerate(dc) if u[1] > lo and u[0] < hi]), DC_C, alpha=0.75, lw=1.1)
zb.set_xlim(lo, hi)
zb.set_ylim(0, max(lc[k], dcc[j]) * 1.35)
zb.annotate(f"LF chunk [{l},{h}): {lc[k]:.0f} ms\n({c[i0]:.0f} ms iteration + {lc[k] - c[i0]:.0f} ms others)", (h, lc[k]),
            xytext=(6, 2), textcoords="offset points", fontsize=7, color=INK, ha="left", va="bottom")
zb.annotate(f"DC leaf [{dl},{dh}): {dcc[j]:.0f} ms\n({c[i0]:.0f} ms iteration + {dcc[j] - c[i0]:.0f} ms others)", (dl, dcc[j]), xytext=(-6, 2),
            textcoords="offset points", fontsize=7, color=INK, ha="right", va="bottom")
zb.set_title(f"the heaviest iteration (#{i0}) and the units that contain it", fontsize=8.5, loc="left", pad=4)
zb.set_xlabel("iteration index")
zb.set_ylabel("cost [ms]")
style(zb)

# ---- bottom right: share of the work held by units above a size
zc = fig.add_subplot(gs[2, 1])
xs = np.geomspace(1, 700, 240)
for vals, col, lab, ls in ((c, INK2, "iterations (G=1)", "-"), (lc, LF_C, f"LF chunks, G={G}", "-"), (dcc, DC_C, f"DC leaves, G={G}", "-")):
    zc.plot(xs, [vals[vals > x].sum() / c.sum() * 100 for x in xs], color=col, lw=1.6, ls=ls, label=lab)
zc.axvline(ideal, color=INK, lw=0.8, ls=(0, (5, 3)))
zc.text(ideal * 0.93, 96, f"ideal span,\n{a.P} workers", fontsize=7, color=INK, va="top", ha="right")
zc.set_xscale("log")
zc.set_xlim(1, 700)
zc.set_ylim(0, 100)
zc.set_xlabel("unit cost x [ms]")
zc.set_ylabel("% of the total work in units larger than x")
zc.set_title("how much work sits in big, unsplittable units", fontsize=8.5, loc="left", pad=4)
zc.legend(frameon=False, fontsize=7.5, labelcolor=INK2, loc="lower left")
style(zc)

fig.savefig(a.out)
print("wrote", a.out)
for thr in (50, 100, 150, 200):
    print(f"units > {thr:3d} ms: iterations {np.sum(c > thr):3d} | LF {np.sum(lc > thr):3d} ({lc[lc > thr].sum() / c.sum() * 100:4.1f}% of work) | DC {np.sum(dcc > thr):3d} ({dcc[dcc > thr].sum() / c.sum() * 100:4.1f}%)")
