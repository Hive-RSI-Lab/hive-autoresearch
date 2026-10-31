#!/bin/sh
# go test -exec wrapper: CPU of each test binary and its reaped children.
exec /usr/bin/time -a -o "$SURVEY_OUT" -f "$(pwd | sed "s#.*/target/##")	%e	%U	%S	%x" "$@"
