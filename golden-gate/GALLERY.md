# Golden Gate 27.2.1 — MacBookPro9,1 / 15-inch Mid 2012

**[English project homepage](../README.md) · [Versiunea română](../README.ro.md) · [Engineering dossier](ENGINEERING.md)**

> **11 authentic screenshots from the 15-inch MacBookPro9,1 tested by [StefanAlMare](https://github.com/StefanAlMare):** ten Stage 1 captures from **20 November 2026**, plus the Build C Weather capture from **25 November 2026**. These are not images from the original MacBookPro9,2 HAO project. Photos document device recognition and particular observations, not a blanket compatibility certification. Personal hardware addresses and serial identifiers have been obscured.

> **Română:** 11 capturi autentice de pe MacBookPro9,1 de 15″, testat de StefanAlMare: zece din 20 noiembrie 2026 (etapa 1) și una din 25 noiembrie 2026 (Vremea pe Build C). Nu sunt fotografii de pe MacBookPro9,2 al autorului HAO. Unele dovezi indică detectarea dispozitivelor, nu funcționarea fiecărei caracteristici. Adresele hardware și numerele de serie private au fost mascate.

## 01 — Working desktop and the dual-GPU result

**Golden Gate 27.2.1 reaches the desktop, and NVIDIA drives the internal and external displays in the dual-screen configuration.**

<table>
<tr>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/01-golden-gate-desktop-h264.webp"><img src="images/mbp91/01-golden-gate-desktop-h264.webp" width="100%" alt="Golden Gate 27.2.1 — live desktop" /></a>
  <p><strong>Golden Gate 27.2.1 — live desktop</strong><br /><em>Desktop Golden Gate 27.2.1</em></p>
  <p align="left">About This Hack identifies macOS 27.2.1 (26B131), the Mid 2012 15-inch model, Intel i7 and HD 4000. VideoProc reports H.264 acceleration available; HEVC unavailable.<br /><em>About This Hack identifică 27.2.1 (26B131) și MacBook Pro 15″ din 2012. VideoProc raportează accelerare H.264 disponibilă, iar HEVC indisponibilă.</em></p>
</td>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/10-nvidia-gt650m-dual-display.webp"><img src="images/mbp91/10-nvidia-gt650m-dual-display.webp" width="100%" alt="NVIDIA GT 650M — both screens" /></a>
  <p><strong>NVIDIA GT 650M — both screens</strong><br /><em>NVIDIA GT 650M — ambele ecrane</em></p>
  <p align="left">System Information lists the internal 1680×1050 LCD and an external 1920×1080 monitor under NVIDIA GT 650M; both are online.<br /><em>Informații sistem arată LCD-ul intern 1680×1050 și un monitor extern 1920×1080 sub NVIDIA GT 650M, ambele online.</em></p>
</td>
</tr>
</table>

## 02 — Intel graphics and wireless networking

**Intel HD 4000 on the internal panel; Broadcom Wi-Fi associated and active.**

<table>
<tr>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/05-intel-hd4000-internal-display.webp"><img src="images/mbp91/05-intel-hd4000-internal-display.webp" width="100%" alt="Intel HD 4000 — internal LCD" /></a>
  <p><strong>Intel HD 4000 — internal LCD</strong><br /><em>Intel HD 4000 — LCD intern</em></p>
  <p align="left">The internal 1680×1050 panel is detected under Intel HD 4000 with Metal 2 support and automatic graphics switching reported as compatible.<br /><em>LCD-ul intern 1680×1050 este identificat pe Intel HD 4000, cu Metal 2 și compatibilitate cu comutarea automată.</em></p>
</td>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/03-wifi-connected.webp"><img src="images/mbp91/03-wifi-connected.webp" width="100%" alt="Broadcom Wi-Fi — connected" /></a>
  <p><strong>Broadcom Wi-Fi — connected</strong><br /><em>Wi-Fi Broadcom — conectat</em></p>
  <p align="left">System Information reports an active 802.11ac link, WPA2 security, associated access point and AirDrop capability.<br /><em>Informații sistem confirmă conexiune 802.11ac activă, WPA2, punct de acces asociat și suport AirDrop.</em></p>
</td>
</tr>
</table>

## 03 — Bluetooth and wired Ethernet

**Controller and network-driver evidence from System Information.**

<table>
<tr>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/02-bluetooth-controller.webp"><img src="images/mbp91/02-bluetooth-controller.webp" width="100%" alt="Bluetooth controller — active" /></a>
  <p><strong>Bluetooth controller — active</strong><br /><em>Controller Bluetooth — activ</em></p>
  <p align="left">The Bluetooth controller is active and recognized, with supported device-service profiles listed.<br /><em>Controllerul Bluetooth este activ și recunoscut, cu profiluri de servicii enumerate.</em></p>
</td>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/06-gigabit-ethernet.webp"><img src="images/mbp91/06-gigabit-ethernet.webp" width="100%" alt="Broadcom Gigabit Ethernet" /></a>
  <p><strong>Broadcom Gigabit Ethernet</strong><br /><em>Ethernet Gigabit Broadcom</em></p>
  <p align="left">Broadcom 57765-B0 appears as en0 with AppleBCM5701Ethernet and maximum 1 Gb/s link capability.<br /><em>Broadcom 57765-B0 este identificat ca en0, prin AppleBCM5701Ethernet, cu capacitate 1 Gb/s.</em></p>
</td>
</tr>
</table>

## 04 — Thunderbolt 2 and built-in audio

**The Thunderbolt 2 dock is enumerated, while HDMI hot-disconnection through this hub is still a known issue.**

<table>
<tr>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/09-thunderbolt-2-dock.webp"><img src="images/mbp91/09-thunderbolt-2-dock.webp" width="100%" alt="Thunderbolt 2 dock recognized" /></a>
  <p><strong>Thunderbolt 2 dock recognized</strong><br /><em>Dock Thunderbolt 2 recunoscut</em></p>
  <p align="left">An Elgato Thunderbolt 2 Dock is enumerated on the Thunderbolt bus with a 10 Gb/s active link. Display hot-unplug through the dock is not yet reliable.<br /><em>Dockul Elgato Thunderbolt 2 apare în magistrală, cu legătură activă de 10 Gb/s. Deconectarea monitorului prin dock rămâne problematică.</em></p>
</td>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/04-integrated-audio.webp"><img src="images/mbp91/04-integrated-audio.webp" width="100%" alt="Built-in audio devices" /></a>
  <p><strong>Built-in audio devices</strong><br /><em>Dispozitive audio integrate</em></p>
  <p align="left">System Information lists the integrated microphone, line input and built-in output. Audio function has also been reported working on the test Mac.<br /><em>Sistemul identifică microfonul, intrarea de linie și ieșirea internă; funcționarea sunetului a fost confirmată și practic.</em></p>
</td>
</tr>
</table>

## 05 — Camera and storage

**Detected devices: built-in FaceTime camera, Intel SATA/AHCI controller and internal SSD.**

<table>
<tr>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/08-facetime-camera.webp"><img src="images/mbp91/08-facetime-camera.webp" width="100%" alt="Built-in FaceTime HD camera detected" /></a>
  <p><strong>Built-in FaceTime HD camera detected</strong><br /><em>Camera FaceTime HD detectată</em></p>
  <p align="left">The integrated FaceTime HD camera is enumerated. This screenshot demonstrates detection, not a captured video stream.<br /><em>Camera FaceTime HD integrată este recunoscută; captura dovedește detectarea, nu testarea unui flux video.</em></p>
</td>
<td width="50%" valign="top" align="center">
  <a href="images/mbp91/07-sata-storage.webp"><img src="images/mbp91/07-sata-storage.webp" width="100%" alt="Intel SATA controller and SSD" /></a>
  <p><strong>Intel SATA controller and SSD</strong><br /><em>Controller SATA Intel și SSD</em></p>
  <p align="left">Intel 7 Series SATA/AHCI and an internal SSD are recognized. Golden Gate itself was tested from a separate USB SSD.<br /><em>Controllerul Intel 7 Series SATA/AHCI și SSD-ul intern sunt recunoscute. Golden Gate a fost testat de pe SSD USB separat.</em></p>
</td>
</tr>
</table>

## 06 — Weather running on Build C (25 November 2026)

**Weather now launches and remains open on the real MacBookPro9,1.** The screenshot captures the populated forecast, weather conditions and detailed panels, with the battery and sound menu-bar icons oriented correctly. The small map preview on Weather's overview **remains unfinished**.

**Română:** Aplicația **Vremea pornește și rămâne deschisă** pe MacBookPro9,1 real. Captura arată prognoza, condițiile meteo și panourile detaliate, precum și orientarea corectă a pictogramelor bateriei și sunetului din bara de meniu. **Miniatura hărții meteo de pe pagina principală** rămâne incompletă.

<table>
<tr><td align="center" valign="top">
  <a href="images/mbp91/11-weather-working-build-c-20261125.webp"><img src="images/mbp91/11-weather-working-build-c-20261125.webp" width="100%" alt="Golden Gate Build C on MacBookPro9,1 — Weather running on 25 November 2026, with forecasts and menu-bar battery/sound icons" /></a>
  <p><strong>Build C — Weather operational, 25 November 2026, 23:29 EET</strong><br /><em>Build C — Vremea funcțională, 25 noiembrie 2026, ora 23:29</em></p>
  <p align="left">This image proves the application is open and has populated content at the captured moment, **not** uninterrupted long-term stability or complete map rendering. Background animation, working main map and stable launch were separately confirmed by the operator. The original PNG was converted to WebP at its native 1680 × 1048 resolution for the gallery.<br /><em>Imaginea dovedește că aplicația este deschisă și afișează date la momentul capturii, nu stabilitatea de durată sau randarea completă a hărților. Fundalul animat, harta mare și pornirea stabilă au fost confirmate separat de operator. Captura PNG originală a fost convertită la WebP, păstrând rezoluția 1680 × 1048.</em></p>
</td></tr>
</table>

[**Build C Weather / menu-bar technical record (EN)**](build-c/WEATHER-MENUBAR-20261125.md) · [**Raport în română**](build-c/WEATHER-MENUBAR-20261125.ro.md)

## What the screenshots do — and do not — prove

- **Proven by an actual image:** Golden Gate desktop, OS build/model information, internal panel on Intel HD 4000, internal plus external monitor listed under NVIDIA, connected Wi-Fi, active Bluetooth and recognized hardware devices. The new Build C capture also shows **Weather open with populated forecasts** and visible battery/sound menu-bar icons.
- **Proven by separate project tests:** NVIDIA Metal 4×4 clear/readback (**16/16 pixels**), GMUX transitions between Intel/NVIDIA observed by the operator, and working sound/input/USB.
- **Still open:** Wi-Fi and Bluetooth menu-bar icons, NTFS/exFAT mounting, battery usage charts, **Weather's small overview map preview**, certain Control Center calls and HDMI hot-unplug through the Thunderbolt dock.
- **Important:** VideoProc's H.264 acceleration status is **the application's reported capability**; this screenshot is not a measured encoding benchmark. The camera screenshot only establishes detection.

**More information:** [First boot and GPU validation](STAGE-1.md) · [Complete A/B history (RO)](ISTORIC-A-B.md) · [Image B repair ledger (RO)](REGISTRU-TEHNIC-B.md).

**Credits:** Original HAO: [lythka](https://github.com/lythka). MacBookPro9,1 adaptation, hardware experiments and screenshots: [StefanAlMare](https://github.com/StefanAlMare). Implementation assistance: Codex (OpenAI).
