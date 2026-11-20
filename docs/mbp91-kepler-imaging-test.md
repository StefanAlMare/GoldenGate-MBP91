# MacBookPro9,1 imaging test on a second USB disk

English · [Română](mbp91-kepler-imaging-test.ro.md)

The control is the bootable MacBookPro9,1 external SSD running Golden 26B131 and HAO `1547dcb`. This experimental profile keeps both GPU drivers and omits two Tahoe 25G229 framework merges from the Kepler hardware map, ImageIO and CMPhoto. The test asks whether those shared components affect icon generation or display. The profile and separate iMac assembly kit have been verified. The kit manifest covers 36,077 entries with SHA-256 `fb07b7b93fa70396e5ed322d7309a7fb1b5c48f0ef6a8a859bc1b5c46ae41a0a`. The image still needs local assembly, EFI and first-boot checks, and a physical test.

## Preparing the candidate

Use the 9,1 builder with this branch's `tools/oclp-hardware/profiles/mbp91.json` when preparing the hardware artifact. Assemble a fresh offline System from the stage preceding the hardware merges. An already populated System retains files from the earlier merges. Use the 9,1 EFI, both GPU drivers, the same HAO runtime, donor and icon store as the control. Preserve the two volume-specific `noauto` rules and compare with the same account and language.

Use the [original 26B131 shared-cache recipe](../patches/golden-gate-userspace/src/prespecialization-26B131.json) for this candidate (SHA-256 `6d0c221c778b41048bcf9caceb9aaa0929fa48421404c4b2d391c99468b46f4c`). The existing 9,1 kit carries a different recipe beginning `8e0669e2`. Its recorded 12 framework and executable overrides extend the original 10 by exactly ImageIO and CMPhoto. The local generator reproduced the original baseline for cache family A (`262FA161`). Run the normal builder checks against the candidate's actual offline System and cache before writing the test disk.

## Physical comparison

Record which GPU owns the internal LCD. On each installation, open the same volume, check its icon and the Finder View menu, and look at the Wi‑Fi and Bluetooth symbols. Repeat on the other GPU if the system can switch. Verify the NVIDIA Metal readback afterwards. A change in symptoms identifies the pair of framework merges as a candidate cause. A subsequent one-at-a-time comparison can distinguish the two.

### Physical shader results on Golden 26B131

On 19 November 2026, two runs on MacBookPro9,1 with local HAO runtime `1547dcb` returned identical GPU records. A native x86_64 process selected each Metal registry ID and drew the same 32 × 32 Wi-Fi mask, covering 175 foreground pixels and 849 background pixels.

| GPU | Separate texture read | Color attachment read in the fragment shader |
| --- | --- | --- |
| Intel HD Graphics 4000 | 1,024/1,024, maximum channel error 0/255 | 1,024/1,024, maximum channel error 0/255 |
| NVIDIA GeForce GT 650M | 1,024/1,024, maximum channel error 1/255 | Pipeline creation for `fetch0` returned `CompilerError` 2, `Unhandled metadata type: air.render_target`. No pixels were produced by this case. |

The [upstream system adapter](../patches/golden-gate-metal-framebuffer/build/src/encoder.m) selects the Intel driver class `MTLIGAccelDevice`. Its presence in the test process alone does not establish which GPU it adapted. The two earlier Finder and IconServices captures recorded placeholder images and XPC errors. They do not associate a Finder request with the NVIDIA shader error.

The follow-up on this MacBook confirmed the author's pre-transformed `fetch0` on the GT 650M. With separate source and destination textures, the driver reported the input at index 127. The readback matched all 175 symbol pixels and all 849 background pixels, with a maximum channel error of 1/255. In the same session the original shader again failed at pipeline creation. This was an offscreen test. The active WindowServer render device at login, on-screen icons and Finder responsiveness remain to be validated.

The retained login log on 19 November 2026 counted 33 WindowServer entries matching a broad graphics/error text filter in the first 30 seconds of the current WindowServer process (16:30:37–16:31:07 EET). The filter did not identify a GPU or report the exact shader rejection in those entries. The next capture started at 16:31:26 EET. It returned at least 25,826 Finder image-generation entries with error 4097 and 25,914 IconServices listener rejections before the log reader hit its 90-second timeout. These are counts of log records. The period between the two captures is unobserved. The second capture is incomplete.

For the external-copy comparison, retain the same EFI, runtime, ImageIO and CMPhoto on both sides and change only the Kepler adaptation. At first login compare Wi-Fi and Bluetooth with sound, Time Machine and eject. In the same Finder window check the Tahoe volume icon, time to respond, and IconServices image failures during the observation. The separate image experiment that omits two imaging frameworks answers a different question.
