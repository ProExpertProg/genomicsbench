# GenomicsBench on OpenCilk

This branch replaces the OpenMP / `std::thread` parallel loops of the CPU benchmarks with `cilk_for`.

| benchmark | loop | trip count (small input) | notes |
|---|---|---|---|
| fmi | batches of reads (`main`) | 1954 | 1M reads / batch 512 |
| bsw | batches of pairs (`main`) | 196 | 100k pairs / batch 512 |
| phmm | batches (`main`, repeated `-l` times) | 550 | |
| dbg | assembly regions (`main`) | 667 | region chr22:16.0M-16.5M |
| chain | calls (`host_chain_kernel`) | 1001 | |
| poa | batches (`main`) | 1000 | |
| pileup | 100 kb chunks (`main`) | 15 | |
| kmer-cnt | tasks per call of `processInParallel` | 1770 (one call per pass) | was a hand-written thread pool |

Not converted: `abea` (GPU/pthread pipeline), `grm` (plink, needs MKL), the Python benchmarks.
The OpenMP regions inside `bsw/bandedSWA.cpp` (sort-block loops) already ran with `num_threads(1)` inside the outer
parallel loop, so they are plain serial loops now.

Per-thread scratch state is indexed by the worker number (`gb_worker_id()` in `benchmarks/cilk_util.h`), and the thread-count
command-line arguments are ignored: the worker count is `CILK_NWORKERS`. Each loop prints
`CILKFOR-ITERS <name> <n>` on stderr.

## Findings (8 workers, WSL2, small inputs; medians of 2-3 runs, kernel seconds)

The trip counts are far below the cheetah default grainsize of 2048, so with the default every loop runs as
one serial chunk. Runtime grainsize 1 is the best or near-best everywhere; the compile-time coarsening factor
(1/4/16) makes no measurable difference for these coarse loops.

| benchmark | default | G=1 | G=4 | G=16 | G=64 |
|---|---|---|---|---|---|
| bsw | 0.25 | 0.10 | 0.06 | 0.06 | 0.11 |
| phmm | 7.3 | 1.4 | 1.4 | 1.7 | 1.6 |
| pileup (15 chunks) | 7.2 | 1.5 | 2.5 | 7.5 | 6.9 |
| chain | 1.9 | 0.36 | 0.36 | 0.37 | 0.40 |
| poa | 59 | 26 | 26 | 22 | 22 |
| dbg | 4.9 | 1.1 | 1.4 | 2.3 | 2.8 |
| fmi (chr22 index) | 52 | 8.4 | 8.7 | 8.8 | 9.3 |
| kmer-cnt | 12 | 6.1 | 4.7 | 4.2 | 4.3 |

## Pitfalls hit while porting

* Loops need unit stride to be lowered to the runtime `cilk_for` (`fmi`: `i += batch_size` with a runtime stride
  gave "could not compute finite loop trip count" and the loop ignored `CILK_GRAINSIZE`).
* Build with optimization (`fmi`'s Makefile had no `-O`; at `-O0` the runtime `cilk_for` lowering does not happen).
* The inlined ABI bitcode references `default_grainsize`, which is hidden in `libopencilk.so`: link the static runtime
  (`scripts/make-resource-dir.sh` does this with linker scripts).
* The cheetah runtime must be built with `-DCILK_DEFAULT_GRAINSIZE=<n>`, otherwise `CILK_GRAINSIZE` is ignored.
* Datasets: `fmi/broad*` is an 18 GB index. For the small run I built a bwa-mem2 index of chr22 only
  (`bwa-mem2 index -p broad chr22.fa`, set `FMI_INDEX`), so the fmi workload differs from upstream's.
  `dbg/small` is empty in the archive; the sweep uses the large BAM with the small region.
* bwa-mem2's `utils.h` fails with GCC >= 11 (use `g++-10` for `tools/bwa-mem2`).

## Running

```bash
# dependencies as in README.md (htslib, bwa-mem2, minimap2, spoa, GKL's libgkl_pairhmm_c)
export CLANG_BIN_DIR=~/OpenCilk/build/bin           # OpenCilk clang
export CHEETAH_BUILD=~/cheetah/build-release        # built with -DCILK_DEFAULT_GRAINSIZE=2048
scripts/sweep-cilk.sh -i ../input-datasets -T                         # trip counts only
scripts/sweep-cilk.sh -i ../input-datasets -w 8 -c "1 4 16" -g "default 1 4 16 64" -n 3 -o out
```

Output: `out/results.csv` (`bench,size,coarsen,grainsize,workers,rep,wall_s,kernel_s,iters,status`), per-run logs
and the binaries per coarsening factor under `out/`. See `scripts/sweep-cilk.sh -h`.
