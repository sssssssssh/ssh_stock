#!/bin/sh
set -eu
[ "$#" -eq 1 ] || exit 64
# Reads an offline directory of public artifacts; no network or signer/private key.
exec python -m scripts.a42364_bootstrap_builder --verify "$1"
