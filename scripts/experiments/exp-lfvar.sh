#!/bin/bash
# chain, 64 workers: stock dc and lf against private LF variants (thief takes 2/3 or 4/5 of the victim's remaining chunks); NUMA balancing off
set -e
W=~/gb/lfvar; mkdir -p $W/cheetah; cd $W/cheetah
ln -sfn ~/OpenCilk/opencilk/cheetah/cmake-build-release-dc cmake-build-release-dc
ln -sfn ~/OpenCilk/opencilk/cheetah/cmake-build-release-lf cmake-build-release-lf
ln -sfn ~/gb/cl/cheetah-lf67/cmake-build-release-lf cmake-build-release-lf67
ln -sfn ~/gb/cl/cheetah-lf80/cmake-build-release-lf cmake-build-release-lf80
cd ~/gb/genomicsbench
scripts/sweep-lfdc.sh -C -B $W/cheetah -r dc,lf,lf67,lf80 -b chain -o $W/out
old=$(cat /proc/sys/kernel/numa_balancing)
trap 'sudo sysctl -q -w kernel.numa_balancing=$old; echo "restored numa_balancing=$(cat /proc/sys/kernel/numa_balancing)"' EXIT
sudo sysctl -q -w kernel.numa_balancing=0
scripts/sweep-lfdc.sh -S -B $W/cheetah -r dc,lf,lf67,lf80 -b chain -w 64 -g 4,8,64 -o $W/out
echo LFVARDONE
