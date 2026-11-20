#!/usr/bin/ruby
# encoding: UTF-8
# One NSWorkspace request in stock Ruby, using the x86_64 Objective-C ABI.
# Invoke with /usr/bin/arch -x86_64 /usr/bin/ruby --disable-gems. The caller
# controls the deadline and obtains unified logs for this process by PID.
def native_error(stage, error)
  message = error.message.encode('UTF-8', invalid: :replace, undef: :replace).gsub(/[[:cntrl:]]+/, ' ')
  warn "GG_NATIVE_ERROR #{stage} #{error.class} #{message[0, 165]}"
end

def function(image, name, args, result)
  Fiddle::Function.new(image[name], args, result)
end

begin
  require 'fiddle'
  PTR = Fiddle::TYPE_VOIDP
  INT = Fiddle::TYPE_INT
  DYLD = Fiddle::Handle::DEFAULT
  OBJC = Fiddle.dlopen('/usr/lib/libobjc.A.dylib')
  IMAGE_COUNT = function(DYLD, '_dyld_image_count', [], INT)
  IMAGE_NAME = function(DYLD, '_dyld_get_image_name', [INT], PTR)
  IMAGE_HEADER = function(DYLD, '_dyld_get_image_header', [INT], PTR)
  CLASS = function(OBJC, 'objc_getClass', [PTR], PTR)
  CLASS_IMAGE = function(OBJC, 'class_getImageName', [PTR], PTR)
  SELECTOR = function(OBJC, 'sel_registerName', [PTR], PTR)
  OBJECT = function(OBJC, 'objc_msgSend', [PTR, PTR], PTR)
  OBJECT_WITH_ARG = function(OBJC, 'objc_msgSend', [PTR, PTR, PTR], PTR)
  OBJECT_AT_INDEX = function(OBJC, 'objc_msgSend', [PTR, PTR, Fiddle::TYPE_SIZE_T], PTR)
  ENCODE_BITMAP = function(OBJC, 'objc_msgSend', [PTR, PTR, Fiddle::TYPE_SIZE_T, PTR], PTR)
  LENGTH = function(OBJC, 'objc_msgSend', [PTR, PTR], Fiddle::TYPE_SIZE_T)
  DRAIN = function(OBJC, 'objc_msgSend', [PTR, PTR], Fiddle::TYPE_VOID)
  SET_OBJECT = function(OBJC, 'objc_msgSend', [PTR, PTR, PTR], Fiddle::TYPE_VOID)
  SET_ARGUMENT = function(OBJC, 'objc_msgSend', [PTR, PTR, PTR, Fiddle::TYPE_LONG], Fiddle::TYPE_VOID)
  INIT_BITMAP = function(OBJC, 'objc_msgSend',
    [PTR, PTR, PTR, Fiddle::TYPE_LONG, Fiddle::TYPE_LONG, Fiddle::TYPE_LONG, Fiddle::TYPE_LONG,
     Fiddle::TYPE_CHAR, Fiddle::TYPE_CHAR, PTR, Fiddle::TYPE_LONG, Fiddle::TYPE_LONG], PTR)
rescue LoadError, StandardError => error
  native_error('initializare', error)
  exit 3
end

def required(ptr, label)
  raise "Indisponibil: #{label}" if ptr.null?
  ptr
end

def image_arch(index)
  header = required(IMAGE_HEADER.call(index), 'antet Mach-O')
  magic, cpu_type = header[0, 8].unpack('V2')
  raise 'Procesul sau cadrul AppKit nu folosește x86_64.' unless magic == 0xfeedfacf && cpu_type == 0x01000007
  'x86_64'
end

def image_inventory
  # An image can be loaded between calls. Retry if dyld's list has grown
  # or any pointer was unavailable during the enumeration.
  3.times do
    count = IMAGE_COUNT.call
    raise 'Inventar dyld nevalid.' unless (1..32_768).cover?(count)
    names = count.times.map do |i|
      ptr = IMAGE_NAME.call(i)
      ptr.to_s unless ptr.null?
    end
    return names if !names.include?(nil) && IMAGE_COUNT.call == count
  end
  raise 'Inventarul dyld nu a rămas stabil.'
end

