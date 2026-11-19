# Preview an fstab profile for one machine

English · [Română](Previzualizare-fstab.md) · [Volume kit](README.md)

Boot a working macOS installation on the target machine with the relevant disks connected. Run the inventory from this directory and select the affected NTFS or exFAT partitions using their BSD identifiers for this boot.

```sh
./Inventar.command
```

Replace the two example identifiers with your own. Choose fresh output filenames. Keep the resulting UUID plan in the machine's private records.

```sh
(set -C; ./Inventar.command --plan disk7s3 disk7s6 > plan-local.txt)
```

Check `private/etc/fstab` on the **Golden Data volume intended for the test**. If it exists, save a local copy as `fstab-original.txt`. Preview the merged file with Python 3.

```sh
python3 Pregateste-fstab.py --plan plan-local.txt --base fstab-original.txt
```

If you have verified that the target has no `fstab`, replace `--base fstab-original.txt` with `--empty`. To keep the preview in a new working file, enable shell overwrite protection.

```sh
(set -C; python3 Pregateste-fstab.py --plan plan-local.txt --base fstab-original.txt > fstab-proposed.txt)
```

Check the messages, exit status and differences from the original. If validation fails, the new file may be empty. The tool preserves an existing identical rule. It stops on conflicting or repeated rules for a selected volume and on entries such as `LABEL=` or `/dev/…` that need manual review. It prints the result after validating the entire plan. The shell can truncate an existing output file before the program starts. Use a new filename with `set -C`.

Integrate the verified profile when assembling the Golden test copy. The MacBookPro9,1 activation and restore package was checked for that machine. On another machine, verify the target disk, original configuration and restoration procedure separately before applying a profile.
