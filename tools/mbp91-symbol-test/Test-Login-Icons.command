#!/bin/bash
# Run on the SSH client. Reports contain grouped events and sampling times.
set -u
umask 077
remote_script() {
cat <<'REMOTE'
set -u
export LC_ALL=C
IFS= read -r -d '' decoder <<'PERL' || :
use strict;
use warnings;
use JSON::PP;
use Time::Local qw(timegm);
my $details = @ARGV && $ARGV[0] eq '--details';
shift @ARGV if $details;
my @windows = map { [split /:/, $_, 3] } @ARGV;
my (%n,%times,%seconds,$end,$malformed,$opaque);
sub static_template {
    my ($fmt) = @_;
    return 'indisponibil' unless defined $fmt && length $fmt;
    $fmt =~ s/[^\x20-\x7e]/ /g;
    $fmt =~ s{(?:[a-zA-Z]+://|/)[^\s,\x22\x27]+}{[cale]}g;
    $fmt =~ s/\b[\w.+-]+\@[\w.-]+/[adresa]/g;
    $fmt =~ s/\b[\da-f]{8}(?:-[\da-f]{4}){3}-[\da-f]{12}\b/[uuid]/ig;
    $fmt =~ s/\b0x[\da-f]{6,}\b/[adresa]/ig;
    $fmt =~ s/\b(?:\d{1,3}\.){3}\d{1,3}\b/[ip]/g;
    $fmt =~ s/\s+/ /g;
    return substr($fmt,0,220);
}
while (<STDIN>) {
    next if /^\s*$/;
    my $e = eval { decode_json($_) };
    if (ref $e ne 'HASH') { ++$malformed; next }
    if (exists $e->{finished}) { $end=1; next }
    my $time = $e->{timestamp} // '';
    unless ($time =~ /^(\d{4})-(\d\d)-(\d\d)[ T](\d\d):(\d\d):(\d\d)(?:\.\d+)?(Z|[+-]\d\d:?\d\d)$/) { ++$malformed; next }
    my ($y,$m,$d,$h,$min,$s,$z)=($1,$2,$3,$4,$5,$6,$7);
    my $k="$y-$m-$d $h:$min:$s$z";
    unless (exists $seconds{$k}) {
        my $offset=0;
        if ($z =~ /([+-])(\d\d):?(\d\d)/) { $offset=($1 eq '+' ? 1 : -1)*(3600*$2+60*$3) }
        my $utc=eval { timegm($s,$min,$h,$d,$m-1,$y) };
        unless (defined $utc) { ++$malformed; next }
        $seconds{$k}=$utc-$offset;
    }
    my $epoch=$seconds{$k};
    my ($window)=grep { $epoch >= $_->[1] && $epoch < $_->[2] } @windows;
    next unless $window;
    my $proc=$e->{processImagePath} // $e->{process} // '';
    $proc =~ s{.*/}{};
    my $msg=$e->{eventMessage} // '';
    my $sender=$e->{senderImagePath} // ''; $sender =~ s{.*/}{};
    my $gui= $proc =~ /^(?:WindowServer|Finder|ControlCenter|SystemUIServer|iconservicesagent|iconservicesd|Dock|loginwindow)$/;
    my $driver=$proc =~ /^(?:AGX|AppleIntel|NVDA|GeForce|MetalDriver)/i;
    my $who=$gui ? $proc : $proc =~ /compiler/i ? 'serviciu-compilator (client necunoscut)' : $driver ? 'driver (client necunoscut)' : 'alt proces (client necunoscut)';
    next if $proc =~ /^(?:python(?:[0-9.]*)?|osascript|log|perl)$/i;
    my $event;
    if ($msg =~ /unhandled metadata type\s*:\s*air\.render_target\b/i) { $event='air.render_target respins' }
    elsif ($msg =~ /\bair\.render_target\b/i) { $event='air.render_target mentionat' }
    elsif ($proc eq 'Finder' && $msg =~ /failed to generate image/i && $msg =~ /\bNSCocoaErrorDomain\s+Code=4097\b/i) { $event='generare imagine, 4097' }
    elsif ($proc =~ /^iconservices(?:agent|d)$/ && $msg =~ /(?:rejected by the listener|listener rejected)/i) { $event='conexiune refuzata de listener' }
    elsif (($gui || $proc =~ /compiler/i || ($details && $driver)) && $msg =~ /(?:shader|pipeline|metal compiler|framebuffer|RenderBox)/i && $msg =~ /(?:fail|error|unsupported|reject|could not|unable)/i) { $event='alta eroare grafica, nespecifica' }
    else { ++$opaque; next }
    my $gpu='fara marca GPU in mesaj/emitent';
    my $source="$msg $sender";
    my $nv=$source =~ /(?:nvidia|geforce|\bNVDA)/i;
    my $ig=$source =~ /(?:\bIntel|AppleIntelHD|HD Graphics 4000)/i;
    $gpu=$nv&&$ig ? 'ambele marci mentionate' : $nv ? 'NVIDIA mentionat' : 'Intel mentionat' if $nv || $ig;
    my $key="$who | $event | $gpu";
    if ($details) {
        next if $event eq 'generare imagine, 4097' || $event eq 'conexiune refuzata de listener';
        $sender='indisponibil' unless $sender =~ /\A[A-Za-z0-9_.+-]{1,72}\z/;
        my %hints;
        while ($msg =~ /\b(MTLLibraryErrorDomain|MTLRenderPipelineErrorDomain|MTLCommandBufferErrorDomain|CompilerError|NSOSStatusErrorDomain|NSPOSIXErrorDomain|NSCocoaErrorDomain)\b(?:\s*[,;:(=]?\s*(?:code|error)?\s*[:=]?\s*(-?\d{1,10})\b)?/ig) {
            $hints{defined($2) ? "$1 $2" : $1}=1;
        }
        while ($msg =~ /\b(out of memory|timed out|unsupported pixel format|invalid pixel format|device removed|internal compiler error|pipeline creation failed|failed to compile|shader compilation failed|failed to create|invalid descriptor|fetch0|fragment shader|vertex shader|RenderBox|framebuffer|shader|pipeline)\b/ig) {
            $hints{lc($1)}=1;
        }
        while ($msg =~ /\b(kIOReturn[A-Za-z]{1,40}|kCGError[A-Za-z]{1,40}|MTL(?:CommandBuffer|RenderPipeline|Library)Error[A-Za-z]{1,48}|AIR(?:Compiler|Linker)Error[A-Za-z]{0,40})\b/g) {
            $hints{$1}=1;
        }
        while ($msg =~ /\b(error(?:\s+code)?|status|errno|IOReturn|OSStatus)\s*[:=]?\s*(0x[\da-f]{1,8}|-?\d{1,10})\b/ig) {
            $hints{lc($1).' '.lc($2)}=1;
        }
        $key .= ' | emitent='.$sender.' | sablon='.static_template($e->{formatString});
        $key .= ' | indicii='.join(', ',sort keys %hints) if %hints;
        my $bounds=($times{$window->[0]}{$key} //= [$time,$time]);
        $bounds->[1]=$time;
    }
    ++$n{$window->[0]}{$key};
}
for my $w (@windows) {
    print "[$w->[0]]\n";
    my $bucket=$n{$w->[0]} || {};
    print "  0 evenimente clasificate vizibile\n" unless keys %$bucket;
    my @keys=sort { $bucket->{$b} <=> $bucket->{$a} || $a cmp $b } keys %$bucket;
    my $total=@keys;
    splice(@keys,50) if $details && @keys>50;
    for my $group (@keys) {
        print "  $group | $bucket->{$group}";
        print ' | ',join(' .. ',@{$times{$w->[0]}{$group}}) if $details;
        print "\n";
    }
    print "  Alte grupuri omise din afișare: ",$total-@keys,"\n" if $total>@keys;
}
printf "Jurnal: marcaj final=%s, invalide=%d, potriviri neclasificate=%d\n",$end?'da':'nu',$malformed||0,$opaque||0;
exit(($end && !$malformed) ? 0 : 3);
PERL
if [[ ${1:-} == --check ]]; then
    check=$(/usr/bin/perl -e "$decoder" 'probe:10:20' <<'FIXTURES'
{"timestamp":"1970-01-01 02:00:10.123+0200","processImagePath":"/a/WindowServer","eventMessage":"Unhandled metadata type: air.render_target","senderImagePath":"/drivers/GeForceMTLDriver"}
{"timestamp":"1970-01-01 00:00:11Z","process":"MTLCompilerService","eventMessage":"Unhandled metadata type: air.render_target"}
{"timestamp":"1970-01-01 00:00:12Z","process":"Finder","eventMessage":"Failed to generate image NSCocoaErrorDomain Code=4097"}
{"timestamp":"1970-01-01 00:00:20Z","process":"iconservicesagent","eventMessage":"peer rejected by the listener"}
{"timestamp":"1970-01-01 00:00:13Z","process":"python3.12","eventMessage":"Unhandled metadata type: air.render_target"}
{"finished":true}
FIXTURES
    ) || exit 1
    [[ $check == *'WindowServer | air.render_target respins | NVIDIA mentionat | 1'* &&
       $check == *'serviciu-compilator (client necunoscut) | air.render_target respins'* &&
       $check == *'Finder | generare imagine, 4097'* && $check != *'conexiune refuzata'* && $check != *'alt proces'* ]] || exit 1
    check=$(/usr/bin/perl -e "$decoder" -- --details 'inceput:10:12' 'gol:12:14' 'login:14:20' <<'DETAILS'
{"timestamp":"1970-01-01 00:00:10Z","process":"WindowServer","eventMessage":"Shader /Users/secret/file failed (CompilerError, code 2), kIOReturnUnsupported status=0xe00002c7","senderImagePath":"/System/Metal","formatString":"shader %s failed at /Users/private/file"}
{"timestamp":"1970-01-01 00:00:12Z","process":"MTLCompilerService","eventMessage":"Unhandled metadata type: air.render_target","formatString":"Unhandled metadata type: %@"}
{"timestamp":"1970-01-01 00:00:14Z","process":"Finder","eventMessage":"failed to generate image NSCocoaErrorDomain Code=4097","formatString":"must not be exported"}
{"finished":true}
DETAILS
    ) || exit 1
    [[ $check == *'CompilerError 2'* && $check == *'kIOReturnUnsupported'* && $check == *'status 0xe00002c7'* &&
       $check == *'sablon=shader %s failed at [cale]'* &&
       $check == *'[gol]'*'serviciu-compilator (client necunoscut)'* && $check == *'[login]'*'0 evenimente'* &&
       $check != *'/Users/'* && $check != *'must not be exported'* ]] || exit 1
    echo 'Verificat local: decodare NDJSON, intervale, atribuire, separarea XPC si excluderea probei sintetice.'
    exit 0
fi
uid=$(/usr/bin/id -u)
if [[ $(/usr/sbin/sysctl -n hw.model) != MacBookPro9,1 || $(/usr/bin/sw_vers -buildVersion) != 26B131 || ( ${1:-} != --graphics-details && $(/usr/bin/stat -f %u /dev/console) != "$uid" ) ]]; then
    echo 'Ținta trebuie să fie MacBookPro9,1 cu build 26B131 si utilizatorul SSH în sesiunea grafică.'; exit 2
fi
/usr/bin/perl -MJSON::PP -MTime::Local -e 1 || exit 2
now() { /bin/date +%s; }
stamp() { /bin/date -r "$1" '+%Y-%m-%d %H:%M:%S%z'; }
query_timeout=90
decoder_mode=summary
partial=0
scan() {
    local lo=$1 hi=$2
    shift 2
    [[ $decoder_mode == details ]] && set -- --details "$@"
    printf 'Citire %s .. %s\n' "$(stamp "$lo")" "$(stamp "$hi")"
    /usr/bin/perl -e 'alarm shift; exec @ARGV or die $!' "$query_timeout" /usr/bin/log show --style ndjson --info --debug --start "$(stamp "$lo")" --end "$(stamp "$hi")" --predicate "$pred" | /usr/bin/perl -e "$decoder" -- "$@"
    local -a rc=("${PIPESTATUS[@]}")
    if [[ ${rc[0]} != 0 || ${rc[1]} != 0 ]]; then echo "Citire incompletă (log=${rc[0]} decodor=${rc[1]})."; partial=3; fi
}
if [[ ${1:-} == --graphics-details ]]; then
    # Retrospective for report GoldenGate-Login-Icons.P1u3MRAU, independent of current boot.
    incident_epoch() { /bin/date -j -f '%Y-%m-%d %H:%M:%S%z' "2026-11-19 $1+0200" +%s; }
    lo=$(incident_epoch 16:30:37) && middle=$(incident_epoch 16:31:07) &&
        login_begin=$(incident_epoch 16:31:26) && hi=$(incident_epoch 16:32:56) || exit 2
    echo 'Golden 26B131, incidentul din 19 noiembrie 2026. Intervalele sunt consecutive, cu capătul final exclus.'
    echo 'Grupare după proces, marcă GPU menționată, emitent, șablon static și indicii tehnice.'
    decoder_mode=details
    query_timeout=60
    pred='(eventMessage CONTAINS[c] "air.render_target") OR (((process IN {"WindowServer","Finder","ControlCenter","SystemUIServer","iconservicesagent","iconservicesd","Dock","loginwindow"}) OR process CONTAINS[c] "compiler" OR process BEGINSWITH[c] "AGX" OR process BEGINSWITH[c] "AppleIntel" OR process BEGINSWITH[c] "NVDA" OR process BEGINSWITH[c] "GeForce" OR process BEGINSWITH[c] "MetalDriver") AND (eventMessage CONTAINS[c] "shader" OR eventMessage CONTAINS[c] "pipeline" OR eventMessage CONTAINS[c] "metal compiler" OR eventMessage CONTAINS[c] "framebuffer" OR eventMessage CONTAINS[c] "RenderBox") AND (eventMessage CONTAINS[c] "fail" OR eventMessage CONTAINS[c] "error" OR eventMessage CONTAINS[c] "unsupported" OR eventMessage CONTAINS[c] "reject" OR eventMessage CONTAINS[c] "could not" OR eventMessage CONTAINS[c] "unable"))'
    scan "$lo" "$middle" "pornire-WindowServer:$lo:$middle"
    scan "$middle" "$login_begin" "interval-anterior-necitit:$middle:$login_begin"
    # Stream each part separately so a late interruption preserves earlier windows.
    for ((start=login_begin; start<hi; start+=30)); do
        stop=$((start+30))
        ((stop>hi)) && stop=$hi
        scan "$start" "$stop" "pornire-ControlCenter:$start:$stop"
    done
    echo 'Zero înseamnă că nu s-au returnat evenimente clasificate. Jurnalul poate omite evenimente. Marca dintr-un mesaj și emitentul acestuia nu identifică automat GPU-ul care a randat sau clientul compilatorului.'
    exit "$partial"
fi
clock=$(now)
boot=$(/usr/sbin/sysctl -n kern.boottime | /usr/bin/sed -nE 's/.*sec = ([0-9]+),.*/\1/p')
[[ $boot =~ ^[0-9]+$ ]] || { echo 'Ora pornirii este indisponibilă.'; exit 2; }
start_process() {
    local pid text
    pid=$(/usr/bin/pgrep "$@" | /usr/bin/head -1)
    [[ $pid =~ ^[0-9]+$ ]] || return 1
    text=$(/bin/ps -p "$pid" -o lstart=) || return 1
    /bin/date -j -f '%a %b %e %T %Y' "$text" +%s 2>/dev/null
}
cc=$(start_process -u "$uid" -x ControlCenter) || cc=0
ws=$(start_process -x WindowServer) || ws=0
user=$(/usr/bin/id -un)
ut=$(/usr/bin/who | /usr/bin/awk -v u="$user" '$1==u && $2=="console" && $5 ~ /^[0-9][0-9]:[0-9][0-9]$/ {print $3,$4,$5; exit}')
login=0
if [[ -n $ut ]]; then
    year=$(/bin/date +%Y)
    login=$(/bin/date -j -f '%Y %b %e %H:%M:%S' "$year $ut:00" +%s 2>/dev/null) || login=0
    if ((login > clock+60)); then login=$(/bin/date -j -f '%Y %b %e %H:%M:%S' "$((year-1)) $ut:00" +%s 2>/dev/null) || login=0; fi
fi
printf 'MacBookPro9,1 Golden 26B131. Pornire: %s\n' "$(stamp "$boot")"
((ws>0)) && printf 'Proces WindowServer curent pornit: %s\n' "$(stamp "$ws")"
((cc>0)) && printf 'Proces ControlCenter curent pornit: %s\n' "$(stamp "$cc")"
if ((login>=boot-60 && login<=clock)); then
    printf 'Sesiune console, precizie de un minut: %s\n' "$(stamp "$login")"
    begin=$login; label='login-console'
    if ((cc>=login && cc<=login+120)); then begin=$((cc-5)); label='pornire-ControlCenter-la-login'; fi
elif ((cc>=boot && cc<=clock)); then
    begin=$((cc-5)); label='pornire-ControlCenter-login-neconfirmat'
else
    begin=$boot; label='pornire-sistem-login-neconfirmat'
fi
((begin<boot)) && begin=$boot
hist_end=$((begin+90))
((hist_end>clock)) && hist_end=$clock
pred='(eventMessage CONTAINS[c] "air.render_target") OR (process == "Finder" AND eventMessage CONTAINS[c] "failed to generate image" AND eventMessage CONTAINS "4097") OR ((process IN {"iconservicesagent","iconservicesd"}) AND (eventMessage CONTAINS[c] "rejected by the listener" OR eventMessage CONTAINS[c] "listener rejected")) OR (((process IN {"WindowServer","Finder","ControlCenter","SystemUIServer","iconservicesagent","iconservicesd","Dock","loginwindow"}) OR process CONTAINS[c] "compiler") AND (eventMessage CONTAINS[c] "shader" OR eventMessage CONTAINS[c] "pipeline" OR eventMessage CONTAINS[c] "framebuffer" OR eventMessage CONTAINS[c] "RenderBox") AND (eventMessage CONTAINS[c] "fail" OR eventMessage CONTAINS[c] "error" OR eventMessage CONTAINS[c] "unsupported" OR eventMessage CONTAINS[c] "reject" OR eventMessage CONTAINS[c] "could not" OR eventMessage CONTAINS[c] "unable"))'
slots=()
phase() {
    local tag=$1 secs=$2 prompt=$3 lo hi
    printf '\n%s (%s s)\n' "$prompt" "$secs"
    lo=$(now); /bin/sleep "$secs"; hi=$(now)
    slots+=("$tag:$lo:$hi")
}
if [[ ${1:-} != --login-only ]]; then
    echo 'Urmează patru intervale. Acționează pe ecranul MacBook-ului și închide fiecare meniu înainte de pasul următor.'
    phase repaus 8 'Acum lasă desktopul nemișcat'
    phase sunet 12 'Acum deschide meniul de sunet vizibil, apoi închide-l'
    phase wifi 12 'Acum apasă în locul pictogramei Wi-Fi lipsă, apoi închide meniul'
    phase finder 15 'Acum deschide sau selectează volumul Tahoe în Finder'
    echo 'Acțiunile s-au încheiat. Se citesc intervalele înregistrate.'
    /bin/sleep 2
fi
pre=$ws; pre_label=pornire-proces-WindowServer-curent
if ((pre<boot || pre>clock)); then pre=$boot; pre_label=pornire-sistem-WindowServer-neconfirmat; fi
pre_end=$((pre+30))
((pre_end>clock)) && pre_end=$clock
# Split overlaps at the login boundary. The printed phase counts are disjoint.
if ((pre<begin && pre_end>begin)); then pre_end=$begin; fi
if ((pre>=begin && pre<hist_end)); then
    echo 'Pornirea procesului WindowServer (sau ancora de boot) se suprapune cu intervalul de login de mai jos.'
    pre=$hist_end
fi
((pre_end>pre)) && scan "$pre" "$pre_end" "$pre_label:$pre:$pre_end"
if ((hist_end>begin)); then scan "$begin" "$hist_end" "$label:$begin:$hist_end"
else echo 'Intervalul istoric al sesiunii este prea scurt pentru măsurare.'; partial=3
fi
if [[ ${1:-} != --login-only ]]; then
    first=${slots[0]#*:}; first=${first%:*}
    last=${slots[3]##*:}
    scan "$first" "$last" "${slots[@]}"
fi
echo 'Istoricul privește pornirea proceselor din sesiunea curentă. Jurnalul poate omite sau masca erorile. Marca GPU este o mențiune din același mesaj sau din emitent. Un serviciu de compilare separat nu identifică aplicația client.'
exit "$partial"
REMOTE
}
if [[ ${1:-} == --check && $# == 1 ]]; then remote_script | /bin/bash -s -- --check; exit $?; fi
mode=--live
if [[ ${1:-} == --login-only || ${1:-} == --graphics-details ]]; then mode=$1; shift; fi
dest=${1:-${GOLDEN_GATE_SSH:-}}
if [[ $# -gt 1 || ! $dest =~ ^[[:alnum:]_][[:alnum:]_.-]*@[[:alnum:]][[:alnum:].-]*$ ]]; then
    echo 'Utilizare: Test-Login-Icons.command [--login-only | --graphics-details] utilizator@gazdă (sau --check)' >&2; exit 2
fi
dir=$(cd "$(dirname "$0")" && pwd -P) || exit 1
prefix=GoldenGate-Login-Icons
[[ $mode == --graphics-details ]] && prefix=GoldenGate-Graphics-Details
report=$(/usr/bin/mktemp "$dir/../$prefix.XXXXXXXX") || exit 1
echo "Raport pe iMac: $report"
remote_script | /usr/bin/ssh -T -F /dev/null -o StrictHostKeyChecking=yes -o UpdateHostKeys=no -o ClearAllForwardings=yes -o ForwardAgent=no -o ForwardX11=no -o ConnectTimeout=10 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 "$dest" /bin/bash -s -- "$mode" | /usr/bin/tee "$report"
rc=("${PIPESTATUS[@]}")
((rc[2] == 0)) || exit 1
exit "${rc[1]}"
