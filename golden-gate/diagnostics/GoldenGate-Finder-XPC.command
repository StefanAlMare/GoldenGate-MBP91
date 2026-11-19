#!/bin/bash
# Run on the SSH client. Only the report is written, alongside this script.
set -u
umask 077
destination=${1:-${GOLDEN_GATE_SSH:-}}
if [[ $# -gt 1 || ! $destination =~ ^[[:alnum:]_][[:alnum:]_.-]*@[[:alnum:]][[:alnum:].-]*$ ]]; then
    echo 'Usage: GoldenGate-Finder-XPC.command user@known-host' >&2
    exit 2
fi
cd "$(dirname "$0")" || exit 1
report=$(/usr/bin/mktemp "$PWD/GoldenGate-Finder-XPC-Report.XXXXXXXX") || exit 1
echo "Report on SSH client: $report"
# Authentication uses the client's terminal. Remote stdin carries the script.
/usr/bin/ssh -T -F /dev/null -o StrictHostKeyChecking=yes -o UpdateHostKeys=no \
    -o ClearAllForwardings=yes -o ForwardAgent=no -o ConnectTimeout=10 \
    "$destination" /bin/bash -s <<'REMOTE' | /usr/bin/tee "$report"
set -u
export LC_ALL=C
uid=$(/usr/bin/id -u)
if [[ $(/usr/sbin/sysctl -n hw.model) != MacBookPro9,1 || $(/usr/bin/sw_vers -buildVersion) != 26B131 || $(/usr/bin/stat -f %u /dev/console) != "$uid" ]]; then
    echo 'Stopped: requires MacBookPro9,1 on build 26B131 with the SSH user logged into the desktop.'
    exit 2
fi
echo 'MacBookPro9,1 | 26B131 | SSH user owns the desktop session'
partial=0
check_file() {
    local name=$1 path=$2 expected=$3 sum
    if ! sum=$(/usr/bin/shasum -a 256 "$path" 2>/dev/null); then
        echo "UNREADABLE $name"
        partial=1
        return
    fi
    sum=${sum%% *}
    if [[ $sum == "$expected" ]]; then
        echo "MATCH $name $sum"
    else
        echo "MISMATCH $name actual=$sum expected=$expected"
    fi
}
core=/System/Library/CoreServices
agents=/System/Library/LaunchAgents
daemons=/System/Library/LaunchDaemons
agent=com.apple.iconservices.iconservicesagent
daemon=com.apple.iconservices.iconservicesd
check_file Finder "$core/Finder.app/Contents/MacOS/Finder" a690785915dd1f5ce99e4c3c1a3708b42e13ef613748d8414e47e62a75e64abe
check_file iconservicesagent "$core/iconservicesagent" cf1e92d68dcc75d290ad6ea693d04fc0d7a96d5b4be8d1ded6228751fa55bf82
check_file iconservicesd "$core/iconservicesd" 30e0f70516a572aca2d3a21bd86b75a041c04e734b6a8b51f31b14f03a86ce1b
check_file Finder-launch-agent "$agents/com.apple.Finder.plist" 203128008a22f11f92e4a35e73a20c3e8bc55711cdd8133f8d290f5479a16e15
check_file IconServices-launch-agent "$agents/$agent.plist" d428ea0a01c0ccfd388686f4df4ceb35449d842d3aec37657eaa1c0404fe2d0e
check_file IconServices-system-agent "$daemons/$agent.plist" b6947a97dd8b9cc240e36a45d3739d2463e49220d1f05c7ca06ef53afd4227df
check_file IconServices-store-daemon "$daemons/$daemon.plist" 04a107a2dee70016ec5d49a5abffc84d70e04dba115f5289e4e35216be6bd1b5
if [[ -x /usr/libexec/hao ]]; then
    aot=$(/usr/libexec/hao --aot --check -- "$core/iconservicesd" 2>&1)
    aot_status=$?
    case "$aot" in
        *': valid ('*) aot_kind=valid ;;
        *missing*|*'not found'*) aot_kind=missing ;;
        *invalid*|*stale*) aot_kind='invalid or stale' ;;
        *) aot_kind='undetermined' ;;
    esac
    echo "iconservicesd AOT check: $aot_kind (status=$aot_status)"
else
    echo 'iconservicesd AOT check unavailable'
    partial=1
fi

inspect_job() {
    local label=$1 job=$2 detail reason
    if detail=$(/bin/launchctl print "$job" 2>&1); then
        echo "$label registered"
        printf '%s\n' "$detail" | /usr/bin/awk '
            /^[[:space:]]*(state|pid|runs|last exit code) = / && !seen[$1]++ { print "  " $0 }
            /"com\.apple\.iconservices(\.store)?" =>/ {print "  endpoint " $1}'
    else
        case "$detail" in
            *'Could not find service'*) reason='service not found' ;;
            *'Could not find domain'*) reason='domain not found' ;;
            *'permitted'*|*'privilege'*|*'denied'*) reason='access denied' ;;
            *) reason='launchctl could not inspect this job' ;;
        esac
        echo "$label: $reason"
        partial=1
    fi
}
inspect_job GUI-agent "gui/$uid/$agent"
inspect_job system-agent "system/$agent"
inspect_job system-daemon "system/$daemon"

