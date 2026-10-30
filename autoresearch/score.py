"""The project's score: the summed best kept gain of every loop run.

Each runs/<name>/ that holds a results.tsv and the config.json it ran from
(with its metric command) is one run. A run's gain is the % its best kept
row improves on its baseline row, in the direction config.json names
(min/lower, the default, or max/higher); a row is kept only when the
target's tests passed. The score is the sum over runs, so a new run starting
from its baseline adds 0 and lowers nothing. 0 when there is no run yet.

Self-contained on purpose: everything that decides the score is in this
file (the project's score.paths), and it reads results.tsv by its header's
column names, so the loop that writes the log can change freely.
"""
import csv
import glob
import json
import os
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


def runs(root):
    return sorted(os.path.dirname(p) for p in glob.glob(os.path.join(root, "runs", "*", "results.tsv")))


def score(root):
    total, lines = 0.0, []
    for d in runs(root):
        gain, why = run_gain(d)
        name = os.path.basename(d)
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
