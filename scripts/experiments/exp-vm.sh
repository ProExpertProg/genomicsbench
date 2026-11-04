#!/bin/bash
# bsw at 128 workers (no tracing: the binaries of the sweep), 21 reps, with NUMA counters sampled; usage: exp-vm.sh "<cfg list>" <tag>
B=~/logs/261103-genomicsbench/bin; D=~/gb/data/input-datasets; O=~/gb/vm; mkdir -p $O
k=0
for c in $1; do k=$((k+1))
  env GB_REPEAT=21 CILK_NWORKERS=128 CILK_GRAINSIZE=1 setarch x86_64 -R taskset -c 0-127 ionice -c 2 -n 0 \
    python3 ~/gb/vmwatch.py $O/bsw-$c-$2-$k.csv -- $B/$c/bsw -pairs $D/bsw/large/bandedSWA_SRR7733443_1m_input.txt -t 1 -b 512
  echo "done bsw $c #$k numa_balancing=$(cat /proc/sys/kernel/numa_balancing)"
done
echo VMDONE
