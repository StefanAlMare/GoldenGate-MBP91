#!/bin/bash
# Source this file in an Aqua shell, then call icon_reference.
icon_reference() {
    if [[ ${1:-} != --check ]]; then
        if [[ $(/bin/launchctl managername) != Aqua || $(/usr/bin/id -u) == 0 ||
              $(/usr/bin/id -u) != "$(/usr/bin/stat -f %u /dev/console)" ]]; then
            echo 'Oprit: proba cere sesiunea Aqua a utilizatorului conectat la desktop.'
            return 2
        fi
    fi
    /usr/bin/perl - "${1:-}" <<'PERL'
use strict;
use warnings;
use JSON::PP qw(decode_json);
use POSIX qw(strftime _exit);
use Time::HiRes qw(clock_gettime CLOCK_MONOTONIC);
$| = 1;
my $compare = ($ARGV[0] // '') eq '--compare-clients';
my $apps = ($ARGV[0] // '') eq '--apps';
my @ui_processes = qw(Dock Spotlight ControlCenter SystemUIServer);
my %ui = map { $_ => {} } @ui_processes;

sub record_ui {
    my ($e) = @_;
    my $name = $e->{processImagePath} // $e->{process} // '';
    $name =~ s{.*/}{};
    my $sample = $ui{$name} or return;
    my $msg = $e->{eventMessage} // '';
    return unless ($e->{subsystem} // '') =~ /iconservices/i ||
        ($e->{senderImagePath} // '') =~ m{/IconServices(?:/|$)}i ||
        $msg =~ /\bcom\.apple\.iconservices\b/i;
    ++$sample->{records};
    ++$sample->{errors} if $msg =~ /\bNSCocoaErrorDomain\s+Code=4097\b/;
}

sub record {
    my ($event, $by_pid) = @_;
    my $sample = $by_pid->{$event->{processID} // ''} or return;
    my $process = $event->{processImagePath} // $event->{process} // '';
    $process =~ s{.*/}{};
    return unless $process eq ($sample->{process} // 'osascript');
    ++$sample->{client_records};
    my $msg = $event->{eventMessage} // '';
    my $agent = $msg =~ /\bcom\.apple\.iconservices(?![.\w-])/i;
    my $store = $msg =~ /\bcom\.apple\.iconservices\.store(?![.\w-])/i;
    return unless $agent || $store || ($event->{subsystem} // '') =~ /iconservices/i ||
        ($event->{senderImagePath} // '') =~ m{/IconServices(?:/|$)}i || $msg =~ /failed to generate image/i;
    ++$sample->{icon_records};
    $sample->{endpoint_agent} = 1 if $agent;
    $sample->{endpoint_store} = 1 if $store;
    ++$sample->{error4097} if $msg =~ /\bNSCocoaErrorDomain\s+Code=4097\b/;
}

sub evidence {
    my ($s, $complete) = @_;
    return 'observed_4097' if $s->{error4097};
    return 'log_incomplete' unless $complete;
    return 'request_failed' if $s->{rc};
    return 'no_client_records' unless $s->{client_records};
    return 'no_icon_records' unless $s->{icon_records};
    return 'visible_no_4097';
}

if (($ARGV[0] // '') eq '--check') {
    my %by_pid = (42 => {});
    record({process=>'osascript',processID=>42,eventMessage=>'com.apple.iconservices.store'}, \%by_pid);
    die 'store' unless $by_pid{42}{endpoint_store} && !$by_pid{42}{endpoint_agent};
    record({process=>'osascript',processID=>43,eventMessage=>'Failed to generate image NSCocoaErrorDomain Code=4097'}, \%by_pid);
    record({process=>'osascript',processID=>42,subsystem=>'other',eventMessage=>'NSCocoaErrorDomain Code=4097'}, \%by_pid);
    die 'scope' unless evidence($by_pid{42},1) eq 'visible_no_4097';
    record({processImagePath=>'/usr/bin/osascript',processID=>42,subsystem=>'com.apple.iconservices',eventMessage=>'NSCocoaErrorDomain Code=4097'}, \%by_pid);
    die 'missing 4097' unless evidence($by_pid{42},1) eq 'observed_4097';
    die 'records' unless $by_pid{42}{icon_records} == 2 && $by_pid{42}{client_records} == 3;
    die 'invisible' unless evidence({},1) eq 'no_client_records' && evidence({},0) eq 'log_incomplete';
    $by_pid{55} = {process=>'ruby'};
    record({process=>'osascript', processID=>55, subsystem=>'com.apple.iconservices', eventMessage=>'NSCocoaErrorDomain Code=4097'}, \%by_pid);
    die 'ruby attribution' if $by_pid{55}{client_records};
    record({processImagePath=>'/System/Library/Frameworks/Ruby.framework/Versions/2.6/usr/bin/ruby', processID=>55,
            subsystem=>'com.apple.iconservices', eventMessage=>'NSCocoaErrorDomain Code=4097'}, \%by_pid);
    die 'ruby error' unless evidence($by_pid{55},1) eq 'observed_4097';
    print "OK icon_reference\n"; exit 0;
}

sub child_reader {
    my ($limit, @cmd) = @_;
    my $pid = open(my $fh, '-|');
    die "Proces indisponibil.\n" unless defined $pid;
    unless ($pid) {
        my $capture = ($compare || $apps) && $cmd[0] ne '/usr/bin/log';
        if ($capture) {
            open STDERR, '>&', \*STDOUT or _exit(126);
        } else {
            open STDERR, '>', '/dev/null' or _exit(126);
        }
        $SIG{ALRM} = 'DEFAULT';
        alarm $limit;
        exec { $cmd[0] } @cmd or do {
            print STDERR "exec $cmd[0]: $!\n" if $capture;
            _exit(127);
        };
    }
    return ($pid, $fh);
}

sub status_code {
    my ($st) = @_;
    return 255 if $st < 0;
    return 128 + ($st & 127) if $st & 127;
    return $st >> 8;
}

sub client_output {
    my ($fh) = @_;
    my $output = '';
    my $limit = 128 * 1024;
    while (read($fh, my $block, 8192)) {
        $output .= substr($block, 0, $limit - length($output)) if length($output) < $limit;
    }
    return $output;
}

sub report_failure {
    my ($tag, $pid, $rc, $output) = @_;
    my @notes = grep { /\S/ && !/^GG_(?:NATIVE(?:_ORIGIN|_PNG64)?|OSA) / } split /[\r\n]+/, $output;
    my @cause = grep { /GG_NATIVE_ERROR|LoadError|SyntaxError|invalid multibyte|dyld|cannot load|arch:|exec /i } @notes;
    my %seen;
    my $count = 0;
    for my $line (@cause, @notes) {
        $line =~ s/\e\[[0-9;?]*[A-Za-z]//g;
        $line =~ s/[\x00-\x1f\x7f]/ /g;
        $line = substr($line, 0, 240);
        next if $seen{$line}++;
        print "GG_CLIENT_DIAGNOSTIC tag=$tag pid=$pid rc=$rc $line\n";
        last if ++$count == 3;
    }
    print "GG_CLIENT_DIAGNOSTIC tag=$tag pid=$pid rc=$rc fara_mesaj_de_la_proces\n" unless $count;
}

my $request = <<'JS';
ObjC.import("AppKit");
function run(args) {
    const icon = $.NSWorkspace.sharedWorkspace.iconForFile(args[0]);
    const count = Number(icon.TIFFRepresentation.length);
    if (!(count > 0)) throw new Error("No TIFF");
    if (args[1] === "identity") {
        ObjC.bindFunction("_dyld_image_count", ["unsigned int", []]);
        ObjC.bindFunction("_dyld_get_image_header", ["void *", ["unsigned int"]]);
        ObjC.bindFunction("_dyld_get_image_name", ["char *", ["unsigned int"]]);
        const header = $.NSData.dataWithBytesLength($._dyld_get_image_header(0),8);
        const bytes = ObjC.unwrap(header.base64EncodedStringWithOptions(0));
        const arch = {"z/rt/gcAAAE=":"x86_64", "z/rt/gwAAAE=":"arm64"}[bytes] || "unknown";
        const n = Number($._dyld_image_count());
        if (!(n > 0 && n <= 32768)) throw new Error("Inventar dyld nevalid");
        let hao = 0;
        for (let i = 0; i < n; i++) {
            const name = $._dyld_get_image_name(i);
            if (!name) throw new Error("Nume dyld indisponibil");
            if (/^libhao(?:\.[^/]+)*\.dylib$/i.test(String(name).split("/").pop())) hao = 1;
        }
        if (Number($._dyld_image_count()) !== n) throw new Error("Inventarul dyld s-a schimbat");
        return "GG_OSA pid=" + Number($.NSProcessInfo.processInfo.processIdentifier) + " arch=" + arch +
            " images=" + n + " libhao=" + hao + " tiff_bytes=" + count;
    }
    return String(count);
}
JS
sub stamp { return strftime('%Y-%m-%d %H:%M:%S%z', localtime($_[0])) }
my $start = stamp(time);
my (@samples, %by_pid);
my @items = $compare ? map({[$_, '/Applications']} qw(osa_first ruby_first ruby_repeat osa_repeat))
                     : $apps ? (['finder', '/System/Library/CoreServices/Finder.app'],
                                ['settings', '/System/Applications/System Settings.app'],
                                ['activity', '/System/Applications/Utilities/Activity Monitor.app'])
                     : (['root', '/'], ['apps_first', '/Applications'], ['apps_repeat', '/Applications']);
for my $item (@items) {
    if ($apps && !-f "$item->[1]/Contents/Info.plist") {
        print "GG_APP_ICON tag=$item->[0] evidence=bundle_unavailable\n";
        next;
    }
    my $ruby = $apps || ($compare && $item->[0] =~ /^ruby/);
    my @cmd = $ruby ? ('/usr/bin/arch','-x86_64','/usr/bin/ruby','--disable-gems','-EUTF-8:UTF-8','-e',$ENV{GG_ICON_NATIVE_SOURCE},'--',$item->[1])
                    : ('/usr/bin/osascript','-l','JavaScript','-e',$request,$item->[1],($compare ? ('identity') : ()));
    my $before = clock_gettime(CLOCK_MONOTONIC);
    my ($pid, $fh) = child_reader($apps ? 12 : 25, @cmd);
    my $output = client_output($fh);
    close $fh;
    my $rc = status_code($?);
    my $ms = int(1000*(clock_gettime(CLOCK_MONOTONIC)-$before)+0.5);
    my ($bytes, $arch, $images, $hao, $self, $preview);
    if ($compare || $apps) {
        my $label = $ruby ? 'GG_NATIVE' : 'GG_OSA';
        ($self,$arch,$images,$hao,$bytes) = $output =~ /^\Q$label\E pid=(\d+) arch=(x86_64|arm64|unknown) images=(\d+) libhao=([01]) tiff_bytes=([1-9]\d{0,11})(?: elapsed_ms=\d+)?\s*$/m;
        $rc ||= 3 unless defined($self) && $self == $pid && $images && $arch ne 'unknown';
        $rc ||= 3 if $apps && (($arch // '') ne 'x86_64' || ($hao // 1) != 0);
        printf "%s tag=%s pid=%d self=%s arch=%s images=%s libhao=%s\n", $apps ? 'GG_APP_CLIENT' : 'GG_CLIENT',
            $item->[0], $pid, map {defined $_ ? $_ : 'unobserved'} ($self, $arch, $images, $hao);
        if ($ruby && $output =~ /^(GG_NATIVE_ORIGIN [^\r\n]{1,1024})$/m) { print "$1\n" }
        if ($ruby && $output =~ /^GG_NATIVE_PREVIEW ([^\r\n]{1,300})$/m) {
            print "GG_PREVIEW_DETAIL tag=$item->[0] pid=$pid $1\n";
        }
        report_failure($item->[0], $pid, $rc, $output) if $rc;
        if ($ruby && !$rc && $output =~ /^GG_NATIVE_PNG64 ([A-Za-z0-9+\/=]{1,64000})$/m) {
            print(($apps ? 'GG_APP_PNG' : 'GG_CLIENT_PNG'), " $item->[0] $1\n");
            $preview = 1;
        }
    } else {
        ($bytes) = $output =~ /\A\s*([1-9]\d{0,11})\s*\z/;
    }
    $rc = 3 if !$rc && !defined($bytes);
    my $s = {tag=>$item->[0], pid=>$pid, rc=>$rc, elapsed_ms=>$ms, tiff_bytes=>$bytes // 0,
        process=>$ruby ? 'ruby' : 'osascript', arch=>$arch, libhao=>$hao, preview=>$preview};
    push @samples, $s; $by_pid{$pid}=$s;
    printf "Cerere %s | PID %d | %d ms | %d octeți TIFF | cod %d\n", $s->{tag},$pid,$ms,$s->{tiff_bytes},$rc;
}
exit 3 if $apps && !@samples;
sleep 2;
my $end = stamp(time);
my $predicate = $compare ? 'process IN {"osascript","ruby"}' : $apps ? 'process == "ruby"' : 'process == "osascript"';
if ($apps) {
    my $names = join(',', map { qq{"$_"} } @ui_processes);
    $predicate .= qq{ OR (process IN {$names} AND } .
        '(subsystem CONTAINS[c] "iconservices" OR senderImagePath CONTAINS[c] "/IconServices" OR eventMessage CONTAINS[c] "com.apple.iconservices"))';
}
my ($logpid, $logs) = child_reader($apps ? 12 : 60, '/usr/bin/log','show','--style','ndjson','--info','--debug','--start',$start,'--end',$end,'--predicate',$predicate);
my ($finished,$invalid)=(0,0);
while (<$logs>) {
    next unless /\S/;
    my $e = eval { decode_json($_) };
    if (ref($e) ne 'HASH') { ++$invalid; next }
    if (exists $e->{finished}) { $finished=1; next }
    if (($compare || $apps) && ($e->{eventType} // '') =~ /loss|dropped/i) { ++$invalid; next }
    record($e, \%by_pid);
    record_ui($e) if $apps;
}
close $logs;
my $log_rc = status_code($?);
my $complete = $log_rc == 0 && $finished && !$invalid ? 1 : 0;
printf "%s start=%s end=%s rc=%d finished=%d invalid=%d complete=%d\n", $apps ? 'GG_APP_LOG' : 'GG_ICON_LOG', $start,$end,$log_rc,$finished,$invalid,$complete;
for my $s (@samples) {
    printf "%s tag=%s pid=%d elapsed_ms=%d tiff_bytes=%d rc=%d client_records=%d icon_records=%d endpoint_agent=%d endpoint_store=%d error4097=%d evidence=%s%s\n",
        $apps ? 'GG_APP_ICON' : 'GG_ICON',
        $s->{tag}, (map { $s->{$_} // 0 } qw(pid elapsed_ms tiff_bytes rc client_records icon_records endpoint_agent endpoint_store error4097)), evidence($s,$complete),
        $apps ? ' preview='.int($s->{preview} // 0) : '';
}
if ($apps) {
    for my $name (@ui_processes) {
        my $sample = $ui{$name};
        my $seen = $sample->{errors} ? 'observed_4097' : !$complete ? 'log_incomplete'
                 : $sample->{records} ? 'visible_no_4097' : 'no_visible_icon_records';
        printf "GG_UI_ICON process=%s icon_records=%d error4097=%d evidence=%s\n",
            $name, $sample->{records} // 0, $sample->{errors} // 0, $seen;
    }
    exit($complete && @samples == @items && !grep({$_->{rc} || !$_->{preview}} @samples) ? 0 : 3);
}
if ($compare) {
    my @native = grep {$_->{tag} =~ /^ruby/} @samples;
    my @osa = grep {$_->{tag} =~ /^osa/} @samples;
    my $native_confirmed = @native == 2 && !grep {$_->{rc} || ($_->{arch}//'') ne 'x86_64' || ($_->{libhao}//1) != 0} @native;
    my $osa_hao = !grep {$_->{rc} || ($_->{libhao}//0) != 1} @osa;
    print "GG_IDENTITATE Ruby_x86_64_fara_libhao=", $native_confirmed ? 'confirmat' : 'neconfirmat',
          " osascript_cu_libhao=", $osa_hao ? 'observat' : 'neconfirmat', "\n";
    for my $group (\@native, \@osa) {
        my @e = map {evidence($_,$complete)} @$group;
        my $result = grep({$_->{rc}} @$group) ? 'cerere_sau_identitate_neconfirmata'
                   : $e[0] eq $e[1] ? $e[0] : 'rezultate_diferite';
        print "GG_COMPARATIE client=$group->[0]{process} probe=", join(',',@e), " rezultat=$result\n";
    }
    my $logs_usable = !grep {evidence($_,$complete) !~ /^(observed_4097|visible_no_4097)$/} (@native,@osa);
    exit($native_confirmed && $osa_hao && $complete && $logs_usable ? 0 : 3);
}
exit($complete && !grep({$_->{rc}} @samples) ? 0 : 3);
PERL
}
# Call only after icon_reference completes and prints its log status. The preview
# is a separate request; it does not measure Finder or enter the timed sample.
icon_reference_preview() {
    if [[ $(/bin/launchctl managername) != Aqua || $(/usr/bin/id -u) == 0 ||
          $(/usr/bin/id -u) != "$(/usr/bin/stat -f %u /dev/console)" ]]; then
        echo 'Previzualizare indisponibilă: sesiunea Aqua nu este activă.' >&2
        return 2
    fi
    local picture
    if ! picture=$(/usr/bin/perl -e 'alarm 25; exec @ARGV or die $!' /usr/bin/osascript -l JavaScript 2>/dev/null <<'JS'
ObjC.import("AppKit");
ObjC.import("CoreGraphics");
ObjC.import("ImageIO");
const side = 64;
const icon = $.NSWorkspace.sharedWorkspace.iconForFile("/Applications");
const reps = $.NSBitmapImageRep.imageRepsWithData(icon.TIFFRepresentation);
// Prefer the first actual 64px representation. Otherwise downsample the
// nearest larger one, or upscale the largest representation available.
let selected, best = Infinity;
for (let i = 0; i < Number(reps.count); i++) {
    const rep = reps.objectAtIndex(i);
    const width = Number(rep.pixelsWide), height = Number(rep.pixelsHigh);
    if (!(width > 0 && height > 0)) continue;
    const extent = Math.max(width, height);
    const score = extent >= side ? extent - side : 1000000 + side - extent;
    if (score < best) { selected = rep; best = score; }
    if (score === 0) break;
}
if (!selected) throw Error("No bitmap");
const color = $.CGColorSpaceCreateWithName($.kCGColorSpaceSRGB);
const ctx = $.CGBitmapContextCreate(null, side, side, 8, side*4, color, 1);
const width = Number(selected.pixelsWide), height = Number(selected.pixelsHigh);
const scale = side / Math.max(width, height);
const w = width * scale, h = height * scale;
$.CGContextClearRect(ctx, $.CGRectMake(0, 0, side, side));
$.CGContextSetInterpolationQuality(ctx, 3);
$.CGContextDrawImage(ctx, $.CGRectMake((side-w)/2, (side-h)/2, w, h), selected.CGImage);
const pixels = $.CGBitmapContextCreateImage(ctx);
const png = $.NSMutableData.data;
const dest = $.CGImageDestinationCreateWithData(png, $("public.png"), 1, null);
$.CGImageDestinationAddImage(dest, pixels, null);
if (!$.CGImageDestinationFinalize(dest)) throw Error("PNG encoding");
const n = Number(png.length);
if (!(n >= 67 && n <= 48000)) throw Error("PNG size");
const result = ObjC.unwrap(png.base64EncodedStringWithOptions(0));
if (result.length !== 4*Math.ceil(n/3) || !/^iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(result)) throw Error("PNG data");
result;
JS
    ); then
        echo 'Previzualizarea pentru /Applications nu a putut fi produsă.' >&2
        return 3
    fi
    printf 'GG_PREVIEW %s\n' "$picture"
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then icon_reference "$@"; fi
