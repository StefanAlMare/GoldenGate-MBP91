# hao-patcher

[English original](README.upstream.md) · [Proiectul MacBookPro9,1 în română](README.ro.md)

Traducerea documentației originale a proiectului HAO Patcher. Rezultatele de mai jos sunt cele raportate de proiect pe MacBookPro9,2.

hao-patcher construiește imagini de disc pentru **macOS 27 (Golden Gate) pe Mac-uri Intel x86_64**. Versiunea descrisă aici este macOS 27.2.1 (26B131).

macOS 27 nu oferă suport pentru Mac-uri Intel. Imaginea combină volumele System și Data din Golden Gate cu extensiile de kernel, driverele și fișierele de pornire pentru Intel încă incluse în macOS 26 (Tahoe). OpenCore Legacy Patcher asigură suportul pentru hardware mai vechi. Imaginea include corecții de compatibilitate și hao-runtime, care execută pe procesorul Intel programele Golden Gate disponibile exclusiv pentru ARM. [hao-runtime](https://github.com/lythka/hao-runtime)

![macOS 27.2.1 pe un MacBook Pro din 2012, cu Despre acest Mac, Centrul de control și widgeturi](docs/images/desktop-intel.jpg)

[Galerie](docs/gallery.md) · [Progres](docs/progress.md) · [Construirea imaginii](docs/building.md) · [Susține autorul proiectului](https://buymeacoffee.com/lythka)

### Accelerare Metal pe Intel HD 4000

Hărți afișează imagini din satelit și clădiri 3D folosind bibliotecile de shadere Apple, adaptate pentru compilatorul Metal al HD 4000. Hărțile din Vremea au nevoie de *argument buffers* și de texturi ASTC. hao-patcher adaugă suport pentru ambele în compilatorul de shadere și în driver. [Biblioteci Metal](cache/metallib) · [Suport pentru argument buffers](tools/metal-argbuf)

<p>
<img src="docs/images/gallery/maps-3d-buildings.jpg" alt="Clădiri 3D în vederea din satelit din Hărți pe HD 4000" width="49%">
<img src="docs/images/gallery/weather-temperature-map.jpg" alt="Harta temperaturilor din Vremea pe HD 4000" width="49%">
</p>

Galeria include Safari, YouTube, hărțile vântului și ale calității aerului, WebGPU și SceneKit. [Galerie](docs/gallery.md)

## Stadiu

Versiune preliminară pentru dezvoltatori. Proiectul original a dezvoltat și a testat macOS 27.2.1 (26B131) pe MacBook Pro de 13 inchi din 2012, model MacBookPro9,2, cu Ivy Bridge și Intel HD 4000. În această versiune a documentației, proiectul original nu raportează teste pe alte Mac-uri Intel.

| Domeniu | Funcții confirmate pe MacBookPro9,2 |
|---|---|
| Pornire | Se afișează doar sigla Apple. Ecranul se aprinde la circa 46 s după pornirea kernelului (circa 50 s la prima pornire). Funcționează Asistentul de configurare, crearea contului și autentificarea automată. |
| Desktop | Bara de meniu, Dock, Finder, Liquid Glass, Centrul de control, indexarea Spotlight, fereastra de autentificare și ecranul de blocare. |
| Grafică | Accelerare Metal pe HD 4000, argument buffers, texturi ASTC și decodare video hardware (YouTube la 1080p). |
| Conectivitate | Wi-Fi din Asistentul de configurare și din Configurări sistem, reconectarea la rețelele memorate la pornire, Ethernet, Bluetooth, AirDrop, detectarea ecranelor AirPlay și redarea sunetului prin difuzoare AirPlay. |
| Audio și periferice | Difuzoare, cameră, microfon, tastele de luminozitate, iluminarea tastaturii, tastatura și trackpadul integrate, tastatură și maus USB externe. |
| Alimentare și porturi | Repaus și trezire, inclusiv la închiderea și deschiderea capacului, nivelul și încărcarea bateriei, USB 3 la viteza USB 3 și slotul pentru carduri SD. |
| Aplicații | Safari (YouTube și WebGPU), Hărți (glob 3D, imagini din satelit, clădiri 3D), Vremea (prognoze și hărți pentru temperatură, calitatea aerului și vânt), Poze, Muzică, TV, Podcasturi, Calendar, Previzualizare, App Store, Cărți, News, Bursa, Terminal și Configurări sistem. |
| 3D | Scene SceneKit cu materiale, umbre și reflexii. Quick Look și Previzualizare deschid scene SceneKit. |
| Conturi | iMessage, autentificare în App Store și instalarea aplicațiilor din App Store. |
| Programe exclusiv ARM | hao-runtime execută pe Intel programele macOS 27 disponibile exclusiv pentru ARM și aplicațiile construite numai pentru Apple silicon. |

La data documentației originale nu exista încă o versiune publicată. Următoarea versiune planificată era v0.0.1. [Versiuni planificate](https://github.com/lythka/hao-patcher/milestones)

Procedura de instalare este în curs de validare. [Instalare](#instalare)

Listele detaliate, noutățile și corecțiile individuale se găsesc în [Progres](docs/progress.md).

## Riscuri

**Protecții de securitate reduse.** Această versiune preliminară oferă un nivel de protecție mai redus decât macOS pe un Mac compatibil. System Integrity Protection este parțial dezactivat, verificarea semnăturilor prin Apple Mobile File Integrity este relaxată, iar protecția prin sigilarea volumului de sistem și Secure Boot sunt dezactivate. Instalează imaginea numai pe un Mac fără date care necesită protecție.

Folosește hao-patcher numai pe un **Mac dedicat testelor**, al cărui conținut îl poți pierde.

- Instalarea unei imagini suprascrie întregul disc țintă.
- Imaginea dezactivează AMFI, reduce protecția SIP și dezactivează verificarea volumului rădăcină (`csr-active-config` 0x803). Secure Boot este dezactivat, programele din System sunt resemnate ad-hoc, iar OpenCore încarcă extensii de kernel terțe. Modificările sunt enumerate în documentația de securitate. Vulnerabilitățile se raportează în privat. [Modificări de securitate](docs/security.md) · [Raportarea vulnerabilităților](SECURITY.md)
- hao-runtime modifică direct fișierele System și nu include un program de dezinstalare. Traducerea binară este experimentală și poate provoca închiderea programelor sau deteriorarea datelor acestora. [De citit înainte de utilizare](https://github.com/lythka/hao-runtime#read-first)
- Pentru recuperare, ține apăsată tasta Option la pornire și alege alt disc sau pornește în Internet Recovery cu Command–Option–R. Resetează NVRAM cu Command–Option–P–R, apoi șterge discul și reinstalează o versiune macOS compatibilă sau restaurează o copie de siguranță.

## Instalare

Procedura proiectului original pentru această versiune preliminară este în curs de validare. **Instalarea șterge discul intern al MacBook Pro.**

1. Obține utilitarul hao și lista de fișiere a versiunii, în ordinea următoare: `git clone --branch v0.0.1 https://github.com/lythka/hao-patcher`, `cd hao-patcher/tools/hao`, apoi `curl -LO https://github.com/lythka/hao-assets/releases/download/27.2.1-26B131.0/release.json`.
2. Execută `sudo ./hao create-installer --link-on-target`, alege unitatea USB și confirmă ștergerea ei. Păstrează unitatea la tine până la instalare. O persoană cu acces la ea poate modifica programele pe care le instalează. Înainte de instalare, hao verifică unitatea folosind manifestul, pentru a detecta deteriorări sau modificări simple.
3. Pe MacBook Pro, ține apăsată tasta Option la pornire și alege **EFI Boot**. Urmează o pauză de câteva minute fără mesaje. În Terminalul din Recovery execută `/Volumes/HAO/install`.
4. După prima pornire, rulează o singură dată `sudo /usr/libexec/hao --aot`.

Ghidul de instalare cuprinde cerințele, jurnalele de inclus într-un raport de eroare și instrucțiuni pentru construirea din surse. [Ghid de instalare](docs/install.md)

## Construirea imaginii

Ghidul de construire descrie intrările necesare, etapele de asamblare și testarea în QEMU. Documentația de arhitectură explică legăturile dintre componente, iar ghidul pentru contributori prezintă testele și convențiile proiectului. [Construirea unei imagini](docs/building.md) · [Arhitectură](docs/architecture.md) · [Contribuții](CONTRIBUTING.md)

| Director | Conținut |
|---|---|
| `pipeline/` | Asamblarea imaginii, înregistrările intrărilor, țintele și seturile de corecții |
| `patches/` | Rețete de instalare, câte un director pentru fiecare corecție. [Catalog](docs/PATCHES.md) |
| `tools/` | Instrumente pentru construirea corecțiilor, pregătirea intrărilor, lucrul cu imagini și testarea în QEMU |
| `cache/` | Generatoare de biblioteci Metal și de shadere |
| `docs/` | Stadiul proiectului, arhitectura, intrările și ghidul de construire |

## Credite

Proiectul se bazează pe [OpenCore Legacy Patcher](https://github.com/dortania/OpenCore-Legacy-Patcher), [OpenCore](https://github.com/acidanthera/OpenCorePkg), [Lilu](https://github.com/acidanthera/Lilu), [MacKernelSDK](https://github.com/acidanthera/MacKernelSDK), [MetallibSupportPkg](https://github.com/dortania/MetallibSupportPkg), [sursele XNU de la Apple](https://github.com/apple-oss-distributions/xnu) și [QEMU](https://www.qemu.org/). Fișierul NOTICE.md al fiecărui instrument enumeră sursele terțe incluse.

Acest produs include software dezvoltat de Dortania și de contributorii OpenCore Legacy Patcher.

## Licență

Codul original este disponibil sub licența MIT. Codul terț și componentele Apple își păstrează propriile condiții de utilizare. [Licență MIT](LICENSE) · [Condiții și atribuiri](NOTICE.md)
