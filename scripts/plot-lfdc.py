#!/usr/bin/env python3
"""G curves of the lf/dc sweep (sweep-lfdc.sh) in the format of the PBBS v2 sweep plots (pbbsbench_plots.py):
one row per benchmark, one column per worker count, x = runtime grainsize G (log2), y = median kernel time over the
trials. LF at the exact G (markers + line); DC smudged over [G/2, G], its effective grainsize. The first row (ALL)
is the geomean over the benchmarks of each cell divided by its benchmark's best cell.

    python3 plot-lfdc.py results.csv --out sweep.pdf
"""
import argparse

import pandas as pd

import pbbsbench_plots as pl

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("csv", help="results.csv of sweep-lfdc.sh")
ap.add_argument("--out", default="sweep.pdf")
ap.add_argument("-w", "--workers", default="32,64,128")
ap.add_argument("--stat", default="median", choices=["min", "median", "mean"])
ap.add_argument("--per-page", type=int, default=5)
ap.add_argument("--title", default="GenomicsBench lf vs dc")
a = ap.parse_args()

d = pd.read_csv(a.csv)
s = (d.groupby(["bench", "config", "workers", "grain"])["kernel_s"].agg(a.stat).rename("value").reset_index()
     .rename(columns={"grain": "grainsize"}).assign(coarsen=0))   # no -stripmine-coarsen-factor in this sweep
s.attrs.update(unit="time [s]", dropped=[], nobase=[])
workers = [int(w) for w in a.workers.split(",")]
figs = pl.plot_sweep(s, workers=workers, smudged=("dc",), per_page=a.per_page, title=a.title)
if a.out.endswith(".pdf"):
    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(a.out) as pdf:
        for f in figs:
            pdf.savefig(f)
else:
    import os
    root, ext = os.path.splitext(a.out)
    for i, f in enumerate(figs):
        f.savefig(f"{root}-{i + 1}{ext}" if len(figs) > 1 else a.out, dpi=150)
print(f"{len(figs)} pages -> {a.out}")
