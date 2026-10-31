#!/bin/bash
# The probe's answer times (ms): key=value lines, then the median.
set -o pipefail
cd "$1/internal/core" && HIVE_ANSWER_PROBE=1 "$2" -test.run '^TestAnswerProbe$' -test.count=1 | sed -n 's/^probe: //p'
