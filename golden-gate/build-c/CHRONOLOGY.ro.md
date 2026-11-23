# Build C — registrul cronologic al execuției

[**Română**](CHRONOLOGY.ro.md) · [**English**](CHRONOLOGY.md) · [Prezentare](README.ro.md)

Perioada **20–23 noiembrie 2026**, după ultima publicare A/B. Mașina: MacBookPro9,1, Golden Gate **27.2.1 (26B131)**. Sunt păstrate și încercările eșuate, în ordinea reală a operațiilor. Surse: Work2, Work3, arhivele CLT/LD, raportul Xcode din 23 noiembrie și probele operatorului.

| Data | Pas | Ce am făcut | Rezultat |
|:--|:--|:--|:--|
| **20 nov.** | C-01 | Continuarea construirii C; plist original `AirportBrcmFixup` necesar la validare | Blocajul constructorului depășit; C a pornit ulterior |
| **21 nov.** | C-02 | Inventar CLT 27.2, xcrun, Clang 21, SDK, Python HAO privat 3.12.14 | Reperul stabilit |
| **21 nov.** | C-03 | Trei adaptări HAO: intrare tipizată `xcrun_main`, identificare furnizor pentru două adrese dyld, `RTLD_DEFAULT` între imaginile ARM guest | Probe private reușite |
| **21 nov.** | C-04 | C/C++, `make`, extensie Python și comenzi Apple prin HAO privat | PASS, inițial fără integrare globală |
| **21 nov.** | C-05 | Diagnostic `ld`/`libLTO` și relansarea linkerului, fără eliminarea argumentelor Apple | Linkare Intel și LTO autentic PASS în testele private |
| **21 nov.** | C-06 | `clang.cfg`, `clang++.cfg`, `clang-cpp.cfg` pentru implicit `x86_64-apple-darwin` | 13 probe plus baseline PASS, păstrarea țintelor explicite |
| **21 nov.** | C-07 | Staging: 80 shimuri + 4 fișiere HAO System, 3 CFG Data | Verificare SHA completă: **84/84 + 3/3** |
| **21 nov. 23:33** | C-08 | Prima aplicare permanentă HAO, după `DeRez` eșuează la `GetFileInfo` | Tranzacție retrasă, fără snapshot nou |
| **22 nov.** | C-09 | Investigarea inodeului APFS comprimat cu 78 nume și `UF_COMPRESSED` pierdut pentru 77 | Cauza confirmată, snapshotul vechi intact |
| **22 nov. 00:55** | C-10 | Backend HAO corectat și testat în APFS privat | **8/8 probe APFS** și **11/11 offline PASS** |
| **22 nov.** | C-11 | Pe copia experimentală C: recuperarea celor 77, instalarea backendului și overlayului | HAO exit 0, **84 System + 3 Data PASS** |
| **22 nov. ~02:16** | C-12 | Reboot în noul snapshot CLT | Snapshot `672C29E6-307D-4E15-B328-714D6C35B005` confirmat pornit |
| **22 nov.** | C-13 | Diagnosticul blocajului `clang ... -o` și corecția linkerului, snapshot LD suplimentar | `54804A00-E81C-4290-A2B8-33C601D45823` selectat; testele normale C/C++/LTO/make/Python PASS |
| **22 nov.** | C-14 | Lansarea GUI Xcode 27.2 prin HAO și analiza pachetelor First Launch | GUI pornește; inițial `PKInstallErrorDomain Code=201` și `xcodebuild` 69 |
| **23 nov. 13:59** | C-15 | Proiect C nou prin `xcodebuild`, Swift Build 6.4.2 Intel și linker Apple | `** BUILD SUCCEEDED **`; programul Intel executat, `3589 → 6442255` |
| **23 nov.** | C-16 | Încă patru proiecte Xcode Intel: C++17, Objective-C, Swift, AppKit | **4/4 PASS**, aplicația AppKit inspectată |
| **23 nov.** | C-17 | Primele 10 cereri Xcode ARM/Universal folosesc destinație incompatibilă | Cod 70 înainte de compilare |
| **23 nov.** | C-18 | Repetarea cu `My Mac` și `ARCHS=arm64` / `ARCHS=x86_64 arm64` | **10/10 PASS**, câte cinci ARM și Universal 2, verificate Mach-O și `lipo` |
| **23 nov.** | C-19 | Clang direct, independent de proiectele Xcode | **ARM64-direct PASS, Universal2-direct PASS**; jurnal pe iMac |
| **22–23 nov.** | C-20 | Instalare MacPorts 2.12.7 și compilarea din surse prin HAO/CLT | Mai multe porturi instalate conform operatorului, altele încă în construcție; lista finală urmează |
| **23 nov.** | C-21 | Actualizări upstream evaluate privat pentru constructor, EFI și Metal r12; diagnostic WeatherKit/VFX | Teste de sursă, fără promovare în build C nou, fără a pretinde că Weather/EFI sunt rezolvate |

**Precizări:** compilarea ARM64 nu dovedește rularea nativă pe Apple Silicon. Pentru Xcode, buildurile CLI sunt demonstrate, dar `⌘B` interactiv și interfața AppKit cer probe distincte. Snapshotul LD este consemnat ca selectat; o probă separată de reboot din el nu trebuie inventată. Modificările Data nu se retrag doar prin revenirea la snapshotul System anterior.

**Atribuire:** HAO original [lythka](https://github.com/lythka/hao-patcher), HAO runtime, OpenCore/OCLP; adaptare 9,1 și teste fizice [StefanAlMare](https://github.com/StefanAlMare) cu asistență Codex. [Dovezi CLT](TOOLCHAIN-EVIDENCE.md) · [Dovezi Xcode](XCODE.md).