def hao_paths(names)
  names.select { |path| File.basename(path).match?(/\Alibhao(?:\.[^\/]+)*\.dylib\z/i) }
end

# NSRect is passed by value. NSInvocation lets AppKit marshal the CGRect from
# its method signature without relying on a particular struct calling convention.
def scaled_bitmap(rep, width, height)
  klass = CLASS.call('NSBitmapImageRep')
  space = OBJECT_WITH_ARG.call(CLASS.call('NSString'), SELECTOR.call('stringWithUTF8String:'), 'NSCalibratedRGBColorSpace')
  init = SELECTOR.call('initWithBitmapDataPlanes:pixelsWide:pixelsHigh:bitsPerSample:samplesPerPixel:hasAlpha:isPlanar:colorSpaceName:bytesPerRow:bitsPerPixel:')
  bitmap = required(INIT_BITMAP.call(OBJECT.call(klass, SELECTOR.call('alloc')), init,
                                    nil, 64, 64, 8, 4, 1, 0, space, 256, 32), 'bitmap de 64 px')
  OBJECT.call(bitmap, SELECTOR.call('autorelease'))
  # AppKit's buffer need not start cleared. Set the padding transparent.
  required(OBJECT.call(bitmap, SELECTOR.call('bitmapData')), 'pixeli')[0, 64*256] = "\0".b * (64*256)
  graphics = CLASS.call('NSGraphicsContext')
  context = required(OBJECT_WITH_ARG.call(graphics, SELECTOR.call('graphicsContextWithBitmapImageRep:'), bitmap), 'context bitmap')
  draw = SELECTOR.call('drawInRect:')
  signature = required(OBJECT_WITH_ARG.call(rep, SELECTOR.call('methodSignatureForSelector:'), draw), 'drawInRect:')
  call = required(OBJECT_WITH_ARG.call(CLASS.call('NSInvocation'), SELECTOR.call('invocationWithMethodSignature:'), signature), 'invocare AppKit')
  SET_OBJECT.call(call, SELECTOR.call('setTarget:'), rep)
  SET_OBJECT.call(call, SELECTOR.call('setSelector:'), draw)
  scale = 64.0 / [width, height].max
  w, h = width * scale, height * scale
  rect = [(64-w)/2, (64-h)/2, w, h].pack('d4')
  SET_ARGUMENT.call(call, SELECTOR.call('setArgument:atIndex:'), rect, 2)
  DRAIN.call(graphics, SELECTOR.call('saveGraphicsState'))
  begin
    SET_OBJECT.call(graphics, SELECTOR.call('setCurrentContext:'), context)
    DRAIN.call(call, SELECTOR.call('invoke'))
    success = "\0".b
    SET_OBJECT.call(call, SELECTOR.call('getReturnValue:'), success)
    raise 'Desenarea în bitmap a eșuat.' if success.getbyte(0).zero?
  ensure
    DRAIN.call(graphics, SELECTOR.call('restoreGraphicsState'))
  end
  bitmap
end

def bitmap_preview(tiff)
  representations = OBJECT_WITH_ARG.call(CLASS.call('NSBitmapImageRep'), SELECTOR.call('imageRepsWithData:'), tiff)
  required(representations, 'reprezentări bitmap')
  count = LENGTH.call(representations, SELECTOR.call('count'))
  raise "Număr de cadre TIFF neacceptat: #{count}" unless (1..4096).cover?(count)
  selected = nil
  smallest_score = nil
  count.times do |index|
    rep = OBJECT_AT_INDEX.call(representations, SELECTOR.call('objectAtIndex:'), index)
    width = LENGTH.call(rep, SELECTOR.call('pixelsWide'))
    height = LENGTH.call(rep, SELECTOR.call('pixelsHigh'))
    next unless width.between?(1, 16_384) && height.between?(1, 16_384)
    if width == 64 && height == 64
      selected = [rep, width, height]
      break
    end
    extent = [width, height].max
    score = extent >= 64 ? extent - 64 : 65_536 - extent
    if smallest_score.nil? || score < smallest_score
      selected, smallest_score = [rep, width, height], score
    end
  end
  raise 'TIFF fără cadru utilizabil.' unless selected
  rep, width, height = selected
  # Preserve the existing 64x64 bitmap byte-for-byte whenever it is present.
  rep = scaled_bitmap(rep, width, height) unless width == 64 && height == 64
  properties = OBJECT.call(CLASS.call('NSDictionary'), SELECTOR.call('dictionary'))
  data = required(ENCODE_BITMAP.call(rep, SELECTOR.call('representationUsingType:properties:'), 4, properties), 'PNG')
  length = LENGTH.call(data, SELECTOR.call('length'))
  raise "Lungime PNG nevalidă: #{length}" unless (67..48_000).cover?(length)
  raw = required(OBJECT.call(data, SELECTOR.call('bytes')), 'PNG')[0, length]
  raise 'PNG de 64 px nevalid.' unless raw.start_with?("\x89PNG\r\n\x1a\n".b) && raw[12, 4] == 'IHDR' && raw[16, 8].unpack('N2') == [64, 64]
  puts "GG_NATIVE_PREVIEW source=#{width}x#{height} frames=#{count} output=64x64"
  [raw].pack('m0')
