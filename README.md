# hive-autoresearch

A module for tight, autonomous optimisation loops (after Karpathy's autoresearch): one agent edits code against a single measured metric, runs short fixed-budget experiments, keeps what improves it, reverts what doesn't, and logs every try.

- `program.md`: what the agent does, loop by loop.
- `loop.py` (repo root, the loop that ran `runs/hive-work`): measure, keep or revert, log (`baseline`, `try --idea`, `status`, `plot`).
- `metrics/proc_io.py`: bytes a command and its children wrote, from `/proc/self/io`.
- `metrics/laid_out.py`: bytes a command laid out in files, counted under strace (each file's final size, else what was written to it). Use it where the writes are mmapped, as a linker's are: there `/proc/self/io`'s write_bytes swings with the machine's writeback (runs/hive-gate).
- `runs/<name>/`: one loop each: its config, `results.tsv`, every try's patch, the curve.

Loops so far: [`runs/hive-work`](runs/hive-work/README.md), bytes written by `go test -short ./internal/mod/work` in ihsan-sa/hive, 375.7 → 199.2 MB (-47%) in 5 experiments.

## The loop

`autoresearch/loop.py` (Python 3, stdlib only):

- `loop.py baseline --repo R --metric CMD --log runs/<name>/results.tsv` measures the unchanged repo and writes the log's first row.
- After each edit, `loop.py step --repo R --metric CMD --test CMD --idea "..." --log ...` commits the change, runs the tests, measures the metric (`--repeats`, default 3; the metric's last output line ends in the number), keeps the commit only if the tests pass and it beats the best kept by more than the noise (the spread of the repeats, the larger of the two), and otherwise resets the repo to the best. Every try is a row: `commit metric noise kept idea`, `kept` being `baseline`, `yes` or `no`. The log must live outside the target repo (`step` refuses one inside it), since a revert resets that repo.

## Score and tests

`python3 autoresearch/score.py` prints each run's best kept % gain over its baseline, then their sum (the score); 0 with no run yet. A run is a `runs/<name>/` holding its `results.tsv` and the `config.json` it ran from (target, metric command, `direction` `min` or `max`, min by default); one without `config.json` is listed as not counted. A run counts only once its gain is on the target's main: `runs/<name>/landed.json` names the target project and the commit on its main carrying the kept change (`{"project": "hive", "commit": "2a17147b…", "still": [[path, text], …]}`), and the score checks in the target's clone under `$HIVE_PROJECTS` that the commit is on main, every file it left is still there, and each `still` text is still in its file. So a gain that never reached the target, or that the target since deleted, counts 0 (runs/hive-gate: internal/gate was deleted from hive at 88b00fa6 before its change could land). Columns are read by name (`metric`, `kept`), so any loop's log works. Summing means a new target, which starts at its baseline, adds 0 rather than lowering the score. The score reads only `score.py` (its protected path), nothing from the loop. Since the score comes from logs the work commits itself, commit a run's evidence beside its log: the config, the kept patches and a README with the commands and metric outputs, so a reviewer can check it came from a real run. `python3 -m unittest discover -s tests` tests the loop on a fake metric.
