#include <CoreFoundation/CoreFoundation.h>
#include <math.h>
#include <stdio.h>
#include <string.h>
#include <sys/sysctl.h>

typedef struct {
    CFStringRef key;
    CFTypeRef wanted;
} Preference;

static double number(CFStringRef domain, CFStringRef key, double fallback) {
    CFTypeRef value = CFPreferencesCopyAppValue(key, domain);
    double result;
    if (!value) return fallback;
    int ok = CFGetTypeID(value) == CFNumberGetTypeID() &&
             CFNumberGetValue((CFNumberRef)value, kCFNumberDoubleType, &result) && isfinite(result);
    CFRelease(value);
    return ok ? result : fallback;
}

static int matches(CFStringRef domain, Preference pref) {
    CFTypeRef value = CFPreferencesCopyAppValue(pref.key, domain);
    if (!value) return 0;
    int ok = CFGetTypeID(value) == CFGetTypeID(pref.wanted) && CFEqual(value, pref.wanted);
    CFRelease(value);
    return ok;
}

static void report_key(const char *message, CFStringRef key) {
    char name[128] = "?";
    CFStringGetCString(key, name, sizeof(name), kCFStringEncodingUTF8);
    fprintf(stderr, "GG_DOCK %s: %s.\n", message, name);
}

int main(int argc, char **argv) {
    if (argc != 1) return 2;
    (void)argv;
#ifdef GG_DOCK_TEST_DOMAIN
    // Only the fixture build accepts a different domain, fixed at compile time.
    CFStringRef domain = CFSTR(GG_DOCK_TEST_DOMAIN);
#else
    CFStringRef domain = CFSTR("com.apple.dock");
    char model[64] = {0};
    size_t size = sizeof(model);
    if (sysctlbyname("hw.model", model, &size, NULL, 0) || strcmp(model, "MacBookPro9,1")) {
        fputs("GG_DOCK Acest program cere MacBookPro9,1.\n", stderr);
        return 2;
    }
#endif
    double base = number(domain, CFSTR("tilesize"), 48);
    double large = number(domain, CFSTR("largesize"), 0);
    int adjust_base = base > 112 || base <= 0;
    int normal = base <= 0 ? 48 : 96;
    if (adjust_base) base = normal;
    double desired = large < base + 16 || large > 128 ? fmax(96, ceil(base + 16)) : large;
    CFNumberRef size_pref = CFNumberCreate(NULL, kCFNumberDoubleType, &desired);
    CFNumberRef base_pref = CFNumberCreate(NULL, kCFNumberIntType, &normal);
    Preference prefs[4] = {
        {CFSTR("orientation"), CFSTR("bottom")}, {CFSTR("magnification"), kCFBooleanTrue},
        {CFSTR("largesize"), size_pref}
    };
    int count = 3;
    if (adjust_base) prefs[count++] = (Preference){CFSTR("tilesize"), base_pref};

    CFMutableDictionaryRef updates = CFDictionaryCreateMutable(NULL, count,
        &kCFTypeDictionaryKeyCallBacks, &kCFTypeDictionaryValueCallBacks);
    for (int i = 0; i < count; ++i) {
        if (matches(domain, prefs[i])) continue;
        if (CFPreferencesAppValueIsForced(prefs[i].key, domain)) {
            report_key("Preferință administrată", prefs[i].key);
            return 3;
        }
        CFDictionarySetValue(updates, prefs[i].key, prefs[i].wanted);
    }
    CFIndex changes = CFDictionaryGetCount(updates);
    if (changes) {
        CFPreferencesSetMultiple(updates, NULL, domain, kCFPreferencesCurrentUser, kCFPreferencesAnyHost);
        if (!CFPreferencesAppSynchronize(domain)) {
            fputs("GG_DOCK Scrierea preferințelor nu s-a sincronizat.\n", stderr);
            return 3;
        }
    }
    for (int i = 0; i < count; ++i) {
        if (!matches(domain, prefs[i])) {
            report_key("Valoarea sau tipul diferă după recitire", prefs[i].key);
            return 3;
        }
    }
    printf("GG_DOCK Preferințe confirmate: jos, mărire %.1f → %.1f pt, %ld valori actualizate.\n",
           base, desired, (long)changes);
    CFRelease(updates);
    CFRelease(size_pref);
    CFRelease(base_pref);
    return 0;
}
