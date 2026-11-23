# Engineering dossier — Golden Gate / MacBookPro9,1

**[English project homepage](../README.md) · [Română](../README.ro.md) · [Physical test record](STAGE-1.md)**

This document separates **verified hardware measurements**, **operator observations**, **build provenance**, and **unresolved issues**. The subject is the 15-inch MacBookPro9,1 adaptation of [lythka's HAO](https://github.com/lythka/hao-patcher), not the upstream single-GPU MacBookPro9,2.

> [!IMPORTANT]
> **Stage C technical supplement (21–23 November 2026):** [Chronology](build-c/CHRONOLOGY.md), [CLT/Clang evidence](build-c/TOOLCHAIN-EVIDENCE.md), [Xcode Intel/ARM64/Universal 2](build-c/XCODE.md), and the [live MacPorts ledger](build-c/MACPORTS.md). The measurements below describe the earlier hardware A/B milestone and remain in chronological context.

## The engineering question

The 13-inch MacBookPro9,2 has Ivy Bridge and Intel HD 4000. The 15-inch MacBookPro9,1 adds NVIDIA GT 650M and GMUX. Can Golden Gate 27 run with the two GPUs and the original display-switching architecture?

Our design kept Golden Gate on a separate **external SSD**, preserving a functional internal Tahoe/OCLP system for development and recovery.

## Pinned inputs and provenance

| Input | Identified source |
|---|---|
| Test computer | MacBookPro9,1, i7-3615QM, HD 4000, GT 650M (512 MB), GMUX |
| macOS | Golden Gate 27.2.1, build 26B131 |
| Intel donor | Tahoe 26.7.3, build 25G342 |
| Original HAO Patcher | [6bd75aab112d1078acd8e75180eb510672461365](https://github.com/lythka/hao-patcher/commit/6bd75aab112d1078acd8e75180eb510672461365) |
| Local HAO Runtime | [1547dcb4e19a2ab0843086e3288223f998507a4c](https://github.com/lythka/hao-runtime/commit/1547dcb4e19a2ab0843086e3288223f998507a4c) |
| Boot foundation | OpenCore 1.0.5 and OCLP support |
| Image A, original raw file | SHA256 <code>52a930a84a37b3fdd3443636426503c716e723f7c781332d605f964ad3922f35</code> |
| Image B, after assembly | SHA256 <code>35eeb62d4558ac7e094d40841e8964778001fe0cf499bce1c760a9cb5cb1c465</code> |
| Adaptation source | [Initial builder snapshot](https://github.com/StefanAlMare/GoldenGate-MBP91/tree/0b3d86aba06b3c0d85fc9436f4395194664e75fe) |

The original Image A SHA256 identifies **80 GiB before GPT/APFS expansion**, not the final resized 256 GB disk. The host builder used Tahoe on an Intel iMac20,2 Hackintosh with Xcode 26.6; upstream release proof refers to a different Xcode toolchain.

## Development stages

| Steps | Work performed | Evidence |
|---|---|---|
| **2–4** | MacBookPro9,1 hardware profile, OCLP Intel/NVIDIA/GMUX selection and OpenCore EFI | <code>ocvalidate</code> passed |
| **5–6** | Golden Gate sources, Tahoe Intel/KDK donor packages, DriverKit, Recovery and boot files | Input hashes and donor checks |
| **7–8** | Locally built HAO runtime, HaoExec and embedded stubs for roughly 963 ARM-only executables | Host tests and packaging checks, **not complete external ABI coverage** |
| **9–11** | Metal and graphics preparations, Intel/Kepler kernel extensions, AppleMuxControl and kernel collections | Static file, build and binding checks |
| **12** | 80 GiB APFS image, System/Data, Preboot, EFI | 31 assembly stages completed; EFI validated |
| **13** | Image written to external SSD and fully read back; GPT/APFS extended | 80 GiB readback hash matched |

[Original sources and receipts](etape-a/INDEX.md).

## Setup Assistant — the first blocker

The original boot progressed to loginwindow but stalled near 60%. The system was processing input and Ethernet traffic. Diagnostic stacks showed DiskImages, Disk Arbitration and FSKit waiting while the temporary Setup Assistant RAM disk was not partitioned.

The decisive observed test condition was **excluding both the internal NTFS and exFAT volumes from automount with UUID-specific <code>ro,noauto</code> rules**. Setup Assistant proceeded, an account was created, and desktop sign-in succeeded after reboot.

This is an **observed machine-specific result**, not proof that either individual volume alone caused the issue.

## Dual-GPU: distinguish measurements from observations

**Instrumented:** internal LCD was identified under Intel HD 4000. The GT 650M was selected explicitly in a Metal probe, cleared a 4 × 4 texture and returned **16/16 correct pixels** on readback. That is a specific render-pass success, not a complete rendering test.

**Observed by StefanAlMare on the real laptop:**

- Built-in screen alone ordinarily uses **Intel HD 4000**.
- Connecting an external monitor via the working direct adapter switches **both internal and external screens to NVIDIA**.
- Disconnecting that display through the direct path restores **Intel** on the internal screen.
- Opening **Photos** can activate **NVIDIA for the internal screen even without an external monitor**.
- A monitor connected through a **Thunderbolt HDMI hub** worked if attached at startup, but a previous hub-HDMI removal **blacked out both screens**.

These results establish **observed graphics switching**, while hardware stability, all GMUX cases, and the hub hot-unplug path remain separate validation questions.

## Hardware and application status

**User-confirmed working:** Wi-Fi, Bluetooth, Ethernet, keyboard, mouse, trackpad, keyboard backlighting, display backlight and brightness controls, volume keys, USB and sound. Wi-Fi and Bluetooth remain usable even though the **native menu-bar symbols are not visible**.

**Application launch observation:** all built-in applications tried in the latest hands-on session **opened except Weather**. This is not exhaustive app/function certification. Control Center still has Swift interaction crashes.

**Battery:** the Foundation/Swift <code>DateComponents</code> fix stopped the crash on opening Battery preferences. **Usage/history graphs are still incorrect.**

**Storage:** neither NTFS nor exFAT mounted successfully in the documented Golden Gate image. Earlier Setup Assistant progress depended on excluding these volumes from automount.

## Image B: controlled hardware and UI changes

Image B retained Intel HD 4000 and GT 650M drivers but removed two Kepler overrides of ImageIO/CMPhoto, changing **38 → 36** hardware operations. Its subsequent post-install repairs were measured on the MacBook:

| Area | Modification | Result |
|---|---|---|
| Finder / IconServices | Native Intel agent from Tahoe 25G422 | Four requests dropped from 73 errors each to **zero**; Finder responsive after restart |
| Dock | SkyLight mouse-button return ABI correction | False pressed states eliminated, labels/magnification/auto-reveal restored |
| Window dragging | SkyLight Option-state ABI correction | Normal dragging without unwanted tiling |
| Battery preferences | Foundation Swift <code>DateComponents</code> bridge fix | Pane opens, period selectors work; charts remain wrong |

[Image B repair ledger](REGISTRU-TEHNIC-B.md) · [A/B chronology](ISTORIC-A-B.md).

## Remaining engineering boundaries

- **Visual:** invisible Wi-Fi/Bluetooth menu-bar glyphs; incomplete battery and active-app indicators.
- **Storage:** NTFS/exFAT mounting remains unsuccessful.
- **Battery:** pane repaired; history/usage graphs still incomplete.
- **Applications:** Weather fails to open; some Control Center actions crash.
- **Displays:** direct external-video and GMUX switching have positive observations; Thunderbolt hub hot-unplug has a documented black-screen failure; NVIDIA transparency artifacts persist.
- **HAO payload:** local runtime bootstrap does not reproduce the full upstream external interface-unit/thunk selection or optional async provider. This is a **coverage gap**, not a confirmed explanation for each remaining defect.
- **Distribution:** no public Apple OS image, general installer, or cross-model support claim.

## Technical navigation

[Original build archive](etape-a/INDEX.md) · [First boot and GPU evidence](STAGE-1.md) · [A/B chronology](ISTORIC-A-B.md) · [Image B repair ledger](REGISTRU-TEHNIC-B.md) · [Volume test kit](kit-volume/README.md) · [Future photo gallery](GALLERY.md) · [Licenses](../NOTICE.md)

**Attribution:** Original HAO — [lythka](https://github.com/lythka); MacBookPro9,1 project direction and hardware validation — **[StefanAlMare](https://github.com/StefanAlMare)**; implementation assistance — Codex (OpenAI), with Dortania/Acidanthera and other upstream contributions acknowledged in [NOTICE.md](../NOTICE.md).

*Stage 1 closed: 20 November 2026. Unofficial research preview.*
