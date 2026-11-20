#!/bin/bash
# Emit only classified events and timestamps in the interval of the icon requests.
graphics_log_reference() {
    local start=$1 end=$2 predicate
    local -a status
    predicate='(process IN {"WindowServer","Finder","iconservicesagent","iconservicesd"} OR process CONTAINS[c] "compiler") AND (messageType IN {"error","fault"} OR eventMessage CONTAINS[c] "rejected" OR eventMessage CONTAINS[c] "4097" OR eventMessage CONTAINS[c] "fail" OR eventMessage CONTAINS[c] "error" OR eventMessage CONTAINS[c] "air.render_target" OR eventMessage CONTAINS[c] "symbol not found" OR eventMessage CONTAINS[c] "library not loaded")'
    if [[ ${3:-} == bars ]]; then
        predicate=${predicate/WindowServer/WindowServer\",\"Dock\",\"ControlCenter\",\"SystemUIServer\",\"MenuBarAgent}
    fi
    printf 'Jurnal comun pentru Finder, agenți și grafică, %s .. %s\n' "$start" "$end"
    /usr/bin/perl -e 'alarm 50; exec @ARGV or die $!' /usr/bin/log show --style ndjson --info --debug \
        --start "$start" --end "$end" --predicate "$predicate" |
    /usr/bin/perl -MJSON::PP -e '
        use strict; use warnings;
        my (%groups, $end, $bad, $lost, $read);
        while (<STDIN>) {
            next if /^\s*$/;
            my $r = eval {decode_json($_)};
            if (ref($r) ne "HASH") { ++$bad; next }
            if (exists $r->{finished}) { $end = 1; next }
            if (($r->{eventType}//"") =~ /loss|dropped/i) { ++$lost; next }
            ++$read;
            my $proc = $r->{processImagePath} // $r->{process} // "";
            $proc =~ s{.*/}{};
            my $gpu_compiler = $proc =~ /(?:metal|mtl|gpu|air|geforce|nvda).*compil|compil.*(?:metal|gpu)/i;
            my $bar = $proc =~ /^(?:Dock|ControlCenter|SystemUIServer|MenuBarAgent)$/;
            next unless $bar || $gpu_compiler || $proc =~ /^(?:Finder|WindowServer|iconservicesagent|iconservicesd)$/;
            my $pid = $r->{processID} // "";
            $pid = "?" unless $pid =~ /^\d+$/;
            my $sender = $r->{senderImagePath} // "";
            $sender =~ s{.*/}{};
            my $msg = $r->{eventMessage} // "";
            my $error = ($r->{messageType} // "") =~ /^(?:error|fault)$/i ||
                        $msg =~ /fail|error|unhandled|unsupported|could not|unable|reject|not found|not loaded|crash|exception/i;
            my $family;
            if ($bar && $error && ($sender =~ /IconServices/i || $msg =~ /com\.apple\.iconservices/i || ($r->{subsystem}//"") =~ /iconservices/i)) {
                $family = "pictograme în bară";
            } elsif ($msg =~ /unhandled metadata type\s*:\s*air\.render_target\b/i) {
                $family = "compilare, air.render_target respins";
            } elsif ($error && ("$sender $msg" =~ /\blibhao(?:\.dylib)?\b|\bHaoExec\b/i ||
                     $sender =~ /^(?:dyld|libdyld\.dylib)$/i || $msg =~ /library not loaded|symbol not found/i)) {
                $family = "încărcare sau runtime";
            } elsif ($proc =~ /^iconservices(?:agent|d)$/ && $msg =~ /rejected by the listener|listener rejected|rejected peer/i) {
                $family = "refuz XPC al agentului, client neatribuit";
            } elsif ($proc eq "Finder" && $msg =~ /failed to generate image|IconServices|com\.apple\.iconservices/i && $error) {
                $family = "Finder, pictograme";
            } elsif ($proc eq "Finder" && $sender =~ /IconServices/i && $error) {
                $family = "Finder, pictograme";
            } elsif ($error && ($gpu_compiler || "$sender $msg" =~ /CoreDisplay|framebuffer|Metal|RenderBox|pipeline|shader|NVDA|GeForce|GPUCompiler|GPU Restart/i)) {
                $family = $gpu_compiler ? "compilator GPU, client neatribuit" : "eroare grafică";
            } else { next }
            my $emitter = $sender =~ /^(CoreDisplay|IconServices|libxpc\.dylib|libhao\.dylib|HaoExec|dyld|libdyld\.dylib|Metal|RenderBox|GPUCompiler|SkyLight|WindowServer|Finder)$/i
                          ? $1 : "alt emitent";
            my ($code) = $msg =~ /\b((?:NSCocoaErrorDomain|NSOSStatusErrorDomain|NSPOSIXErrorDomain|MTLCommandBufferErrorDomain|MTLLibraryErrorDomain)\s+Code=-?\d{1,10})\b/i;
            my $source = "$sender $msg";
            my $nv = $source =~ /NVIDIA|GeForce|\bNVDA/i;
            my $ig = $source =~ /\bIntel|AppleIntel/i;
            my $brand = $nv && $ig ? "Intel și NVIDIA menționate" : $nv ? "NVIDIA menționată" : $ig ? "Intel menționată" : ();
            my $who = $gpu_compiler ? "serviciu compilator GPU" : $proc;
            my $key = join(" | ", "$who [$pid]", $family, $emitter, grep {defined} ($code,$brand));
            my $time = $r->{timestamp} // "";
            $time = $time =~ /^\d{4}-\d\d-\d\d[ T](\d\d:\d\d:\d\d(?:\.\d+)?)(?:Z|[-+]\d\d:?\d\d)$/ ? $1 : "?";
            my $g = $groups{$key} //= [0,$time,$time];
            ++$g->[0]; $g->[2] = $time;
        }
        my @sorted = sort { $groups{$b}->[0] <=> $groups{$a}->[0] || $a cmp $b } keys %groups;
        for my $key (@sorted[0..(@sorted > 24 ? 23 : $#sorted)]) {
            printf "  %s | %d | %s .. %s\n", $key, @{$groups{$key}};
        }
        print "Alte grupe omise: ", scalar(@sorted)-24, "\n" if @sorted > 24;
        print "Rezumate din jurnal: ",0+($read//0)," înregistrări selectate, ",scalar(@sorted)," grupe clasificate.\n";
        if (!$end || $bad || $lost) {
            printf "Citire incompletă: marcaj final=%s, înregistrări invalide=%d, semnale de pierdere=%d.\n",$end ? "da" : "absent",$bad//0,$lost//0;
            exit 3;
        }
    '
    status=("${PIPESTATUS[@]}")
    if (( status[0] || status[1] )); then
        printf 'Jurnal parțial sau indisponibil (log=%s, decodor=%s).\n' "${status[0]}" "${status[1]}"
        return 3
    fi
}
