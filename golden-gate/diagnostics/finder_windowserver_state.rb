# Query the hang flag maintained by WindowServer for an existing GUI process.
# The caller supplies Finder's PID in its Aqua session and a wall-clock limit.
require 'fiddle/import'

def unavailable(pid, reason)
  puts "GG_FINDER_WS pid=#{pid} state=unobserved reason=#{reason}"
  exit 3
end

pid = Integer(ARGV.fetch(0), 10) rescue nil
unavailable('-', 'invalid_pid') unless ARGV.length == 1 && pid && pid.between?(1, 2_147_483_647)

begin
  module WindowStatus
    extend Fiddle::Importer
    dlload '/System/Library/PrivateFrameworks/SkyLight.framework/SkyLight',
           '/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices'
    extern 'int SLSMainConnectionID()'
    extern 'unsigned char SLSEventIsAppUnresponsive(int, void*)'
    extern 'int GetProcessForPID(int, void*)'
    extern 'int GetProcessPID(void*, void*)'
  end

  connection = WindowStatus.SLSMainConnectionID
  unavailable(pid, 'no_windowserver_connection') unless connection.positive?
  serial = [0, 0].pack('L2')
  unavailable(pid, 'no_gui_process') unless WindowStatus.GetProcessForPID(pid, serial).zero?
  unavailable(pid, 'empty_serial') if serial.unpack('L2') == [0, 0]

  flag = WindowStatus.SLSEventIsAppUnresponsive(connection, serial)
  confirmed_pid = [0].pack('i')
  unless WindowStatus.GetProcessPID(serial, confirmed_pid).zero? && confirmed_pid.unpack1('i') == pid
    unavailable(pid, 'process_changed')
  end
  unavailable(pid, 'unexpected_flag') unless [0, 1].include?(flag)
  puts "GG_FINDER_WS pid=#{pid} state=#{flag == 1 ? 'marked_unresponsive' : 'not_marked'}"
rescue LoadError, StandardError => error
  unavailable(pid, error.class.name.tr(':', '_'))
end
