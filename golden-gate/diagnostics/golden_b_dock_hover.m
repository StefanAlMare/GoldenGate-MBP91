// Read-only mouseDown targeting and optional AX geometry on Golden B.
#import <AppKit/AppKit.h>
#import <ApplicationServices/ApplicationServices.h>
#include <sys/sysctl.h>
#include <unistd.h>

typedef NS_ENUM(int, DockEdge) { Bottom, Left, Right };

static CGPoint quartzPoint(NSPoint appKitPoint, CGFloat mainHeight) {
    return CGPointMake(appKitPoint.x, mainHeight - appKitPoint.y);
}

static NSDictionary *windowForNumber(NSInteger number, NSArray *list) {
    if (number <= 0 || number > UINT32_MAX) return nil;
    for (NSDictionary *window in list)
        if ([window[(__bridge NSString *)kCGWindowNumber] unsignedIntValue] == (CGWindowID)number)
            return window;
    return nil;
}

static BOOL isUserDock(pid_t pid) {
    int mib[] = { CTL_KERN, KERN_PROC, KERN_PROC_PID, pid };
    struct kinfo_proc info = {0};
    size_t size = sizeof(info);
    return sysctl(mib, 4, &info, &size, NULL, 0) == 0 && size == sizeof(info) &&
        info.kp_eproc.e_pcred.p_ruid == getuid() && strcmp(info.kp_proc.p_comm, "Dock") == 0;
}

static id axAttribute(AXUIElementRef element, CFStringRef name) {
    CFTypeRef value = NULL;
    if (AXUIElementCopyAttributeValue(element, name, &value) != kAXErrorSuccess) return nil;
    return CFBridgingRelease(value);
}

static BOOL axBounds(AXUIElementRef element, CGRect *bounds) {
    id pos = axAttribute(element, kAXPositionAttribute);
    id size = axAttribute(element, kAXSizeAttribute);
    return pos && size && CFGetTypeID((__bridge CFTypeRef)pos) == AXValueGetTypeID() &&
        CFGetTypeID((__bridge CFTypeRef)size) == AXValueGetTypeID() &&
        AXValueGetValue((__bridge AXValueRef)pos, kAXValueCGPointType, &bounds->origin) &&
        AXValueGetValue((__bridge AXValueRef)size, kAXValueCGSizeType, &bounds->size) &&
        !CGRectIsEmpty(*bounds);
}

// Only inspect roles and geometry belonging to this Dock. Do not request titles.
static id itemAtPoint(AXUIElementRef system, pid_t pid, CGPoint point) {
    AXUIElementRef hit = NULL;
    if (AXUIElementCopyElementAtPosition(system, point.x, point.y, &hit) != kAXErrorSuccess) return nil;
    id current = CFBridgingRelease(hit);
    for (int n = 0; current && n < 4; n++) {
        AXUIElementRef el = (__bridge AXUIElementRef)current;
        pid_t owner = 0;
        if (AXUIElementGetPid(el, &owner) != kAXErrorSuccess || owner != pid) return nil;
        if ([axAttribute(el, kAXRoleAttribute) isEqual:@"AXDockItem"]) return current;
        current = axAttribute(el, kAXParentAttribute);
    }
    return nil;
}

static void printRect(CGRect r) {
    printf("%.1f,%.1f %.1fx%.1f", r.origin.x, r.origin.y, r.size.width, r.size.height);
}

