# MacBookPro9,1 imaging test on a second USB disk

English · [Română](mbp91-kepler-imaging-test.ro.md)

The control is the bootable MacBookPro9,1 external SSD running Golden 26B131 and HAO `1547dcb`. This experimental profile keeps both GPU drivers and omits two Tahoe 25G229 framework merges from the Kepler hardware map, ImageIO and CMPhoto. The test asks whether those shared components affect icon generation or display. The profile has passed a comparison of its installation operations. The candidate still needs assembly and a physical boot.

## Preparing the candidate

Use the 9,1 builder with this branch's `tools/oclp-hardware/profiles/mbp91.json` when preparing the hardware artifact. Assemble a fresh offline System from the stage preceding the hardware merges. An already populated System retains files from the earlier merges. Use the 9,1 EFI, both GPU drivers, the same HAO runtime, donor and icon store as the control. Preserve the two volume-specific `noauto` rules and compare with the same account and language.

Use the [original 26B131 shared-cache recipe](../patches/golden-gate-userspace/src/prespecialization-26B131.json) for this candidate (SHA-256 `6d0c221c778b41048bcf9caceb9aaa0929fa48421404c4b2d391c99468b46f4c`). The existing 9,1 kit carries a different recipe beginning `8e0669e2`. Its recorded 12 framework and executable overrides extend the original 10 by exactly ImageIO and CMPhoto. The local generator reproduced the original baseline for cache family A (`262FA161`). Run the normal builder checks against the candidate's actual offline System and cache before writing the test disk.

## Physical comparison

Record which GPU owns the internal LCD. On each installation, open the same volume, check its icon and the Finder View menu, and look at the Wi‑Fi and Bluetooth symbols. Repeat on the other GPU if the system can switch. Verify the NVIDIA Metal readback afterwards. A change in symptoms identifies the pair of framework merges as a candidate cause. A subsequent one-at-a-time comparison can distinguish the two.
