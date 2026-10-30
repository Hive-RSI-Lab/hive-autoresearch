#!/usr/bin/env python3
"""One autoresearch loop: measure, keep or revert, log.

The agent following program.md edits the target repo's editable files, then
calls `loop.py try --idea "..."`. This script does the rest: it checks only
editable files changed, builds, runs the metric enough times to see past the
noise, keeps the change as a commit on the loop's branch only if it beats the
best by more than the margin and the tests pass, else reverts it, and appends
the try to results.tsv either way.

  loop.py -c CONFIG baseline     measure the untouched target, set the noise
  loop.py -c CONFIG try --idea   judge the working tree's change
  loop.py -c CONFIG status       best, noise, experiments left
  loop.py -c CONFIG plot         write curve.svg next to results.tsv

The config (JSON) names the target repo, its loop branch, the editable globs,
the prepare/check/metric commands, the direction (min or max), the
per-experiment budget in seconds and the experiment cap. Commands run in the
target repo through `sh -c`, niced; the metric prints its number on the last
line of stdout and may print `key=value` lines before it, which are logged.
A metric that exits non-zero means the tests failed.
"""

import argparse
import fnmatch
import json
import os
import shutil
import statistics
import subprocess
import sys
import time

COLUMNS = ["n", "time", "commit", "metric", "runs", "wall_s", "kept", "idea", "extra"]


def load(path):
    with open(path) as f:
        cfg = json.load(f)
    cfg["dir"] = os.path.dirname(os.path.abspath(path))
    cfg.setdefault("direction", "min")
    cfg.setdefault("budget_s", 600)
    cfg.setdefault("baseline_runs", 3)
    cfg.setdefault("max_runs", 3)
    cfg.setdefault("min_gain", 0.01)
    cfg.setdefault("max_experiments", 20)
    return cfg


def sh(cfg, cmd, timeout=None, capture=True):
    env = dict(os.environ, LOOP_DIR=cfg["dir"])
    return subprocess.run(["nice", "-n", "10", "sh", "-c", cmd], cwd=cfg["target"], env=env,
                          timeout=timeout, text=True, capture_output=capture)


