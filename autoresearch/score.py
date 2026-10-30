"""The project's score: the summed best kept gain of every loop run.

Each runs/<name>/ that holds a results.tsv and the config.json it ran from
(with its metric command) is one run. A run's gain is the % its best kept
row improves on its baseline row, in the direction config.json names
(min/lower, the default, or max/higher); a row is kept only when the
target's tests passed. The score is the sum over runs, so a new run starting
from its baseline adds 0 and lowers nothing. 0 when there is no run yet.

A run counts only once its gain is on the target's main: runs/<name>/landed.json
names the target project and the commit on its main that carries the kept
change ({"project": "hive", "commit": "2a17147b"}, optionally "still": [[path,
text], ...], lines that must still be in main's files). The score checks it in
the target's clone under $HIVE_PROJECTS (/hive/projects by default, mounted
read-only in a score check): the commit is an ancestor of main, every file it
left is still on main, and each "still" text is still in its file. A run with no
landed.json, or whose change main has since dropped (its files deleted), is
listed as not counted, so a gain on code that never reached the target, or that
the target has since deleted, adds nothing.

Self-contained on purpose: everything that decides the score is in this
file (the project's score.paths), and it reads results.tsv by its header's
column names, so the loop that writes the log can change freely.
"""
import csv
import glob
import json
import os
import subprocess
import sys

KEPT = ("yes", "baseline")


def read_rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def direction(run_dir):
    with open(os.path.join(run_dir, "config.json")) as f:
        d = str(json.load(f).get("direction", "min")).lower()
    return "max" if d in ("max", "higher") else "min"


def run_gain(run_dir):
    """The run's best kept % gain over its baseline, or (None, why) when it doesn't count."""
    if not os.path.isfile(os.path.join(run_dir, "config.json")):
        return None, "no config.json beside results.tsv (what ran: target, metric command)"
    try:
        sign = 1 if direction(run_dir) == "min" else -1
        rows = read_rows(os.path.join(run_dir, "results.tsv"))
        base = next((r for r in rows if r.get("kept") == "baseline"), None)
        if base is None:
            return None, "no baseline row"
        b = float(base["metric"])
        kept = [float(r["metric"]) for r in rows if r.get("kept") in KEPT]
    except (OSError, ValueError, KeyError, TypeError) as e:
        return None, f"unreadable: {e}"
    if b == 0:
        return None, "baseline metric is 0"
    best = min(kept, key=lambda m: sign * m)
    return max(0.0, sign * (b - best) / abs(b) * 100), "ok"


def projects_dir():
    return os.environ.get("HIVE_PROJECTS") or "/hive/projects"


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)


def landed(run_dir):
    """(True, "") when the run's change is on its target's main, else (False, why)."""
    try:
        with open(os.path.join(run_dir, "landed.json")) as f:
            l = json.load(f)
        project, commit = str(l["project"]), str(l["commit"])
        still = [(str(p), str(t)) for p, t in l.get("still", [])]
    except FileNotFoundError:
        return False, "no landed.json: its change isn't shown to be on the target's main"
    except (OSError, ValueError, KeyError, TypeError) as e:
        return False, f"landed.json unreadable: {e}"
    repo = os.path.join(projects_dir(), project)
    if not os.path.isdir(repo):
        return False, f"no clone of {project} at {repo} to check it landed"
    main = "main" if git(repo, "rev-parse", "--verify", "-q", "main^{commit}").returncode == 0 else "HEAD"
    if git(repo, "merge-base", "--is-ancestor", commit, main).returncode != 0:
        return False, f"{project} {commit} is not on {project}'s main"
    first = git(repo, "rev-parse", "--verify", "-q", commit + "^1").returncode == 0
    diff = (["diff", "--name-only", "--diff-filter=d", commit + "^1", commit] if first
            else ["ls-tree", "-r", "--name-only", commit])
    out = git(repo, *diff)
    if out.returncode != 0:
        return False, f"can't list {project} {commit}'s files: {out.stderr.strip()}"
    for path in out.stdout.split():
        if git(repo, "cat-file", "-e", f"{main}:{path}").returncode != 0:
            return False, f"{path} (changed by {project} {commit}) is gone from {project}'s main"
    for path, text in still:
        blob = git(repo, "show", f"{main}:{path}")
        if blob.returncode != 0 or text not in blob.stdout:
            return False, f"{path} on {project}'s main no longer has {text!r}"
    return True, ""


def runs(root):
    return sorted(os.path.dirname(p) for p in glob.glob(os.path.join(root, "runs", "*", "results.tsv")))


def score(root):
    total, lines = 0.0, []
    for d in runs(root):
        gain, why = run_gain(d)
        name = os.path.basename(d)
        if gain is not None:
            ok, why = landed(d)
            if not ok:
                gain = None
        if gain is None:
            lines.append(f"{name}: not counted, {why}")
        else:
            total += gain
            lines.append(f"{name}: {gain:.2f}")
    return total, lines


def main(argv):
    root = argv[1] if len(argv) > 1 else "."
    total, lines = score(root)
    for l in lines or ["(no run yet)"]:
        print(l)
    print(f"{total:.2f}")


if __name__ == "__main__":
    main(sys.argv)
