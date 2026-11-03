#!/usr/bin/env python3
"""Sweep plots for PBBS v2 logs (see pbbsbench_parse.py for the log format).

One row per benchmark, one column per worker count. x = runtime grainsize G (log2 axis), y = the
benchmark's value (geomean over its input cases) of the time [s], or of the speedup over a serial
baseline when ``--baseline`` logs are given. One series per coarsening factor.

  exact configs (LF)   markers + line at the exact G.
  smudged configs (DC) the effective grainsize of DC is somewhere between G/2 and G, so each value
                       is smeared horizontally over [G/2, G] (soft ends, thin dotted line through
                       the centres), instead of claiming a precise G.

The first row (first page) is ``ALL``: per benchmark each cell divided by that benchmark's best
cell of the column (>= 1 = slower than the best, same for time and speedup), then the geomean
over the benchmarks that have every cell.

    python3 pbbsbench_plots.py 261031 [261102-sort ...] -w 32,64,128 --out plots/
    python3 pbbsbench_plots.py 261031 --baseline 261102-serial --out plots/
"""
import argparse
import os

import matplotlib
import numpy as np
import pandas as pd

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e2e1dd"
# Coarsening shades, light -> dark = small -> large, one hue per runtime config.
HUES = {"dc": ["#86b6ef", "#2a78d6", "#0d366b"],      # blue
        "lf": ["#f2b27a", "#e0782a", "#8f3f0a"]}      # orange
FALLBACK = ["#8d8c87", "#52514e", "#0b0b0b"]
MARKERS = ["o", "s", "^", "D", "v", "P"]


def _shades(config, n):
    from matplotlib.colors import LinearSegmentedColormap
    cm = LinearSegmentedColormap.from_list(config, HUES.get(config, FALLBACK))
    return [cm(x) for x in ([0.5] if n == 1 else np.linspace(0, 1, n))]


def _plt():
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "text.color": INK, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
        "axes.edgecolor": GRID, "font.size": 7})
    return plt


def _short(bench):
    return "/\n".join(bench.split("/")[-2:])


def smudge(ax, x0, x1, y, color, half=0.03, alpha=0.8, n=48):
    """Horizontal smear of one value over [x0, x1] (log x, linear y): a Hann window of opacity along
    x, ``half`` = half height as a fraction of the panel's y range."""
    lo, hi = ax.get_ylim()
    h = half * (hi - lo)
    edges = np.geomspace(x0, x1, n + 1)
    win = np.sin(np.pi * (np.arange(n) + 0.5) / n) ** 2
    for k in range(n):
        ax.fill_between(edges[k:k + 2] * [1, 1.02], y - h, y + h, lw=0,
                        color=color, alpha=alpha * win[k], zorder=2)


def draw_panel(ax, sub, smudged, grains):
    """sub: summary rows of one benchmark and worker count (any configs)."""
    vals = sub["value"].to_numpy()
    hi = np.nanmax(vals)
    ax.set_xscale("log", base=2)
    ax.set_ylim(0, hi * 1.08)          # starts at 0; needed first: the smudge height is relative to it
    for config in sorted(sub["config"].unique(), key=lambda c: c in smudged):
        s = sub[sub["config"] == config]
        coarse = sorted(s["coarsen"].dropna().unique())
        for i, (c, col) in enumerate(zip(coarse, _shades(config, len(coarse)))):
            t = s[s["coarsen"] == c].sort_values("grainsize")
            g, v = t["grainsize"].to_numpy(), t["value"].to_numpy()
            if config in smudged:
                for gi, vi in zip(g, v):
                    if gi > 1:
                        smudge(ax, gi / 2, gi, vi, col)
                    else:   # G=1 is exact (the grainsize is guaranteed to be 1): a point, no smear
                        ax.plot([gi], [vi], color=col, marker="o", ms=3.6, mec=SURFACE, mew=0.6,
                                ls="none", zorder=3)
                ax.plot(np.where(g > 1, g / np.sqrt(2), g), v, color=col, lw=0.8, ls=(0, (1, 1.5)),
                        zorder=3)
            else:
                ax.plot(g, v, color=col, lw=1.4, marker=MARKERS[i % len(MARKERS)], ms=3.6,
                        mec=SURFACE, mew=0.6, zorder=3)
    ax.set_xticks(grains, [f"{int(g)}" for g in grains], fontsize=5.5)
    ax.minorticks_off()
    ax.set_xlim(min(grains) / 2 * 0.9, max(grains) * 1.15)
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(5, min_n_ticks=3))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.3g"))
    ax.tick_params(axis="y", labelsize=5.5, length=2)
    ax.tick_params(axis="x", length=2, pad=1)
    ax.grid(color=GRID, lw=0.5, which="major")
    ax.set_axisbelow(True)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)


