#!/usr/bin/env python3
"""Iteration cost of chain against the iteration index (G=1), with the cost of the schedulable units of one or two grainsizes:
LF chunks (exactly G iterations) and DC leaves (between G/2 and G iterations, see runtime/cilk_abi_cilk_for_dc.c).

  top     cost of every unit [ms] along the index: G=1 iterations (grey stems), LF chunks at --G and --G-small (two
          oranges, darker = larger G) and DC leaves at --G (blue), the ideal span with P workers, a threshold line
  strip   where the units exceed the threshold, one row per series, with "x of y units, z% of the work"
  bottom  left: zoom on the heaviest iteration and the unit of each series that contains it
          right: share of the total work held by units larger than x

    python3 plot-chain-cost.py chain-cost.npy --G 16 --G-small 8 -P 128 --out chain-cost-g16.pdf
"""
import argparse
import importlib.util
import os

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e2e1dd"
LF_BIG, LF_SMALL, DC_C = "#9a420a", "#f0913f", "#2a78d6"   # validated (validate_palette.py): two oranges in the L band + blue

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("costs", help=".npy with the cost [s] of every iteration (GB_TRACE of chain, DC G=1)")
ap.add_argument("--G", type=int, default=16, help="grainsize of the LF chunks and DC leaves")
ap.add_argument("--G-small", type=int, default=8, help="second, smaller LF grainsize (0: none)")
ap.add_argument("-P", type=int, default=128, help="workers for the ideal-span line")
ap.add_argument("--threshold", type=float, default=100.0, help="ms; units above it are marked")
ap.add_argument("--out", default="chain-cost.pdf")
a = ap.parse_args()

here = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("sim", os.path.join(here, "sim-cilk-for.py"))
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)

