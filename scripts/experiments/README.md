Scripts of the lf-vs-dc investigation (see ../../INVESTIGATION.md). They were run on the Chameleon node with the paths of that
node (`~/gb/...`, `~/logs/261103-genomicsbench/bin`) and are kept as a record, not as a polished tool.

* `exp-trace.sh` per-iteration traces (`GB_TRACE`) of chain/bsw/fmi, lf vs dc. `exp-vm.sh` + `vmwatch.py` sample /proc/vmstat NUMA
  counters per repetition. `exp-nonuma.sh`, `exp-rerun.sh` the same with `kernel.numa_balancing=0` (restored by a trap).
* `exp-shift.sh` (pileup, level shifts per process), `exp-fmi.sh` (fmi sawtooth reproduction).
* `build-lfvar.sh` + `exp-lfvar.sh`: private copies of the LF runtime with a different steal share and the chain run on them.
* `sim-diag-chain.py`, `sim-perm-chain.py`: critical-iteration and permutation experiments with `../sim-cilk-for.py`
  (they read `traces/chain-cost.npy`, the mean per-iteration cost of chain measured with GB_TRACE).
