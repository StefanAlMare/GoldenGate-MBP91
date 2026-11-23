# Xcode 27.2 pe MacBookPro9,1 — dovezile compilării

[**Română**](XCODE.ro.md) · [**English — complete technical detail**](XCODE.md) · [Prezentare C](README.ro.md)

**23 noiembrie 2026.** Pe MacBookPro9,1 cu Golden Gate 27.2.1 (26B131), Xcode **27.2 (27B52)** a construit proiecte macOS prin `xcodebuild`, prin HAO. Folosește SDK 27.2, Apple Clang 21.0.0, linkerul Apple CLT 27.2 adaptat și serviciul **Swift Build 6.4.2 compilat pentru Intel x86_64**.

![Intel](https://img.shields.io/badge/Intel-5%2F5_PASS-247a5a?style=flat-square) ![ARM64 Universal](https://img.shields.io/badge/ARM64%2BUniversal_2-10%2F10_PASS-247a5a?style=flat-square)

## Prima compilare C prin Xcode

```text
** BUILD SUCCEEDED **
model=MacBookPro9,1 arch=x86_64 n=3589 sum=6442255
```

Suma a fost verificată independent: 3.589 × 3.590 / 2 = **6.442.255**. Programul x86_64 a fost executat pe MacBook. Executabilul are SHA-256 `006f17dc90ab2cd0e4f81da182bac35fa9986db55f4a6373009565abaa90ebdb`.

## Matricea proiectelor

| Proiect | Compilat x86_64 | Compilat ARM64 | Universal 2 | Execuție universală pe Intel |
|:--|:--:|:--:|:--:|:--|
| C | PASS | PASS | PASS | `c 400065` |
| C++17 cu libc++ | PASS | PASS | PASS | `cpp 2104` |
| Objective-C cu Foundation | PASS | PASS | PASS | `objc 1565` |
| Swift cu Foundation | PASS | PASS | PASS | `swift 3103` |
| Aplicație AppKit | PASS | PASS | PASS | Pachetul `.app` inspectat; GUI netestat |

**15 rezultate de compilare:** cinci proiecte x86_64 și încă zece compilări ARM64/Universal 2. Pentru toate cele zece builduri ulterioare `xcodebuild` a ieșit cu **cod 0**; arhitecturile au fost verificate prin antetele Mach-O și `lipo -archs`. Durata celor zece probe a fost de circa 27 minute. Dovezile originale sunt în dosarul privat `GoldenGate-Xcode-Arhitecturi-b2n9s5h0/Dovezi.zip`.

Prima încercare ARM64/Universal a avut cod 70 deoarece destinația `generic/platform=macOS` nu era acceptată. Repetarea cu destinația locală `My Mac`, `ARCHS=arm64` sau `ARCHS=x86_64 arm64` și `ONLY_ACTIVE_ARCH=NO` a reușit 10/10. Aceasta este o corecție a **selecției destinației**, nu a limbajelor de programare.

## Interfață și limite

Interfața Xcode pornește prin lansatorul Intel/HAO, iar în Locations a fost observată selecția Xcode 27.2. Problemele inițiale First Launch din 22 noiembrie (`PKInstallErrorDomain Code=201`, status 69) rămân în istoricul testelor, dar construirea proiectelor prin CLI funcționează în configurația validată.

**Nu s-au certificat încă:** `⌘B` în interfața grafică, un proiect de producție, execuția ARM64 nativă pe Apple Silicon, lansarea ferestrei AppKit și țintele iOS/simulator. Raportul în engleză are toate detaliile: [XCODE.md](XCODE.md).