c = np.load(a.costs) * 1e3                      # ms
n = len(c)
pre = np.concatenate([[0.0], np.cumsum(c)])
cost = lambda units: np.array([pre[h] - pre[l] for l, h in units])
lf_units = lambda G: [(k * G, min((k + 1) * G, n)) for k in range(-(-n // G))]

# (label, units, costs, color), small -> large
series = []
if a.G_small:
    u = lf_units(a.G_small)
    series.append((f"LF G={a.G_small}", u, cost(u), LF_SMALL))
u = lf_units(a.G)
series.append((f"LF G={a.G}", u, cost(u), LF_BIG))
u = sorted(sim.dc_leaves(n, a.G))
series.append((f"DC G={a.G}", u, cost(u), DC_C))
ideal = c.sum() / a.P
T = a.threshold

plt.rcParams.update({"figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
                     "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.edgecolor": GRID, "font.size": 8})


def step(ax, units, vals, color, **kw):
    xs = np.array([[l, h] for l, h in units]).ravel()
    ax.plot(xs, np.repeat(vals, 2), color=color, lw=kw.pop("lw", 0.8), **kw)


def style(ax):
    ax.grid(color=GRID, lw=0.5)
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


fig = plt.figure(figsize=(12.5, 9.6))
gs = fig.add_gridspec(3, 2, height_ratios=[3.0, 1.0, 2.4], hspace=0.42, wspace=0.17, left=0.055, right=0.985,
                      top=0.855, bottom=0.065)
fig.suptitle("chain: cost of the schedulable units along the iteration index", x=0.012, y=0.985, ha="left", fontsize=12,
             fontweight="semibold")
d = series[-1]
fig.text(0.012, 0.953, (f"one iteration = one chain_dp call (GB_TRACE, DC G=1, 64 workers, mean of 10 reps; total {c.sum() / 1e3:.1f} core-s, "
                       f"mean {c.mean():.1f} ms, max {c.max():.0f} ms). The span of the loop is at least the cost of its largest unit.\n"
                       f"LF chunks have exactly G iterations (G={a.G}: {len(series[-2][1])} chunks"
                       + (f", G={a.G_small}: {len(series[0][1])} chunks" if a.G_small else "")
                       + f"); DC G={a.G}: {len(d[1])} leaves of {min(h - l for l, h in d[1])}-{max(h - l for l, h in d[1])} iterations."),
         ha="left", va="top", fontsize=7.5, color=INK2, linespacing=1.5)

handles = [Line2D([], [], color=INK2, lw=1.2, label="iteration (G=1)")]
for lab, units, vals, col in series:
    handles.append(Line2D([], [], color=col, lw=2.0, label=f"{lab}: {n / len(units):.1f} iterations per unit"))
fig.legend(handles=handles, loc="upper right", ncol=len(handles), frameon=False, fontsize=7.5, labelcolor=INK2,
           bbox_to_anchor=(0.985, 0.915))

# ---- top: cost along the index
ax = fig.add_subplot(gs[0, 0:2])
ax.vlines(np.arange(n), 0, c, color=INK2, lw=0.45, alpha=0.85, zorder=2)
for lab, units, vals, col in series[::-1]:          # largest G first, so the finer series stay visible on top
    step(ax, units, vals, col, alpha=0.72, zorder=3, lw=0.8)
ax.axhline(ideal, color=INK, lw=0.8, ls=(0, (5, 3)), zorder=4)
ax.axhline(T, color=INK2, lw=0.7, ls=(0, (1, 2)), zorder=4)
ax.text(n * 0.998, ideal + 5, f"ideal span with {a.P} workers: {ideal:.0f} ms", va="bottom", ha="right", fontsize=7, color=INK)
ax.text(n * 0.998, T + 5, f"{T:.0f} ms", va="bottom", ha="right", fontsize=7, color=INK2, zorder=5,
        bbox=dict(boxstyle="square,pad=0.15", fc=SURFACE, ec="none", alpha=0.85))
for i in np.argsort(c)[::-1][:5]:
    ax.annotate(f"#{i}: {c[i]:.0f} ms", (i, c[i]), xytext=(0, 4), textcoords="offset points", ha="center", fontsize=6.5, color=INK)
ax.set_xlim(0, n)
ax.set_ylim(0, max(max(v.max() for _, _, v, _ in series), c.max(), ideal) * 1.12)
ax.set_ylabel("cost of one unit [ms]")
ax.set_xticklabels([])
style(ax)

# ---- strip: where the units exceed the threshold
rg = fig.add_subplot(gs[1, 0:2], sharex=ax)
rows = series[::-1]                                  # top row: the largest units
for r, (lab, units, vals, col) in enumerate(rows):
    y = len(rows) - 1 - r
    big = [(l + h) / 2 for (l, h), v in zip(units, vals) if v > T]
    rg.vlines(big, y - 0.42, y + 0.08, color=col, lw=0.9)
    rg.add_patch(Rectangle((n * 0.002, y + 0.22), n * 0.006, 0.17, color=col, lw=0, clip_on=False))
    rg.text(n * 0.011, y + 0.30, f"{lab}: {len(big)} of {len(vals)} units, {vals[vals > T].sum() / c.sum() * 100:.0f}% of the work",
            ha="left", va="center", fontsize=7.5, color=INK)
rg.set_ylim(-0.55, len(rows) - 0.45)
rg.set_yticks([])
rg.set_xlabel("iteration index")
rg.set_title(f"units larger than {T:.0f} ms ({T / ideal * 100:.0f}% of the ideal span with {a.P} workers)", fontsize=8.5, loc="left", pad=5)
for sp in ("top", "right", "left"):
    rg.spines[sp].set_visible(False)
rg.grid(color=GRID, lw=0.5, axis="x")

# ---- bottom left: zoom on the heaviest iteration
zb = fig.add_subplot(gs[2, 0])
i0 = int(np.argmax(c))
lo, hi = max(i0 - 45, 0), min(i0 + 46, n)
zb.vlines(np.arange(lo, hi), 0, c[lo:hi], color=INK2, lw=1.4, alpha=0.9, zorder=2)
ymax = 0
leg = []
for lab, units, vals, col in series:
    m = [k for k, (l, h) in enumerate(units) if l <= i0 < h][0]
    l, h = units[m]
    zb.axvspan(l, h, color=col, alpha=0.10, lw=0)
    inside = [k for k, (x, y) in enumerate(units) if y > lo and x < hi]
    step(zb, [units[k] for k in inside], np.array([vals[k] for k in inside]), col, alpha=0.85, lw=1.2, zorder=3)
    ymax = max(ymax, vals[m])
    leg.append(Line2D([], [], color=col, lw=2.0, label=f"{lab} unit [{l},{h}): {vals[m]:.0f} ms ({vals[m] - c[i0]:.0f} ms besides #{i0})"))
zb.set_xlim(lo, hi)
zb.set_ylim(0, ymax * 1.62)
zb.legend(handles=leg, loc="upper left", frameon=False, fontsize=7, labelcolor=INK)
zb.set_title(f"the heaviest iteration (#{i0}: {c[i0]:.0f} ms) and the units that contain it", fontsize=8.5, loc="left", pad=4)
zb.set_xlabel("iteration index")
zb.set_ylabel("cost [ms]")
style(zb)

# ---- bottom right: share of the work held by units above a size
zc = fig.add_subplot(gs[2, 1])
xs = np.geomspace(1, 700, 240)
zc.plot(xs, [c[c > x].sum() / c.sum() * 100 for x in xs], color=INK2, lw=1.6, label="iterations (G=1)")
for lab, units, vals, col in series:
    zc.plot(xs, [vals[vals > x].sum() / c.sum() * 100 for x in xs], color=col, lw=1.6, label=lab)
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
    print(f"units > {thr:3d} ms: iterations {np.sum(c > thr):3d} | " + " | ".join(
        f"{lab} {np.sum(v > thr):3d} ({v[v > thr].sum() / c.sum() * 100:4.1f}% of work)" for lab, _, v, _ in series))
