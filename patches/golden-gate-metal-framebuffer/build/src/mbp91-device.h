#pragma once
#import <Metal/Metal.h>

// Probe or optional -DFB_SYSTEM=1 -DFB_MBP91_DUAL=1 shared core.
// Call synchronously on the device the driver returned, outside the loader, before
// handing it to the first Metal client. Repeat for devices obtained later.
// YES also covers a device class already registered by this copy of the core.
// NO means the device or its methods could not be positively identified.
#ifdef __cplusplus
extern "C" {
#endif
__attribute__((visibility("default"))) BOOL FBInstallMBP91Device(id<MTLDevice> device);
#ifdef __cplusplus
}
#endif
