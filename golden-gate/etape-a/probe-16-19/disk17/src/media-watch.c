/* Read-only observation of IOMedia in the IOService tree. */
#include <CoreFoundation/CoreFoundation.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/IOKitKeys.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <sys/time.h>

#define RAM_SIZE INT64_C(536870912)

typedef struct {
    uint64_t id, root;
    int64_t size;
    bool whole;
    char *bsd, *path;
} Media;

struct Node { Media media; bool seen; struct Node *next; };
static struct Node *nodes;
static unsigned arrivals, changes, removals;

static struct Node **find(uint64_t id) {
    struct Node **n = &nodes;
    while (*n && (*n)->media.id != id) n = &(*n)->next;
    return n;
}

static void fail_alloc(void) { fputs("media-watch: memory allocation failed\n", stderr); exit(71); }

static char *to_escaped(CFTypeRef s) {
    char *v = NULL;
    if (s && CFGetTypeID(s) == CFStringGetTypeID()) {
        CFIndex size = CFStringGetMaximumSizeForEncoding(CFStringGetLength(s), kCFStringEncodingUTF8) + 1;
        if (size > 0) {
            v = malloc((size_t)size);
            if (!v) fail_alloc();
            if (!CFStringGetCString(s, v, size, kCFStringEncodingUTF8)) { free(v); v = NULL; }
        }
    }
    if (!v) { v = strdup("?"); if (!v) fail_alloc(); }
    for (char *p = v; *p; ++p) if ((unsigned char)*p < 32) *p = '?';
    return v;
}

static void emit(const char *event, const Media *m) {
    struct timeval tv; struct tm utc; char stamp[32];
    gettimeofday(&tv, NULL); gmtime_r(&tv.tv_sec, &utc);
    strftime(stamp, sizeof stamp, "%Y-%m-%dT%H:%M:%S", &utc);
    printf("%s.%06dZ\t%s\tregistry_id=0x%llx\troot_id=0x%llx\tbsd=%s\twhole=%u\tsize=%lld\tpath=%s\n",
           stamp,(int)tv.tv_usec,event,(unsigned long long)m->id,(unsigned long long)m->root,
           m->bsd,(unsigned)m->whole,(long long)m->size,m->path);
}

static void record(Media m) {
    struct Node **slot = find(m.id);
    if (!*slot) {
        *slot = calloc(1,sizeof **slot); if (!*slot) fail_alloc();
        ++arrivals; emit("present",&m);
    } else {
        Media *old = &(*slot)->media;
        if (m.root != old->root || m.whole != old->whole || m.size != old->size ||
            strcmp(m.bsd,old->bsd) || strcmp(m.path,old->path)) {
            ++changes; emit("changed",&m);
        }
        free(old->bsd); free(old->path);
    }
    (*slot)->media=m; (*slot)->seen=true;
}

static void forget(uint64_t id) {
    struct Node **slot=find(id); if (!*slot) return;
    struct Node *n=*slot; *slot=n->next;
    ++removals; emit("removed",&n->media);
    free(n->media.bsd); free(n->media.path); free(n);
}

static bool media_geometry(io_registry_entry_t e, int64_t *size, bool *whole) {
    CFTypeRef b=IORegistryEntryCreateCFProperty(e,CFSTR("Whole"),NULL,0);
    CFTypeRef n=IORegistryEntryCreateCFProperty(e,CFSTR("Size"),NULL,0);
    bool ok=b && CFGetTypeID(b)==CFBooleanGetTypeID() && n && CFGetTypeID(n)==CFNumberGetTypeID() &&
            CFNumberGetValue(n,kCFNumberSInt64Type,size);
    if (ok) *whole=CFBooleanGetValue(b);
    if (n) CFRelease(n);
    if (b) CFRelease(b);
    return ok;
}

static bool is_target_root(int64_t size, bool whole) { return whole && size==RAM_SIZE; }

static uint64_t ancestor_root(io_registry_entry_t e) {
    io_registry_entry_t p=0; uint64_t root=0;
    if (IORegistryEntryGetParentEntry(e,kIOServicePlane,&p)!=KERN_SUCCESS) return 0;
    for (;;) {
        if (IOObjectConformsTo(p,"IOMedia")) {
            bool whole; int64_t size;
            if (media_geometry(p,&size,&whole) && is_target_root(size,whole)) {
                IORegistryEntryGetRegistryEntryID(p,&root);
                IOObjectRelease(p); return root;
            }
        }
        io_registry_entry_t next=0;
        kern_return_t kr=IORegistryEntryGetParentEntry(p,kIOServicePlane,&next);
        IOObjectRelease(p);
        if (kr != KERN_SUCCESS) return 0;
        p=next;
    }
}

