# Xcode 27.2 on a real 2012 Intel MacBook — build proofs

[**Overview**](README.md) · [Chronology](CHRONOLOGY.md) · [Clang evidence](TOOLCHAIN-EVIDENCE.md)

**Hardware/software:** MacBookPro9,1; Golden Gate 27.2.1 (26B131); **Xcode 27.2 (27B52)**; Apple Clang 21.0.0 / macOS 27.2 SDK; HAO bridging Apple ARM-only components onto Intel. The build service is **Swift Build 6.4.2 compiled for x86_64** (source commit `2d847030c63961cb1cf8cbb6ad2bc7245fdfeb09`). The Apple linker is CLT 27.2 adapted for Golden Gate.

![Intel](https://img.shields.io/badge/Xcode_x86__64-5%2F5_PASS-247a5a?style=flat-square) ![ARM and Universal](https://img.shields.io/badge/ARM64%2BUniversal_2-10%2F10_PASS-247a5a?style=flat-square) ![GUI](https://img.shields.io/badge/GUI-launches-⌘B_pending-b77d31?style=flat-square)

## 1. First real Xcode project — 23 November, 13:59 Romania

A new `ProbaIntel.xcodeproj` C target was compiled and linked from the actual `xcodebuild` client. Result:

```text
** BUILD SUCCEEDED **
Build service: Swift Build 6.4.2 — x86_64
Executable: Mach-O x86_64, 9,120 bytes
model=MacBookPro9,1 arch=x86_64 n=3589 sum=6442255
```

Arithmetic cross-check: 3,589 × 3,590 / 2 = **6,442,255**. Executable SHA-256 `006f17dc90ab2cd0e4f81da182bac35fa9986db55f4a6373009565abaa90ebdb`. Mach-O `LC_BUILD_VERSION` recorded platform macOS, SDK 27.2 and minimum target 15.0. The project completed with linker and client exit 0.

## 2. Four additional Xcode projects: all x86_64 PASS

| Language / target | Observed on MacBookPro9,1 |
|:--|:--|
| **C++17 + libc++** | Compiled/linked and ran: `cpp 4281` |
| **Objective-C + Foundation** | Compiled/linked and ran: `objc 2313` |
| **Swift + Foundation** | `swiftc` compiled and linked, executable ran: `swift 4453` |
| **AppKit macOS application** | Built `ProbaAppKit.app`; Mach-O, bundle ID and AppKit linkage inspected. GUI launch not checked in this batch. |

Batch reference: `20261123T122816Z-dv1284f27d-3bb899d4`. Each `xcodebuild` returned **exit 0**.

## 3. ARM64 and Universal 2: ten successful Xcode builds

Initial generic destination `generic/platform=macOS` was rejected with exit 70 **before compilation** (10 attempts, no build service started). The validated setting uses the locally resolved `My Mac` destination with `ARCHS=arm64` or `ARCHS=x86_64 arm64`, `ONLY_ACTIVE_ARCH=NO`.

A new run on **23 November 2026** completed `TERMINAT | 10/10 confirmate | cod=0`. Five macOS projects were built as **ARM64** and again as **Universal 2**:

| Project | ARM64 output | Universal 2 output | Intel run proof |
|:--|:--:|:--:|:--|
| **C** | PASS | `x86_64 + arm64` | `c 400065` |
| **C++17 + libc++** | PASS | `x86_64 + arm64` | `cpp 2104` |
| **Objective-C + Foundation** | PASS | `x86_64 + arm64` | `objc 1565` |
| **Swift + Foundation** | PASS | `x86_64 + arm64` | `swift 3103` |
| **AppKit application** | PASS | `x86_64 + arm64` | Bundle and AppKit linkage verified; GUI not launched |

In every Universal 2 output, **both Mach-O slice headers and `lipo -archs`** were checked. The original result files' SHA-256 checks agreed with produced binaries. Four universal console programs were executed successfully on Intel; **native Apple Silicon execution has not been tested**.

Evidence bundle retained on the MacBook: `GoldenGate-Xcode-Arhitecturi-b2n9s5h0/Dovezi.zip` and per-target logs/`Rezultate.json`. The 10/10 batch took approximately **27 minutes**.

## 4. Application launch versus build support

`/Applications/Xcode.app` is a Golden Gate native Intel launcher for the original Apple application at `/Applications/Xcode-27.2.app`. The Xcode GUI launches under HAO, and the Locations screen has displayed Xcode **27.2 (27B52)** as the selected command-line tools.

The initial **22 November** First Launch setup did **not** complete: installer service returned `PKInstallErrorDomain Code=201`, and `xcodebuild -checkFirstLaunchStatus` returned exit 69. The subsequent successful CLI project builds on **23 November** establish that the actual build workflow works under the validated configuration; they do not retroactively prove every First Launch optional component or interactive IDE build was fixed.

### Still to prove

- Interactive GUI build with **⌘B**, breakpoint/debug session and a real user Xcode project.
- Running ARM64 outputs **natively on Apple Silicon**.
- Launching the AppKit GUI bundle, simulator/iOS targets, signing and other Apple platform toolchains.
- Independent reproduction on another Intel model, without the development paths and runtime configuration.

**Proof status:** five Intel Xcode builds + ten ARM64/Universal 2 builds **pass**; full Xcode IDE compatibility **remains experimental**.
