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

### Indexul de pictograme instalat pe MacBook

Sistemul Apple 26B131 și imaginea construită conțineau copii identice, octet cu octet, ale Finder.icns, GenericFolderIcon.icns, pictogramei discului intern și cataloagelor grafice Finder și CoreTypes. În sistemul Apple original și în volumele System/Data ale imaginii construite nu exista un index IconServices populat înainte de pornire.

Pe MacBook-ul pornit, depozitul comun pentru limba română conținea 243 de fișiere de pictograme cu date. Contul folosit de Setup Assistant avea deja un index pentru buildul 26B131 și limba română. Toate cele 456 de înregistrări făceau trimitere la fișiere existente pe această instalare, 228 de fișiere distincte. Contul de sistem avea și el un index compatibil, mai mic. Reparația a instalat indexul de la Setup în cache-ul contului grafic, în locul unde lipsea, apoi a relansat agentul de pictograme al acelui cont. După relansare, indexul de 720.896 de octeți era încă prezent. Depozitul comun și volumul Tahoe au rămas intacte.

StefanAlMare nu a observat o îmbunătățire vizuală înainte de repornire. După repornirea de la 16:29, indexul contului a păstrat dimensiunea, proprietarul, permisiunile și amprenta SHA-256 (`fe6be8430620640f462def2224a9738b8965be2229dfe05179bad69d22ca68c0`). În 15 secunde s-au înregistrat 6.197 de evenimente de refuz al conexiunii, 6.193 de erori la generarea imaginilor și zero erori de deschidere a indexului. Urmărirea acceselor la fișiere nu a găsit în acel interval o citire a indexului de către procesele urmărite.

Într-o captură anterioară, în 58 din 65 de eșantioane ale cozii pentru pictograme absente din cache, Finder aștepta un răspuns XPC sincron. La agentul contului s-au observat o conexiune asociată PID-ului Finder și o anulare în serviciul care primește cererile IconServices. Aceste observații explică întârzierile cererilor de pictograme. Motivul anulării și cauza simbolurilor invizibile din bara de meniu rămân de stabilit.

[Verificarea în regim de citire](diagnostics/GoldenGate-Finder-XPC.command) pe SSD-ul extern pornit a confirmat toate cele șapte amprente. Finder, iconservicesagent și iconservicesd corespund manifestului de construcție. Cele patru configurații de lansare coincid cu fișierele Apple 26B131. Și codul AOT al daemonului a trecut verificarea. Cei doi agenți și daemonul depozitului de pictograme erau porniți. Fiecare fusese lansat o singură dată.

Între 16:33:21 și 16:33:59, ora României, agentul contului a înregistrat 14.032 de refuzuri, iar Finder 14.016 erori de generare a pictogramelor cu codul Foundation 4097. În alte opt secunde, fără deschiderea unei ferestre, același agent a înregistrat 12.110 refuzuri. Din mesajele disponibile pentru al doilea interval nu reiese cine a făcut cererile. În niciunul dintre intervale nu apare motivul precis al refuzului.

### Comparația runtime-ului pe o a doua copie externă

[Rețeta folosită pentru acest Mac](https://github.com/lythka/hao-patcher/blob/6bd75aab112d1078acd8e75180eb510672461365/pipeline/inputs/golden/26B131/hao_runtime) indică pachetul complet `1547dcb-A`, cu amprenta SHA-256 `89aa3ccc61ae20c2ef1eac221413e980701e612e3fe2d837535da7164b534e09`, calculată după regulile proiectului pentru directoare, cu excluderea fișierelor AOT generate local. Ambele construcții vizează familia A a cache-ului (`262FA161`). Amprenta libhao a autorului începe cu `c7a162e2`, iar cea locală cu `11760e88`. Registrul construcției locale confirmă că au fost omise unitățile externe de interfață, bibliotecile de adaptare a apelurilor și componenta opțională pentru apeluri asincrone. [Notele autorului](https://github.com/lythka/hao-patcher/blob/6bd75aab112d1078acd8e75180eb510672461365/patches/hao-runtime/README.md#L43-L55) documentează un runtime anterior pe laptop și indică faptul că acest pachet încă aștepta proba fizică.

La 19 noiembrie, pachetul de referință complet nu era disponibil în fișierele proiectului și în arhivele verificate pe iMac, nici în versiunile publicate sau în artefactele GitHub Actions verificate la autor. Dacă pachetul devine disponibil, se poate testa integral, după verificarea amprentei, pe o a doua copie externă. SSD-ul care pornește rămâne martorul pentru comparație. Cu același cont și același volum, se verifică pictograma discului, timpul de răspuns al meniului Vizualizare și erorile XPC din timpul acelei operații. Simbolurile din bara de meniu trebuie verificate și pe ecran. Până la această probă, diferența dintre runtime-uri rămâne o ipoteză.

## Următoarea probă pe copia externă

În privința stocării, rămâne de verificat fiecare volum NTFS și exFAT separat, prin identificarea UUID-ului, montare manuală doar pentru citire, citirea unui fișier cunoscut și demontare. Pentru alte Mac-uri Intel și Hackintosh se păstrează fișe de probă independente.

## Proveniența ramurii

Ramura privată de lucru pornește din [hao-patcher fb6542d](https://github.com/lythka/hao-patcher/commit/fb6542df15fc299266f788328e41fe908dd19b3e). Pentru comparații ulterioare, reperele upstream din 19 noiembrie sunt [hao-runtime 0714743](https://github.com/lythka/hao-runtime/commit/0714743d11fc76e29e310cab79f1d9f020a4bf74) și [hao-assets 22b18bf](https://github.com/lythka/hao-assets/commit/22b18bfd7d5e7adb2ec3d71c76582b1cabb8d252). Tabelul configurației fizice identifică separat versiunile efectiv folosite la probă.

[Instantaneul surselor constructorului folosit pe 9,1](https://github.com/StefanAlMare/GoldenGate-MBP91/tree/0b3d86aba06b3c0d85fc9436f4395194664e75fe) păstrează cele zece fișiere de adaptare pe baza originală 6bd75aa. Include profilul hardware, selecția pachetelor și generarea EFI. Stările de validare din profiluri reflectă momentul construirii, anterior probei fizice. Imaginea, EFI-ul binar, intrările Apple și capturile brute rămân materiale locale.
