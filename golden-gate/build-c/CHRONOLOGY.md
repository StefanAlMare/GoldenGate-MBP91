# Build C — chronological engineering log

[**English**](CHRONOLOGY.md) · [**Română**](CHRONOLOGY.ro.md) · [Overview](README.md)

**Period:** 20–23 November 2026, starting after the last published A/B hardware milestone. Target: **MacBookPro9,1**, macOS **27.2.1 (26B131)**. Entries are in execution order, including failures, recoveries, and unfinished work. Sources: Work2/Work3 handover, local CLT/LD test reports, Xcode proof document (23 November), operator Clang report and macOS physical observations. This is not a claim of a turnkey installer.

| Date | Step | Operation | Recorded outcome |
|:--|:--|:--|:--|
| **20 Nov** | C-01 | Continue generation C assembly; isolate missing original plist in `AirportBrcmFixup` verification | Build-path repair performed; C subsequently booted |
| **21 Nov** | C-02 | Inspect official CLT 27.2, xcrun, Apple clang 21 and SDK; verify HAO private Python 3.12.14 x86_64 | Baseline established |
| **21 Nov** | C-03 | Create typed `xcrun_main` entry; correct synthetic dyld provider identity; extend guest `RTLD_DEFAULT` lookups | Three pinned runtime adaptations; verified privately |
| **21 Nov** | C-04 | Verify HAO-supported C, C++, `make`, Python native extension and tool discovery in a user-owned CLT environment | Private tests PASS; not yet global |
| **21 Nov** | C-05 | Diagnose Apple `ld` self-exec and `libLTO.dylib` handoff; preserve original linker options, including `-lto_library` | True native linking and LTO PASS in private tests |
| **21 Nov** | C-06 | Add `clang.cfg`, `clang++.cfg` and `clang-cpp.cfg` targeting `x86_64-apple-darwin` by default | 13 focused cases plus baseline PASS; explicit architectures preserved |
| **21 Nov** | C-07 | Stage 80 x86_64 host tool shims + four HAO runtime/trust files; three Clang config files on Data | All **84 System** and **3 CFG** files checksum-verified |
| **21 Nov 23:33** | C-08 | First persistent live HAO patch; `DeRez` replaced then `GetFileInfo changed while patching` | Transaction rolled back; no new boot snapshot |
| **22 Nov** | C-09 | Compare healthy boot snapshot to writable underlying System; analyze APFS compressed inode shared by 78 names | 77 other hardlinks had lost `UF_COMPRESSED`, logically reading empty; root cause documented |
| **22 Nov 00:55** | C-10 | Correct HAO livepatch flag handling and held-inode restoration; regression tests on user-owned APFS fixtures | **8/8 real APFS** and **11/11 offline** tests PASS |
| **22 Nov** | C-11 | On a clone of experimental C, reconstruct the 77 damaged entries as uncompressed hardlinks, install fixed backend and prepared System/Data overlays | HAO exit 0, **84/84 System**, **3/3 CFG** |
| **22 Nov ~02:16** | C-12 | Reboot; read snapshot, SDK, Clang identity and tool discovery from live Golden Gate | Booted CLT snapshot UUID `672C29E6-307D-4E15-B328-714D6C35B005` |
| **22 Nov** | C-13 | Isolate initial global `clang hello.c -o hello` hang; repair LD integration; select new System snapshot | LD snapshot `54804A00-E81C-4290-A2B8-33C601D45823` selected; later C/C++/LTO/make/Python matrix PASS |
| **22 Nov** | C-14 | Set up Xcode 27.2 GUI under HAO; inspect Locations selector and first-launch packages | GUI opens; initial package service `PKInstallErrorDomain Code=201`, first-launch status 69; later CLI builds resolve the important build workflow |
| **23 Nov 13:59** | C-15 | Build a fresh Xcode C project through `xcodebuild`, native x86_64 Swift Build 6.4.2 and Apple CLT linker | `** BUILD SUCCEEDED **`; x86_64 code ran with `n=3589 sum=6442255` |
| **23 Nov** | C-16 | Xcode builds four additional projects: C++17, Objective-C, Swift, AppKit | All four exit 0; console examples run, AppKit bundle inspected |
| **23 Nov** | C-17 | Initial ARM64/Universal 2 Xcode batch requests `generic/platform=macOS` | Ten exit 70 **before compilation** because of unsupported destination |
| **23 Nov** | C-18 | Retry using compatible `My Mac` destination; target `ARCHS=arm64` or `ARCHS=x86_64 arm64`, `ONLY_ACTIVE_ARCH=NO` | **10/10 builds PASS**: five ARM64 and five Universal 2 across C/C++/ObjC/Swift/AppKit; `lipo` and Mach-O confirm slices |
| **23 Nov** | C-19 | Separate Apple Clang direct cross-architecture build test, without Xcode project | **ARM64-direct PASS; Universal2-direct PASS**, operator output; detailed `Raport.jsonl` kept locally on iMac |
| **22–23 Nov** | C-20 | Install MacPorts 2.12.7 and build sources for Darwin 27 x86_64 through adapted CLT/HAO | Several ports have installed according to operator; other source builds still active; final inventory pending |
| **23 Nov** | C-21 | Evaluate newer upstream installer/EFI and Metal r12 changes in private builder sources; investigate WeatherKit/VFX and EFI separately | Selected source tests PASS; **not** promoted to a new booted C image, not Weather/EFI fixes |

## Important interpretation

The new CLT snapshot is **confirmed booted**. The additional LD snapshot was recorded `RootTo=true`, but its own original record included `reboot_performed=false`; do not substitute snapshot selection for post-restart proof. The subsequent ordinary compiler test matrix is independently reported PASS.

`System` patches and `Data` modifications are distinct: Xcode, CLT installation, Clang CFG, Python, MacPorts and HAO receipts are on Data, so reverting only the System snapshot is not full rollback.

An ARM64 binary **compiled** on Intel is not evidence of native execution on Apple Silicon. Four Universal 2 command-line examples were **executed on Intel**. AppKit bundles were built and inspected, but not launched as GUI apps in that matrix.

Source attribution: [lythka HAO](https://github.com/lythka/hao-patcher), [lythka runtime](https://github.com/lythka/hao-runtime), OpenCore/OCLP; MacBookPro9,1 adaptation and physical tests by [StefanAlMare](https://github.com/StefanAlMare) with Codex assistance. Public proof tables: [Toolchain](TOOLCHAIN-EVIDENCE.md) and [Xcode](XCODE.md).