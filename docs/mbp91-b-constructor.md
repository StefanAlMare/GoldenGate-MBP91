# Reproducing the local Golden B source checkpoint

This branch records the 26B131 MacBookPro9,1 constructor used as the reference for a future assembly. The 36-operation Kepler profile from `21fae1f` omits the ImageIO and CMPhoto overrides from Tahoe 25G229. The stock 10-provider cache recipe has SHA-256 `6d0c221c778b41048bcf9caceb9aaa0929fa48421404c4b2d391c99468b46f4c`. Golden B uses HAO runtime `1547dcb` and the local family-A payload.

The separately staged B kit had manifest SHA-256 `fb07b7b93fa70396e5ed322d7309a7fb1b5c48f0ef6a8a859bc1b5c46ae41a0a`. It predates the desktop recipe. This source checkpoint adds revision 2 of that recipe after `hao-runtime` in the MacBookPro9,1 assembly. Its two inputs are the verified Intel IconServices agent from Tahoe 25G422 and the cumulative 255-byte SkyLight unit for Dock and window tiling. The local Finder snapshot write has receipt `hao-20261120-144841`; first login with a responsive Finder before any relaunch remains a separate hardware check.

## Private inputs

* Stage a copy of the verified hardware tree from the B kit's `assembly-inputs/hardware` at the store-relative path in `pipeline/inputs/golden/26B131/oclp_hardware_mbp91`. The tree includes its build metadata, install map, install tools and payload. Its lock digest covers that tree. Rebuilding the map from the JSON profile alone does not establish this identity.
* Stage the private constructor's verified desktop artifact tree (including its `root` directory) at the path in `pipeline/inputs/golden/26B131/mbp91_desktop`. Check both inputs with the repository's row hashing logic. Keep the other local B inputs and their recorded provenance, including the 26B131 and Tahoe 25G342 donors, kernel and EFI inputs, and the runtime and shared-cache family. The 25G422 donor applies specifically to the Finder agent.
* Keep the two volume-specific `ro,noauto` entries for this test machine as a separate Data-volume personalization using the volume inventory. The records and hashes identify source and inputs. The existing test SSD, its blessed snapshot and the frozen assembly kit are separate artifacts.

No bootable image has been built or started from this combined source checkpoint. Battery and menu-bar experiments remain outside the desktop recipe. Re-evaluate each local desktop rule against any future complete HAO runtime before including it in a new image.