def best_ratio(t, unit):
    """'best LF/best DC': performance of the best LF cell over that of the best DC cell, so > 1 =
    LF faster (speedup: max LF / max DC; time: min DC / min LF). None if either config is absent."""
    v = {c: t.loc[t["config"] == c, "value"].dropna() for c in ("lf", "dc")}
    if v["lf"].empty or v["dc"].empty:
        return None
    return v["lf"].max() / v["dc"].max() if unit == "speedup" else v["dc"].min() / v["lf"].min()


def _gmean(x):
    x = np.asarray(x, dtype=float)
    return float(np.exp(np.mean(np.log(x))))


def all_row(s, workers):
    """Rows for the ALL panel: every cell divided by the best (smallest) cell of its benchmark and worker
    count over all configs and grainsizes (>= 1: slower than the best), then the geomean over the benchmarks
    that have every cell -> (DataFrame like ``s`` for bench 'ALL' or None, #benchmarks included, #left out)."""
    parts, left = [], set()
    ncell = s.groupby(["bench", "workers"]).size().max()
    for (b, w), g in s.groupby(["bench", "workers"]):
        if w not in workers:
            continue
        if len(g) < ncell:
            left.add(b)
            continue
        parts.append(g.assign(value=g["value"] / g["value"].min()))
    if not parts:
        return None, 0, len(left)
    a = pd.concat(parts)
    key = ["config", "coarsen", "grainsize", "workers"]
    out = a.groupby(key, dropna=False)["value"].agg(_gmean).reset_index().assign(bench="ALL")
    return out, a["bench"].nunique(), len(left - set(a["bench"]))


