# Summarize the call graph only. Window titles, queue labels, file paths,
# addresses and the process environment are not copied to the report.
gg_dock_sample_summary() {
    /usr/bin/perl -e '
        use strict; use warnings;
        my ($graph,$done,$seen,$serial,$total,$thread,%best,@path);
        while (<STDIN>) {
            if (/^Call graph:/) { $graph=1; next }
            next unless $graph && !$done;
            if (/^(?:Total number in stack|Sort by top of stack|Binary Images:)/) { $done=1; next }
            if (/^\s*(\d+) Thread_\S+(.*)/) {
                ++$serial; $total=$1; my $info=$2;
                $thread=$info =~ /main-thread|main thread/i ? "main" :
                        $info =~ /animat|displaylink|render.?loop/i ? "animation" : "thread".$serial;
                @path=(); next;
            }
            next unless $total && /^([\s+|!:]*)(\d+)\s+(.+?)\s{2,}\(in ([\w.+-]+)\)/;
            my ($depth,$n,$sym,$lib)=(length($1),$2,$3,$4); ++$seen;
            pop @path while @path && $path[-1][0] >= $depth;
            my $safe = $lib =~ /^(?:Dock|SkyLight|CoreGraphics|HIToolbox|AppKit|QuartzCore|CoreAnimation|CoreFoundation|Foundation|SwiftUI(?:Core)?|libhao(?:_identity)?\.dylib|libxpc\.dylib|libdyld\.dylib|dyld|libdispatch\.dylib|libswiftCore\.dylib|libsystem_(?:kernel|pthread|platform)\.dylib)$/;
            my $frame="…";
            if ($safe) {
                my $label=$sym;
                $label =~ s/\s*\(.*$//; $label =~ s/<.*$//;
                $label="?" if $label =~ /[^A-Za-z0-9_:\$+\-\[\]\.\s~]/ || !length($label);
                $frame=$lib.":".substr($label,0,72);
            }
            push @path,[$depth,$frame];
            my @families;
            push @families,"main" if $thread eq "main";
            push @families,"animation" if $thread eq "animation" || $safe && $sym =~ /magnif|animat|displaylink/i;
            push @families,"tracking" if $safe && $sym =~ /mouse|tracking|cursor|autohide|hitTest/i;
            push @families,"eventloop" if $safe && $sym =~ /nextEvent|sendEvent/i;
            push @families,"SkyLight" if $lib eq "SkyLight";
            push @families,"XPC" if $lib eq "libxpc.dylib" || $safe && $sym =~ /xpc_connection_/;
            push @families,"HAO" if $lib =~ /^libhao/;
            push @families,"lookup" if $safe && $sym =~ /dlsym|witness|common_byte_optional_case|exportTrie/i;
            for my $family (@families) {
                my $old=$best{$family};
                # The thread entry is normally 100% but tells little about its
                # work. Follow the deepest majority path for a named thread.
                if ($family eq "main" || ($family eq "animation" && $thread eq "animation")) {
                    next if $n*2 <= $total;
                    next if $old && $old->[1] >= $depth;
                } else {
                    next if $old && ($n<$old->[0] || ($n==$old->[0] && $depth<=$old->[1]));
                }
                my $lo=@path>3 ? @path-3 : 0;
                $best{$family}=[$n,$depth,$thread,$total,join(" > ",map {$_->[1]} @path[$lo..$#path])];
            }
        }
        unless ($done && $seen && $best{main}) {
            print "GG_DOCK_STACK Graful sau firul principal nu a putut fi citit integral.\n"; exit 3;
        }
        for my $family (qw(main animation tracking eventloop SkyLight XPC HAO lookup)) {
            next unless my $r=$best{$family};
            printf "GG_DOCK_STACK %s | %s | %d/%d | %s\n",$family,$r->[2],$r->[0],$r->[3],$r->[4];
        }
    '
}

gg_sample_dock() (
    local pid=${1:-} owner job start end
    local -a status
    owner=$(/usr/bin/id -u)
    [[ $owner == 501 && $owner == "$(/usr/bin/stat -f %u /dev/console)" && $pid =~ ^[1-9][0-9]*$ ]] || {
        echo 'GG_DOCK_STACK Sesiunea sau PID-ul Dock nu este confirmat.'; return 3;
    }
    job="gui/$owner/com.apple.Dock.agent"
    gg_sample_job_pid() {
        /bin/launchctl print "$job" 2>/dev/null | /usr/bin/awk '
            $1 == "program" && $2 == "=" && $3 == "/System/Library/CoreServices/Dock.app/Contents/MacOS/Dock" {apple=1}
            $1 == "pid" && $2 == "=" {pid=$3}
            END {if (apple && pid) print pid}'
    }
    [[ $pid == "$(gg_sample_job_pid)" ]] || { echo 'GG_DOCK_STACK PID-ul Dock s-a schimbat.'; return 3; }
    start=$(/bin/date '+%H:%M:%S')
    echo "GG_DOCK_STACK Început $start. PID $pid, 8 s la interval de 20 ms."
    /usr/bin/perl -e 'alarm 22; exec @ARGV or die $!' /usr/bin/sample "$pid" 8 20 -file /dev/stdout 2>/dev/null |
        gg_dock_sample_summary
    status=("${PIPESTATUS[@]}")
    end=$(/bin/date '+%H:%M:%S')
    if ((status[0] || status[1])) || [[ $pid != "$(gg_sample_job_pid)" ]]; then
        echo "GG_DOCK_STACK Captură neconfirmată: sample=${status[0]} decodor=${status[1]} final=$end."; return 3
    fi
    echo "GG_DOCK_STACK Final $end. Proporțiile se referă la firul indicat și se pot suprapune."
)
