# hive-autoresearch

A module for tight, autonomous optimisation loops (after Karpathy's autoresearch): one agent edits code against a single measured metric, runs short fixed-budget experiments, keeps what improves it, reverts what doesn't, and logs every try.

## The loop

`autoresearch/loop.py` (Python 3, stdlib only):

- `loop.py baseline --repo R --metric CMD --log runs/<name>/results.tsv` measures the unchanged repo and writes the log's first row.
- After each edit, `loop.py step --repo R --metric CMD --test CMD --idea "..." --log ...` commits the change, runs the tests, measures the metric (`--repeats`, default 3; the metric's last output line ends in the number), keeps the commit only if the tests pass and it beats the best kept by more than the noise (the spread of the repeats, the larger of the two), and otherwise resets the repo to the best. Every try is a row: `commit metric noise kept idea`, `kept` being `baseline`, `yes` or `no`. The log must live outside the target repo (`step` refuses one inside it), since a revert resets that repo.

## Score and tests

`python3 autoresearch/score.py` prints the best kept % reduction of the metric against its baseline in the newest `runs/*/results.tsv` (newest by last commit), 0 with no run yet. It counts reduction only: a run with `--direction higher` scores 0. Commit a run's log under `runs/<name>/` for it to count. `python3 -m unittest discover -s tests` tests the loop on a fake metric.
