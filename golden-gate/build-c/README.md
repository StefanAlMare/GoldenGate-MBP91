# Golden Gate — Build C | 23 November 2026

[**English**](README.md) · [**Română**](README.ro.md) · [Project home](../../README.md)

## A working development toolchain on a 2012 Intel Mac

![macOS](https://img.shields.io/badge/macOS-27.2.1_26B131-315d85?style=flat-square)
![Clang](https://img.shields.io/badge/Clang_21-Intel_ARM64_Universal_2-247a5a?style=flat-square)
![Xcode](https://img.shields.io/badge/Xcode_27.2-10%2F10_ARM%2BUniversal-247a5a?style=flat-square)
![MacPorts](https://img.shields.io/badge/MacPorts_2.12.7-Source_builds_underway-b77d31?style=flat-square)

> **Physical test:** MacBookPro9,1 (15-inch Mid 2012), Ivy Bridge with Intel HD 4000, NVIDIA GT 650M and GMUX. Golden Gate 27.2.1 (26B131) boots from a test USB SSD. Original HAO was developed by [lythka](https://github.com/lythka/hao-patcher); this is an independent MacBookPro9,1 adaptation, not an official Intel macOS release.

| Milestone | Verified evidence | Limit |
|:--|:--|:--|
| **CLT 27.2 / Apple Clang 21** | x86_64 C, C++, true LTO, make and executable run PASS; direct ARM64 and Universal 2 compilation PASS | ARM64 native execution on Apple Silicon not tested |
| **Xcode 27.2 (27B52)** | 5 Intel project builds plus **10/10** ARM64 and Universal 2 builds; C, C++17, Objective-C, Swift and AppKit | CLI `xcodebuild` proven, GUI interactive `⌘B` remains to test |
| **MacPorts 2.12.7** | Source build/installation working through adapted HAO/CLT; 138 active ports in an interim operator report; source builds underway | Count is not 138 individually verified source builds or runtime tests; audit pending |
| **HAO / APFS** | Fixed compressed-hardlink backend, recovered 77 names, installed **84/84 System** and **3/3 Clang CFG** files; confirmed boot from new snapshot | Experimental C clone; System and Data have separate rollback needs |

### Documents — in execution order

1. [Chronology (20–23 November)](CHRONOLOGY.md) · [Cronologie în română](CHRONOLOGY.ro.md)
2. [CLT, HAO and direct Clang evidence](TOOLCHAIN-EVIDENCE.md) · [Română](TOOLCHAIN-EVIDENCE.ro.md)
3. [Xcode 27.2 Intel / ARM64 / Universal 2 verification](XCODE.md) · [Română](XCODE.ro.md)
4. [MacPorts progress and updateable package checklist](MACPORTS.md) · [Română](MACPORTS.ro.md) · [Machine-readable port ledger](ports.csv)
5. [Source-only HAO APFS correction](patches/hao-livepatch-compression.patch) and [read-only future inventory helper](collect-macports.sh)

**Evidence policy:** PASS indicates preserved physical or operator test output. An ongoing MacPorts compile is not called a completed installation. Xcode building ARM64 code on Intel does **not** establish native execution on Apple Silicon. See the [existing Stage 1 gallery](../GALLERY.md) for authentic hardware screenshots.

**Credits:** [lythka's HAO](https://github.com/lythka/hao-patcher), [HAO runtime](https://github.com/lythka/hao-runtime), OCLP/OpenCore; MacBookPro9,1 adaptation and real-device validation by [StefanAlMare](https://github.com/StefanAlMare), assisted by Codex. Apple proprietary software, private logs and installation images are not redistributed.
