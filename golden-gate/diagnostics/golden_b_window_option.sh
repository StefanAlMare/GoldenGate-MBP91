# Read the Option state in isolated processes, keeping the real WindowManager running.
gg_window_option() (
    umask 077
    local dir=$1 uid=21acabfab6cc3ec9a3cf6d4d6b637f5a
    local old=a0bb9d28b8c3b030cbebd2b995d4470269e7c3955ff208b2f7fc5a1ded520a1f
    local new=cd2a77b0e61af60abd4c23e860809aad0af4837dc81886a600831379c2546b3f
    local installed="/usr/lib/hao/if/$uid" isolated rc
    local -a arm=(/usr/libexec/hao -- "$dir/window-option-arm64")
    gg_opt_hash() { /usr/bin/shasum -a 256 "$1" | /usr/bin/awk '{print $1}'; }
    gg_opt_run() { /usr/bin/perl -e 'alarm 12; exec @ARGV or die $!' "$@"; }
    gg_opt_trial() {
        local architecture=$1 out status count high
        shift
        out=$(gg_opt_run "$@") && status=0 || status=$?
        printf '%s\n' "$out"
        [[ "$out" =~ ^GG_WINDOW_OPTION\ arch=$architecture\ option=liber\ public=([4-6])\ octet_diferit=0\ numai_sus=([0-6])$ ]] || return 2
        count=${BASH_REMATCH[1]}; high=${BASH_REMATCH[2]}
        if (( status == 0 && high == 0 )); then return 0; fi
        if (( status == 1 && high == count )); then return 1; fi
        return 2
    }
    [[ -d "$dir" && ! -L "$dir" && -x "$dir/window-option-x86_64" &&
       -x "$dir/window-option-arm64" && -x /usr/libexec/hao ]] || return 2
    if [[ $(gg_opt_run "$dir/window-option-x86_64" --uuid) != "$uid" ||
          ! -f "$installed" || -L "$installed" || $(gg_opt_hash "$installed") != "$old" ||
          ! -f "$dir/skylight-option" || $(gg_opt_hash "$dir/skylight-option") != "$new" ]]; then
        echo 'GG_WINDOW_OPTION neconcludent=SkyLight_sau_unitate_diferita'; return 2
    fi
    echo 'GG_WINDOW_OPTION Control Intel, apoi HAO din sesiunea curentă.'
    gg_opt_trial x86_64 "$dir/window-option-x86_64" || return 2
    unset HAO_IF_DIR
    gg_opt_trial arm64 "${arm[@]}" && rc=0 || rc=$?
    if (( rc != 1 )); then
        if (( rc == 0 )); then echo 'GG_WINDOW_OPTION verdict=defect_nereprodus'; fi
        return 2
    fi
    isolated=$(/usr/bin/mktemp -d "$dir/option-if.XXXXXXXX") || return 2
    echo 'GG_WINDOW_OPTION HAO cu directorul de probă gol.'
    gg_opt_trial arm64 /usr/bin/env HAO_IF_DIR="$isolated" "${arm[@]}" && rc=0 || rc=$?
    (( rc == 1 )) || return 2
    /bin/cp "$installed" "$isolated/$uid" || return 2
    echo 'GG_WINDOW_OPTION HAO cu unitatea Dock actuală în același director de probă.'
    gg_opt_trial arm64 /usr/bin/env HAO_IF_DIR="$isolated" "${arm[@]}" && rc=0 || rc=$?
    (( rc == 1 )) || return 2
    /bin/cp "$dir/skylight-option" "$isolated/$uid" || return 2
    echo 'GG_WINDOW_OPTION HAO cu normalizarea Option, numai în procesul de probă.'
    gg_opt_trial arm64 /usr/bin/env HAO_IF_DIR="$isolated" "${arm[@]}" || return 2
    echo 'GG_WINDOW_OPTION HAO din nou cu unitatea de sistem inițială.'
    gg_opt_trial arm64 "${arm[@]}" && rc=0 || rc=$?
    (( rc == 1 )) || return 2
    echo 'GG_WINDOW_OPTION verdict=normalizare_confirmata'
)
