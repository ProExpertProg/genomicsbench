#!/bin/bash
# fmi at 128 workers: does the slow phase of LF G=2/8 reproduce, and does it depend on process order?
B=~/logs/261103-genomicsbench/bin; D=~/gb/data/input-datasets
echo "numa_balancing=$(cat /proc/sys/kernel/numa_balancing) thp=$(cat /sys/kernel/mm/transparent_hugepage/enabled)"
run() { # cfg G tag
  env GB_REPEAT=11 CILK_NWORKERS=128 CILK_GRAINSIZE=$2 setarch x86_64 -R taskset -c 0-127 ionice -c 2 -n 0 $B/$1/fmi $D/fmi/broad $D/fmi/large/SRR7733443_10m_1.fastq 512 19 1 2>&1 | grep '^GB-KERNEL' | awk -v t="$1 G=$2 $3" '$3>0{printf "%.2f ", $4} END{print " <- " t}'
}
for i in 1 2 3; do run lf 2 "rep$i"; done
for i in 1 2; do run dc 2 "rep$i"; done
for i in 1 2; do run lf 4 "rep$i"; run lf 8 "rep$i"; done
echo EXPDONE
