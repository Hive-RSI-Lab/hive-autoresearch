"""The autoresearch loop's core: measure, decide, keep or revert, log.

An agent edits the target repo, then runs `loop.py step`: the change is
committed, its tests run, the metric is measured a few times, and the
commit is kept only if the tests pass and it beats the best kept by more
than the metric's measured noise; otherwise the repo goes back to the best.
Every try is a row in results.tsv. `loop.py baseline` measures the
unchanged repo first and writes the log's first row.
"""
import argparse
import os
import statistics
import subprocess
import sys

HEADER = ["commit", "metric", "noise", "kept", "idea"]


def measure(cmd, cwd, repeats=3, timeout=None):
    """Run cmd `repeats` times; each run's last output line is a number."""
    samples = []
    for _ in range(repeats):
        out = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True,
                             text=True, timeout=timeout)
        if out.returncode != 0:
            raise RuntimeError(f"metric failed ({out.returncode}): {out.stderr.strip()[-500:]}")
        lines = out.stdout.strip().splitlines()
        if not lines:
            raise RuntimeError("metric printed nothing")
        samples.append(float(lines[-1].split()[-1]))
    return samples


def noise(samples):
    """The spread of repeated runs: what a change has to beat to count."""
    return max(samples) - min(samples) if len(samples) > 1 else 0.0


def decide(best, best_noise, cand, cand_noise, direction="lower", tests_ok=True):
    """Keep only a candidate whose tests pass and that beats best beyond the noise."""
    if not tests_ok:
        return False, "tests failed"
    margin = max(best_noise, cand_noise)
    gain = best - cand if direction == "lower" else cand - best
    if gain > margin:
        return True, f"beats {best:g} by {gain:g} (noise {margin:g})"
    return False, f"gain {gain:g} within noise {margin:g}"


def read_log(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        lines = [l.rstrip("\n") for l in f if l.strip()]
    return [dict(zip(HEADER, l.split("\t"))) for l in lines[1:]]


def append_result(path, commit, metric, noise_, kept, idea):
    new = not os.path.exists(path) or os.path.getsize(path) == 0
    idea = " ".join(str(idea).split())  # one line, no tabs
    kept = kept if isinstance(kept, str) else ("yes" if kept else "no")
    with open(path, "a") as f:
        if new:
            f.write("\t".join(HEADER) + "\n")
        f.write(f"{commit}\t{metric:g}\t{noise_:g}\t{kept}\t{idea}\n")


def best_kept(rows):
    """The last kept row (the baseline counts as kept): each kept row beat the one before."""
    kept = [r for r in rows if r["kept"] in ("yes", "baseline")]
    return kept[-1] if kept else None


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True,
                          text=True).stdout.strip()


def tests_pass(cmd, repo, timeout=None):
    if not cmd:
        return True
    return subprocess.run(cmd, shell=True, cwd=repo, capture_output=True,
                          timeout=timeout).returncode == 0


def baseline(repo, metric, log, repeats=3, timeout=None):
    samples = measure(metric, repo, repeats, timeout)
    m = statistics.median(samples)
    append_result(log, git(repo, "rev-parse", "--short", "HEAD"), m, noise(samples),
                  "baseline", "baseline")
    # "baseline" in the kept column marks the row everything is measured against
    return m


def step(repo, metric, log, idea, test=None, direction="lower", repeats=3, timeout=None):
    """Judge the working tree's change against the best kept; keep or revert it."""
    best = best_kept(read_log(log))
    if best is None:
        raise RuntimeError("no baseline in the log: run `loop.py baseline` first")
    best_sha = git(repo, "rev-parse", "HEAD")
    git(repo, "add", "-A")
    if not git(repo, "status", "--porcelain"):
        raise RuntimeError("no change to try")
    git(repo, "commit", "-q", "-m", f"autoresearch: {idea}")
    sha = git(repo, "rev-parse", "--short", "HEAD")
    ok = tests_pass(test, repo, timeout)
    try:
        samples = measure(metric, repo, repeats, timeout) if ok else []
    except (RuntimeError, ValueError, subprocess.TimeoutExpired):
        ok, samples = False, []
    m = statistics.median(samples) if samples else float("nan")
    n = noise(samples) if samples else 0.0
    kept, why = decide(float(best["metric"]), float(best["noise"]), m, n, direction, ok)
    if not kept:
        git(repo, "reset", "-q", "--hard", best_sha)
    append_result(log, sha, m, n, kept, idea)
    return kept, why


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("baseline", "step"):
        s = sub.add_parser(name)
        s.add_argument("--repo", required=True)
        s.add_argument("--metric", required=True, help="command whose last output line is the number")
        s.add_argument("--log", required=True, help="results.tsv")
        s.add_argument("--repeats", type=int, default=3)
        s.add_argument("--timeout", type=float, help="seconds per metric or test run")
        if name == "step":
            s.add_argument("--idea", required=True)
            s.add_argument("--test", help="command that must pass for a change to be kept")
            s.add_argument("--direction", choices=["lower", "higher"], default="lower")
    a = p.parse_args(argv)
    if a.cmd == "baseline":
        print(baseline(a.repo, a.metric, a.log, a.repeats, a.timeout))
        return 0
    kept, why = step(a.repo, a.metric, a.log, a.idea, a.test, a.direction, a.repeats, a.timeout)
    print(("kept: " if kept else "reverted: ") + why)
    return 0


if __name__ == "__main__":
    sys.exit(main())
