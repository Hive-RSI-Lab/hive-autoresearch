# program.md: one autoresearch loop

After [karpathy/autoresearch](https://github.com/karpathy/autoresearch): one agent
edits code against one measured number, runs short fixed-budget experiments,
keeps what beats the best, reverts what doesn't and logs every try. You are that
agent. `loop.py` does the measuring and the bookkeeping; you have the ideas.

## Setup (once per loop)

1. Write `runs/<name>/config.json`:
   - `target`: a clone of the repo you optimise; `branch`: the loop's branch there.
   - `editable`: globs of the files you may change (relative to `target`). Nothing
     else is changed, and `loop.py try` refuses a tree that does.
   - `prepare` (build) and `check` (vet, a quick test): shell commands run in
     `target` before every measurement; a failure counts as a crash.
   - `metric`: a command that prints one number on its last stdout line
     (`key=value` lines before it are logged) and exits non-zero when the tests
     fail. Prefer counts over wall time on a shared machine: bytes written
     (`metrics/proc_io.py`), syscalls, allocations. They hold still under load.
   - `direction` (`min`|`max`), `budget_s` (per measurement; over it is a
     crash), `max_experiments` (the cap: say it before you start),
     `baseline_runs`, `max_runs`, `min_gain` (the smallest gain worth keeping).
2. `python3 loop.py -c runs/<name>/config.json baseline`: makes the branch,
   measures the untouched target `baseline_runs` times and sets the noise (the
   spread of those runs). The margin to beat is `max(min_gain, 3 x noise)`.

## The loop

Repeat until `max_experiments` is spent or you run out of ideas worth a run:

1. Look at where the metric comes from (profile, trace, read the code) and pick
   the one change you think buys the most. One idea per try, so the log says what
   each was worth.
2. Edit only the editable files.
3. `python3 loop.py -c runs/<name>/config.json try --idea "one line: what and why"`.
   It builds, checks, runs the metric once, and stops there if that run isn't
   better than the best at all; otherwise it runs again (up to `max_runs`) and
   keeps the change, as a commit on the branch, only if the median beats the best
   by more than the margin with every run green. Anything else is reverted.
   Every try, kept or not, is a row in `results.tsv` and its diff is in
   `patches/NNN.patch`.
4. Read the row. A crash is a bug in your change (or a flake: say so in the next
   idea if you retry it). Two tries in a row that don't move the number mean the
   approach is wrong: step outside it.

Run one experiment at a time, niced (loop.py nices every command), so the loop
stays light on a shared machine. Don't edit `results.tsv` by hand.

## The end

`python3 loop.py -c runs/<name>/config.json plot` writes `curve.svg` (best so far
against the experiment number, every try a dot). The kept commits on the
branch are the pull request; `results.tsv` and the curve go with it.
