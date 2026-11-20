"""Create the Foundation call description for Golden's Battery settings extension."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from uuid import UUID


# From the Foundation image in three 26B131 PowerPreferences crash reports.
GOLDEN_FOUNDATION_UUID = "5119c02feccd3c209858a2d9e725c718"
RUNTIME_TOOLS = Path(os.environ.get("GOLDEN_GATE_RUNTIME_TOOLS", Path(__file__).parent / "outils-runtime-locaux"))
SYMBOL = ("_$s10Foundation14DateComponentsV8calendar8timeZone3era4year5month3day4hour6minute"
          "6second10nanosecond7weekday0O7Ordinal7quarter11weekOfMonth0rS4Year0h7ForWeeksU0"
          "AcA8CalendarVSg_AA04TimeF0VSgSiSgA13ZtcfC")

# Resolve the actual implementation, including re-exports, in the active Intel
# cache. A UUID from a binary on a different macOS install would select no unit.
FOUNDATION_UUID_RUBY = r"""
require 'fiddle'
foundation = Fiddle.dlopen('/System/Library/Frameworks/Foundation.framework/Foundation')
symbol = foundation[SYMBOL_NAME]
dladdr = Fiddle::Function.new(Fiddle::Handle::DEFAULT['dladdr'],
  [Fiddle::TYPE_VOIDP, Fiddle::TYPE_VOIDP], Fiddle::TYPE_INT)
info = Fiddle::Pointer.malloc(4 * Fiddle::SIZEOF_VOIDP)
abort 'missing dyld image' if dladdr.call(symbol, info) == 0
base = Fiddle::Pointer.new(info[Fiddle::SIZEOF_VOIDP, Fiddle::SIZEOF_VOIDP].unpack1('J'))
magic, cpu, _, _, count, bytes = base[0, 32].unpack('L<8')
abort 'invalid Intel header' unless magic == 0xfeedfacf && cpu == 0x01000007 && bytes < 4_194_304
cursor = 32
count.times do
  abort 'truncated load command' if cursor + 8 > 32 + bytes
  cmd, size = base[cursor, 8].unpack('L<2')
  abort 'invalid load command' if size < 8 || cursor + size > 32 + bytes
  if cmd == 0x1b && size == 24
    puts base[cursor + 8, 16].unpack1('H*')
    exit 0
  end
  cursor += size
end
abort 'missing LC_UUID'
""".replace("SYMBOL_NAME", "'" + SYMBOL[1:] + "'")


def build_unit(foundation_uuid, tools=RUNTIME_TOOLS):
    """Return a verified single-record HAO interface unit for the supplied UUID."""
    image_uuid = UUID(str(foundation_uuid)).hex
    expected = {
        "hao_ifunit.py": "895f5cf111d643ee7420ebb38751f86c3726ff647c566f42be3261f225f72499",
        "hao_fat.py": "e2cec7bf465549ad8a8e8afa4a23f4b71f0359dfeb2fe18ee4396c0d40299d41",
    }
    for name, digest in expected.items():
        if hashlib.sha256((tools / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f"Generatorul diferă de versiunea verificată: {name}")
    # The remaining eleven Swift Optional<Int> values use 16 bytes each
    # on the ARM64 stack, with an 8-byte payload followed by a one-byte tag.
    layout = ",".join(f"{offset}.8,{offset + 8}.1" for offset in range(0, 176, 16))
    record = "\t".join([SYMBOL, "TYPED", "K", "-", "-", layout, "-"]) + "\n"
    command = [sys.executable, "-I", "-B", str(tools / "hao_ifunit.py")]
    with tempfile.TemporaryDirectory(prefix="golden-calendar-") as tmp:
        unit = Path(tmp) / image_uuid
        subprocess.run(command + ["write", str(unit), "--uuid", image_uuid],
                       input=record.encode("ascii"), check=True)
        subprocess.run(command + ["check", str(unit), "--uuid", image_uuid],
                       stdout=subprocess.PIPE, check=True)
        return unit.read_bytes()