if ! /usr/bin/perl -MJSON::PP -e 1 2>/dev/null; then
    echo 'Log inspection unavailable: the system NDJSON decoder could not start.'
    exit 3
fi
# Limit the launchd/Finder side to IconServices. The two dedicated services
# can describe a failure without mentioning their own service name.
predicate='(process IN {"iconservicesagent", "iconservicesd"}) OR
 ((process == "Finder" OR process == "launchd") AND
  (subsystem BEGINSWITH[c] "com.apple.iconservices" OR eventMessage CONTAINS[c] "iconservices"))'

# On the target, summarize only published phrases and whitelisted metadata.
# Never include unrestricted messages, paths, signing IDs or peer descriptions.
parser='
use strict;
use warnings;
my (%symptoms, %reason, %formats, $records, $bad, $finished, $opaque, $private);
my @rules = (
    [qr/\b(protocol mismatch|protocol violation|unknown protocol|incompatible protocol|unsupported protocol)\b/i, "protocol"],
    [qr/\b(does not conform to (?:the )?protocol|does not respond to (?:the )?selector|unrecognized selector|unknown selector|interface mismatch|unsupported interface|not allowed (?:by|in) (?:the )?interface)\b/i, "interface"],
    [qr/\b(missing (?:required )?entitlement|entitlement (?:is )?(?:missing|not found)|not entitled|requires (?:an? |the )?entitlement|lacks (?:an? |the )?entitlement)\b/i, "entitlement"],
    [qr/\b(permission denied|access denied|operation not permitted|not authorized|authorization failed|not allowed to connect|not permitted to connect|sandbox[: ]+deny|sandbox violation|deny\(\d+\)\s+mach-lookup)\b/i, "access"],
    [qr/\b(code sign(?:ature|ing) (?:check |validation )?failed|invalid (?:code )?signature|signature validation failed|code requirement (?:failed|not satisfied))\b/i, "validation"],
    [qr/\b(service (?:not found|unavailable)|no such (?:service|process)|could not find service|unknown service|bootstrap_look_up|lookup failed|endpoint (?:not found|unavailable))\b/i, "availability"],
    [qr/\b(connection (?:to service )?(?:was |is )?(?:invalidated|interrupted)|connection invalid|broken pipe|connection reset by peer|connection timed out)\b/i, "connection"],
    [qr/\b(terminated (?:by|due to) signal|exited due to signal|uncaught exception|segmentation fault|crash(?:ed|ing)|spawn failed|failed to spawn|service exited)\b/i, "lifecycle"],
    [qr/\b(failed to decode|decoding failed|invalid archive|could not unarchive|secure coding|not in the allowed classes|unexpected class)\b/i, "decode"]
);
while (<STDIN>) {
    next if /^\s*$/;
    my $e = eval { decode_json($_) };
    if (ref($e) ne "HASH") { ++$bad; next }
    if (exists $e->{finished}) { $finished=1; next }
    my $msg=$e->{eventMessage} // "";
    my $proc=$e->{processImagePath} // $e->{process} // "";
    $proc =~ s{.*/}{};
    next unless $proc =~ /^(Finder|iconservicesagent|iconservicesd|launchd)$/;
    ++$records;
    ++$private if $msg =~ /<private>/;
    my $pid=$e->{processID} // "";
    my $sender=$e->{senderImagePath} // "";
    $sender =~ s{.*/}{};
    $sender="other" unless $sender =~ /^(Finder|iconservicesagent|iconservicesd|launchd|libxpc\.dylib|libsystem_[a-z]+\.dylib|IconServices(?:Agent|Store)?|Foundation|CoreFoundation|AppKit|LaunchServices|Security|libdispatch\.dylib)$/;
    my $time=$e->{timestamp} // "";
    $time="time unavailable" unless $time =~ /^[0-9T :+.\-]+$/ && length($time) <= 36;
    my $who=$proc . ($pid =~ /^\d{1,9}$/ ? "[$pid]" : "") . "/$sender";
    my @marks;
    my $bucket=$msg =~ /rejected by the listener/i ? "listener rejected peer"
        : $msg =~ /failed to generate image/i ? "failed to generate image"
        : $msg =~ /failed to open store index/i ? "failed to open store index" : "";
    if ($bucket) { push @marks, ["symptom", $bucket] }
    for my $r (@rules) {
        if ($msg =~ $r->[0]) { push @marks, ["detail", "$r->[1]: " . lc($1)] }
    }
    my @codes = $msg =~ /\b((?:NSCocoaErrorDomain|NSPOSIXErrorDomain|NSOSStatusErrorDomain)\s+Code=-?\d{1,9}|errno[:= ]+\d{1,3})\b/ig;
    if (!@marks && @codes) { push @marks, ["detail", "published error code"] }
    if (!@marks || (@marks==1 && $marks[0][1] eq "published error code")) {
        if (($e->{messageType} // "") =~ /^(error|fault)$/i ||
                $msg =~ /reject|refus|den(?:y|ied|ial)|fail|protocol|entitle|crash/i) {
            ++$opaque;
            # formatString is a static logging template. Only that
            # field may supply text here, never a formatted eventMessage.
            my $fmt=$e->{formatString} // "";
            $fmt =~ s/[^\x20-\x7e]/ /g;
            $fmt =~ s{(?:https?://|/)[^\s,%]+}{[location]}gi;
            $fmt =~ s/\b[\w.+-]+\@[\w.-]+\.[\w.-]+/[address]/g;
            $fmt =~ s/\b[A-F0-9]{8}(?:-[A-F0-9]{4}){3}-[A-F0-9]{12}\b/[id]/gi;
            $fmt =~ s/\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z][\w.-]+\b/$& =~ m{^com\.apple\.iconservices(?:\.(?:store|iconservicesagent|iconservicesd))?$}i ? $& : "[identifier]"/ge;
            $fmt =~ s/\s+/ /g;
            $fmt=substr($fmt,0,180);
            $fmt="static template unavailable" if $fmt !~ /\S/;
            push @marks, ["format", $fmt];
        }
    }
    my @services = $msg =~ /\b(com\.apple\.iconservices(?:\.iconservicesagent|\.iconservicesd|\.store)?)(?![.\w])/ig;
    my %seen;
    my $extras=join(" ", grep { !$seen{$_}++ } (@codes,@services));
    for my $mark (@marks) {
        my ($kind,$phrase)=@$mark;
        my $key=join(" | ", $who, $phrase, grep {length} $extras);
        my $group=($kind eq "detail" ? \%reason : $kind eq "format" ? \%formats : \%symptoms);
        my $x=($group->{$key} //= [$time,$time,0]);
        $x->[1]=$time;
        ++$x->[2];
    }
}
for my $pair (["detail",\%reason],["unclassified static template",\%formats],["symptom",\%symptoms]) {
    my ($kind,$group)=@$pair;
    my @keys=sort { $group->{$b}[2] <=> $group->{$a}[2] || $a cmp $b } keys %$group;
    printf "%s groups=%d\n", $kind, scalar @keys;
    my $limit=$kind eq "detail" ? 24 : 8;
    for my $k (splice(@keys,0,$limit)) {
        my ($first,$last,$n)=@{$group->{$k}};
        print "  $first .. $last | $k | count=$n\n";
    }
    print "  other groups omitted=",scalar(@keys),"\n" if @keys;
}
printf "Visible records=%d; containing <private>=%d; unclassified failure-related messages=%d; malformed=%d; end marker=%s\n", $records||0, $private||0, $opaque||0, $bad||0, $finished ? "yes" : "no";
exit(($bad || !$finished || !$records) ? 3 : 0);
'
capture() {
    local label=$1 start=$2 end=$3
    local -a result
    echo "$label: $start to $end"
    /usr/bin/log show --style ndjson --info --debug --start "$start" --end "$end" \
        --predicate "$predicate" 2>/dev/null | /usr/bin/perl -MJSON::PP -e "$parser"
    result=("${PIPESTATUS[@]}")
    if [[ ${result[0]} != 0 || ${result[1]} != 0 ]]; then
        echo "Limited visibility: log status=${result[0]}, decoder status=${result[1]}. The interval cannot establish an absence of failures."
        partial=1
    fi
}
echo 'Observing a fresh eight-second interval without opening a Finder window.'
fresh_start=$(/bin/date '+%Y-%m-%d %H:%M:%S%z')
/bin/sleep 8
fresh_end=$(/bin/date '+%Y-%m-%d %H:%M:%S%z')
capture 'Earlier reproduction (EET)' '2026-11-19 16:33:21+0200' '2026-11-19 16:33:59+0200'
capture 'Fresh passive interval' "$fresh_start" "$fresh_end"
echo 'Info/debug records can be absent or privacy-redacted. Detail phrases describe what a process reported.'
[[ $partial == 0 ]] || exit 3
REMOTE
status=("${PIPESTATUS[@]}")
if [[ ${status[1]} != 0 ]]; then
    echo 'Could not write the complete local report.' >&2
    exit 1
fi
if [[ ${status[0]} != 0 ]]; then
    echo "Collection incomplete (status ${status[0]}). Any available observations are in the local report." >&2
fi
exit "${status[0]}"
