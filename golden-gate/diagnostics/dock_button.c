#include <CoreGraphics/CoreGraphics.h>
#include <dlfcn.h>
#include <mach-o/loader.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

/* The 26B131 ARM Dock tests W0 after CGSInputButtonState(1,0).
 * Intel SkyLight defines only AL on its valid-connection path. */
#if defined(__arm64__)
#define ARCH_NAME "arm64"
extern uint32_t dock_button(int32_t, uint32_t) __asm__("_CGSInputButtonState");
#else
#define ARCH_NAME "x86_64"
extern uint8_t dock_button(int32_t, uint32_t) __asm__("_CGSInputButtonState");
#endif

#if defined(__x86_64__)
static int skylight_uuid(void) {
    const char *path = "/System/Library/PrivateFrameworks/SkyLight.framework/Versions/A/SkyLight";
    void *lib = dlopen(path, RTLD_LAZY | RTLD_LOCAL);
    void *canonical = lib ? dlsym(lib, "SLSInputButtonState") : NULL;
    Dl_info info = {0};
    if (canonical != (void *)dock_button || !dladdr(canonical, &info) ||
        !info.dli_fname || strcmp(info.dli_fname, path)) return 2;
    const struct mach_header_64 *hdr = info.dli_fbase;
    if (!hdr || hdr->magic != MH_MAGIC_64 || hdr->cputype != CPU_TYPE_X86_64) return 2;
    const uint8_t *pos = (const uint8_t *)(hdr + 1);
    const uint8_t *end = pos + hdr->sizeofcmds;
    for (uint32_t i = 0; i < hdr->ncmds; i++) {
        if ((size_t)(end - pos) < sizeof(struct load_command)) return 2;
        const struct load_command *cmd = (const struct load_command *)pos;
        if (cmd->cmdsize < sizeof(*cmd) || cmd->cmdsize > end - pos) return 2;
        if (cmd->cmd == LC_UUID && cmd->cmdsize == sizeof(struct uuid_command)) {
            const struct uuid_command *id = (const struct uuid_command *)pos;
            for (size_t j = 0; j < sizeof(id->uuid); j++) printf("%02x", id->uuid[j]);
            putchar('\n');
            return 0;
        }
        pos += cmd->cmdsize;
    }
    return 2;
}
#endif

int main(int argc, char **argv) {
#if defined(__x86_64__)
    if (argc == 2 && !strcmp(argv[1], "--uuid")) return skylight_uuid();
#else
    (void)argv;
#endif
    if (argc != 1 || !CGMainDisplayID()) {
        puts("GG_BUTTON inconclusive=no_display_or_invalid_arguments");
        return 2;
    }
    unsigned released = 0, byte_pressed = 0, false_pressed = 0;
    for (unsigned i = 0; i < 6; i++) {
        bool before = CGEventSourceButtonState(kCGEventSourceStateCombinedSessionState, kCGMouseButtonLeft);
        uint32_t state = dock_button(1, 0);
        bool after = CGEventSourceButtonState(kCGEventSourceStateCombinedSessionState, kCGMouseButtonLeft);
        if (!before && !after) {
            released++;
            if ((state & 255u) != 0) byte_pressed++;
            else if (state != 0) false_pressed++;
        }
        usleep(50000);
    }
    printf("GG_BUTTON arch=%s released=%u low_byte_pressed=%u false_pressed=%u\n",
           ARCH_NAME, released, byte_pressed, false_pressed);
    if (released < 4 || byte_pressed) return 2;
    if (false_pressed == released) return 1;
    return false_pressed == 0 ? 0 : 2;
}
