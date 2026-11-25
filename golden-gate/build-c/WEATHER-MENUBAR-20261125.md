# Build C — Weather and menu-bar improvements (25 November 2026)

[**English**](WEATHER-MENUBAR-20261125.md) · [**Română**](WEATHER-MENUBAR-20261125.ro.md) · [Build C](README.md) · [Chronology](CHRONOLOGY.md)

**Physical system:** Golden Gate **27.2.1 (26B131)** on the 15-inch **MacBookPro9,1** (Intel HD 4000 + NVIDIA GT 650M / GMUX). This updates the *current C state*; the earlier A/B records correctly describe a time when Weather did not launch.

| Feature | Observation on latest booted C snapshot |
|:--|:--|
| **Weather launch / stability** | **PASS:** starts normally and remains open; no spontaneous crash/termination reported |
| **Animated weather background** | **PASS:** visible and changes between selected cities |
| **Forecasts and weather details** | **PASS:** overview, multi-day forecast and tested detail cards display data |
| **Main weather map** | **PASS:** operator confirmed functional |
| **Small map preview on Weather overview** | **OPEN:** mini-map/preview remains incomplete; this is the remaining reported Weather issue |
| **Battery menu-bar icon** | **PASS (visual, after reboot):** orientation corrected; battery terminal on the right |
| **Speaker/sound menu-bar icon** | **PASS (visual, after reboot):** sound waves point right |

**Evidence:** operator's 25 November **23:29:29 EET** real-device screenshot displays Weather open in Romanian with populated forecast and detailed panels, plus battery/sound icons in the menu bar. Work4 physical observations additionally confirm animated background changes and the main map. The screenshot was provided privately and **is not redistributed in this repository**.

**Technical scope:** Work3/Work4 compared Intel and NVIDIA/Kepler render paths. The mini-preview remained incomplete even with Intel selected during diagnostics; a completed large map or passing render probe does **not** prove the preview layer is fixed. No specific cause is certified from these observations, and no new source patch is claimed in this documentation-only milestone.

**Still separate:** Wi-Fi/Bluetooth menu icons, Battery usage graphs/charge accuracy, Control Center, NTFS/exFAT, Thunderbolt hub HDMI hot-unplug and remaining NVIDIA visual artifacts are not marked solved. Correct icon orientation is not evidence of accurate battery state. General installability and cross-model compatibility remain experimental.

**Credits:** This hardware adaptation builds on the original [lythka HAO architecture](https://github.com/lythka/hao-patcher), with OpenCore/OCLP and Tahoe components. MacBookPro9,1 project and device verification by [StefanAlMare](https://github.com/StefanAlMare), with Codex assistance. No Apple proprietary files or private logs are included.
