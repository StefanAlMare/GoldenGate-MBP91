#!/bin/bash
# Observe the logged-in user's Finder without opening a window or sending it Apple events.
finder_reference_cache() {
    local base
    base=$(/usr/bin/getconf DARWIN_USER_CACHE_DIR 2>/dev/null) || base=
    /usr/bin/perl -MFcntl=:mode -e '
        use strict; use warnings;
        sub metadata {
            my ($label,$path) = @_;
            my @s = lstat($path);
            unless (@s) {
                my $why = $!{ENOENT} ? "absent" : "inaccesibil";
                print "$label | $why\n"; return;
            }
            my $type = S_ISREG($s[2]) ? "fișier" : S_ISDIR($s[2]) ? "director" : "alt tip";
            printf "%s | %s | uid=%d mod=%04o | mtime=%d", $label, $type, $s[4], $s[2]&07777, $s[9];
            print " | octeți=$s[7]" if S_ISREG($s[2]);
            print "\n";
        }
        my $base = shift;
        if ($base =~ m{^/(?:private/)?var/folders/} && $base !~ m{/\.\.(?:/|$)}) {
            $base =~ s{/$}{};
            metadata("Index IconServices utilizator","$base/com.apple.iconservices/store.index");
            metadata("Metadate cache utilizator","$base/com.apple.iconservices/__cache_info__");
        } else {
            print "Cache utilizator | cale indisponibilă\n";
        }
        metadata("Depozit comun IconServices","/Library/Caches/com.apple.iconservices.store");
        metadata("Metadate depozit comun","/Library/Caches/com.apple.iconservices.store/store-info.plist");
    ' "$base"
}

finder_reference_stack() {
    /usr/bin/perl -e '
        use strict; use warnings;
        my ($graph,$main,$done,$total,$deep,$count,$result,$guest,@path);
        while (<STDIN>) {
            if (/^Call graph:/) { $graph=1; next }
            next unless $graph && !$done;
            if (/^(?:Total number in stack|Sort by top of stack|Binary Images:)/) { $done=1; next }
            if (/^\s*(\d+) Thread_\S+(.*)/) {
                my ($samples,$queue)=($1,$2);
                $main = $queue =~ /com\.apple\.main-thread|\bMain Thread\b/i;
                if ($main) { $total=$samples; @path=() }
                next;
            }
            next unless $main && /^([\s+:|!]*)(\d+)\s+(.+?)\s{2,}\(in ([\w.+-]+)\)/;
            my ($d,$n,$symbol,$lib) = (length($1),$2,$3,$4);
            pop @path while @path && $path[-1][0] >= $d;
            $symbol = substr($symbol,0,95);
            push @path, [$d,"$symbol [$lib]"];
            next unless $n*2 > $total && (!defined($deep) || $d > $deep);
            ($deep,$count)=($d,$n);
            my $lo = @path > 5 ? @path-5 : 0;
            $result = join(" → ",map { $_->[1] } @path[$lo..$#path]);
            $guest="";
            if (!grep { $_->[1] !~ /\[libhao\.dylib\]$/ } @path[$lo..$#path]) {
                my ($last) = grep { $_->[1] !~ /\[libhao\.dylib\]$/ } reverse @path;
                $guest=$last ? " | ultimul cadru înainte de HAO: ".$last->[1] : "";
            }
        }
        unless ($done && $total && defined($result)) { exit 3 }
        print "Fir principal Finder | $count/$total observații | $result$guest\n";
    '
}

finder_reference() {
    local uid pid
    local -a rc
    uid=$(/usr/bin/id -u)
    pid=$(/usr/bin/pgrep -u "$uid" -x Finder 2>/dev/null)
    if [[ $pid =~ ^[0-9]+$ ]]; then
        printf 'Finder | PID=%s | început captură %s\n' "$pid" "$(/bin/date '+%Y-%m-%d %H:%M:%S%z')"
        /usr/bin/perl -e 'alarm 15; exec @ARGV or die $!' /usr/bin/sample "$pid" 2 15 -file /dev/stdout 2>/dev/null | finder_reference_stack
        rc=("${PIPESTATUS[@]}")
        if ((rc[0] || rc[1])); then
            printf 'Fir principal Finder | captură incompletă (sample=%d decodor=%d)\n' "${rc[0]}" "${rc[1]}"
        fi
        printf 'Finder | sfârșit captură %s\n' "$(/bin/date '+%Y-%m-%d %H:%M:%S%z')"
        /usr/bin/perl -e 'alarm 8; exec @ARGV or die $!' /usr/bin/osascript -l JavaScript -e '
            ObjC.import("CoreGraphics");
            function run(argv) {
                const list = ObjC.deepUnwrap($.CGWindowListCopyWindowInfo(17,0));
                if (!Array.isArray(list) || list.length === 0) return "Ferestre Finder | inventar indisponibil";
                const n = list.filter(w => Number(w.kCGWindowOwnerPID) === Number(argv[0]) && Number(w.kCGWindowLayer) === 0).length;
                return "Ferestre Finder | vizibile pe stratul normal=" + n;
            }' "$pid" 2>/dev/null || echo 'Ferestre Finder | inventar indisponibil'
    else
        echo 'Finder | PID unic indisponibil pentru utilizatorul curent'
    fi
}

if [[ ${BASH_SOURCE[0]:-} == "$0" || -z ${BASH_SOURCE[0]:-} ]]; then
    case ${1:-} in
        '') finder_reference; finder_reference_cache ;;
        --cache) finder_reference_cache ;;
        *) exit 2 ;;
    esac
fi
