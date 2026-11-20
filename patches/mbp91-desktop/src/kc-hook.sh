#!/bin/sh
# Install the per-user IconServices agent at its launch plist's existing path.
set -eu
system=${1:?offline Golden System mount}
hook=$(cd "$(dirname "$0")" && pwd)
input="$hook/inputs/mbp91_desktop/root"
agent=System/Library/CoreServices/iconservicesagent
unit=usr/lib/hao/if/21acabfab6cc3ec9a3cf6d4d6b637f5a
source_agent="$input/$agent"
source_unit="$input/$unit"
dest_agent="$system/$agent"
dest_unit="$system/$unit"
fail() { echo "mbp91-desktop: $*" >&2; exit 1; }
digest() { shasum -a 256 "$1" | awk '{print $1}'; }
test -n "$system" && test "$(cd "$system" && pwd -P)" != / || fail "expected offline System"
test "$(plutil -extract ProductBuildVersion raw -o - "$system/System/Library/CoreServices/SystemVersion.plist")" = 26B131 || fail "wrong System build"
for p in System System/Library System/Library/CoreServices usr usr/lib usr/lib/hao usr/lib/hao/if "$agent" "$unit"; do
    test ! -L "$system/$p" || fail "unexpected symlink: $p"
done
test -f "$dest_agent" && test -d "$system/usr/lib/hao" || fail "install after hao-runtime"
codesign --verify --strict --architecture x86_64 -R '=anchor apple and identifier "com.apple.iconservicesagent"' "$source_agent"
test "$(digest "$source_agent")" = 0c34b609f914b0f1e1e263268528e04715ce59d4de34770cba3af1d40d752de8 || fail "unexpected Tahoe agent"
test "$(digest "$source_unit")" = cd2a77b0e61af60abd4c23e860809aad0af4837dc81886a600831379c2546b3f || fail "unexpected cumulative SkyLight unit"
if test -e "$dest_unit"; then
    cmp -s "$source_unit" "$dest_unit" ||
        test "$(digest "$dest_unit")" = a0bb9d28b8c3b030cbebd2b995d4470269e7c3955ff208b2f7fc5a1ded520a1f ||
        fail "SkyLight already has different interface records"
fi
if ! cmp -s "$source_agent" "$dest_agent"; then
    test "$(digest "$dest_agent")" = cf1e92d68dcc75d290ad6ea693d04fc0d7a96d5b4be8d1ded6228751fa55bf82 || fail "unexpected base IconServices agent"
    install -S -o root -g wheel -m 0755 -f restricted "$source_agent" "$dest_agent"
fi
if test ! -d "$system/usr/lib/hao/if"; then
    install -d -o root -g wheel -m 0755 "$system/usr/lib/hao/if"
fi
install -S -o root -g wheel -m 0644 "$source_unit" "$dest_unit"
cmp -s "$source_agent" "$dest_agent" && cmp -s "$source_unit" "$dest_unit"
