# Golden Gate volume kit

English · [Română](Citeste.md)

Use the kit to inventory disks and preview per-volume `fstab` rules before starting Golden Gate on an Intel Mac or Hackintosh. It reads disk metadata with the current user's permissions. Both tools use English by default. Pass `--lang ro` as the first option for Romanian output.

1. On the test machine, connect the disks that will be present at boot. Open `Inventar.command` from Finder or run `./Inventar.command` from this directory. The [inventory guide](Inventory.md) explains how to interpret the report and select partitions.
2. Use the [fstab preview guide](Fstab-preview.md) to merge the selected rules with a copy of the target Golden Data volume's configuration. Each rule uses the local filesystem UUID. Keep plans containing UUIDs with the machine's private records.
3. Fill in the [hardware test record](Hardware-test.md) for each hardware and build combination. On Hackintosh, record the physical motherboard, storage controller, CPU and GPU separately from the SMBIOS model reported by OpenCore.

## What to test

On MacBookPro9,1 with Golden 26B131, Setup Assistant appeared after two rules excluded the internal NTFS and exFAT volumes from automount. On another machine, first record whether Setup starts normally. If it stalls, look for both Setup waiting for its RAM disk and a pending FSKit mount request in the same boot. A stalled progress bar alone cannot identify the cause.

The kit produces a preview. Applying a profile to a new machine requires identifying the test copy's System/Data pair, preserving its original configuration and preparing a way to restore it. The separate MacBookPro9,1 activation package contains identifiers specific to the original test machine.

Record Setup Assistant, Finder, login after a restart and file access as separate milestones. A volume covered by `ro,noauto` stays excluded from automount after login. After a stable restart, each volume can be tested separately with an explicit read-only mount and a read of a known file. Record the IORegistry `Open` state, whether the mount completed, and whether the read succeeded.
