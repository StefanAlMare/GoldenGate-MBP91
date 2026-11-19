# MacBookPro9,1 · First setup on 19 November 2026

**English** · [Română](STADIUL-1.md)

StefanAlMare booted Golden Gate 27.2.1 (26B131) from an external USB SSD on a MacBookPro9,1 and began setup in Setup Assistant. He confirmed this on the MacBook’s screen. The detailed captures in the local project log come from earlier boots that stalled during setup.

## Test system

| Component | Reference |
|---|---|
| Mac | 15-inch MacBook Pro, Mid 2012, with Ivy Bridge, Intel HD 4000, NVIDIA GeForce GT 650M and GMUX. An earlier capture showed the Intel GPU driving the internal display. |
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

## Next test on the external copy

1. Keep the same image, EFI, runtime and two volume rules. Record whether setup completes and Finder appears. Save the diagnostic capture for that boot.
2. Test a restart separately. Record whether login succeeds and the desktop returns.
3. After a stable login, test one volume at a time. Confirm its UUID, request a manual read-only mount, read a known file and unmount the volume. Record the result separately for NTFS and exFAT.

GT 650M rendering, GMUX switching, other Intel Macs and Hackintosh systems each require physical tests. The volume kit on this branch inventories disks and previews rules for the volumes the operator selects.

## Source history

The private working branch starts at [hao-patcher fb6542d](https://github.com/lythka/hao-patcher/commit/fb6542df15fc299266f788328e41fe908dd19b3e). The upstream references recorded on 19 November for future comparisons are [hao-runtime 0714743](https://github.com/lythka/hao-runtime/commit/0714743d11fc76e29e310cab79f1d9f020a4bf74) and [hao-assets 22b18bf](https://github.com/lythka/hao-assets/commit/22b18bfd7d5e7adb2ec3d71c76582b1cabb8d252). The test system table records the versions used on the physical Mac.

The [MacBookPro9,1 builder snapshot](https://github.com/StefanAlMare/GoldenGate-MBP91/tree/0b3d86aba06b3c0d85fc9436f4395194664e75fe) preserves the ten adaptation files on their original base, 6bd75aa. They cover the hardware profile, package selection and EFI generation. Validation fields in the profiles reflect the state at build time, before the physical test. The image, EFI binaries, Apple inputs and raw captures are kept locally.
