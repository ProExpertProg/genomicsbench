#!/bin/bash
# A/B: the same NUMA-counter probe with automatic NUMA balancing disabled; the setting is always restored
old=$(cat /proc/sys/kernel/numa_balancing)
trap 'sudo sysctl -q -w kernel.numa_balancing=$old; echo "restored numa_balancing=$(cat /proc/sys/kernel/numa_balancing)"' EXIT
sudo sysctl -q -w kernel.numa_balancing=0
echo "numa_balancing now $(cat /proc/sys/kernel/numa_balancing) (was $old)"
~/gb/exp-vm.sh "lf dc lf dc lf dc" off
