# encoding: UTF-8
# Read Option only. Use the Intel Ruby with Golden B booted and the desktop awake.
require 'fiddle'

def inconclusive(reason)
  puts "GG_OPTION neconcludent: #{reason}"
  exit 3
end

begin
  inconclusive('este necesar Ruby Intel') unless RUBY_PLATFORM.include?('x86_64')
  cg = Fiddle.dlopen('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
  sky_path = '/System/Library/PrivateFrameworks/SkyLight.framework/Versions/A/SkyLight'
  sky = Fiddle.dlopen(sky_path)
  int, ptr = Fiddle::TYPE_INT, Fiddle::TYPE_VOIDP
  fn = Fiddle::Function
  display = fn.new(cg['CGMainDisplayID'], [], int).call
  unless display != 0 && fn.new(cg['CGDisplayIsOnline'], [int], int).call(display) != 0
    inconclusive('ecranul principal activ nu este accesibil')
  end

  impl = sky['CGSInputModifierKeyState']
  inconclusive('aliasurile SkyLight diferă') unless impl == sky['SLSInputModifierKeyState']
  info = Fiddle::Pointer.malloc(4 * Fiddle::SIZEOF_VOIDP)
  uuid = Fiddle::Pointer.malloc(16)
  dyld = Fiddle::Handle::DEFAULT
  if fn.new(dyld['dladdr'], [ptr, ptr], int).call(impl, info) == 0
    inconclusive('imaginea Intel pentru apelul Option nu a fost identificată')
  end
  name, base = info[0, 2 * Fiddle::SIZEOF_VOIDP].unpack('J2')
  unless name != 0 && base != 0 && Fiddle::Pointer.new(name).to_s == sky_path &&
         fn.new(dyld['_dyld_get_image_uuid'], [ptr, ptr], Fiddle::TYPE_CHAR).call(base, uuid) != 0 &&
         uuid[0, 16].unpack1('H*') == '21acabfab6cc3ec9a3cf6d4d6b637f5a'
    inconclusive('imaginea SkyLight diferă de Golden B')
  end

  flags = fn.new(cg['CGEventSourceFlagsState'], [int], Fiddle::TYPE_LONG_LONG)
  # The 26B131 WindowManager checks the full 32-bit return at 0x10016bcec.
  key = fn.new(impl, [int, int], int)
  option_clear = -> do
    session = flags.call(0) & 0x80000
    hid = flags.call(1) & 0x80000
    session.zero? && hid.zero?
  end
  released = low_pressed = high_only = 0
  6.times do
    before = option_clear.call
    word = key.call(0, 3) & 0xffffffff
    after = option_clear.call
    if before && after
      released += 1
      if (word & 0xff) != 0
        low_pressed += 1
      elsif word != 0
        high_only += 1
      end
    end
    sleep 0.05
  end
  puts "GG_OPTION Intel: liber public=#{released}/6, octet apăsat=#{low_pressed}, numai biți superiori=#{high_only}."
  if released < 4 || low_pressed != 0 || (high_only != 0 && high_only != released)
    inconclusive('stare instabilă sau diferență față de citirile publice')
  end
  if high_only == released
    puts 'GG_OPTION Intel: octetul indică liber; rezultatul de 32 de biți este nenul.'
  else
    puts 'GG_OPTION Intel: octetul și rezultatul de 32 de biți indică liber.'
  end
  puts 'GG_OPTION Rezultatul privește procesul Intel. Interpretarea în WindowManager prin HAO se verifică separat.'
rescue Fiddle::DLError, ArgumentError, TypeError, RangeError
  inconclusive('apelurile de sistem necesare nu sunt disponibile')
end
