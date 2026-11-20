# MacBookPro9,1 desktop on 26B131

On 20 November 2026, each of four requests for the Applications folder icon logged 73 Foundation 4097 errors on Golden B. After the Apple-signed Intel IconServices user agent from Tahoe 25G422 took over, all four requests returned the icon with zero 4097 errors. Requests for the Finder, System Settings and Activity Monitor icons also succeeded. WindowServer still marked the existing Finder (PID 525) unresponsive. The operator confirmed that Finder responded normally after relaunching it.

The image recipe installs the donor pinned by the local `mbp91_desktop` input at the path used by Golden's existing launch agent. On first login to the new image, check app and disk icons and use a fresh Finder window to open Applications before any manual relaunch.

The second file supplies the one-byte return width of the SkyLight button and modifier state calls under both their CGS and SLS names. The operator verified Dock hover and screen-edge activation on Golden B and confirmed that adding the modifier records corrected unintended window tiling. The cumulative unit has 255 bytes and SHA-256 `cd2a77b0e61af60abd4c23e860809aad0af4837dc81886a600831379c2546b3f`.

## Revisions

Revision 1 selects both files for the 9,1 pack after hao-runtime. The assembled image containing both still needs its first physical boot.

Revision 2 keeps the same Finder agent and selects the cumulative SkyLight unit. On B it can replace the known 155-byte Dock-only unit. A fresh image assembled with this revision still needs a physical first-login test.
