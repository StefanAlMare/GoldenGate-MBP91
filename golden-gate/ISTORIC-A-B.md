# Golden Gate pe MacBookPro9,1 — istoricul variantelor A și B

> **Continuare:** [Build C — cronologia tehnică 20–23 noiembrie 2026](build-c/CHRONOLOGY.ro.md), inclusiv CLT, HAO, APFS, Xcode, Clang și MacPorts. Acest dosar păstrează numai etapele istorice A/B.

Între 17 și 20 noiembrie 2026, Golden Gate 27.2.1 (26B131) a ajuns de la un profil pentru MacBookPro9,1 la prima configurare pe un SSD USB, desktop și autentificare după repornire. Pe varianta B au fost confirmate fizic reparații pentru Finder, Dock, tragerea ferestrelor și deschiderea panoului Baterie. Calculatorul testat a fost un MacBook Pro de 15″, Mid 2012, cu Intel HD Graphics 4000, NVIDIA GeForce GT 650M și comutatorul grafic GMUX.

Autorul principal al HAO este **lythka**. Portarea locală și validarea pe hardware îi aparțin lui **StefanAlMare ([@StefanAlMare](https://github.com/StefanAlMare))**. Implementarea instrumentelor, a adaptărilor locale și a probelor a fost realizată cu **Codex (OpenAI)**. Componentele de pornire și driverele de compatibilitate au folosit și proiectul OpenCore Legacy Patcher.

## 17–18 noiembrie · Construirea imaginii A

| Pași | Ce s-a făcut | Ce a fost verificat |
|---|---|---|
| 2–4 | S-a derivat profilul 9,1 din constructorul HAO. S-au adăugat selecția hardware pentru Ivy Bridge, Kepler, Metal 3802, audio și Wi-Fi, apoi s-a generat EFI. | Constructorul a selectat profilul. Pachetul hardware A conținea 38 de operații. EFI de bază a trecut verificarea cu `ocvalidate`. |
| 5–8 | S-au pregătit componentele Apple 26B131 și donorii Tahoe 25G342. Arhiva de runtime cerută de rețetă era indisponibilă. S-au compilat local runtime-ul x86_64 și extensia HaoExec, apoi s-a pregătit pachetul de pornire. | Testele runtime pe gazdă au trecut. Împachetarea a verificat 963 de executabile, inclusiv `launchd` și `xpcproxy`. Pachetului îi lipseau unitățile externe de descriere a apelurilor și furnizorul asincron opțional. |
| 9–11 | S-au pregătit bibliotecile Metal, shaderul „hello” al Setup Assistant, componentele de compatibilitate pentru afișaj și rețea, KDK-ul și colecțiile de kernel. | Au fost verificate produsele compilării și prezența componentelor în colecții. Randarea pe GT 650M a fost măsurată ulterior pe MacBook. |
| 12–13 | S-a asamblat imaginea de 80 GiB și s-a scris pe SSD-ul USB extern. | S-au recitit integral cei 85 899 345 920 octeți. SHA-256 a coincis cu cel al imaginii. Apoi s-au repoziționat structurile GPT, s-a extins containerul APFS și s-a verificat EFI. |

Constructorul folosit a fost `hao-patcher` la `6bd75aab`, cu adaptările locale pentru 9,1. Ambele variante au folosit runtime-ul construit din `1547dcb4`. Binarul Intel încărcat la pornire a fost identificat în stivele capturate pe MacBook. [Constructorul HAO](https://github.com/lythka/hao-patcher/commit/6bd75aab112d1078acd8e75180eb510672461365) · [Runtime-ul HAO](https://github.com/lythka/hao-runtime/commit/1547dcb4e19a2ab0843086e3288223f998507a4c)

## 19 noiembrie · Cele trei probe ale primei configurări pe A

| Pornire | Ce s-a văzut pe MacBook |
|---|---|
| De referință | Bara s-a oprit la aproximativ 60%. WindowServer procesa evenimente. NTFS apărea deschis, iar exFAT închis. Discul RAM de 512 MiB pentru utilizatorul temporar de Setup a rămas fără partiții în 146 de citiri. |
| Cu NTFS exclus de la automontare | NTFS apărea închis, iar exFAT deschis. Discul RAM a rămas fără partiții în alte 146 de citiri. Captura păstrează starea dispozitivelor. Fișierul de configurare al acelei porniri lipsește din captură. |
| Cu NTFS și exFAT excluse | Cu câte o regulă individuală `ro,noauto` pentru cele două volume interne, operatorul a văzut Setup Assistant și a parcurs configurarea. A ajuns la desktop și s-a autentificat din nou după repornire. |

În cele două porniri blocate, DiskImages2 aștepta serviciul Disk Arbitration. În același interval, `diskarbitrationd` aștepta în `LiveFSMountClient`, iar un fir din `fskitd` se afla în apelul de montare. Stivele nu identifică volumul din acel apel. Excluderea cumulativă a permis prima configurare pe acest Mac.

În sesiunea fizică, ecranul intern fusese identificat pe Intel HD 4000. O probă Metal a selectat explicit GT 650M, a umplut o suprafață de 4 × 4 pixeli și a recitit corect toți cei 16 pixeli. Operatorul a confirmat Wi-Fi, Bluetooth, sunet, USB, tastatură, trackpad și tastele de luminozitate și volum.

## Varianta B · Ce s-a schimbat în imagine

Pentru a izola influența bibliotecilor grafice, B a păstrat driverele ambelor plăci și a eliminat cele două suprascrieri Kepler ale componentelor ImageIO și CMPhoto din Tahoe 25G229. Pachetul hardware a trecut de la 38 la 36 de operații, iar lista pentru pregătirea cache-ului a trecut de la 12 la 10 intrări. Kitul B a fost verificat, asamblat cu Preboot și EFI și personalizat cu cele două reguli de automontare. Corecțiile de mai jos au fost aplicate ulterior pe SSD-ul B.

| Artefact la momentul verificării | SHA-256 |
|---|---|
| Imaginea A, înainte de extinderea APFS | `52a930a84a37b3fdd3443636426503c716e723f7c781332d605f964ad3922f35` |
| Imaginea B, după asamblare | `35eeb62d4558ac7e094d40841e8964778001fe0cf499bce1c760a9cb5cb1c465` |
| Imaginea B, după adăugarea celor două reguli | `0294ea6d7f7560cdff96f1df877aab926ea17c51b67d9ed550eec74dcdd8757c` |

## 20 noiembrie · Reparații confirmate pe B

| Componentă | Schimbarea locală și rezultatul fizic |
|---|---|
| Finder și IconServices | Patru cereri de pictogramă pentru dosarul Aplicații înregistrau câte 73 de erori Foundation 4097. Cu agentul Apple care conține cod Intel nativ din Tahoe 25G422, aceleași patru cereri au dat zero erori. După relansarea Finder, interfața a răspuns normal. Agentul a fost instalat pe snapshot, iar operatorul a confirmat că Finder funcționează de la autentificare după repornire. |
| Dock | O descriere de apel SkyLight a corectat citirea stării butonului mouse-ului. În probă au dispărut toate cele șase indicații false de apăsare, iar retragerea corecției le-a readus. După repornire, operatorul a confirmat etichetele, mărirea pictogramelor la trecerea cursorului și reapariția Dock-ului ascuns. |
| Tragerea ferestrelor | O unitate SkyLight cumulativă a păstrat corecția Dock și a adăugat citirea stării tastei Opțiune. După instalare și repornire, ferestrele au putut fi trase obișnuit fără a declanșa mozaicul nedorit. |
| Configurări sistem → Baterie | Extensia PowerPreferences se închidea la afișarea panoului. O descriere Foundation a corectat transmiterea argumentelor pentru `DateComponents`. După repornire, panoul s-a deschis, au funcționat opțiunile și ambii selectori de perioadă. Procesul a rămas activ pe toată durata probei de 30 de secunde. |

## Ce a rămas deschis pe B

- **NTFS și exFAT.** Cererile de montare pentru citire au expirat. La repornirea cu `ro,auto` pentru ambele volume, MacBook-ul a ajuns la login, iar ambele volume erau nemontate. Componentele NTFS și exFAT au fost identificate în sistem. Extensia FSKit exFAT a pornit și a raportat recunoașterea unei resurse. Identificatorii mascați din jurnal împiedică atribuirea fiecărui mesaj unui volum. Citirea unui fișier de pe oricare dintre cele două volume rămâne neconfirmată.
- **Bara de meniu și Dock.** Zonele Wi-Fi și Bluetooth deschid meniurile, dar simbolurile native rămân invizibile. Difuzorul este vizibil. Simbolurile Wi-Fi și Bluetooth au fost afișate cu succes într-un element temporar AppKit. Deschiderea Centrului de control a produs două căderi cu aceeași stivă în `swift_setAtWritableKeyPath`. Punctul de sub aplicațiile active din Dock poate dispărea în timp ce aplicația continuă să ruleze. Aplicația Vreme se închide la lansare și pictograma ei lipsește din bară.
- **Afișarea bateriei.** Informații sistem și `pmset` citesc bateria. PowerLog conținea 31 de valori valide între 95 și 100% și 10 intervale orare cu ecranul activ. Afișarea pe 24 de ore variază la schimbarea ferestrei active, inclusiv cu ecranul intern pe Intel. Pe 10 zile s-au văzut două bare de utilizare. Pictograma din meniu rămâne incompletă.
- **Ecranul extern.** Cu adaptorul direct mini DisplayPort–HDMI, operatorul a confirmat conectarea și deconectarea la cald și comutarea Intel/NVIDIA. Cu HDMI prin hubul Thunderbolt, monitorul a funcționat dacă era conectat de la pornire. Scoaterea cablului HDMI a lăsat ambele ecrane negre și a impus oprirea din buton. Pe NVIDIA au mai fost observate artefacte în transparențe și pe unele contururi. Funcționarea pe alte Mac-uri Intel sau Hackintosh necesită validări distincte.

## Sursele etapelor

| Material | Unde se găsește |
|---|---|
| Prima configurare și capturile descrise în fișa inițială | [Stadiul 1](STADIUL-1.md) |
| Adaptările originale de constructor pentru MacBookPro9,1 | [Constructorul care a produs A](https://github.com/StefanAlMare/GoldenGate-MBP91/tree/0b3d86aba06b3c0d85fc9436f4395194664e75fe) |
| Pregătirea hardware și rețeta desktop pentru B | [Sursele constructorului B](https://github.com/StefanAlMare/GoldenGate-MBP91/blob/2a00ef190a10a2a51e069fbeb3a2f691ba387873/docs/mbp91-b-constructor.md) |
| Comparația A/B, probele grafice și pictogramele după login | [Fișa tehnică în română](https://github.com/StefanAlMare/GoldenGate-MBP91/blob/6ba34ef2f16e9442783ee9fbb724366673465670/docs/mbp91-kepler-imaging-test.ro.md) |
| Proba experimentală pentru framebuffer și alegerea GPU-ului | [Sursa și instrucțiunile probei](../patches/golden-gate-metal-framebuffer/build/README.md) |
| Rezultatele fiecărei intervenții, probele negative și cele 29 de rapoarte identificate prin SHA-256 | [Registrul tehnic B](REGISTRU-TEHNIC-B.md) |
| Sursele probelor pentru Finder, Dock, ferestre, baterie și volume | [Ghidul probelor și șabloanelor A/B](PROBE-A-B.md) |
| Construcția inițială, pe pași, cu sursele locale și amprentele rapoartelor | [Indexul etapelor 2–13 și al probelor ulterioare](etape-a/INDEX.md) |
