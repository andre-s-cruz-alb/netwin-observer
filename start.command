#!/bin/sh
set -eu
cd "$(dirname "$0")"
socket_dir="/tmp/nwo-$(id -u)"

cleanup() {
  if [ -d "$socket_dir" ]; then
    printf '\nEncerrando conexões SSH persistentes...\n'
    for sock in "$socket_dir"/*; do
      [ -S "$sock" ] || continue
      ssh -O exit -S "$sock" x 2>/dev/null || true
    done
  fi
}
trap cleanup EXIT

python3 server.py "$@"
