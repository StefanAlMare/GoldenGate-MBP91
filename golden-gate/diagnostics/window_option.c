#include <CoreGraphics/CoreGraphics.h>
#include <dlfcn.h>
#include <mach-o/loader.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

/* Match the CoreGraphics import and the width tested by WindowManager
 * 26B131 at 0x10016bce4. Its native Intel implementation returns a byte. */
#if defined(__arm64__)
#define ARCH "arm64"
extern uint32_t modifier(int32_t, int32_t) __asm__("_CGSInputModifierKeyState");
#else
#define ARCH "x86_64"
extern uint8_t modifier(int32_t, int32_t) __asm__("_CGSInputModifierKeyState");

static int print_uuid(void) {
    const char *path = "/System/Library/PrivateFrameworks/SkyLight.framework/Versions/A/SkyLight";
    void *lib = dlopen(path, RTLD_LAZY | RTLD_LOCAL);
    Dl_info info = {0};
    if (!lib || dlsym(lib, "SLSInputModifierKeyState") != (void *)modifier ||
        !dladdr((void *)modifier, &info) || !info.dli_fname || strcmp(info.dli_fname, path)) return 2;
    const struct mach_header_64 *hdr = info.dli_fbase;
    if (!hdr || hdr->magic != MH_MAGIC_64 || hdr->cputype != CPU_TYPE_X86_64) return 2;
    const uint8_t *pos = (const uint8_t *)(hdr + 1);
    size_t left = hdr->sizeofcmds;
    for (uint32_t i = 0; i < hdr->ncmds && left >= sizeof(struct load_command); i++) {
        const struct load_command *cmd = (const struct load_command *)pos;
        if (cmd->cmdsize < sizeof(*cmd) || cmd->cmdsize > left) return 2;
        if (cmd->cmd == LC_UUID && cmd->cmdsize == sizeof(struct uuid_command)) {
            const struct uuid_command *uuid = (const struct uuid_command *)cmd;
            for (size_t j = 0; j < sizeof(uuid->uuid); j++) printf("%02x", uuid->uuid[j]);
            putchar('\n');
            return 0;
        }
        pos += cmd->cmdsize;
        left -= cmd->cmdsize;
    }
    return 2;
}
#endif

/* Only read the public Option flag. Zero means the public sources disagree. */
static int public_option(void) {
    CGEventFlags session = CGEventSourceFlagsState(kCGEventSourceStateCombinedSessionState);
    CGEventFlags hid = CGEventSourceFlagsState(kCGEventSourceStateHIDSystemState);
    if ((session ^ hid) & kCGEventFlagMaskAlternate) return 0;
    return session & kCGEventFlagMaskAlternate ? 1 : -1;
}

int main(int argc, char **argv) {
#if defined(__x86_64__)
    if (argc == 2 && strcmp(argv[1], "--uuid") == 0) return print_uuid();
#endif
    bool held = argc == 2 && strcmp(argv[1], "--held") == 0;
    if (argc != 1 && !held) return 2;
    CGDirectDisplayID display = CGMainDisplayID();
    if (!display || !CGDisplayIsOnline(display)) {
        puts("GG_WINDOW_OPTION inconcludent=ecran_indisponibil");
        return 2;
    }
    unsigned matched = 0, wrong_byte = 0, high_only = 0;
    for (unsigned i = 0; i < 6; i++) {
        int before = public_option();
        uint32_t word = modifier(0, 3);
        int after = public_option();
        if (before == (held ? 1 : -1) && before == after) {
            matched++;
            bool low = (word & 255) != 0;
            if (low != held) wrong_byte++;
            else if (!low && word) high_only++;
        }
        usleep(50000);
    }
    printf("GG_WINDOW_OPTION arch=%s option=%s public=%u octet_diferit=%u numai_sus=%u\n",
           ARCH, held ? "apasat" : "liber", matched, wrong_byte, high_only);
    if (matched < 4 || wrong_byte) return 2;
    if (high_only == matched) return 1;
    return high_only == 0 ? 0 : 2;
}
