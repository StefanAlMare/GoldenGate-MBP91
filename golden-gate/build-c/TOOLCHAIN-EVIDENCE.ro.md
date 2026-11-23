# Build C — dovezi CLT, Clang și corecția HAO/APFS

[**Română**](TOOLCHAIN-EVIDENCE.ro.md) · [**English — date complete**](TOOLCHAIN-EVIDENCE.md) · [Prezentare C](README.ro.md) · [Cronologie](CHRONOLOGY.ro.md)

**Sistem testat:** MacBookPro9,1 (15″, Mid 2012), procesor Intel Ivy Bridge, Golden Gate **27.2.1 (26B131)**. Toolchain: **Command Line Tools 27.2**, **Apple Clang 21.0.0 (clang-2100.4.1.1)**, SDK macOS **27.2**, țintă implicită `x86_64-apple-darwin`. Separăm probele fizice de rezultatele comunicate de operator.

## Compilare și execuție

| Test | Dovadă consemnată | Statut |
|:--|:--|:--|
| C și C++ native x86_64 | Compilare, linkare și execuție: `GG_POSTBOOT_NATIVE_OK`, `GG_CPP_NATIVE_OK` | **PASS fizic** |
| LTO autentic și `make` | Compilare, linkare și executabil Intel rulat | **PASS fizic** |
| `xcrun` și SDK | Clang localizat în CLT; SDK 27.2 | **PASS fizic** |
| Python 3.14.10 x86_64 | Verificări `ctypes`, SQLite, SSL | **PASS fizic** |
| Clang direct ARM64 | `ARM64-direct PASS` | **PASS raportat de operator** |
| Clang direct Universal 2 | `Universal2-direct PASS` | **PASS raportat de operator** |

**Proba directă Clang din 23 noiembrie 2026**, independentă de proiectele Xcode:

```text
ARM64-direct PASS
Universal2-direct PASS
```

Raportul original este păstrat local pe iMac în `GoldenGate-C-Clang.HcenV1/Raport.jsonl`; fișierul JSONL integral **nu a fost încă publicat** și nu pretindem că a fost reanalizat aici. Pentru compilările prin Xcode există separat [matricea celor 15 builduri (RO)](XCODE.ro.md), cu verificarea antetelor Mach-O și `lipo`.

**Universal 2** înseamnă un binar ce conține **x86_64 + ARM64**. Compilarea ARM64 pe Intel **nu dovedește execuția nativă pe Apple Silicon**. Au fost demonstrate execuții Intel și ale secțiunilor x86_64 din patru programe universale Xcode.

## Integrare HAO și snapshoturi

În timpul instalării permanente, un inode APFS comprimat avea **78 de hardlinkuri**; după modificarea flagului `UF_COMPRESSED`, **77** dintre celelalte nume nu mai aveau conținut logic accesibil. Corecția backendului păstrează starea compresiei pentru legăturile rămase. A trecut **8/8 teste APFS fizice** și **11/11 teste offline**, apoi instalarea pe **copia experimentală C** a verificat **84/84 fișiere System** și **3/3 configurații Clang Data**.

Pornirea din snapshotul CLT cu UUID `672C29E6-307D-4E15-B328-714D6C35B005` a fost confirmată. Snapshotul LD ulterior (`54804A00-E81C-4290-A2B8-33C601D45823`) a fost selectat, **fără probă independentă documentată de reboot din acel snapshot**. Modificările de pe Data necesită evaluare și restaurare separate de snapshotul System.

**Codul corecției:** [diff HAO/APFS](patches/hao-livepatch-compression.patch). Este un patch pentru o versiune specifică HAO și necesită retestare înainte de aplicarea pe alte versiuni sau discuri.

**Surse și credite:** [HAO Patcher](https://github.com/lythka/hao-patcher) și [HAO runtime](https://github.com/lythka/hao-runtime) de `lythka`; OpenCore/OCLP; adaptare, teste și documentare MacBookPro9,1 de [StefanAlMare](https://github.com/StefanAlMare), cu asistență Codex. Nu redistribuim software Apple și nici loguri private. Pentru valori SHA-256 și numele rapoartelor: [versiunea tehnică completă în engleză](TOOLCHAIN-EVIDENCE.md).
