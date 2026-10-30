# hive-autoresearch

A module for tight, autonomous optimisation loops (after Karpathy's autoresearch): one agent edits code against a single measured metric, runs short fixed-budget experiments, keeps what improves it, reverts what doesn't, and logs every try.

- `program.md`: what the agent does, loop by loop.
- `loop.py` (repo root, the loop both `runs/` ran from): measure, keep or revert, log (`baseline`, `try --idea`, `status`, `plot`).
- `metrics/proc_io.py`: bytes a command and its children wrote, from `/proc/self/io`.
- `metrics/laid_out.py`: bytes a command laid out in files, counted under strace (each file's final size, else what was written to it). Use it where the writes are mmapped, as a linker's are: there `/proc/self/io`'s write_bytes swings with the machine's writeback (runs/hive-gate).
- `runs/<name>/`: one loop each: its config, `results.tsv`, every try's patch, the curve.

Loops so far: [`runs/hive-work`](runs/hive-work/README.md), bytes written by `go test -short ./internal/mod/work` in ihsan-sa/hive, 375.7 → 199.2 MB (-47%) in 5 experiments.

## The loop

`loop.py` (repo root, Python 3, stdlib only; the one both runs used), driven by a run's `config.json` (see `program.md` for its keys):

- `loop.py -c runs/<name>/config.json baseline` makes the loop's branch in the target, measures the untouched target `baseline_runs` times and sets the noise (the runs' spread). The margin to beat is `max(min_gain, 3 x noise)`.
- After each edit, `loop.py -c ... try --idea "..."` refuses a change outside the `editable` globs, saves the diff as `patches/NNN.patch`, runs `prepare` and `check`, then the metric (its last stdout line is the number, `key=value` lines before it are logged, non-zero exit or over `budget_s` is a crash). It stops after one run that isn't better at all, otherwise runs up to `max_runs` and keeps the change as a commit only if the median beats the best by more than the margin; anything else is reverted, new files included. Every try is a row in `results.tsv` (`n time commit metric runs wall_s kept idea extra`, `kept` being `baseline`, `yes`, `no` or `crash`), up to `max_experiments`.
- `loop.py -c ... status` prints the best, noise, margin and experiments; `plot` writes `curve.svg`.

## Score and tests

`python3 autoresearch/score.py` prints each run's best kept % gain over its baseline, then their sum (the score); 0 with no run yet. A run is a `runs/<name>/` holding its `results.tsv` and the `config.json` it ran from (target, metric command, `direction` `min` or `max`, min by default); one without `config.json` is listed as not counted. Columns are read by name (`metric`, `kept`), so any loop's log works. Summing means a new target, which starts at its baseline, adds 0 rather than lowering the score. The score reads only `score.py` (its protected path), nothing from the loop. Since the score comes from logs the work commits itself, commit a run's evidence beside its log: the config, the kept patches and a README with the commands and metric outputs, so a reviewer can check it came from a real run. `python3 -m unittest discover -s tests` tests `loop.py` on a fake target and metric.
