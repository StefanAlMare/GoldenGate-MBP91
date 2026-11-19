# MacBookPro9,1 · Prima configurare din 19 noiembrie 2026

[English](STAGE-1.md) · **Română**

StefanAlMare a pornit Golden Gate 27.2.1 (26B131) de pe un SSD USB extern pe MacBookPro9,1 și a început configurarea în Setup Assistant. A confirmat vizual apariția interfeței Setup Assistant. Capturile detaliate disponibile în registrul local provin din pornirile anterioare, când configurarea se bloca.

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

## Repornirea și proba fizică Metal din 19 noiembrie

StefanAlMare a ajuns la desktop, a repornit și s-a autentificat din nou. În sesiunea respectivă, inventarul grafic arăta ecranul intern de 1680 × 1050 pe Intel HD 4000. Golden raporta Metal 2 pentru ambele plăci și 512 MB VRAM pentru GeForce GT 650M.

[Rulat pe MacBook prin SSH, testul Metal](diagnostics/metal-check.m) a selectat explicit GT 650M. Identificatorul Metal `0x1000004b7` corespunde serviciului `nvAccelerator` din IORegistry la această pornire. GPU-ul a umplut cu roșu o suprafață RGBA de 4 × 4 pixeli. Testul a copiat rezultatul într-un buffer, l-a sincronizat și a verificat fiecare pixel pe CPU.

```text
PASS: NVIDIA GeForce GT 650M | Metal render clear + readback | 16/16 pixels
```

Proba confirmă execuția operațiilor Metal de umplere și copiere pe GT 650M. Execuția shaderelor și comutarea ecranului intern prin GMUX necesită probe separate.

StefanAlMare a raportat Wi-Fi, Bluetooth, sunet, USB, trackpad și tastatură funcționale, inclusiv tastele de luminozitate și volum. Unele pictograme din bara de meniu rămâneau invizibile deși răspundeau la clic, volumele de pe desktop aveau pictograme de folder, iar în Configurări sistem lipseau pictograme. Cauza rămâne deschisă.

## Finder și IconServices după autentificare

După relansare, Finder a deschis un dosar gol. Preferințele pentru bara de cale și bara de stare au fost citite ca activate. StefanAlMare a confirmat că Finder a răspuns în cele din urmă, cu întârziere mare, iar volumele au păstrat pictogramele de folder. Lentoarea s-a manifestat și în afara volumului Tahoe.

Pe sistemul 26B131 pornit, `hao --aot --check` a confirmat cod precompilat valid pentru **Finder și iconservicesagent** în `/private/var/db/hao`. La verificări lipsea indexul IconServices al contului (`store.index`), inclusiv după repornirea confirmată a agentului. În captura anterioară apar și cereri de imagini eșuate (Foundation 4097) și conexiuni XPC refuzate. Motivul refuzurilor rămâne deschis.

Pentru comparația pe o copie separată, rețeta originală de pictograme cere depozitul comun și indexul de utilizator corespunzător, din același build 26B131. Se verifică aceeași fereastră goală, aceeași pictogramă de volum și dacă Finder mai înregistrează erori XPC. Fișierele AOT validate pot fi păstrate pentru această probă.

## Următoarea probă pe copia externă

În privința stocării, rămâne de verificat fiecare volum NTFS și exFAT separat, prin identificarea UUID-ului, montare manuală doar pentru citire, citirea unui fișier cunoscut și demontare. Pentru alte Mac-uri Intel și Hackintosh se păstrează fișe de probă independente.

## Proveniența ramurii

Ramura privată de lucru pornește din [hao-patcher fb6542d](https://github.com/lythka/hao-patcher/commit/fb6542df15fc299266f788328e41fe908dd19b3e). Pentru comparații ulterioare, reperele upstream din 19 noiembrie sunt [hao-runtime 0714743](https://github.com/lythka/hao-runtime/commit/0714743d11fc76e29e310cab79f1d9f020a4bf74) și [hao-assets 22b18bf](https://github.com/lythka/hao-assets/commit/22b18bfd7d5e7adb2ec3d71c76582b1cabb8d252). Tabelul configurației fizice identifică separat versiunile efectiv folosite la probă.

[Instantaneul surselor constructorului folosit pe 9,1](https://github.com/StefanAlMare/GoldenGate-MBP91/tree/0b3d86aba06b3c0d85fc9436f4395194664e75fe) păstrează cele zece fișiere de adaptare pe baza originală 6bd75aa. Include profilul hardware, selecția pachetelor și generarea EFI. Stările de validare din profiluri reflectă momentul construirii, anterior probei fizice. Imaginea, EFI-ul binar, intrările Apple și capturile brute rămân materiale locale.
