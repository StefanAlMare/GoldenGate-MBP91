#!/bin/bash
# Read-only stdin payload for both Golden and Tahoe on the MacBookPro9,1.
display_reference() (
set -u
model=$(/usr/sbin/sysctl -n hw.model)
version=$(/usr/bin/sw_vers -productVersion)
build=$(/usr/bin/sw_vers -buildVersion)
printf 'Ecrane — %s, macOS %s (%s), %s\n' "$model" "$version" "$build" "$(/bin/date '+%Y-%m-%d %H:%M:%S %z')"
if [[ $model != MacBookPro9,1 || ( $build != 26B131 && ( $version != 26.* || $build != 25* ) ) ]]; then
    echo 'Acest reper se colectează pe MacBookPro9,1 cu Tahoe 26.x sau Golden 26B131.'
    exit 2
fi

# The SDK specifies that this API returns the Metal device driving the given
# display at query time. An application may submit other work to another GPU.
map=$(/usr/bin/perl -e 'alarm 12; exec @ARGV or die $!' /usr/bin/osascript -l JavaScript -e '
    ObjC.import("AppKit"); ObjC.import("CoreGraphics"); ObjC.import("Metal");
    const screens=$.NSScreen.screens, rows=[], found=new Set();
    function add(id,title) {
        if (!id || found.has(id) || !$.CGDisplayIsOnline(id)) return;
        found.add(id);
        let gpu="", reg="";
        try {
            const dev=$.CGDirectDisplayCopyCurrentMetalDevice(id);
            gpu=String(ObjC.unwrap(dev.name)||"");
            const num=Number(dev.registryID);
            if (Number.isSafeInteger(num) && num>0) reg=" | MTL registry ID 0x"+num.toString(16);
        } catch (e) {}
        const kind=$.CGDisplayIsBuiltin(id) ? "intern" : "extern";
        const safe=String(title || "nume indisponibil").replace(/[\x00-\x1f\x7f]/g," ").slice(0,96);
        const mirror=$.CGDisplayMirrorsDisplay(id);
        rows.push("CoreGraphics | "+kind+" | "+safe+" | ID "+id+" | "+
            $.CGDisplayPixelsWide(id)+" × "+$.CGDisplayPixelsHigh(id)+" | GPU "+(gpu||"indisponibil")+
            reg+(mirror ? " | oglindește ID "+mirror : ""));
    }
    for (let i=0;i<Number(screens.count);i++) {
        const s=screens.objectAtIndex(i);
        const id=Number(s.deviceDescription.objectForKey($("NSScreenNumber")).unsignedIntValue);
        let name="";
        try { name=ObjC.unwrap(s.localizedName) } catch (e) {}
        add(id,name);
    }
    if (!found.size) add(Number($.CGMainDisplayID()),"ecran principal");
    rows.join("\n");
' )
cg_rc=$?
[[ -z $map ]] || printf '%s\n' "$map"
if ((cg_rc)) || [[ -z $map ]]; then
    echo 'CoreGraphics: fără asociere disponibilă din această sesiune.'
fi

/usr/bin/perl -e 'alarm 28; exec @ARGV or die $!' /usr/sbin/system_profiler -json -timeout 20 SPDisplaysDataType |
/usr/bin/perl -MJSON::PP -e '
    use strict; use warnings;
    local $/; my $raw=<STDIN>; my $j=eval { decode_json($raw // "") }; my $found=0;
    exit 3 unless ref($j) eq "HASH" && ref($j->{SPDisplaysDataType}) eq "ARRAY";
    sub safe {
        my ($s)=@_; return "necunoscut" unless defined($s) && !ref($s) && length($s);
        $s=~s/[\x00-\x1f\x7f]/ /g;
        return substr($s,0,96)
    }
    binmode STDOUT, ":encoding(UTF-8)";
    for my $g (@{$j->{SPDisplaysDataType}}) {
        my $gpu=safe($g->{sppci_model}//$g->{_name});
        my $metal=safe($g->{spdisplays_metal}//$g->{spdisplays_metal_support});
        print "GPU inventariat | $gpu | Metal $metal\n";
        for my $d (@{$g->{spdisplays_ndrvs}//[]}) {
            my $name=safe($d->{_name});
            my $res=safe($d->{_spdisplays_pixels}//$d->{spdisplays_pixelresolution}//$d->{_spdisplays_resolution}//$d->{spdisplays_resolution});
            my $conn=safe($d->{spdisplays_connection_type}//$d->{spdisplays_display_type});
            my $online=safe($d->{spdisplays_online});
            print "System Information | $name | $res | GPU $gpu | conexiune $conn | online $online\n";
            $found=1 if $gpu ne "necunoscut";
        }
    }
    exit($found ? 0 : 3)
'
rc=("${PIPESTATUS[@]}")
if ((rc[0] || rc[1])); then echo "System Information: inventar de ecrane incomplet (profil=${rc[0]}, citire=${rc[1]})."; fi
if [[ $cg_rc == 0 && $map =~ \|\ GPU\ (Intel|NVIDIA|AMD|Apple) ]] || ((rc[0] == 0 && rc[1] == 0)); then exit 0; fi
exit 3
)
if [[ ${BASH_SOURCE[0]:-} == "$0" || ( $0 == /bin/bash && ${BASH_SOURCE[0]:-} == "" ) ]]; then
    display_reference
fi
