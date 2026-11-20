# Read-only history from the Golden B unified log; call as the logged-in user.
gg_dock_history_decode() {
    /usr/bin/perl -MJSON::PP -e '
        use strict; use warnings;
        my ($wanted,$boot) = @ARGV;
        my (%events,%counts,%uncounted);
        my ($end,$bad,$lost,$wrongboot,$seq,$kept) = (0) x 6;
        # Only print fixed labels and allowlisted values. Mouse event descriptions
        # in particular may contain coordinates or information about other windows.
        sub kind {
            my ($text)=@_;
            return "mouse.enter.add"  if $text =~ /^Adding mouse enter event\b/i;
            return "mouse.leave.add"  if $text =~ /^Adding mouse leave event\b/i;
            return "mouse.enter.handle" if $text =~ /^(?:-\[DockBar )?handleDockEventMouseEnter:/;
            return "mouse.leave.handle" if $text =~ /^(?:-\[DockBar )?handleDockEventMouseLeave:/;
            if ($text =~ /^magnification override\s*:?\s*(begin|release|clear)\b/i) {
                my $label = "magnification.override.".lc($1);
                $label .= " kind=none" if $text =~ /\bkind=none\b/i;
                for my $key ("pref","effective") {
                    $label .= " $key=".lc($1) if $text =~ /\b\Q$key\E\s*(?:=|->)\s*(YES|NO|true|false|on|off|0|1)\b/i;
                }
                return $label;
            }
            if ($text =~ /^(?:magnificationEnabled|magnification[ ._-]*(?:enabled|enable)|magnifyEnabled)\b/i) {
                return "magnification.enabled".($text =~ /[:=]\s*(YES|NO|true|false|on|off|0|1)\b/i ? "=".lc($1) : "");
            }
            if ($text =~ /^SetOrientationPreference\b/) {
                my $label="orientation.set";
                for my $key ("orientation","pinning") {
                    $label .= " $key=".lc($1) if $text =~ /\b\Q$key\E\s*=\s*(left|right|bottom|-?[0-9]{1,3})\b/i;
                }
                return $label;
            }
            return "tracking.update" if $text =~ /^Entering DockBar\.updateDigTrackingRects\b/;
            return "tracking.region.result" if $text =~ /^Resulting digRegion:/;
            return "tracking.ignore.space_spans_displays" if $text =~ /^Ignoring because spacesSpansDisplays\b/;
            return "tracking.ignore.allow_dock_display_switching" if $text =~ /^Ignoring because allowDockDisplaySwitching\b/;
            return "tracking.ignore.orientation_other_than_bottom" if $text =~ /^No computation because barOrientation != bottom\b/;
            return "tracking.refused" if $text =~ /^(?:refused|failed|unable|cannot) (?:to )?(?:add|update|create|install|register) (?:a |the )?(?:mouse )?tracking (?:area|region|rect)\b/i ||
                                         $text =~ /^(?:mouse )?tracking (?:area|region|rect)\b.{0,60}?\b(?:failed|refused|rejected|denied)\b/i;
            return "autohide.mouse_outside_rect" if $text =~ /^Not autohiding; mouse not in rect\b/;
            return "autohide.start" if $text =~ /^Starting autohide\b/;
            return "autohide.no_hide.not_windows_mode" if $text =~ /^Not in windows mode; did NOT hide\b/;
            return "autohide.no_hide.bar_shown" if $text =~ /^Bar window is shown; will NOT hide\b/;
            return "autohide.no_hide.tile_bouncing" if $text =~ /^Tile is bouncing; will NOT hide\b/;
            return "autohide.no_hide.expose" if $text =~ /^In expose mode; did NOT hide\b/;
            for my $state (["pref",qr/^Autohide Pref Value:/],["initial",qr/^Initial value autoHideOn=/],
                           ["off",qr/^Disabling; setting autoHideOn=/],["no_op",qr/^Skipping no-op autohide change; autoHideOn=/]) {
                if ($text =~ $state->[1]) {
                    my $v=$text =~ /[:=]\s*(YES|NO|true|false|on|off|0|1)\b/i ? "=".lc($1) : "";
                    return "autohide.$state->[0]".$v;
                }
            }
            return;
        }
        while (<STDIN>) {
            next if /^\s*$/;
            my $r=eval {decode_json($_)};
            if (ref($r) ne "HASH") { ++$bad; next }
            if (exists $r->{finished}) { $end=1; next }
            if (($r->{eventType}//"") =~ /loss|drop/i) { ++$lost; next }
            my $path=$r->{processImagePath} // $r->{process} // "";
            next unless $path eq "/System/Library/CoreServices/Dock.app/Contents/MacOS/Dock" || $path eq "Dock";
            my $pid=$r->{processID}//$r->{processIdentifier}//"";
            if ($pid !~ /^[1-9][0-9]{0,8}$/) { ++$bad; next }
            next if $wanted ne "all" && $pid ne $wanted;
            my $uuid=$r->{bootUUID}//"";
            if ($boot ne "" && $uuid ne "" && lc($uuid) ne lc($boot)) { ++$wrongboot; next }
            my $k=kind($r->{eventMessage}//"") // kind($r->{formatString}//"");
            next unless defined $k;
            my $ts=$r->{timestamp}//"";
            if ($ts !~ /^\d{4}-\d\d-\d\d[ T](\d\d:\d\d:\d\d(?:\.\d{1,9})?)(?:Z|[-+]\d{2}:?\d{2})$/) { ++$bad; next }
            my $time=$1;
            ++$counts{$pid}{$k};
            # machTimestamp orders records independently of the display timezone.
            my $mach=$r->{machTimestamp}//0;
            $mach=0 unless $mach =~ /^[0-9]{1,19}$/;
            if (++$kept <= 30000) { push @{$events{$pid}}, [$ts,$time,$k,++$seq,$mach] }
            else { ++$uncounted{$pid} }
        }
        for my $pid (sort {$a <=> $b} keys %counts) {
            my $rows=$events{$pid}//[];
            my $all_mach=@$rows && !grep { !$_->[4] } @$rows;
            my @ordered=sort { ($all_mach ? $a->[4] <=> $b->[4] : $a->[0] cmp $b->[0]) || $a->[3] <=> $b->[3] } @$rows;
            my @runs;
            for my $e (@ordered) {
                if (@runs && $runs[-1][2] eq $e->[2]) { $runs[-1][1]=$e->[1]; ++$runs[-1][3] }
                else { push @runs,[$e->[1],$e->[1],$e->[2],1] }
            }
            print "GG_DOCK_HISTORY PID=$pid totaluri: ", join(", ", map {"$_ x$counts{$pid}{$_}"} sort keys %{$counts{$pid}}), "\n";
            my $skipped=@runs>80 ? @runs-80 : 0;
            for (my $i=0;$i<@runs;$i++) {
                if ($skipped && $i==40) { print "GG_DOCK_HISTORY PID=$pid ... $skipped secvente intermediare omise din afisare.\n"; $i+=$skipped }
                my ($first,$last,$what,$n)=@{$runs[$i]};
                printf "GG_DOCK_HISTORY PID=%d %s%s %s x%d\n",$pid,$first,($first eq $last ? "" : "..$last"),$what,$n;
            }
            print "GG_DOCK_HISTORY PID=$pid ",$uncounted{$pid}," evenimente numarate peste limita cronologiei.\n" if $uncounted{$pid};
        }
        if (!$end || $bad || $lost || $wrongboot) {
            print "GG_DOCK_HISTORY Jurnal incomplet: final=$end, inregistrari invalide=$bad, pierderi=$lost, alt boot=$wrongboot.\n";
            exit 3;
        }
        if (!keys %counts) { print "GG_DOCK_HISTORY Niciun eveniment relevant returnat pentru fereastra ceruta.\n"; }
        exit 0;
    ' "$1" "$2"
}

gg_dock_history_window() (
    set +e
    local label=$1 from=$2 through=$3 wanted=$4 boot_id=$5 start end filter term clauses=
    local -a status
    start=$(/bin/date -r "$from" '+%F %T%z') || return 3
    end=$(/bin/date -r "$through" '+%F %T%z') || return 3
    printf 'GG_DOCK_HISTORY %s | %s .. %s | PID=%s\n' "$label" "$start" "$end" "$wanted"
    # Match the stable log terms from the arm64e Dock in Golden 26B131.
    for term in 'Adding mouse' DockEventMouse magnif SetOrientationPreference tracking digRegion \
                'Ignoring because' barOrientation autohid 'NOT hide'; do
        if [[ -n $clauses ]]; then clauses="$clauses OR "; fi
        clauses="$clauses eventMessage CONTAINS[c] \"$term\""
    done
    filter="process == \"Dock\" AND ($clauses)"
    if [[ $wanted != all ]]; then filter="$filter AND processIdentifier == $wanted"; fi
    /usr/bin/perl -e 'alarm 40; exec @ARGV or die $!' /usr/bin/log show --style ndjson --info --debug \
        --start "$start" --end "$end" --predicate "$filter" 2>/dev/null | gg_dock_history_decode "$wanted" "$boot_id"
    status=("${PIPESTATUS[@]}")
    if (( status[0] || status[1] )); then
        printf 'GG_DOCK_HISTORY Verificare incompletă (log=%s, decodor=%s).\n' "${status[0]}" "${status[1]}"
        return 3
    fi
)

gg_dock_history() (
    set +e
    local now boot uuid fixed_start fixed_end from rc=0
    now=$(/bin/date +%s) || return 3
    boot=$(/usr/sbin/sysctl -n kern.boottime | /usr/bin/sed -nE 's/^.*sec = ([0-9]+), usec =.*$/\1/p')
    if [[ ! $boot =~ ^[0-9]+$ || $boot -gt $now ]]; then
        echo 'GG_DOCK_HISTORY Pornirea curentă nu a putut fi datată.'
        return 3
    fi
    uuid=$(/usr/sbin/sysctl -n kern.bootsessionuuid 2>/dev/null) || uuid=
    [[ $uuid =~ ^[[:xdigit:]]{8}(-[[:xdigit:]]{4}){3}-[[:xdigit:]]{12}$ ]] || uuid=
    printf 'GG_DOCK_HISTORY Pornire %s. Numără numai mesajele păstrate în jurnal.\n' "$(/bin/date -r "$boot" '+%F %T%z')"
    fixed_start=$(/bin/date -j -f '%F %T%z' '2026-11-20 13:22:48+0200' +%s) || return 3
    fixed_end=$((fixed_start+13))
    if (( fixed_start >= boot && fixed_end <= now )); then
        gg_dock_history_window 'Proba de mișcare kdnxd7fn' "$fixed_start" "$fixed_end" 5687 "$uuid" || rc=3
    else
        echo 'GG_DOCK_HISTORY Intervalul probei de mișcare nu aparține integral pornirii curente.'
        rc=3
    fi
    from=$(( now-900 > boot ? now-900 : boot ))
    # Preserve the user's orientation test after the timed hover trial even
    # when preparing this diagnostic took longer than the recent window.
    if (( fixed_end >= boot && fixed_end < from && now-fixed_end <= 3600 )); then
        from=$fixed_end
    fi
    gg_dock_history_window 'Activitate recentă (toate instanțele Dock)' "$from" "$now" all "$uuid" || rc=3
    return "$rc"
)