def plot_sweep(s, workers=(32, 64, 128), smudged=("dc",), benches=None, per_page=5, title=None):
    """-> list of matplotlib Figures (pages). ``s`` is the output of ``pbbsbench_parse.summarize``."""
    plt = _plt()
    from matplotlib.lines import Line2D
    unit = s.attrs.get("unit", "time [s]")
    s = s[s["workers"].isin(workers)]
    if benches:
        s = s[s["bench"].isin(benches)]
    order = sorted(set(s["bench"]), key=lambda b: b.split("/")[-2:])
    grains = sorted(s["grainsize"].dropna().unique())
    rows = [(b, s[s["bench"] == b]) for b in order]
    ar = all_row(s, workers) if len(order) > 1 else (None,)
    notes = {}
    if ar[0] is not None:
        ar_df, n_in, n_left = ar
        rows.insert(0, ("ALL", ar_df))
        notes["ALL"] = f"{n_in} benchmarks" + (f"\n({n_left} without baseline/partial left out)" if n_left else "")
    for b, sub in rows:   # note partial benchmarks
        if b != "ALL" and sub.groupby("workers").size().min() < s.groupby(["bench", "workers"]).size().max():
            notes[b] = "partial"
    pages = [rows[i:i + per_page] for i in range(0, len(rows), per_page)] or [[]]
    left, cw, ch, head = 1.9, 2.6, 1.85, 1.6
    figs = []
    # legend entries: every (config, coarsening) pair, as drawn
    handles = []
    for config in sorted(s["config"].unique(), key=lambda c: c in smudged):
        coarse = sorted(s.loc[s["config"] == config, "coarsen"].dropna().unique())
        for i, (c, col) in enumerate(zip(coarse, _shades(config, len(coarse)))):
            lab = (f"{config.upper()}" if int(c) == 0 else f"{config.upper()} C={int(c)}") + (" (G/2…G)" if config in smudged else "")
            handles.append(Line2D([], [], color=col, lw=5 if config in smudged else 1.4,
                                  alpha=0.6 if config in smudged else 1, label=lab,
                                  marker=None if config in smudged else MARKERS[i % len(MARKERS)],
                                  ms=3.6, solid_capstyle="butt"))
    for pi, page in enumerate(pages):
        fig = plt.figure(figsize=(left + cw * len(workers) + 0.3, head + ch * len(page)))
        gs = fig.add_gridspec(len(page), len(workers), left=left / fig.get_figwidth(), right=0.995,
                              top=1 - (head - 0.1) / fig.get_figheight(), bottom=0.06, wspace=0.22,
                              hspace=0.5)
        fig.suptitle(f"{title or 'PBBS v2 sweep'}   (page {pi + 1}/{len(pages)})", x=0.012,
                     y=1 - 0.1 / fig.get_figheight(), ha="left", fontsize=11, fontweight="semibold")
        fig.text(0.012, 1 - 0.33 / fig.get_figheight(), (
            f"y: {unit}, median over trials · x: runtime grainsize G · series: runtime config\n"
            "panel titles: best LF/best DC = best LF cell over best DC cell, in performance (>1: LF faster)\n"
            "exact markers: G as set · smudge: value spread over G/2 → G, the effective grainsize "
            "is somewhere in between (dotted line through the centres); DC G=1 is exact (point)\n"
            + ("ALL row: each cell / its benchmark's best cell (>= 1: slower than the best), geomean over the benchmarks"
               if ar[0] is not None else "")), ha="left", va="top", fontsize=7, color=INK2,
            linespacing=1.5)
        fig.legend(handles=handles, ncol=len(handles), loc="upper left", frameon=False, fontsize=6.5,
                   bbox_to_anchor=(left / fig.get_figwidth(), 1 - 0.95 / fig.get_figheight()),
                   handlelength=2.2, columnspacing=1.2, labelcolor=INK2)
        for r, (b, sub) in enumerate(page):
            for k, w in enumerate(workers):
                ax = fig.add_subplot(gs[r, k])
                t = sub[sub["workers"] == w]
                if t.empty:
                    ax.axis("off")
                    continue
                draw_panel(ax, t, smudged, grains)
                ratio = best_ratio(t, unit)
                ttl = (f"{w} workers" if r == 0 else "") + ("" if ratio is None else
                       ("  ·  " if r == 0 else "") + f"best LF/best DC = {ratio:.2f}×")
                if ttl:
                    ax.set_title(ttl, fontsize=7.5 if r == 0 else 6.5, loc="left", pad=3,
                                 color=INK if r == 0 else INK2)
                if k == 0:
                    ax.annotate("all\nbenchmarks" if b == "ALL" else _short(b), xy=(0, 0.5),
                                xycoords="axes fraction", xytext=(-30, 0), ha="right", va="center",
                                textcoords="offset points", fontsize=8.5, fontweight="semibold",
                                linespacing=1.3)
                    if b in notes:
                        ax.annotate(notes[b], xy=(0, 0.5), xycoords="axes fraction",
                                    xytext=(-30, -24), textcoords="offset points", ha="right",
                                    va="top", fontsize=5.5, color=INK2, style="italic")
                    if b == "ALL":
                        ax.set_ylabel("time / best (geomean)", fontsize=6.5)
                    else:
                        ax.set_ylabel(unit, fontsize=6.5)
                if r == len(page) - 1:
                    ax.set_xlabel("runtime grainsize G", fontsize=6.5, labelpad=2)
        figs.append(fig)
    return figs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("logs", nargs="+", help="log files / directories; later ones win on overlap")
    ap.add_argument("--baseline", nargs="+", help="serial baseline logs (same format) -> plot speedups")
    ap.add_argument("-w", "--workers", default="32,64,128")
    ap.add_argument("--smudge", default="dc", help="comma separated configs drawn smudged G/2..G "
                    "(default dc; '' = none)")
    ap.add_argument("--missing-baseline", type=float, help="baseline time [s] to assume for input "
                    "cases without a baseline (default: drop them)")
    ap.add_argument("--stat", default="median", choices=["min", "median", "mean", "geomean"])
    ap.add_argument("--benches", help="comma separated subset, e.g. histogram/parallel")
    ap.add_argument("--per-page", type=int, default=5)
    ap.add_argument("--label", default="pbbsv2")
    ap.add_argument("--out", default=".")
    ap.add_argument("--fmt", default="pdf", choices=["pdf", "png", "svg"])
    ap.add_argument("--dpi", type=int, default=170)
    a = ap.parse_args(argv)
    matplotlib.use("Agg")
    cases = pp.parse_logs(a.logs)
    base = pp.parse_logs(a.baseline) if a.baseline else None
    s = pp.summarize(cases, a.stat, base, a.missing_baseline)
    if s.attrs["dropped"]:
        print("no baseline for:", ", ".join(s.attrs["dropped"]))
    if s.empty:
        raise SystemExit("nothing to plot (no logs, or no input case of the baseline matches)")
    workers = [int(x) for x in a.workers.split(",")]
    figs = plot_sweep(s, workers, tuple(x for x in a.smudge.split(",") if x),
                      a.benches.split(",") if a.benches else None, a.per_page,
                      f"{a.label}: {a.stat} {s.attrs['unit']}")
    os.makedirs(a.out, exist_ok=True)
    if a.fmt == "pdf":
        from matplotlib.backends.backend_pdf import PdfPages
        p = os.path.join(a.out, f"{a.label}-sweep.pdf")
        with PdfPages(p) as pdf:
            for f in figs:
                pdf.savefig(f)
        print(p)
    else:
        for i, f in enumerate(figs, 1):
            p = os.path.join(a.out, f"{a.label}-sweep-p{i}.{a.fmt}")
            f.savefig(p, dpi=a.dpi)
            print(p)


if __name__ == "__main__":
    main()
