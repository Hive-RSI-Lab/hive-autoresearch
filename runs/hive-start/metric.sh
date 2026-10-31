#!/bin/sh
# CPU ms of app.New on a restart of a workspace holding the first 300 MB of the
# Hive's journal (internal/app/startmeasure_test.go on the loop's branch),
# normalised for the machine's load: the candidate (app.test) and a reference
# built from the untouched baseline (ref.test) run alternately, twice each,
# and the number is REF_MS x candidate/reference, REF_MS being the baseline's
# CPU on a quieter machine. Raw CPU drifted 15% with load here (load 40 -> 87),
# the ratio far less. The workspace is on tmpfs, so a run writes nothing to disk.
set -e
REF_MS=12996
one() {
	out=$(cd internal/app && HIVE_START_JOURNAL=/dev/shm/ev.part HIVE_START_WS=/dev/shm/ws \
		"$1" -test.run '^TestStartMeasure$' -test.count=1)
	echo "$out" | grep -q '^PASS$'
	echo "$out" | tr '\n' ' '
}
r1=$(one "$HOME/ar4/tmp/ref.test"); c1=$(one "$HOME/ar4/tmp/app.test")
r2=$(one "$HOME/ar4/tmp/ref.test"); c2=$(one "$HOME/ar4/tmp/app.test")
python3 - "$REF_MS" "$r1" "$c1" "$r2" "$c2" <<'PY'
import sys
ref_ms = int(sys.argv[1])
runs = [dict(kv.split("=") for kv in s.split() if "=" in kv) for s in sys.argv[2:]]
ref = [int(r["cpu_ms"]) for r in runs[0::2]]
cand = [int(r["cpu_ms"]) for r in runs[1::2]]
ratio = sum(c / r for c, r in zip(cand, ref)) / len(ref)
print(f"ref_cpu_ms={sum(ref) // len(ref)}")
print(f"cpu_ms={sum(cand) // len(cand)}")
print(f"alloc_mb={runs[1]['alloc_mb']}")
print(f"mallocs_k={runs[1]['mallocs_k']}")
print(round(ref_ms * ratio))
PY
