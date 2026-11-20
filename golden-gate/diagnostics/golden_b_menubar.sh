# Sourced after the caller verifies the Golden B volume and console owner.
gg_menubar_decode() {
    /usr/bin/perl -MJSON::PP -e '
        use strict; use warnings;
        binmode STDOUT, ":encoding(UTF-8)";
        my $compiler = (@ARGV && shift eq "compiler");
        my (%rows, $finished, $invalid, $lost, $overflow, $anchor);
        sub short_text {
            my ($s,$limit) = @_;
            $s //= "";
            $s =~ s/[\x00-\x1f\x7f]+/ /g;
            $s =~ s{(/Users/)[^/\s]+}{$1<user>}g;
            return length($s) > $limit ? substr($s,0,$limit-3)."..." : $s;
        }
        while (<STDIN>) {
            next if /^\s*$/;
            my $r = eval { decode_json($_) };
            if (ref($r) ne "HASH") { ++$invalid; next }
            if (exists $r->{finished}) { $finished=1; next }
            if (($r->{eventType}//"") =~ /loss|drop/i) { ++$lost; next }
            my $proc = $r->{processImagePath} // $r->{process} // "";
            $proc =~ s{.*/}{};
            if ($compiler) {
                next unless $proc =~ /(?:MTL|Metal|GPU).*Compiler|AGXCompiler|Intel.*Compiler/i;
            } else {
                next unless $proc =~ /^(?:ControlCenter|MenuBarAgent|SystemUIServer|WindowServer)$/;
            }
            my $sender = $r->{senderImagePath} // ""; $sender =~ s{.*/}{};
            my ($system,$category,$msg,$fmt) = map { $r->{$_} // "" }
                qw(subsystem category eventMessage formatString);
            next unless $compiler || "$sender $system $category $msg $fmt" =~
                /RenderBox|Metal|shader|air\.render_target|framebuffer|pipeline|image provider|GPUCompiler/i;
            my $error = ($r->{messageType}//"") =~ /^(error|fault)$/i ||
                "$msg $fmt" =~ /fail|error|timed?\s*out|timeout|unsupported|unhandled|invalid|reject|could not|unable|not found/i;
            next unless $compiler || $error;
            if (!$compiler && $proc eq "ControlCenter" && $msg =~ /compiler failed to build request/i &&
                    ($r->{timestamp}//"") =~ /^(\d{4}-\d\d-\d\d[ T]\d\d:\d\d:\d\d)(?:\.\d+)?([-+]\d{4})$/) {
                $anchor = "$1$2"; $anchor =~ tr/T/ /;
            }
            my $keytext = short_text($msg || $fmt,400);
            $keytext =~ s/\b0x[\da-f]{8,}\b/<addr>/ig;
            my $key = join("\t",$proc,$sender,$system,$category,$keytext);
            unless (exists $rows{$key}) {
                if (keys(%rows) >= 96) { ++$overflow; next }
                $rows{$key} = [0,short_text($r->{timestamp},40),short_text($proc,40),
                    short_text($sender,64),short_text($system,100),short_text($category,100),
                    short_text($msg,450),short_text($fmt,240),$error ? 1 : 0];
            }
            ++$rows{$key}[0];
        }
        my @sorted = sort { $rows{$b}[8] <=> $rows{$a}[8] || $rows{$b}[0] <=> $rows{$a}[0] || $a cmp $b } keys %rows;
        for my $key (splice(@sorted,0,12)) {
            my ($n,$when,$proc,$sender,$s,$c,$msg,$fmt) = @{$rows{$key}};
            print "GG_MENUBAR $when | $proc | $sender | $s/$c | x$n | ",($msg || "(mesaj indisponibil)"),"\n";
            print "GG_MENUBAR format: $fmt\n" if length($fmt) && $fmt ne $msg;
        }
        print "GG_MENUBAR Alte grupe: ",scalar(@sorted),"; evenimente peste limita de grupare: ",($overflow//0),"\n"
            if @sorted || $overflow;
        if (!$finished || $invalid || $lost) {
            print "GG_MENUBAR Jurnal incomplet: final=",($finished//0),", linii invalide=",($invalid//0),", pierderi=",($lost//0),"\n";
            exit 3;
        }
        unless (keys %rows) {
            print $compiler ? "GG_MENUBAR Niciun mesaj al serviciului de compilare in aceasta fereastra.\n" :
                              "GG_MENUBAR Nicio eroare grafica relevanta in acest interval.\n";
            exit 4;
        }
        print "GG_SHADER_TIME $anchor\n" if $anchor;
        exit 0;
    ' "${1:-client}"
}

gg_menubar_window() (
    set +e
    local label=$1 start=$2 end=$3 mode=${4:-client} predicate
    local -a status
    predicate='process IN {"ControlCenter","MenuBarAgent","SystemUIServer","WindowServer"} AND (messageType IN {"error","fault"} OR eventMessage CONTAINS[c] "fail" OR eventMessage CONTAINS[c] "error" OR eventMessage CONTAINS[c] "timed out" OR eventMessage CONTAINS[c] "unhandled" OR eventMessage CONTAINS[c] "unsupported")'
    if [[ $mode == compiler ]]; then
        predicate='process CONTAINS[c] "Compiler"'
    fi
    printf 'GG_MENUBAR %s | %s .. %s\n' "$label" "$start" "$end"
    /usr/bin/perl -e 'alarm 35; exec @ARGV or die $!' /usr/bin/log show --style ndjson --info --debug \
        --start "$start" --end "$end" --predicate "$predicate" | gg_menubar_decode "$mode"
    status=("${PIPESTATUS[@]}")
    if (( status[0] )); then
        printf 'GG_MENUBAR Citirea jurnalului a eșuat (log=%s).\n' "${status[0]}"
        return 3
    fi
    return "${status[1]}"
)

gg_menubar_registry() {
    /usr/bin/perl -e '
        my $pid = shift; my ($root,$node,%hits);
        while (<STDIN>) {
            if (/^([| ]*)\+-o (.*?)\s+<class ([\w.-]+), id (0x[\da-f]+),/i) {
                $root="$2 ($3, $4)" if $1 eq ""; $node=$3; next;
            }
            if (/^[| ]*"IOUserClientCreator"\s*=\s*"pid\s+\Q$pid\E,\s*ControlCenter"\s*$/ && defined $root) {
                $hits{"$root | $node"}++;
            }
        }
        print "GG_ACCEL ControlCenter PID=$pid | $_ | clienți=$hits{$_}\n" for sort keys %hits;
        exit(keys(%hits) ? 0 : 4);
    ' "$1"
}

gg_menubar_mappings() (
    local pid=$1 role=$2
    local -a status
    /usr/bin/perl -e 'alarm 7; exec @ARGV or die $!' /usr/sbin/lsof -nP -a -p "$pid" -d txt -Fn 2>/dev/null |
    /usr/bin/awk -v role="$role" -v pid="$pid" '
        /^n/ {
            p=substr($0,2)
            if (p ~ /\/(libmetal-framebuffer\.dylib|libhaoMetalCompilerCompat\.dylib|MetalOld\.dylib|AppleIntelHD4000GraphicsMTLDriver|GeForceMTLDriver|MTLCompiler|GPUCompiler|libLLVM_helper\.dylib|iCBE\.dylib)$/ && !seen[p]++) {
                print "GG_MAP", role, "PID=" pid, p; count++
            }
        }
        END {if (!count) exit 4}'
    status=("${PIPESTATUS[@]}")
    if (( status[0] || status[1] )); then
        printf 'GG_MAP %s PID=%s | imagini neconfirmate (lsof=%s, filtru=%s).\n' "$role" "$pid" "${status[0]}" "${status[1]}"
    fi
)

gg_menubar_metal_state() (
    local pid others path expected hash cache sub root
    local -a status
    pid=$(/usr/bin/pgrep -u "$(/usr/bin/id -u)" -x ControlCenter)
    if [[ $pid =~ ^[0-9]+$ ]]; then
        /usr/bin/perl -e 'alarm 8; exec @ARGV or die $!' /usr/sbin/ioreg -p IOService -r -c IOAccelerator -l -w 220 2>/dev/null |
            gg_menubar_registry "$pid"
        status=("${PIPESTATUS[@]}")
        (( status[0] == 0 && status[1] == 0 )) || echo 'GG_ACCEL Niciun accelerator deschis de ControlCenter nu a putut fi confirmat.'
        gg_menubar_mappings "$pid" ControlCenter
    else
        echo 'GG_ACCEL Procesul ControlCenter al contului nu este identificabil.'
    fi
    others=$(/usr/bin/pgrep -x MTLCompilerService | /usr/bin/head -3)
    for pid in $others; do
        [[ $pid =~ ^[0-9]+$ ]] && gg_menubar_mappings "$pid" MTLCompilerService
    done
    [[ -n $others ]] || echo 'GG_MAP Nicio instanță MTLCompilerService observată în acest moment.'
    # Reference hashes from the actual Golden B kit inputs assembled on the iMac.
    while IFS=' ' read -r expected path; do
        hash=$(/usr/bin/shasum -a 256 "$path" 2>/dev/null) || { echo "GG_METAL necitit $path"; continue; }
        hash=${hash%% *}
        if [[ $hash == "$expected" ]]; then
            printf 'GG_METAL conform cu B | %s\n' "$path"
        else
            printf 'GG_METAL diferit | %s | instalat=%s | kit=%s\n' "$path" "$hash" "$expected"
        fi
    done <<'GG_GOLDEN_B_FILES'
898cab41fbf2ab39c973e884da22b7ad92871fe1c9c54fc21308df869bca1e94 /usr/lib/libmetal-framebuffer.dylib
ebd2ecbe8ef7fb1e1610fcce3228df06f110df8c647658c2077406302666a403 /System/Library/PrivateFrameworks/RenderBox.framework/Versions/A/Resources/default.metallib
58aae32289d3143ddbefc9db67a757e014a89a22aeda0fa21ad12adb1c7bc777 /System/Library/Frameworks/Metal.framework/Versions/A/XPCServices/MTLCompilerService.xpc/Contents/MacOS/MTLCompilerService
337869eaa4a48d4c0685272da8d48a404d9ccd6e494be466c6e1fe5ec5b6b8b2 /System/Library/PrivateFrameworks/MTLCompiler.framework/Versions/3802/Libraries/libhaoMetalCompilerCompat.dylib
GG_GOLDEN_B_FILES
    cache=$(/usr/bin/getconf DARWIN_USER_CACHE_DIR) || return
    if [[ $cache == /* ]]; then
        for sub in 0_0/functions.data 0_0/functions.list 31001/libraries.data 31001/libraries.list; do
            for role in sesiune seed; do
                root="${cache%/}/com.apple.controlcenter/com.apple.metal"
                [[ $role != seed ]] || root='/Library/Application Support/PerUserSeed/metal/com.apple.controlcenter/com.apple.metal'
                if [[ -r $root/$sub ]]; then
                    /usr/bin/stat -f "GG_CACHE $role $sub | %z octeți" "$root/$sub"
                else
                    echo "GG_CACHE $role $sub | indisponibil"
                fi
            done
        done
    fi
)

gg_inspect_menubar() (
    set +e
    local now boot from old_start old_end rc display_rc log_summary anchor moment
    display_reference
    display_rc=$?
    (( display_rc == 0 )) || echo 'GG_MENUBAR GPU-ul ecranului nu a fost confirmat.'
    gg_menubar_metal_state
    now=$(/bin/date +%s) || return 3
    boot=$(/usr/sbin/sysctl -n kern.boottime | /usr/bin/sed -nE 's/^.*sec = ([0-9]+), usec =.*$/\1/p')
    if [[ ! $boot =~ ^[0-9]+$ || $boot -gt $now ]]; then
        echo 'GG_MENUBAR Ora pornirii nu a putut fi stabilită.'
        return 3
    fi
    from=$(( now-240 > boot ? now-240 : boot ))
    log_summary=$(gg_menubar_window 'Sesiunea curentă' "$(/bin/date -r "$from" '+%F %T%z')" "$(/bin/date -r "$now" '+%F %T%z')")
    rc=$?
    printf '%s\n' "$log_summary"
    if (( rc != 0 )); then
        # Interval measured around the ControlCenter relaunch on this Golden B boot.
        old_start=$(/bin/date -j -f '%F %T%z' '2026-11-20 12:55:35+0200' +%s) || return 3
        old_end=$(( old_start+39 ))
        if (( boot <= old_start && old_end <= now && old_start < from )); then
            log_summary=$(gg_menubar_window 'Relansarea Control Center din același boot' \
                "$(/bin/date -r "$old_start" '+%F %T%z')" "$(/bin/date -r "$old_end" '+%F %T%z')")
            rc=$?
            printf '%s\n' "$log_summary"
        fi
    fi
    anchor=$(printf '%s\n' "$log_summary" | /usr/bin/sed -n 's/^GG_SHADER_TIME //p' | /usr/bin/tail -1)
    # The saved 13:06 report contains this exact pair of errors on the same boot.
    [[ -n $anchor ]] || anchor='2026-11-20 13:05:23+0200'
    moment=$(/bin/date -j -f '%F %T%z' "$anchor" +%s)
    if [[ $moment =~ ^[0-9]+$ ]] && (( boot <= moment && moment <= now )); then
        gg_menubar_window 'Compilator: mesaje din jurul erorii ControlCenter (clientul cererii nu este identificat prin timp)' \
            "$(/bin/date -r "$(( moment-3 > boot ? moment-3 : boot ))" '+%F %T%z')" \
            "$(/bin/date -r "$(( moment+3 < now ? moment+3 : now ))" '+%F %T%z')" compiler
    fi
    if (( rc != 0 )); then
        echo 'GG_MENUBAR Mesajele disponibile nu identifică eroarea de randare.'
        return 3
    fi
    return "$display_rc"
)
