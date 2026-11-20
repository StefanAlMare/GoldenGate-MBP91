import Darwin
import Foundation

#if arch(arm64)
let architecture = "arm64"
#elseif arch(x86_64)
let architecture = "x86_64"
#else
#error("Build the battery calendar probe for Intel or ARM64.")
#endif

let calendar = Calendar.current
let components = DateComponents(hour: 0)
if calendar.date(from: components) == nil {
    print("GG_CALENDAR arch=\(architecture) hour=0 date=nil")
    exit(1)
}
print("GG_CALENDAR arch=\(architecture) hour=0 date=present")
