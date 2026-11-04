#!/usr/bin/env python3
"""vmwatch.py <out.csv> -- cmd args...: run cmd; sample /proc/vmstat NUMA counters every 0.25 s and timestamp every GB-KERNEL line.
out.csv rows: 'v,<t>,<numa_hint_faults>,<numa_pte_updates>,<numa_pages_migrated>,<pgmigrate_success>' and 'k,<t_end>,<rep>,<seconds>'."""
import subprocess, sys, threading, time

out, cmd = sys.argv[1], sys.argv[sys.argv.index('--') + 1:]
KEYS = ("numa_hint_faults", "numa_pte_updates", "numa_pages_migrated", "pgmigrate_success")
stop = False
lock = threading.Lock()
f = open(out, "w")

def vm():
    d = {}
    for line in open("/proc/vmstat"):
        k, v = line.split()
        if k in KEYS: d[k] = int(v)
    return [d.get(k, 0) for k in KEYS]

def sampler():
    while not stop:
        with lock: f.write("v,%.3f,%s\n" % (time.time(), ",".join(map(str, vm()))))
        time.sleep(0.25)

th = threading.Thread(target=sampler); th.start()
p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, bufsize=1)
for line in p.stderr:
    if line.startswith("GB-KERNEL"):
        _, _, rep, sec = line.split()
        with lock: f.write("k,%.3f,%s,%s\n" % (time.time(), rep, sec))
p.wait(); stop = True; th.join(); f.close()
sys.exit(p.returncode)
