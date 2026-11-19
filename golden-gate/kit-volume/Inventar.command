#!/bin/sh
set -eu
kit_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/osascript -l JavaScript - "$@" < "$kit_dir/inventar.js"
