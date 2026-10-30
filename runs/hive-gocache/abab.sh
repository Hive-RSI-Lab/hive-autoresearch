#!/bin/sh
# Baseline and final commits of internal/gocache's tests, interleaved, CPU ms each.
T=/hive/home/ar3/target; out=/work/runs/hive-gocache/logs/abab.tsv
F=$(git -C $T rev-parse --short autoresearch/gocache-test-cpu)
echo "commit	round	cpu_ms	wall_s" > $out
for c in de0d3b6f $F; do
  rm -rf /hive/home/ar3/wt_$c; git -C $T worktree add -f -q --detach /hive/home/ar3/wt_$c $c
  (cd /hive/home/ar3/wt_$c && GOTOOLCHAIN=local go test -c -o /hive/home/ar3/tmp/ab_$c.test ./internal/gocache)
done
for i in 1 2 3; do for c in de0d3b6f $F; do
  r=$(nice -n 10 python3 /work/metrics/proc_io.py --field cpu_ms --cwd /hive/home/ar3/wt_$c/internal/gocache --tmpdir /hive/home/ar3/tmp -- /hive/home/ar3/tmp/ab_$c.test -test.short -test.count=1; echo "rc=$?")
  echo "$c	$i	$(echo "$r" | grep -v rc= | tail -1)	$(echo "$r" | grep ^wall_s= | cut -d= -f2)	$(echo "$r" | grep rc=)" >> $out
done; done
echo done >> $out
