# hive-autoresearch

A module for tight, autonomous optimisation loops (after Karpathy's autoresearch): one agent edits code against a single measured metric, runs short fixed-budget experiments, keeps what improves it, reverts what doesn't, and logs every try.

- `program.md`: what the agent does, loop by loop.
- `loop.py`: measure, keep or revert, log (`baseline`, `try --idea`, `status`, `plot`).
- `metrics/proc_io.py`: bytes a command and its children wrote, from `/proc/self/io`.
- `runs/<name>/`: one loop each: its config, `results.tsv`, every try's patch, the curve.

Loops so far: [`runs/hive-work`](runs/hive-work/README.md), bytes written by `go test -short ./internal/mod/work` in ihsan-sa/hive, 375.7 → 199.2 MB (-47%) in 5 experiments.
