#!/bin/sh
set -eu
# No flags, shell expansion of credentials, environment approval or implicit SQL.
[ "$#" -eq 0 ] || exit 64
exec /usr/local/libexec/space-g1-pg17-bootstrap-native
