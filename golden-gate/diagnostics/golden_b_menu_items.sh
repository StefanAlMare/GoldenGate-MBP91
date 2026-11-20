# Read-only, from the console user's SSH login on Golden B. No Apple events.
gg_menu_items() (
    local scope key val pid proc screens
    local -a pids args
    echo 'GG_MENU Telemetrie de alimentare'
    /usr/bin/pmset -g batt
    for scope in ByHost utilizator; do
        args=()
        [[ $scope != ByHost ]] || args=(-currentHost)
        for key in BatteryShowPercentage Battery WiFi Bluetooth Sound Weather; do
            val=$(/usr/bin/defaults "${args[@]}" read com.apple.controlcenter "$key" 2>/dev/null) || val=
            [[ $val =~ ^-?[0-9]{1,3}$ ]] || val=nespecificat
            echo "GG_MENU com.apple.controlcenter $scope $key=$val"
        done
    done
    pids=()
    for proc in ControlCenter MenuBarAgent SystemUIServer; do
        pid=$(/usr/bin/pgrep -u "$(/usr/bin/id -u)" -x "$proc" 2>/dev/null)
        [[ $pid =~ ^[1-9][0-9]*$ ]] && pids+=("$proc=$pid")
    done
    (( ${#pids[@]} )) || { echo 'GG_MENU Procesele barei nu sunt identificabile.'; return 3; }
    # Window and AX coordinates both use the global, top-left-origin desktop.
    # NSScreen.frame instead uses a bottom-left origin on the primary display.
    screens=$(/usr/bin/perl -e 'alarm 8; exec @ARGV or die $!' /usr/bin/osascript -l JavaScript -e '
        ObjC.import("AppKit"); ObjC.import("CoreGraphics");
        const displays=$.NSScreen.screens, rows=[], ids=new Set();
        function add(id) {
            if (!id || ids.has(id)) return;
            const b=$.CGDisplayBounds(id);
            const values=[id,b.origin.x,b.origin.y,b.size.width,b.size.height].map(Number);
            if (values.every(Number.isFinite) && values[3]>0 && values[4]>0) {
                ids.add(id); rows.push(values.join(","));
            }
        }
        for (let i=0;i<Number(displays.count);i++) {
            add(Number(displays.objectAtIndex(i).deviceDescription.objectForKey($("NSScreenNumber")).unsignedIntValue));
        }
        add(Number($.CGMainDisplayID()));
        rows.join("\n");
    ') || screens=
    GG_MENU_DISPLAYS="$screens" /usr/bin/perl -e 'alarm 20; exec @ARGV or die $!' /usr/bin/arch -x86_64 /usr/bin/ruby --disable-gems -EUTF-8:UTF-8 - "${pids[@]}" <<'GG_MENU_RUBY'
# encoding: UTF-8
require 'fiddle/import'
module UI
  extend Fiddle::Importer
  dlload '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices',
         '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
  extern 'void* CFStringCreateWithCString(void*, const char*, unsigned int)'
  extern 'unsigned char CFStringGetCString(void*, void*, long, unsigned int)'
  extern 'unsigned long CFGetTypeID(void*)'
  extern 'unsigned long CFStringGetTypeID()'
  extern 'long CFArrayGetCount(void*)'
  extern 'void* CFArrayGetValueAtIndex(void*, long)'
  extern 'void* CFDictionaryGetValue(void*, void*)'
  extern 'unsigned char CFNumberGetValue(void*, int, void*)'
  extern 'void* CGWindowListCopyWindowInfo(unsigned int, unsigned int)'
  extern 'unsigned char CGRectMakeWithDictionaryRepresentation(void*, void*)'
  extern 'unsigned long AXValueGetTypeID()'
  extern 'unsigned int AXValueGetType(void*)'
  extern 'unsigned char AXValueGetValue(void*, unsigned int, void*)'
  extern 'unsigned char AXIsProcessTrusted()'
  extern 'void* AXUIElementCreateApplication(int)'
  extern 'int AXUIElementSetMessagingTimeout(void*, float)'
  extern 'int AXUIElementCopyAttributeValue(void*, void*, void*)'
end
def key(s)
  @keys ||= {}
  @keys[s] ||= UI.CFStringCreateWithCString(nil, s, 0x08000100)
end
def str(obj)
  return '' if !obj || obj.null? || UI.CFGetTypeID(obj) != UI.CFStringGetTypeID()
  buf = "\0" * 2048
  UI.CFStringGetCString(obj, buf, buf.bytesize, 0x08000100) == 0 ? '' : buf.split("\0", 2).first.to_s.scrub
end
def number(obj)
  buf = [0].pack('q')
  return unless obj && !obj.null? && UI.CFNumberGetValue(obj, 4, buf) != 0
  buf.unpack1('q')
end
def attr(obj, name)
  buf = [0].pack('J')
  return unless UI.AXUIElementCopyAttributeValue(obj, key(name), buf).zero?
  Fiddle::Pointer.new(buf.unpack1('J'))
end
def items(obj)
  return [] if !obj || obj.null?
  UI.CFArrayGetCount(obj).times.map { |i| UI.CFArrayGetValueAtIndex(obj, i) }
end
def label(text)
  {'Wi-Fi'=>/wi[\s\-\u2010-\u2013]?fi/i,'Bluetooth'=>/bluetooth/i,
   'Vreme'=>/weather|vreme|m[eé]t[eé]o/i,
   'Baterie'=>/batter(?:y|ie)|baterie/i,'Sunet'=>/sound|sunet|volume/i}.each do |name, match|
    return name if text.match?(match)
  end
  nil
end
def cg_bounds(win)
  bounds = UI.CFDictionaryGetValue(win,key('kCGWindowBounds'))
  buf = "\0" * 32 # CGRect on x86_64
  return if bounds.null? || UI.CGRectMakeWithDictionaryRepresentation(bounds,buf).zero?
  buf.unpack('d4')
end
def ax_pair(obj, attribute, type)
  value = attr(obj,attribute)
  return unless value && !value.null? && UI.CFGetTypeID(value) == UI.AXValueGetTypeID() &&
                UI.AXValueGetType(value) == type
  buf = "\0" * 16
  buf.unpack('d2') unless UI.AXValueGetValue(value,type,buf).zero?
end
def location(rect, screens)
  return 'poziție indisponibilă' unless rect && rect.all?(&:finite?)
  x,y,w,h = rect
  ids = screens.select do |_,sx,sy,sw,sh|
    w > 0 && h > 0 && x < sx+sw && x+w > sx && y < sy+sh && y+h > sy
  end.map(&:first)
  display = if screens.empty?
              'topologie indisponibilă'
            elsif ids.empty?
              'fără intersecție'
            else
              ids.join(',')
            end
  "dreptunghi=#{rect.map { |v| '%g' % v }.join(',')} | ID ecran=#{display}"
end
screens = ENV.fetch('GG_MENU_DISPLAYS','').lines.map do |line|
  values = line.strip.split(',')
  next unless values.length == 5
  [Integer(values[0]), *values.drop(1).map { |v| Float(v) }]
end.compact
puts 'GG_MENU Topologia ecranelor este indisponibilă.' if screens.empty?
screens.each do |id,*rect|
  puts "GG_MENU Ecran #{id} | x,y,lățime,înălțime=#{rect.map { |v| '%g' % v }.join(',')}"
end
owners = ARGV.map { |entry| name, pid = entry.split('='); [Integer(pid),name] }.to_h
windows = UI.CGWindowListCopyWindowInfo(17,0) # on-screen, without desktop elements
seen = []
count = named = 0
items(windows).each do |win|
  owner = owners[number(UI.CFDictionaryGetValue(win,key('kCGWindowOwnerPID')))]
  next unless owner
  title = str(UI.CFDictionaryGetValue(win,key('kCGWindowName')))
  count += 1
  named += 1 unless title.empty?
  name = label(title)
  next unless name
  seen << "#{owner}/#{name}"
  puts "GG_MENU CG #{owner}/#{name} | #{location(cg_bounds(win),screens)}"
end
if windows.null?
  puts 'GG_MENU Lista ferestrelor nu este disponibilă acestei sesiuni.'
else
  puts "GG_MENU CG ferestre ale proceselor barei=#{count}, cu nume accesibil=#{named}; module recunoscute: #{seen.uniq.sort.join(', ').sub(/^$/, 'niciunul')}."
end
if UI.AXIsProcessTrusted.zero?
  puts 'GG_MENU Arborele de accesibilitate nu este disponibil acestei probe.'
else
  owners.each do |pid,owner|
    app = UI.AXUIElementCreateApplication(pid)
    if app.null? || UI.AXUIElementSetMessagingTimeout(app,1.0) != 0
      puts "GG_MENU AX #{owner}: proces inaccesibil."
      next
    end
    menu = attr(app,'AXExtrasMenuBar')
    children = menu && attr(menu,'AXChildren')
    unless children && !children.null?
      puts "GG_MENU AX #{owner}: inventarul AXExtrasMenuBar/AXChildren este indisponibil."
      next
    end
    matches = items(children).map do |item|
      fields = %w[AXIdentifier AXTitle AXDescription AXValue].map { |k| str(attr(item,k)) }
      name = fields.map { |field| label(field) }.compact.first
      next unless name
      pos = ax_pair(item,'AXPosition',1)
      size = ax_pair(item,'AXSize',2)
      puts "GG_MENU AX #{owner}/#{name} | #{location(pos && size && pos+size,screens)}"
      name == 'Baterie' && fields.join(' ').match?(/\d\s*(%|la sută|percent)/i) ? 'Baterie (procent în textul accesibil)' : name
    end.compact.uniq
    puts "GG_MENU AX #{owner}: #{matches.join(', ').sub(/^$/, 'niciun element identificabil')}."
  end
end
GG_MENU_RUBY
)
