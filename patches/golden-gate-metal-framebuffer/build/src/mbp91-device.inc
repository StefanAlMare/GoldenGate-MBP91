// Included only in the probe or in a deliberately deferred, dual-driver build.
#import "mbp91-device.h"
#include <sys/sysctl.h>
#include <string.h>

static BOOL mbp91SysctlEquals(const char *key, const char *expected) {
    char value[64] = {};
    size_t size = sizeof(value);
    return sysctlbyname(key, value, &size, NULL, 0) == 0 &&
        size == strlen(expected) + 1 && memcmp(value, expected, size) == 0;
}

static BOOL mbp91DeviceClassMatches(id<MTLDevice> device, Class cls) {
    // Both class exports were inspected in the staged B driver binaries.
    // A proxy, subclass, renamed binary or different graphics stack needs its
    // own ABI evidence. Do not redirect its parent or search bundles by suffix.
    const char *owner = class_getImageName(cls);
    if (!owner) return NO;
    const char *name = class_getName(cls);
    if (!strcmp(name, "NVMTLDevice") &&
        !strcmp(owner, "/System/Library/Extensions/GeForceMTLDriver.bundle/Contents/MacOS/GeForceMTLDriver"))
        return [device.name isEqualToString:@"NVIDIA GeForce GT 650M"];
    if (!strcmp(name, "MTLIGAccelDevice") &&
        !strcmp(owner, "/System/Library/Extensions/AppleIntelHD4000GraphicsMTLDriver.bundle/Contents/MacOS/AppleIntelHD4000GraphicsMTLDriver"))
        return [device.name isEqualToString:@"Intel HD Graphics 4000"];
    return NO;
}

static BOOL mbp91FactorySignaturesMatch(Class cls) {
    const SEL selectors[] = {
        @selector(newRenderPipelineStateWithDescriptor:error:),
        @selector(newRenderPipelineStateWithDescriptor:options:reflection:error:),
        @selector(newRenderPipelineStateWithDescriptor:completionHandler:),
        @selector(newRenderPipelineStateWithDescriptor:options:completionHandler:),
        @selector(newCommandQueue),
        @selector(newCommandQueueWithMaxCommandBufferCount:)
    };
    for (size_t i = 0; i < sizeof(selectors)/sizeof(selectors[0]); ++i) {
        Method method = class_getInstanceMethod(cls, selectors[i]);
        struct objc_method_description abi = protocol_getMethodDescription(@protocol(MTLDevice), selectors[i], YES, YES);
        if (!abi.types || !method || !method_getTypeEncoding(method)) return NO;
        NSMethodSignature *want = [NSMethodSignature signatureWithObjCTypes:abi.types];
        NSMethodSignature *have = [NSMethodSignature signatureWithObjCTypes:method_getTypeEncoding(method)];
        if (!want || !have || want.numberOfArguments != have.numberOfArguments ||
            strcmp(want.methodReturnType, have.methodReturnType)) return NO;
        for (NSUInteger j = 0; j < want.numberOfArguments; ++j)
            if (strcmp([want getArgumentTypeAtIndex:j], [have getArgumentTypeAtIndex:j])) return NO;
    }
    return YES;
}

BOOL FBInstallMBP91Device(id<MTLDevice> device) {
    if (!device || !mbp91SysctlEquals("hw.model", "MacBookPro9,1") ||
        !mbp91SysctlEquals("kern.osversion", "26B131")) return NO;
    Class cls = object_getClass(device);
    if (!cls || !mbp91DeviceClassMatches(device, cls) || !device.registryID) return NO;

    // Process-wide marker plus a concrete-class lock also covers an accidental
    // second opt-in copy. Each copy has its own pipeline/encoder tracking keys,
    // so returning success for the second copy would conflate their pipelines.
    const void *ownerKey = sel_getName(sel_registerName("fb_mbp91FramebufferDeviceOwner_v1"));
    @synchronized (cls) {
        NSValue *owner = objc_getAssociatedObject(cls, ownerKey);
        if (owner) return owner.pointerValue == &deviceHooksKey;
        if (!mbp91FactorySignaturesMatch(cls)) return NO;
        // A reentrant or interrupted installation must not report success.
        objc_setAssociatedObject(cls, ownerKey, [NSValue valueWithPointer:NULL], OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        deviceHooks(cls);
        objc_setAssociatedObject(cls, ownerKey, [NSValue valueWithPointer:&deviceHooksKey], OBJC_ASSOCIATION_RETAIN_NONATOMIC);
        return YES;
    }
}
