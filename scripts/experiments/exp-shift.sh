#!/bin/bash
# frequency of "slow phase then speed-up" processes: pileup, 128 workers, G=2, alternating lf/dc
B=~/logs/261103-genomicsbench/bin; D=~/gb/data/input-datasets
for k in 1 2 3 4 5 6 7 8; do for c in lf dc; do
  r=$(env GB_REPEAT=11 CILK_NWORKERS=128 CILK_GRAINSIZE=2 setarch x86_64 -R taskset -c 0-127 ionice -c 2 -n 0 $B/$c/pileup $D/pileup/large/HG002_prom_R941_guppy360_2_GRCh38_ch20.bam chr20:1-64444167 1 2>&1 | grep '^GB-KERNEL' | awk '$3>0{printf "%.2f ", $4}')
  echo "pileup $c G=2 #$k $(date +%T): $r"
done; done
echo SHIFTDONE