static void inspect(io_registry_entry_t e) {
    Media m={0};
    if (IORegistryEntryGetRegistryEntryID(e,&m.id)!=KERN_SUCCESS) return;
    struct Node *existing=*find(m.id); if (existing) existing->seen=true;
    if (!media_geometry(e,&m.size,&m.whole)) return;
    m.root=is_target_root(m.size,m.whole) ? m.id : ancestor_root(e);
    if (!m.root) return;
    CFTypeRef b=IORegistryEntryCreateCFProperty(e,CFSTR("BSD Name"),NULL,0);
    CFStringRef path=IORegistryEntryCopyPath(e,kIOServicePlane);
    m.bsd=to_escaped(b); m.path=to_escaped(path);
    if (b) CFRelease(b);
    if (path) CFRelease(path);
    record(m);
}

static void drain(void *terminated, io_iterator_t it) {
    io_service_t obj;
    while ((obj=IOIteratorNext(it))) {
        if (terminated) {
            uint64_t id;
            if (IORegistryEntryGetRegistryEntryID(obj,&id)==KERN_SUCCESS) forget(id);
        } else inspect(obj);
        IOObjectRelease(obj);
    }
}

static kern_return_t snapshot(void) {
    io_iterator_t it=0;
    CFMutableDictionaryRef match=IOServiceMatching("IOMedia");
    if (!match) return KERN_RESOURCE_SHORTAGE;
    kern_return_t kr=IOServiceGetMatchingServices(MACH_PORT_NULL,match,&it);
    if (kr!=KERN_SUCCESS) return kr;
    for (struct Node *n=nodes;n;n=n->next) n->seen=false;
    drain(NULL,it);
    bool valid=IOIteratorIsValid(it); IOObjectRelease(it);
    if (!valid) return KERN_FAILURE;
    struct Node *n=nodes;
    while (n) { struct Node *next=n->next; if (!n->seen) forget(n->media.id); n=next; }
    return KERN_SUCCESS;
}

static int self_test(void) {
    if (!is_target_root(RAM_SIZE,true) || is_target_root(RAM_SIZE,false) || is_target_root(RAM_SIZE+1,true)) return 1;
    Media m={1,1,RAM_SIZE,true,strdup("disk-test"),strdup("IOService:/test")};
    record(m);
    m.bsd=strdup("disk-test"); m.path=strdup("IOService:/test"); record(m);
    m.bsd=strdup("disk-test2"); m.path=strdup("IOService:/test"); record(m);
    Media c={2,1,1024,false,strdup("disk-tests1"),strdup("IOService:/test/part")};
    record(c); forget(2); forget(1); forget(1);
    return arrivals==2 && changes==1 && removals==2 && !nodes ? 0:1;
}

static double now(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC,&ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec/1e9;
}

int main(int argc,char **argv) {
    setvbuf(stdout,NULL,_IOLBF,0);
    if (argc==2 && !strcmp(argv[1],"--self-test")) return self_test();
    bool once=argc==2 && !strcmp(argv[1],"--once");
    if (!once && argc!=1) { fputs("Usage: media-watch [--once|--self-test]\n",stderr); return 64; }
    printf("IOMedia begin pid-mode=%s whole-bytes=%lld\n",once?"once":"watch",(long long)RAM_SIZE);
    IONotificationPortRef note=NULL; io_iterator_t attached=0,gone=0; CFRunLoopSourceRef source=NULL;
    bool flag=true;
    if (!once) {
        note=IONotificationPortCreate(MACH_PORT_NULL);
        if (note) source=IONotificationPortGetRunLoopSource(note);
        if (source) {
            CFRunLoopAddSource(CFRunLoopGetCurrent(),source,kCFRunLoopDefaultMode);
            kern_return_t a=IOServiceAddMatchingNotification(note,kIOTerminatedNotification,IOServiceMatching("IOMedia"),drain,&flag,&gone);
            if (!a) drain(&flag,gone);
            kern_return_t b=IOServiceAddMatchingNotification(note,kIOFirstMatchNotification,IOServiceMatching("IOMedia"),drain,NULL,&attached);
            if (!b) drain(NULL,attached);
            printf("IOMedia notifications matching=%d terminated=%d\n",b,a);
        } else puts("IOMedia notifications unavailable; polling");
    }
    double end=now()+300;
    int good=0, bad=0;
    do {
        kern_return_t kr=snapshot();
        if (!kr) ++good; else if (++bad==1) printf("IOMedia registry query failed: 0x%x\n",kr);
        if (once) break;
        if (source) CFRunLoopRunInMode(kCFRunLoopDefaultMode,2.0,false);
        else { struct timespec delay={2,0}; nanosleep(&delay,NULL); }
    } while(now()<end);
    printf("IOMedia end queries_ok=%d queries_failed=%d arrivals=%u changes=%u removals=%u\n",good,bad,arrivals,changes,removals);
    if (attached) IOObjectRelease(attached);
    if (gone) IOObjectRelease(gone);
    if (source) CFRunLoopRemoveSource(CFRunLoopGetCurrent(),source,kCFRunLoopDefaultMode);
    if (note) IONotificationPortDestroy(note);
    return good?0:1;
}
