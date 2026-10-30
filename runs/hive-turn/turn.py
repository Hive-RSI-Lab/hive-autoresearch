#!/usr/bin/env python3
"""Bytes one hive worker turn's routine lays out on disk, in the env the target gives a worker.

Run from the target (an ihsan-sa/hive clone). It asks the target's own code
for a worker's sandbox env (a throwaway test calls Runs.sandboxSpec for a
worker run in home, HOME a placeholder for the hive user's home), keeps the
cache settings in it, then times what a worker does in a fresh run HOME:
clone the project as NewCheckout does (git clone --no-local --no-hardlinks),
go build ./..., go vet and go test -short one package. The hive user's home
is SHARED (default /home/hive, whose caches agents in home fill). Modules
come from SHARED's download cache with no network (a cold HOME extracts them
as a fetch would). Prints laid_out.py's key=value lines and the bytes.
"""
import os, shutil, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LAID_OUT = os.path.join(HERE, "..", "..", "metrics", "laid_out.py")
SHARED = os.environ.get("SHARED", "/home/hive")
SCRATCH = os.environ.get("SCRATCH", "/tmp/ar4/turns")
PLACE = "/hive-user-home-probe"
CACHE_KEYS = ("GOCACHE", "GOMODCACHE", "GOPATH", "XDG_CACHE_HOME", "GOFLAGS", "UV_CACHE_DIR", "PIP_CACHE_DIR")
PROBE = '''package core

import (
	"fmt"
	"path/filepath"
	"testing"

	"github.com/ihsan-sa/hive-standalone-build/internal/harness"
)

func TestZZTurnEnvProbe(t *testing.T) {
	c, _ := testHive(t)
	t.Setenv("HOME", "%s")
	h, _ := harness.Get("fake")
	s, err := c.Runs.sandboxSpec(c.WS.LoadConfig(), isolatedSB{}, h, Run{RunSpec: RunSpec{ID: "w1", Role: "worker", Harness: "fake"}}, 1, false, filepath.Join(t.TempDir(), "p"), nil, "")
	if err != nil {
		t.Fatal(err)
	}
	for _, kv := range s.Env {
		fmt.Println("TURNENV " + kv)
	}
}
''' % PLACE

ROUTINE = """set -e
git clone -q --no-local --no-hardlinks "$1" work
cd work
go build ./...
go vet ./internal/agentcli
go test -short -count=1 ./internal/agentcli
"""


def turn_env(target):
    probe = os.path.join(target, "internal", "core", "zz_turn_env_probe_test.go")
    with open(probe, "w") as f:
        f.write(PROBE)
    try:
        p = subprocess.run(["go", "test", "-count=1", "-run", "^TestZZTurnEnvProbe$", "-v", "./internal/core"],
                           cwd=target, capture_output=True, text=True,
                           env=dict(os.environ, GOTOOLCHAIN="local"))
    finally:
        os.remove(probe)
    if p.returncode:
        sys.exit("probe failed:\n" + (p.stdout + p.stderr)[-2000:])
    env = {}
    for l in p.stdout.splitlines():
        if l.startswith("TURNENV "):
            k, _, v = l[8:].partition("=")
            env[k] = v
    return env


def main():
    target = os.getcwd()
    got = turn_env(target)
    # One fixed folder, as every worker's checkout is /work in its sandbox:
    # go's cache keys a package's build by its folder, so a new path a turn
    # would miss every build of the project's own packages.
    run = os.path.join(SCRATCH, "turn")
    if os.path.exists(run):
        subprocess.run(["chmod", "-R", "u+w", run])
        shutil.rmtree(run)
    home, tmp = os.path.join(run, "home"), os.path.join(run, "tmp")
    os.makedirs(home)  # makes run too
    os.makedirs(tmp)
    env = {"PATH": os.environ["PATH"], "HOME": home, "TMPDIR": tmp, "LANG": "C.UTF-8", "GOTOOLCHAIN": "local",
           "GOPROXY": "file://" + os.path.join(SHARED, "go", "pkg", "mod", "cache", "download")}
    for k in CACHE_KEYS:
        if k in got:
            v = got[k].replace(PLACE, SHARED).replace(got.get("HOME", "/hive/home"), home)
            env[k] = v
            print(f"env_{k}={v}")
    try:
        keep = ["--keep", os.environ["TURN_KEEP"]] if os.environ.get("TURN_KEEP") else []
        p = subprocess.run([sys.executable, LAID_OUT, "--cwd", run] + keep + ["--", "sh", "-c", ROUTINE, "sh", target],
                           env=env, capture_output=True, text=True)
        sys.stdout.write(p.stdout)
        sys.stderr.write(p.stderr)
        sys.exit(p.returncode)
    finally:
        subprocess.run(["chmod", "-R", "u+w", run])
        shutil.rmtree(run, ignore_errors=True)


main()
