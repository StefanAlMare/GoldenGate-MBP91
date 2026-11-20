#!/bin/bash
# Capture one physical Finder gesture with the same NVIDIA device on both screens.
finder_nvidia_route() {
    /usr/bin/perl -e 'alarm 10; exec @ARGV or die $!' /usr/bin/osascript -l JavaScript -e '
        ObjC.import("AppKit"); ObjC.import("CoreGraphics"); ObjC.import("Metal");
        ObjC.bindFunction("object_getClass", ["Class", ["id"]]);
        ObjC.bindFunction("class_getName", ["char *", ["Class"]]);
        ObjC.bindFunction("class_getImageName", ["char *", ["Class"]]);
        const screens = $.NSScreen.screens, rows = [], internal = [], external = [];
        for (let i = 0; i < Number(screens.count); i++) {
            const screen = screens.objectAtIndex(i);
            const id = Number(screen.deviceDescription.objectForKey($("NSScreenNumber")).unsignedIntValue);
            if (!$.CGDisplayIsOnline(id)) continue;
            const device = $.CGDirectDisplayCopyCurrentMetalDevice(id);
            const name = String(ObjC.unwrap(device.name)), reg = Number(device.registryID);
            const cls = $.object_getClass(device);
            const builtin = Boolean($.CGDisplayIsBuiltin(id));
            rows.push((builtin ? "Intern" : "Extern") + " | ID " + id + " | " + name +
                      " | 0x" + reg.toString(16) + " | " + String($.class_getName(cls)) +
                      " | " + String($.class_getImageName(cls)));
            if (name === "NVIDIA GeForce GT 650M" && Number.isSafeInteger(reg) && reg > 0)
                (builtin ? internal : external).push(reg);
        }
        if (!internal.some(id => external.includes(id))) throw Error("Ruta comună GT 650M nu a fost confirmată. " + rows.join("; "));
        rows.sort().join("\n");'
}

finder_nvidia_sample() {
    local role=$1 pid=$2
    if [[ ! $pid =~ ^[0-9]+$ ]]; then echo "$role | PID unic indisponibil."; return; fi
    /usr/bin/perl -e 'alarm 30; exec @ARGV or die $!' /usr/bin/sample "$pid" 12 25 -file /dev/stdout 2>/dev/null |
    /usr/bin/awk -v role="$role" -v pid="$pid" '
        /^Call graph:/ { graph=1; print "GG_STACK " role }
        /^(Total number in stack|Sort by top of stack|Binary Images:)/ && graph {
            print "Total number in stack"; print "GG_ENDSTACK " role; graph=0; complete=1
        }
        graph { print }
        /^Binary Images:/ { images=1 }
        images && /\/(libmetal-framebuffer[[:alnum:]_-]*\.dylib|GeForceMTLDriver|AppleIntelHD4000GraphicsMTLDriver|libhao\.dylib)[[:space:]]*$/ {
            seen[$NF]=1
        }
        END {
            if (graph) print "GG_ENDSTACK " role;
            print role " PID " pid " | stivă completă: " (complete ? "da" : "neobservată");
            if (images) { for (name in seen) print role " PID " pid " | imagine mapată: " name }
        }'
    local -a codes=("${PIPESTATUS[@]}")
    if (( codes[0] || codes[1] )); then echo "$role PID $pid | captură indisponibilă sau parțială (sample=${codes[0]}, citire=${codes[1]})."; fi
}

finder_nvidia_windows() {
    /usr/bin/perl -e 'alarm 19; exec @ARGV or die $!' /usr/bin/osascript -l JavaScript -e '
        ObjC.import("AppKit"); ObjC.import("CoreGraphics");
        function emit(text) {
            $.NSFileHandle.fileHandleWithStandardOutput.writeData($(text+"\n").dataUsingEncoding($.NSUTF8StringEncoding));
        }
        function run(argv) {
            const pid=Number(argv[0]);
            function ids() {
                const all=ObjC.deepUnwrap($.CGWindowListCopyWindowInfo(17,0));
                if (!Array.isArray(all) || !all.length) return null;
                return all.filter(w => Number(w.kCGWindowOwnerPID) === pid && Number(w.kCGWindowLayer) === 0)
                          .map(w => Number(w.kCGWindowNumber)).sort((a,b) => a-b).join(",");
            }
            let last=ids();
            try {
                const active=$.NSWorkspace.sharedWorkspace.frontmostApplication;
                emit("Finder în prim-plan la semnal | "+(Number(active.processIdentifier)===pid ? "da" : "nu"));
            } catch (e) { emit("Finder în prim-plan la semnal | neobservat"); }
            emit("ACUM — cu Finder activ pe MacBook, apasă ⌘N o singură dată.");
            const start=Date.now();
            emit("Ferestre Finder la semnal | "+(last===null ? "inventar indisponibil" : last || "niciuna vizibilă"));
            for (let i=0; i<20; i++) {
                $.NSThread.sleepForTimeInterval(0.5);
                const current=ids();
                if (current!==last) emit("La "+((Date.now()-start)/1000).toFixed(1)+" s de la semnal | ferestre Finder vizibile: "+(current===null ? "inventar indisponibil" : current || "niciuna"));
                last=current;
            }
        }' "$1"
}

finder_nvidia() (
    local before after finder agent window_server start end
    [[ ! -t 1 ]] || stty onlcr 2>/dev/null || true
    before=$(finder_nvidia_route) || { echo 'Captura nu a început. Verifică dacă ambele ecrane sunt active pe GT 650M.'; exit 3; }
    printf 'Ecrane înainte de gest\n%s\n' "$before"
    finder=$(/usr/bin/pgrep -u "$uid" -x Finder)
    [[ $finder =~ ^[0-9]+$ ]] || { echo 'Finder fără PID unic.'; exit 3; }
    agent=$(/usr/bin/pgrep -u "$uid" -x iconservicesagent)
    window_server=$(/usr/bin/pgrep -x WindowServer)
    echo 'Activează Finder pe MacBook. Semnalul pentru ⌘N apare în cinci secunde.'
    /bin/sleep 5
    start=$(/bin/date '+%Y-%m-%d %H:%M:%S%z')
    /bin/ps -p "$finder" -o pid,%cpu,state,etime,comm
    exec 3< <(finder_nvidia_sample Finder "$finder")
    exec 4< <(finder_nvidia_sample iconservicesagent "$agent")
    exec 5< <(finder_nvidia_sample WindowServer "$window_server")
    finder_nvidia_windows "$finder" || echo 'Observația ferestrelor a fost incompletă.'
    end=$(/bin/date '+%Y-%m-%d %H:%M:%S%z')
    /bin/ps -p "$finder" -o pid,%cpu,state,etime,comm
    after=$(finder_nvidia_route) || after=
    printf 'Ecrane după gest\n%s\n' "${after:-Rută indisponibilă}"
    if [[ $before != "$after" ]]; then echo 'Ruta diferă între capturi. Comparația pe NVIDIA este neconcludentă.'; fi
    /bin/cat <&3
    /bin/cat <&4
    /bin/cat <&5
    [[ $(/usr/bin/pgrep -u "$uid" -x Finder) == "$finder" ]] || echo 'PID Finder schimbat în timpul probei.'
    graphics_log_reference "$start" "$end"
)
