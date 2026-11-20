# encoding: UTF-8
# System Ruby -x86_64; offscreen NSImage drawing, no application interaction.
require 'fiddle/import'
require 'json'

module API
  extend Fiddle::Importer
  dlload Fiddle::Handle::DEFAULT, '/usr/lib/libobjc.A.dylib',
         '/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics',
         '/System/Library/Frameworks/AppKit.framework/AppKit'
  extern 'void *objc_getClass(const char *)'
  extern 'void *class_getImageName(void *)'
  extern 'void *sel_registerName(const char *)'
  extern 'unsigned int _dyld_image_count()'
  extern 'void *_dyld_get_image_header(unsigned int)'
  extern 'void *_dyld_get_image_name(unsigned int)'
  extern 'void *CGColorSpaceCreateWithName(void *)'
  extern 'void CGColorSpaceRelease(void *)'
  extern 'void *CGBitmapContextCreate(void *, size_t, size_t, size_t, size_t, void *, unsigned int)'
  extern 'void *CGBitmapContextCreateImage(void *)'
  extern 'void CGContextRelease(void *)'
  extern 'void CGImageRelease(void *)'
  extern 'void CGContextSetRGBFillColor(void *, double, double, double, double)'
  extern 'void CGContextMoveToPoint(void *, double, double)'
  extern 'void CGContextAddLineToPoint(void *, double, double)'
  extern 'void CGContextClosePath(void *)'
  extern 'void CGContextFillPath(void *)'
end

P = Fiddle::TYPE_VOIDP
I = Fiddle::TYPE_LONG
D = Fiddle::TYPE_DOUBLE
V = Fiddle::TYPE_VOID
C = Fiddle::TYPE_CHAR
SIDE = 32
SEND = Fiddle::Handle::DEFAULT['objc_msgSend']
METHODS = {}

def send_obj(obj, selector, types = [], args = [], result = P)
  signature = [result, *types]
  fn = METHODS[signature] ||= Fiddle::Function.new(SEND, [P, P, *types], result)
  fn.call(obj, API.sel_registerName(selector), *args)
end

def ns_string(s)
  send_obj(API.objc_getClass('NSString'), 'stringWithUTF8String:', [P], [s])
end

def identity
  images = []
  3.times do
    count = API._dyld_image_count
    raise 'Invalid dyld inventory size' unless count.between?(1,32768)
    images = count.times.map do |i|
      path = API._dyld_get_image_name(i)
      path.to_s unless path.null?
    end
    break if images.none?(&:nil?) && API._dyld_image_count == count
    images = []
  end
  raise 'Unstable dyld inventory' if images.empty?
  path = API.class_getImageName(API.objc_getClass('NSImage')).to_s
  index = images.index(path) if path.match?(%r{\A/System/Library/Frameworks/AppKit\.framework/(?:Versions/[^/]+/)?AppKit\z})
  raise 'Unknown NSImage provider' unless index
  arch = lambda do |i|
    hdr = API._dyld_get_image_header(i)
    !hdr.null? && hdr[0,8].unpack('V2') == [0xfeedfacf,0x01000007]
  end
  raise 'Expected native x86_64 client and AppKit' unless arch.call(0) && arch.call(index)
  raise 'libhao loaded in reference process' if images.any? { |n| File.basename(n).match?(/\Alibhao(?:\..+)?\.dylib\z/i) }
  {arch: 'x86_64', appkit_arch: 'x86_64', libhao: 0}
end

# Marshal NSSize and the two by-value NSRects using the framework's own ABI.
def invocation(target, selector)
  sel = API.sel_registerName(selector)
  signature = send_obj(target, 'methodSignatureForSelector:', [P], [sel])
  raise "Unavailable selector: #{selector}" if signature.null?
  call = send_obj(API.objc_getClass('NSInvocation'), 'invocationWithMethodSignature:', [P], [signature])
  send_obj(call, 'setTarget:', [P], [target], V)
  send_obj(call, 'setSelector:', [P], [sel], V)
  call
end

def draw_symbol(image, context)
  call = invocation(image, 'size')
  send_obj(call, 'invoke', [], [], V)
  packed = "\0".b * 16
  send_obj(call, 'getReturnValue:', [P], [packed], V)
  w,h = packed.unpack('d2')
  return false unless [w,h].all? { |v| v.finite? && v.positive? }
  scale = (SIDE - 2) / [w,h].max
  w *= scale
  h *= scale
  draw = invocation(image, 'drawInRect:fromRect:operation:fraction:')
  args = [[(SIDE-w)/2,(SIDE-h)/2,w,h].pack('d4'), [0.0,0.0,0.0,0.0].pack('d4'), [2].pack('q'), [1.0].pack('d')]
  args.each_with_index { |bytes,i| send_obj(draw, 'setArgument:atIndex:', [P,I], [bytes,i+2], V) }
  graphics = API.objc_getClass('NSGraphicsContext')
  canvas = send_obj(graphics,'graphicsContextWithCGContext:flipped:',[P,C],[context,0])
  raise 'No NSGraphicsContext' if canvas.null?
  send_obj(graphics,'saveGraphicsState',[],[],V)
  begin
    send_obj(graphics,'setCurrentContext:',[P],[canvas],V)
    send_obj(draw,'invoke',[],[],V)
  ensure
    send_obj(graphics,'restoreGraphicsState',[],[],V)
  end
  true
