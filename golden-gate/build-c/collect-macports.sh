#!/bin/sh
set -eu
umask 077

# Evidence-only MacPorts inventory for experimental Golden Gate C.
# No sudo, installs, updates, mounting, EFI, snapshots or System writes.
# Run after an active install batch, then redact the local report before sharing.
if [ "$#" -gt 0 ]; then
    report=$1
else
    stamp=$(/bin/date -u +%Y%m%dT%H%M%SZ)
    report="$HOME/Desktop/GoldenGate-C-MacPorts-Evidence-$stamp.txt"
fi
case "$report" in
    /*) ;;
    *) echo "Give an absolute report path." >&2; exit 2 ;;
esac
if [ -e "$report" ] || [ -L "$report" ]; then
    echo "Refusing to replace an existing report." >&2
    exit 2
fi

model=$(/usr/sbin/sysctl -n hw.model)
build=$(/usr/bin/sw_vers -buildVersion)
if [ "$model" != MacBookPro9,1 ] || [ "$build" != 26B131 ]; then
    echo "Refusing: not the tested Golden Gate C model and build." >&2
    exit 2
fi

(
    echo "Golden Gate C — read-only MacPorts inventory"
    /bin/date -u +%Y-%m-%dT%H:%M:%SZ
    echo "Hardware: $model"
    /usr/bin/sw_vers
    echo
    echo "Booted snapshot:"
    /usr/sbin/diskutil info / | /usr/bin/grep -E 'APFS Snapshot Name|APFS Snapshot UUID' || :
    echo
    echo "Apple toolchain:"
    /usr/bin/xcrun --sdk macosx --show-sdk-version || :
    /usr/bin/clang -print-target-triple || :
    echo
    echo "Python:"
    if [ -x /usr/local/bin/python3 ]; then
        /usr/local/bin/python3 -I -B -c 'import platform,sys; print(platform.machine(),sys.version.split()[0])' || :
    fi
    echo
    echo "MacPorts:"
    if [ -x /opt/local/bin/port ]; then
        /opt/local/bin/port version || :
        echo
        echo "ALL INSTALLED (active and inactive):"
        /opt/local/bin/port installed || :
        echo
        echo "REQUESTED (if registered):"
        /opt/local/bin/port echo requested || :
        echo
        echo "ACTIVE:"
        /opt/local/bin/port installed active || :
    else
        echo "MacPorts executable missing."
    fi
    echo
    echo "Review paths, installed programs and any personal data before publishing."
) > "$report" 2>&1
printf 'Local report created: %s\n' "$report"
