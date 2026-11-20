#!/bin/bash
set -eu
folder=$(cd "$(dirname "$0")" && pwd -P)
exec /usr/bin/python3 -I -B "$folder/lowered-run.py" "$@"
