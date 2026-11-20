# Messages emitted by the Battery pane in Golden 26B131. Export only counts
# and query status. An omitted message is different from an explicit zero.
gg_battery_counts() {
    /usr/bin/arch -x86_64 /usr/bin/ruby --disable-gems -EUTF-8:UTF-8 -rjson -e '# encoding: UTF-8
        series = {
            "uisoc levels" => "24h nivel baterie", "screen on times" => "24h ecran activ",
            "10d usage times" => "10z ecran activ", "10d uisoc" => "10z utilizare energie"
        }
        STDIN.each_line do |line|
            next unless line.lstrip.start_with?("{")
            begin
                row = JSON.parse(line)
            rescue JSON::ParserError
                warn "GG_ISTORIC Înregistrare ilizibilă în jurnal."
                exit 3
            end
            msg = row["eventMessage"].to_s.strip
            case msg
            when /\Agot (\d+|<private>) (uisoc levels|screen on times|10d usage times|10d uisoc)\z/i
                count, name = $1, $2.downcase
                result = "#{series.fetch(name)} | intrări=#{count == "<private>" ? "indisponibil" : count}"
            when /\Aquery failed: empty payload/i then result = "răspuns gol"
            when /find response key in query/i then result = "cheie din răspuns fără configurație în cerere"
            when /\Ano response: retrying query/i then result = "fără răspuns, cerere repetată"
            else next
            end
            puts "GG_ISTORIC #{ARGV.first} | #{row["timestamp"]} | PID=#{row["processID"]} | #{result}"
        end
    ' "$1"
}

gg_battery_history() {
    local window=$1
    shift
    local predicate='(subsystem == "com.apple.batteryui" OR process == "PowerPreferences") AND
        (eventMessage CONTAINS[c] "UISoC levels" OR eventMessage CONTAINS[c] "screen on times"
        OR eventMessage CONTAINS[c] "10d usage times" OR eventMessage CONTAINS[c] "10d UISoC"
        OR eventMessage BEGINSWITH[c] "query failed: empty payload"
        OR eventMessage CONTAINS[c] "find response key in query"
        OR eventMessage BEGINSWITH[c] "no response: retrying query")'
    /usr/bin/perl -e 'alarm 55; exec @ARGV or die $!' /usr/bin/log "$@" --style ndjson \
        --predicate "$predicate" 2>"$t/$window.err" | gg_battery_counts "$window" >"$t/$window.counts"
    local statuses=("${PIPESTATUS[@]}")
    /bin/cat "$t/$window.counts"
    if (( statuses[0] != 0 || statuses[1] != 0 )); then
        echo "GG_ISTORIC $window | citire incompletă (log=${statuses[0]}, filtru=${statuses[1]})."
        /usr/bin/head -n 1 "$t/$window.err"
        return 3
    elif [[ ! -s "$t/$window.counts" ]]; then
        echo "GG_ISTORIC $window | niciun contor sau mesaj despre răspuns în jurnalul accesibil."
    fi
}