static int observe(pid_t pid) {
    CGDirectDisplayID ids[32];
    uint32_t displays = 0;
    if (CGGetActiveDisplayList(32, ids, &displays) != kCGErrorSuccess || !displays || displays >= 32) {
        puts("GG_HOVER Ecranele active nu au putut fi identificate.");
        return 3;
    }
    NSString *orientation = CFBridgingRelease(CFPreferencesCopyAppValue(CFSTR("orientation"), CFSTR("com.apple.dock")));
    DockEdge edge = [orientation isEqual:@"left"] ? Left : [orientation isEqual:@"right"] ? Right : Bottom;
    for (uint32_t i = 0; i < displays; i++) {
        printf("GG_DISPLAY id=%u bounds=", ids[i]); printRect(CGDisplayBounds(ids[i])); puts("");
    }
    BOOL trusted = AXIsProcessTrusted(); // Never call AXIsProcessTrustedWithOptions(prompt).
    id systemAX = trusted ? CFBridgingRelease(AXUIElementCreateSystemWide()) : nil;
    if (systemAX) AXUIElementSetMessagingTimeout((__bridge AXUIElementRef)systemAX, 0.12f);
    printf("GG_HOVER Dock PID=%d | margine=%s | AX=%s\n", pid,
           edge == Left ? "stânga" : edge == Right ? "dreapta" : "jos", trusted ? "disponibil" : "fără acces");
    puts("GG_HOVER ACUM: ține cursorul în fereastra Finder sau Configurări o secundă, treci peste două pictograme din Dock și revino în fereastră.");
    puts("GG_HOVER AppKit identifică fereastra care ar primi un clic în acel punct. Proba nu generează clicuri.");
    NSMutableArray *items = [NSMutableArray array];
    CGFloat maxOver[3] = {0}, minAway[3] = {CGFLOAT_MAX, CGFLOAT_MAX, CGFLOAT_MAX};
    int dockCount = 0, controlCount = 0, unknownCount = 0, axCount = 0;
    BOOL crossed = NO, returned = NO;
    NSInteger previousNumber = -1;
    NSString *previousLabel = nil;
    NSUInteger previousItem = 0;
    double start = NSProcessInfo.processInfo.systemUptime;
    for (;;) { @autoreleasepool {
        double elapsed = NSProcessInfo.processInfo.systemUptime - start;
        if (elapsed >= 12.0) break;
        NSPoint mouse = [NSEvent mouseLocation];
        // Both AppKit calls use the same bottom-left coordinate system, even on a secondary display.
        NSInteger number = [NSWindow windowNumberAtPoint:mouse belowWindowWithWindowNumber:0];
        NSArray *windows = CFBridgingRelease(CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID));
        NSDictionary *hit = windowForNumber(number, windows);
        NSNumber *layer = hit[(__bridge NSString *)kCGWindowLayer];
        pid_t owner = [hit[(__bridge NSString *)kCGWindowOwnerPID] intValue];
        BOOL dockHit = owner == pid;
        NSString *label = owner > 0 ? @"altă fereastră" : @"fără țintă identificabilă";
        BOOL control = NO;
        if (dockHit) {
            label = @"Dock";
        } else if (owner > 0 && layer && layer.intValue == 0) {
            NSString *bundle = [NSRunningApplication runningApplicationWithProcessIdentifier:owner].bundleIdentifier;
            if ([bundle isEqual:@"com.apple.finder"] || [bundle isEqual:@"com.apple.systempreferences"]) {
                label = [bundle isEqual:@"com.apple.finder"] ? @"Finder" : @"Configurări";
                control = YES;
            }
        }
        CGPoint point = quartzPoint(mouse, CGRectGetHeight(CGDisplayBounds(CGMainDisplayID())));
        // AX does a separate hit test in top-left global coordinates, independently of Dock's window bounds.
        id item = systemAX ? itemAtPoint((__bridge AXUIElementRef)systemAX, pid, point) : nil;
        if (item && items.count < 3 && ![items containsObject:item]) [items addObject:item];
        NSUInteger index = item ? [items indexOfObject:item] : NSNotFound;
        NSUInteger tag = index == NSNotFound ? 0 : index + 1;
        BOOL over = dockHit || item != nil;
        if (dockHit) dockCount++;
        if (item) axCount++;
        if (owner <= 0) unknownCount++;
        if (over && controlCount > 0) crossed = YES;
        if (control && !item) { controlCount++; if (crossed) returned = YES; }
        if (number != previousNumber || ![label isEqual:previousLabel] || previousItem != tag) {
            printf("GG_HIT t=%.2f quartz=%.1f,%.1f țintă=%s fereastră=%ld layer=%s",
                   elapsed, point.x, point.y, label.UTF8String, (long)number, layer ? layer.stringValue.UTF8String : "?");
            if (dockHit) {
                CGRect r = CGRectZero;
                NSDictionary *geometry = hit[(__bridge NSString *)kCGWindowBounds];
                if (geometry && CGRectMakeWithDictionaryRepresentation((__bridge CFDictionaryRef)geometry,&r)) {
                    printf(" bounds="); printRect(r);
                }
            }
            if (item) printf(" AX=element_Dock:%lu", (unsigned long)tag);
            puts("");
            previousNumber = number; previousLabel = label; previousItem = tag;
        }
        for (NSUInteger i = 0; i < items.count; i++) {
            CGRect r = CGRectZero;
            if (!axBounds((__bridge AXUIElementRef)items[i], &r)) continue;
            CGFloat extent = edge == Bottom ? CGRectGetWidth(r) : CGRectGetHeight(r);
            if (i == index && CGRectContainsPoint(r,point)) maxOver[i] = MAX(maxOver[i],extent);
            if (control && !item && !CGRectContainsPoint(CGRectInset(r,-64,-64),point))
                minAway[i] = MIN(minAway[i],extent);
        }
        [NSThread sleepForTimeInterval:0.23];
    }}
    if (!isUserDock(pid)) { puts("GG_HOVER Procesul Dock s-a schimbat în timpul probei."); return 3; }
    printf("GG_HOVER eșantioane mouseDown_Dock=%d fereastră_control=%d țintă_neidentificată=%d element_AX_Dock=%d\n",
           dockCount,controlCount,unknownCount,axCount);
    printf("GG_HOVER traseu fereastră→Dock=%s | revenire în fereastră=%s\n",
           crossed ? "observat" : "neconfirmat", returned ? "observată" : "neconfirmată");
    BOOL paired = NO;
    for (NSUInteger i = 0; i < items.count; i++) if (maxOver[i] > 0 && minAway[i] < CGFLOAT_MAX) {
        paired = YES;
        printf("GG_HOVER item=%lu dimensiune_AX_sub_cursor_max=%.1f dimensiune_AX_departe_min=%.1f diferență=%.1f puncte\n",
               (unsigned long)i+1,maxOver[i],minAway[i],maxOver[i]-minAway[i]);
    }
    if (!paired) puts("GG_HOVER Dimensiunea aceluiași element deasupra și în afara Dock-ului nu a putut fi comparată.");
    puts("GG_HOVER Geometria ferestrei sau a elementului AX singură nu confirmă pixelii pictogramei.");
    return crossed && returned ? 0 : 3;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        setvbuf(stdout, NULL, _IOLBF, 0);
        if (argc != 2) { puts("GG_HOVER Utilizare: dock-hover-x86_64 PID_Dock"); return 2; }
        char *end = NULL;
        long p = strtol(argv[1], &end, 10);
        if (!end || *end || p <= 1 || p > INT_MAX || !isUserDock((pid_t)p)) {
            puts("GG_HOVER PID-ul Dock al acestui cont nu a fost confirmat."); return 2;
        }
        return observe((pid_t)p);
    }
}
