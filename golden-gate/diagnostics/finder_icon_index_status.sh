#!/bin/bash
# Called in the existing Aqua session, after finder_reference.sh has been sourced.
finder_icon_index_status() (
    export LC_ALL=C
    limited() { /usr/bin/perl -e 'alarm shift; exec @ARGV or exit 127' "$@"; }
    local volume status rc state marker root_state=unknown app bundle real_id matches metadata
    local query_state=ok found visible indexed_id line
    for volume in / /System/Volumes/Data; do
        status=$(limited 4 /usr/bin/mdutil -s "$volume" 2>&1); rc=$?
        case "$status" in
            *"Spotlight server is disabled"*) state=server_disabled ;;
            *"Indexing and searching disabled"*) state=search_and_index_disabled ;;
            *"Indexing disabled"*) state=indexing_disabled ;;
            *"Indexing enabled"*) state=indexing_enabled ;;
            *) state=unknown ;;
        esac
        if ((rc)); then state=unavailable; fi
        [[ $volume != / ]] || root_state=$state
        marker=not_seen
        if [[ -e "${volume%/}/.metadata_never_index" ]]; then marker=present; fi
        status=${status//$'\n'/ }
        printf 'GG_SPOTLIGHT_VOLUME volume=%s state=%s rc=%d metadata_never_index=%s detail=%.180s\n' \
            "$volume" "$state" "$rc" "$marker" "$status"
    done

    local query='(kMDItemCFBundleIdentifier == "com.apple.systempreferences" || kMDItemCFBundleIdentifier == "com.apple.ActivityMonitor" || kMDItemCFBundleIdentifier == "com.apple.calculator")'
    matches=$(limited 6 /usr/bin/mdfind -onlyin /System/Applications "$query" 2>&1); rc=$?
    if ((rc)); then query_state=unavailable; fi
    # mdfind can return success while its server is disabled. An exact result
    # is still valuable, but silence in that case cannot establish a miss.
    while IFS= read -r line; do
        if [[ -n $line && $line != /* ]]; then query_state=diagnostic; fi
    done <<< "$matches"
    printf 'GG_SPOTLIGHT_QUERY scope=/System/Applications state=%s rc=%d\n' "$query_state" "$rc"
    for app in '/System/Applications/System Settings.app' '/System/Applications/Utilities/Activity Monitor.app' '/System/Applications/Calculator.app'; do
        case "$app" in
            */'System Settings.app') bundle=com.apple.systempreferences ;;
            */'Activity Monitor.app') bundle=com.apple.ActivityMonitor ;;
            */Calculator.app) bundle=com.apple.calculator ;;
        esac
        real_id=$(/usr/bin/plutil -extract CFBundleIdentifier raw -o - "$app/Contents/Info.plist" 2>/dev/null)
        if [[ $real_id != "$bundle" ]]; then
            printf 'GG_SPOTLIGHT_APP bundle=%s file=unconfirmed search=unobserved\n' "$bundle"
            continue
        fi
        found=no_match
        if [[ $query_state != ok ]]; then found=unobserved
        elif [[ $root_state == server_disabled || $root_state == search_and_index_disabled ]]; then found=search_disabled
        elif [[ $root_state == indexing_disabled ]]; then found=no_match_indexing_disabled
        fi
        if [[ $query_state == ok ]]; then
            while IFS= read -r line; do
                if [[ $line == "$app" || ( $line == /* && $line -ef $app ) ]]; then found=hit; break; fi
            done <<< "$matches"
        fi
        metadata=$(limited 3 /usr/bin/mdls -name kMDItemCFBundleIdentifier -name kMDItemFSInvisible "$app" 2>/dev/null); rc=$?
        indexed_id=unavailable
        visible=unknown
        if ((rc==0)); then
            if [[ $metadata == *"\"$bundle\""* ]]; then indexed_id=matches_file; else indexed_id=not_confirmed; fi
            if [[ $metadata =~ kMDItemFSInvisible[[:blank:]]*=[[:blank:]]*0 ]]; then visible=yes
            elif [[ $metadata =~ kMDItemFSInvisible[[:blank:]]*=[[:blank:]]*1 ]]; then visible=no; fi
        fi
        printf 'GG_SPOTLIGHT_APP bundle=%s file=confirmed search=%s indexed_bundle_id=%s fs_visible=%s mdls_rc=%d\n' \
            "$bundle" "$found" "$indexed_id" "$visible" "$rc"
    done
    finder_reference_cache | while IFS= read -r line; do printf 'GG_ICONS_CACHE %s\n' "$line"; done
)
