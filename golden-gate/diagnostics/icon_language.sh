#!/bin/bash
# Source in the console user's Aqua session, then call gg_icon_language.
gg_icon_language() (
    set +e
    set +u
    local uuid boot boot_sec cache output file domain count first ordered locale value i
    uuid=$(/usr/sbin/sysctl -n kern.bootsessionuuid 2>/dev/null)
    [[ $uuid =~ ^[[:xdigit:]]{8}(-[[:xdigit:]]{4}){3}-[[:xdigit:]]{12}$ ]] || uuid=unknown
    boot=$(LC_ALL=C /usr/sbin/sysctl -n kern.boottime 2>/dev/null)
    boot_sec=unknown
    if [[ $boot =~ sec[[:space:]]*=[[:space:]]*([0-9]+) ]]; then boot_sec=${BASH_REMATCH[1]}; fi
    printf 'GG_LANG_BOOT uuid=%s boot_sec=%s\n' "$uuid" "$boot_sec"

    # CFPreferencesCopyValue queries one exact user, host and application;
    # named domains cannot inherit the global AppleLanguages value here.
    # NSLocale also reports the language visible to this fresh Aqua client.
    if output=$(/usr/bin/perl -e 'alarm 8; exec @ARGV or exit 127' /usr/bin/osascript -l JavaScript 2>/dev/null <<'JS'
ObjC.import('Foundation');
ObjC.import('CoreFoundation');
function scalar(v) {
    return typeof v === 'string' && /^[A-Za-z0-9_@=.,+;-]{1,100}$/.test(v) ? v : 'unknown';
}
function languages(v) {
    if (!Array.isArray(v) || !v.length) return ['unknown', 'unknown'];
    const order = v.slice(0, 10).map(scalar);
    return [order[0], order.join(',')];
}
function exact(key, app, host) {
    const ref = $.CFPreferencesCopyValue($(key), app, $.kCFPreferencesCurrentUser, host);
    const object = ObjC.castRefToObject(ref);
    return object.isNil() ? null : ObjC.deepUnwrap(object);
}
function run() {
    const any = $.kCFPreferencesAnyHost, here = $.kCFPreferencesCurrentHost, global = $.kCFPreferencesAnyApplication;
    function globalKey(key) {
        const local = exact(key, global, here);
        return local === null ? exact(key, global, any) : local;
    }
    const order = languages(globalKey('AppleLanguages'));
    const rows = ['GG_LANG_USER source=CFPreferences first=' + order[0] + ' ordered=' + order[1] + ' locale=' + scalar(globalKey('AppleLocale'))];
    const effective = languages(ObjC.deepUnwrap($.NSLocale.preferredLanguages));
    rows.push('GG_LANG_AQUA first=' + effective[0] + ' ordered=' + effective[1] + ' locale=' + scalar(ObjC.unwrap($.NSLocale.currentLocale.localeIdentifier)));
    const domains = ['com.apple.finder','com.apple.IconServices','com.apple.iconservicesagent','com.apple.iconservicesd','com.apple.iconservices.iconservicesagent','com.apple.iconservices.iconservicesd'];
    let count = 0;
    domains.forEach(function(domain) {
        [[any,'any_host'],[here,'current_host']].forEach(function(scope) {
            const langs = exact('AppleLanguages', $(domain), scope[0]), loc = exact('AppleLocale', $(domain), scope[0]);
            if (langs === null && loc === null) return;
            rows.push('GG_LANG_OVERRIDE domain=' + domain + ' scope=' + scope[1] + ' ordered=' + (langs === null ? 'unset' : languages(langs)[1]) + ' locale=' + (loc === null ? 'unset' : scalar(loc)));
            count++;
        });
    });
    rows.push('GG_LANG_OVERRIDE_SCAN source=CFPreferences scopes=any_and_current_host count=' + count);
    return rows.join('\n');
}
JS
    ) && [[ $output == GG_LANG_USER* && $output == *GG_LANG_OVERRIDE_SCAN* ]]; then
        printf '%s\n' "$output"
    else
        # Disk fallback reads only the named persistent domain. ByHost values
        # and NSLocale are unavailable through this fallback.
        disk_prefs() {
            local prefs=$1 length n x
            first=unknown; ordered=unset; locale=unset
            length=$(/usr/bin/plutil -extract AppleLanguages raw -o - "$prefs" 2>/dev/null) || length=
            if [[ $length =~ ^[0-9]{1,5}$ ]]; then
                ordered=
                for ((n=0; n<length && n<10; n++)); do
                    x=$(/usr/bin/plutil -extract "AppleLanguages.$n" raw -o - "$prefs" 2>/dev/null)
                    [[ $x =~ ^[a-zA-Z0-9_-]{1,64}$ ]] || x=unknown
                    [[ $n != 0 ]] || first=$x
                    ordered="${ordered:+$ordered,}$x"
                done
                ordered=${ordered:-unknown}
            fi
            x=$(/usr/bin/plutil -extract AppleLocale raw -o - "$prefs" 2>/dev/null) && {
                if [[ $x =~ ^[a-zA-Z0-9_@=.,+\;-]{1,100}$ ]]; then locale=$x; else locale=unknown; fi
            }
            return 0
        }
        disk_prefs "$HOME/Library/Preferences/.GlobalPreferences.plist"
        printf 'GG_LANG_USER source=plist first=%s ordered=%s locale=%s\n' "$first" "$ordered" "$locale"
        echo 'GG_LANG_AQUA first=unknown ordered=unknown locale=unknown'
        count=0
        for domain in com.apple.finder com.apple.IconServices com.apple.iconservicesagent com.apple.iconservicesd com.apple.iconservices.iconservicesagent com.apple.iconservices.iconservicesd; do
            file="$HOME/Library/Preferences/$domain.plist"
            [[ -f $file && -r $file ]] || continue
            disk_prefs "$file"
            if [[ $ordered != unset || $locale != unset ]]; then
                printf 'GG_LANG_OVERRIDE domain=%s scope=any_host ordered=%s locale=%s\n' "$domain" "$ordered" "$locale"
                ((count++))
            fi
        done
        printf 'GG_LANG_OVERRIDE_SCAN source=readable_plists scopes=any_host_only count=%s\n' "$count"
    fi

    file_state() {
        local p=$1 s
        if [[ -z $p ]]; then echo unknown; return; fi
        if s=$(LC_ALL=C /usr/bin/stat -f '%HT' "$p" 2>&1); then
            if [[ $s != 'Regular File' ]]; then echo other_type
            elif [[ -r $p ]]; then echo present
            else echo unreadable; fi
        elif [[ $s == *'No such file or directory'* ]]; then echo absent
        else echo unreadable; fi
    }
    scalar_key() {
        local x
        if x=$(/usr/bin/plutil -extract "$1" raw -o - "$2" 2>/dev/null); then
            if [[ $x =~ ^[a-zA-Z0-9_.-]{1,64}$ ]]; then printf '%s' "$x"; else printf unknown; fi
        else printf unset; fi
    }
    metadata() {
        local target=$1 p=$2 state lang=unknown build=unknown version=unknown
        state=$(file_state "$p")
        if [[ $state == present ]]; then
            # -lint rejects JSON on some macOS releases; conversion to stdout
            # authenticates the syntax of both plist and JSON without writing.
            if /usr/bin/plutil -convert xml1 -o - "$p" >/dev/null 2>&1; then
                lang=$(scalar_key language "$p"); build=$(scalar_key ProductBuildVersion "$p"); version=$(scalar_key version "$p")
            else state=invalid; fi
        fi
        printf 'GG_LANG_CACHE kind=%s state=%s language=%s build=%s version=%s\n' "$target" "$state" "$lang" "$build" "$version"
    }
    cache=$(/usr/bin/getconf DARWIN_USER_CACHE_DIR 2>/dev/null)
    if [[ $cache =~ ^(/private)?/var/folders/[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+/C/?$ ]]; then
        cache="${cache%/}/com.apple.iconservices"
    else cache=; fi
    metadata user "${cache:+$cache/__cache_info__}"
    metadata common '/Library/Caches/com.apple.iconservices.store/store-info.plist'
    file="${cache:+$cache/store.index}"
    value=$(file_state "$file"); count=unknown
    if [[ $value == present ]]; then
        count=$(/usr/bin/stat -f '%z' "$file" 2>/dev/null)
        [[ $count =~ ^[0-9]+$ ]] || count=unknown
    fi
    printf 'GG_LANG_INDEX state=%s bytes=%s\n' "$value" "$count"
    return 0
)
