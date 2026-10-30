#!/bin/sh
T=/hive/home/ar3/target; out=/hive/home/ar3/survey.tsv
for rel in "$@"; do
  name=$(echo $rel | tr / _); bin=/hive/home/ar3/tmp/$name.test
  cd $T && GOTOOLCHAIN=local go test -c -o $bin ./$rel >/dev/null 2>&1 || { echo "$rel	build-failed" >> $out; continue; }
  res=$(timeout 2700 nice -n 10 python3 /work/metrics/proc_io.py --field cpu_s --cwd $T/$rel --tmpdir /hive/home/ar3/tmp -- $bin -test.short -test.count=1 -test.timeout=2400s; echo "rc=$?")
  echo "$rel	$(echo "$res" | tr '\n' ' ')" >> $out
  rm -f $bin
done
