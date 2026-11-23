# Golden Gate — Build C | 23 noiembrie 2026

[**Română**](README.ro.md) · [**English**](README.md) · [Pagina principală](../../README.ro.md)

## Mediu de dezvoltare funcțional pe un Mac Intel din 2012

![macOS](https://img.shields.io/badge/macOS-27.2.1_26B131-315d85?style=flat-square)
![Clang](https://img.shields.io/badge/Clang_21-Intel_ARM64_Universal_2-247a5a?style=flat-square)
![Xcode](https://img.shields.io/badge/Xcode_27.2-10%2F10_ARM%2BUniversal-247a5a?style=flat-square)
![MacPorts](https://img.shields.io/badge/MacPorts_2.12.7-Compilare_in_curs-b77d31?style=flat-square)

> **Test fizic:** MacBookPro9,1 de 15″ (Mid 2012), Ivy Bridge, Intel HD 4000, NVIDIA GT 650M, GMUX. Golden Gate 27.2.1 (26B131) pornește de pe un SSD USB experimental. Autorul HAO original este [lythka](https://github.com/lythka/hao-patcher); aceasta este o adaptare independentă 9,1, nu o distribuție oficială.

| Realizare | Probă | Limită |
|:--|:--|:--|
| **CLT 27.2 / Apple Clang 21** | C, C++, LTO autentic, make și executabile x86_64 PASS; compilare directă ARM64 și Universal 2 PASS | Execuția nativă pe Apple Silicon nu a fost testată |
| **Xcode 27.2 (27B52)** | 5 proiecte Intel plus **10/10** builduri ARM64 și Universal 2; C, C++17, Objective-C, Swift și AppKit | `xcodebuild` verificat, `⌘B` din interfață încă netestat |
| **MacPorts 2.12.7** | Compilare/instalare din surse prin HAO/CLT; 138 de porturi active raportate intermediar; compilările continuă | Nu reprezintă 138 de builduri din surse ori teste individuale; inventarul verificat urmează |
| **HAO / APFS** | Backend corectat, 77 legături recuperate, **84/84 System** și **3/3 CFG Data**, boot din snapshot nou | Copie C experimentală, System/Data se restaurează separat |

### Documentație în ordinea execuției

1. [Cronologia (20–23 noiembrie)](CHRONOLOGY.ro.md) · [English](CHRONOLOGY.md)
2. [Dovezile CLT, HAO și Clang (RO)](TOOLCHAIN-EVIDENCE.ro.md) · [Detalii EN](TOOLCHAIN-EVIDENCE.md)
3. [Xcode 27.2 — Intel / ARM64 / Universal 2](XCODE.ro.md)
4. [Registrul MacPorts actualizabil](MACPORTS.ro.md) · [Tabel porturi](ports.csv)
5. [Corecția sursă HAO APFS](patches/hao-livepatch-compression.patch) și [colectorul read-only](collect-macports.sh)

**Separăm dovezile:** PASS fizic sau raportat cu rezultat concret nu înseamnă compatibilitate generală. Porturile care încă se compilează nu sunt marcate finalizate. Compilarea ARM64 pe Intel nu dovedește execuția nativă pe Apple Silicon. [Galeria A/B](../GALLERY.md) păstrează fotografiile reale ale hardwareului.

**Atribuire:** [HAO original](https://github.com/lythka/hao-patcher), [HAO runtime](https://github.com/lythka/hao-runtime), OpenCore/OCLP; portare și teste pe MacBookPro9,1 de [StefanAlMare](https://github.com/StefanAlMare) cu asistență Codex. Nu publicăm software Apple, imagini de instalare ori jurnale private.