def git(cfg, *args):
    p = subprocess.run(["git", *args], cwd=cfg["target"], text=True, capture_output=True)
    if p.returncode:
        sys.exit(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.stdout.strip()


def tsv(cfg):
    return os.path.join(cfg["dir"], "results.tsv")


def rows(cfg):
    if not os.path.exists(tsv(cfg)):
        return []
    with open(tsv(cfg)) as f:
        lines = f.read().splitlines()
    return [dict(zip(COLUMNS, l.split("\t"))) for l in lines[1:] if l]


def append(cfg, row):
    new = not os.path.exists(tsv(cfg))
    with open(tsv(cfg), "a") as f:
        if new:
            f.write("\t".join(COLUMNS) + "\n")
        f.write("\t".join(str(row.get(c, "")).replace("\t", " ").replace("\n", " ") for c in COLUMNS) + "\n")


def state(cfg):
    p = os.path.join(cfg["dir"], "state.json")
    return json.load(open(p)) if os.path.exists(p) else {}


def save_state(cfg, st):
    with open(os.path.join(cfg["dir"], "state.json"), "w") as f:
        json.dump(st, f, indent=1)


def better(cfg, a, b):
    return a < b if cfg["direction"] == "min" else a > b


def gain(cfg, new, best):
    """Relative improvement of new over best, positive when better."""
    return (best - new) / best if cfg["direction"] == "min" else (new - best) / best


def changed(cfg):
    out = subprocess.run(["git", "status", "--porcelain", "--untracked-files=all"], cwd=cfg["target"],
                         text=True, capture_output=True, check=True).stdout
    return [l[3:].split(" -> ")[-1] for l in out.splitlines() if l]


def editable(cfg, path):
    return any(fnmatch.fnmatch(path, g) for g in cfg["editable"])


def revert(cfg, paths):
    git(cfg, "reset", "-q", "--", *paths)  # drop try's `add -N`, so new files count as untracked
    tracked = [p for p in paths if subprocess.run(["git", "ls-files", "--error-unmatch", p], cwd=cfg["target"],
                                                  capture_output=True).returncode == 0]
    if tracked:
        git(cfg, "checkout", "--", *tracked)
    for p in set(paths) - set(tracked):
        full = os.path.join(cfg["target"], p)
        shutil.rmtree(full) if os.path.isdir(full) else os.remove(full)


def run_metric(cfg):
    """One measurement: (value or None, wall seconds, extras, error text)."""
    t = time.time()
    try:
        p = sh(cfg, cfg["metric"], timeout=cfg["budget_s"])
    except subprocess.TimeoutExpired:
        return None, time.time() - t, {}, f"over the {cfg['budget_s']} s budget"
    wall = time.time() - t
    lines = p.stdout.strip().splitlines()
    if p.returncode or not lines:
        return None, wall, {}, (p.stdout + p.stderr)[-1500:] or f"metric exited {p.returncode} with no output"
    extras = dict(l.split("=", 1) for l in lines[:-1] if "=" in l)
    return float(lines[-1]), wall, extras, ""


def measure(cfg, runs, judge=None):
    """Run the metric up to runs times; judge(values) may stop early by
    returning a verdict. Returns (values, walls, extras, error)."""
    vals, walls, extras = [], [], {}
    for _ in range(runs):
        v, w, ex, err = run_metric(cfg)
        if v is None:
            return vals, walls, extras, err
        vals.append(v)
        walls.append(w)
        extras = ex
        print(f"  run {len(vals)}: {v:,.0f} in {w:.0f} s", flush=True)
        if judge and judge(vals) is not None:
            break
    return vals, walls, extras, ""


def spread(vals):
    m = statistics.median(vals)
    return (max(vals) - min(vals)) / abs(m) if len(vals) > 1 and m else 0.0


def margin(cfg, st):
    return max(cfg["min_gain"], 3 * st.get("noise", 0.0))


def prepare(cfg):
    for key in ("prepare", "check"):
        if cfg.get(key):
            p = sh(cfg, cfg[key], timeout=cfg["budget_s"])
            if p.returncode:
                return f"{key} failed: " + (p.stdout + p.stderr)[-1500:]
    return ""


def cmd_baseline(cfg, a):
    st = state(cfg)
    if not st.get("branch_made"):
        if git(cfg, "rev-parse", "--abbrev-ref", "HEAD") != cfg["branch"]:
            git(cfg, "checkout", "-b", cfg["branch"])
        st["branch_made"] = True
    if changed(cfg):
        sys.exit("baseline wants a clean target: " + ", ".join(changed(cfg)))
    err = prepare(cfg)
    if err:
        sys.exit(err)
    vals, walls, ex, err = measure(cfg, a.runs or cfg["baseline_runs"])
    if err:
        sys.exit("baseline metric failed: " + err)
    best = statistics.median(vals)
    st.update(best=best, noise=max(st.get("noise", 0.0), spread(vals)), commit=git(cfg, "rev-parse", "--short", "HEAD"))
    save_state(cfg, st)
    append(cfg, dict(n=0, time=time.strftime("%Y-%m-%dT%H:%M:%S"), commit=st["commit"], metric=f"{best:.0f}",
                     runs=",".join(f"{v:.0f}" for v in vals), wall_s=f"{statistics.median(walls):.1f}",
                     kept="baseline", idea=a.idea or "baseline", extra=" ".join(f"{k}={v}" for k, v in ex.items())))
    print(f"baseline {best:,.0f}  noise {st['noise']:.2%}  margin {margin(cfg, st):.2%}")


def cmd_try(cfg, a):
    st = state(cfg)
    if "best" not in st:
        sys.exit("run baseline first")
    n = len(rows(cfg))
    if n > cfg["max_experiments"]:
        sys.exit(f"the cap of {cfg['max_experiments']} experiments is spent")
    paths = changed(cfg)
    if not paths:
        sys.exit("nothing changed")
    outside = [p for p in paths if not editable(cfg, p)]
    if outside:
        sys.exit("changed outside the editable files (revert them yourself): " + ", ".join(outside))
    patch = os.path.join(cfg["dir"], "patches", f"{n:03d}.patch")
    os.makedirs(os.path.dirname(patch), exist_ok=True)
    git(cfg, "add", "-N", "--", *paths)
    with open(patch, "w") as f:
        f.write(f"# {a.idea}\n" + git(cfg, "diff") + "\n")
    best, m = st["best"], margin(cfg, st)
    print(f"try {n}: {a.idea}\n  best {best:,.0f}, needs {m:.2%} better")

    def judge(vals):
        med = statistics.median(vals)
        if not better(cfg, med, best) and len(vals) >= 1:
            return False  # no better at all: one run is enough to say so
        if len(vals) >= 2 and all(gain(cfg, v, best) > m for v in vals):
            return True
        return None

    err = prepare(cfg)
    vals, walls, ex = [], [], {}
    if not err:
        vals, walls, ex, err = measure(cfg, cfg["max_runs"], judge)
    med = statistics.median(vals) if vals else None
    keep = not err and med is not None and len(vals) >= 2 and gain(cfg, med, best) > m
    commit = "-"
    if keep:
        git(cfg, "add", "--", *paths)
        git(cfg, "commit", "-q", "-m", a.idea)
        commit = git(cfg, "rev-parse", "--short", "HEAD")
        st.update(best=med, commit=commit, noise=max(st.get("noise", 0.0), spread(vals)))
        save_state(cfg, st)
    else:
        revert(cfg, paths)
    verdict = "crash" if err else ("yes" if keep else "no")
    append(cfg, dict(n=n, time=time.strftime("%Y-%m-%dT%H:%M:%S"), commit=commit,
                     metric=f"{med:.0f}" if med is not None else "", runs=",".join(f"{v:.0f}" for v in vals),
                     wall_s=f"{statistics.median(walls):.1f}" if walls else "", kept=verdict, idea=a.idea,
                     extra=" ".join(f"{k}={v}" for k, v in ex.items())))
    if err:
        print("  CRASH (reverted): " + err)
    elif med is not None:
        print(f"  {'KEPT' if keep else 'reverted'}: {med:,.0f} ({gain(cfg, med, best):+.2%} vs best)")


def cmd_status(cfg, a):
    st = state(cfg)
    rs = rows(cfg)
    print(json.dumps(dict(best=st.get("best"), commit=st.get("commit"), noise=st.get("noise"),
                          margin=margin(cfg, st), experiments=max(len(rs) - 1, 0),
                          cap=cfg["max_experiments"], kept=sum(r["kept"] == "yes" for r in rs)), indent=1))


def cmd_plot(cfg, a):
    rs = [r for r in rows(cfg) if r["metric"]]
    if not rs:
        sys.exit("nothing to plot")
    scale, unit = (1e6, "MB") if max(float(r["metric"]) for r in rs) > 1e6 else (1, "")
    W, H, L, R, T, B = 720, 380, 64, 24, 64, 48
    xs = [int(r["n"]) for r in rs]
    ys = [float(r["metric"]) / scale for r in rs]
    xmax, ymax = max(xs + [1]), max(ys) * 1.08
    X = lambda x: L + (W - L - R) * x / xmax
    Y = lambda y: T + (H - T - B) * (1 - y / ymax)
    blue, muted, ink, ink2, grid, surf = "#2a78d6", "#898781", "#0b0b0b", "#52514e", "#e6e5e0", "#fcfcfb"
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" font-family="system-ui,sans-serif" font-size="12">',
         f'<rect width="{W}" height="{H}" fill="{surf}"/>',
         f'<text x="{L}" y="22" font-size="14" fill="{ink}">{cfg.get("title", "metric")} ({unit or "value"}, lower is better)</text>'
         if cfg["direction"] == "min" else f'<text x="{L}" y="22" font-size="14" fill="{ink}">{cfg.get("title", "metric")}</text>']
    for i in range(5):
        v = ymax * i / 4
        o.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="{grid}"/>')
        o.append(f'<text x="{L - 8}" y="{Y(v) + 4:.1f}" text-anchor="end" fill="{muted}">{v:.0f}</text>')
    for x in range(0, xmax + 1):
        o.append(f'<text x="{X(x):.1f}" y="{H - B + 18}" text-anchor="middle" fill="{muted}">{x}</text>')
    o.append(f'<text x="{(L + W - R) / 2}" y="{H - 10}" text-anchor="middle" fill="{ink2}">experiment</text>')
    best, pts = None, []
    for r, x, y in zip(rs, xs, ys):
        if r["kept"] in ("baseline", "yes"):
            if best is not None:
                pts.append((x, best))
            best = y
            pts.append((x, best))
    pts.append((xmax, best))
    o.append(f'<polyline fill="none" stroke="{blue}" stroke-width="2" points="'
             + " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts) + '"/>')
    for r, x, y in zip(rs, xs, ys):
        kept = r["kept"] in ("baseline", "yes")
        fill = blue if kept else surf
        stroke = surf if kept else muted
        o.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="5" fill="{fill}" stroke="{stroke}" stroke-width="2">'
                 f'<title>#{r["n"]} {r["kept"]}: {y:.1f} {unit} - {r["idea"]}</title></circle>')
    lx = L
    o.append(f'<circle cx="{lx}" cy="40" r="5" fill="{blue}"/><text x="{lx + 10}" y="44" fill="{ink2}">kept (line: best so far)</text>')
    o.append(f'<circle cx="{lx + 160}" cy="40" r="5" fill="{surf}" stroke="{muted}" stroke-width="2"/>'
             f'<text x="{lx + 170}" y="44" fill="{ink2}">reverted</text>')
    o.append("</svg>")
    out = os.path.join(cfg["dir"], "curve.svg")
    with open(out, "w") as f:
        f.write("\n".join(o) + "\n")
    print(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-c", "--config", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("baseline")
    b.add_argument("--runs", type=int)
    b.add_argument("--idea")
    t = sub.add_parser("try")
    t.add_argument("--idea", required=True)
    sub.add_parser("status")
    sub.add_parser("plot")
    a = ap.parse_args()
    cfg = load(a.config)
    dict(baseline=cmd_baseline, try_=cmd_try, status=cmd_status, plot=cmd_plot)[a.cmd.replace("try", "try_")](cfg, a)


if __name__ == "__main__":
    main()