end

begin
  path = ARGV.fetch(0, '')
  paths = ['/', '/Applications', '/System/Library/CoreServices/Finder.app',
           '/System/Applications/System Settings.app', '/System/Applications/Utilities/Activity Monitor.app']
  raise 'Calea nu aparține setului de pictograme verificat.' unless ARGV.size == 1 && paths.include?(path)
  raise 'Mediul cere injectarea de biblioteci.' unless ENV['DYLD_INSERT_LIBRARIES'].to_s.empty?
  arch = image_arch(0)
  # Keep the handle alive until after the request and the second inventory.
  appkit = Fiddle.dlopen('/System/Library/Frameworks/AppKit.framework/AppKit')
  before = image_inventory
  workspace_class = required(CLASS.call('NSWorkspace'), 'NSWorkspace')
  appkit_path = required(CLASS_IMAGE.call(workspace_class), 'imaginea NSWorkspace').to_s
  appkit_index = before.index(appkit_path)
  raise 'Originea NSWorkspace nu corespunde cadrului AppKit încărcat.' unless appkit_index &&
    appkit_path.match?(%r{\A/System/Library/Frameworks/AppKit\.framework/(?:Versions/[^/]+/)?AppKit\z})
  appkit_arch = image_arch(appkit_index)

  pool = required(OBJECT.call(CLASS.call('NSAutoreleasePool'), SELECTOR.call('new')), 'NSAutoreleasePool')
  begin
    argument = required(OBJECT_WITH_ARG.call(CLASS.call('NSString'), SELECTOR.call('stringWithUTF8String:'), path), 'NSString')
    start = Process.clock_gettime(Process::CLOCK_MONOTONIC)
    workspace = required(OBJECT.call(workspace_class, SELECTOR.call('sharedWorkspace')), 'sharedWorkspace')
    icon = required(OBJECT_WITH_ARG.call(workspace, SELECTOR.call('iconForFile:'), argument), 'iconForFile:')
    tiff = required(OBJECT.call(icon, SELECTOR.call('TIFFRepresentation')), 'TIFFRepresentation')
    bytes = LENGTH.call(tiff, SELECTOR.call('length'))
    elapsed = ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - start) * 1000).round
    raise 'Reprezentare TIFF goală.' unless bytes.positive?
    after = image_inventory
    hao = (hao_paths(before) | hao_paths(after))
    puts "GG_NATIVE_ORIGIN main=#{before.first} appkit=#{appkit_path} appkit_arch=#{appkit_arch} hao_paths=#{hao.empty? ? '-' : hao.join(',')}"
    puts "GG_NATIVE pid=#{Process.pid} arch=#{arch} images=#{after.size} libhao=#{hao.empty? ? 0 : 1} tiff_bytes=#{bytes} elapsed_ms=#{elapsed}"
    STDOUT.flush
    unless path == '/'
      begin
        preview = bitmap_preview(tiff)
        puts "GG_NATIVE_PNG64 #{preview}" if preview
      rescue StandardError => error
        warn "GG_NATIVE_PREVIEW output=unavailable reason=#{error.class}: #{error.message}"
      end
    end
  ensure
    DRAIN.call(pool, SELECTOR.call('drain'))
  end
rescue StandardError => error
  native_error('cerere', error)
  exit 3
end
