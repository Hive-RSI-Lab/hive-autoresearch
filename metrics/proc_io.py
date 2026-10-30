#!/usr/bin/env python3
"""Run a command and print what it and every child it reaped wrote.

  proc_io.py [--field write_bytes] [--cwd DIR] [--tmpdir DIR] -- cmd args...

The kernel folds a reaped child's I/O counters into its parent's, so after
waiting, the growth in this process's /proc/self/io is the whole tree's
(a child orphaned to init is not counted). Prints key=value lines (every
/proc/self/io field, net_write_bytes = write_bytes - cancelled_write_bytes,
wall_s, cpu_s, cpu_ms), then the chosen field alone on the last line. Exits with the
command's code. --tmpdir points TMPDIR at a fresh directory on a real disk
(a tmpfs /tmp counts no write_bytes) and removes it after.
"""
import argparse, os, resource, shutil, subprocess, sys, tempfile, time

ap = argparse.ArgumentParser()
ap.add_argument("--field", default="write_bytes")
ap.add_argument("--cwd")
ap.add_argument("--tmpdir")
ap.add_argument("cmd", nargs=argparse.REMAINDER)
a = ap.parse_args()
cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd

def io():
    return {k: int(v) for k, v in (l.split(":") for l in open("/proc/self/io"))}

env = dict(os.environ)
tmp = None
if a.tmpdir:
    os.makedirs(a.tmpdir, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=a.tmpdir)
    env["TMPDIR"] = tmp
before, t = io(), time.time()
p = subprocess.run(cmd, cwd=a.cwd, env=env, stdout=subprocess.DEVNULL, stderr=sys.stderr if os.environ.get("PROC_IO_VERBOSE") else subprocess.DEVNULL)
wall = time.time() - t
after = io()
ru = resource.getrusage(resource.RUSAGE_CHILDREN)
if tmp:
    shutil.rmtree(tmp, ignore_errors=True)
d = {k: after[k] - before[k] for k in after}
d["net_write_bytes"] = d["write_bytes"] - d["cancelled_write_bytes"]
d["wall_s"] = round(wall, 1)
d["cpu_s"] = round(ru.ru_utime + ru.ru_stime, 1)
d["cpu_ms"] = round((ru.ru_utime + ru.ru_stime) * 1000)
for k, v in d.items():
    print(f"{k}={v}")
print(d[a.field])
sys.exit(p.returncode)
