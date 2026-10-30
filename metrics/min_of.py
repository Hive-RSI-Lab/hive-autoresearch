#!/usr/bin/env python3
"""Run a metric command N times and print the smallest of its numbers.

  min_of.py N -- cmd args...

For wall time on a loaded machine: load only ever adds time, so the fastest
of a few runs is a steadier reading of what the code costs than their median.
cmd prints its number on its last stdout line (as metrics/proc_io.py does);
the key=value lines of the fastest run are passed on, then min_of=N and the
number. Exits non-zero, at once, as soon as one run does.
"""
import subprocess, sys

n = int(sys.argv[1])
cmd = sys.argv[2:]
if cmd[:1] == ["--"]:
    cmd = cmd[1:]
best = None
for _ in range(n):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, text=True)
    if p.returncode != 0:
        sys.stdout.write(p.stdout)
        sys.exit(p.returncode)
    lines = p.stdout.strip().splitlines()
    v = float(lines[-1])
    if best is None or v < best[0]:
        best = (v, lines[:-1])
for l in best[1]:
    print(l)
print(f"min_of={n}")
print(f"{best[0]:g}")
