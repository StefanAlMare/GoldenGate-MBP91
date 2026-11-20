# Compare the private button-state call used by Dock against the public CG API.
# All HAO options are scoped to a child process. The caller owns the temporary
# directory and has already checked the Mac, build, login and Golden B volume.
gg_dock_button() (
    umask 077
    local dir=$1 uuid expected=21acabfab6cc3ec9a3cf6d4d6b637f5a
    local digest=a0bb9d28b8c3b030cbebd2b995d4470269e7c3955ff208b2f7fc5a1ded520a1f
    local native_rc baseline_rc empty_rc corrected_rc repeat_rc
    [[ ! -L "$dir" && -d "$dir" && -x "$dir/dock-button-x86_64" &&
        -x "$dir/dock-button-arm64" && -x /usr/libexec/hao ]] || return 2
    gg_button_run() { /usr/bin/perl -e 'alarm 9; exec @ARGV or die $!' "$@"; }
    gg_button_trial() {
        local arch=$1 out rc released higher
        shift
        out=$(gg_button_run "$@") && rc=0 || rc=$?
        printf '%s\n' "$out"
        [[ "$out" =~ ^GG_BUTTON\ arch=$arch\ released=([4-6])\ low_byte_pressed=0\ false_pressed=([0-6])$ ]] || return 2
        released=${BASH_REMATCH[1]}
        higher=${BASH_REMATCH[2]}
        if (( rc == 0 && higher == 0 )); then return 0; fi
        if (( rc == 1 && higher == released )); then return 1; fi
        return 2
    }
    uuid=$(gg_button_run "$dir/dock-button-x86_64" --uuid) || {
        echo 'GG_BUTTON Neconcludent: implementarea SkyLight nu a putut fi identificată.'; return 2;
    }
    [[ "$uuid" == "$expected" && -f "$dir/$expected" &&
        $(/usr/bin/shasum -a 256 "$dir/$expected" | /usr/bin/awk '{print $1}') == "$digest" ]] || {
        echo 'GG_BUTTON Neconcludent: imaginea SkyLight sau descrierea apelului diferă.'; return 2;
    }
    echo "GG_BUTTON SkyLight Intel $uuid. Control nativ."
    gg_button_trial x86_64 "$dir/dock-button-x86_64" && native_rc=0 || native_rc=$?
    if (( native_rc != 0 )); then
        echo 'GG_BUTTON Neconcludent: controlul nativ nu a confirmat un ecran și butonul stâng liber.'
        return 2
    fi
    unset HAO_IF_DIR
    echo 'GG_BUTTON ARM înainte de corecție.'
    gg_button_trial arm64 /usr/libexec/hao -- "$dir/dock-button-arm64" && baseline_rc=0 || baseline_rc=$?
    if (( baseline_rc == 0 )); then
        echo 'GG_BUTTON Apelul ARM inițial a indicat corect butonul liber. Defectul investigat nu s-a reprodus.'
        return 0
    fi
    if (( baseline_rc != 1 )); then
        echo "GG_BUTTON Neconcludent: proba inițială ARM a ieșit cu $baseline_rc."
        return 2
    fi
    local unitdir
    unitdir=$(/usr/bin/mktemp -d "$dir/button-if.XXXXXXXX") || return 2
    # HAO_IF_DIR replaces the system search path. Keep that choice identical
    # when comparing the empty directory with the directory containing the unit.
    echo 'GG_BUTTON ARM cu directorul de probă gol.'
    gg_button_trial arm64 /usr/bin/env HAO_IF_DIR="$unitdir" /usr/libexec/hao -- "$dir/dock-button-arm64" &&
        empty_rc=0 || empty_rc=$?
    if (( empty_rc != 1 )); then
        echo "GG_BUTTON Neconcludent: schimbarea directorului singură a modificat rezultatul (cod=$empty_rc)."
        return 2
    fi
    /bin/cp "$dir/$expected" "$unitdir/$expected" || return 2
    echo 'GG_BUTTON ARM cu normalizarea rezultatului, doar în procesul de test.'
    gg_button_trial arm64 /usr/bin/env HAO_IF_DIR="$unitdir" /usr/libexec/hao -- "$dir/dock-button-arm64" &&
        corrected_rc=0 || corrected_rc=$?
    echo 'GG_BUTTON ARM repetat cu configurația inițială.'
    gg_button_trial arm64 /usr/libexec/hao -- "$dir/dock-button-arm64" && repeat_rc=0 || repeat_rc=$?
    if (( corrected_rc == 0 && repeat_rc == 1 )); then
        echo 'GG_BUTTON Buton raportat fals apăsat înainte, liber cu descrierea apelului, fals apăsat din nou după retragere.'
        return 0
    fi
    echo "GG_BUTTON Neconcludent: cu normalizare=$corrected_rc, repetare inițială=$repeat_rc."
    return 2
)
