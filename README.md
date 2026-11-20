# Golden Gate on MacBookPro9,1

**English** · [Română](README.ro.md)

[Istoricul proiectului în română — construcțiile A și B, pornirea de pe USB, reparațiile și ce a rămas de rezolvat](golden-gate/ISTORIC-A-B.md)

On 19 November 2026, **StefanAlMare** reached Setup Assistant and began configuring Golden Gate 27.2.1 (26B131) on a 15-inch Mid 2012 MacBook Pro. The Mac booted from an external USB SSD. The successful run followed the addition of two `ro,noauto` rules, one for the internal NTFS volume and one for the internal exFAT volume.

StefanAlMare subsequently reached the desktop and signed in again after a restart. A Metal test explicitly selected the NVIDIA GeForce GT 650M and successfully read back all 16 pixels of a cleared render target. The display inventory taken before the test placed the internal LCD on Intel HD 4000. The [Stage 1 test record](golden-gate/STAGE-1.md) identifies the image, EFI and runtime used on the Mac and compares the three boot tests. The [volume inventory kit](golden-gate/kit-volume/README.md) lets you inspect a machine's volumes and preview its fstab rules.

## Credits

[lythka](https://github.com/lythka) is the principal author of HAO. The [original HAO Patcher README](README.upstream.md) documents the upstream work on MacBookPro9,2. Its contributors and component licenses are credited in the [project notices](NOTICE.md).

**Ștefan Ilmare (@StefanAlMare)** led the MacBookPro9,1 adaptation, ran the hardware tests and confirmed the results on screen. **Codex (OpenAI)** implemented the local adaptations, build and diagnostic tools, and documented the results.