end

def sample(kind, name)
  pixels = ("\0".b * (SIDE * SIDE * 4))
  space = API.CGColorSpaceCreateWithName(ns_string('kCGColorSpaceSRGB'))
  raise 'No sRGB' if space.null?
  begin
    context = API.CGBitmapContextCreate(pixels,SIDE,SIDE,8,SIDE*4,space,0x4001)
    raise 'No RGBA bitmap context' if context.null?
    if kind == 'control' && name == 'solid-16x16'
      API.CGContextSetRGBFillColor(context,1,1,1,1)
      API.CGContextMoveToPoint(context,8,8)
      [[24,8],[24,24],[8,24]].each { |x,y| API.CGContextAddLineToPoint(context,x,y) }
      API.CGContextClosePath(context)
      API.CGContextFillPath(context)
    elsif kind != 'control'
      n = ns_string(name)
      image = if kind == 'sf'
                send_obj(API.objc_getClass('NSImage'),'imageWithSystemSymbolName:accessibilityDescription:',[P,P],[n,n])
              else
                send_obj(API.objc_getClass('NSImage'),'imageNamed:',[P],[n])
              end
      return {state:'unavailable'} if image.null?
      return {state:'invalid-image'} if send_obj(image,'isValid',[],[],C).zero?
      return {state:'invalid-size'} unless draw_symbol(image,context)
    end
    cg = API.CGBitmapContextCreateImage(context)
    raise 'No CGImage' if cg.null?
    rep = send_obj(send_obj(API.objc_getClass('NSBitmapImageRep'),'alloc'),'initWithCGImage:',[P],[cg])
    raise 'No bitmap rep' if rep.null?
    alpha = (0...SIDE).flat_map do |y|
      (0...SIDE).map do |x|
        color = send_obj(rep,'colorAtX:y:',[I,I],[x,y])
        raise 'Invalid sampled color' if color.null?
        send_obj(color,'alphaComponent',[],[],D)
      end
    end
    hash = alpha.reduce(2166136261) { |a,v| ((a ^ (v >= 0.45 ? 1 : 0)) * 16777619) & 0xffffffff }
    nonzero = alpha.count(&:positive?)
    marked = alpha.each_index.select { |i| alpha[i] >= 0.45 }
    covered = marked.length
    if covered > 0
      xs = marked.map { |i| i % SIDE }
      ys = marked.map { |i| i / SIDE }
      box_area = (xs.max - xs.min + 1) * (ys.max - ys.min + 1)
    end
    state = if nonzero.zero?
              'empty'
            elsif covered.zero?
              'faint'
            elsif kind != 'control' && covered == box_area
              'solid-rectangle'
            else
              'pixels'
            end
    {state:state, nonzero:nonzero, covered:covered, peakAlpha255:(255*alpha.max).round, mask32:'%08x' % hash}
  ensure
    send_obj(rep,'release',[],[],V) if rep && !rep.null?
    API.CGImageRelease(cg) if cg && !cg.null?
    API.CGContextRelease(context) if context && !context.null?
    API.CGColorSpaceRelease(space)
  end
end

begin
  pool = send_obj(API.objc_getClass('NSAutoreleasePool'),'new')
  identity
  requests = [%w[control empty],%w[control solid-16x16],%w[sf speaker.wave.2.fill],
              %w[sf wifi],%w[sf bluetooth],%w[named NSBluetoothTemplate]]
  rows = requests.map do |kind,name|
    begin
      {kind:kind, name:name}.merge(sample(kind,name))
    rescue StandardError => error
      {kind:kind, name:name, state:'probe-error', error:error.message.to_s[0,120]}
    end
  end
  puts "GG_INTEL_IDENTITY #{identity.to_json}"
  rows.each { |row| puts "GG_INTEL_SYMBOL #{row.to_json}" }
  ok = rows[0][:nonzero] == 0 && rows[1][:covered] == 256 && rows[1][:nonzero] == 256 &&
       rows.none? { |row| row[:state] == 'probe-error' }
  puts "GG_INTEL_CONTROLS #{ok ? 'PASS' : 'FAIL'}"
  exit(ok ? 0 : 3)
rescue StandardError => error
  warn "GG_INTEL_ERROR #{error.message.to_s[0,160]}"
  exit 3
ensure
  send_obj(pool,'drain',[],[],V) if pool && !pool.null?
end
