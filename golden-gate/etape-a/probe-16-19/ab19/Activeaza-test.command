#!/bin/sh
set -u
kit_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd) || exit 1
for py in /opt/local/bin/python3 /usr/local/bin/python3 /usr/bin/python3; do
  if [ -x "$py" ] && "$py" -I -B -c 'import sys;sys.exit(sys.version_info < (3,9))' 2>/dev/null; then
    exec /usr/bin/sudo -- "$py" -I -B "$kit_dir/ab.py" enable
  fi
done
printf '%s\n' 'Acest pachet folosește Python 3.9 sau mai nou, ca scripturile anterioare.' >&2
exit 1
