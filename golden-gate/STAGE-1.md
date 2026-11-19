# MacBookPro9,1 · First setup on 19 November 2026

**English** · [Română](STADIUL-1.md)

StefanAlMare booted Golden Gate 27.2.1 (26B131) from an external USB SSD on a MacBookPro9,1 and began setup in Setup Assistant. He confirmed this on the MacBook’s screen. The detailed captures in the local project log come from earlier boots that stalled during setup.

## Test system

| Component | Reference |
|---|---|
| Mac | 15-inch MacBook Pro, Mid 2012, with Ivy Bridge, Intel HD 4000, NVIDIA GeForce GT 650M and GMUX. The post-restart display inventory listed the 1680 × 1050 internal LCD under Intel HD 4000. |
| Storage | The internal disk held Tahoe/OCLP and the NTFS and exFAT volumes. Golden Gate ran from the external USB SSD. The Tahoe donor build was 25G342. |
| Builder used for the physical test | [hao-patcher 6bd75aa](https://github.com/lythka/hao-patcher/commit/6bd75aab112d1078acd8e75180eb510672461365) with local MacBookPro9,1 adaptations |
| Locally built runtime | `1547dcb4e19a2ab0843086e3288223f998507a4c`. The x86_64 Mach-O UUID for `libhao` in the stack traces matched the local binary. Its SHA-256 was `11760e88422c301f2d99f32581902c4e891e7819110aab0565e65e14f34a1a45`. |
| Original 80 GiB image | SHA-256 `52a930a84a37b3fdd3443636426503c716e723f7c781332d605f964ad3922f35`, calculated before the APFS container was expanded and the SSD was booted. |
| EFI archive used in the test | SHA-256 `5c112839a68f54f74949e5f7a4f55d7acc74187bdf5553a1e5f598b5806c14ca`. The configuration passed `ocvalidate`. |

## Three successive tests

| Test | Observation |
|---|---|
| Baseline | The progress bar stopped at about 60%. WindowServer continued processing events. In the DiskImages2 baseline capture, NTFS showed `Open=Yes` and exFAT showed `Open=No`. The 512 MiB RAM disk remained unpartitioned across 146 readings. |
| NTFS excluded from automount | NTFS changed to `Open=No` and exFAT to `Open=Yes`. The RAM disk remained unpartitioned across another 146 readings. The capture recorded device state. The `fstab` from that boot was unavailable. |
| Both NTFS and exFAT excluded from automount | With a separate `ro,noauto` rule for each volume UUID, StefanAlMare saw Setup Assistant and began setup. This visual observation still needs to be matched to a diagnostic capture from the successful boot. |

On the stalled boots, the setup service was waiting for the temporary user’s RAM disk. DiskImages2 was waiting for Disk Arbitration to finish its pending operations. During the same interval, `diskarbitrationd` was waiting in `LiveFSMountClient`, and a thread in `fskitd` was in `mount(2)`. The stack traces did not identify which volume the call targeted. The sequence points to automount as an area to investigate on this Mac. The specific role of exFAT and the cause of the stall remain open.

## Desktop, restart and GPU test on 19 November 2026

StefanAlMare reached the desktop, restarted the Mac and signed in again successfully. An SSH session from the iMac reached the MacBookPro9,1 on build 26B131. During hands-on use, StefanAlMare reported working Wi-Fi, Bluetooth, sound, USB, trackpad and keyboard, including the brightness and volume keys.

| Evidence | Observation |
|---|---|
| Display inventory after restart | The internal LCD was online under Intel HD 4000. The GT 650M reported 512 MB VRAM on PCIe x8. Both GPUs reported Metal 2 support. |
| I/O Registry | Both accelerators were active. The NVIDIA accelerator had registry ID `0x1000004b7`. |
| Metal probe over SSH | The probe enumerated both GPUs and selected the NVIDIA device with that same registry ID. It cleared a 4 × 4 RGBA texture to red, copied the result to a CPU-readable buffer and verified all 16 pixels. [Probe source](diagnostics/metal-check.m) |

```text
PASS: NVIDIA GeForce GT 650M | Metal render clear + readback | 16/16 pixels
```

This confirms that the GT 650M executed a Metal render-pass clear and returned the expected pixel values. Shader execution and GMUX display switching remain untested.

## Finder and IconServices after login

A separate Finder relaunch opened an empty folder. The path-bar and status-bar preferences both read back as enabled. StefanAlMare reported that Finder eventually responded, still with a long delay, and the drive icons still looked like folders. The slowdown also occurred outside the Tahoe volume.

On the running 26B131 system, `hao --aot --check` reported valid precompiled code for **both Finder and iconservicesagent** under `/private/var/db/hao`. The per-user IconServices index (`store.index`) was missing at the time of the checks, including after a verified restart of the user agent. The earlier capture also recorded failed image requests (Foundation 4097) and XPC listener rejections. The reason for those rejections remains open.

### Icon index installed on the test Mac

The stock Apple 26B131 system and the assembled image contained byte-identical copies of Finder.icns, GenericFolderIcon.icns, the internal disk icon, and the Finder and CoreTypes asset catalogs. The original System and the assembled System/Data volumes contained no populated IconServices index before boot.

On the running MacBook, the shared Romanian store contained 243 nonempty units. The local Setup Assistant account already had an index for 26B131 and Romanian. All 456 records referred to units present on this same installation, covering 228 distinct units. The system account also held a smaller matching index. The repair installed the Setup account's index at the previously missing path in the desktop user's cache, then relaunched that user's IconServices agent. The 720,896-byte index remained present immediately after relaunch. The shared store and the Tahoe volume were untouched.

StefanAlMare saw no visual improvement before reboot. After the 16:29 reboot, the desktop user's index still had the same size, owner, mode and SHA-256 (`fe6be8430620640f462def2224a9738b8965be2229dfe05179bad69d22ca68c0`). The 15-second check recorded 6,197 listener rejection events, 6,193 image-generation errors and zero index-open errors. Its filtered filesystem trace returned no matching accesses, so it could not establish whether either process read the index during the check.

An earlier Finder sample shows 58 of 65 samples on the icon cache-miss queue waiting for a synchronous XPC reply. The user agent sampled a connection from Finder's PID and a cancellation on its IconServices listener. These observations explain delays in icon requests. The reason the listener cancels the connection and the cause of the missing menu-bar symbols are still open.

In the assembled image on the iMac, Finder, iconservicesagent and iconservicesd matched their build manifest. The four Finder and IconServices launch plists matched Apple's 26B131 image byte for byte. The [read-only comparison](diagnostics/GoldenGate-Finder-XPC.command) checks the running installation against those seven files, inspects the registered services and reads the published messages around the failure.

## Open observations and next tests

- Some menu-bar controls opened when clicked even though their icons were invisible. Desktop drive icons appeared as folders, and icons were missing in System Settings. The cause remains open.
- The next storage test is a manual read-only mount after login on the external Golden installation. Test NTFS and exFAT separately, verify the UUID, read a known file and unmount each volume.
- Other Intel Macs and Hackintosh systems require their own hardware tests. The volume kit on this branch inventories disks and previews rules for the selected volumes.

## Source history

The private working branch starts at [hao-patcher fb6542d](https://github.com/lythka/hao-patcher/commit/fb6542df15fc299266f788328e41fe908dd19b3e). The upstream references recorded on 19 November for future comparisons are [hao-runtime 0714743](https://github.com/lythka/hao-runtime/commit/0714743d11fc76e29e310cab79f1d9f020a4bf74) and [hao-assets 22b18bf](https://github.com/lythka/hao-assets/commit/22b18bfd7d5e7adb2ec3d71c76582b1cabb8d252). The test system table records the versions used on the physical Mac.

The [MacBookPro9,1 builder snapshot](https://github.com/StefanAlMare/GoldenGate-MBP91/tree/0b3d86aba06b3c0d85fc9436f4395194664e75fe) preserves the ten adaptation files on their original base, 6bd75aa. They cover the hardware profile, package selection and EFI generation. Validation fields in the profiles reflect the state at build time, before the physical test. The image, EFI binaries, Apple inputs and raw captures are kept locally.
