# CLT 27.2 / HAO / Apple Clang — physical test evidence

[**Build C**](README.md) · [Chronology](CHRONOLOGY.md) · [Xcode matrix](XCODE.md) · [MacPorts](MACPORTS.md)

**Test target:** 15-inch MacBookPro9,1 (Mid 2012), Intel Ivy Bridge, dual GPU, Golden Gate C **27.2.1 / 26B131**. All hashes are SHA-256 unless noted. This file quotes **selected proof lines**, not complete logs or Apple binaries.

## 1. System deployment and post-reboot validation

The staged manifest had **84 System files** (80 HAO-adapted tool shims and four runtime/trust or activation files) plus **three Data-side Clang CFGs**. The SHA/size gate reported:

```text
System: 84/84
Clang CFG: 3/3
Files: 88/88
RESULT: PASS
```

The corrected HAO installation reported `OFFICIAL HAO EXIT=0`, `SYSTEM POST-APPLY VERIFIED — 84/84`, `DATA CFG INSTALLED — 3/3`, and selected a new APFS System snapshot. **After restarting the real Mac**, the following were observed:

```text
ProductVersion: 27.2.1
BuildVersion: 26B131
APFS Snapshot UUID: 672C29E6-307D-4E15-B328-714D6C35B005
xcrun --find clang: /Library/Developer/CommandLineTools/usr/bin/clang
xcrun --sdk macosx --show-sdk-version: 27.2
Apple clang version 21.0.0 (clang-2100.4.1.1)
Target: x86_64-apple-darwin
Configuration file: /Library/Developer/CommandLineTools/usr/bin/clang.cfg
```

### Subsequent linker repair: physical result matrix

The first ordinary `clang hello.c -o hello` command hung. A separate LD integration on the C clone selected `com.apple.bless.7AA57939-77F8-4658-B20F-2CB5ADBCA2A7` (UUID `54804A00-E81C-4290-A2B8-33C601D45823`). The original verification record included `reboot_performed=false` / `ready=false` for snapshot promotion **but** a postboot execution test matrix of normal commands passed:

| Command class | Captured status / output |
|:--|:--|
| `/usr/bin/xcrun --find clang` | **PASS** |
| `/usr/bin/xcrun --sdk macosx --show-sdk-version` | **PASS**, `27.2` |
| `/usr/bin/clang -print-target-triple` | **PASS**, `x86_64-apple-darwin` |
| `/usr/bin/clang hello.c -o hello`, then run | **PASS**, `GG_POSTBOOT_NATIVE_OK` |
| `/usr/bin/clang++ hello.cpp -o cpp`, then run | **PASS**, `GG_CPP_NATIVE_OK` |
| `clang -flto -c` and `clang -flto` link, then run | **PASS**, `GG_POSTBOOT_NATIVE_OK` |
| `/usr/bin/make` plus produced executable | **PASS**, `GG_POSTBOOT_NATIVE_OK` |
| `python3 -I -B` with ctypes, SQLite and SSL checks | **PASS**, Python **3.14.10**, `x86_64`, OpenSSL 3.5.9 |
| `/opt/local/bin/port version` | **PASS**, `Version: 2.12.7` |

The original file `GoldenGate-C-LD-verify-20261122-041834-f7bb5acb.txt` contains the process matrix, Mach-O slices and output evidence. The `C`, `C++`, LTO and make results are **native executable runtime proof**, not just the compiler printing its version.

## 2. Direct Apple Clang: x86_64, ARM64 and Universal 2

On **23 November 2026**, an additional test **outside Xcode's project build workflow** ran on the same MacBook via an iMac launch command:

```text
/bin/sh /private/tmp/GoldenGate-Link-nr10q6g3/Clang-ARM-Universal.command

ARM64-direct PASS
Universal2-direct PASS
Clang direct a trecut pentru ARM64 și Universal 2.
```

Report recorded locally on the iMac at `/private/tmp/GoldenGate-C-Clang.HcenV1/Raport.jsonl`. These outcomes were supplied directly by the operator. **The detailed JSONL was not transferred into this GitHub revision**, so the direct ARM64 and Universal 2 test is marked **operator-verified PASS** (not independently re-parsed here). The Xcode `lipo`-checked Universal 2 matrix has separate, preserved physical evidence: [Xcode](XCODE.md).

**Important:** Clang building an ARM64 image on Intel is not proof of execution on Apple Silicon. Verified native execution is for x86_64, plus the x86_64 slice of the Universal 2 console binaries under Xcode.

## 3. HAO compressed-hardlink incident and correction

| Item | Exact evidence |
|:--|:--|
| Failed livepatch receipt | `hao-20261121-233304`, error `usr/bin/GetFileInfo changed while patching` |
| Original shared inode | **78 hardlinks**, `UF_COMPRESSED` present (flag bit `0x20`), logical data 200,560 bytes |
| Failure symptom | One target (`DeRez`) restored separately; 77 remaining names shared inode with flags 0 and apparent zero-length contents |
| Healthy original logical SHA | `ed6f5284033aa2aae6a58427c25ba3ab119947b40365627b24e5d51a4b70a1cd` |
| Root cause | Original HAO backend `chflags(..., 0, follow_symlinks=False)` cleared the compression bit for all hardlink peers before one path was replaced |
| Fix | Preserve existing storage bit; hold old inode descriptor and restore flags for remaining links through replacement/rollback |
| Validation | **8/8 physical private APFS tests**, **11/11 offline regression tests**, then successful global overlay on **experimental C clone** |
| Scope limit | Does **not** restore initial hardlink topology, full ACL/xattrs or Data by a snapshot rollback |

**Patch source:** [hao-livepatch-compression.patch](patches/hao-livepatch-compression.patch), SHA-256 `0e7c507e1b1b77ce45523f96f06b93da25a6e56a27342a0b9172055f383f2581`. It was generated from the captured original source, is pinned to that version and requires rebasing/tests before use with newer upstream HAO.

## 4. Provenance pins

| Component | SHA-256 |
|:--|:--|
| Original `livepatch.py` captured from C | `c1bddd3e3cd76c513e6a131ea5ce5a3a898afcb04ded92395fda7a9bcc32d56a` |
| Fixed `livepatch.py` | `271a542d21e5817553066dee20b5b33c6044cbb1b34ef9dc4085bee2250ce440` |
| CLT staging manifest | `bcfe4f590d36fee1f206206c1a8d1036ee5af39356c3dab5fbe0fb5342ca4581` |
| Toolchain HAO runtime candidate (1,642,272 bytes) | `59e5fdf95a166a5b30dbc6250eb3842400c3d24818d858fe69a16878c9021fcc` |
| Work2/Work3 handover ZIP, retained offline | `b8dfd5b69e3bfd244fa00799c8ec97983af93c3ee9bbaa54a1d5edc737c9f1c4` |
| Work2 milestone ZIP, retained offline | `0d57ccaf3d464a4cdd86601ca00e04fb25a267eb3f8fc8d4d1428d80e824958e` |

### Source-to-result chain

**Original HAO + local xcrun/dyld/RTLD adaptations → private Intel + LTO proofs → official compiler CFGs → validated 84+3 staging → APFS fix → C snapshot boot → normal C/C++/LTO/make execution → Xcode cross-architecture builds.**

Original logs and archives are retained outside GitHub. No third-party Apple executable or user-private diagnostic dump is reproduced here.
