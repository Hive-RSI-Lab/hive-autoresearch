"""The project's score: the best kept improvement in the latest results log.

Prints the % reduction of the target metric, best kept row against the
baseline row, in the newest runs/*/results.tsv (newest by last commit, then
by modification time); 0 when there is no run yet. A row is kept only when
the target's tests passed, so the best kept is always a green one.
"""
import glob
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from loop import best_kept, read_log  # noqa: E402


def committed_at(path):
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%ct", "--", os.path.basename(path)],
                             cwd=os.path.dirname(path) or ".", capture_output=True, text=True).stdout
        return int(out.strip() or 0)
    except (OSError, ValueError):
        return 0


def latest_log(root):
    logs = glob.glob(os.path.join(root, "runs", "*", "results.tsv"))
    return max(logs, key=lambda p: (committed_at(p), os.path.getmtime(p)), default=None)


def score(path):
    if path is None:
        return 0.0
    rows = read_log(path)
    base = next((r for r in rows if r["kept"] == "baseline"), None)
    best = best_kept(rows)
    if base is None or best is None or float(base["metric"]) == 0:
        return 0.0
    b, m = float(base["metric"]), float(best["metric"])
    return max(0.0, (b - m) / abs(b) * 100)


def main(argv):
    root = argv[1] if len(argv) > 1 else "."
    path = latest_log(root)
    print(f"log: {path or '(no run yet)'}")
    print(f"{score(path):.2f}")


if __name__ == "__main__":
    main(sys.argv)
