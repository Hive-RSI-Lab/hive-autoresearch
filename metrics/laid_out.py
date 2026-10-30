#!/usr/bin/env python3
"""Run a command under strace and print the bytes it laid out in files.

  laid_out.py [--cwd DIR] [--tmpdir DIR] [--keep LOG] -- cmd args...

For a command whose writes are mostly mmapped (a linker's output), the
kernel's write_bytes depends on when writeback catches a page: a page
rewritten after it was written back counts twice, so it swings with the
machine's load. This counts what the command asked the filesystem for
instead, which holds still: for each regular file, the largest size an
ftruncate or fallocate gave it, else the bytes write/pwrite/writev put in it.
Pipes, sockets and /dev are left out. Prints key=value lines (laid_out_bytes,
write_bytes, sized_bytes, files, plus /proc/self/io's write_bytes as
io_write_bytes, wall_s), then laid_out_bytes alone. Exits with the
command's code. --tmpdir as in proc_io.py.
"""
import argparse, os, re, shutil, subprocess, sys, tempfile, time

ap = argparse.ArgumentParser()
ap.add_argument("--cwd")
ap.add_argument("--tmpdir")
ap.add_argument("--keep", help="keep the strace log here")
ap.add_argument("cmd", nargs=argparse.REMAINDER)
a = ap.parse_args()
cmd = a.cmd[1:] if a.cmd[:1] == ["--"] else a.cmd

env = dict(os.environ)
tmp = None
if a.tmpdir:
    os.makedirs(a.tmpdir, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=a.tmpdir)
    env["TMPDIR"] = tmp
fd, log = tempfile.mkstemp(prefix="laid-out-", suffix=".strace", dir=a.tmpdir)
os.close(fd)


def io():
    return {k: int(v) for k, v in (l.split(":") for l in open("/proc/self/io"))}


before, t = io(), time.time()
p = subprocess.run(["strace", "-f", "-qq", "-y", "-e", "signal=none", "-o", log,
                    "-e", "trace=write,pwrite64,writev,pwritev,pwritev2,ftruncate,fallocate"] + cmd,
                   cwd=a.cwd, env=env, stdout=subprocess.DEVNULL,
                   stderr=sys.stderr if os.environ.get("PROC_IO_VERBOSE") else subprocess.DEVNULL)
wall = time.time() - t
io_written = io()["write_bytes"] - before["write_bytes"]

# "PID call(FD</path>, ...) = N", or a call strace split: "<... call resumed>, ...) = N"
call = re.compile(r"^\d+\s+(\w+)\(\d+<([^>]*)>(.*)\)\s+=\s+(-?\d+)")
start = re.compile(r"^(\d+)\s+(\w+)\(\d+<([^>]*)>(.*)<unfinished \.\.\.>$")
resumed = re.compile(r"^(\d+)\s+<\.\.\. (\w+) resumed>(.*)\)\s+=\s+(-?\d+)")
pending = {}
written, sized = {}, {}


def count(name, path, args, ret):
    if ret < 0 or not path.startswith("/") or path.startswith("/dev/"):
        return
    if name in ("ftruncate", "fallocate"):
        size = int(re.findall(r"\d+", args)[-1]) + (int(re.findall(r"\d+", args)[-2]) if name == "fallocate" else 0)
        sized[path] = max(sized.get(path, 0), size)
    else:
        written[path] = written.get(path, 0) + ret


with open(log, errors="replace") as f:
    for line in f:
        line = line.rstrip("\n")
        m = call.match(line)
        if m:
            count(m.group(1), m.group(2), m.group(3), int(m.group(4)))
            continue
        m = start.match(line)
        if m:
            pending[(m.group(1), m.group(2))] = (m.group(3), m.group(4))
            continue
        m = resumed.match(line)
        if m and (m.group(1), m.group(2)) in pending:
            path, args = pending.pop((m.group(1), m.group(2)))
            count(m.group(2), path, args + m.group(3), int(m.group(4)))

if a.keep:
    shutil.move(log, a.keep)
else:
    os.remove(log)
if tmp:
    shutil.rmtree(tmp, ignore_errors=True)
w = sum(v for k, v in written.items() if k not in sized)
s = sum(sized.values())
d = dict(laid_out_bytes=w + s, write_bytes=w, sized_bytes=s, files=len(set(written) | set(sized)),
         io_write_bytes=io_written, wall_s=round(wall, 1))
for k, v in d.items():
    print(f"{k}={v}")
print(d["laid_out_bytes"])
sys.exit(p.returncode)
