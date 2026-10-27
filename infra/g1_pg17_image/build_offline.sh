#!/bin/sh
set -eu
# Static plan ONLY. Actual image build is a separate explicitly authorized activity.
[ "$#" -eq 2 ] || exit 64
exec python -m scripts.a42364_bootstrap_builder --plan "$1" "$2"
