#!/usr/bin/ruby
# Run in the console user's Aqua session with a caller-supplied deadline.
# AXWindows is a CFArray attribute. Query only its count, without retrieving
# any window, reading its title, sending Apple events or opening a window.
def unobserved(pid, reason)
  puts "GG_AX pid=#{pid} result=unobserved reason=#{reason}"
  exit 3
end

pid_arg = ARGV.first.to_s
unobserved('-', 'invalid_pid') unless ARGV.size == 1 && /\A[1-9][0-9]{0,9}\z/.match?(pid_arg)
pid = Integer(pid_arg)
unobserved('-', 'invalid_pid') if pid > 2_147_483_647

begin
  require 'fiddle/import'
  module AX
    extend Fiddle::Importer
    dlload '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices',
           '/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation'
    extern 'unsigned char AXIsProcessTrusted()'
    extern 'void* AXUIElementCreateApplication(int)'
    extern 'int AXUIElementSetMessagingTimeout(void*, float)'
    extern 'int AXUIElementGetAttributeValueCount(void*, void*, long*)'
    extern 'void* CFStringCreateWithCString(void*, const char*, unsigned int)'
    extern 'void CFRelease(void*)'
  end

  unobserved(pid, 'permission_absent') if AX.AXIsProcessTrusted.zero?
  app = AX.AXUIElementCreateApplication(pid)
  unobserved(pid, 'missing_app') if app.null?
  begin
    status = AX.AXUIElementSetMessagingTimeout(app, 3.0)
    unobserved(pid, "set_timeout_#{status}") unless status.zero?
    # kAXWindowsAttribute is CFSTR("AXWindows") in the public SDK.
    key = AX.CFStringCreateWithCString(nil, 'AXWindows', 0x08000100)
    unobserved(pid, 'missing_key') if key.null?
    begin
      count = [-1].pack('l!')
      start = Process.clock_gettime(Process::CLOCK_MONOTONIC)
      status = AX.AXUIElementGetAttributeValueCount(app, key, count)
      elapsed = ((Process.clock_gettime(Process::CLOCK_MONOTONIC) - start) * 1000).round
      unobserved(pid, "count_#{status}") unless status.zero?
      unobserved(pid, 'invalid_count') if count.unpack1('l!').negative?
      puts "GG_AX pid=#{pid} result=reply elapsed_ms=#{elapsed}"
    ensure
      AX.CFRelease(key)
    end
  ensure
    AX.CFRelease(app)
  end
rescue LoadError, StandardError => error
  unobserved(pid, error.class.name.tr(':', '_'))
end
