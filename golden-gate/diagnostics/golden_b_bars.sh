# Sourced by the root controller after it has verified the Golden B receipt.
gg_bar_job() {
    local name=$1 file=$2 detail path program label state p executable
    executable="/System/Library/CoreServices/$name.app/Contents/MacOS/$name"
    path="/System/Library/LaunchAgents/com.apple.$file.plist"
    label=$(/usr/bin/plutil -extract Label raw -o - "$path" 2>/dev/null) || return 2
    case "$name/$label" in
        Dock/com.apple.Dock.agent|ControlCenter/com.apple.controlcenter|SystemUIServer/com.apple.SystemUIServer.agent|MenuBarAgent/com.apple.MenuBarAgent|Finder/com.apple.Finder) ;;
        *) return 2 ;;
    esac
    [[ $(/usr/bin/plutil -extract Program raw -o - "$path") == "$executable" ]] || return 2
    bar_target="gui/501/$label"
    detail=$(bounded 4 /bin/launchctl print "$bar_target" 2>/dev/null) || return 3
    [[ $(field path) == "$path" && $(field type) == LaunchAgent && $(field program) == "$executable" ]] || return 2
    p=$(field pid)
    [[ -n $p ]] || return 4
    [[ $p =~ ^[1-9][0-9]*$ && $(/bin/ps -p "$p" -o uid= | /usr/bin/awk '{print $1}') == 501 ]] || return 2
    program=$(image_path "$p" 2>/dev/null) && [[ $program -ef $executable ]] || return 2
    bar_pid=$p
}

gg_bars_session() {
    local live path
    [[ -L $lock && $(/usr/bin/readlink "$lock") == "$t" && $(get result) == kept && ! -e $t/undo ]] &&
        root_gate && live=$(registered_pid) && [[ $live == "$agent_pid" ]] &&
        path=$(image_path "$live") && [[ $path -ef "$agent_path" ]] &&
        gg_bar_job Finder Finder && [[ $bar_pid == "$finder_pid" ]]
}

gg_bar_refresh_one() {
    local name=$1 file=$2 old=$3 n rc kicked=0
    gg_bars_session || return 7
    gg_bar_job "$name" "$file" || { echo "GG_BAR owner=$name state=identity_changed"; return 2; }
    if [[ $bar_pid == "$old" ]]; then
        # Ordinary SIGTERM from the session owner, after verifying the live image.
        # The user's normal launchd job supervises the replacement.
        if ! /usr/bin/sudo -n -H -u '#501' -- /bin/kill -TERM "$old"; then
            gg_bar_job "$name" "$file" && [[ $bar_pid != "$old" ]] ||
                { echo "GG_BAR owner=$name state=termination_unconfirmed old=$old"; return 2; }
        fi
    else
        echo "GG_BAR owner=$name state=already_relaunched old=$old new=$bar_pid"
        return 0
    fi
    for ((n=0;n<30;n++)); do
        gg_bar_job "$name" "$file"; rc=$?
        if ((rc==0)) && [[ $bar_pid != "$old" ]]; then
            echo "GG_BAR owner=$name state=relaunched old=$old new=$bar_pid"
            return 0
        fi
        if ((rc==4 && n>=5 && !kicked)); then
            # A clean exit can leave a demand-started job registered but idle.
            # Plain kickstart starts it only if needed. Never terminate twice.
            gg_bars_session || return 7
            if gg_bar_job "$name" "$file"; then continue; else rc=$?; fi
            if ((rc==4)); then
                kicked=1
                bounded 8 /bin/launchctl kickstart "$bar_target" ||
                    echo "GG_BAR owner=$name state=start_request_failed"
            fi
        fi
        /bin/sleep 0.4
    done
    echo "GG_BAR owner=$name state=relaunch_unconfirmed old=$old"
    return 2
}

gg_refresh_bars() (
    local t=${t:-} bar_pid= bar_target= agent_pid agent_path finder_pid i rc failed=0
    local names=(Dock ControlCenter SystemUIServer MenuBarAgent)
    local files=(Dock controlcenter SystemUIServer MenuBarAgent) original=()
    [[ -n $t && $(get result) == kept && ! -e $t/undo ]] ||
        { echo 'GG_BARS Agentul Intel păstrat în această sesiune nu este confirmat.'; return 3; }
    agent_pid=$(get ready)
    agent_path=$(get donor)
    gg_bar_job Finder Finder || { echo 'GG_BARS Procesul Finder nu a fost confirmat.'; return 3; }
    finder_pid=$bar_pid
    gg_bars_session && [[ $(bounded 8 /bin/launchctl asuser 501 /usr/bin/sudo -n -H -u '#501' -- /bin/launchctl managername) == Aqua ]] ||
        { echo 'GG_BARS Sesiunea Aqua sau procesul IconServices Intel s-a schimbat.'; return 3; }
    # Advisory flock survives the child through this shared open-file description
    # and is released by the kernel even if the SSH client disconnects.
    exec 8<"$t/ready" || return 3
    /usr/bin/perl -MFcntl=:flock -e 'open my $f, "<&=8" or exit 2; exit(flock($f, LOCK_EX|LOCK_NB) ? 0 : 1)' ||
        { echo 'GG_BARS O reîmprospătare este deja în curs.'; return 3; }
    echo "GG_BARS start finder_pid=$finder_pid agent_intel_pid=$agent_pid"
    for ((i=0;i<${#names[@]};i++)); do
        if gg_bar_job "${names[i]}" "${files[i]}"; then
            original[i]=$bar_pid
        else
            rc=$?; original[i]=
            echo "GG_BAR owner=${names[i]} state=skipped registration_rc=$rc"
            if [[ ${names[i]} != MenuBarAgent || $rc == 2 ]]; then failed=1; fi
        fi
    done
    for ((i=0;i<${#names[@]};i++)); do
        [[ -n ${original[i]} ]] || continue
        if gg_bar_refresh_one "${names[i]}" "${files[i]}" "${original[i]}"; then continue; else rc=$?; fi
        failed=1
        if ((rc==7)); then break; fi
    done
    if ! gg_bars_session; then echo 'GG_BARS Sesiunea, Finder sau agentul Intel s-a schimbat.'; return 3; fi
    echo "GG_BARS final finder_pid=$finder_pid agent_intel_pid=$agent_pid incomplete=$failed"
    ((failed==0)) || return 3
)
