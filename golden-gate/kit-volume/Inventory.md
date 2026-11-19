# Disk inventory

English · [Română](Inventar.ro.md) · [Volume kit](README.md)

Open `Inventar.command` in Finder on the test machine. The report appears in Terminal. Run it from Tahoe before installation or from Golden after Setup. BSD identifiers such as `disk0s3` apply only to the current boot. The model field shows the SMBIOS presented to macOS. Record separately whether the hardware is an original Mac or a Hackintosh.

The inventory uses macOS commands and libraries to read disk metadata with ordinary user permissions. The report includes the model, architecture, build, disk location and partition state. A “Microsoft Basic Data” partition with an unidentified filesystem requires further investigation. A candidate is a partition whose filesystem and identity the tool could verify. The MacBookPro9,1 result warrants a test when the symptoms and logs match.

To preview rules, open Terminal in the tool directory. Replace the example identifiers with those in your machine's current inventory.

```sh
./Inventar.command --plan disk0s3 disk0s6
```

This prints an `fstab` plan with the private filesystem UUIDs of the partitions you selected. The tool accepts identifiable NTFS and exFAT data partitions. It excludes EFI, the running system, its APFS physical stores and ambiguous identities. A separate data partition on the same physical disk as Tahoe can be selected. If a selected UUID occurs twice in the visible inventory, including on a virtual disk, the tool refuses the plan.

Share the ordinary report when discussing compatibility. Keep the UUID plan local. Applying a `noauto` rule separately excludes the volume from automount for as long as the rule is in effect, including after Setup.
