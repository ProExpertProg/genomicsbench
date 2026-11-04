#!/bin/bash
# usage: exp-trace.sh <bench> <workers> "<G list>" <processes per point> [reps]
b=$1 W=$2 Gs=$3 N=${4:-1} R=${5:-11}
D=~/gb/data/input-datasets; B=~/gb/trace/bin; O=~/gb/trace/runs; mkdir -p $O
cmd() { case $1 in
 chain) echo "$2 -i $D/chain/large/c_elegans_40x.10k.in -o /dev/null";;
 bsw)   echo "$2 -pairs $D/bsw/large/bandedSWA_SRR7733443_1m_input.txt -t 1 -b 512";;
 fmi)   echo "$2 $D/fmi/broad $D/fmi/large/SRR7733443_10m_1.fastq 512 19 1";;
esac; }
pin() { local n=128 f=0; [ "$1" -le 64 ] && f=64; echo $f-$((f + $1 - 1)); }
for ((k=1; k<=N; k++)); do for G in $Gs; do for c in dc lf; do
  d=$O/$b-$c-w$W-g$G-$k; mkdir -p $d
  env GB_REPEAT=$R GB_TRACE=$d CILK_NWORKERS=$W CILK_GRAINSIZE=$G setarch x86_64 -R taskset -c $(pin $W) ionice -c 2 -n 0 $(cmd $b $B/$c/$b) > $d/out.log 2>&1
  echo "$b $c w=$W G=$G #$k: $(grep '^GB-KERNEL' $d/out.log | awk '$3>0{printf "%.3f ", $4}')"
done; done; done
echo EXPDONE
