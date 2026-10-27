#!/bin/sh
set -eu
[ "$#" -eq 0 ] || exit 64
# One explicitly budgeted call; socket readiness is NOT authenticated Owner readiness.
exec /usr/lib/postgresql/17/bin/pg_isready -q -h /run/postgresql -p 5432
