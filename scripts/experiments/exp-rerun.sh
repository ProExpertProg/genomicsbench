#!/bin/bash
# targeted rerun of the cases where LF looked slower, with automatic NUMA balancing off (always restored)
old=$(cat /proc/sys/kernel/numa_balancing)
trap 'sudo sysctl -q -w kernel.numa_balancing=$old; echo "restored numa_balancing=$(cat /proc/sys/kernel/numa_balancing)"' EXIT
sudo sysctl -q -w kernel.numa_balancing=0
echo "numa_balancing now $(cat /proc/sys/kernel/numa_balancing) (was $old) $(date +%T)"
OUT=~/logs/261103-numa-off; mkdir -p $OUT; ln -sfn ~/logs/261103-genomicsbench/bin $OUT/bin
cd ~/gb/genomicsbench
S="scripts/sweep-lfdc.sh -S -o $OUT"
$S -b chain -w 64 -g 4,8,64
$S -b bsw -w 128 -g 8,16
$S -b fmi -w 128 -g 2,8
$S -b pileup -w 32 -g 16
echo RERUNDONE $(date +%T)
