# MacBookPro9,1 · Prima configurare din 19 noiembrie 2026

[English](STAGE-1.md) · **Română**

StefanAlMare a pornit Golden Gate 27.2.1 (26B131) de pe un SSD USB extern pe MacBookPro9,1 și a început configurarea în Setup Assistant. Confirmarea acestei ultime probe este vizuală. Capturile detaliate disponibile în registrul local provin din pornirile anterioare, când configurarea se bloca.

## Configurația fizică

| Element | Referință |
|---|---|
| Mac | MacBook Pro 15″ Mid 2012, Ivy Bridge, Intel HD 4000, NVIDIA GeForce GT 650M, GMUX. În captura anterioară, ecranul intern era pe Intel. |
| Discuri | Tahoe/OCLP și volume NTFS și exFAT pe discul intern. Golden Gate pe SSD-ul USB extern, cu donor Tahoe 25G342. |
| Baza constructorului folosit fizic | [hao-patcher 6bd75aa](https://github.com/lythka/hao-patcher/commit/6bd75aab112d1078acd8e75180eb510672461365), cu adaptările locale pentru 9,1 |
| Runtime construit local | `1547dcb4e19a2ab0843086e3288223f998507a4c`. UUID-ul Mach-O x86_64 al libhao din stive coincide cu cel al binarului local. SHA-256 al binarului `11760e88422c301f2d99f32581902c4e891e7819110aab0565e65e14f34a1a45` |
| Imagine inițială de 80 GiB | SHA-256 `52a930a84a37b3fdd3443636426503c716e723f7c781332d605f964ad3922f35`. Amprenta precedă extinderea APFS și pornirile de pe SSD. |
| Arhiva EFI a probei | SHA-256 `5c112839a68f54f74949e5f7a4f55d7acc74187bdf5553a1e5f598b5806c14ca`. Configurația a trecut ocvalidate. |

## Trei probe succesive

| Probă | Observație |
|---|---|
| Referință | Bara se oprea la circa 60%. WindowServer procesa evenimente. În proba de referință DiskImages2, NTFS apărea cu `Open=Yes`, exFAT cu `Open=No`. Discul RAM de 512 MiB a rămas fără partiții în 146 de citiri. |
| Excluderea NTFS | NTFS a trecut la `Open=No`, exFAT la `Open=Yes`. Discul RAM a rămas fără partiții în alte 146 de citiri. Captura consemnează starea dispozitivelor, dar nu include fișierul fstab al acelei porniri. |
| Excluderea cumulativă NTFS și exFAT | Cu o regulă `ro,noauto` specifică UUID-ului fiecărui volum, StefanAlMare a văzut Setup Assistant și a început configurarea. Captura tehnică a pornirii reușite rămâne de corelat cu această observație. |

În pornirile blocate, serviciul de configurare aștepta discul RAM al utilizatorului temporar. DiskImages2 aștepta ca Disk Arbitration să termine operațiile în curs. În același interval, diskarbitrationd aștepta în LiveFSMountClient, iar fskitd avea un fir în mount(2). Stivele nu identifică volumul transmis apelului. Succesiunea probelor susține investigarea automontării pe acest Mac. Contribuția individuală a exFAT și cauza internă a blocajului rămân de stabilit.

## Următoarea probă pe copia externă

1. Cu aceeași imagine, EFI, runtime și aceleași două reguli, se consemnează finalizarea Setup și apariția Finder. Se păstrează captura asociată acelei porniri.
2. Se verifică separat o repornire, autentificarea și revenirea la desktop.
3. După un login stabil, se verifică pe rând câte un volum, identificat din nou după UUID: montare manuală doar pentru citire, citirea unui fișier cunoscut și demontare. Se consemnează rezultatul pentru fiecare sistem de fișiere.

Randarea pe GT 650M, comutarea GMUX, alte Mac-uri Intel și Hackintosh necesită probe fizice proprii. Kitul portabil din această ramură inventariază discurile și generează o previzualizare a regulilor pentru volume selectate explicit.

## Proveniența ramurii

Ramura privată de lucru pornește din [hao-patcher fb6542d](https://github.com/lythka/hao-patcher/commit/fb6542df15fc299266f788328e41fe908dd19b3e). Pentru comparații ulterioare, reperele upstream din 19 noiembrie sunt [hao-runtime 0714743](https://github.com/lythka/hao-runtime/commit/0714743d11fc76e29e310cab79f1d9f020a4bf74) și [hao-assets 22b18bf](https://github.com/lythka/hao-assets/commit/22b18bfd7d5e7adb2ec3d71c76582b1cabb8d252). Tabelul configurației fizice identifică separat versiunile efectiv folosite la probă.

[Instantaneul surselor constructorului folosit pe 9,1](https://github.com/StefanAlMare/GoldenGate-MBP91/tree/0b3d86aba06b3c0d85fc9436f4395194664e75fe) păstrează cele zece fișiere de adaptare pe baza originală 6bd75aa. Include profilul hardware, selecția pachetelor și generarea EFI. Stările de validare din profiluri reflectă momentul construirii, anterior probei fizice. Imaginea, EFI-ul binar, intrările Apple și capturile brute rămân materiale locale.
