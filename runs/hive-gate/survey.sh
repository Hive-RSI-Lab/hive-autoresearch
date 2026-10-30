#!/bin/sh
# Measure write_bytes of every package's -short test binary once.
cd /hive/home/ar/target
out=/hive/home/ar/survey.tsv
touch $out
for d in $(GOTOOLCHAIN=local go list -f '{{if or .TestGoFiles .XTestGoFiles}}{{.Dir}}{{end}}' ./...); do
  rel=${d#/hive/home/ar/target/}; [ "$rel" = "$d" ] && rel=.
  grep -q "^$rel	" $out && continue
  name=$(echo $rel | tr / _)
  bin=/hive/home/ar/tmp/$name.test
  GOTOOLCHAIN=local go test -c -o $bin ./$rel >/dev/null 2>&1 || { echo "$rel	build-failed" >> $out; continue; }
  res=$(timeout 2700 nice -n 10 python3 /work/metrics/proc_io.py --field write_bytes --cwd $d --tmpdir /hive/home/ar/tmp -- $bin -test.short -test.count=1 -test.timeout=2400s; echo "rc=$?")
  echo "$rel	$(echo "$res" | tr '\n' ' ')" >> $out
  rm -f $bin
done
echo done >> $out
